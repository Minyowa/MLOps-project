"""감성 분류 모델 학습.

과정
  1. 공식 학습셋(15만)에서 10%를 검증셋으로 떼어 피처 후보를 비교한다
     (공식 테스트셋은 마지막에 한 번만 사용 — 테스트셋을 보고 고르면 성능이 부풀려짐)
  2. 검증 정확도가 가장 높은 설정으로 학습셋 전체를 다시 학습
  3. 공식 테스트셋(5만)으로 최종 평가 → models/model.joblib, models/metrics.json

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
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reviewpulse.text import normalize  # noqa: E402

CANDIDATES = {
    # v1: 단어(띄어쓰기) 단위 — 한국어 리뷰는 띄어쓰기·줄임말이 제각각이라 약함
    "word_1-2gram": dict(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=100_000),
    # v2: 글자 1~3개 조각 — '짜증나네요', '짜증남', '짜증' 이 같은 조각('짜증')을 공유
    "char_1-3gram": dict(analyzer="char_wb", ngram_range=(1, 3), min_df=2, max_features=100_000),
}
C = 2.0


def load(name):
    df = pd.read_csv(ROOT / "data" / f"nsmc_{name}.txt", sep="\t").dropna(subset=["document"])
    df["document"] = df["document"].map(normalize)
    return df[df["document"] != ""]


def build(params):
    return make_pipeline(TfidfVectorizer(sublinear_tf=True, **params),
                         LogisticRegression(max_iter=2000, C=C))


def metrics(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p).ravel()
    return {"accuracy": round(accuracy_score(y, p), 4), "precision": round(precision_score(y, p), 4),
            "recall": round(recall_score(y, p), 4), "f1": round(f1_score(y, p), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}


def main():
    train, test = load("train"), load("test")
    print(f"학습 {len(train):,} / 테스트 {len(test):,} (테스트 긍정 비율 {test.label.mean():.1%})")
    tr, va = train_test_split(train, test_size=0.1, random_state=42, stratify=train.label)

    results = {"baseline_majority": {"val_accuracy": round(max(va.label.mean(), 1 - va.label.mean()), 4)}}
    print(f"  {'baseline_majority':16s} val={results['baseline_majority']['val_accuracy']:.4f}")
    for name, params in CANDIDATES.items():
        t = time.time()
        m = build(params).fit(tr.document, tr.label)
        results[name] = {"val_accuracy": round(accuracy_score(va.label, m.predict(va.document)), 4),
                         "train_accuracy": round(accuracy_score(tr.label, m.predict(tr.document)), 4),
                         "params": params}
        print(f"  {name:16s} val={results[name]['val_accuracy']:.4f} "
              f"train={results[name]['train_accuracy']:.4f} ({time.time() - t:.0f}s)")

    best = max(CANDIDATES, key=lambda n: results[n]["val_accuracy"])
    model = build(CANDIDATES[best]).fit(train.document, train.label)
    test_m = metrics(test.label, model.predict(test.document))
    test_m["train_accuracy"] = round(accuracy_score(train.label, model.predict(train.document)), 4)
    print(f"\n최종: {best} | 공식 테스트 acc={test_m['accuracy']:.4f} F1={test_m['f1']:.4f} "
          f"(train acc={test_m['train_accuracy']:.4f})")

    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    version = time.strftime("%Y%m%d-%H%M%S")
    joblib.dump({"model": model, "version": f"{best}@{version}", "sklearn_version": sklearn.__version__},
                out / "model.joblib", compress=3)
    (out / "metrics.json").write_text(json.dumps({
        "dataset": "NSMC (네이버 영화 리뷰, train 150k / test 50k)",
        "selected": best, "model_version": f"{best}@{version}", "C": C,
        "validation": results, "test": test_m, "sklearn_version": sklearn.__version__,
    }, ensure_ascii=False, indent=2))
    print(f"저장: {out / 'model.joblib'}, {out / 'metrics.json'}")


if __name__ == "__main__":
    main()
