"""Authored offline safeguards, not observed historical production failures."""
from copy import deepcopy
from datetime import date
import builtins
import hashlib
import io
from contextlib import redirect_stdout
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from regression import (
    EvidenceError, canonical_hash, case_result, compare, drift, main, promote, provenance_hash, sample_synthetic,
    run_candidate,
)
from settings import CRITERIA, ROLES, PROJECT
from scenarios import SCENARIOS


def evidence(count_per_journey=5):
    pins = {r: {"name": "cs-sim-" + r.replace("_", "-"), "version": "1",
                "definition_sha256": canonical_hash({"test_definition": r})} for r in ROLES}
    provenance = {
        "source_revision": "test-gold", "project_endpoint": PROJECT,
        "model_id": "gpt-4.1-mini", "model_version": "test-fixed-version", "model_sku": "Standard",
        "agent_pins": pins, "config_sha256": canonical_hash({"test_config": True}),
        "judge_model": {"project_endpoint": PROJECT, "model_id": "gpt-4.1-mini",
                        "model_version": "test-fixed-judge-version", "model_sku": "Standard"},
    }
    calibration = {
        "calibration_status": "established_on_supplied_labels", "sample_count": 50,
        "insufficient_sample": False, "kappa": {c: .8 for c in CRITERIA},
        "labels_sha256": canonical_hash({"test_labels_only": True}),
        "judge_pins_sha256": canonical_hash({r: p for r, p in pins.items() if r.startswith("judge_")}),
        "judge_model_sha256": canonical_hash(provenance["judge_model"]),
    }
    def stage(count, historical=False):
        manifest, results = [], []
        for scenario in SCENARIOS.values():
            for i in range(count):
                case = {"case_id": scenario.id + "-" + str(i),
                        "case_sha256": canonical_hash({"fixture": scenario.id, "variant": i}),
                        "scenario_id": scenario.id, "journey_type": scenario.category}
                if historical:
                    case["origin"] = "authored_safeguard"
                manifest.append(case)
                results.append({k: case[k] for k in ("case_id", "case_sha256", "scenario_id", "journey_type")} | {
                    "provenance_sha256": provenance_hash(provenance), "status": "completed",
                    "raw_result_sha256": canonical_hash({"authored_test_raw_result": case["case_id"]}),
                    "task_completed": True, "criteria": [True, True, True], "goal_index": 10, "coherence": 9,
                })
        return {"manifest": manifest, "manifest_sha256": canonical_hash(manifest), "results": results}
    gold = {"schema_version": 1, "synthetic": True, "frozen": True, "dataset_id": "test-frozen-dataset",
            "dataset_sha256": canonical_hash({"test_dataset": True}), "provenance": provenance,
            "calibration": calibration, "stages": {
                "canary": stage(1), "full": stage(count_per_journey), "historical": stage(1, True)}}
    candidate = deepcopy(gold)
    candidate["frozen"] = False
    candidate["provenance"]["source_revision"] = "test-candidate"
    bind_results(candidate)
    return gold, candidate


def bind_results(bundle):
    for stage in bundle["stages"].values():
        for row in stage["results"]:
            row["provenance_sha256"] = provenance_hash(bundle["provenance"])


def rebuild_manifest(stage):
    stage["manifest_sha256"] = canonical_hash(stage["manifest"])


class RegressionTests(unittest.TestCase):
    def test_business_prompts_versions_and_target_model_version_may_change(self):
        gold, candidate = evidence()
        candidate["provenance"]["model_version"] = "test-new-target-serving-version"
        for role in ("triage", "policy", "resolution"):
            candidate["provenance"]["agent_pins"][role].update(
                version="2", definition_sha256=canonical_hash({"new_test_prompt": role}))
        bind_results(candidate)
        report = compare(gold, candidate)
        self.assertTrue(report["passed"], report)
        self.assertNotEqual(report["gold_provenance_sha256"], report["candidate_provenance_sha256"])
        self.assertEqual(set(report["allowed_target_changes"]), {
            "source_revision", "model_version", "agent_pins.triage", "agent_pins.policy", "agent_pins.resolution"})
        candidate["stages"]["canary"]["results"][0]["provenance_sha256"] = provenance_hash(gold["provenance"])
        self.assertIn("result_pin_or_config_mismatch", compare(gold, candidate)["blocked"])

    def test_changed_judge_or_judge_model_blocked_even_with_rebound_valid_calibration(self):
        for change in ("judge_pin", "judge_model"):
            with self.subTest(change=change):
                gold, candidate = evidence()
                if change == "judge_pin":
                    candidate["provenance"]["agent_pins"]["judge_tone"]["version"] = "2"
                    candidate["calibration"]["judge_pins_sha256"] = canonical_hash({
                        r: p for r, p in candidate["provenance"]["agent_pins"].items() if r.startswith("judge_")})
                else:
                    candidate["provenance"]["judge_model"]["model_version"] = "test-other-judge-version"
                    candidate["calibration"]["judge_model_sha256"] = canonical_hash(candidate["provenance"]["judge_model"])
                bind_results(candidate)
                self.assertIn("frozen_judge_or_config_mismatch", compare(gold, candidate)["blocked"])

    def test_cli_promotion_exclusive_output_never_overwrites_existing_gold(self):
        root = Path(__file__).parent / "evaluation-artifacts"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            directory = Path(directory)
            gold, candidate = evidence()
            approval = {"approved": True, "approver": "test-only-human",
                        "candidate_sha256": canonical_hash(candidate),
                        "comparison_sha256": canonical_hash(compare(gold, candidate))}
            for name, data in (("gold", gold), ("candidate", candidate), ("approval", approval)):
                (directory / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
            old_bytes = (directory / "gold.json").read_bytes()
            argv = ["regression.py", "promote", "--gold", str(directory / "gold.json"),
                    "--candidate", str(directory / "candidate.json"), "--approval", str(directory / "approval.json")]
            with redirect_stdout(io.StringIO()), patch("sys.argv", argv + ["--output", str(directory / "new-gold.json")]):
                self.assertEqual(main(), 0)
                new_bytes = (directory / "new-gold.json").read_bytes()
                self.assertEqual(main(), 1)
                self.assertEqual((directory / "new-gold.json").read_bytes(), new_bytes)
            with redirect_stdout(io.StringIO()), patch("sys.argv", argv + ["--output", str(directory / "gold.json")]):
                self.assertEqual(main(), 1)
            self.assertEqual((directory / "gold.json").read_bytes(), old_bytes)

    def test_cli_invalid_json_nan_or_duplicate_key_fails_before_comparison(self):
        from regression import load_json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            for text in ('{"score":NaN}', '{"synthetic":false,"synthetic":true}'):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(EvidenceError):
                    load_json(path)

    def test_existing_native_readback_adapter_no_second_runner(self):
        gold, _ = evidence()
        case = gold["stages"]["canary"]["manifest"][0]
        p = gold["provenance"]
        run = {
            "id": "synthetic-run", "scenario_id": case["scenario_id"], "status": "completed",
            "agent_pins": {r: {"name": v["name"], "version": v["version"]} for r, v in p["agent_pins"].items()},
            "goal_index": 10,
            "judge": {"criteria": [True, True, True], "coherence": 9,
                      "specialized": {c: {"score": 9} for c in CRITERIA}},
            "ledger": {"action": SCENARIOS[case["scenario_id"]].action, "state": "recorded",
                       "simulation": True, "real_transaction": False, "amount_sgd": None},
        }
        result = case_result(case, run, p)
        self.assertTrue(result["task_completed"])
        self.assertEqual(result["raw_result_sha256"], canonical_hash(run))
        with self.assertRaises(EvidenceError):
            case_result(case, run | {"agent_pins": {}}, p)
        run["ledger"]["action"] = "refund_recorded"
        with self.assertRaises(EvidenceError):
            case_result(case, run, p)
        run.update(status="failed", judge=None, goal_index=None)
        failed = case_result(case, run, p)
        self.assertFalse(failed["task_completed"])
        self.assertIsNone(failed["goal_index"])

    def test_identical_metrics_pass_all_stages_not_automatic_promotion(self):
        gold, candidate = evidence()
        result = compare(gold, candidate)
        self.assertTrue(result["passed"])
        self.assertEqual([s["stage"] for s in result["stages"]], ["canary", "full", "historical"])
        self.assertFalse(result["production_promotion_allowed"])
        self.assertTrue(result["demo_build_allowed"])

    def test_absolute_two_percentage_points_not_relative_percent(self):
        gold, candidate = evidence(25)  # 100 cases, 25 per journey.
        g, c = gold["stages"]["full"]["results"], candidate["stages"]["full"]["results"]
        # Gold 50%, candidate 48%: absolute drop .02 passes despite relative drop .04.
        for i in range(50):
            g[i]["task_completed"] = c[i]["task_completed"] = False
            g[i].update(criteria=[False, True, True], goal_index=7)
            c[i].update(criteria=[False, True, True], goal_index=7)
        for i in (60, 85):
            c[i].update(task_completed=False, criteria=[False, True, True], goal_index=7)
        result = compare(gold, candidate)
        self.assertTrue(result["passed"], result)
        full = result["stages"][1]
        self.assertEqual(full["drops"]["completion"], .02)
        c[61].update(task_completed=False, criteria=[False, True, True], goal_index=7)
        result = compare(gold, candidate)
        self.assertFalse(result["passed"])
        self.assertIn("completion_regression_or_unknown", result["stages"][1]["reasons"])

    def test_score_thresholds_inclusive_no_binary_float_false_fail(self):
        gold, candidate = evidence(25)
        for bundle in (gold, candidate):
            for stage in bundle["stages"].values():
                for row in stage["results"]:
                    row.update(task_completed=False, criteria=[True, True, False], goal_index=7)
        for stage in candidate["stages"].values():
            for row in stage["results"]:
                row["coherence"] = 8.5
        for row in candidate["stages"]["full"]["results"][:10]:
            row.update(criteria=[False, True, False], goal_index=4)
        self.assertTrue(compare(gold, candidate)["passed"])
        candidate["stages"]["full"]["results"][10].update(criteria=[False, True, False], goal_index=4)
        self.assertFalse(compare(gold, candidate)["passed"])

    def test_journey_five_percentage_point_boundary(self):
        gold, candidate = evidence(20)
        candidate["stages"]["full"]["results"][0].update(task_completed=False, criteria=[False, True, True], goal_index=7)
        self.assertTrue(compare(gold, candidate)["passed"])  # 1/20=.05; overall 1/80=.0125.
        candidate["stages"]["full"]["results"][1].update(task_completed=False, criteria=[False, True, True], goal_index=7)
        result = compare(gold, candidate)
        self.assertFalse(result["passed"])
        self.assertIn("journey_completion_regression:return", result["stages"][1]["reasons"])

    def test_missing_extra_duplicate_cases_fail_closed(self):
        for mutation in ("missing", "extra", "duplicate"):
            with self.subTest(mutation=mutation):
                gold, candidate = evidence()
                rows = candidate["stages"]["canary"]["results"]
                if mutation == "missing":
                    rows.pop()
                elif mutation == "extra":
                    rows.append(deepcopy(rows[0]) | {"case_id": "extra"})
                else:
                    rows[-1] = deepcopy(rows[0])
                self.assertFalse(compare(gold, candidate)["passed"])

    def test_missing_category_even_if_both_bundles_match(self):
        gold, candidate = evidence()
        for bundle in (gold, candidate):
            stage = bundle["stages"]["full"]
            stage["manifest"] = [m for m in stage["manifest"] if m["journey_type"] != "shipping"]
            stage["results"] = [m for m in stage["results"] if m["journey_type"] != "shipping"]
            rebuild_manifest(stage)
        self.assertIn("missing_journey_category", compare(gold, candidate)["blocked"])

    def test_failed_call_never_disappears_or_passes(self):
        gold, candidate = evidence()
        row = candidate["stages"]["canary"]["results"][0]
        row.update(status="failed", task_completed=False, criteria=None, goal_index=None, coherence=None)
        result = compare(gold, candidate)
        self.assertFalse(result["passed"])
        self.assertEqual(result["stages"][0]["candidate"]["attempts"], 4)
        self.assertEqual(result["stages"][0]["candidate"]["errors"], 1)
        self.assertIn("failed_calls_present", result["stages"][0]["reasons"])
        self.assertEqual(len(result["stages"]), 1)

    def test_nonfinite_unknown_scores_and_status_refused(self):
        for value in (float("nan"), float("inf"), None, "9", True):
            with self.subTest(value=str(value)):
                gold, candidate = evidence()
                candidate["stages"]["canary"]["results"][0]["goal_index"] = value
                self.assertFalse(compare(gold, candidate)["passed"])
        gold, candidate = evidence()
        candidate["stages"]["canary"]["results"][0]["status"] = "unknown"
        self.assertFalse(compare(gold, candidate)["passed"])

    def test_dataset_case_hash_disallowed_model_config_and_result_pin_mismatch(self):
        for target in ("dataset", "case", "model_id", "model_sku", "config", "result"):
            with self.subTest(target=target):
                gold, candidate = evidence()
                if target == "dataset":
                    candidate["dataset_sha256"] = "b" * 64
                elif target == "case":
                    candidate["stages"]["canary"]["results"][0]["case_sha256"] = "b" * 64
                elif target == "model_id":
                    candidate["provenance"]["model_id"] = "other"
                elif target == "model_sku":
                    candidate["provenance"]["model_sku"] = "GlobalStandard"
                elif target == "config":
                    candidate["provenance"]["config_sha256"] = "b" * 64
                else:
                    candidate["stages"]["canary"]["results"][0]["provenance_sha256"] = "b" * 64
                self.assertFalse(compare(gold, candidate)["passed"])

    def test_missing_uncalibrated_or_sample_mismatched_baseline(self):
        for field, value in (("calibration_status", "calibration_not_established"),
                             ("sample_count", 49), ("sample_count", 51),
                             ("labels_sha256", None), ("judge_pins_sha256", "b" * 64)):
            with self.subTest(field=field, value=value):
                gold, candidate = evidence()
                gold["calibration"][field] = value
                report = compare(gold, candidate)
                self.assertFalse(report["passed"])
                self.assertTrue(report["demo_build_allowed"])
                self.assertEqual(report["stages"], [])
        gold, candidate = evidence()
        del gold["calibration"]
        self.assertFalse(compare(gold, candidate)["passed"])

    def test_canary_failure_prevents_full_historical_inspection(self):
        gold, candidate = evidence()
        candidate["stages"]["canary"]["results"][0].update(
            task_completed=False, criteria=[False, False, False], goal_index=0)
        candidate["stages"]["full"] = {"deliberately": "malformed later stage"}
        candidate["stages"]["historical"] = None
        report = compare(gold, candidate)
        self.assertEqual(report["blocked"], ["stage_failed:canary"])
        self.assertEqual(len(report["stages"]), 1)

    def test_canary_only_receipt_does_not_claim_full_or_historical(self):
        gold, candidate = evidence()
        del candidate["stages"]["full"]
        del candidate["stages"]["historical"]
        report = compare(gold, candidate, "canary")
        self.assertTrue(report["passed"])
        self.assertEqual(report["next_stage"], "full")
        self.assertFalse(report["production_promotion_allowed"])

    def test_historical_observed_bug_requires_evidence_not_invented(self):
        gold, candidate = evidence()
        for bundle in (gold, candidate):
            stage = bundle["stages"]["historical"]
            stage["manifest"][0]["origin"] = "observed_bug"
            rebuild_manifest(stage)
        self.assertIn("observed_bug_evidence_required", compare(gold, candidate)["blocked"])
        for bundle in (gold, candidate):
            stage = bundle["stages"]["historical"]
            stage["manifest"][0].update(evidence_ref="test-only-issue", evidence_sha256="a" * 64)
            rebuild_manifest(stage)
        self.assertTrue(compare(gold, candidate)["passed"])

    def test_explicit_promotion_requires_approval_bound_to_exact_evidence(self):
        gold, candidate = evidence()
        before = deepcopy(gold)
        report = compare(gold, candidate)
        approval = {"approved": True, "approver": "test-human-only",
                    "candidate_sha256": canonical_hash(candidate), "comparison_sha256": canonical_hash(report)}
        promoted = promote(gold, candidate, approval)
        self.assertTrue(promoted["frozen"])
        self.assertEqual(gold, before)
        self.assertEqual(promoted["promotion"]["previous_gold_sha256"], canonical_hash(gold))
        with self.assertRaises(EvidenceError):
            promote(gold, candidate, approval | {"approved": False})
        with self.assertRaises(EvidenceError):
            promote(gold, candidate, approval | {"candidate_sha256": "b" * 64})
        with self.assertRaises(EvidenceError):
            promote(gold, candidate, approval | {"comparison_sha256": "b" * 64})

    def test_gold_must_be_frozen(self):
        gold, candidate = evidence()
        gold["frozen"] = False
        self.assertIn("gold_not_frozen", compare(gold, candidate)["blocked"])


class DriftTests(unittest.TestCase):
    def test_drift_cli_exit_refuses_insufficient_or_threshold_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            for variant, expected in (("stable", 0), ("drift", 1), ("insufficient", 1)):
                rows = self.snapshots()
                if variant == "drift":
                    for row in rows:
                        if row["date"] >= "2026-10-11":
                            row["task_completed"] = 0
                elif variant == "insufficient":
                    rows = [r for r in rows if r["date"] >= "2026-10-11"]
                path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
                with self.subTest(variant=variant), redirect_stdout(io.StringIO()), patch("sys.argv", [
                    "regression.py", "drift", "--snapshots", str(path), "--as-of", "2026-10-17",
                ]):
                    self.assertEqual(main(), expected)

    def snapshots(self):
        return [{"date": day, "synthetic": True, "journey_type": j, "attempts": n,
                 "task_completed": n, "errors": 0, "scored": n, "goal_sum": n * score,
                 "coherence_sum": n * score}
                for day, n, score in (("2026-10-04", 10, 9), ("2026-10-11", 1, 1),
                                      ("2026-10-17", 9, 10)) for j in ("return", "billing", "shipping", "exception")]

    def test_seven_day_rolling_weighted_by_attempts_not_daily_means(self):
        report = drift(self.snapshots(), "2026-10-17")
        self.assertEqual(report["recent"]["start"], "2026-10-11")
        self.assertEqual(report["recent"]["end"], "2026-10-17")
        self.assertEqual(report["recent"]["system"]["attempts"], 40)
        self.assertEqual(report["recent"]["system"]["goal"], 9.1)  # (1*1+9*10)/10, not 5.5.
        self.assertEqual(report["status"], "no_threshold_drift")

    def test_outside_window_ignored_unknowns_not_imputed_zero(self):
        rows = self.snapshots()
        rows.append({"date": "2026-09-01", "synthetic": True, "journey_type": "return", "attempts": 100,
                     "task_completed": 100, "errors": 0, "scored": 100, "goal_sum": 1000, "coherence_sum": 1000})
        rows[-2].update(task_completed=8, errors=1, scored=8, goal_sum=80, coherence_sum=80)
        report = drift(rows, "2026-10-17")
        self.assertEqual(report["recent"]["system"]["attempts"], 40)
        self.assertIsNone(report["recent"]["system"]["goal"])
        self.assertEqual(report["recent"]["system"]["errors"], 1)
        self.assertEqual(report["status"], "insufficient_data")

    def test_non_synthetic_transcript_unknown_journey_duplicate_denied(self):
        variants = [
            self.snapshots() + [self.snapshots()[0]],
            [self.snapshots()[0] | {"synthetic": False}],
            [self.snapshots()[0] | {"transcript": "not accepted"}],
            [self.snapshots()[0] | {"journey_type": "unknown"}],
        ]
        for rows in variants:
            with self.subTest(rows=len(rows)), self.assertRaises(EvidenceError):
                drift(rows, "2026-10-17")

    def test_sampling_deterministic_exact_hash_rule_synthetic_only(self):
        import hashlib
        selected = []
        for i in range(1000):
            run_id = "synthetic-run-" + str(i)
            actual = sample_synthetic(run_id, synthetic=True)
            self.assertEqual(actual, int(hashlib.sha256(run_id.encode()).hexdigest(), 16) % 10000 < 100)
            selected.append(actual)
        self.assertGreater(sum(selected), 0)
        self.assertEqual(sample_synthetic("synthetic-run-1", synthetic=True),
                         sample_synthetic("synthetic-run-1", synthetic=True))
        with self.assertRaises(EvidenceError):
            sample_synthetic("synthetic-run-1", synthetic=False)


class RunPreflightTests(unittest.TestCase):
    """Only negative/offline cases. No SDK, credentials, model or cloud execution."""
    ENV = {"AZURE_CLIENT_ID": "11111111-1111-1111-1111-111111111111",
           "AGENT_TRIAGE_VERSION": "1", "AGENT_POLICY_VERSION": "1", "AGENT_RESOLUTION_VERSION": "1",
           "GITHUB_SHA": "authored-test-revision"}

    def inputs(self, directory):
        directory = Path(directory)
        gold, _ = evidence()
        rows = [{"case_id": c["case_id"], "fixture_id": c["scenario_id"],
                 "customer_request": SCENARIOS[c["scenario_id"]].request, "synthetic": True}
                for c in gold["stages"]["full"]["manifest"]]
        config = {"profile": "customer-service-native-v1", "consensus": False}
        gold["evaluation_config"] = config
        gold["provenance"]["config_sha256"] = canonical_hash(config)
        by_id = {r["case_id"]: r for r in rows}
        for stage in gold["stages"].values():
            for case in stage["manifest"]:
                case["case_sha256"] = canonical_hash(by_id[case["case_id"]])
            for row in stage["results"]:
                row["case_sha256"] = canonical_hash(by_id[row["case_id"]])
            rebuild_manifest(stage)
        bind_results(gold)
        dataset = directory / "synthetic.jsonl"
        dataset.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        gold["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
        path = directory / "gold.json"
        path.write_text(json.dumps(gold), encoding="utf-8")
        return path, dataset, gold, rows

    def refuse_sdk(self, touched):
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name in ("azure.ai.evaluation", "native", "evaluate_cli"):
                touched.append(name)
                raise ImportError("Intentional offline SDK guard")
            return original(name, *args, **kwargs)
        return guarded

    def test_missing_gold_and_authorization_block_before_sdk_import(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.json"
            touched = []
            with patch("builtins.__import__", side_effect=self.refuse_sdk(touched)):
                report = run_candidate(missing, missing, allow_model_calls=True)
                self.assertEqual(report["blocked"], ["calibrated_gold_file_required"])
                report = run_candidate(missing, missing)
                self.assertEqual(report["blocked"], ["explicit_model_call_authorization_required"])
            self.assertEqual(touched, [])
            self.assertFalse(report["passed"])

    def test_uncalibrated_gold_and_missing_cohort_block_before_sdk_import(self):
        for variant in ("uncalibrated", "missing_case", "case_hash", "conflicting_fixture"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                path, dataset, gold, rows = self.inputs(directory)
                if variant == "uncalibrated":
                    gold["calibration"]["calibration_status"] = "calibration_not_established"
                elif variant == "missing_case":
                    rows.pop()
                elif variant == "case_hash":
                    rows[0]["customer_request"] = "Changed synthetic request, not approved frozen case."
                else:
                    rows[0]["scenario_id"] = "duplicate-charge"
                dataset.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
                gold["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
                path.write_text(json.dumps(gold), encoding="utf-8")
                touched = []
                with patch("builtins.__import__", side_effect=self.refuse_sdk(touched)):
                    report = run_candidate(path, dataset, allow_model_calls=True)
                self.assertFalse(report["passed"])
                self.assertTrue(report["blocked"])
                self.assertEqual(touched, [])
                self.assertEqual(report["stage_execution"], [])

    def test_profile_hash_budget_and_frozen_judge_settings_fail_before_sdk(self):
        for variant in ("config_missing", "config_hash", "budget", "judge_version", "business_version"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                path, dataset, gold, _ = self.inputs(directory)
                env, budget = dict(self.ENV), 200
                if variant == "config_missing":
                    del gold["evaluation_config"]
                elif variant == "config_hash":
                    gold["evaluation_config"]["consensus"] = True
                elif variant == "budget":
                    budget = 10
                elif variant == "judge_version":
                    env["AGENT_JUDGE_TONE_VERSION"] = "2"
                else:
                    del env["AGENT_POLICY_VERSION"]
                path.write_text(json.dumps(gold), encoding="utf-8")
                touched = []
                with patch.dict("os.environ", env, clear=True), patch(
                    "builtins.__import__", side_effect=self.refuse_sdk(touched)
                ):
                    report = run_candidate(path, dataset, allow_model_calls=True, max_model_calls=budget)
                self.assertFalse(report["passed"])
                self.assertEqual(touched, [])
                self.assertEqual(report["stage_execution"], [])

    def test_valid_offline_preflight_missing_sdk_explicitly_blocked_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path, dataset, _, _ = self.inputs(directory)
            touched = []
            with patch.dict("os.environ", self.ENV, clear=True), patch(
                "builtins.__import__", side_effect=self.refuse_sdk(touched)
            ):
                report = run_candidate(path, dataset, allow_model_calls=True)
            self.assertEqual(report["blocked"], ["azure_ai_evaluation_not_installed"])
            self.assertEqual(touched, ["azure.ai.evaluation"])
            self.assertEqual(report["planned_max_model_calls"], 196)
            self.assertFalse(report["passed"])
            self.assertIsNone(report["candidate"])

    def test_cli_writes_blocked_state_and_invalid_output_cannot_start_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path, dataset, _, _ = self.inputs(directory)
            output = directory / "deploy" / ".state" / "regression-report.json"
            before = path.read_bytes()
            touched = []
            argv = ["regression.py", "run", "--gold", str(path), "--dataset", str(dataset),
                    "--allow-model-calls", "--output", str(output)]
            with patch.dict("os.environ", self.ENV, clear=True), patch(
                "builtins.__import__", side_effect=self.refuse_sdk(touched)
            ), patch("pathlib.Path.cwd", return_value=directory), patch("sys.argv", argv), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 1)
            report = json.loads(output.read_text())
            self.assertEqual(report["blocked"], ["azure_ai_evaluation_not_installed"])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(touched, ["azure.ai.evaluation"])
            touched.clear()
            with patch("builtins.__import__", side_effect=self.refuse_sdk(touched)), patch(
                "sys.argv", argv[:-1] + [str(path)]
            ), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 1)
            self.assertEqual(touched, [])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
