import json
import os

os.environ["LOG_SINKS"] = "local"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from linkguard.logsink import EventLogger, LocalSink  # noqa: E402

client = TestClient(main.app)


class Stub:
    def __init__(self, p):
        self.p = p

    def predict_proba(self, x):
        return [[1 - self.p, self.p]]


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(main, "logger", EventLogger([LocalSink(str(path))]))
    monkeypatch.setattr(main, "_stats", {"checks": 0, "feedback": 0, "correct": 0})
    return path


def events(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_health_and_ui():
    assert client.get("/health").json()["status"] == "ok"
    assert "LinkGuard" in client.get("/").text


@pytest.mark.parametrize("p,verdict,label", [(0.9, "위험", 1), (0.5, "주의", 1), (0.1, "안전", 0)])
def test_verdict_levels(monkeypatch, p, verdict, label):
    monkeypatch.setattr(main, "_model", Stub(p))
    r = client.post("/v1/check", json={"url": "https://example.top/abc"}).json()
    assert r["verdict"] == verdict and r["label_id"] == label and r["stage"] == "model"


def test_official_domain_bypasses_model(monkeypatch):
    monkeypatch.setattr(main, "_model", Stub(0.99))
    r = client.post("/v1/check", json={"url": "https://www.hometax.go.kr/websquare/websquare.html"}).json()
    assert r["verdict"] == "안전" and r["stage"] == "official_domain"


def test_check_logs_redacted_url(tmp_log, monkeypatch):
    monkeypatch.setattr(main, "_model", Stub(0.95))
    r = client.post("/v1/check", json={"url": "https://pay-check.top/a?phone=01012345678", "channel": "sms"}).json()
    ev = events(tmp_log)[0]
    assert ev["event"] == "check" and ev["check_id"] == r["check_id"]
    assert ev["url_redacted"] == "pay-check.top/a?phone=*"
    assert "01012345678" not in json.dumps(ev)
    assert ev["channel"] == "sms" and ev["model_version"] == main.MODEL_VERSION


def test_feedback_true_label_and_stats(tmp_log, monkeypatch):
    monkeypatch.setattr(main, "_model", Stub(0.2))
    r = client.post("/v1/check", json={"url": "https://free-gift.xyz/claim"}).json()
    fb = client.post("/v1/feedback", json={"check_id": r["check_id"], "true_label": 1}).json()
    assert fb == {"check_id": r["check_id"], "true_label": 1, "is_correct": False}
    last = events(tmp_log)[-1]
    assert last["event"] == "feedback" and last["pred_label"] == 0 and last["true_label"] == 1
    s = client.get("/v1/stats").json()
    assert s["checks"] == 1 and s["feedback"] == 1 and s["live_accuracy"] == 0.0


def test_feedback_is_correct_tf(monkeypatch):
    monkeypatch.setattr(main, "_model", Stub(0.9))
    r = client.post("/v1/check", json={"url": "https://x.top/"}).json()
    fb = client.post("/v1/feedback", json={"check_id": r["check_id"], "is_correct": True}).json()
    assert fb["true_label"] == 1 and fb["is_correct"] is True


def test_validation():
    assert client.post("/v1/check", json={"url": "그냥 문장입니다"}).status_code == 422
    assert client.post("/v1/check", json={"url": "ab"}).status_code == 422
    assert client.post("/v1/feedback", json={"check_id": "nope", "true_label": 1}).status_code == 404
    r = client.post("/v1/check", json={"url": "https://naver.com"}).json()
    assert client.post("/v1/feedback", json={"check_id": r["check_id"]}).status_code == 422


def test_log_failure_does_not_break_api(monkeypatch):
    class Broken:
        name = "broken"

        def send(self, e):
            raise RuntimeError("AWS down")

    monkeypatch.setattr(main, "logger", EventLogger([Broken()]))
    assert client.post("/v1/check", json={"url": "https://naver.com"}).status_code == 200
    assert main.logger.errors == 1


def test_reputable_domain_rule(monkeypatch):
    monkeypatch.setattr(main, "_model", Stub(0.99))
    monkeypatch.setattr(main, "REPUTABLE", {"coupang.com"})
    r = client.post("/v1/check", json={"url": "https://www.coupang.com/vp/products/1"}).json()
    assert r["verdict"] == "안전" and r["stage"] == "reputable_domain"
    r2 = client.post("/v1/check", json={"url": "https://coupang.com.evil.top/login"}).json()
    assert r2["verdict"] == "위험" and r2["stage"] == "model"      # 이름만 흉내 낸 가짜는 통과 못 함
