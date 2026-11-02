#!/usr/bin/env bash
# 매주 계정이 초기화되는 학교 AWS 계정용: 명령 하나로 서비스를 다시 올린다.
#   CloudShell에서:
#     git clone -b feature/deploy-japan https://github.com/Minyowa/MLOps-project.git
#     cd MLOps-project && bash infra/up.sh
#
#   1) EC2·보안 그룹·키 페어 생성 (이미 있으면 재사용)       — infra/create_ec2.sh
#   2) EC2 부팅 스크립트(Docker 설치)가 끝날 때까지 대기
#   3) GitHub Secrets/Variables 갱신 (EC2_HOST, EC2_SSH_KEY …) — gh CLI
#   4) GitHub Actions 배포 실행 → 끝날 때까지 대기
#   5) http://<IP>/health 로 배포 버전 확인
#
# 왜 Actions가 EC2까지 만들지 않나: 학생 계정은 IAM 역할(OIDC)을 만들 수 없고 키도 초기화되므로,
# AWS 자격 증명을 GitHub에 둘 수 없다. 대신 CloudShell(이미 로그인된 상태)에서 이 스크립트를 한 번 실행한다.
set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.env
export AWS_DEFAULT_REGION=$REGION

step() { echo; echo "==== $*"; }

# 0) gh CLI 준비 (CloudShell에는 기본 설치돼 있지 않음)
if ! command -v gh >/dev/null; then
  step "GitHub CLI 설치"
  sudo dnf install -y -q 'dnf-command(config-manager)'
  sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
  sudo dnf install -y -q gh --repo gh-cli
fi
if ! gh auth status -h github.com >/dev/null 2>&1; then
  step "GitHub 로그인 — 아래 코드를 복사해 https://github.com/login/device 에 입력하세요"
  gh auth login -h github.com -p https -w
fi

# 1) EC2
step "1/5 EC2 준비 ($REGION)"
bash infra/create_ec2.sh
# shellcheck source=/dev/null
source infra/.ec2.env

# 2) Docker 설치 완료 대기 (user-data)
step "2/5 EC2 안 Docker 설치 대기"
SSH=(ssh -i "$KEY_FILE" -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
for i in $(seq 1 40); do
  if "${SSH[@]}" "ec2-user@$IP" 'test -f /var/log/linkguard-bootstrap.log && docker compose version' 2>/dev/null; then
    break
  fi
  [ "$i" = 40 ] && { echo "❌ 10분 안에 Docker 설치가 끝나지 않았어요"; exit 1; }
  sleep 15
done

# 3) GitHub 설정 — IP와 키가 매주 바뀌므로 매번 덮어쓴다
step "3/5 GitHub Secrets/Variables 갱신 ($GH_REPO)"
gh secret set EC2_HOST -R "$GH_REPO" -b "$IP"
gh secret set EC2_SSH_KEY -R "$GH_REPO" < "$KEY_FILE"
gh variable set AWS_REGION -R "$GH_REPO" -b "$REGION"
gh variable set S3_BUCKET -R "$GH_REPO" -b "$BUCKET"
gh variable set LOG_SINKS -R "$GH_REPO" -b "$LOG_SINKS"

# 4) 배포 실행
step "4/5 GitHub Actions 배포 ($DEPLOY_BRANCH)"
if gh workflow run ci-cd.yml -R "$GH_REPO" --ref "$DEPLOY_BRANCH" -f deploy=true 2>/dev/null; then
  # 수동 실행 버튼(workflow_dispatch)은 워크플로가 main에 merge된 뒤부터 쓸 수 있음
  sleep 8
  RUN_ID=$(gh run list -R "$GH_REPO" -w ci-cd -b "$DEPLOY_BRANCH" -e workflow_dispatch -L 1 --json databaseId -q '.[0].databaseId')
else
  # merge 전: 이 브랜치의 마지막 push 실행을 다시 돌린다 (새 Secrets 값으로 실행됨)
  RUN_ID=$(gh run list -R "$GH_REPO" -w ci-cd -b "$DEPLOY_BRANCH" -e push -L 1 --json databaseId -q '.[0].databaseId')
  [ -n "$RUN_ID" ] || { echo "❌ $DEPLOY_BRANCH 브랜치에 push 실행 기록이 없어요. 커밋을 하나 push하세요"; exit 1; }
  gh run rerun "$RUN_ID" -R "$GH_REPO"
  # 재실행이 시작돼 상태가 completed에서 바뀔 때까지 기다린 뒤 지켜본다 (안 그러면 이전 결과를 보고 바로 끝남)
  for _ in $(seq 1 20); do
    [ "$(gh run view "$RUN_ID" -R "$GH_REPO" --json status -q .status)" != completed ] && break
    sleep 3
  done
fi
echo "Actions: https://github.com/$GH_REPO/actions/runs/$RUN_ID"
gh run watch "$RUN_ID" -R "$GH_REPO" --exit-status --interval 15

# 5) 확인
step "5/5 배포 확인"
curl -fsS "http://$IP/health"
echo
echo
echo "✅ 접속 주소: http://$IP/"
echo "   이번 주 IP가 바뀌었으니 PR·과제 캡처에는 새 주소 화면을 쓰세요."
echo "   다 쓰면 종료: aws ec2 terminate-instances --instance-ids $INSTANCE_ID"
