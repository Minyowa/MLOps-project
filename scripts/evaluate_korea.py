"""한국 사용자 관점 추가 평가 — 저장된 모델로 실행 (재학습 없음).

공개된 한국 피싱 URL 원본 데이터가 없어서(README '데이터 선택' 참고) 사기 탐지율은 JPCERT로만 잰다.
대신 한국인이 실제로 쓰는 정상 사이트를 사기로 오판하지 않는지는 측정할 수 있다.

  1) 인기 사이트 목록 중 .kr 도메인, 그중 학습에 쓰지 않은 20% (train.py와 같은 분할)
  2) 한국인이 자주 쓰는 주요 서비스 실제 주소 (포털·은행·쇼핑·택배·통신·공공)
  3) 한국 기관을 사칭한 형태의 예시 주소 (사칭 탐지 확인용, 실제 피싱 데이터 아님)
  지표: 모델만 썼을 때 / 서비스(policy.decide = 규칙 + 모델) 기준 판정

결과: models/metrics_korea.json
사용법: python scripts/train.py 이후  python scripts/evaluate_korea.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import train as T  # noqa: E402
from linkguard.features import load_reputable, normalize  # noqa: E402
from linkguard.policy import decide  # noqa: E402

KOREAN_SERVICES = [
    "https://www.naver.com", "https://m.blog.naver.com/abc/223456789", "https://www.daum.net",
    "https://open.kakao.com/o/sAbCdE", "https://pf.kakao.com/_xabc",
    "https://www.kbstar.com", "https://www.shinhan.com", "https://www.wooribank.com", "https://www.hanabank.com",
    "https://m.kakaobank.com", "https://www.tossbank.com", "https://toss.im",
    "https://www.coupang.com/vp/products/123456", "https://www.11st.co.kr", "https://www.gmarket.co.kr",
    "https://www.baemin.com", "https://www.musinsa.com/products/123",
    "https://www.cjlogistics.com/ko/tool/parcel/tracking", "https://www.epost.go.kr", "https://www.lotteglogis.com",
    "https://www.tworld.co.kr", "https://www.kt.com",
    "https://www.gov.kr", "https://www.hometax.go.kr", "https://www.nhis.or.kr", "https://www.minwon.go.kr",
]
IMPERSONATION_EXAMPLES = [
    "https://cjlogistics-delivery.top/kr", "http://epost-kr.cfd/?info=x", "https://kakaobank-login.top",
    "https://shinhancard-pay.cc/verify", "https://coupang-event.shop/gift?id=1", "https://naver.com.verify.top/login",
    "https://toss-event.shop", "https://hometax-refund.xyz",
]


def verdict(risk: float) -> str:
    return "위험" if risk >= 0.7 else "주의" if risk >= 0.3 else "안전"


def main():
    _, top, _ = T.load()
    _, top_te = train_test_split(top, test_size=0.2, random_state=T.SEED)   # train.py와 같은 분할
    kr = top_te[top_te["d"].str.lower().str.endswith(".kr")]
    model = joblib.load(ROOT / "models" / "model.joblib")["model"]
    reputable = load_reputable(ROOT / "models" / "reputable_domains.txt")

    risk = model.predict_proba(kr["norm"])[:, 1]
    service_risk = np.array([decide(u, r, reputable).risk for u, r in zip(kr["norm"], risk)])

    def run(urls):
        rows = []
        for u in urls:
            n = normalize(u)
            mr = float(model.predict_proba([n])[0][1])
            d = decide(n, mr, reputable)
            rows.append({"url": u, "model_risk": round(mr, 3), "service_risk": round(d.risk, 3),
                         "verdict": verdict(d.risk), "stage": d.stage})
        return rows

    services = run(KOREAN_SERVICES)
    fakes = run(IMPERSONATION_EXAMPLES)

    def dist(r):
        v = [verdict(x) for x in r]
        return {k: round(v.count(k) / len(v), 4) for k in ("안전", "주의", "위험")}

    out = {
        "target": "인기 사이트 목록의 .kr 도메인 중 학습에 쓰지 않은 것 (모두 정상 사이트)",
        "n": int(len(kr)),
        "model_only": {"false_alarm_rate": round(float((risk >= 0.5).mean()), 4), "verdicts": dist(risk)},
        "service_with_rules": {"false_alarm_rate": round(float((service_risk >= 0.5).mean()), 4),
                               "verdicts": dist(service_risk)},
        "examples_flagged": kr.loc[service_risk >= 0.7, "d"].head(15).tolist(),
        "korean_services": {
            "n": len(services),
            "model_only_not_safe": [r["url"] for r in services if verdict(r["model_risk"]) != "안전"],
            "service_not_safe": [r["url"] for r in services if r["verdict"] != "안전"],
            "rows": services},
        "impersonation_examples": {
            "n": len(fakes),
            "model_only_danger": sum(verdict(r["model_risk"]) == "위험" for r in fakes),
            "service_danger": sum(r["verdict"] == "위험" for r in fakes),
            "rows": fakes},
    }
    (ROOT / "models" / "metrics_korea.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
