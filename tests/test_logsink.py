"""CloudWatch / S3 싱크를 가짜 AWS(moto)로 검증."""
import json

import boto3
import pytest
from moto import mock_aws

from reviewpulse.logsink import CloudWatchSink, EventLogger, S3Sink

EVENT = {"event": "prediction", "prediction_id": "abc123", "ts": "2026-10-26T08:15:30.123+00:00",
         "text": "재밌어요", "pred_label": 1, "prob_positive": 0.91}


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        yield


def test_cloudwatch_sink_writes_json(aws):
    sink = CloudWatchSink("/reviewpulse/app", "api-test")
    CloudWatchSink("/reviewpulse/app", "api-test")          # 이미 있어도 실패하지 않음
    sink.send(EVENT)
    out = boto3.client("logs").get_log_events(logGroupName="/reviewpulse/app", logStreamName="api-test")
    assert json.loads(out["events"][0]["message"]) == EVENT


def test_s3_sink_partitioned_key(aws):
    boto3.client("s3").create_bucket(Bucket="rp-logs",
                                     CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"})
    sink = S3Sink("rp-logs", "logs/")
    sink.send(EVENT)
    keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket="rp-logs")["Contents"]]
    assert keys == ["logs/prediction/dt=2026-10-26/20261026T081530.123+0000-abc123.json"]


def test_from_env_builds_all_sinks(aws, monkeypatch, tmp_path):
    boto3.client("s3").create_bucket(Bucket="rp-logs",
                                     CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"})
    monkeypatch.setenv("LOG_SINKS", "local,cloudwatch,s3")
    monkeypatch.setenv("LOCAL_LOG_PATH", str(tmp_path / "e.jsonl"))
    monkeypatch.setenv("S3_BUCKET", "rp-logs")
    lg = EventLogger.from_env()
    assert lg.sink_names == ["local", "cloudwatch", "s3"]
    lg.log(EVENT)
    assert lg.errors == 0
