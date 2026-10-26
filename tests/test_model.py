"""모델 품질 회귀 테스트 — 재학습 후 기준을 못 넘으면 실패."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "models" / "metrics.json").read_text())


def test_test_accuracy_in_target_range():
    acc = M["test"]["accuracy"]
    assert 0.85 <= acc < 0.95, acc         # 기준 이상, 비정상적으로 높지도 않음


def test_beats_majority_and_word_baseline():
    v = M["validation"]
    assert v[M["selected"]]["val_accuracy"] > v["word_1-2gram"]["val_accuracy"]
    assert v[M["selected"]]["val_accuracy"] > v["baseline_majority"]["val_accuracy"] + 0.3


def test_no_large_overfit():
    assert M["test"]["train_accuracy"] - M["test"]["accuracy"] < 0.05
