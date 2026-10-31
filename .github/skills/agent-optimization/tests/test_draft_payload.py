import json

import pytest

from agent_optimization.scripts.draft_payload import draft_operation, record_probe_rejection


def test_small_parts_form_the_exact_probe_payload_without_credentials(tmp_path):
    draft_operation(tmp_path, "draft", {"reset": True, "patch": {"name": "Structured evidence", "parent_version": 2, "design_audit": {"hypothesis": "Test actual observations"}}})
    tool = {"name": "category_view", "code": "def run(ctx):\n    return ctx.query(\"SELECT category FROM evidence WHERE evidence_role='Related'\")\n"}
    result = draft_operation(tmp_path, "draft", {"patch": {"design_audit": {"changes": ["Add a separate view"]}}, "append_tool": tool})
    assert result["tools"] == ["category_view"]
    payload = draft_operation(tmp_path, "probe", {"draft": True, "case_ids": ["first", "second"]})
    assert payload["proposal"]["tools"] == [tool]
    assert payload["proposal"]["design_audit"] == {"hypothesis": "Test actual observations", "changes": ["Add a separate view"]}
    assert payload["proposal"] == json.loads((tmp_path / "proposal-draft.json").read_text())
    assert "task_key" not in payload
    assert draft_operation(tmp_path, "draft", {"show": "name"})["value"] == "Structured evidence"
    assert draft_operation(tmp_path, "publish", {"probe_id": "receipt"}) == {"probe_id": "receipt"}


@pytest.mark.parametrize("payload", [{"patch": {"task_key": "not-allowed"}}, {"reset": "yes"}, {"path": "/outside"}, {"patch": {"system_prompt": "x" * 65537}}, {"patch": {"tools": [{}] * 6}}])
def test_draft_cannot_choose_paths_credentials_or_unbounded_payloads(tmp_path, payload):
    with pytest.raises(ValueError):
        draft_operation(tmp_path, "draft", payload)


def test_draft_refuses_symlink_and_empty_probe(tmp_path):
    with pytest.raises(ValueError, match="nonempty"):
        draft_operation(tmp_path, "probe", {"draft": True, "case_ids": []})
    outside = tmp_path / "outside.json"
    outside.write_text("preserve")
    (tmp_path / "proposal-draft.json").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic"):
        draft_operation(tmp_path, "draft", {"reset": True})
    assert outside.read_text() == "preserve"


def test_probe_rejection_keeps_only_bounded_admission_identifiers(tmp_path):
    payload = {"case_ids": ["mistyped-case", "other-case"], "task_key": "fixture-secret",
               "proposal": {"parent_version": 7, "system_prompt": "not-recorded",
                            "design_audit": {"parent_training_run_id": "completed-parent", "hypothesis": "not-recorded"},
                            "tools": [{"id": "retained-tool", "code": "not-recorded"}]}}
    record_probe_rejection(tmp_path, payload, 404)
    target = tmp_path / "last-probe-rejection.json"
    content = target.read_text()
    assert json.loads(content) == {"http_status": 404, "case_ids": payload["case_ids"],
                                  "parent_version": 7, "parent_training_run_id": "completed-parent",
                                  "tool_ids": ["retained-tool"]}
    assert "fixture-secret" not in content and "not-recorded" not in content
    assert oct(target.stat().st_mode)[-3:] == "600"
    record_probe_rejection(tmp_path, {"case_ids": ["later-case"]}, 400)
    assert json.loads(target.read_text())["case_ids"] == ["later-case"]
    assert len(list(tmp_path.iterdir())) == 1


def test_probe_rejection_refuses_unbounded_or_symlinked_records(tmp_path):
    with pytest.raises(ValueError, match="64 KiB"):
        record_probe_rejection(tmp_path, {"case_ids": ["x" * 65537]}, 404)
    target = tmp_path / "last-probe-rejection.json"
    assert not target.exists()
    outside = tmp_path / "outside.json"
    outside.write_text("preserve")
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic"):
        record_probe_rejection(tmp_path, {"case_ids": []}, 404)
    assert outside.read_text() == "preserve"