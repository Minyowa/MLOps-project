"""서비스 로그(CloudWatch) → 재학습용 데이터셋.

사용법 (CloudShell, 추가 설치 없이 표준 라이브러리만 사용):
    aws logs filter-log-events --log-group-name /linkguard/app --output json > logs/cloudwatch.json
    python3 scripts/prepare_feedback.py logs/cloudwatch.json

입력: CloudWatch 이벤트 JSON({"events":[{"message": "..."}]}) 또는 컨테이너 로컬 로그(JSONL)
출력: data/feedback/feedback_<날짜>.csv  — url, label(1=사기, 0=안전) 과 근거 컬럼

전처리 규칙
  1. 검사(check)와 신고(feedback)를 check_id로 이어 붙인다. 신고가 없는 검사는 정답이 없어 버린다.
  2. 같은 검사에 신고를 여러 번 누르면 마지막 신고만 쓴다.
  3. 호스트가 주소 형식이 아니면 버린다 (한글·욕설 같은 장난 입력, 점 없는 문자열 등).
  4. 같은 주소에 여러 사람이 신고하면 다수결. 동률(의견 충돌)은 버린다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_OK = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$")
IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
FIELDS = ["url", "label", "votes_scam", "votes_safe", "pred_label", "model_risk", "stage", "model_version"]


def read_events(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    try:  # CloudWatch CLI 출력
        raw = [e["message"] for e in json.loads(text)["events"]]
    except (json.JSONDecodeError, KeyError, TypeError):  # 로컬 JSONL
        raw = [line for line in text.splitlines() if line.strip()]
    events = []
    for m in raw:
        try:
            events.append(json.loads(m))
        except json.JSONDecodeError:
            pass
    return events


def valid_host(host: str) -> bool:
    host = (host or "").split(":")[0]
    return bool(HOST_OK.match(host) or IPV4.match(host))


def true_label(fb: dict) -> int | None:
    if fb.get("true_label") in (0, 1):
        return fb["true_label"]
    if fb.get("is_correct") is not None and fb.get("pred_label") in (0, 1):
        return fb["pred_label"] if fb["is_correct"] else 1 - fb["pred_label"]
    return None


def build(events: list[dict]) -> tuple[list[dict], Counter]:
    stats = Counter()
    checks = {e["check_id"]: e for e in events if e.get("event") == "check" and e.get("check_id")}
    feedback = {}
    for e in sorted((e for e in events if e.get("event") == "feedback"), key=lambda e: e.get("ts", "")):
        feedback[e.get("check_id")] = e          # 규칙 2: 마지막 신고만
    stats["검사 로그"] = len(checks)
    stats["신고 로그(검사 단위)"] = len(feedback)

    votes = defaultdict(list)
    for cid, fb in feedback.items():
        chk = checks.get(cid)
        if chk is None:
            stats["제외: 짝이 되는 검사 없음"] += 1
            continue
        label = true_label(fb)
        if label is None:
            stats["제외: 정답 없음"] += 1
            continue
        if not valid_host(chk.get("host", "")):
            stats["제외: 주소 형식 아님"] += 1     # 규칙 3
            continue
        votes[chk["url_redacted"]].append((label, chk))

    rows = []
    for url, vs in votes.items():
        c = Counter(label for label, _ in vs)
        if c[1] == c[0]:
            stats["제외: 의견 충돌(동률)"] += 1   # 규칙 4
            continue
        last = vs[-1][1]
        rows.append({"url": url, "label": int(c[1] > c[0]), "votes_scam": c[1], "votes_safe": c[0],
                     "pred_label": last.get("pred_label"), "model_risk": last.get("model_risk"),
                     "stage": last.get("stage"), "model_version": last.get("model_version")})
    rows.sort(key=lambda r: r["url"])
    stats["최종 학습 데이터(고유 주소)"] = len(rows)
    stats["└ 사기(1)"] = sum(r["label"] for r in rows)
    stats["└ 안전(0)"] = len(rows) - stats["└ 사기(1)"]
    stats["└ 당시 모델이 틀린 주소"] = sum(r["pred_label"] != r["label"] for r in rows)
    return rows, stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", type=Path, help="CloudWatch JSON 또는 로컬 JSONL 로그")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "feedback" / f"feedback_{date.today():%Y%m%d}.csv")
    args = ap.parse_args()

    rows, stats = build(read_events(args.logs))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    width = max(len(k) for k in stats) + 2
    for k, v in stats.items():
        print(f"{k:<{width}} {v}")
    print(f"\n저장: {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    if not rows:
        sys.exit("학습에 쓸 신고 데이터가 없어요")


if __name__ == "__main__":
    main()
