#!/bin/bash
# EC2 첫 부팅 때 한 번 실행 (Amazon Linux 2023): Docker + Compose 플러그인 + git 설치
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user
mkdir -p /usr/local/lib/docker/cli-plugins
ARCH=$(uname -m)
curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-${ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
mkdir -p /opt/linkguard/logs && chown -R ec2-user /opt/linkguard && chown 10001 /opt/linkguard/logs
echo "linkguard bootstrap done" > /var/log/linkguard-bootstrap.log
