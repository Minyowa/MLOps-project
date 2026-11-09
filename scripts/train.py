"""피싱 링크 판정 모델 학습.

평가 설계 — "지금 사용자가 받는 링크"를 흉내 낸 현실 평가셋
  · 사기 링크: JPCERT 2024년 이후 확인된 피싱 (학습에 쓴 2023년 이전 사이트는 제외)  → 미래 데이터
  · 정상 링크: 2017년 데이터 중 학습에 안 쓴 사이트 + 인기 사이트 목록 중 학습에 안 쓴 20%
  · 50:50으로 맞춤
  2017년 데이터 안에서만 나눠 평가하면 0.96이 나오지만, 최신 스미싱에서는 크게 떨어진다(README 참고).

데이터 조합 비교
  A) 2017년 데이터만
  C) A + JPCERT 2019~2023 피싱
  D) C + 인기 사이트 10만 개 (요즘 정상 사이트)
  E) D + 서비스 사용자 신고 데이터 (data/feedback/*.csv) ← 신고 데이터가 있으면 최종

신고 데이터 오염 방지
  · 인기 사이트(상위 REPUTATION_TOP_K)를 '사기'로 신고한 것, 피싱 이력 도메인을 '안전'으로 신고한 것은
    자동 반영하지 않고 검토 대상(quarantined)으로 뺀다. 예: google.com/search 를 사기로 신고 → 구글 검색 전체가 위험해짐

재학습 품질 게이트 — 하나라도 어기면 모델 파일을 바꾸지 않고 실패(exit 1) → 배포되지 않는다
  1. 현실 평가셋 서비스 정확도가 직전 모델보다 GATE_TOLERANCE 넘게 떨어지거나 오탐률이 GATE_TOLERANCE 넘게 오름
  2. 카나리: 반드시 안전이어야 하는 주소(CANARY_SAFE)를 모델이 위험(≥0.5)으로 보거나,
     반드시 잡아야 하는 주소(CANARY_SCAM)를 안전(<0.5)으로 봄. 평가셋 평균에 묻히는 개별 주소 붕괴를 잡는다

사용법: python scripts/download_data.py && python scripts/train.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from linkguard.features import host_of, normalize, registered_domain  # noqa: E402
from linkguard.policy import decide  # noqa: E402

SEED = 0
CUTOFF_YEAR = 2023      # 이 해까지의 피싱은 학습, 이후는 평가
TEST_PER_CLASS = 20_000
MAX_FEATURES = 200_000
REPUTATION_TOP_K = 10_000
FEEDBACK_WEIGHT = 100         # 신고 1건의 가중치. 78만 건 사이에서 신고 수십 건이 묻히지 않게 (가중치 실험: README)
GATE_TOLERANCE = 0.01
CANARY_SAFE = [
    "https://www.google.com/search?q=weather", "https://www.google.co.jp/search?q=天気",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.naver.com", "https://search.naver.com/search.naver?query=x",
    "https://www.yahoo.co.jp", "https://www.amazon.co.jp/dp/B0C1234567", "https://github.com/torvalds/linux",
    "https://ja.wikipedia.org/wiki/東京", "https://www.instagram.com/", "https://x.com/home",
]
CANARY_SCAM = [
    "https://kuronekoyamato-delivery.top/jp", "https://smbc-card-login.top/vpass", "http://bsqzqdqykm.duckdns.org/?vjhgb",
    "https://amazon-co-jp-login.top/signin", "https://naver-login-secure.xyz/nid",
]   # 인기 상위 N개 도메인을 '평판 좋은 사이트'로 (피싱 이력 있으면 제외)


def domain(norm_url: str) -> str:
    return registered_domain(host_of(norm_url))


def load():
    old = pd.read_csv(ROOT / "data" / "urls.csv").dropna()
    old["norm"] = old["url"].map(normalize)
    old = old.drop_duplicates("norm")
    old["y"] = (old["label"] == "bad").astype(int)

    top = pd.read_csv(ROOT / "data" / "top100k.txt", header=None, names=["d"]).dropna()
    top["norm"] = top["d"].map(normalize)
    top["y"] = 0

    files = sorted((ROOT / "data" / "jpcert").glob("*.csv"))
    jp = pd.concat([pd.read_csv(f).assign(year=int(f.stem[:4])) for f in files]).dropna(subset=["URL"])
    jp["norm"] = jp["URL"].str.replace("*", "x", regex=False).map(normalize)   # JPCERT는 개인정보를 *로 가림
    jp = jp.drop_duplicates("norm")
    jp["y"] = 1

    for df in (old, top, jp):
        df["dom"] = df["norm"].map(domain)
    return old, top, jp


def load_feedback() -> pd.DataFrame:
    """scripts/prepare_feedback.py가 만든 신고 데이터. 같은 주소는 최신 파일의 정답을 쓴다."""
    files = sorted((ROOT / "data" / "feedback").glob("feedback_*.csv"))
    if not files:
        return pd.DataFrame(columns=["url", "label", "pred_label", "norm", "y", "file"])
    fb = pd.concat([pd.read_csv(f).assign(file=f.name) for f in files])
    fb["norm"] = fb["url"].map(normalize)
    fb = fb.drop_duplicates("norm", keep="last")
    fb["y"] = fb["label"].astype(int)
    return fb


def quarantine(fb: pd.DataFrame, popular: set[str], phishing: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """사람 검토 대상으로 분리할 신고.
    · 인기 사이트 '본체'를 사기로 신고 (google.com/search, pornhub.com …)
      — 인기 호스팅의 하위 주소(xxx.weebly.com, xxx.blogspot.com)는 실제 피싱이 많아 그대로 반영
    · 인기 사이트가 아닌 피싱 이력 도메인을 안전으로 신고 (github.com, instagram.com 같은 인기 사이트는 반영)
    """
    host = fb.norm.map(host_of).str.removeprefix("www.")
    apex = host == fb.dom
    bad = (((fb.y == 1) & fb.dom.isin(popular) & apex) |
           ((fb.y == 0) & fb.dom.isin(phishing) & ~fb.dom.isin(popular)))
    return fb[~bad], fb[bad]


def canaries(model) -> list[str]:
    """반드시 지켜야 하는 개별 주소 판정. 어긴 주소 목록을 돌려준다."""
    safe = model.predict_proba([normalize(u) for u in CANARY_SAFE])[:, 1]
    scam = model.predict_proba([normalize(u) for u in CANARY_SCAM])[:, 1]
    return ([f"안전이어야 함 {u} ({r:.2f})" for u, r in zip(CANARY_SAFE, safe) if r >= 0.5] +
            [f"위험이어야 함 {u} ({r:.2f})" for u, r in zip(CANARY_SCAM, scam) if r < 0.5])


def fit(train: pd.DataFrame):
    sw = train["w"].fillna(1.0).to_numpy() if "w" in train else np.ones(len(train))
    return build().fit(train.norm, train.y, logisticregression__sample_weight=sw)


def build():
    return make_pipeline(
        TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=3, max_features=MAX_FEATURES, sublinear_tf=True),
        LogisticRegression(max_iter=3000, C=4, class_weight="balanced"))


def metrics(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p).ravel()
    return {"accuracy": round(accuracy_score(y, p), 4), "precision": round(precision_score(y, p), 4),
            "recall_phishing": round(recall_score(y, p), 4), "f1": round(f1_score(y, p), 4),
            "false_alarm_rate": round(fp / (fp + tn), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}


def main():
    t0 = time.time()
    old, top, jp = load()
    fb = load_feedback()
    print(f"2017 URL {len(old):,} | 인기 사이트 {len(top):,} | JPCERT 피싱 {len(jp):,} | 사용자 신고 {len(fb):,}")
    out = ROOT / "models"
    baseline = json.loads((out / "metrics.json").read_text()) if (out / "metrics.json").exists() else None
    prev_model = joblib.load(out / "model.joblib")["model"] if (out / "model.joblib").exists() else None

    tr_i, te_i = next(GroupShuffleSplit(1, test_size=0.2, random_state=SEED).split(old, old.y, groups=old.dom))
    old_tr, old_te = old.iloc[tr_i], old.iloc[te_i]
    top_tr, top_te = train_test_split(top, test_size=0.2, random_state=SEED)
    jp_tr = jp[jp.year <= CUTOFF_YEAR]
    jp_te = jp[(jp.year > CUTOFF_YEAR) & ~jp.dom.isin(set(jp_tr.dom))]

    benign_te = pd.concat([old_te[old_te.y == 0].sample(TEST_PER_CLASS // 2, random_state=SEED),
                           top_te.sample(TEST_PER_CLASS // 2, random_state=SEED)])
    benign_te = benign_te[~benign_te.dom.isin(set(jp_tr.dom))]
    n = min(len(benign_te), len(jp_te))
    test = pd.concat([jp_te.sample(n, random_state=SEED), benign_te.sample(n, random_state=SEED)])
    print(f"현실 평가셋: 최신 피싱 {n:,} + 정상 {n:,}")

    combos = {
        "A_2017_only": old_tr,
        "C_plus_recent_phishing": pd.concat([old_tr, jp_tr]),
        "D_plus_recent_phishing_and_popular_sites": pd.concat([old_tr, jp_tr, top_tr]),
    }
    # 신고 데이터 오염 방지 (평판 목록 계산과 같은 기준: 인기 상위 K, 학습 데이터의 피싱 이력)
    phish_history = set(jp_tr.dom) | set(old_tr[old_tr.y == 1].dom)
    ranked = set(top["d"].head(REPUTATION_TOP_K).str.lower().map(registered_domain))
    quarantined = fb.iloc[0:0]
    if len(fb):
        fb["dom"] = fb["norm"].map(domain)
        fb, quarantined = quarantine(fb, ranked, phish_history)
        print(f"  신고 검토 대상(자동 반영 제외) {len(quarantined)}개: {', '.join(quarantined.url.head(15))}"
              f"{' …' if len(quarantined) > 15 else ''}")
    if len(fb):
        combos["E_plus_user_feedback"] = pd.concat([combos["D_plus_recent_phishing_and_popular_sites"],
                                                    fb.assign(w=FEEDBACK_WEIGHT)])
    results, models = {}, {}
    for name, train in combos.items():
        m = fit(train)
        r = metrics(test.y, m.predict(test.norm))
        r["train_accuracy"] = round(accuracy_score(train.y, m.predict(train.norm)), 4)
        r["popular_site_false_alarm"] = round(float(m.predict(top_te.norm).mean()), 4)
        r["n_train"] = int(len(train))
        results[name], models[name] = r, m
        print(f"  {name:42s} 정확도={r['accuracy']:.3f} 사기탐지율={r['recall_phishing']:.3f} "
              f"오탐={r['false_alarm_rate']:.3f} 인기사이트오탐={r['popular_site_false_alarm']:.3f} "
              f"(train={r['train_accuracy']:.3f})")

    final = "E_plus_user_feedback" if len(fb) else "D_plus_recent_phishing_and_popular_sites"

    # 신고 주소에서 직전 모델 대비 얼마나 고쳐졌나 (신고 데이터는 학습에 들어가므로 '반영 확인'용, 일반화 성능 아님)
    feedback = None
    if len(fb):
        after = (models[final].predict_proba(fb.norm)[:, 1] >= 0.5).astype(int)
        before = (prev_model.predict_proba(fb.norm)[:, 1] >= 0.5).astype(int) if prev_model else fb["pred_label"]
        feedback = {"quarantined": sorted(quarantined.url), "n": int(len(fb)), "files": sorted(fb["file"].unique()), "weight": FEEDBACK_WEIGHT,
                    "before_correct": int((before == fb.y).sum()), "after_correct": int((after == fb.y).sum()),
                    "fixed": sorted(fb.url[(before != fb.y) & (after == fb.y)]),
                    "still_wrong": sorted(fb.url[after != fb.y]),
                    "broken": sorted(fb.url[(before == fb.y) & (after != fb.y)])}
        print(f"  신고 주소 {feedback['n']}개: 직전 모델 {feedback['before_correct']}개 정답 → 새 모델 {feedback['after_correct']}개 정답"
              f" (고쳐짐 {len(feedback['fixed'])}, 여전히 틀림 {len(feedback['still_wrong'])}, 새로 틀림 {len(feedback['broken'])})")

    # 평판 도메인 목록: 인기 상위 K개 - 학습 데이터에서 피싱이 올라간 적 있는 도메인(무료 호스팅 등)
    reputable = sorted(ranked - phish_history)
    print(f"평판 도메인 {len(reputable):,}개 (피싱 이력으로 제외 {len(ranked & phish_history)}개)")

    # 서비스 전체(규칙 + 모델) 평가
    rep_set = set(reputable)
    model_risk = models[final].predict_proba(test.norm)[:, 1]
    decisions = [decide(u, r, rep_set) for u, r in zip(test.norm, model_risk)]
    service = metrics(test.y, [int(d.risk >= 0.5) for d in decisions])
    rule_safe = [d.stage in ("official_domain", "official_brand", "reputable_domain") for d in decisions]
    service["phishing_passed_by_rules"] = int(sum(s and y == 1 for s, y in zip(rule_safe, test.y)))
    service["stage_counts"] = pd.Series([d.stage for d in decisions]).value_counts().to_dict()
    print(f"  서비스 전체(규칙+모델) 정확도={service['accuracy']:.3f} 사기탐지율={service['recall_phishing']:.3f} "
          f"오탐={service['false_alarm_rate']:.3f} 규칙으로 통과된 사기={service['phishing_passed_by_rules']}")

    # 품질 게이트: 직전 모델보다 현실 평가셋 성능이 떨어지면 저장하지 않는다
    gate = {"tolerance": GATE_TOLERANCE, "passed": True, "canary_failed": canaries(models[final])}
    print(f"  카나리 {len(CANARY_SAFE) + len(CANARY_SCAM)}개: " +
          ("모두 통과" if not gate["canary_failed"] else "실패 → " + "; ".join(gate["canary_failed"])))
    if baseline:
        b = baseline["service_with_rules"]
        gate.update({"baseline_version": baseline["model_version"],
                     "accuracy": [b["accuracy"], service["accuracy"]],
                     "false_alarm_rate": [b["false_alarm_rate"], service["false_alarm_rate"]]})
        gate["passed"] = bool(service["accuracy"] >= b["accuracy"] - GATE_TOLERANCE and
                          service["false_alarm_rate"] <= b["false_alarm_rate"] + GATE_TOLERANCE)
        print(f"  품질 게이트: 정확도 {b['accuracy']:.4f} → {service['accuracy']:.4f}, "
              f"오탐 {b['false_alarm_rate']:.4f} → {service['false_alarm_rate']:.4f} "
              f"→ {'통과' if gate['passed'] else '실패'}")
    gate["passed"] = gate["passed"] and not gate["canary_failed"]
    if not gate["passed"]:
        sys.exit("❌ 품질 게이트 실패: 직전 모델보다 나빠져서 모델을 바꾸지 않습니다")

    out.mkdir(exist_ok=True)
    (out / "reputable_domains.txt").write_text("\n".join(reputable) + "\n")
    version = f"char3-5_lr{f'+fb{len(fb)}' if len(fb) else ''}@{time.strftime('%Y%m%d-%H%M%S')}"
    joblib.dump({"model": models[final], "version": version, "sklearn_version": sklearn.__version__},
                out / "model.joblib", compress=3)
    (out / "metrics.json").write_text(json.dumps({
        "task": "링크 하나 → 피싱/악성(1) vs 정상(0)",
        "eval_set": f"JPCERT {CUTOFF_YEAR + 1}년 이후 피싱(학습에 없던 사이트) {n} + 학습에 없던 정상 {n}",
        "selected": final, "model_version": version,
        "results": results, "test": results[final], "service_with_rules": service,
        "feedback": feedback, "gate": gate,
        "reputation": {"top_k": REPUTATION_TOP_K, "n_domains": len(reputable)},
        "sklearn_version": sklearn.__version__,
    }, ensure_ascii=False, indent=2))
    print(f"최종: {final} → {out / 'model.joblib'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
