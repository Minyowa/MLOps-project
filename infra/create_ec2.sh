#!/usr/bin/env bash
# AWS CLI로 배포용 EC2 1대를 만든다 (처음 한 번).
#   사용법: bash infra/create_ec2.sh
#   만드는 것: 키 페어, 보안 그룹(22: 내 IP만, 80: 전체), Amazon Linux 2023 EC2(Docker 설치), S3 로그 버킷
set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.env
export AWS_DEFAULT_REGION=$REGION

echo "== 리전 $REGION, 계정 $(aws sts get-caller-identity --query Account --output text)"

# 1) 키 페어 (없을 때만 만들고 .pem 저장)
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  mkdir -p "$(dirname "$KEY_FILE")"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query KeyMaterial --output text > "$KEY_FILE"
  chmod 400 "$KEY_FILE"
  echo "키 페어 생성: $KEY_FILE"
fi

# 2) 보안 그룹 (기본 VPC)
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$NAME-sg" Name=vpc-id,Values="$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$NAME-sg" --description "LinkGuard web" --vpc-id "$VPC_ID" \
          --query GroupId --output text)
  MY_IP=$(curl -fsS https://checkip.amazonaws.com)
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP/32"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0
  echo "보안 그룹 생성: $SG_ID (SSH는 $MY_IP 에서만)"
  echo "※ GitHub Actions로 배포하려면 22번 포트를 Actions 러너에도 열어야 합니다 (docs/deploy.md 참고)"
fi

# 3) 최신 Amazon Linux 2023 AMI
AMI_ID=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
         --query Parameter.Value --output text)

# 4) EC2 생성 — 컨테이너 안에서 인스턴스 역할(IMDSv2)을 쓰려면 hop limit 2가 필요
PROFILE_ARG=()
if [ -n "$INSTANCE_PROFILE" ] && aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE" >/dev/null 2>&1; then
  PROFILE_ARG=(--iam-instance-profile "Name=$INSTANCE_PROFILE")
else
  echo "인스턴스 프로필 없음 → CloudWatch/S3 로그를 쓰려면 나중에 권한을 붙이세요"
fi
INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" "${PROFILE_ARG[@]}" \
  --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2 \
  --user-data file://infra/user-data.sh \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "EC2 생성 중: $INSTANCE_ID"
aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID"
IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

# 5) 로그 버킷 (이름은 계정 ID로 유일하게)
BUCKET="$NAME-logs-$(aws sts get-caller-identity --query Account --output text)"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || {
  if [ "$REGION" = "us-east-1" ]; then aws s3api create-bucket --bucket "$BUCKET"
  else aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint="$REGION"; fi
}

echo
echo "== 완료"
echo "   인스턴스 : $INSTANCE_ID ($IP)"
echo "   S3 버킷  : $BUCKET"
echo "   다음 단계: S3_BUCKET=$BUCKET bash infra/deploy.sh"
