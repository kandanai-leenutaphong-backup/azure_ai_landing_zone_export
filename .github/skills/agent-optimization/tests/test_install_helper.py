import os
import io
import json
import runpy
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_optimization import OptimizationTerminal
from agent_optimization.scripts.install_helper import generate, helper_targets, install_helper

ORIGIN = "http://127.0.0.1:9002"
API_PATH = "/api/cyber/optimization/terminal"
# What a workspace initialized by an older generator holds: same request target, no draft support.
OLD_HELPER = '''#!/usr/bin/python3
import json, sys, urllib.request
from pathlib import Path
workspace = Path(__file__).resolve().parent
payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {{}}
access = json.loads((workspace.parent / "task-access.json").read_text())
payload.update(access)
request = urllib.request.Request({base!r} + "/" + sys.argv[1], data=json.dumps(payload).encode(),
    headers={{"Content-Type":"application/json", "X-Copilot-Terminal":"1", "Origin":{origin!r}}})
'''


def session(tmp_path, *, base=ORIGIN + API_PATH, origin=ORIGIN):
    workspace = tmp_path / "0ceb69aa-2682-45cd-b010-9990ab52563a" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "TASK.md").write_text("existing task")
    (workspace / "opt").write_text(OLD_HELPER.format(base=base, origin=origin))
    (workspace / "opt").chmod(0o500)
    return workspace


def test_install_replaces_an_older_helper_with_the_current_generator(tmp_path):
    workspace = session(tmp_path)
    receipt = install_helper(workspace, ORIGIN, API_PATH)
    helper, draft = workspace / "opt", workspace / "optimization_draft.py"
    assert receipt["session"] == workspace.parent.name and receipt["unchanged"] is False
    assert receipt["helper_before"] != receipt["helper_after"] and receipt["draft_before"] is None
    assert helper_targets(helper.read_text()) == (ORIGIN + API_PATH, ORIGIN)
    assert "from optimization_draft import draft_operation" in helper.read_text()
    compile(helper.read_text(), "opt", "exec")
    assert oct(helper.stat().st_mode)[-3:] == "500" and oct(draft.stat().st_mode)[-3:] == "400"
    assert sorted(path.name for path in workspace.iterdir()) == ["TASK.md", "opt", "optimization_draft.py"]


def test_reinstalling_the_same_helper_is_idempotent(tmp_path):
    workspace = session(tmp_path)
    first = install_helper(workspace, ORIGIN, API_PATH)
    second = install_helper(workspace, ORIGIN, API_PATH)
    assert second["unchanged"] is True
    assert (second["helper_before"], second["draft_before"]) == (first["helper_after"], first["draft_after"])
    assert second["helper_after"] == first["helper_after"] and second["draft_after"] == first["draft_after"]


@pytest.mark.parametrize("origin,api_path", [
    ("http://127.0.0.1:9003", API_PATH),
    (ORIGIN, "/api/cyber/optimization/other"),
    ("http://127.0.0.1:9002?token=x", API_PATH),
])
def test_install_refuses_to_retarget_an_existing_helper(tmp_path, origin, api_path):
    workspace = session(tmp_path)
    before = (workspace / "opt").read_text()
    with pytest.raises(ValueError):
        install_helper(workspace, origin, api_path)
    assert (workspace / "opt").read_text() == before
    assert not (workspace / "optimization_draft.py").exists()


def test_install_refuses_symlinked_targets_without_writing_through_them(tmp_path):
    workspace = session(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("preserve")
    (workspace / "optimization_draft.py").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic"):
        install_helper(workspace, ORIGIN, API_PATH)
    assert outside.read_text() == "preserve"


@pytest.mark.parametrize("prepare", [
    lambda workspace: (workspace / "opt").unlink(),
    lambda workspace: (workspace / "TASK.md").unlink(),
    lambda workspace: (workspace / "opt").unlink() or (workspace / "opt").write_text("print('no request here')"),
])
def test_install_refuses_a_workspace_that_is_not_an_initialized_session(tmp_path, prepare):
    workspace = session(tmp_path)
    prepare(workspace)
    with pytest.raises(ValueError):
        install_helper(workspace, ORIGIN, API_PATH)
    assert not (workspace / "optimization_draft.py").exists()


def test_install_refuses_directories_that_are_not_a_private_session_workspace(tmp_path):
    loose = tmp_path / "not-a-session" / "workspace"
    loose.mkdir(parents=True)
    with pytest.raises(ValueError, match="session-uuid"):
        install_helper(loose, ORIGIN, API_PATH)
    repository = Path(__file__).resolve().parents[4]
    with pytest.raises(ValueError):
        install_helper(repository / "0ceb69aa-2682-45cd-b010-9990ab52563a" / "workspace", ORIGIN, API_PATH)


def test_installed_helper_drafts_locally_without_contacting_the_backend(tmp_path):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key": "test-only-dummy"}')
    environment = dict(os.environ, PYTHONPATH=str(workspace), PATH=os.environ.get("PATH", ""))
    run = subprocess.run([sys.executable, str(workspace / "opt"), "draft",
                          '{"reset": true, "patch": {"name": "Installed by operator"}}'],
                         capture_output=True, text=True, cwd=workspace, env=environment)
    assert run.returncode == 0, run.stderr
    assert "draft_digest" in run.stdout and "test-only-dummy" not in run.stdout
    assert "Installed by operator" in (workspace / "proposal-draft.json").read_text()


def test_generate_writes_the_two_files_a_fresh_workspace_needs(tmp_path):
    digests = generate(tmp_path, ORIGIN + "/", API_PATH)
    assert set(digests) == {"draft_digest", "helper_digest"}
    assert helper_targets((tmp_path / "opt").read_text()) == (ORIGIN + API_PATH, ORIGIN)
    assert "def draft_operation" in (tmp_path / "optimization_draft.py").read_text()


@pytest.mark.parametrize("action,stage_field,status", [
    ("tune", "training_run_id", "tuned"),
    ("tune", "training_run_id", "tuning"),
    ("evaluate", "evaluation_id", "completed"),
    ("evaluate", "evaluation_id", "running"),
    ("evaluate", "evaluation_id", "failed"),
])
def test_helper_reads_existing_stage_instead_of_starting_another(tmp_path, monkeypatch, capsys, action, stage_field, status):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), action, '{"version":6}'])
    calls = []
    feedback = {"version": 6, "version_status": status, "stage_counts": {"training": 3, "evaluation": 2}, stage_field: "existing-run"}

    def respond(request, **options):
        calls.append(request.full_url)
        return io.BytesIO(json.dumps(feedback).encode())

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    with pytest.raises(SystemExit) as ended:
        runpy.run_path(str(workspace / "opt"), run_name="__main__")
    assert ended.value.code == 0
    assert calls == [ORIGIN + API_PATH + "/feedback"]
    result = json.loads(capsys.readouterr().out)
    assert result["stage_reused"] is True and result[stage_field] == "existing-run"
    assert "fixture-access" not in json.dumps(result)


def test_helper_admits_only_a_missing_saved_stage(tmp_path, monkeypatch, capsys):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), "evaluate", '{"version":6}'])
    calls = []

    def respond(request, **options):
        calls.append(request.full_url)
        result = {"version": 6, "stage_counts": {"training": 3, "evaluation": 2}, "training_run_id": "complete"}
        if request.full_url.endswith("/evaluate"):
            result["evaluation_id"] = "new-run"
        return io.BytesIO(json.dumps(result).encode())

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    runpy.run_path(str(workspace / "opt"), run_name="__main__")
    assert calls == [ORIGIN + API_PATH + "/feedback", ORIGIN + API_PATH + "/evaluate"]
    assert json.loads(capsys.readouterr().out)["evaluation_id"] == "new-run"


@pytest.mark.parametrize("fields", [None, ["training_run_id", "development_failures"]])
def test_helper_feedback_keeps_authoring_ids_visible_in_large_responses(tmp_path, monkeypatch, capsys, fields):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    payload = {"version": 4, **({"fields": fields} if fields else {})}
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), "feedback", json.dumps(payload)])
    failures = [{"case_id": f"case-{grade}-{index}", "expected": grade, "predicted": "other", "correct": False}
                for grade in ("true_positive", "benign_positive", "false_positive") for index in range(6)]
    feedback = {"version": 4, "stage_counts": {"training": 5958, "evaluation": 1200},
                "operator_guidance": [{"guidance": "large historical guidance " * 2000},
                                      {"id": "latest-note", "guidance": "Reuse the exact current development IDs."}],
                "development_failures": failures, "training_run_id": "exact-parent-run",
                "agent_configuration": {"version": 4, "system_prompt": "Exact immutable parent prompt."},
                "training_metrics": {"macro_f1": 0.4, "per_class": {"true_positive": {"support": 2000}}},
                "evaluation_metrics": {"macro_f1": 0.3}}

    def respond(request, **options):
        sent = json.loads(request.data)
        assert sent == {"version": 4, "task_key": "fixture-access"}
        assert request.full_url == ORIGIN + API_PATH + "/feedback"
        return io.BytesIO(json.dumps(feedback).encode())

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    runpy.run_path(str(workspace / "opt"), run_name="__main__")
    output = capsys.readouterr().out
    assert len(output.encode()) < 6000
    result = json.loads(output)
    assert result["training_run_id"] == "exact-parent-run"
    assert "fixture-access" not in output
    if fields:
        assert result == {field: feedback[field] for field in fields}
    else:
        assert {case["expected"] for case in result["development_examples"]} == {"true_positive", "benign_positive", "false_positive"}
        assert output.index('"development_examples"') < output.index('"training_metrics"')
        assert result["agent_configuration"] == feedback["agent_configuration"]
        assert result["latest_operator_guidance"] == feedback["operator_guidance"][-1]
        assert result["training_metrics"] == {"macro_f1": 0.4}
        assert "large historical guidance" not in output
        assert "operator_guidance" in result["available_fields"] and "more" in result


@pytest.mark.parametrize("payload", [{"version": 0}, {"version": True}, {"version": "6"},
                                    {"version": 6, "fields": ["training_run_id"]}])
def test_helper_rejects_invalid_stage_payload_before_any_request(tmp_path, monkeypatch, payload):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), "tune", json.dumps(payload)])
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *arguments, **options: calls.append(arguments))
    with pytest.raises(SystemExit):
        runpy.run_path(str(workspace / "opt"), run_name="__main__")
    assert calls == []


def test_helper_refuses_backend_fallback_to_another_version(tmp_path, monkeypatch):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), "tune", '{"version":99}'])
    calls = []

    def respond(request, **options):
        calls.append(request.full_url)
        return io.BytesIO(b'{"version":6,"stage_counts":{"training":5958},"training_run_id":"existing"}')

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    with pytest.raises(SystemExit, match="not the returned saved version"):
        runpy.run_path(str(workspace / "opt"), run_name="__main__")
    assert calls == [ORIGIN + API_PATH + "/feedback"]


@pytest.mark.parametrize("status,started,expected_calls", [(409, True, 3), (400, False, 3), (403, True, 2)])
def test_helper_recognizes_only_a_read_back_coordinator_race(tmp_path, monkeypatch, capsys, status, started, expected_calls):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), "evaluate", '{"version":6}'])
    calls = []

    def respond(request, **options):
        calls.append(request.full_url)
        if request.full_url.endswith("/evaluate"):
            raise urllib.error.HTTPError(request.full_url, status, "refused", {}, io.BytesIO(b'{"detail":"refused"}'))
        feedback = {"version": 6, "stage_counts": {"training": 5958, "evaluation": 1200}, "version_status": "tuned"}
        if len(calls) > 1 and started:
            feedback.update(evaluation_id="coordinator-run", version_status="running")
        return io.BytesIO(json.dumps(feedback).encode())

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    with pytest.raises(SystemExit) as ended:
        runpy.run_path(str(workspace / "opt"), run_name="__main__")
    assert len(calls) == expected_calls
    assert calls.count(ORIGIN + API_PATH + "/evaluate") == 1
    result = json.loads(capsys.readouterr().out)
    assert ended.value.code == (0 if status == 409 and started else 1)
    assert result.get("stage_reused", False) is (status == 409 and started)


@pytest.mark.parametrize("status", [400, 401, 404])
def test_helper_records_rejected_probe_identifiers_without_retry_or_credentials(tmp_path, monkeypatch, capsys, status):
    workspace = session(tmp_path)
    install_helper(workspace, ORIGIN, API_PATH)
    (workspace.parent / "task-access.json").write_text('{"task_key":"fixture-access"}')
    monkeypatch.syspath_prepend(str(workspace))
    payload = {"case_ids": ["mistyped", "other"], "proposal": {"parent_version": 7,
               "design_audit": {"parent_training_run_id": "completed-parent"}, "tools": [{"id": "retained"}]}}
    monkeypatch.setattr(sys, "argv", [str(workspace / "opt"), "probe", json.dumps(payload)])
    calls = []

    def respond(request, **options):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, status, "refused", {}, io.BytesIO(b'{"detail":"refused"}'))

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    with pytest.raises(SystemExit) as ended:
        runpy.run_path(str(workspace / "opt"), run_name="__main__")
    assert ended.value.code == 1
    assert calls == [ORIGIN + API_PATH + "/probe"]
    output = capsys.readouterr().out
    assert json.loads(output) == {"detail": "refused"}
    saved = (workspace / "last-probe-rejection.json").read_text()
    assert json.loads(saved)["case_ids"] == payload["case_ids"]
    assert json.loads(saved)["http_status"] == status
    assert "fixture-access" not in saved + output


@pytest.mark.parametrize("number", [None, 1, 2, 99, True])
def test_cli_feedback_exposes_only_the_exact_owned_version_configuration(number):
    versions = [{"version": index, "system_prompt": f"Exact parent prompt {index}",
                 "tool_ids": [f"tool-{index}"], "situation_detector_version": index,
                 "situation_detector_digest": f"detector-{index}", "knowledge_access": True,
                 "private_field": "not-in-configuration"} for index in (1, 2)]
    calls = []

    def get(owner, identifier):
        calls.append((owner, identifier))
        return {"status": "ready", "versions": versions}

    terminal = OptimizationTerminal.__new__(OptimizationTerminal)
    terminal.bindings = {"/workspace": ("owner", "experiment")}
    terminal.service = SimpleNamespace(get=get, feedback=lambda owner, identifier, selected:
                                      {"version": selected if selected is not None else 2})
    operation = terminal.operation("feedback")
    if number is not None and (type(number) is not int or number not in (1, 2)):
        with pytest.raises(ValueError, match="existing integer version"):
            operation(Path("/workspace"), {"version": number}, {})
    else:
        result = operation(Path("/workspace"), {"version": number}, {})
        selected = versions[(number or 2) - 1]
        assert result["agent_configuration"] == {field: value for field, value in selected.items() if field != "private_field"}
    assert calls == [("owner", "experiment")]
    with pytest.raises(PermissionError, match="No experiment bound"):
        operation(Path("/unbound"), {}, {})
