"""ReviewPulse API — 영화 관객 반응(댓글) 긍정/부정 판정 + 담당자 검수(정답) 수집.

실행: uvicorn app.main:app --host 0.0.0.0 --port 8000  →  http://localhost:8000 (검수 화면)

환경변수
  MODEL_PATH        모델 파일 (기본 models/model.joblib)
  REVIEW_LOW/HIGH   이 확률 구간이면 '검수 권장' 표시 (기본 0.35 / 0.65)
  LOG_SINKS         local,cloudwatch,s3 중 선택 (기본 local) — reviewpulse/logsink.py 참고
"""
from __future__ import annotations

import os
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Literal

import joblib
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from reviewpulse.logsink import EventLogger
from reviewpulse.text import MAX_CHARS, normalize

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.getenv("MODEL_PATH", ROOT / "models" / "model.joblib"))
REVIEW_LOW = float(os.getenv("REVIEW_LOW", "0.35"))
REVIEW_HIGH = float(os.getenv("REVIEW_HIGH", "0.65"))

_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
MODEL_VERSION: str = _bundle["version"]

logger = EventLogger.from_env()

# 최근 예측 보관 (정답 입력 시 예측값과 연결하기 위함). 프로세스 메모리 — 재시작 시 초기화
_recent: "OrderedDict[str, dict]" = OrderedDict()
_RECENT_MAX = 10_000
_stats = {"predictions": 0, "feedback": 0, "correct": 0}
_lock = Lock()

app = FastAPI(title="ReviewPulse", version="1.0.0",
              description="영화 관객 댓글의 긍정/부정을 판정하고, 담당자 검수 결과(정답)를 수집하는 API")

LABELS = {1: "긍정", 0: "부정"}


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, examples=["배우들 연기 미쳤다 두 번 봐도 안 아까움"])
    source: str | None = Field(None, max_length=50, description="댓글 출처 (예: community, youtube)")


class PredictResponse(BaseModel):
    prediction_id: str
    label: Literal["긍정", "부정"]
    label_id: Literal[0, 1]
    prob_positive: float
    needs_review: bool = Field(..., description="확률이 애매해 사람 검수를 권장하는지")
    model_version: str


class FeedbackRequest(BaseModel):
    prediction_id: str
    is_correct: bool | None = Field(None, description="예측이 맞았는지 (T/F)")
    true_label: Literal[0, 1] | None = Field(None, description="실제 정답 (1=긍정, 0=부정)")
    reviewer: str | None = Field(None, max_length=50)

    @model_validator(mode="after")
    def need_one(self):
        if self.is_correct is None and self.true_label is None:
            raise ValueError("is_correct 또는 true_label 중 하나는 필요합니다")
        return self


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION, "log_sinks": logger.sink_names}


@app.post("/v1/predict", response_model=PredictResponse)
def predict(req: PredictRequest, bg: BackgroundTasks):
    text = normalize(req.text)
    if not text:
        raise HTTPException(status_code=422, detail="빈 문장입니다")
    t0 = time.perf_counter()
    prob = float(_model.predict_proba([text])[0][1])
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    label_id = int(prob >= 0.5)
    pid = uuid.uuid4().hex
    needs_review = REVIEW_LOW <= prob <= REVIEW_HIGH

    event = {"event": "prediction", "prediction_id": pid, "ts": logger.now(),
             "text": text, "text_truncated": len(req.text) > MAX_CHARS, "source": req.source,
             "pred_label": label_id, "prob_positive": round(prob, 4), "needs_review": needs_review,
             "model_version": MODEL_VERSION, "latency_ms": latency_ms}
    with _lock:
        _recent[pid] = {"pred_label": label_id, "prob_positive": prob}
        if len(_recent) > _RECENT_MAX:
            _recent.popitem(last=False)
        _stats["predictions"] += 1
    bg.add_task(logger.log, event)

    return PredictResponse(prediction_id=pid, label=LABELS[label_id], label_id=label_id,
                           prob_positive=round(prob, 4), needs_review=needs_review,
                           model_version=MODEL_VERSION)


@app.post("/v1/feedback")
def feedback(req: FeedbackRequest, bg: BackgroundTasks):
    with _lock:
        pred = _recent.get(req.prediction_id)
    if pred is None:
        raise HTTPException(status_code=404, detail="알 수 없는(또는 만료된) prediction_id")

    pred_label = pred["pred_label"]
    if req.true_label is not None:
        true_label = req.true_label
    else:
        true_label = pred_label if req.is_correct else 1 - pred_label
    is_correct = true_label == pred_label

    with _lock:
        _stats["feedback"] += 1
        _stats["correct"] += int(is_correct)
    bg.add_task(logger.log, {
        "event": "feedback", "prediction_id": req.prediction_id, "ts": logger.now(),
        "pred_label": pred_label, "true_label": true_label, "is_correct": is_correct,
        "reviewer": req.reviewer, "model_version": MODEL_VERSION})
    return {"prediction_id": req.prediction_id, "true_label": true_label, "is_correct": is_correct}


@app.get("/v1/stats")
def stats():
    """운영 중 실제 정확도 = 담당자가 검수한 건 중 맞은 비율."""
    with _lock:
        s = dict(_stats)
    s["live_accuracy"] = round(s["correct"] / s["feedback"], 4) if s["feedback"] else None
    s["model_version"] = MODEL_VERSION
    s["log_errors"] = logger.errors
    return s
