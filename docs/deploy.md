# LinkGuard 배포 가이드 (Docker → EC2, GitHub Actions / AWS CLI)

## 1. 인프라 구성

```
 개발자 ── git push ──▶ GitHub ──▶ GitHub Actions ──────────────────────────────┐
                                    ① 테스트 (pytest 54개)                       │
                                    ② Docker 이미지 빌드 + 컨테이너 스모크 테스트   │
                                    ③ GHCR(ghcr.io)에 이미지 푸시 (sha 태그)       │
                                    ④ SSH로 EC2 접속 → docker compose pull/up     │
                                    ⑤ http://EC2/health 의 app_version 확인       │
                                                                                ▼
 사용자(브라우저) ── HTTP :80 ──▶ EC2 (Amazon Linux 2023, t3.small, 도쿄 리전)
                                 └ Docker Compose
                                    └ linkguard 컨테이너 (FastAPI :8000, 모델 포함)
                                         ├─▶ CloudWatch Logs  /linkguard/app   (검사·신고 로그)
                                         └─▶ S3  linkguard-logs-<계정>/logs/{check,feedback}/dt=YYYY-MM-DD/
                                 └ 인스턴스 프로필(IAM 역할) — 키 없이 CloudWatch·S3에 기록
```

| 선택 | 이유 |
|---|---|
| **EC2 + Docker Compose** | 컨테이너 1개짜리 서비스에 가장 단순. 서버 안에서 `docker compose ps/logs`로 바로 확인 가능 |
| ECS(Fargate)는 다음 단계 | 태스크 정의·ALB·IAM 역할이 더 필요. 사용자가 늘면 같은 이미지를 그대로 옮길 수 있음 |
| **도쿄 리전(ap-northeast-1)** | 사용자가 일본에 있으므로 지연 시간 최소화. AWS Academy Learner Lab은 `us-east-1`만 되는 경우가 많아 `REGION`으로 변경 가능 |
| **GHCR** | 저장소가 GitHub에 있어 별도 AWS 자격 증명 없이 `GITHUB_TOKEN`으로 푸시 가능. Learner Lab 키가 4시간마다 바뀌는 문제를 피함 |
| **인스턴스 프로필** | 컨테이너가 IAM 역할로 CloudWatch·S3에 기록 → 액세스 키를 서버나 GitHub에 두지 않음. 컨테이너에서 역할을 쓰려면 IMDSv2 hop limit 2 필요(스크립트에 반영) |
| t3.small | 모델(3.5MB) + FastAPI는 메모리 수백 MB. EC2 위에서 이미지 빌드(CLI 방식)까지 하려면 1GB인 t3.micro는 빠듯함 |

## 2. 처음 한 번: EC2 만들기 (AWS CLI)

```bash
aws configure            # 또는 Learner Lab의 AWS Details → 자격 증명 붙여넣기
bash infra/create_ec2.sh # 키 페어, 보안 그룹(22: 내 IP, 80: 전체), EC2(Docker 설치), S3 버킷 생성
```
출력되는 **공인 IP**와 **S3 버킷 이름**을 적어 두세요. 설정은 `infra/config.env`에서 바꿀 수 있어요 (리전, 인스턴스 타입, 인스턴스 프로필).

## 3. 배포 자동화 — 방법 A: GitHub Actions (`.github/workflows/ci-cd.yml`)

**설정** (GitHub 저장소 → Settings → Secrets and variables → Actions)

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `EC2_HOST` | EC2 공인 IP |
| Secret | `EC2_SSH_KEY` | `~/.ssh/linkguard-key.pem` 파일 내용 전체 |
| Variable | `S3_BUCKET` | create_ec2.sh가 출력한 버킷 이름 |
| Variable | `AWS_REGION` | 예: `ap-northeast-1` |

- GitHub 러너의 IP는 고정돼 있지 않아서, 보안 그룹의 22번 포트를 러너에도 열어야 합니다. 과제용이라면 22번을 `0.0.0.0/0`으로 열고 **키 인증만** 쓰는 방식이 가장 간단합니다. 실서비스에서는 SSM Run Command나 self-hosted runner로 바꾸는 게 좋아요.
- GHCR 패키지는 처음엔 비공개로 만들어집니다. 배포 단계가 `GITHUB_TOKEN`으로 EC2에서 로그인해서 받으므로 그대로 써도 됩니다.

**실행**
- PR을 올리면: 테스트 → 이미지 빌드 → 컨테이너 스모크 테스트 (배포 안 함)
- `main` 또는 `feature/deploy-*` 브랜치에 push: 위 + GHCR 푸시 + EC2 배포 + 버전 확인
- **Actions → ci-cd → Run workflow**(수동 실행)도 같지만, 이 버튼은 워크플로 파일이 main에 merge된 뒤에만 보여요. 그 전에는 `feature/deploy-japan` 브랜치에 push해서 배포하세요.
- 비밀값이 없으면 배포 단계는 "건너뜀" 안내만 남기고 성공 처리돼요.

## 4. 배포 자동화 — 방법 B: 로컬에서 AWS CLI 스크립트 (`infra/deploy.sh`)

```bash
S3_BUCKET=linkguard-logs-<계정ID> bash infra/deploy.sh feature/deploy-japan
```
1. `aws ec2 describe-instances`로 `Name=linkguard` 태그가 붙은 EC2를 찾고
2. SSH로 접속해 해당 커밋을 받아 `docker compose up -d --build`
3. `http://<IP>/health`의 `app_version`이 그 커밋인지 확인하고 끝냅니다.

방법 A는 "검증된 같은 이미지"를 배포하고, 방법 B는 EC2에서 같은 Dockerfile로 다시 빌드해요. 둘 다 `app_version`으로 어떤 커밋이 떠 있는지 확인할 수 있어요.

## 5. 웹으로 동작 확인 (과제 6)
- `http://<EC2 IP>/` 에 접속해 링크를 검사하고 「詐欺だった / 安全だった」를 눌러 봅니다.
- 화면 맨 아래 `app <커밋>` 표시와 `http://<EC2 IP>/health`로 배포 버전을 확인해요.
- CloudWatch 콘솔 → 로그 그룹 `/linkguard/app`, S3 콘솔 → `logs/check/`, `logs/feedback/`에서 로그를 확인해요.

## 6. 문구 수정 후 재배포 (과제 7)
1. `app/static/index.html`의 `title` 문구 한 줄을 바꾸고 커밋·푸시합니다.
   예: `title: "届いたリンク、開く前にチェック"` → `"届いたリンク、開く前に必ずチェック"`
2. `feature/deploy-japan` 브랜치에 push하면 Actions가 자동으로 배포해요 (또는 `bash infra/deploy.sh feature/deploy-japan`).
3. 확인할 것
   - Actions 로그 마지막에 `✅ http://<IP> 에 <새 커밋> 배포 완료`가 찍혀요.
   - 웹 화면의 제목이 바뀌고, 맨 아래 `app` 버전이 새 커밋으로 바뀌어요.
   - 같은 Dockerfile·compose·환경변수로 떠서, 모델 버전과 로그 설정은 이전과 같아요.

## 7. 되돌리기 (롤백)
```bash
# 이전 커밋 이미지로 되돌리기 (EC2에서)
cd /opt/linkguard && IMAGE=ghcr.io/minyowa/mlops-project:<이전 sha> APP_VERSION=<이전 sha> PORT=80 docker compose up -d --no-build
```

## 8. 정리 (비용)
과제가 끝나면 EC2를 종료하세요. 콘솔이나 `aws ec2 terminate-instances --instance-ids <ID>`로 할 수 있어요. t3.small 도쿄 리전 온디맨드 요금 기준으로 켜 두면 하루 약 0.65달러 정도예요 (요금은 바뀔 수 있으니 콘솔에서 확인하세요).
