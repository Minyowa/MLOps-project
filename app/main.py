"""LinkGuard API — 받은 링크의 피싱·악성 위험도 판정 + 사용자 신고(실제 결과) 수집.

실행: uvicorn app.main:app --host 0.0.0.0 --port 8000  →  http://localhost:8000 (사용자 화면)

환경변수
  MODEL_PATH          모델 파일 (기본 models/model.joblib)
  CAUTION / DANGER    위험 확률 기준 (기본 0.3 / 0.7): 미만 '안전', 사이 '주의', 이상 '위험'
  LOG_SINKS           local,cloudwatch,s3 중 선택 (기본 local) — linkguard/logsink.py 참고
"""
from __future__ import annotations

import hashlib
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

from linkguard.features import (extract, host_of, is_official, load_reputable, normalize, reasons, redact,
                                registered_domain)
from linkguard.logsink import EventLogger

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.getenv("MODEL_PATH", ROOT / "models" / "model.joblib"))
CAUTION = float(os.getenv("CAUTION", "0.3"))
DANGER = float(os.getenv("DANGER", "0.7"))

_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
MODEL_VERSION: str = _bundle["version"]
# 인기 상위 1만 개 중 피싱 이력이 없는 도메인 (scripts/train.py가 생성)
REPUTABLE = load_reputable(os.getenv("REPUTABLE_PATH", MODEL_PATH.parent / "reputable_domains.txt"))

logger = EventLogger.from_env()

_recent: "OrderedDict[str, dict]" = OrderedDict()   # 신고 시 검사 결과와 연결 (프로세스 메모리)
_RECENT_MAX = 10_000
_stats = {"checks": 0, "feedback": 0, "correct": 0}
_lock = Lock()

app = FastAPI(title="LinkGuard", version="1.0.0",
              description="문자·메신저로 받은 링크의 피싱·악성 위험도를 판정하고, 사용자가 알려 준 실제 결과를 수집하는 API")


class CheckRequest(BaseModel):
    url: str = Field(..., min_length=3, max_length=2000, examples=["https://cjlogistics-delivery.top/kr"])
    channel: Literal["sms", "messenger", "email", "web", "other"] | None = Field(None, description="링크를 받은 경로")


class CheckResponse(BaseModel):
    check_id: str
    verdict: Literal["안전", "주의", "위험"]
    label_id: Literal[0, 1] = Field(..., description="1=피싱·악성, 0=정상 (기준 0.5)")
    risk: float = Field(..., description="피싱·악성일 확률")
    stage: Literal["official_domain", "reputable_domain", "model"]
    host: str
    reasons: list[str]
    model_version: str


class FeedbackRequest(BaseModel):
    check_id: str
    true_label: Literal[0, 1] | None = Field(None, description="실제 결과: 1=사기였음, 0=안전했음")
    is_correct: bool | None = Field(None, description="판정이 맞았는지 (T/F)")

    @model_validator(mode="after")
    def need_one(self):
        if self.true_label is None and self.is_correct is None:
            raise ValueError("true_label 또는 is_correct 중 하나는 필요합니다")
        return self


def _verdict(risk: float) -> str:
    return "위험" if risk >= DANGER else "주의" if risk >= CAUTION else "안전"


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION, "log_sinks": logger.sink_names,
            "reputable_domains": len(REPUTABLE),
            "thresholds": {"caution": CAUTION, "danger": DANGER}}


@app.post("/v1/check", response_model=CheckResponse)
def check(req: CheckRequest, bg: BackgroundTasks):
    norm = normalize(req.url)
    host = host_of(norm).split(":")[0]
    if "." not in host or " " in norm:
        raise HTTPException(status_code=422, detail="링크 형식이 아닙니다 (예: https://example.com/...)")

    t0 = time.perf_counter()
    model_risk = float(_model.predict_proba([norm])[0][1])
    if is_official(norm):
        risk, stage, why = 0.0, "official_domain", ["정부·공공기관 전용 도메인이에요 (개인이 등록할 수 없음)"]
    elif registered_domain(host) in REPUTABLE:
        risk, stage, why = 0.0, "reputable_domain", [
            "많은 사람이 쓰는 사이트예요 (인기 상위 1만, 피싱 이력 없음). 단, 사이트 안의 글·채팅 내용까지 보장하지는 않아요"]
    else:
        risk, stage = model_risk, "model"
        why = reasons(extract(norm))
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    label_id = int(risk >= 0.5)
    cid = uuid.uuid4().hex

    with _lock:
        _recent[cid] = {"label_id": label_id}
        if len(_recent) > _RECENT_MAX:
            _recent.popitem(last=False)
        _stats["checks"] += 1
    bg.add_task(logger.log, {
        "event": "check", "check_id": cid, "ts": logger.now(),
        "url_redacted": redact(norm), "url_sha256": hashlib.sha256(norm.encode()).hexdigest(),
        "host": host, "channel": req.channel, "stage": stage,
        "pred_label": label_id, "risk": round(risk, 4), "model_risk": round(model_risk, 4), "verdict": _verdict(risk),
        "model_version": MODEL_VERSION, "latency_ms": latency_ms})

    return CheckResponse(check_id=cid, verdict=_verdict(risk), label_id=label_id, risk=round(risk, 4),
                         stage=stage, host=host, reasons=why, model_version=MODEL_VERSION)


@app.post("/v1/feedback")
def feedback(req: FeedbackRequest, bg: BackgroundTasks):
    with _lock:
        rec = _recent.get(req.check_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="알 수 없는(또는 만료된) check_id")
    pred = rec["label_id"]
    true_label = req.true_label if req.true_label is not None else (pred if req.is_correct else 1 - pred)
    is_correct = true_label == pred
    with _lock:
        _stats["feedback"] += 1
        _stats["correct"] += int(is_correct)
    bg.add_task(logger.log, {
        "event": "feedback", "check_id": req.check_id, "ts": logger.now(),
        "pred_label": pred, "true_label": true_label, "is_correct": is_correct, "model_version": MODEL_VERSION})
    return {"check_id": req.check_id, "true_label": true_label, "is_correct": is_correct}


@app.get("/v1/stats")
def stats():
    """운영 중 실제 정확도 = 사용자가 결과를 알려 준 건 중 판정이 맞은 비율."""
    with _lock:
        s = dict(_stats)
    s["live_accuracy"] = round(s["correct"] / s["feedback"], 4) if s["feedback"] else None
    s["model_version"] = MODEL_VERSION
    s["log_errors"] = logger.errors
    return s
