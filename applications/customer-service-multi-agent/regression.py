"""Offline regression gates plus explicitly authorized, bounded native-SDK orchestration."""
import argparse
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from types import SimpleNamespace
import uuid
from settings import CRITERIA, ROLES, PROJECT, MODEL
from scenarios import SCENARIOS

JOURNEYS = frozenset(s.category for s in SCENARIOS.values())
STAGES = ("canary", "full", "historical")
THRESHOLDS = {"completion_drop": Decimal(".02"), "goal_drop": Decimal(".3"),
              "coherence_drop": Decimal(".5"), "journey_completion_drop": Decimal(".05")}
HASH = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
MAX_CASES = 1000
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _require(condition, code):
    if not condition:
        raise EvidenceError(code)


def _hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def _number(value, low=0, high=10):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def _parse_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError("nonfinite_json")))


def load_json(path):
    _require(Path(path).stat().st_size <= MAX_EVIDENCE_BYTES, "evidence_file_too_large")
    return _parse_json(Path(path).read_text(encoding="utf-8"))


def provenance_hash(provenance):
    """Bind each result to its OWN complete model/prompt/config/source provenance."""
    return canonical_hash(provenance)


def frozen_evaluation_hash(provenance):
    return canonical_hash({
        "project_endpoint": provenance["project_endpoint"],
        "judge_model": provenance["judge_model"],
        "judge_pins": {r: p for r, p in provenance["agent_pins"].items() if r.startswith("judge_")},
        "config_sha256": provenance["config_sha256"],
    })


def _provenance(bundle):
    p = bundle["provenance"]
    required = {"source_revision", "project_endpoint", "model_id", "model_version", "model_sku",
                "agent_pins", "config_sha256", "judge_model"}
    _require(isinstance(p, dict) and set(p) == required, "incomplete_provenance")
    _require(all(isinstance(p[k], str) and p[k] and p[k].lower() not in (
        "unknown", "unavailable", "none", "null") for k in (
        "source_revision", "project_endpoint", "model_id", "model_version", "model_sku")),
        "unknown_model_or_source_provenance")
    _require(p["project_endpoint"] == PROJECT and p["model_id"] == MODEL and p["model_sku"] == "Standard",
             "unassigned_model_or_project")
    judge_model = p["judge_model"]
    _require(isinstance(judge_model, dict) and set(judge_model) == {
        "project_endpoint", "model_id", "model_version", "model_sku"}, "incomplete_judge_model")
    _require(judge_model["project_endpoint"] == PROJECT and judge_model["model_id"] == MODEL
             and judge_model["model_sku"] == "Standard"
             and isinstance(judge_model["model_version"], str) and judge_model["model_version"]
             and judge_model["model_version"].lower() not in ("unknown", "unavailable", "none", "null"),
             "unknown_or_unassigned_judge_model")
    _require(_hash(p["config_sha256"]), "unknown_config_hash")
    _require(isinstance(p["agent_pins"], dict) and set(p["agent_pins"]) == set(ROLES), "missing_or_extra_agent_pins")
    for role, pin in p["agent_pins"].items():
        _require(isinstance(pin, dict) and set(pin) == {"name", "version", "definition_sha256"}, "incomplete_agent_pin")
        _require(pin["name"] == "cs-sim-" + role.replace("_", "-") and isinstance(pin["version"], str)
                 and pin["version"].isdecimal() and int(pin["version"]) > 0
                 and _hash(pin["definition_sha256"]), "invalid_agent_pin")
    return p


def _calibration(bundle):
    c = bundle["calibration"]
    _require(isinstance(c, dict), "missing_calibration")
    _require(c.get("calibration_status") == "established_on_supplied_labels", "uncalibrated_evidence")
    _require(type(c.get("sample_count")) is int and 50 <= c["sample_count"] <= 100,
             "calibration_sample_mismatch")
    _require(c.get("insufficient_sample") is False and _hash(c.get("labels_sha256")),
             "missing_calibration_labels_provenance")
    _require(set(c.get("kappa", {})) == set(CRITERIA)
             and all(_number(k, -1, 1) and k > .7 for k in c["kappa"].values()),
             "calibration_agreement_not_established")
    judges = {r: p for r, p in bundle["provenance"]["agent_pins"].items() if r.startswith("judge_")}
    _require(c.get("judge_pins_sha256") == canonical_hash(judges), "calibration_judge_pin_mismatch")
    _require(c.get("judge_model_sha256") == canonical_hash(bundle["provenance"]["judge_model"]),
             "calibration_judge_model_mismatch")


def _manifest(stage, name):
    _require(isinstance(stage, dict), "invalid_stage")
    manifest = stage["manifest"]
    _require(isinstance(manifest, list) and 1 <= len(manifest) <= MAX_CASES, "invalid_stage_manifest_size")
    _require(stage.get("manifest_sha256") == canonical_hash(manifest), "stage_manifest_hash_mismatch")
    indexed = {}
    for item in manifest:
        _require(isinstance(item, dict), "invalid_manifest_case")
        _require(_identifier(item.get("case_id")) and item["case_id"] not in indexed, "duplicate_or_invalid_case_id")
        _require(_hash(item.get("case_sha256")), "unknown_case_hash")
        _require(item.get("scenario_id") in SCENARIOS, "unknown_scenario")
        _require(item.get("journey_type") == SCENARIOS[item["scenario_id"]].category, "case_journey_mismatch")
        if name == "historical":
            origin = item.get("origin")
            _require(origin in ("authored_safeguard", "observed_bug"), "historical_origin_required")
            if origin == "observed_bug":
                _require(isinstance(item.get("evidence_ref"), str) and item["evidence_ref"]
                         and _hash(item.get("evidence_sha256")), "observed_bug_evidence_required")
        indexed[item["case_id"]] = item
    _require({i["journey_type"] for i in manifest} == JOURNEYS, "missing_journey_category")
    return indexed


def _results(stage, manifest, expected_provenance):
    rows = stage["results"]
    _require(isinstance(rows, list) and len(rows) == len(manifest), "case_sample_count_mismatch")
    seen = set()
    for row in rows:
        _require(isinstance(row, dict), "invalid_raw_case_result")
        case_id = row.get("case_id")
        _require(case_id in manifest and case_id not in seen, "missing_extra_or_duplicate_case")
        seen.add(case_id)
        case = manifest[case_id]
        _require(all(row.get(k) == case[k] for k in ("case_sha256", "scenario_id", "journey_type")),
                 "case_identity_or_hash_mismatch")
        _require(row.get("provenance_sha256") == expected_provenance, "result_pin_or_config_mismatch")
        _require(_hash(row.get("raw_result_sha256")), "raw_result_provenance_required")
        _require(row.get("status") in ("completed", "failed"), "unknown_case_status")
        _require(type(row.get("task_completed")) is bool, "unknown_completion_label")
        if row["status"] == "failed":
            _require(row["task_completed"] is False and row.get("goal_index") is None
                     and row.get("coherence") is None and row.get("criteria") is None, "failed_case_claims_success")
        else:
            _require(_number(row.get("goal_index")) and _number(row.get("coherence")),
                     "unknown_or_nonfinite_score")
            criteria = row.get("criteria")
            _require(isinstance(criteria, list) and len(criteria) == 3
                     and all(type(c) is bool for c in criteria), "missing_raw_binary_criteria")
            _require(row["task_completed"] == all(criteria)
                     and row["goal_index"] == sum(w for w, passed in zip((3, 4, 3), criteria) if passed),
                     "raw_criteria_completion_or_goal_mismatch")
    _require(seen == set(manifest), "case_set_mismatch")
    return rows


def case_result(case, run, provenance):
    """Adapt existing SimulationService readback, never invoke a second model runner."""
    _require(isinstance(case, dict) and isinstance(run, dict), "invalid_case_or_raw_result")
    _provenance({"provenance": provenance})
    _require(case.get("scenario_id") in SCENARIOS and run.get("scenario_id") == case["scenario_id"],
             "raw_result_scenario_mismatch")
    scenario = SCENARIOS[case["scenario_id"]]
    _require(case.get("journey_type") == scenario.category and _identifier(case.get("case_id"))
             and _hash(case.get("case_sha256")), "invalid_case_identity")
    expected_pins = {r: {"name": p["name"], "version": p["version"]} for r, p in provenance["agent_pins"].items()}
    _require(run.get("agent_pins") == expected_pins, "raw_result_agent_pin_mismatch")
    status = run.get("status")
    _require(status in ("completed", "failed"), "raw_result_not_terminal")
    task_completed, goal, coherence, criteria = False, None, None, None
    if status == "completed":
        judge, ledger = run["judge"], run["ledger"]
        criteria = judge["criteria"]
        _require(isinstance(criteria, list) and len(criteria) == 3
                 and all(type(c) is bool for c in criteria), "unknown_raw_criteria")
        _require(set(judge["specialized"]) == set(CRITERIA), "missing_specialized_judge")
        _require(ledger.get("action") == scenario.action and ledger.get("state") == "recorded"
                 and ledger.get("simulation") is True and ledger.get("real_transaction") is False
                 and ledger.get("amount_sgd") == (49 if scenario.id == "duplicate-charge" else None),
                 "raw_result_ledger_mismatch")
        task_completed = all(criteria)
        goal = sum(w for w, passed in zip((3, 4, 3), criteria) if passed)
        coherence = judge["coherence"]
        _require(run.get("goal_index") == goal and _number(coherence)
                 and coherence == judge["specialized"]["consistency"]["score"], "raw_result_score_mismatch")
    else:
        _require(run.get("goal_index") is None and run.get("judge") is None, "failed_raw_result_claims_scores")
    return {k: case[k] for k in ("case_id", "case_sha256", "scenario_id", "journey_type")} | {
        "run_id": run.get("id"), "raw_result_sha256": canonical_hash(run),
        "provenance_sha256": provenance_hash(provenance), "status": status,
        "task_completed": task_completed, "criteria": criteria, "goal_index": goal, "coherence": coherence,
    }


def _metrics(rows):
    n = len(rows)
    scored = [r for r in rows if r["status"] == "completed"]
    return {"attempts": n, "errors": n - len(scored), "scored": len(scored),
            "completion": Decimal(sum(r["task_completed"] for r in rows)) / n,
            "goal": sum((Decimal(str(r["goal_index"])) for r in scored), Decimal(0)) / len(scored) if scored else None,
            "coherence": sum((Decimal(str(r["coherence"])) for r in scored), Decimal(0)) / len(scored) if scored else None}


def _serial_metrics(values):
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in values.items()}


def compare_stage(gold_stage, candidate_stage, name, gold_provenance, candidate_provenance):
    gold_manifest = _manifest(gold_stage, name)
    candidate_manifest = _manifest(candidate_stage, name)
    _require(gold_manifest == candidate_manifest, "gold_candidate_manifest_mismatch")
    gold = _results(gold_stage, gold_manifest, gold_provenance)
    candidate = _results(candidate_stage, candidate_manifest, candidate_provenance)
    gm, cm = _metrics(gold), _metrics(candidate)
    reasons = []
    if gm["errors"] or cm["errors"]:
        reasons.append("failed_calls_present")
    drops = {}
    for key, threshold in (("completion", THRESHOLDS["completion_drop"]),
                           ("goal", THRESHOLDS["goal_drop"]),
                           ("coherence", THRESHOLDS["coherence_drop"])):
        value = gm[key] - cm[key] if gm[key] is not None and cm[key] is not None else None
        drops[key] = float(value) if value is not None else None
        if value is None or value > threshold:
            reasons.append(key + "_regression_or_unknown")
    journey = {}
    for category in sorted(JOURNEYS):
        g = _metrics([r for r in gold if r["journey_type"] == category])
        c = _metrics([r for r in candidate if r["journey_type"] == category])
        drop = g["completion"] - c["completion"]
        journey[category] = {"gold": _serial_metrics(g), "candidate": _serial_metrics(c),
                             "completion_drop": float(drop)}
        if drop > THRESHOLDS["journey_completion_drop"]:
            reasons.append("journey_completion_regression:" + category)
    return {"stage": name, "passed": not reasons, "reasons": reasons,
            "gold": _serial_metrics(gm), "candidate": _serial_metrics(cm),
            "drops": drops, "journeys": journey,
            "historical_origin_note": "Authored safeguards unless supplied observed-bug evidence reference/hash exists; not independently verified."}


def compare(gold, candidate, through="historical"):
    """Fail closed. Later stages are not inspected until preceding stage passes."""
    report = {"schema_version": 1, "passed": False, "production_promotion_allowed": False,
              "demo_build_allowed": True, "stages": [], "blocked": [],
              "thresholds": {k: float(v) for k, v in THRESHOLDS.items()},
              "threshold_units": "absolute percentage-point completion drops, absolute 0..10 score drops",
              "comparability_policy": {
                  "allowed_changes": ["source_revision", "target.model_version", "business_agent_versions_and_definitions"],
                  "target_model_id": MODEL, "target_model_sku": "Standard",
                  "frozen": ["dataset", "case_identities", "judge_pins", "judge_model", "calibration", "config_sha256"],
              }}
    try:
        _require(through in STAGES, "unknown_stage")
        for bundle in (gold, candidate):
            _require(isinstance(bundle, dict) and type(bundle.get("schema_version")) is int
                     and bundle["schema_version"] == 1 and bundle.get("synthetic") is True,
                     "synthetic_evidence_required")
            _require(_identifier(bundle.get("dataset_id")) and _hash(bundle.get("dataset_sha256")),
                     "unknown_dataset_identity")
            _provenance(bundle)
            _calibration(bundle)
        _require(gold.get("frozen") is True, "gold_not_frozen")
        _require(gold["dataset_id"] == candidate["dataset_id"]
                 and gold["dataset_sha256"] == candidate["dataset_sha256"], "dataset_mismatch")
        gp, cp = provenance_hash(gold["provenance"]), provenance_hash(candidate["provenance"])
        frozen = frozen_evaluation_hash(gold["provenance"])
        _require(frozen == frozen_evaluation_hash(candidate["provenance"]), "frozen_judge_or_config_mismatch")
        _require(canonical_hash(gold["calibration"]) == canonical_hash(candidate["calibration"]),
                 "frozen_calibration_or_sample_mismatch")
        changes = {}
        for field in ("source_revision", "model_version"):
            a, b = gold["provenance"][field], candidate["provenance"][field]
            if a != b:
                changes[field] = {"gold": a, "candidate": b}
        for role in ("triage", "policy", "resolution"):
            a = gold["provenance"]["agent_pins"][role]
            b = candidate["provenance"]["agent_pins"][role]
            if a != b:
                changes["agent_pins." + role] = {"gold": a, "candidate": b}
        report.update(gold_sha256=canonical_hash(gold), candidate_sha256=canonical_hash(candidate),
                      gold_provenance_sha256=gp, candidate_provenance_sha256=cp,
                      frozen_evaluation_sha256=frozen, allowed_target_changes=changes)
        for stage in STAGES[:STAGES.index(through) + 1]:
            result = compare_stage(gold["stages"][stage], candidate["stages"][stage], stage, gp, cp)
            if stage == "full":
                # Only inspected after canary passed; same canary cases must belong to full cohort.
                for bundle in (gold, candidate):
                    canary = {c["case_id"]: c for c in bundle["stages"]["canary"]["manifest"]}
                    full = {c["case_id"]: c for c in bundle["stages"]["full"]["manifest"]}
                    _require(all(full.get(key) == value for key, value in canary.items()),
                             "canary_not_subset_of_full")
            report["stages"].append(result)
            if not result["passed"]:
                report["blocked"] = ["stage_failed:" + stage]
                return report
        report["passed"] = True
        report["production_promotion_allowed"] = False  # Explicit human approval still required.
        report["completed_through"] = through
        report["next_stage"] = STAGES[STAGES.index(through) + 1] if through != "historical" else None
    except (EvidenceError, KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
        # Only controlled error codes are exposed; malformed evidence never passes.
        import sys
        exc = sys.exc_info()[1]
        report["blocked"] = [str(exc) if isinstance(exc, EvidenceError) else "malformed_evidence"]
    return report


def promote(gold, candidate, approval):
    """Return new frozen artifact. Caller must write a NEW exclusive path, never overwrite gold."""
    report = compare(gold, candidate)
    _require(report["passed"], "regression_gate_not_passed")
    _require(isinstance(approval, dict), "invalid_human_approval")
    _require(approval.get("approved") is True and _identifier(approval.get("approver")),
             "explicit_human_approval_required")
    _require(approval.get("candidate_sha256") == canonical_hash(candidate)
             and approval.get("comparison_sha256") == canonical_hash(report), "approval_evidence_mismatch")
    result = deepcopy(candidate)
    result["frozen"] = True
    result["promotion"] = {"previous_gold_sha256": canonical_hash(gold),
                           "human_approval_sha256": canonical_hash(approval),
                           "comparison_sha256": canonical_hash(report)}
    return result


def sample_synthetic(run_id, *, synthetic):
    """Deterministic 1% hash bucket assignment, not a promise every small cohort has 1%."""
    _require(synthetic is True and _identifier(run_id), "synthetic_run_id_required")
    return int(hashlib.sha256(run_id.encode()).hexdigest(), 16) % 10000 < 100


def drift(snapshots, as_of):
    """Two adjacent seven-day windows, weighted by raw attempt/score sums."""
    end = date.fromisoformat(as_of)
    seen = set()
    required = {"date", "synthetic", "journey_type", "attempts", "task_completed", "errors",
                "scored", "goal_sum", "coherence_sum"}
    _require(isinstance(snapshots, list) and len(snapshots) <= 10000, "snapshot_size_limit")
    for row in snapshots:
        _require(set(row) == required and row["synthetic"] is True, "synthetic_snapshot_schema_required")
        day = date.fromisoformat(row["date"])
        _require(row["journey_type"] in JOURNEYS, "unknown_snapshot_journey")
        key = (day, row["journey_type"])
        _require(key not in seen, "duplicate_day_journey_snapshot")
        seen.add(key)
        n = row["attempts"]
        _require(type(n) is int and 0 <= n <= 1000000000, "invalid_attempt_count")
        for field in ("task_completed", "errors", "scored"):
            _require(type(row[field]) is int and 0 <= row[field] <= n, "invalid_snapshot_count")
        _require(row["task_completed"] <= row["scored"] and row["scored"] + row["errors"] <= n,
                 "inconsistent_snapshot_denominators")
        _require(_number(row["goal_sum"], 0, 10 * row["scored"])
                 and _number(row["coherence_sum"], 0, 10 * row["scored"]), "invalid_snapshot_score_sum")

    def window(start, stop):
        selected = [r for r in snapshots if start <= date.fromisoformat(r["date"]) <= stop]
        def totals(rows):
            n = sum(r["attempts"] for r in rows)
            scored = sum(r["scored"] for r in rows)
            return {"attempts": n, "scored": scored, "errors": sum(r["errors"] for r in rows),
                    "completion": sum(r["task_completed"] for r in rows) / n if n else None,
                    # Never impute unknown scores as zero just to satisfy attempt weighting.
                    "goal": sum(r["goal_sum"] for r in rows) / n if n and scored == n else None,
                    "coherence": sum(r["coherence_sum"] for r in rows) / n if n and scored == n else None,
                    "unscored": n - scored}
        return {"start": start.isoformat(), "end": stop.isoformat(), "system": totals(selected),
                "journeys": {j: totals([r for r in selected if r["journey_type"] == j]) for j in sorted(JOURNEYS)}}
    recent = window(end - timedelta(days=6), end)
    prior = window(end - timedelta(days=13), end - timedelta(days=7))
    drops, alerts = {}, []
    for field, threshold in (("completion", .02), ("goal", .3), ("coherence", .5)):
        a, b = prior["system"][field], recent["system"][field]
        drops[field] = a - b if a is not None and b is not None else None
        if a is not None and b is not None and Decimal(str(a)) - Decimal(str(b)) > Decimal(str(threshold)):
            alerts.append(field + "_drift")
    sufficient = all(v is not None for v in drops.values())
    for j in JOURNEYS:
        a, b = prior["journeys"][j]["completion"], recent["journeys"][j]["completion"]
        if a is None or b is None:
            sufficient = False
        elif Decimal(str(a)) - Decimal(str(b)) > THRESHOLDS["journey_completion_drop"]:
            alerts.append("journey_completion_drift:" + j)
    return {"synthetic": True, "recent": recent, "prior": prior, "drops": drops,
            "status": "insufficient_data" if not sufficient else "drift_detected" if alerts else "no_threshold_drift",
            "alerts": sorted(alerts), "production_promotion_allowed": False,
            "scope": "Offline synthetic snapshots only; no production transcript ingestion or online sampling"}


def _run_dataset(gold, dataset_path):
    """Validate ALL cohorts before importing any cloud/evaluation SDK."""
    path = Path(dataset_path)
    _require(path.stat().st_size <= MAX_EVIDENCE_BYTES, "dataset_file_too_large")
    data = path.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == gold["dataset_sha256"], "dataset_artifact_hash_mismatch")
    rows = [_parse_json(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    _require(1 <= len(rows) <= 20, "run_dataset_requires_1_to_20_cases")
    indexed = {}
    for row in rows:
        _require(isinstance(row, dict) and _identifier(row.get("case_id"))
                 and row["case_id"] not in indexed, "invalid_or_duplicate_dataset_case_id")
        scenario = row.get("scenario_id", row.get("fixture_id"))
        _require(scenario in SCENARIOS and row.get("synthetic", True) is True, "synthetic_fixture_binding_required")
        _require("scenario_id" not in row or "fixture_id" not in row
                 or row["scenario_id"] == row["fixture_id"], "dataset_fixture_binding_mismatch")
        _require(isinstance(row.get("customer_request"), str)
                 and 1 <= len(row["customer_request"].strip()) <= 2000, "bounded_synthetic_request_required")
        indexed[row["case_id"]] = (row, scenario)
    _require(set(indexed) == {c["case_id"] for c in gold["stages"]["full"]["manifest"]},
             "full_dataset_cohort_mismatch")
    for stage in STAGES:
        for case in gold["stages"][stage]["manifest"]:
            _require(case["case_id"] in indexed, "stage_case_missing_from_dataset")
            row, scenario = indexed[case["case_id"]]
            _require(case["case_sha256"] == canonical_hash(row) and case["scenario_id"] == scenario
                     and case["journey_type"] == SCENARIOS[scenario].category, "dataset_case_hash_or_fixture_mismatch")
    return indexed


def _run_settings(gold):
    """Explicit business pins; frozen judges from calibrated gold. No API auth bypass."""
    pins = {}
    for role in ROLES:
        name = "AGENT_" + role.upper() + "_VERSION"
        if role.startswith("judge_"):
            pins[role] = {k: gold["provenance"]["agent_pins"][role][k] for k in ("name", "version")}
            _require(name not in os.environ or os.environ[name] == pins[role]["version"],
                     "configured_judge_version_differs_from_gold")
        else:
            version = os.environ.get(name, "")
            _require(version.isdecimal() and int(version) > 0, "explicit_business_agent_versions_required")
            pins[role] = {"name": "cs-sim-" + role, "version": version}
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    _require(bool(client_id), "existing_managed_identity_client_id_required")
    client_id = str(uuid.UUID(client_id))
    source = os.environ.get("GITHUB_SHA") or os.environ.get("APP_REVISION")
    _require(isinstance(source, str) and source and source.lower() not in ("local", "unknown"),
             "explicit_candidate_source_revision_required")
    return SimpleNamespace(pins=pins, client_id=client_id, appinsights=None, otlp_endpoint=None,
                           credential_mode="managed_identity"), source


def _native_provenance(agents, settings, source, config_hash):
    """Actual project agent/deployment readback, before any responses.create call."""
    from native import verify_definition
    pins, models, deployments = {}, {}, {}
    for role in ROLES:
        pin = settings.pins[role]
        agent = agents.project.agents.get_version(agent_name=pin["name"], agent_version=pin["version"])
        _require(str(agent.version) == pin["version"], "native_agent_version_readback_mismatch")
        verify_definition(agent, role)
        pins[role] = {**pin, "definition_sha256": canonical_hash(agent.definition.as_dict())}
        model = agent.definition.model
        if model not in deployments:
            deployments[model] = agents.project.deployments.get(name=model)
        deployment = deployments[model]
        models[role] = {"project_endpoint": PROJECT, "model_id": deployment.model_name,
                        "model_version": deployment.model_version, "model_sku": deployment.sku.name}
    target = models["triage"]
    judge = models["judge_factual_accuracy"]
    _require(all(models[r] == target for r in ("triage", "policy", "resolution")), "heterogeneous_target_models_unsupported")
    _require(all(models["judge_" + c] == judge for c in CRITERIA), "heterogeneous_judge_models_unsupported")
    provenance = {**target, "source_revision": source, "agent_pins": pins,
                  "judge_model": judge, "config_sha256": config_hash}
    _provenance({"provenance": provenance})
    return provenance


def run_candidate(gold_path, dataset_path, *, allow_model_calls=False, max_model_calls=200):
    """Bounded SDK orchestration over existing SimulationEvaluator, never a second model runner."""
    report = {"command": "run", "passed": False, "production_promotion_allowed": False,
              "demo_build_allowed": True, "blocked": [], "stage_execution": [],
              "candidate": None, "raw_results": {}, "max_model_calls": max_model_calls}
    provider = agents = service = None
    try:
        _require(allow_model_calls is True, "explicit_model_call_authorization_required")
        _require(Path(gold_path).is_file(), "calibrated_gold_file_required")
        gold = load_json(gold_path)
        baseline = compare(gold, gold, "historical")
        _require(baseline["passed"], "gold_preflight_failed:" + ",".join(baseline["blocked"]))
        _require(Path(dataset_path).is_file(), "frozen_dataset_file_required")
        indexed = _run_dataset(gold, dataset_path)
        # Profile declares the existing owner's 3/4/3 schema, 400 output tokens,
        # >=7-second pacing and zero retries. Only consensus is selectable here.
        config = gold.get("evaluation_config")
        _require(isinstance(config, dict) and set(config) == {"profile", "consensus"}
                 and config["profile"] == "customer-service-native-v1" and type(config["consensus"]) is bool,
                 "frozen_execution_config_required")
        _require(canonical_hash(config) == gold["provenance"]["config_sha256"], "execution_config_hash_mismatch")
        calls = sum(len(gold["stages"][s]["manifest"]) for s in STAGES) * (15 if config["consensus"] else 7)
        _require(type(max_model_calls) is int and 1 <= max_model_calls <= 1000 and calls <= max_model_calls,
                 "explicit_model_call_budget_exceeded")
        report["planned_max_model_calls"] = calls
        settings, source = _run_settings(gold)
        try:
            from azure.ai.evaluation import evaluate
        except ImportError:
            raise EvidenceError("azure_ai_evaluation_not_installed") from None
        import inspect
        _require({"data", "evaluators", "fail_on_evaluator_errors", "output_path"}.issubset(inspect.signature(evaluate).parameters),
                 "installed_evaluation_sdk_api_unsupported")
        from native import NativeAgents
        from evaluate_cli import SimulationEvaluator
        from simulation import SimulationService, Store
        from telemetry import Telemetry, configure
        provider = configure(settings)
        agents = NativeAgents(settings)
        observed = _native_provenance(agents, settings, source, canonical_hash(config))
        candidate = deepcopy(gold)
        candidate.pop("promotion", None)
        candidate.update(frozen=False, provenance=observed)
        for stage in STAGES:
            candidate["stages"][stage]["results"] = []
        _calibration(candidate)
        _require(frozen_evaluation_hash(observed) == frozen_evaluation_hash(gold["provenance"]),
                 "observed_judge_or_config_differs_from_gold")
        report["candidate"] = candidate
        service = SimulationService(Store(":memory:"), agents, Telemetry(provider), settings.pins)
        captured = []
        evaluator = SimulationEvaluator(service, consensus=config["consensus"], result_sink=captured.append)
        lock = threading.Lock()
        with tempfile.TemporaryDirectory(prefix="cs-regression-") as directory:
            for stage_name in STAGES:
                stage = candidate["stages"][stage_name]
                manifest = {c["case_id"]: c for c in stage["manifest"]}
                raw = report["raw_results"][stage_name] = {}
                stage_failed = threading.Event()

                class CaseEvaluator:
                    def __call__(self, *, case_id: str, scenario_id: str, customer_request: str, **kwargs):
                        with lock:
                            try:
                                _require(not stage_failed.is_set(), "stage_already_failed")
                                _require(case_id not in raw, "sdk_duplicate_case_refused")
                                case = manifest[case_id]
                                _require(scenario_id == case["scenario_id"], "sdk_fixture_binding_mismatch")
                                captured.clear()
                                try:
                                    return evaluator(scenario_id=scenario_id, customer_request=customer_request)
                                finally:
                                    if captured:
                                        actual = captured[-1]
                                        raw[case_id] = actual
                                        stage["results"].append(case_result(case, actual, observed))
                            except Exception:
                                stage_failed.set()
                                raise

                # SDK receives JSONL FILE, not unsupported data-list input.
                data = [{"case_id": c["case_id"], "scenario_id": c["scenario_id"],
                         "customer_request": indexed[c["case_id"]][0]["customer_request"]} for c in stage["manifest"]]
                stage_path = Path(directory) / (stage_name + ".jsonl")
                stage_path.write_text("\n".join(json.dumps(row) for row in data), encoding="utf-8")
                try:
                    evaluate(data=str(stage_path), evaluators={"synthetic_journey": CaseEvaluator()},
                             output_path=str(Path(directory) / (stage_name + "-sdk-results.json")),
                             fail_on_evaluator_errors=True)
                except Exception:
                    stage_failed.set()
                    report["blocked"] = ["sdk_stage_execution_failed:" + stage_name]
                comparison = compare(gold, candidate, stage_name)
                report["comparison"] = comparison
                report["stage_execution"].append({
                    "stage": stage_name, "expected": len(manifest), "captured": len(raw),
                    "failed": sum(r["status"] == "failed" for r in stage["results"]),
                    "passed": comparison["passed"] and not report["blocked"],
                })
                if report["blocked"] or not comparison["passed"]:
                    report["blocked"] = report["blocked"] or comparison["blocked"]
                    return report
        report["passed"] = True
    except EvidenceError as exc:
        report["blocked"] = [str(exc)]
    except ImportError:
        report["blocked"] = ["runtime_dependency_not_installed"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        report["blocked"] = ["missing_or_invalid_run_prerequisite"]
    except Exception:
        # Includes unavailable MI/Foundry metadata readback. No raw credential/provider diagnostics.
        report["blocked"] = ["native_metadata_or_execution_prerequisite_failed"]
    finally:
        try:
            if service is not None:
                service.close()
            elif agents is not None:
                agents.close()
            if provider is not None:
                provider.shutdown()
        except Exception:
            report["passed"] = False
            report["blocked"].append("run_cleanup_failed")
    return report


def _write_run_report(output, report, gold_path, dataset_path):
    output = Path(output).resolve()
    app = Path(__file__).parent.resolve()
    allowed = (app / "evaluation-artifacts", Path.cwd().resolve() / "deploy" / ".state")
    _require(any(output.is_relative_to(root) for root in allowed), "run_output_outside_explicit_state_boundary")
    _require(output not in (Path(gold_path).resolve(), Path(dataset_path).resolve()), "run_cannot_overwrite_inputs")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic report replacement only; gold/dataset/source are never overwritten.
    with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, delete=False, encoding="utf-8") as target:
        temp = Path(target.name)
        try:
            json.dump(report, target, allow_nan=False, indent=2)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("compare")
    check.add_argument("--gold", type=Path, required=True)
    check.add_argument("--candidate", type=Path, required=True)
    check.add_argument("--through", choices=STAGES, default="canary")
    promotion = commands.add_parser("promote")
    for name in ("gold", "candidate", "approval", "output"):
        promotion.add_argument("--" + name, type=Path, required=True)
    rolling = commands.add_parser("drift")
    rolling.add_argument("--snapshots", type=Path, required=True)
    rolling.add_argument("--as-of", required=True)
    sample = commands.add_parser("sample")
    sample.add_argument("--run-id", required=True)
    sample.add_argument("--synthetic", action="store_true", required=True)
    run = commands.add_parser("run", help="Explicit bounded native SDK run; calibrated gold required first")
    run.add_argument("--gold", type=Path, required=True)
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--allow-model-calls", action="store_true")
    run.add_argument("--max-model-calls", type=int, default=200)
    args = parser.parse_args()
    try:
        if args.command == "run":
            _write_run_report(args.output, {"command": "run", "passed": False,
                                           "blocked": ["not_started"], "production_promotion_allowed": False},
                              args.gold, args.dataset)
            result = run_candidate(args.gold, args.dataset, allow_model_calls=args.allow_model_calls,
                                   max_model_calls=args.max_model_calls)
            _write_run_report(args.output, result, args.gold, args.dataset)
            # Full synthetic raw readbacks stay in explicit state artifact, never stdout/logs.
            print(json.dumps({"passed": result["passed"], "blocked": result["blocked"],
                              "stage_execution": result["stage_execution"], "report": str(args.output),
                              "production_promotion_allowed": False}, allow_nan=False))
            return 0 if result["passed"] else 1
        if args.command == "compare":
            result = compare(load_json(args.gold), load_json(args.candidate), args.through)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["passed"] else 1
        if args.command == "sample":
            result = {"synthetic": True, "selected": sample_synthetic(args.run_id, synthetic=args.synthetic),
                      "bucket_rule": "SHA256(run_id) modulo 10000 < 100"}
        elif args.command == "drift":
            _require(args.snapshots.stat().st_size <= MAX_EVIDENCE_BYTES, "snapshot_file_too_large")
            rows = [_parse_json(line) for line in args.snapshots.read_text(encoding="utf-8").splitlines() if line.strip()]
            result = drift(rows, args.as_of)
        else:
            result = promote(load_json(args.gold), load_json(args.candidate), load_json(args.approval))
            output = args.output.resolve()
            root = Path(__file__).parent.resolve() / "evaluation-artifacts"
            _require(output.is_relative_to(root), "promotion_output_outside_evaluation_artifacts")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as target:
                json.dump(result, target, indent=2, allow_nan=False)
            result = {"written": str(output), "gold_sha256": canonical_hash(result),
                      "previous_gold_unchanged": True}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if args.command != "drift" or result["status"] == "no_threshold_drift" else 1
    except (EvidenceError, KeyError, TypeError, ValueError, OSError):
        print(json.dumps({"passed": False, "blocked": "invalid_or_unavailable_evidence_or_output",
                          "production_promotion_allowed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
