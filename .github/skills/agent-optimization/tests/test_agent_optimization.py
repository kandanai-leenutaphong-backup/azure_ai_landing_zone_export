"""The optimization component, exercised with a neutral domain and no application import.

The point of these checks is independence: a second host, with its own labels, scorer name,
tool families and authorization rule, gets a working optimization ledger out of the same code
any other host runs — without an application package ever being imported.
"""

import json
import sys
import subprocess
import tempfile
import unittest
from asyncio import CancelledError
from contextvars import ContextVar
from pathlib import Path
from threading import Barrier, Event, Thread
from time import monotonic
from unittest.mock import patch

from agentcraft_core import CallerContext, ExecutionContext, current_execution, reserve

from agent_optimization import (
    GradeEvaluator,
    OptimizationProfile,
    OptimizationService,
    PROTOCOLS,
    PythonToolRunner,
    score,
)

LABELS = ("accept", "review", "reject")

TOOL_CODE = "def run(ctx):\n    return {'rows': 1}\n"


def neutral_request(prompt, evidence, model):
    return {"model": model, "instructions": prompt, "input": json.dumps(evidence), "store": False}


NEUTRAL_PROFILE = OptimizationProfile(
    grades=LABELS,
    scorer_version="neutral-macro-f1-v1",
    tool_runtime="neutral-python-tool-v1",
    tool_families=("sampling", "calibration"),
    objective="Neutral triage decision quality",
    baseline_proposal={"name": "Neutral baseline", "system_prompt": "Decide the outcome.",
                       "rationale": "Control.", "parent_version": None,
                       "tools": [{"name": "basic", "code": TOOL_CODE, "description": "Sample rows.",
                                  "queries": "Rows.", "returns": "A count.", "logic": "Counts."}]},
    model_request=neutral_request,
    runtime={"tool_runtime": "neutral-python-tool-v1", "max_output_tokens": 128},
)


class FakeDataset:
    """The structural protocol the component depends on. No domain meaning lives here."""

    profile_digest = "neutral-profile-digest"

    def describe(self):
        return {"dataset_id": "neutral"}

    def cases(self):
        return [{"case_id": character * 16, "expected": label, "split": split,
                 "start_time": "2024-01-01", "end_time": "2024-01-02"}
                for character, label, split in (("a", "accept", "development"),
                                                ("b", "review", "validation"),
                                                ("c", "reject", "validation"))]

    def query(self, case_id, sql):
        return {"columns": ["rows"], "rows": [[1]], "truncated": False}

    def full_cases(self):
        return [{**case, "stage": "training" if case["split"] == "development" else "evaluation"}
                for case in self.cases()]

    def profiles(self):
        return {"columns": [], "rows": []}

    def run_tool(self, case_id, tool, scope=None):
        return {"rows": 1}


def owner_of(caller):
    if caller != "operator":
        raise PermissionError("Only the operator may optimize")
    return "operator-directory"


class AgentOptimizationComponentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = OptimizationService(FakeDataset(), self.root / "experiments", "neutral-model",
                                           lambda prompt, evidence, model: {"grade": "accept", "rationale": "fixture"},
                                           authorize=owner_of, profile=NEUTRAL_PROFILE)
        self.addCleanup(self.service.close)

    def _completed_final_fixture(self):
        with patch.object(self.service.dataset, "stress_cases", lambda final=False: self.service.case_set, create=True):
            experiment = self.service.create("operator", "Synthetic final eligibility", "stress-10")
        self.service.futures[experiment["id"]].result(timeout=10)
        with self.service.lock:
            experiment = self.service.get("operator", experiment["id"])
            experiment["status"] = "completed"
            self.service._store("operator", experiment)
        return experiment

    def test_component_imports_without_the_application(self):
        result = subprocess.run([sys.executable, "-c", "import sys; import agent_optimization; assert not any(name.startswith('app.') for name in sys.modules)"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_neutral_host_gets_a_measured_baseline_ledger(self):
        experiment = self.service.create("operator", "Neutral experiment")
        self.service.futures[experiment["id"]].result(timeout=10)
        saved = self.service.get("operator", experiment["id"])
        self.assertEqual(saved["scorer_version"], "neutral-macro-f1-v1")
        self.assertEqual(saved["tool_runtime"], "neutral-python-tool-v1")
        self.assertEqual(saved["objective"], "Neutral triage decision quality")
        evaluation = saved["versions"][0]["evaluations"][-1]
        self.assertEqual(evaluation["status"], "completed")
        self.assertEqual(sorted(evaluation["metrics"]["per_class"]), sorted(LABELS))
        self.assertEqual(evaluation["metrics"]["case_count"], 3)
        self.assertTrue((self.root / "experiments" / "operator-directory" / experiment["id"] / "experiment.json").exists())

    def test_outer_evaluation_failure_persists_safe_machine_metadata(self):
        sentinel = "private-provider-response-outer-evaluation"
        with patch.object(self.service.evaluator, "run", side_effect=RuntimeError(sentinel)):
            experiment = self.service.create("operator", "Failed evaluation")
            self.service.futures[experiment["id"]].result(timeout=10)
        saved = self.service.get("operator", experiment["id"])
        version = saved["versions"][0]
        evaluation = version["evaluations"][-1]
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(version["status"], "failed")
        self.assertEqual(evaluation["status"], "failed")
        self.assertEqual(evaluation["error"], "measurement_failed")
        self.assertEqual(version["error"], "measurement_failed")
        self.assertEqual(evaluation["failure"], {
            "code": "measurement_failed", "category": "failed", "capability_id": "agent-optimization",
            "operation": "evaluate", "run_id": evaluation["id"], "effect": "unknown",
            "retry": "read_back_first", "action": "inspect_record",
        })
        self.assertEqual(version["failure"], evaluation["failure"])
        for path in self.root.rglob("*.json"):
            self.assertNotIn(sentinel, path.read_text())

    def test_publish_failures_preserve_native_errors_without_capturing_exception_text(self):
        for error_type, code, category in ((ValueError, "candidate_rejected", "invalid"),
                                            (TypeError, "publish_failed", "failed"),
                                            (RuntimeError, "publish_failed", "failed")):
            with self.subTest(error_type=error_type.__name__):
                class PrivateError(error_type):
                    def __str__(self):
                        raise AssertionError("exception_text_inspected")

                experiment = self.service.create("operator", "Publish diagnostics")
                identifier = experiment["id"]
                self.service.futures[identifier].result(timeout=10)
                directory = self.service.directory("operator", identifier)
                historical = directory / "rejections" / "historical.json"
                historical.parent.mkdir()
                historical.write_bytes(b'{"at":"2000-01-01","proposal":{"name":"old"},"error":"historical diagnostic"}\n')
                immutable = {path: path.read_bytes() for path in directory.rglob("*.json")
                             if path.name != "experiment.json"}
                proposal = {**NEUTRAL_PROFILE.baseline_proposal, "name": "Next", "parent_version": 1}
                original_proposal = json.dumps(proposal, sort_keys=True)
                error = PrivateError("private-publish-response")
                with patch.object(self.service, "_publish", side_effect=error):
                    with self.assertRaises(error_type) as caught:
                        self.service.publish("operator", identifier, proposal)
                self.assertIs(caught.exception, error)
                saved = self.service.get("operator", identifier)
                rejection = saved["rejections"][-1]
                failure = {"code": code, "category": category, "capability_id": "agent-optimization",
                           "operation": "publish", "experiment_id": identifier, "rejection_id": rejection["id"],
                           "effect": "unknown", "retry": "read_back_first", "action": "inspect_record"}
                self.assertEqual(rejection["error"], code)
                self.assertEqual(rejection["failure"], failure)
                self.assertEqual(rejection["proposal"], proposal)
                self.assertEqual(saved["events"][-1]["event"], "candidate_rejected")
                self.assertEqual(saved["events"][-1]["detail"], code)
                self.assertEqual(saved["events"][-1]["failure"], failure)
                self.assertEqual(json.dumps(proposal, sort_keys=True), original_proposal)
                for path, contents in immutable.items():
                    self.assertEqual(path.read_bytes(), contents)
                for path in directory.rglob("*.json"):
                    self.assertNotIn("private-publish-response", path.read_text())
                    self.assertNotIn("PrivateError", path.read_text())

    def test_outer_final_failure_persists_safe_machine_metadata(self):
        experiment = self._completed_final_fixture()
        sentinel = "private-provider-response-outer-final"
        with patch.object(self.service.evaluator, "run", side_effect=RuntimeError(sentinel)):
            self.service.verify_final("operator", experiment["id"])
            self.service.futures[experiment["id"]].result(timeout=10)
        saved = self.service.get("operator", experiment["id"])
        record = saved["final_verification"]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error"], "measurement_failed")
        self.assertEqual(record["failure"], {
            "code": "measurement_failed", "category": "failed", "capability_id": "agent-optimization",
            "operation": "verify_final", "run_id": record["id"], "effect": "unknown",
            "retry": "read_back_first", "action": "inspect_record",
        })
        path = self.service.directory("operator", experiment["id"]) / "final-evaluations" / f"{record['id']}.json"
        self.assertEqual(json.loads(path.read_text()), record)
        for path in self.root.rglob("*.json"):
            self.assertNotIn(sentinel, path.read_text())

    def test_the_injected_authorization_decides_who_may_read(self):
        experiment = self.service.create("operator", "Owned")
        self.service.futures[experiment["id"]].result(timeout=10)
        with self.assertRaises(PermissionError):
            self.service.get("intruder", experiment["id"])

    def test_outer_handlers_propagate_control_exceptions_without_persisting_text(self):
        sentinel = "private-outer-control-exception"
        for operation in ("evaluate", "verify_final"):
            for control in (KeyboardInterrupt, SystemExit, CancelledError):
                with self.subTest(operation=operation, control=control.__name__):
                    experiment = self._completed_final_fixture() if operation == "verify_final" else None
                    error = control(sentinel)
                    with patch.object(self.service.evaluator, "run", side_effect=error):
                        if operation == "verify_final":
                            self.service.verify_final("operator", experiment["id"])
                        else:
                            experiment = self.service.create("operator", "Control propagation")
                        with self.assertRaises(control) as caught:
                            self.service.futures[experiment["id"]].result(timeout=5)
                    self.assertIs(caught.exception, error)
                    saved = self.service.get("operator", experiment["id"])
                    record = (saved["final_verification"] if operation == "verify_final" else
                              saved["versions"][0]["evaluations"][-1])
                    self.assertNotEqual(record["status"], "completed")
        for path in self.root.rglob("*.json"):
            self.assertNotIn(sentinel, path.read_text())

    def test_close_waits_for_worker_persistence_without_holding_its_lock(self):
        entered, release, signalled, closed = Event(), Event(), Event(), Event()
        failures, late_writes = [], []
        original_run, original_store = self.service.evaluator.run, self.service._store

        def run(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return original_run(*args, **kwargs)

        def store(*args):
            late_writes.append(closed.is_set())
            return original_store(*args)

        def close():
            try:
                self.service.close(timeout=2)
            except BaseException as error:
                failures.append(error)
            finally:
                closed.set()

        with patch.object(self.service.evaluator, "run", side_effect=run), patch.object(self.service, "_store", side_effect=store):
            experiment = self.service.create("operator", "Cooperative close")
            future = self.service.futures[experiment["id"]]
            self.assertTrue(entered.wait(timeout=5))
            stop = self.service.stops[experiment["id"]]
            original_set = stop.set

            def signal():
                original_set()
                signalled.set()

            closer = Thread(target=close)
            try:
                with patch.object(stop, "set", side_effect=signal):
                    closer.start()
                    self.assertTrue(signalled.wait(timeout=5))
                    self.assertFalse(closed.is_set())
                    release.set()
                    closer.join(timeout=5)
                    self.assertFalse(closer.is_alive())
                    self.assertEqual(failures, [])
                    self.assertTrue(future.done())
            finally:
                release.set()
                closer.join(timeout=5)
                future.result(timeout=5)
        self.assertTrue(late_writes)
        self.assertFalse(any(late_writes))
        saved = self.service.get("operator", experiment["id"])
        self.assertEqual(saved["versions"][0]["evaluations"][-1]["status"], "cancelled")
        self.assertIsNone(self.service.close(timeout=0))

    def test_close_timeout_is_incomplete_and_new_submissions_write_nothing(self):
        entered, release = Event(), Event()
        original_run = self.service.evaluator.run

        def run(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return original_run(*args, **kwargs)

        with patch.object(self.service.evaluator, "run", side_effect=run):
            experiment = self.service.create("operator", "Unsettled close")
            future = self.service.futures[experiment["id"]]
            try:
                self.assertTrue(entered.wait(timeout=5))
                started = monotonic()
                with self.assertRaisesRegex(TimeoutError, "^optimization_close_timeout$"):
                    self.service.close(timeout=0.05)
                self.assertLess(monotonic() - started, 1)
                self.assertFalse(future.done())
                self.assertEqual(self.service.get("operator", experiment["id"])["status"], "baseline_running")
                before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
                submissions = (
                    lambda: self.service.create("operator", "Refused after close"),
                    lambda: self.service.evaluate("operator", experiment["id"], 1),
                    lambda: self.service.measure("operator", experiment["id"], 1, "training"),
                    lambda: self.service.verify_final("operator", experiment["id"]),
                )
                for submit in submissions:
                    with self.assertRaisesRegex(RuntimeError, "^optimization_service_closing$"):
                        submit()
                self.assertEqual(before, {path.relative_to(self.root): path.read_bytes()
                                          for path in self.root.rglob("*") if path.is_file()})
            finally:
                release.set()
                future.result(timeout=5)
                self.service.close(timeout=1)
        with self.assertRaisesRegex(RuntimeError, "^optimization_service_closing$"):
            self.service.create("operator", "Refused after settlement")

    def test_close_tracks_reassigned_futures_and_cancels_queued_records(self):
        yielded, release = Event(), Event()
        original_evaluate = self.service._evaluate

        def evaluate(*args):
            original_evaluate(*args)
            if not yielded.is_set():
                yielded.set()
                self.assertTrue(release.wait(timeout=5))

        with patch.object(self.service, "_evaluate", side_effect=evaluate), patch.object(
                self.service.evaluator, "run", wraps=self.service.evaluator.run) as run:
            experiment = self.service.create("operator", "Reassigned future")
            first = self.service.futures[experiment["id"]]
            try:
                self.assertTrue(yielded.wait(timeout=5))
                self.service.evaluate("operator", experiment["id"], 1)
                second = self.service.futures[experiment["id"]]
                self.assertIsNot(first, second)
                self.assertIn(first, self.service._owned_futures)
                self.assertIn(second, self.service._owned_futures)
                with self.assertRaisesRegex(TimeoutError, "^optimization_close_timeout$"):
                    self.service.close(timeout=0)
            finally:
                release.set()
                self.service.close(timeout=2)
            self.assertTrue(first.done())
            self.assertTrue(second.done())
            self.assertEqual(run.call_count, 1)
        records = self.service.get("operator", experiment["id"])["versions"][0]["evaluations"]
        self.assertEqual([record["status"] for record in records], ["completed", "cancelled"])
        directory = self.service.directory("operator", experiment["id"]) / "evaluations"
        self.assertEqual([json.loads((directory / f"{record['id']}.json").read_text())["status"]
                          for record in records], ["completed", "cancelled"])

    def test_close_signals_and_settles_final_verification(self):
        experiment = self._completed_final_fixture()
        entered, release = Event(), Event()
        observed = []
        original_run = self.service.evaluator.run

        def run(candidate, tools, cases, cancelled, progress, **kwargs):
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            observed.append(cancelled())
            return original_run(candidate, tools, cases, cancelled, progress, **kwargs)

        with patch.object(self.service.evaluator, "run", side_effect=run):
            self.service.verify_final("operator", experiment["id"])
            try:
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaisesRegex(TimeoutError, "^optimization_close_timeout$"):
                    self.service.close(timeout=0)
            finally:
                release.set()
                self.service.close(timeout=2)
        self.assertEqual(observed, [True])
        saved = self.service.get("operator", experiment["id"])
        self.assertEqual(saved["status"], "completed")
        record = saved["final_verification"]
        self.assertEqual(record["status"], "cancelled")
        self.assertEqual(record["error"], "measurement_cancelled")
        self.assertEqual(record["failure"]["category"], "interrupted")
        path = self.service.directory("operator", experiment["id"]) / "final-evaluations" / f"{record['id']}.json"
        self.assertEqual(json.loads(path.read_text()), record)

    def test_close_has_finite_timeout_and_reports_lock_contention(self):
        for timeout in (-1, float("inf"), float("nan"), None, "1", True):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, "^invalid_close_timeout$"):
                self.service.close(timeout=timeout)
        entered, release = Event(), Event()

        def hold_lock():
            with self.service.lock:
                entered.set()
                release.wait(timeout=5)

        holder = Thread(target=hold_lock)
        holder.start()
        try:
            self.assertTrue(entered.wait(timeout=5))
            started = monotonic()
            with self.assertRaisesRegex(TimeoutError, "^optimization_close_lock_timeout$"):
                self.service.close(timeout=0.05)
            self.assertLess(monotonic() - started, 1)
        finally:
            release.set()
            holder.join(timeout=5)
        self.assertFalse(holder.is_alive())
        self.assertIsNone(self.service.close(timeout=1))

    def test_case_workers_share_atomic_budget_with_fresh_contexts(self):
        dataset = FakeDataset()
        cases = [{**dataset.cases()[0], "case_id": str(index)} for index in range(4)]
        marker = ContextVar("optimizer_case_test", default="host")
        for workers in (1, 2):
            for allowance in (0, 2):
                with self.subTest(workers=workers, allowance=allowance):
                    context = ExecutionContext.create(CallerContext("operator"), limits={"model_calls": allowance})
                    observed = []
                    barrier = Barrier(workers)

                    def predict(prompt, evidence, model):
                        observed.append((current_execution(), marker.get()))
                        if workers > 1:
                            marker.set("case")
                            barrier.wait(timeout=5)
                        reserve("model_calls")
                        return {"grade": "accept", "rationale": "fixture"}

                    evaluator = GradeEvaluator(dataset, predict, NEUTRAL_PROFILE)
                    with context.activate():
                        results, metrics = evaluator.run({"system_prompt": "fixture", "model": "fixture"}, [], cases,
                                                         lambda: False, lambda result: None, workers=workers)
                    self.assertTrue(all(active is context and value == "host" for active, value in observed))
                    self.assertEqual(len(observed), 4)
                    self.assertEqual(context.budget.snapshot()["reserved"], {"model_calls": allowance})
                    self.assertEqual(sum(result["predicted"] == "accept" for result in results), allowance)
                    self.assertEqual(sum(result["error"] == "prediction_failed" for result in results), 4 - allowance)
                    self.assertEqual(metrics["case_count"], 4)
                    self.assertIsNone(current_execution())

    def test_service_dispatch_preserves_nested_shared_execution_context(self):
        for operation in ("evaluate", "measure", "verify_final"):
            for allowance in (0, 2):
                with self.subTest(operation=operation, allowance=allowance):
                    experiment = self._completed_final_fixture() if operation == "verify_final" else None
                    context = ExecutionContext.create(CallerContext("operator"), limits={"model_calls": allowance})
                    service_contexts, case_contexts, predictions = [], [], []
                    original_run = self.service.evaluator.run

                    def run(*args, **kwargs):
                        service_contexts.append(current_execution())
                        return original_run(*args, **kwargs)

                    def predict(prompt, evidence, model):
                        case_contexts.append(current_execution())
                        reserve("model_calls")
                        predictions.append("accept")
                        return {"grade": "accept", "rationale": "fixture"}

                    protocol = "full-10" if operation == "measure" else "smoke"
                    with (patch.object(self.service.evaluator, "run", side_effect=run),
                          patch.object(self.service.evaluator, "predict", side_effect=predict),
                          patch.dict(PROTOCOLS, {protocol: {**PROTOCOLS[protocol], "workers": 2}})):
                        with context.activate():
                            if operation == "verify_final":
                                self.service.verify_final("operator", experiment["id"])
                            else:
                                experiment = self.service.create("operator", "Shared context fixture", protocol)
                        self.service.futures[experiment["id"]].result(timeout=10)
                        self.service.futures[experiment["id"]].result(timeout=10)
                    self.assertTrue(service_contexts)
                    self.assertTrue(all(active is context for active in [*service_contexts, *case_contexts]))
                    self.assertEqual(len(case_contexts), 3)
                    self.assertEqual(len(predictions), allowance)
                    self.assertEqual(context.budget.snapshot()["reserved"], {"model_calls": allowance})
                    self.assertIsNone(current_execution())
                    saved = self.service.get("operator", experiment["id"])
                    runs = ([saved["final_verification"]] if operation == "verify_final" else
                            [*saved["versions"][0]["training_runs"], *saved["versions"][0]["evaluations"]])
                    self.assertTrue(all(record["status"] == "completed" for record in runs))
                    self.assertEqual(sum(record["metrics"]["case_count"] for record in runs), 3)
                    self.assertAlmostEqual(sum(record["metrics"]["case_count"] * record["metrics"]["error_rate"]
                                               for record in runs), 3 - allowance)

    def test_service_queue_does_not_renew_shared_deadline(self):
        entered, release = Event(), Event()
        observed = []
        original_run = self.service.evaluator.run

        def run(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return original_run(*args, **kwargs)

        def predict(prompt, evidence, model):
            observed.append(current_execution())
            reserve("model_calls")
            return {"grade": "accept", "rationale": "fixture"}

        with (patch("agentcraft_core.time.monotonic", return_value=100) as clock,
              patch.object(self.service.evaluator, "run", side_effect=run),
              patch.object(self.service.evaluator, "predict", side_effect=predict),
              patch.dict(PROTOCOLS, {"smoke": {**PROTOCOLS["smoke"], "workers": 2}})):
            context = ExecutionContext.create(CallerContext("operator"), limits={"model_calls": 3}, timeout_seconds=1)
            with context.activate():
                experiment = self.service.create("operator", "Expired queued context")
            try:
                self.assertTrue(entered.wait(timeout=5))
                clock.return_value = 102
            finally:
                release.set()
                self.service.futures[experiment["id"]].result(timeout=5)
        self.assertEqual(context.deadline, 101)
        self.assertEqual(context.budget.snapshot()["reserved"], {"model_calls": 0})
        self.assertEqual(len(observed), 3)
        self.assertTrue(all(active is context for active in observed))
        record = self.service.get("operator", experiment["id"])["versions"][0]["evaluations"][-1]
        self.assertEqual(record["metrics"]["error_rate"], 1)
        self.assertTrue(all(case["error"] == "prediction_failed" and case["predicted"] is None for case in record["cases"]))

    def test_the_host_scorer_labels_are_the_only_classes_counted(self):
        cases = [{"expected": "accept", "predicted": "accept", "correct": True, "elapsed_ms": 1},
                 {"expected": "reject", "predicted": "accept", "correct": False, "elapsed_ms": 3}]
        metrics = score(cases, 4, LABELS)
        self.assertEqual(sorted(metrics["per_class"]), sorted(LABELS))
        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(sorted(metrics["confusion_matrix"]["accept"]), sorted((*LABELS, "Error")))

    def test_a_tool_without_a_run_entry_point_is_refused(self):
        with self.assertRaises(ValueError):
            PythonToolRunner.validate("x = 1\n")

    def test_missing_bubblewrap_refuses_without_a_sandbox_fallback(self):
        runner = PythonToolRunner(str(self.root / "missing-bubblewrap"))
        with self.assertRaisesRegex(ValueError, "Bubblewrap"):
            runner.run(TOOL_CODE, self.root / "absent.sqlite")


if __name__ == "__main__":
    unittest.main()
