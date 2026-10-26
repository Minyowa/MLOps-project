"""검사·신고 로그 수집기.

이벤트 2종류를 JSON 한 줄씩 남긴다.
  - check    : 검사한 링크(쿼리 값 제거), 예측값, 확률, 모델 버전, 지연 시간
  - feedback : 사용자가 알려 준 실제 결과(사기였음/안전했음)

싱크(LOG_SINKS 환경변수, 쉼표 구분)
  - local      : logs/events.jsonl (기본값, AWS 없이도 동작)
  - cloudwatch : CloudWatch Logs  (CW_LOG_GROUP, CW_LOG_STREAM)
  - s3         : S3 객체 1건 = 이벤트 1건
                 s3://{S3_BUCKET}/{S3_PREFIX}{event}/dt=YYYY-MM-DD/{시각}-{check_id}.json
                 (dt= 파티션 형식이라 나중에 Athena로 바로 조회 가능)

AWS 자격 증명은 boto3 기본 방식(환경변수, ~/.aws, EC2 역할 등)을 따른다.
로그 전송이 실패해도 예측 API는 멈추지 않는다(로그는 best-effort, 실패는 stderr에 기록).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class LocalSink:
    name = "local"

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def send(self, event: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


class CloudWatchSink:
    name = "cloudwatch"

    def __init__(self, group: str, stream: str, client=None):
        import boto3
        self.client = client or boto3.client("logs")
        self.group, self.stream = group, stream
        self._lock = threading.Lock()
        for call, kwargs in ((self.client.create_log_group, {"logGroupName": group}),
                             (self.client.create_log_stream, {"logGroupName": group, "logStreamName": stream})):
            try:
                call(**kwargs)
            except self.client.exceptions.ResourceAlreadyExistsException:
                pass

    def send(self, event: dict) -> None:
        with self._lock:
            self.client.put_log_events(
                logGroupName=self.group, logStreamName=self.stream,
                logEvents=[{"timestamp": int(time.time() * 1000),
                            "message": json.dumps(event, ensure_ascii=False)}])


class S3Sink:
    name = "s3"

    def __init__(self, bucket: str, prefix: str = "logs/", client=None):
        import boto3
        self.client = client or boto3.client("s3")
        self.bucket, self.prefix = bucket, prefix

    def key_for(self, event: dict) -> str:
        ts = event["ts"]
        return (f"{self.prefix}{event['event']}/dt={ts[:10]}/"
                f"{ts.replace(':', '').replace('-', '')}-{event['check_id']}.json")

    def send(self, event: dict) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self.key_for(event),
                               Body=json.dumps(event, ensure_ascii=False).encode(),
                               ContentType="application/json")


class EventLogger:
    def __init__(self, sinks):
        self.sinks = list(sinks)
        self.errors = 0

    @classmethod
    def from_env(cls) -> "EventLogger":
        names = [s.strip() for s in os.getenv("LOG_SINKS", "local").split(",") if s.strip()]
        sinks = []
        for n in names:
            if n == "local":
                sinks.append(LocalSink(os.getenv("LOCAL_LOG_PATH", "logs/events.jsonl")))
            elif n == "cloudwatch":
                sinks.append(CloudWatchSink(os.getenv("CW_LOG_GROUP", "/linkguard/app"),
                                            os.getenv("CW_LOG_STREAM", f"api-{os.getpid()}")))
            elif n == "s3":
                sinks.append(S3Sink(os.environ["S3_BUCKET"], os.getenv("S3_PREFIX", "logs/")))
            else:
                raise ValueError(f"알 수 없는 LOG_SINKS 항목: {n}")
        return cls(sinks)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def log(self, event: dict) -> None:
        for sink in self.sinks:
            try:
                sink.send(event)
            except Exception as e:  # 로그 실패가 서비스 장애가 되지 않도록
                self.errors += 1
                print(f"[logsink] {sink.name} 전송 실패: {e!r}", file=sys.stderr)

    @property
    def sink_names(self) -> list[str]:
        return [s.name for s in self.sinks]
