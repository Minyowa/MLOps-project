"""일본 사용자 관점 추가 평가 — 저장된 모델로 실행 (재학습 없음).

  1) 사칭 규칙을 실제 데이터로 검증: JPCERT 2024년 이후 피싱(평가셋과 같은 기간)에는 사칭 대상 브랜드가
     적혀 있다(description 열). 규칙이 잡은 브랜드가 실제 사칭 대상과 맞는지 확인한다.
  2) 학습에 쓰지 않은 인기 .jp 사이트의 오탐
  3) 일본인이 자주 쓰는 주요 서비스 실제 주소 (쇼핑·카드·은행·택배·통신·공공) — 점검용 표본

결과: models/metrics_japan.json
사용법: python scripts/train.py 이후  python scripts/evaluate_japan.py
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

# JPCERT description → brands.py 이름
DESC_TO_BRAND = {
    "Amazon": "Amazon", "三井住友カード": "三井住友カード", "Vpass": "三井住友カード", "三井住友銀行": "三井住友カード",
    "Apple ID": "Apple", "えきねっと": "えきねっと", "au": "au/KDDI", "イオンカード": "イオンカード", "イオン銀行": "イオンカード",
    "SAISON CARD": "セゾンカード", "クレディセゾン": "セゾンカード", "メルカリ": "メルカリ", "JCB": "JCB",
    "エポスカード": "エポスカード", "ETC利用照会サービス": "ETC利用照会サービス", "楽天": "楽天", "楽天カード": "楽天",
    "三菱UFJニコス": "三菱UFJ", "三菱UFJ銀行": "三菱UFJ", "マネックス証券": "マネックス証券", "softbank": "ソフトバンク",
    "ヤマト運輸": "ヤマト運輸", "JAバンク": "JAバンク", "総務省": "総務省", "TEPCO": "東京電力", "国税庁": "国税庁",
    "NTT docomo": "NTTドコモ", "SBI証券": "SBI証券", "Viewcard": "ビューカード", "BIGLOBE": "BIGLOBE",
    "UC Card": "UCカード", "MICARD": "MICARD", "American Express": "American Express", "Microsoft": "Microsoft",
    "みずほ銀行": "みずほ銀行", "ヨドバシカメラ": "ヨドバシカメラ", "Orico": "オリコ", "PayPay": "PayPay",
    "全国信用金庫協会": "信用金庫", "日本郵便": "日本郵便", "佐川急便": "佐川急便",
}

JAPANESE_SERVICES = [
    "https://www.amazon.co.jp/gp/your-account", "https://www.rakuten.co.jp", "https://jp.mercari.com",
    "https://www.yahoo.co.jp", "https://line.me/ja/",
    "https://www.smbc-card.com/mem/index.jsp", "https://www.jcb.co.jp", "https://www.saisoncard.co.jp",
    "https://www.aeon.co.jp", "https://www.eposcard.co.jp", "https://paypay.ne.jp",
    "https://www.bk.mufg.jp", "https://www.mizuhobank.co.jp", "https://www.jabank.org",
    "https://toi.kuronekoyamato.co.jp/cgi-bin/tneko", "https://www.sagawa-exp.co.jp", "https://www.post.japanpost.jp",
    "https://www.docomo.ne.jp", "https://www.au.com", "https://www.softbank.jp", "https://www.tepco.co.jp",
    "https://www.eki-net.com", "https://www.etc-meisai.jp", "https://www.nta.go.jp",
    "https://www.city.yokohama.lg.jp", "https://www.apple.com/jp/",
]


def verdict(risk: float) -> str:
    return "위험" if risk >= 0.7 else "주의" if risk >= 0.3 else "안전"


def main():
    old, top, jp = T.load()
    model = joblib.load(ROOT / "models" / "model.joblib")["model"]
    reputable = load_reputable(ROOT / "models" / "reputable_domains.txt")

    # 1) 실제 JPCERT 2024+ 피싱에서 사칭 규칙 검증
    te = jp[jp.year > T.CUTOFF_YEAR].copy()
    risk = model.predict_proba(te["norm"])[:, 1]
    dec = [decide(u, r, reputable) for u, r in zip(te["norm"], risk)]
    te["stage"] = [d.stage for d in dec]
    te["brand"] = [d.brand for d in dec]
    te["service_risk"] = [d.risk for d in dec]
    imp = te[te.stage == "brand_impersonation"]
    known = imp[imp.description.isin(DESC_TO_BRAND)]
    real = {
        "n_phishing_2024_plus": int(len(te)),
        "flagged_as_impersonation": round(float((te.stage == "brand_impersonation").mean()), 4),
        "brand_matches_jpcert_label": round(float((known.brand == known.description.map(DESC_TO_BRAND)).mean()), 4),
        "recall_model_only": round(float((risk >= 0.5).mean()), 4),
        "recall_service": round(float((te.service_risk >= 0.5).mean()), 4),
        "passed_as_official_brand": int((te.stage == "official_brand").sum()),
    }

    # 2) 학습에 쓰지 않은 인기 .jp 사이트
    _, top_te = train_test_split(top, test_size=0.2, random_state=T.SEED)   # train.py와 같은 분할
    jpd = top_te[top_te["d"].str.lower().str.endswith(".jp")]
    r2 = model.predict_proba(jpd["norm"])[:, 1]
    s2 = np.array([decide(u, r, reputable).risk for u, r in zip(jpd["norm"], r2)])

    def dist(rs):
        v = [verdict(x) for x in rs]
        return {k: round(v.count(k) / len(v), 4) for k in ("안전", "주의", "위험")}

    # 3) 주요 서비스 실제 주소
    rows = []
    for u in JAPANESE_SERVICES:
        n = normalize(u)
        mr = float(model.predict_proba([n])[0][1])
        d = decide(n, mr, reputable)
        rows.append({"url": u, "model_risk": round(mr, 3), "service_risk": round(d.risk, 3),
                     "verdict": verdict(d.risk), "stage": d.stage})

    out = {
        "jpcert_real_phishing": real,
        "popular_jp_sites": {"n": int(len(jpd)),
                             "model_only": {"false_alarm_rate": round(float((r2 >= 0.5).mean()), 4), "verdicts": dist(r2)},
                             "service": {"false_alarm_rate": round(float((s2 >= 0.5).mean()), 4), "verdicts": dist(s2)}},
        "japanese_services": {"n": len(rows),
                              "model_only_not_safe": [r["url"] for r in rows if verdict(r["model_risk"]) != "안전"],
                              "service_not_safe": [r["url"] for r in rows if r["verdict"] != "안전"],
                              "rows": rows},
    }
    (ROOT / "models" / "metrics_japan.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "japanese_services"}, ensure_ascii=False, indent=2))
    print("주요 서비스", len(rows), "| 모델만 안전 아님:", out["japanese_services"]["model_only_not_safe"],
          "| 서비스 안전 아님:", out["japanese_services"]["service_not_safe"])


if __name__ == "__main__":
    main()
