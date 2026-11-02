"""CloudWatch / S3 전송을 가짜 AWS(moto)로 검증."""
import json

import boto3
import pytest
from moto import mock_aws

from linkguard.logsink import CloudWatchSink, EventLogger, S3Sink

EVENT = {"event": "check", "check_id": "abc123", "ts": "2026-10-26T09:15:30.123+00:00",
         "url_redacted": "x.top/a?phone=*", "pred_label": 1, "risk": 0.97}


@pytest.fixture
def aws(monkeypatch):
    for k, v in {"AWS_DEFAULT_REGION": "ap-northeast-2", "AWS_ACCESS_KEY_ID": "testing",
                 "AWS_SECRET_ACCESS_KEY": "testing"}.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="lg-logs",
                                         CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"})
        yield


def test_cloudwatch(aws):
    sink = CloudWatchSink("/linkguard/app", "api-test")
    CloudWatchSink("/linkguard/app", "api-test")   # 이미 있어도 실패하지 않음
    sink.send(EVENT)
    out = boto3.client("logs").get_log_events(logGroupName="/linkguard/app", logStreamName="api-test")
    assert json.loads(out["events"][0]["message"]) == EVENT


def test_s3_partitioned_key(aws):
    S3Sink("lg-logs", "logs/").send(EVENT)
    keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket="lg-logs")["Contents"]]
    assert keys == ["logs/check/dt=2026-10-26/20261026T091530.123+0000-abc123.json"]


def test_from_env_all_sinks(aws, monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_SINKS", "local,cloudwatch,s3")
    monkeypatch.setenv("LOCAL_LOG_PATH", str(tmp_path / "e.jsonl"))
    monkeypatch.setenv("S3_BUCKET", "lg-logs")
    lg = EventLogger.from_env()
    assert lg.sink_names == ["local", "cloudwatch", "s3"]
    lg.log(EVENT)
    assert lg.errors == 0
