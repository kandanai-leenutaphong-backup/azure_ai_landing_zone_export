import asyncio
from dataclasses import replace
import json
import threading
from unittest.mock import Mock

import pytest

from agent_optimization import GradeEvaluator, RunSaveError, detector_version, measure_run, run_recovery, write_json
from agent_optimization import persistence
from test_agent_optimization import FakeDataset, NEUTRAL_PROFILE
from test_joint import definition


def test_completed_manifest_is_read_back_before_staging_is_removed(tmp_path):
    jobs = run_recovery(tmp_path, "run-1")
    outcome = jobs.commit("run-1", {"id": "run-1", "status": "completed"})
    assert outcome.saved and outcome.verified
    assert json.loads((tmp_path / "run.json").read_text()) == {"id": "run-1", "status": "completed"}
    assert list(jobs.pending()) == []


def test_failed_save_preserves_manifest_and_recommit_does_not_rerun_work(tmp_path, monkeypatch):
    jobs = run_recovery(tmp_path, "run-1")
    original_write = persistence._write

    def fail(*args, **kwargs):
        raise OSError("fixture storage failure")

    monkeypatch.setattr(persistence, "_write", fail)
    outcome = jobs.commit("run-1", {"id": "run-1", "result": [1, 2, 3]})
    assert not outcome.saved and outcome.recoverable
    assert outcome.artifact.path.is_file()
    monkeypatch.setattr(persistence, "_write", original_write)
    restarted = run_recovery(tmp_path, "run-1")
    restored = restarted.recommit(restarted.read("run-1"))
    assert restored.saved and restored.verified
    assert json.loads((tmp_path / "run.json").read_text())["result"] == [1, 2, 3]
    assert list(jobs.pending()) == []


def test_manifest_conflict_preserves_both_owned_outputs(tmp_path):
    path = tmp_path / "run.json"
    path.write_bytes(b'{"foreign":true}')
    outcome = run_recovery(tmp_path, "run-1").commit("run-1", {"id": "run-1"})
    assert outcome.state == "conflict" and outcome.recoverable
    assert path.read_bytes() == b'{"foreign":true}'


def test_immutable_json_refuses_overwrite(tmp_path):
    path = tmp_path / "generation.json"
    write_json(path, {"version": 1}, immutable=True)
    with pytest.raises(FileExistsError):
        write_json(path, {"version": 2}, immutable=True)
    assert json.loads(path.read_text()) == {"version": 1}


def test_manifest_store_refuses_another_run_identity(tmp_path):
    outcome = run_recovery(tmp_path, "run-1").commit("run-2", {"id": "run-2"})
    assert not outcome.saved and outcome.recoverable
    assert not (tmp_path / "run.json").exists()


def test_manifest_does_not_follow_a_symlink(tmp_path):
    target = tmp_path / "outside.json"
    target.write_bytes(b"preserve")
    (tmp_path / "run.json").symlink_to(target)
    outcome = run_recovery(tmp_path, "run-1").commit("run-1", {"id": "run-1"})
    assert not outcome.saved and outcome.recoverable
    assert target.read_bytes() == b"preserve"


@pytest.mark.parametrize("failed_save", [False, True])
def test_measured_run_manifest_recovers_without_repeating_prediction(tmp_path, monkeypatch, failed_save):
    calls = []

    def predict(prompt, evidence, model):
        calls.append(evidence)
        assert "expected" not in json.dumps(evidence)
        return {"grade": "accept", "rationale": "synthetic fixture"}

    dataset = FakeDataset()
    evaluator = GradeEvaluator(dataset, predict, NEUTRAL_PROFILE)
    directory = tmp_path / "measured-run"
    record = {"id": "measured-run", "stage": "training", "workers": 1}
    original_write = persistence._write

    def write(path, content, **options):
        if failed_save and path.name == "run.json":
            raise OSError("fixture manifest save failure")
        return original_write(path, content, **options)

    monkeypatch.setattr(persistence, "_write", write)

    def measure():
        return measure_run(evaluator, {"version": 1, "system_prompt": "Fixture", "model": "fixture"},
                           [], dataset.cases(), record, directory, lambda: False, lambda count: None)

    if failed_save:
        with pytest.raises(RunSaveError) as failure:
            measure()
        assert failure.value.outcome.recoverable
        monkeypatch.setattr(persistence, "_write", original_write)
        jobs = run_recovery(directory, record["id"])
        staged = jobs.read(record["id"])
        assert staged.payload["status"] == "completed"
        assert jobs.recommit(staged).verified
    else:
        assert measure()["status"] == "completed"
    assert len(calls) == len(dataset.cases())
    saved = json.loads((directory / "run.json").read_text())
    assert saved["cases_finished"] == saved["metrics"]["case_count"] == len(calls)
    assert len((directory / "cases.jsonl").read_text().splitlines()) == len(calls)
    assert (directory / "best.json").is_file() and (directory / "worst.json").is_file()


@pytest.mark.parametrize("workers", [1, 3])
@pytest.mark.parametrize("failure_stage", ["detection", "tool", "knowledge", "prediction"])
def test_callback_failures_save_only_safe_diagnostics_and_actual_attempts(tmp_path, workers, failure_stage):
    private = "synthetic-token prompt-content response-content /private/provider-path expected=reject"
    failure_type = type("PrivateProviderFailureName", (RuntimeError,), {})
    dataset = FakeDataset()
    dataset.detector_query = Mock(return_value={"rows": [{"total": 1}]})
    dataset.detector_process = Mock(return_value={"matched": True, "facts": ["One observed row"],
                                                 "technique_ids": [], "summary": {"total": 1}})

    def run_tool(case_id, tool, window):
        assert set(window) == {"start", "end"}
        if failure_stage == "tool" and tool["id"] == "second":
            raise failure_type(private)
        return {"rows": 1}

    dataset.run_tool = Mock(side_effect=run_tool)
    knowledge = Mock(return_value={"rows": []})
    predict = Mock(return_value={"grade": "accept", "rationale": "Fixture", "diagnosis": "Hypothesis",
                                 "proposed_actions": [], "citations": []})
    if failure_stage == "detection":
        dataset.detector_query.side_effect = failure_type(private)
    elif failure_stage == "knowledge":
        knowledge.side_effect = failure_type(private)
    elif failure_stage == "prediction":
        predict.side_effect = failure_type(private)
    cases = [{**case, "start_time": "2024-01-01T00:00:00Z", "end_time": "2024-01-01T00:30:00Z"}
             for case in dataset.cases()]
    tools = [{"id": name, "name": name} for name in ("first", "second", "tail")]
    candidate = {"version": 1, "system_prompt": "Fixture", "model": "fixture", "situation_detector_version": 1,
                 "knowledge_access": True, "_detector": detector_version(definition(), [], "fixture")}
    evaluator = GradeEvaluator(dataset, predict, NEUTRAL_PROFILE, knowledge_search=knowledge)
    directory = tmp_path / "new-run"
    record = measure_run(evaluator, candidate, tools, cases, {"id": "new-run", "stage": "training", "workers": workers},
                         directory, lambda: False, lambda count: None)
    saved = json.loads((directory / "run.json").read_text())
    rows = [json.loads(line) for line in (directory / "cases.jsonl").read_text().splitlines()]
    attempts = {"detection": 0, "tool": 2, "knowledge": 3, "prediction": 3}[failure_stage]
    assert saved == record
    assert saved["status"] == "completed"
    assert saved["cases_finished"] == saved["metrics"]["case_count"] == len(cases)
    assert saved["metrics"]["error_rate"] == 1 and saved["metrics"]["macro_f1"] == 0
    assert sorted(row["case_id"] for row in rows) == sorted(case["case_id"] for case in cases)
    assert all(row["error"] == f"{failure_stage}_failed" and row["predicted"] is None
               and row["correct"] is False and row["actions_executed"] is False for row in rows)
    assert all(row["tool_calls"] == attempts for row in rows)
    assert dataset.run_tool.call_count == len(cases) * attempts
    assert predict.call_count == (len(cases) if failure_stage == "prediction" else 0)
    for call in predict.call_args_list:
        assert "expected" not in json.dumps(call.args[1])
        assert "reject" not in json.dumps(call.args[1])
    for kind in ("best", "worst"):
        transcript = json.loads((directory / f"{kind}.json").read_text())["case"]["transcript"]
        assert transcript["error"] == f"{failure_stage}_failed"
        assert transcript["model_call_attempted"] is (failure_stage == "prediction")
        assert transcript["tool_ids"] == ["first", "second", "tail"]
    for path in directory.rglob("*"):
        if path.is_file():
            assert private.encode() not in path.read_bytes()
            assert failure_type.__name__.encode() not in path.read_bytes()


def test_failure_diagnostics_never_format_untrusted_exceptions():
    class UnprintableFailure(Exception):
        def __str__(self):
            raise AssertionError("Exception text must not be inspected")

    evaluator = GradeEvaluator(FakeDataset(), Mock(side_effect=UnprintableFailure()), NEUTRAL_PROFILE)
    rows, metrics = evaluator.run({"system_prompt": "Fixture", "model": "fixture"}, [], FakeDataset().cases(),
                                  lambda: False, lambda row: None, capture=True)
    assert metrics["error_rate"] == 1
    assert all(row["error"] == row["transcript"]["error"] == "prediction_failed" for row in rows)


@pytest.mark.parametrize("failure_stage", ["request", "progress"])
def test_run_failure_diagnostics_are_safe_and_historical_diagnostics_unchanged(tmp_path, failure_stage):
    private = "historical-provider-token /private/request-path prompt-content"
    historical = {"id": "old-run", "status": "failed", "error": private, "provenance": "retained fixture"}
    old_directory = tmp_path / "old-run"
    assert run_recovery(old_directory, "old-run").commit("old-run", historical).verified
    original = (old_directory / "run.json").read_bytes()

    def fail(*arguments):
        raise RuntimeError(private)

    profile = replace(NEUTRAL_PROFILE, model_request=fail) if failure_stage == "request" else NEUTRAL_PROFILE
    evaluator = GradeEvaluator(FakeDataset(), lambda *arguments: {"grade": "accept"}, profile)
    directory = tmp_path / "new-run"
    result = measure_run(evaluator, {"version": 1, "system_prompt": "Fixture", "model": "fixture"}, [], FakeDataset().cases(),
                         {"id": "new-run", "stage": "training", "workers": 1}, directory, lambda: False,
                         fail if failure_stage == "progress" else lambda count: None)
    assert result["status"] == "failed" and result["error"] == "measurement_failed"
    assert result["cases_finished"] == (0 if failure_stage == "request" else 3)
    assert json.loads((directory / "run.json").read_text()) == result
    assert private not in json.dumps(result)
    assert (old_directory / "run.json").read_bytes() == original
    assert json.loads(original) == historical


def test_evaluator_preserves_case_order_after_out_of_order_completion():
    released = threading.Event()
    dataset = FakeDataset()
    cases = dataset.cases()[:2]
    completion_order = []

    def run_tool(case_id, tool, window):
        if case_id == cases[0]["case_id"]:
            assert released.wait(timeout=5)
        return {"rows": 1}

    def progress(row):
        completion_order.append(row["case_id"])
        if row["case_id"] == cases[1]["case_id"]:
            released.set()

    answer = {"grade": "accept", "rationale": "Retained model response"}
    dataset.run_tool = run_tool
    evaluator = GradeEvaluator(dataset, lambda *arguments: answer, NEUTRAL_PROFILE)
    rows, metrics = evaluator.run({"system_prompt": "Fixture", "model": "fixture"}, [{"name": "sample"}], cases,
                                  lambda: False, progress, workers=2, capture=True)
    assert completion_order == [cases[1]["case_id"], cases[0]["case_id"]]
    assert [row["case_id"] for row in rows] == [case["case_id"] for case in cases]
    assert metrics["error_rate"] == 0
    assert all(row["tool_calls"] == 1 and row["error"] == "" and row["transcript"]["response"] == answer for row in rows)


@pytest.mark.parametrize("control", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_evaluator_propagates_control_exceptions(control):
    evaluator = GradeEvaluator(FakeDataset(), Mock(side_effect=control()), NEUTRAL_PROFILE)
    progress = Mock()
    with pytest.raises(control):
        evaluator.run({"system_prompt": "Fixture", "model": "fixture"}, [], FakeDataset().cases(), lambda: False, progress)
    progress.assert_not_called()