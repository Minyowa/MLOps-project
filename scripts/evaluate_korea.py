"""한국 사용자 관점 점검 — 저장된 모델로 실행 (재학습 없음).

한국 대상 공개 피싱 URL 원본이 없어서(KISA는 통계만 공개), 직접 고른 점검 세트로 확인한다.
  1) 한국인이 자주 쓰는 실제 서비스 40곳 (은행·카드·택배·통신·공공·쇼핑·게임) → 모두 '안전'이어야 함
  2) 한국 기관을 사칭한 모양의 주소 15개 (택배·은행·카드·공공·플랫폼) → '위험' + 공식 주소 안내
     ※ 2)는 피싱 패턴을 흉내 내 만든 예시 주소다. 실제 수집 데이터가 아니므로 탐지율의 근거로 쓰지 않는다.

결과: models/metrics_korea.json
사용법: python scripts/evaluate_korea.py   (BRAND_REGION 기본 jp,kr)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from linkguard.brands import REGION  # noqa: E402
from linkguard.features import load_reputable, normalize  # noqa: E402
from linkguard.policy import decide  # noqa: E402

KOREAN_SERVICES = [
    "https://www.naver.com", "https://m.naver.com", "https://mail.naver.com", "https://www.daum.net",
    "https://www.kakaocorp.com", "https://www.kakaobank.com", "https://www.cjlogistics.com/ko/tool/parcel/tracking",
    "https://service.epost.go.kr/iservice/usr/trace/usrtrc001k01.jsp", "https://www.lotteglogis.com/home/reservation/tracking/index",
    "https://www.hanjin.com/kor/CMS/DeliveryMgr/WaybillSch.do", "https://www.ilogen.com/web/personal/trace",
    "https://www.kbstar.com", "https://card.kbcard.com", "https://www.shinhan.com", "https://www.shinhancard.com",
    "https://www.wooribank.com", "https://www.hanabank.com", "https://banking.nonghyup.com", "https://www.ibk.co.kr",
    "https://www.samsungcard.com", "https://www.hyundaicard.com", "https://www.lottecard.co.kr", "https://www.bccard.com",
    "https://toss.im", "https://www.coupang.com/np/search?q=x", "https://www.tworld.co.kr", "https://www.lguplus.com",
    "https://www.nhis.or.kr", "https://www.hometax.go.kr", "https://www.gov.kr", "https://www.11st.co.kr",
    "https://www.gmarket.co.kr", "https://www.ssg.com", "https://www.musinsa.com", "https://www.baemin.com",
    "https://www.nexon.com", "https://lostark.game.onstove.com", "https://www.yes24.com", "https://www.danawa.com",
    "https://www.kt.com",
]
KOREAN_IMPERSONATION = [
    "https://cjlogistics-delivery.top/track", "https://epost-redelivery.xyz/kr", "https://kbstar-login.info",
    "https://shinhan-card-verify.com", "https://nhis-checkup-result.info", "https://hometax-refund.top",
    "https://toss-auth-secure.net", "https://coupang-order-cancel.xyz", "https://kakao-account-lock.top",
    "https://naver-login-secure.xyz/nid", "https://lguplus-billing.info", "https://hanjin-parcel-check.info",
    "https://gov24-notice.top", "https://wooribank-otp.site", "https://samsungcard-event.icu",
]


def verdict(risk: float) -> str:
    return "위험" if risk >= 0.7 else "주의" if risk >= 0.3 else "안전"


def check(model, reputable, urls):
    rows = []
    for u in urls:
        n = normalize(u)
        mr = float(model.predict_proba([n])[0][1])
        d = decide(n, mr, reputable)
        rows.append({"url": u, "model_risk": round(mr, 3), "service_risk": round(d.risk, 3),
                     "verdict": verdict(d.risk), "stage": d.stage, "brand": d.brand})
    return rows


def main():
    model = joblib.load(ROOT / "models" / "model.joblib")["model"]
    reputable = load_reputable(ROOT / "models" / "reputable_domains.txt")
    safe, fake = check(model, reputable, KOREAN_SERVICES), check(model, reputable, KOREAN_IMPERSONATION)
    out = {
        "brand_region": REGION,
        "korean_services": {"n": len(safe),
                            "model_only_not_safe": [r["url"] for r in safe if verdict(r["model_risk"]) != "안전"],
                            "service_not_safe": [r["url"] for r in safe if r["verdict"] != "안전"], "rows": safe},
        "korean_impersonation_examples": {"n": len(fake),
                                          "service_danger": sum(r["verdict"] == "위험" for r in fake),
                                          "official_address_shown": sum(r["stage"] == "brand_impersonation" for r in fake),
                                          "rows": fake},
    }
    (ROOT / "models" / "metrics_korea.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    s, f = out["korean_services"], out["korean_impersonation_examples"]
    print(f"[BRAND_REGION={REGION}] 한국 서비스 {s['n']}곳: 모델만 안전 아님 {len(s['model_only_not_safe'])} → "
          f"서비스 안전 아님 {len(s['service_not_safe'])} {s['service_not_safe']}")
    print(f"한국 사칭 예시 {f['n']}개: 위험 {f['service_danger']}, 공식 주소 안내 {f['official_address_shown']}")


if __name__ == "__main__":
    main()
