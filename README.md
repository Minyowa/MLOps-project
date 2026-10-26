# LinkGuard — 받은 링크, 열기 전에 검사하는 피싱 판정 서비스

## 1. 서비스 정의

> **문자·메신저·메일로 받은 링크를 열기 전에 붙여 넣으면, 피싱(스미싱)·악성 사이트일 위험도를 알려 주고, 사용자가 알려 준 실제 결과로 계속 정확해지는 서비스.**

| 항목 | 내용 |
|---|---|
| **누가** | 스마트폰을 쓰는 누구나 (특히 택배·결제·지원금 문자를 자주 받는 사람) |
| **어떤 상황에** | "택배 주소 확인 바랍니다 http://…" 같은 링크를 받았는데 열어도 되는지 모를 때 |
| **입력** | 링크 주소 1개 (+ 받은 경로: 문자/메신저/메일 등) |
| **예측** | 위험 확률과 3단계 판정(안전 / 주의 / 위험), 눈에 띄는 위험 신호 설명 |
| **정답(사용자 입력)** | 사용자가 나중에 **"사기였어요"(1) / "안전했어요"(0)** 를 누름 — 휴대폰의 스팸 신고처럼 익숙한 동작 |
| **링크를 열지 않음** | 주소 모양만 분석하므로 검사 자체가 위험하지 않음 |

## 2. 데이터

| 데이터 | 내용 | 용도 |
|---|---|---|
| [faizann24 URL 데이터](https://github.com/faizann24/Using-machine-learning-to-detect-malicious-URLs) | 2017년 무렵 정상·악성 URL 41만 건 | 기본 학습 |
| [JPCERT/CC 피싱 URL](https://github.com/JPCERTCC/phishurl-list) | 일본 침해사고대응팀이 **실제로 확인한 피싱 링크** 27만 건 (2019~2026, 택배·결제 사칭 스미싱 위주) | 2023년까지 학습, **2024년 이후는 평가** |
| [인기 사이트 10만](https://github.com/zer0h/top-1000000-domains) | 많이 방문하는 사이트 도메인 | 요즘 정상 사이트 |

**정규화(학습·서빙 공용)**: 2017년 데이터의 정상 링크는 전부 `https://`, `www.` 없이 경로가 붙은 형태로 저장돼 있었습니다. 그대로 쓰면 사용자가 붙여 넣는 `https://www.naver.com`을 "처음 보는 모양"으로 보고 위험 판정합니다. 그래서 학습과 서빙 모두 `normalize()`로 표기 차이를 없앱니다.

## 3. 평가 방법 — "지금 사용자가 받는 링크"를 흉내 낸 현실 평가셋

- **사기 링크**: JPCERT **2024년 이후** 피싱 19,896건. 학습(2023년까지)에 나온 사이트는 제외 → **미래의, 처음 보는 사기 링크**
- **정상 링크**: 학습에 안 쓴 사이트 19,896건 (2017년 정상 링크 + 인기 사이트)
- 50:50, 학습과 겹치는 사이트 없음

## 4. 모델 실험 기록 (과제 3-1, 3-2)

| 버전 | 변경 | 결과 | 판단 |
|---|---|---|---|
| v1 | 2017년 데이터, 무작위 분할, 주소 글자 조각 | 0.978 | **90% 후반** → 원인 점검 |
| v2 | 같은 사이트가 학습·테스트에 섞이지 않게 분할 | 0.965 | 여전히 높음 |
| v3 | 2017년 모델로 **최신 실제 스미싱** 검사 | 탐지율 **0.645** | 데이터가 오래돼서 요즘 사기 링크를 놓침 → **평가 방법 재정의** (현실 평가셋) |
| v3' | 사이트 이름 대신 주소 구조 피처 20개 | 최신 스미싱 탐지율 0.530 | 더 나쁨 → 피처 문제가 아니라 **데이터 문제** |

**현실 평가셋 결과 (데이터 조합별)**

| 학습 데이터 | 정확도 | 사기 탐지율 | 정상 오탐 | 인기 사이트 오탐 |
|---|---|---|---|---|
| A) 2017년 데이터만 | 0.788 ❌ | 0.824 | 24.8% | 45.8% |
| C) A + 최신 피싱(2019~23) | 0.823 ❌ | **0.938** | 29.3% | **56.1%** — 처음 보는 건 다 사기로 판정 |
| **D) C + 요즘 인기 사이트** | **0.918** ✅ | 0.876 | 4.1% | 6.4% |

- 최신 피싱만 넣으면 탐지율은 오르지만, **정상 사이트까지 사기로 판정**해서 오히려 쓸 수 없습니다. 요즘 정상 사이트를 함께 넣어야 균형이 잡힙니다.
- 학습 정확도 0.977과 평가 정확도 0.918의 차이는 과적합이 아니라 **평가셋이 미래의 처음 보는 링크**이기 때문입니다.

**최종 서비스 (규칙 + 모델)**

| Accuracy | Precision | 사기 탐지율 (Recall) | F1 | 정상 오탐 |
|---|---|---|---|---|
| **0.920** | 0.961 | 0.876 | 0.917 | 3.5% |

## 5. 판정 흐름

```
링크 → 정규화 ─┬─ 정부·공공 도메인(.go.kr, gov.kr, .gov …)        → 안전 (개인이 등록 불가)
               ├─ 평판 도메인 (인기 상위 1만 − 피싱 이력 192개 제외)  → 안전
               └─ 그 외 → 모델(주소 글자 3~5개 조각 + 로지스틱 회귀) → 위험 확률
                          0.3 미만 안전 / 0.3~0.7 주의 / 0.7 이상 위험
```

- **평판 도메인 목록은 데이터로 만듭니다.** 인기 상위 1만 개 중 학습 데이터에서 **피싱이 올라간 적 있는 도메인**(`github.io`, `blogspot.com`, `duckdns.org`, `weebly.com` 등 누구나 페이지를 만들 수 있는 곳)은 자동 제외합니다. 현실 평가셋에서 이 규칙 때문에 통과된 사기 링크는 19,896건 중 9건입니다.
- `coupang.com.evil.top`, `coupang-event.shop`처럼 이름만 흉내 낸 주소는 규칙에 걸리지 않고 모델이 판정합니다.

## 6. API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 사용자 화면 |
| POST | `/v1/check` | `{"url": "...", "channel": "sms"}` → `verdict`, `risk`, `reasons`, `check_id` |
| POST | `/v1/feedback` | `{"check_id": "...", "true_label": 1}` (사기였음=1, 안전했음=0) 또는 `{"is_correct": true}` |
| GET | `/v1/stats` | 검사 수, 결과를 알려 준 수, **사용자 기준 실제 정확도** |
| GET | `/health` | 상태, 모델 버전, 로그 싱크 |

### 수집되는 로그 (JSON 한 줄)
```json
{"event": "check", "check_id": "78c9…", "ts": "2026-10-26T09:21:58.395+00:00",
 "url_redacted": "coupang-event.shop/gift?id=*", "url_sha256": "faf51e…", "host": "coupang-event.shop",
 "channel": "sms", "stage": "model", "pred_label": 1, "risk": 0.9799, "model_risk": 0.9799,
 "verdict": "위험", "model_version": "char3-5_lr@20261026-182114", "latency_ms": 2.33}
{"event": "feedback", "check_id": "78c9…", "ts": "2026-10-26T09:21:59.008+00:00",
 "pred_label": 1, "true_label": 1, "is_correct": true, "model_version": "char3-5_lr@20261026-182114"}
```
- `check_id`로 검사와 실제 결과를 이어 붙여 **운영 중 정확도**를 계산합니다.
- **개인정보 보호**: 링크의 쿼리 값(`?phone=010…`, 인증 토큰 등)은 지우고 저장합니다. 같은 링크인지 비교할 수 있도록 원본은 해시(`url_sha256`)로만 남깁니다.
- `model_risk`: 규칙으로 '안전' 처리된 경우에도 모델 점수를 남겨, 평판 목록이 틀리는 경우를 나중에 찾을 수 있게 합니다.

## 7. 실행

```bash
pip install -r requirements.txt
python scripts/download_data.py     # data/ (약 50MB)
python scripts/train.py             # models/model.joblib, reputable_domains.txt, metrics.json (약 5분)
uvicorn app.main:app --port 8000    # http://localhost:8000
pytest                              # 31개 (AWS 로그는 moto 가짜 AWS로 검증)
```

### AWS 로그 수집 켜기 (CloudWatch + S3)
1. 자격 증명: `aws configure` 또는 환경변수 (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, AWS Academy는 `AWS_SESSION_TOKEN`까지). EC2라면 IAM 역할로 대체 가능
2. S3 버킷 만들기 (이름은 전 세계에서 유일해야 함)
   ```bash
   aws s3 mb s3://linkguard-logs-<본인이름> --region ap-northeast-2
   ```
3. 실행
   ```bash
   export AWS_DEFAULT_REGION=ap-northeast-2
   export LOG_SINKS=local,cloudwatch,s3
   export S3_BUCKET=linkguard-logs-<본인이름>
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   로그 그룹 `/linkguard/app`은 앱이 처음 뜰 때 자동으로 만듭니다.
4. 확인: CloudWatch 콘솔 → 로그 그룹 `/linkguard/app` / S3 콘솔 → `logs/check/`, `logs/feedback/` (`dt=날짜` 폴더)

필요 권한: `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`, `s3:PutObject`

Docker:
```bash
docker build -t linkguard .
docker run -p 8000:8000 -e LOG_SINKS=local,cloudwatch,s3 -e S3_BUCKET=... -e AWS_DEFAULT_REGION=ap-northeast-2 \
  -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN linkguard
```

## 8. 화면

![검사 화면](docs/ui.png)

## 9. 한계와 다음 단계
- **주소만 봅니다.** 정상 사이트 안의 사기 글(예: 오픈채팅방, 게시글)은 판별하지 못합니다.
- 평판 목록 밖의 정상 사이트(예: `m.kakaobank.com` 0.33, GitHub 저장소 주소 0.62)는 '주의'가 나올 수 있습니다. → 사용자가 "안전했어요"를 누른 기록을 모아 재학습
- 학습 데이터의 피싱은 일본 대상이 많습니다. 한국 스미싱(택배·지원금 사칭)에서의 정확도는 사용자 신고 로그로 감시해야 합니다.
- 최근 검사 기록과 통계는 프로세스 메모리 → 여러 인스턴스로 늘리면 공유 저장소 필요
- 다음 단계: S3의 신고 로그를 Athena로 집계 → 정확도가 떨어지면 신고 데이터를 더해 재학습

## 출처
- JPCERT/CC, *Phishing URL dataset*, https://github.com/JPCERTCC/phishurl-list
- Faizan Ahmad, *Using machine learning to detect malicious URLs*, https://github.com/faizann24/Using-machine-learning-to-detect-malicious-URLs
- zer0h, *Top-1000000-Domains*, https://github.com/zer0h/top-1000000-domains
