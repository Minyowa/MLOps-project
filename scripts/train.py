"""피싱 링크 판정 모델 학습.

평가 설계 — "지금 사용자가 받는 링크"를 흉내 낸 현실 평가셋
  · 사기 링크: JPCERT 2024년 이후 확인된 피싱 (학습에 쓴 2023년 이전 사이트는 제외)  → 미래 데이터
  · 정상 링크: 2017년 데이터 중 학습에 안 쓴 사이트 + 인기 사이트 목록 중 학습에 안 쓴 20%
  · 50:50으로 맞춤
  2017년 데이터 안에서만 나눠 평가하면 0.96이 나오지만, 최신 스미싱에서는 크게 떨어진다(README 참고).

데이터 조합 비교
  A) 2017년 데이터만
  C) A + JPCERT 2019~2023 피싱
  D) C + 인기 사이트 10만 개 (요즘 정상 사이트)          ← 최종

사용법: python scripts/download_data.py && python scripts/train.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from linkguard.features import host_of, is_official, normalize, registered_domain  # noqa: E402

SEED = 0
CUTOFF_YEAR = 2023      # 이 해까지의 피싱은 학습, 이후는 평가
TEST_PER_CLASS = 20_000
MAX_FEATURES = 200_000
REPUTATION_TOP_K = 10_000   # 인기 상위 N개 도메인을 '평판 좋은 사이트'로 (피싱 이력 있으면 제외)


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
    print(f"2017 URL {len(old):,} | 인기 사이트 {len(top):,} | JPCERT 피싱 {len(jp):,}")

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
    results, models = {}, {}
    for name, train in combos.items():
        m = build().fit(train.norm, train.y)
        r = metrics(test.y, m.predict(test.norm))
        r["train_accuracy"] = round(accuracy_score(train.y, m.predict(train.norm)), 4)
        r["popular_site_false_alarm"] = round(float(m.predict(top_te.norm).mean()), 4)
        r["n_train"] = int(len(train))
        results[name], models[name] = r, m
        print(f"  {name:42s} 정확도={r['accuracy']:.3f} 사기탐지율={r['recall_phishing']:.3f} "
              f"오탐={r['false_alarm_rate']:.3f} 인기사이트오탐={r['popular_site_false_alarm']:.3f} "
              f"(train={r['train_accuracy']:.3f})")

    final = "D_plus_recent_phishing_and_popular_sites"

    # 평판 도메인 목록: 인기 상위 K개 - 학습 데이터에서 피싱이 올라간 적 있는 도메인(무료 호스팅 등)
    phish_history = set(jp_tr.dom) | set(old_tr[old_tr.y == 1].dom)
    ranked = set(top["d"].head(REPUTATION_TOP_K).str.lower().map(registered_domain))
    reputable = sorted(ranked - phish_history)
    print(f"평판 도메인 {len(reputable):,}개 (피싱 이력으로 제외 {len(ranked & phish_history)}개)")

    # 서비스 전체(규칙 + 모델) 평가
    p = models[final].predict(test.norm)
    rule_safe = test.norm.map(is_official).values | test.dom.isin(set(reputable)).values
    service = metrics(test.y, (p * ~rule_safe).astype(int))
    service["phishing_passed_by_rules"] = int((rule_safe & (test.y.values == 1)).sum())
    print(f"  서비스 전체(규칙+모델) 정확도={service['accuracy']:.3f} 사기탐지율={service['recall_phishing']:.3f} "
          f"오탐={service['false_alarm_rate']:.3f} 규칙으로 통과된 사기={service['phishing_passed_by_rules']}")

    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    (out / "reputable_domains.txt").write_text("\n".join(reputable) + "\n")
    version = f"char3-5_lr@{time.strftime('%Y%m%d-%H%M%S')}"
    joblib.dump({"model": models[final], "version": version, "sklearn_version": sklearn.__version__},
                out / "model.joblib", compress=3)
    (out / "metrics.json").write_text(json.dumps({
        "task": "링크 하나 → 피싱/악성(1) vs 정상(0)",
        "eval_set": f"JPCERT {CUTOFF_YEAR + 1}년 이후 피싱(학습에 없던 사이트) {n} + 학습에 없던 정상 {n}",
        "selected": final, "model_version": version,
        "results": results, "test": results[final], "service_with_rules": service,
        "reputation": {"top_k": REPUTATION_TOP_K, "n_domains": len(reputable)},
        "sklearn_version": sklearn.__version__,
    }, ensure_ascii=False, indent=2))
    print(f"최종: {final} → {out / 'model.joblib'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
