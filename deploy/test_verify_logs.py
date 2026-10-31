import json

import pytest

import verify_logs


def test_query_decodes_dynamic_values_but_preserves_plain_strings(monkeypatch):
    monkeypatch.setattr(verify_logs, "az", lambda *args: {"tables": [{
        "columns": [
            {"name": "operations", "type": "dynamic"},
            {"name": "status", "type": "string"},
            {"name": "events", "type": "long"},
        ],
        "rows": [['["triage","policy"]', "completed", 2]],
    }]})
    assert verify_logs.query("synthetic query") == [{
        "operations": ["triage", "policy"], "status": "completed", "events": 2,
    }]


def test_chat_readback_checks_each_completed_turn_without_claiming_chat_judging(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_logs, "STATE", tmp_path)
    (tmp_path / "smoke.json").write_text(json.dumps({"results": [{"trace_id": "a" * 32}]}))
    (tmp_path / "chat-browser-verification.json").write_text(json.dumps({
        "status": "passed", "turns": [
            {"status": "completed", "trace_id": "b" * 32},
            {"status": "completed", "trace_id": "c" * 32},
        ],
    }))
    calls = []

    def summary(trace_id, operations):
        calls.append((trace_id, operations))
        return {"event_count": 1, "missing_fields": 0, "operations": sorted(operations)}

    monkeypatch.setattr(verify_logs, "trace_summary", summary)
    monkeypatch.setattr(verify_logs, "query", lambda _: [
        {"tier": tier} for tier in ("system", "journey", "agent")])
    result = verify_logs.verify()
    assert calls == [("a" * 32, verify_logs.OPERATIONS),
                     ("b" * 32, {"chat.turn"}), ("c" * 32, {"chat.turn"})]
    assert [row["trace_id"] for row in result["chat_traces"]] == ["b" * 32, "c" * 32]


def test_trace_readback_refuses_missing_fields_and_invalid_ids(monkeypatch):
    monkeypatch.setattr(verify_logs, "query", lambda _: [
        {"event_count": 1, "missing_fields": 1, "operations": ["chat.turn"]}])
    with pytest.raises(RuntimeError, match="structured fields"):
        verify_logs.trace_summary("b" * 32, {"chat.turn"})
    with pytest.raises(ValueError, match="invalid trace ID"):
        verify_logs.trace_summary('bad"', {"chat.turn"})
