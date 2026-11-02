#!/usr/bin/env bash
# AWS CLI로 배포용 EC2 1대를 만든다. 여러 번 실행해도 안전 (이미 있는 건 다시 쓰고, 없는 것만 만든다).
#   사용법: bash infra/create_ec2.sh
#   만드는 것: 키 페어, 보안 그룹(22: SSH_CIDR, 80: 전체), Amazon Linux 2023 EC2(Docker 설치), S3 로그 버킷
#   매주 계정이 초기화되는 환경이면 이 스크립트 대신 infra/up.sh (EC2 생성 + GitHub 설정 + 재배포)를 쓰세요.
set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.env
export AWS_DEFAULT_REGION=$REGION

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "== 리전 $REGION, 계정 $ACCOUNT"

# 0) 이미 실행 중인 EC2가 있으면 그대로 사용
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

# 1) 키 페어 — AWS에 없거나, AWS에는 있는데 이 PC에 .pem이 없으면(CloudShell 초기화 등) 새로 만든다
new_key() {
  mkdir -p "$(dirname "$KEY_FILE")"
  rm -f "$KEY_FILE"   # 이전 .pem이 읽기 전용(400)이면 덮어쓰기가 안 되므로 지우고 만든다
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query KeyMaterial --output text > "$KEY_FILE"
  chmod 400 "$KEY_FILE"
  echo "키 페어 생성: $KEY_FILE"
}
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  if [ "$INSTANCE_ID" != "None" ] && [ -f "$KEY_FILE" ]; then
    echo "AWS의 키 페어는 지워졌지만 EC2와 .pem은 남아 있어 그대로 사용"
  else
    new_key
  fi
elif [ ! -f "$KEY_FILE" ]; then
  if [ "$INSTANCE_ID" != "None" ]; then
    echo "❌ 실행 중인 EC2($INSTANCE_ID)의 키 파일 $KEY_FILE 이 없습니다. EC2를 종료한 뒤 다시 실행하세요:"
    echo "   aws ec2 terminate-instances --instance-ids $INSTANCE_ID"
    exit 1
  fi
  aws ec2 delete-key-pair --key-name "$KEY_NAME"
  new_key
fi

# 2) 보안 그룹 (기본 VPC). 이미 있으면 규칙만 보장
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$NAME-sg" Name=vpc-id,Values="$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$NAME-sg" --description "LinkGuard web" --vpc-id "$VPC_ID" \
          --query GroupId --output text)
  echo "보안 그룹 생성: $SG_ID"
fi
allow() {  # 같은 규칙이 이미 있으면 AWS가 오류를 내므로 무시
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port "$1" --cidr "$2" >/dev/null 2>&1 || true
}
allow 22 "$SSH_CIDR"     # GitHub Actions 러너가 SSH로 배포 (키 인증만 허용)
allow 80 0.0.0.0/0       # 웹 서비스

# 3) EC2 — 없을 때만 생성
if [ "$INSTANCE_ID" = "None" ]; then
  AMI_ID=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
           --query Parameter.Value --output text)
  # 컨테이너 안에서 인스턴스 역할(IMDSv2)을 쓰려면 hop limit 2가 필요
  PROFILE_ARG=()
  if [ -n "$INSTANCE_PROFILE" ] && aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE" >/dev/null 2>&1; then
    PROFILE_ARG=(--iam-instance-profile "Name=$INSTANCE_PROFILE")
  else
    echo "인스턴스 프로필 없음 → 로그는 컨테이너 로컬 파일에만 기록 (LOG_SINKS=local)"
  fi
  INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" "${PROFILE_ARG[@]}" \
    --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2 \
    --user-data file://infra/user-data.sh \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'Instances[0].InstanceId' --output text)
  echo "EC2 생성 중: $INSTANCE_ID (2~4분)"
else
  echo "기존 EC2 사용: $INSTANCE_ID"
fi
aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID"
IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

# 4) 로그 버킷 (이름은 계정 ID로 유일하게). 권한이 없으면 건너뜀
BUCKET="$NAME-logs-$ACCOUNT"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || {
  if [ "$REGION" = "us-east-1" ]; then aws s3api create-bucket --bucket "$BUCKET" >/dev/null
  else aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint="$REGION" >/dev/null; fi
} || echo "S3 버킷을 만들지 못했어요 (권한 없음) — 서비스에는 영향 없음"

# 5) 고정 IP (Elastic IP) — EC2를 새로 만들어도 같은 주소로 접속되게, 이름표로 찾아 다시 붙인다
if [ "$USE_EIP" = 1 ]; then
  ALLOC_ID=$(aws ec2 describe-addresses --filters "Name=tag:Name,Values=$NAME-eip" \
             --query 'Addresses[0].AllocationId' --output text)
  if [ "$ALLOC_ID" = "None" ]; then
    ALLOC_ID=$(aws ec2 allocate-address --domain vpc \
      --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME-eip}]" \
      --query AllocationId --output text) || ALLOC_ID=None
    [ "$ALLOC_ID" != "None" ] && echo "고정 IP 새로 발급: $ALLOC_ID"
  fi
  if [ "$ALLOC_ID" != "None" ] &&
     aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --allow-reassociation >/dev/null; then
    IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)
    echo "고정 IP 연결: $IP"
  else
    echo "⚠️ 고정 IP를 쓸 수 없어 자동 배정 IP($IP)를 사용합니다 (권한 확인 필요)"
  fi
fi

# infra/up.sh가 읽는 결과
cat > infra/.ec2.env <<EOF
INSTANCE_ID=$INSTANCE_ID
IP=$IP
BUCKET=$BUCKET
EOF

echo
echo "== 완료"
echo "   인스턴스 : $INSTANCE_ID ($IP)"
echo "   S3 버킷  : $BUCKET"
