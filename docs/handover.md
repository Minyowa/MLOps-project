# LinkGuard 처음 받는 사람을 위한 실행·배포 가이드

이 문서만 보고 **내 GitHub 저장소(fork) → 학교 AWS 계정의 EC2**까지 배포하고 동작을 확인할 수 있게 쓴 문서입니다.
걸리는 시간: 처음 30분 정도 (대부분 자동으로 진행되는 시간)

> 서비스가 무엇인지는 [README 1. 서비스 정의](../README.md#1-서비스-정의)를 먼저 읽어 주세요.
> 한 줄 요약: 받은 링크를 열기 전에 붙여 넣으면, 기관을 사칭한 피싱인지 주소만 보고 판정해 주는 웹 서비스입니다.

## 0. 전체 그림

```
내 GitHub 저장소 (fork)
  └─ GitHub Actions ci-cd: 테스트 → 도커 이미지 빌드 → GHCR(ghcr.io/<내아이디>/mlops-project)에 저장 → SSH로 EC2에 배포
AWS (학교 계정, 서울 리전)
  └─ CloudShell에서 infra/up.sh 한 번 실행
       ├─ EC2·보안 그룹·키 페어·고정 IP 만들기 (이름: linkguard-<내아이디>)
       ├─ 내 저장소의 GitHub Secrets/Variables 자동 등록 (EC2 주소·키 등)
       └─ Actions 배포 실행 → 끝날 때까지 기다렸다가 접속 주소 출력
EC2 안: Docker 컨테이너 1개 (웹 화면 + API + 모델) → 로그는 CloudWatch /linkguard-<내아이디>/app
```

**학교 AWS 계정은 여러 명이 같이 쓰는 계정**입니다. 그래서 모든 AWS 자원 이름에 GitHub 아이디를 붙여(`linkguard-<내아이디>`) 다른 사람 자원과 겹치지 않게 했습니다. 따로 설정할 필요는 없습니다.

## 1. 준비물

| 준비물 | 확인 방법 |
|---|---|
| GitHub 계정 | 로그인되는지 |
| 학교 AWS 계정 콘솔 로그인 | 오른쪽 위 리전을 **아시아 태평양(서울)** 으로 |
| CloudShell 사용 가능 | 콘솔 위쪽 `>_` 아이콘을 누르면 터미널이 열리는지 |

내 PC에 설치할 것은 없습니다. 모든 작업은 브라우저(GitHub, AWS 콘솔)와 CloudShell에서 합니다.

## 2. GitHub: 저장소 fork 하기 (3분)

1. https://github.com/Minyowa/MLOps-project 오른쪽 위 **Fork** 클릭
2. **"Copy the `main` branch only" 체크를 반드시 해제**하고 Create fork
   - 실제 코드는 `main`이 아니라 `feature/handover` 브랜치에 있습니다. 체크된 채로 만들면 빈 저장소가 됩니다.
3. 내 fork에서 **Settings → General → Default branch** 를 `feature/handover` 로 바꾸기 (⇄ 버튼 → 선택 → Update)
   - 수동 배포 실행(workflow_dispatch)이 기본 브랜치에 있는 워크플로만 찾기 때문입니다.
   - **4단계보다 먼저** 하세요. 기본 브랜치가 `main`인 채로 Actions 탭을 열면 "Get started with GitHub Actions" 화면만 나옵니다. 이때 Configure는 누르지 마세요.
4. 내 fork의 **Actions** 탭 → **"I understand my workflows, go ahead and enable them"** 클릭
   - fork는 보안상 Actions가 꺼진 채로 만들어집니다. 이걸 안 누르면 배포가 시작되지 않습니다.

## 3. (선택) 내 PC에서 먼저 띄워 보기

Docker Desktop이 있으면 배포 전에 화면을 볼 수 있습니다. 없으면 건너뛰세요.

```bash
git clone https://github.com/<내아이디>/MLOps-project.git
cd MLOps-project
docker compose up --build        # → http://localhost:8080
```

## 4. AWS: 배포하기 (명령 두 줄, 5~10분)

CloudShell(서울 리전)에서 실행합니다. **한 줄씩** 붙여 넣으세요. 여러 줄을 한 번에 붙이면 앞 명령이 도는 동안 뒤 줄이 입력으로 빨려 들어가 실행되지 않습니다.

```bash
git clone https://github.com/<내아이디>/MLOps-project.git
```
```bash
cd MLOps-project && bash infra/up.sh
```

진행 중에 손이 가는 곳은 GitHub 로그인 한 번뿐입니다.

| 화면에 나오는 것 | 할 일 |
|---|---|
| `Authenticate Git with your GitHub credentials? (Y/n)` | **Y** |
| `! First copy your one-time code: XXXX-XXXX` | 코드를 복사해 https://github.com/login/device 에 입력 → **Authorize github** |
| `AccessDenied ... iam:...` 같은 빨간 줄 (안 나올 수도 있음) | 무시해도 됩니다 (학생 계정은 IAM 역할을 못 만듦 → 학교가 만들어 둔 역할을 씀) |
| `curl: (7) Failed to connect` (배포 확인 단계 첫 줄) | 정상입니다. 컨테이너가 뜨는 중이라 다시 시도해서 성공합니다 |

마지막에 이렇게 나오면 성공입니다.
```
✅ 접속 주소: http://<EC2 IP>/
   로그: CloudWatch 로그 그룹 /linkguard-<내아이디>/app
```

### up.sh가 자동으로 정하는 값

| 값 | 어디서 정해지나 | 예 |
|---|---|---|
| GitHub 저장소 | clone한 폴더의 `origin` 주소 | `<내아이디>/MLOps-project` |
| 배포 브랜치 | 지금 체크아웃한 브랜치 | `feature/handover` |
| 리전 | CloudShell에서 고른 리전 | `ap-northeast-2` |
| AWS 자원 이름 | `linkguard-` + GitHub 아이디(소문자) | `linkguard-honggildong` |
| SSH 키 파일 | CloudShell 홈 폴더 | `~/.ssh/linkguard-<내아이디>-key.pem` |
| CloudWatch 로그 그룹 | 자원 이름 | `/linkguard-<내아이디>/app` |
| EC2 권한(인스턴스 프로필) | 학교가 만들어 둔 역할 | `yeonsung-ec2-cloudwatch-role` |

다른 값을 쓰고 싶으면 실행할 때 앞에 붙이면 됩니다. 예: `INSTANCE_TYPE=t3.micro bash infra/up.sh`
(전체 목록: `infra/config.env`)

### GitHub에 자동 등록되는 것 (손으로 넣을 필요 없음)

내 fork의 Settings → Secrets and variables → Actions 에서 확인할 수 있습니다.

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `EC2_HOST` | EC2 공인 IP |
| Secret | `EC2_SSH_KEY` | SSH 키 파일 내용 |
| Variable | `AWS_REGION`, `S3_BUCKET`, `LOG_SINKS`, `CW_LOG_GROUP` | 리전, 로그 버킷, `local,cloudwatch`, 로그 그룹 |

## 5. 동작 확인 체크리스트

| # | 확인 | 정상일 때 |
|---|---|---|
| 1 | 브라우저에서 `http://<EC2 IP>/health` | `"status":"ok"`, `"brand_region":"jp,kr"`, `"log_sinks":["local","cloudwatch"]`, `"log_sinks_failed":{}` |
| 2 | `http://<EC2 IP>/` 에서 `https://kuronekoyamato-delivery.top/jp` 검사 | **危険(위험)**, 야마토운수 사칭 + 공식 주소 안내 |
| 3 | 화면을 **한국어**로 바꾸고 `https://cjlogistics-delivery.top/track` 검사 | **위험**, CJ대한통운 사칭 + 공식 주소 `cjlogistics.com` |
| 4 | `https://www.naver.com`, `https://www.yahoo.co.jp` 검사 | **안전** |
| 5 | 결과 아래 「詐欺だった / 사기였어요」 클릭 | "사기였다고 기록했어요." 메시지, 통계의 결과 보고 수 증가 |
| 6 | AWS 콘솔 → CloudWatch → 로그 그룹 `/linkguard-<내아이디>/app` | `"event": "check"`, `"event": "feedback"` 로그 |
| 7 | 화면 맨 아래 | `app <커밋7자리> · model char3-5_lr+fb270@… · brands jp,kr` |

검증 기록 (2026-11-16, 서울 리전, app `9029866`)
- cucumbersoap: 이 문서만 보고 fork부터 배포까지 진행, 체크리스트 7/7 통과 (약 10분) — PR #7
- jyh0729: 배포 + 7번 재학습까지 진행, retrain 성공 (7분 32초, 검역 13건, 카나리·게이트 통과) — PR #8

브라우저 주소창의 "주의 요함" 표시는 HTTPS가 아니라서 나오는 것입니다(과제용 HTTP 배포).

## 6. 코드를 고친 뒤 다시 배포하기

같은 환경으로 다시 배포하는 방법은 두 가지입니다.

```bash
# A. CloudShell에서 수동 실행 (어느 브랜치든)
gh workflow run ci-cd.yml -R <내아이디>/MLOps-project --ref <브랜치> -f deploy=true
# -R을 빼려면 처음 한 번: gh repo set-default <내아이디>/MLOps-project  (원본 Minyowa 말고 내 fork 선택)
```
- B. `feature/deploy-` 로 시작하는 브랜치나 `main`에 push하면 자동으로 배포됩니다.

배포가 끝나면 `/health`의 `app_version`이 새 커밋 번호로 바뀝니다. (Actions 로그 마지막 줄: `✅ http://*** 에 <커밋> 배포 완료`)

## 7. (선택) 신고 로그로 재학습하기

```bash
cd ~/MLOps-project && source infra/config.env && mkdir -p logs
git config --global user.name "<GitHub아이디>"; git config --global user.email "<이메일>"   # CloudShell에서 처음 한 번 (커밋에 필요)
aws logs filter-log-events --log-group-name "$CW_LOG_GROUP" --output json > logs/cloudwatch.json
python3 scripts/prepare_feedback.py logs/cloudwatch.json          # → data/feedback/feedback_<날짜>.csv
git checkout -b feature/retrain-<이름>
git add data/feedback && git commit -m "data: 신고 데이터" && git push -u origin feature/retrain-<이름>
```
- push하면 Actions **retrain** 이 재학습 → 검역·카나리·품질 게이트 → 새 모델 커밋 → 배포까지 합니다 (10분 정도).
- 재학습은 운영 서버에 배포되므로 `main`, `feature/retrain-*` 브랜치에서만 돕니다.
- 신고 기준은 [README "사기"의 범위](../README.md#사기의-범위--신고-기준이기도-함)를 따르세요. 성인·불법 사이트를 "사기"로 신고하면 모델이 오염됩니다.

## 8. 문제 해결

실제로 배포하면서 겪은 문제들입니다.

| 증상 | 원인 | 해결 |
|---|---|---|
| `❌ Actions 배포를 시작하지 못했어요` / `could not find any workflows named ci-cd.yml` | fork에서 Actions가 꺼져 있거나, 기본 브랜치에 워크플로가 없음 | 2번의 3·4단계 (기본 브랜치 `feature/handover`, Actions 사용 버튼) 후 `bash infra/up.sh` 다시 실행 |
| Actions 탭에 "Get started with GitHub Actions" 화면만 나옴 | 기본 브랜치가 아직 `main` | 2번의 3단계(기본 브랜치 변경)를 먼저 한 뒤 Actions 탭 다시 열기 |
| 기본 브랜치 변경 시 `Could not change default branch` | GitHub 일시 오류 | ① 새로고침(F5) 후 다시 시도 ② 계속 실패하면 4번의 `bash infra/up.sh`를 먼저 실행해 gh 설치·로그인이 된 뒤 CloudShell에서 `gh repo edit <내아이디>/MLOps-project --default-branch feature/handover` |
| 원본 문서·스크립트가 바뀌었는데 내 fork는 그대로 | fork는 자동으로 동기화되지 않음 | 내 fork에서 `feature/handover` 선택 → **Sync fork → Update branch**, CloudShell에서 `git pull` |
| fork에 `feature/handover` 브랜치가 없음 | fork할 때 "main branch only"가 체크돼 있었음 | fork를 지우고 체크 해제 후 다시 fork (Settings 맨 아래 Delete this repository) |
| `git push` 할 때 `Username for 'https://github.com'` / `/usr/bin/gh: No such file` | CloudShell이 쉬었다 켜지면 홈 폴더 밖에 설치한 gh가 지워짐 | Ctrl+C 후 `bash infra/up.sh` 다시 실행(자동 설치) 또는 아래 3줄을 한 줄씩:<br>`sudo dnf install -y 'dnf-command(config-manager)'`<br>`sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo`<br>`sudo dnf install -y gh --repo gh-cli` |
| `❌ 실행 중인 EC2(i-…)의 키 파일 … 이 없습니다` | CloudShell 홈이 초기화돼 키 파일이 사라짐 | 안내된 `aws ec2 terminate-instances …` 실행 후 `bash infra/up.sh` 다시 실행 |
| `/health`의 `log_sinks_failed`에 `cloudwatch` | EC2에 역할이 안 붙음 | `aws ec2 associate-iam-instance-profile --instance-id <ID> --iam-instance-profile Name=yeonsung-ec2-cloudwatch-role` 후 6번 A로 재배포 |
| 배포 단계에서 `docker login` / `pull` 권한 오류 | fork의 Actions 토큰 권한이 읽기 전용으로 제한됨 | fork의 Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save |
| `⚠️ 고정 IP를 쓸 수 없어…` | 계정 권한상 Elastic IP 불가 | 그대로 진행됩니다. 대신 EC2를 새로 만들 때마다 주소가 바뀝니다 |
| 다음 주에 사이트가 안 열림 | 학교 계정이 매주 EC2를 정리함 | CloudShell에서 `cd ~/MLOps-project && git pull && bash infra/up.sh` (폴더가 없으면 4번부터) |
| `No default remote repository has been set` (gh workflow run 실행 시) | fork는 원본과 내 저장소가 둘 다 연결돼 있어 gh가 대상을 모름 | 명령에 `-R <내아이디>/MLOps-project`를 붙이거나, `gh repo set-default <내아이디>/MLOps-project` 후 다시 실행 (원본 Minyowa를 고르면 안 됨) |
| `Please tell me who you are` / `empty ident name` (git commit 시) | CloudShell에 git 사용자 정보가 없음 | `git config --global user.email "<이메일>"`, `git config --global user.name "<아이디>"` 후 커밋 다시 실행 |
| `src refspec feature/retrain-<이름> does not match any` (git push 시) | `git checkout -b`에 브랜치 이름을 잘못 입력함 (예: 이름이 두 번 들어감) | `git branch`로 현재 이름 확인 → `git branch -m feature/retrain-<이름>`으로 바꾼 뒤 push |

## 9. 다 쓰고 정리하기 (비용)

EC2와 고정 IP는 켜 둔 시간만큼 요금이 나갑니다. **고정 IP는 EC2를 지워도 따로 반납해야 합니다.**

```bash
cd ~/MLOps-project && source infra/config.env
aws ec2 terminate-instances --instance-ids $(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=running" --query 'Reservations[].Instances[].InstanceId' --output text)
aws ec2 release-address --allocation-id $(aws ec2 describe-addresses --filters "Name=tag:Name,Values=$NAME-eip" --query 'Addresses[0].AllocationId' --output text)
```
- 종료(terminate)는 서버를 **완전히 삭제**합니다. 코드·이미지는 GitHub에, 로그는 CloudWatch에 남아 있어서 `up.sh`로 언제든 다시 만들 수 있습니다.
- 고정 IP 반납은 EC2 종료가 끝난 뒤(1~2분) 실행하세요. 연결된 상태면 오류가 납니다.

## 10. 보안 주의

- `~/.ssh/*.pem` 키 파일 내용, GitHub Secrets 화면, `infra/.ec2.env`는 **캡처해서 올리거나 커밋하지 마세요.**
- PR·과제 캡처에서는 EC2 IP를 가리는 것을 권장합니다.
