"""모델 품질 회귀 테스트 — 재학습 후 기준을 못 넘으면 실패."""
import json
from pathlib import Path

import joblib

from linkguard.features import normalize

ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "models" / "metrics.json").read_text())
MODEL = joblib.load(ROOT / "models" / "model.joblib")["model"]


def test_realistic_accuracy_in_target_range():
    acc = M["test"]["accuracy"]
    assert 0.85 <= acc < 0.95, acc


def test_final_beats_older_data_combinations():
    r = M["results"]
    assert r[M["selected"]]["accuracy"] > r["A_2017_only"]["accuracy"]
    assert r[M["selected"]]["popular_site_false_alarm"] < 0.10


def risk(url):
    return MODEL.predict_proba([normalize(url)])[0][1]


def test_obvious_cases():
    assert risk("http://bsqzqdqykm.duckdns.org/?vjhgb") > 0.7
    assert risk("https://www.naver.com") < 0.3
    assert risk("https://www.youtube.com/watch?v=dQw4w9WgXcQ") < 0.3


def test_reputation_list_excludes_phishing_hosts():
    rep = set((ROOT / "models" / "reputable_domains.txt").read_text().split())
    assert "naver.com" in rep
    assert not {"duckdns.org", "blogspot.com", "github.io", "weebly.com"} & rep
    assert M["service_with_rules"]["phishing_passed_by_rules"] < 50


def test_japan_evaluation():
    j = json.loads((ROOT / "models" / "metrics_japan.json").read_text())
    assert j["japanese_services"]["service_not_safe"] == []
    assert j["jpcert_real_phishing"]["brand_matches_jpcert_label"] >= 0.9
    assert j["jpcert_real_phishing"]["passed_as_official_brand"] == 0
    assert j["popular_jp_sites"]["service"]["false_alarm_rate"] <= 0.06


def test_user_feedback_reflected():
    # 신고 데이터로 재학습했다면: 신고 주소 정답 수가 줄지 않고, 품질 게이트를 통과했어야 함
    f = M.get("feedback")
    if not f:
        return
    assert f["after_correct"] >= f["before_correct"], f
    assert M["gate"]["passed"]
