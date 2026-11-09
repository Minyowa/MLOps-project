"""CloudWatch 로그 → 재학습 데이터 전처리 규칙."""
import json

from scripts.prepare_feedback import build, read_events


def chk(cid, url, host, pred, risk=0.5):
    return {"event": "check", "check_id": cid, "url_redacted": url, "host": host,
            "pred_label": pred, "model_risk": risk, "stage": "model", "model_version": "v1"}


def fb(cid, ts, true_label=None, is_correct=None, pred=None):
    return {"event": "feedback", "check_id": cid, "ts": ts, "true_label": true_label,
            "is_correct": is_correct, "pred_label": pred}


EVENTS = [
    chk("a", "ggole.com/", "ggole.com", 0), fb("a", "1", true_label=1),          # 모델이 틀림 → 사기
    chk("b", "pkg.go.dev/", "pkg.go.dev", 1),
    fb("b", "1", true_label=1), fb("b", "2", true_label=0),                     # 마지막 신고(안전)만
    chk("c", "시발.com/", "시발.com", 0), fb("c", "1", true_label=0),            # 장난 입력 → 제외
    chk("d", "x.top/", "x.top", 1), fb("d", "1", true_label=1),
    chk("e", "x.top/", "x.top", 1), fb("e", "1", true_label=0),                 # 1:1 충돌 → 제외
    chk("f", "a.xyz/", "a.xyz", 1), fb("f", "1", is_correct=True, pred=1),      # is_correct로 정답 복원
    chk("g", "nolabel.com/", "nolabel.com", 0),                                 # 신고 없음 → 제외
    fb("zz", "1", true_label=1),                                                # 짝 없는 신고 → 제외
]


def test_rules():
    rows, stats = build(EVENTS)
    got = {r["url"]: r["label"] for r in rows}
    assert got == {"ggole.com/": 1, "pkg.go.dev/": 0, "a.xyz/": 1}
    assert stats["제외: 주소 형식 아님"] == 1
    assert stats["제외: 의견 충돌(동률)"] == 1
    assert stats["제외: 짝이 되는 검사 없음"] == 1
    assert stats["└ 당시 모델이 틀린 주소"] == 2   # ggole(0→1), pkg.go.dev(1→0)


def test_reads_cloudwatch_and_jsonl(tmp_path):
    cw = tmp_path / "cw.json"
    cw.write_text(json.dumps({"events": [{"message": json.dumps(e)} for e in EVENTS]}))
    jl = tmp_path / "local.jsonl"
    jl.write_text("\n".join(json.dumps(e) for e in EVENTS) + "\nnot json\n")
    assert read_events(cw) == read_events(jl) == EVENTS
