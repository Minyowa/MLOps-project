#!/usr/bin/env bash
# AWS CLI + SSH로 EC2에 배포한다 (GitHub Actions 없이 로컬에서 실행하는 방법).
#   사용법: S3_BUCKET=<버킷> bash infra/deploy.sh [git-ref]      (기본 ref: 현재 브랜치)
#   하는 일: 태그로 EC2 찾기 → EC2에서 해당 커밋 받기 → docker compose 빌드·재시작 → /health로 버전 확인
set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.env
export AWS_DEFAULT_REGION=$REGION
REF=${1:-$(git rev-parse --abbrev-ref HEAD)}
SHA=$(git rev-parse --short "origin/$REF" 2>/dev/null || git rev-parse --short "$REF")
LOG_SINKS=${LOG_SINKS:-local,cloudwatch,s3}
S3_BUCKET=${S3_BUCKET:?S3_BUCKET을 지정하세요 (create_ec2.sh가 출력한 버킷 이름)}

IP=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=running" \
     --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
[ "$IP" = "None" ] && { echo "실행 중인 '$NAME' EC2가 없습니다. infra/create_ec2.sh를 먼저 실행하세요."; exit 1; }
echo "== $REF ($SHA) → $IP 배포"

# 변수는 로컬에서 채워서 보낸다 (의도된 동작)
# shellcheck disable=SC2087
ssh -o StrictHostKeyChecking=accept-new -i "$KEY_FILE" "ec2-user@$IP" bash -s <<REMOTE
set -euo pipefail
if [ ! -d "$APP_DIR/.git" ]; then git clone "$REPO_URL" "$APP_DIR.tmp" && cp -a "$APP_DIR.tmp/." "$APP_DIR/" && rm -rf "$APP_DIR.tmp"; fi
cd "$APP_DIR"
git fetch --all --quiet && git checkout --quiet "$SHA"
mkdir -p logs && sudo chown 10001 logs
APP_VERSION=$SHA IMAGE=linkguard:$SHA PORT=80 LOG_SINKS=$LOG_SINKS S3_BUCKET=$S3_BUCKET AWS_DEFAULT_REGION=$REGION \
  docker compose up -d --build
docker image prune -f >/dev/null
REMOTE

echo "== 상태 확인"
for _ in $(seq 1 30); do
  if HEALTH=$(curl -fsS "http://$IP/health" 2>/dev/null); then
    echo "$HEALTH"
    echo "$HEALTH" | grep -q "\"app_version\":\"$SHA\"" && { echo "✅ 배포 완료: http://$IP  (app_version=$SHA)"; exit 0; }
  fi
  sleep 5
done
echo "❌ /health에서 app_version=$SHA 를 확인하지 못했습니다"; exit 1
