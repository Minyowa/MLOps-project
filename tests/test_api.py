import json
import os

os.environ["LOG_SINKS"] = "local"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from reviewpulse.logsink import EventLogger, LocalSink  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(main, "logger", EventLogger([LocalSink(str(path))]))
    monkeypatch.setattr(main, "_stats", {"predictions": 0, "feedback": 0, "correct": 0})
    return path


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_health_and_ui():
    assert client.get("/health").json()["status"] == "ok"
    assert "ReviewPulse" in client.get("/").text


def test_predict_returns_label_and_logs(tmp_log):
    r = client.post("/v1/predict", json={"text": "  시간   아깝다 졸다 나옴 ", "source": "community"}).json()
    assert r["label"] == "부정" and r["label_id"] == 0
    assert 0 <= r["prob_positive"] <= 1
    ev = events(tmp_log)
    assert len(ev) == 1 and ev[0]["event"] == "prediction"
    assert ev[0]["text"] == "시간 아깝다 졸다 나옴"          # 정규화된 문장이 기록됨
    assert ev[0]["prediction_id"] == r["prediction_id"]
    assert ev[0]["model_version"] == main.MODEL_VERSION


def test_feedback_true_false_maps_to_label(tmp_log):
    r = client.post("/v1/predict", json={"text": "ㅋㅋㅋㅋ 개꿀잼"}).json()
    assert r["label_id"] == 1
    fb = client.post("/v1/feedback", json={"prediction_id": r["prediction_id"], "is_correct": False}).json()
    assert fb == {"prediction_id": r["prediction_id"], "true_label": 0, "is_correct": False}
    last = events(tmp_log)[-1]
    assert last["event"] == "feedback" and last["pred_label"] == 1 and last["true_label"] == 0


def test_feedback_with_explicit_label_and_stats():
    r = client.post("/v1/predict", json={"text": "돈 주고 보기 아까운 영화"}).json()
    client.post("/v1/feedback", json={"prediction_id": r["prediction_id"], "true_label": 0})
    s = client.get("/v1/stats").json()
    assert s["predictions"] == 1 and s["feedback"] == 1 and s["live_accuracy"] == 1.0


def test_feedback_validation():
    assert client.post("/v1/feedback", json={"prediction_id": "nope", "is_correct": True}).status_code == 404
    r = client.post("/v1/predict", json={"text": "좋아요"}).json()
    assert client.post("/v1/feedback", json={"prediction_id": r["prediction_id"]}).status_code == 422


def test_blank_text_rejected():
    assert client.post("/v1/predict", json={"text": "   "}).status_code == 422
    assert client.post("/v1/predict", json={"text": ""}).status_code == 422


def test_log_failure_does_not_break_api(monkeypatch):
    class Broken:
        name = "broken"

        def send(self, event):
            raise RuntimeError("AWS down")

    monkeypatch.setattr(main, "logger", EventLogger([Broken()]))
    assert client.post("/v1/predict", json={"text": "재밌어요"}).status_code == 200
    assert main.logger.errors == 1
