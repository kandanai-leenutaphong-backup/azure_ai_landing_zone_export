"""Read-only integrity verification for a recorded agent optimization campaign.

One bounded scan per invocation. Reads the ledger, recomputes every digest and metric with the
component's own functions, and writes its report into a separate proof directory.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_optimization import audit_results, digest, score, verify_detector
from agent_optimization.process import creative_coverage, require_creative_coverage
from agent_optimization.service import PROTOCOLS

CASE_FIELDS = ("case_id", "expected", "split", "stage", "start_time", "end_time",
               "evidence_band", "evidence_count")
SECRET_MARKERS = ("api_key", "apikey", "client_secret", "account_key", "-----begin",
                  "authorization:", "accountkey=", "sharedaccesskey")
TRAJECTORY_COLUMNS = ("version", "generation", "stage", "run_id", "cases", "errors", "error_rate",
                      "macro_f1", "accuracy", "mean_ms", "p95_ms", "best_prior_evaluation_macro_f1",
                      "delta_vs_best_prior", "delta_vs_baseline")


def equivalent(actual, expected) -> bool:
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(equivalent(actual[key], value) for key, value in expected.items()))
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(equivalent(one, other) for one, other in zip(actual, expected)))
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9)
    return actual == expected


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def source_digest(code: str) -> str:
    return digest(ast.dump(ast.parse(code), include_attributes=False))


def tool_identity(definition: dict) -> str:
    fields = {field: str(definition.get(field, "")).strip() for field in ("queries", "returns", "logic")}
    return digest({"name": str(definition.get("name", "")).strip(), "code": definition.get("code", ""),
                   "family": definition.get("family", "sampling"), **fields,
                   "supersedes": definition.get("supersedes"),
                   "change_rationale": definition.get("change_rationale", [])})


class Report:
    def __init__(self) -> None:
        self.violations: list[dict] = []
        self.unverified: list[dict] = []
        self.log: list[str] = []

    def fail(self, check: str, detail) -> None:
        self.violations.append({"check": check, "detail": str(detail)[:400]})
        self.log.append(f"VIOLATION {check}: {str(detail)[:200]}")

    def note(self, check: str, detail) -> None:
        self.unverified.append({"check": check, "detail": str(detail)[:400]})
        self.log.append(f"UNVERIFIED {check}: {str(detail)[:200]}")

    def expect(self, condition, check: str, detail) -> bool:
        if not condition:
            self.fail(check, detail)
        return bool(condition)

    def line(self, text: str) -> None:
        self.log.append(text)


class Campaign:
    def __init__(self, root: Path, proof: Path, report: Report) -> None:
        self.root = root
        self.proof = proof
        self.report = report
        self.experiment = json.loads((root / "experiment.json").read_text())
        self.cases = json.loads((root / "cases.json").read_text())
        self.case_map = {case["case_id"]: case for case in self.cases}
        self.grades = sorted({case["expected"] for case in self.cases})
        self.counts: Counter = Counter()
        self.stages: list[dict] = []
        self.incomplete: list[dict] = []
        self.tools: dict[str, dict] = {}
        self.usage: dict[str, list[int]] = {}
        self.pins: dict = {}
        self.pins_created = False

    def stage_cases(self, stage: str) -> list[dict]:
        return [case for case in self.cases if case["stage"] == stage]

    def verify_cases(self) -> None:
        report = self.experiment
        self.report.expect(len(self.case_map) == len(self.cases), "case_ids_unique", len(self.cases))
        self.report.expect(digest(self.cases) == report["case_digest"], "case_digest", report["case_digest"])
        self.report.expect(len(self.cases) == report["case_count"], "case_count", len(self.cases))
        observed = dict(Counter(case["stage"] for case in self.cases))
        self.report.expect(observed == report.get("stage_counts", observed), "stage_counts", observed)
        limits = PROTOCOLS.get(report["protocol"], {})
        for key in ("max_versions", "min_versions", "max_tools"):
            if key in limits:
                self.report.expect(report["limits"][key] == limits[key], "protocol_limits", key)
        contract = report.get("exploration_contract")
        if contract:
            self.report.expect(report["limits"]["workers"] == contract["workers"], "creative_workers",
                               report["limits"]["workers"])

    def pin_baseline(self) -> None:
        config = json.loads((self.root / "versions/1.json").read_text())
        relatives = ["cases.json", "versions/1.json"]
        number = config.get("situation_detector_version")
        if number is not None:
            relatives.append(f"detectors/{number}.json")
        for identifier in config["tool_ids"]:
            relatives += [f"tools/{identifier}.json", f"tools/{identifier}.py"]
        current = {relative: file_hash(self.root / relative) for relative in relatives}
        path = self.proof / "early-artifact-hashes.json"
        if path.exists():
            self.pins = json.loads(path.read_text())
            recorded = self.pins.get("hashes", {})
            for relative, value in recorded.items():
                self.report.expect(current.get(relative) == value, "baseline_pin_changed", relative)
            for relative in current:
                self.report.expect(relative in recorded, "baseline_pin_unrecorded", relative)
            self.report.expect(self.pins.get("case_digest") == self.experiment["case_digest"],
                               "baseline_pin_case_digest", self.pins.get("case_digest"))
            return
        self.pins = {"pinned_at": datetime.now(timezone.utc).isoformat(), "experiment_id": self.experiment["id"],
                     "case_digest": self.experiment["case_digest"], "hashes": current}
        self.proof.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.pins, indent=2, sort_keys=True) + "\n")
        self.pins_created = True
        self.report.line(f"pinned {len(current)} baseline artifacts")

    def verify_tool(self, identifier: str, version: int) -> None:
        path = self.root / "tools" / f"{identifier}.json"
        if not path.exists():
            self.report.fail("tool_missing", identifier)
            return
        tool = json.loads(path.read_text())
        self.tools[identifier] = tool
        self.usage.setdefault(identifier, []).append(version)
        self.report.expect(tool["code"] == (self.root / "tools" / f"{identifier}.py").read_text(),
                           "tool_source_mismatch", identifier)
        self.report.expect(tool["source_digest"] == source_digest(tool["code"]), "tool_source_digest", identifier)
        identity = tool_identity(tool)
        self.report.expect(tool["digest"] == identity and tool["id"] == "tool_" + identity[:20],
                           "tool_identity", identifier)
        self.report.expect(tool["introduced_agent_version"] <= version, "tool_introduced_after_use", identifier)
        predecessor_id = tool.get("supersedes")
        if predecessor_id:
            previous = self.tools.get(predecessor_id)
            if previous is None:
                previous_path = self.root / "tools" / f"{predecessor_id}.json"
                previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
            if self.report.expect(previous is not None, "tool_predecessor_missing", predecessor_id):
                self.report.expect(previous["name"] == tool["name"] and previous["family"] == tool["family"],
                                   "tool_revision_identity", identifier)
                self.report.expect(tool["revision"] == previous["revision"] + 1, "tool_revision_number", identifier)
                self.report.expect(tool["lineage_id"] == previous.get("lineage_id", previous["id"]),
                                   "tool_lineage", identifier)
        else:
            self.report.expect(tool["revision"] == 1 and tool["lineage_id"] == "lineage_" + tool["digest"][:20],
                               "tool_lineage_root", identifier)

    def verify_version(self, candidate: dict) -> dict:
        number = candidate["version"]
        config = json.loads((self.root / "versions" / f"{number}.json").read_text())
        for field in ("system_prompt", "model", "tool_ids", "situation_detector_version",
                      "situation_detector_digest", "knowledge_access", "parent_version", "generation"):
            if field in candidate and field in config:
                self.report.expect(config[field] == candidate[field], "version_config_mismatch",
                                   f"v{number}.{field}")
        self.report.expect(config["model"] == self.experiment["versions"][0]["model"], "model_changed", number)
        detector_number = config.get("situation_detector_version")
        if detector_number is not None:
            detector = json.loads((self.root / "detectors" / f"{detector_number}.json").read_text())
            try:
                verify_detector(detector)
            except Exception as error:
                self.report.fail("detector_verification", f"v{number}: {error}")
            self.report.expect(detector["digest"] == config["situation_detector_digest"],
                               "detector_digest_pin", number)
        for identifier in config["tool_ids"]:
            self.verify_tool(identifier, number)
        return config

    def verify_exemplar(self, directory: Path, kind: str, run: dict, config: dict, expected_row: dict) -> None:
        path = directory / f"{kind}.json"
        if not path.exists():
            self.report.fail("exemplar_missing", f"{run['id']}/{kind}")
            return
        example = json.loads(path.read_text())
        label = f"{run['id']}/{kind}"
        self.report.expect(example["run_id"] == run["id"] and example["stage"] == run["stage"]
                           and example["agent_version"] == run["agent_version"] and example["selection"] == kind,
                           "exemplar_identity", label)
        case = dict(example["case"])
        transcript = case.pop("transcript", None)
        self.report.expect(equivalent(case, expected_row), "exemplar_selection", label)
        source = self.case_map.get(case["case_id"], {})
        self.report.expect(all(case.get(field) == source.get(field) for field in CASE_FIELDS),
                           "exemplar_case_row", label)
        if not self.report.expect(isinstance(transcript, dict), "exemplar_transcript_missing", label):
            return
        evidence = transcript.get("evidence", {})
        self.report.expect(transcript.get("tool_ids") == config["tool_ids"], "exemplar_tool_ids", label)
        self.report.expect(evidence.get("time_window") == {"start": source.get("start_time"), "end": source.get("end_time")},
                           "exemplar_time_window", label)
        detector = evidence.get("situation_detector")
        if config.get("situation_detector_version") is not None:
            if self.report.expect(isinstance(detector, dict), "exemplar_detector_missing", label):
                self.report.expect(detector.get("digest") == config["situation_detector_digest"],
                                   "exemplar_detector_digest", label)
                self.report.expect(isinstance(detector.get("window"), dict) and isinstance(detector.get("summary"), dict),
                                   "exemplar_detector_shape", label)
                self.report.expect(detector.get("situations") == [item for item in detector.get("rule_results", []) if item["matched"]],
                                   "exemplar_detector_situations", label)
                if not detector.get("situations"):
                    self.report.expect(transcript.get("model_call_attempted") is False and case["error"],
                                       "detector_miss_model_call", label)
        self.verify_request(transcript, config, case, label)
        self.report.expect(transcript.get("error") == case["error"], "exemplar_error", label)
        self.report.expect(case.get("actions_executed", False) is False, "exemplar_actions_executed", label)
        if case["error"]:
            return
        response = transcript.get("response")
        if self.report.expect(isinstance(response, dict), "exemplar_response_missing", label):
            self.report.expect(response.get("grade") == case["predicted"], "exemplar_response_grade", label)
            self.report.expect(transcript.get("model_call_attempted") is True, "exemplar_model_call", label)
            documents = evidence.get("knowledge", {}).get("result", {}).get("rows", [])
            allowed = {str(document[key]) for document in documents if isinstance(document, dict)
                       for key in ("doc_id", "path") if document.get(key)}
            self.report.expect(set(response.get("citations", [])) <= allowed, "exemplar_citations", label)
        self.report.expect(len(evidence.get("tools", [])) == len(config["tool_ids"]), "exemplar_tool_results", label)

    def verify_request(self, transcript: dict, config: dict, case: dict, label: str) -> None:
        request = transcript.get("request")
        if not self.report.expect(isinstance(request, dict), "request_missing", label):
            return
        self.report.expect(request.get("model") == config["model"], "request_model", label)
        self.report.expect(request.get("store") is False, "request_store", label)
        self.report.expect(isinstance(request.get("instructions"), str)
                           and config["system_prompt"] in request.get("instructions", ""),
                           "request_prompt", label)
        workflow = "situation_detector" in transcript.get("evidence", {})
        budget = request.get("max_output_tokens")
        self.report.expect(isinstance(budget, int) and (budget == 1200 if workflow else budget > 0),
                           "request_output_budget", f"{label}: {budget}")
        if workflow:
            fmt = request.get("text", {}).get("format", {})
            self.report.expect(fmt.get("type") == "json_schema" and fmt.get("strict") is True,
                               "request_strict_schema", label)
        payload = request.get("input", "")
        self.report.expect(case["case_id"] not in payload and "expected" not in payload,
                           "request_label_leak", label)
        start = payload.find("{")
        if start < 0:
            self.report.note("request_evidence_readback", f"{label}: no JSON object in request input")
            return
        try:
            value, index = json.JSONDecoder().raw_decode(payload, start)
        except ValueError as error:
            self.report.note("request_evidence_readback", f"{label}: {error}")
            return
        if payload[index:].strip():
            self.report.note("request_evidence_readback", f"{label}: trailing request text not parsed")
            return
        self.report.expect(equivalent(value, transcript.get("evidence")), "request_evidence_mismatch", label)

    def verify_run(self, candidate: dict, run: dict, stage: str, config: dict) -> None:
        number = candidate["version"]
        directory = self.root / "runs" / run["id"]
        selected = self.stage_cases(stage)
        if run["status"] != "completed":
            detail = {"version": number, "stage": stage, "status": run["status"], "id": run["id"],
                      "reported_count": run["cases_finished"]}
            path = directory / "cases.jsonl"
            if run["status"] != "running" and path.exists():
                raw = path.read_bytes()
                rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
                detail["retained_count"] = len(rows)
                detail["case_file_sha256"] = hashlib.sha256(raw).hexdigest()
                self.report.expect({row["case_id"] for row in rows} <= {case["case_id"] for case in selected},
                                   "attempt_case_membership", run["id"])
            self.incomplete.append(detail)
            return
        saved = json.loads((directory / "run.json").read_text())
        self.report.expect(equivalent(saved, run), "run_record_mismatch", run["id"])
        self.report.expect(run["stage"] == stage and run["agent_version"] == number, "run_identity", run["id"])
        self.report.expect(run["workers"] == self.experiment["limits"]["workers"], "run_workers", run["id"])
        self.report.expect(run["config_digest"] == digest(config), "run_config_digest", run["id"])
        self.report.expect(run["case_digest"] == digest(selected), "run_case_digest", run["id"])
        self.report.expect(run["profile_digest"] == self.experiment["profile_digest"], "run_profile_digest", run["id"])
        self.report.expect(run["scorer_version"] == self.experiment["scorer_version"], "run_scorer", run["id"])
        self.report.expect(run["dataset_id"] == self.experiment["dataset_id"], "run_dataset", run["id"])
        self.report.expect(run["tool_ids"] == config["tool_ids"] and run["model"] == config["model"],
                           "run_pins", run["id"])
        for field in ("situation_detector_version", "situation_detector_digest", "knowledge_access"):
            if field in run:
                self.report.expect(run[field] == config[field], "run_detector_pins", f"{run['id']}.{field}")
        rows = [json.loads(line) for line in (directory / "cases.jsonl").read_text().splitlines() if line.strip()]
        self.report.expect(len(rows) == run["cases_finished"] == run["case_count"] == len(selected),
                           "run_case_count", run["id"])
        self.report.expect({row["case_id"] for row in rows} == {case["case_id"] for case in selected},
                           "run_case_membership", run["id"])
        for row in rows:
            if "transcript" in row:
                self.report.fail("outcome_transcript_retained", row["case_id"])
                break
        source = self.case_map
        if any(any(row.get(field) != source.get(row["case_id"], {}).get(field) for field in CASE_FIELDS) for row in rows):
            self.report.fail("outcome_case_row_changed", run["id"])
        if any(row.get("actions_executed", False) is not False for row in rows):
            self.report.fail("outcome_actions_executed", run["id"])
        self.report.expect(equivalent(score(rows, run["metrics"]["elapsed_ms"], self.grades), run["metrics"]),
                           "run_metrics_recompute", run["id"])
        self.report.expect(equivalent(audit_results(rows, self.grades), run["audit"]), "run_audit_recompute", run["id"])
        self.report.expect(set(run["metrics"]["per_class"]) == set(self.grades), "run_per_class_keys", run["id"])
        best = min(rows, key=lambda item: (not item["correct"], item["elapsed_ms"], item["case_id"]))
        worst = max(rows, key=lambda item: (bool(item["error"]), not item["correct"], item["elapsed_ms"], item["case_id"]))
        for kind, expected_row in (("best", best), ("worst", worst)):
            self.verify_exemplar(directory, kind, run, config, expected_row)
            self.counts["exemplars"] += 1
        if stage == "evaluation":
            training = [item for item in candidate["training_runs"] if item["status"] == "completed"]
            if self.report.expect(bool(training), "evaluation_without_training", run["id"]):
                latest = training[-1]
                self.report.expect(latest["completed_at"] <= run["started_at"], "stage_order", run["id"])
                self.report.expect(latest["config_digest"] == run["config_digest"], "stage_config_drift", run["id"])
        errors = sum(bool(row["error"]) for row in rows)
        self.counts["runs"] += 1
        self.counts["outcomes"] += len(rows)
        self.counts["errors"] += errors
        self.counts[stage] += 1
        self.stages.append({"version": number, "generation": candidate.get("generation"), "stage": stage,
                            "run_id": run["id"], "cases": len(rows), "errors": errors,
                            "error_rate": run["metrics"]["error_rate"], "macro_f1": run["metrics"]["macro_f1"],
                            "accuracy": run["metrics"]["accuracy"], "mean_ms": run["metrics"]["mean_ms"],
                            "p95_ms": run["metrics"]["p95_ms"]})

    def verify_probe(self, candidate: dict, config: dict) -> None:
        receipt_reference = candidate.get("probe_receipt")
        number = candidate["version"]
        if not receipt_reference:
            self.report.fail("successor_without_probe", number)
            return
        path = self.root / "probes" / f"{receipt_reference['id']}.json"
        if not path.exists():
            self.report.fail("probe_receipt_missing", receipt_reference["id"])
            return
        receipt = json.loads(path.read_text())
        self.counts["probes"] += 1
        label = f"v{number}/{receipt['id']}"
        self.report.expect(receipt["status"] == "passed", "probe_status", label)
        proposal = {key: value for key, value in receipt["proposal"].items() if key != "probe_id"}
        self.report.expect(receipt["proposal_digest"] == digest(proposal), "probe_proposal_digest", label)
        self.report.expect(receipt_reference["proposal_digest"] == receipt["proposal_digest"],
                           "probe_reference_digest", label)
        self.report.expect(proposal.get("system_prompt") == config["system_prompt"], "probe_prompt", label)
        definitions = proposal.get("tools", [])
        identifiers = []
        for definition in definitions:
            if "id" in definition:
                identifiers.append(definition["id"])
            elif "code" in definition:
                identifiers.append("tool_" + tool_identity(definition)[:20])
            else:
                self.report.note("probe_tool_selection", f"{label}: tool definition without id or code")
        if len(identifiers) == len(definitions):
            self.report.expect(sorted(identifiers) == sorted(config["tool_ids"]), "probe_tool_selection", label)
        selection = proposal.get("situation_detector")
        if isinstance(selection, int):
            self.report.expect(selection == config["situation_detector_version"], "probe_detector", label)
        else:
            self.report.expect(receipt["detector_digest"] == config["situation_detector_digest"],
                               "probe_detector", label)
        self.report.expect(proposal.get("knowledge_access", True) == config["knowledge_access"],
                           "probe_knowledge_access", label)
        case_ids = receipt["case_ids"]
        self.report.expect(2 <= len(case_ids) <= 4 and len(set(case_ids)) == len(case_ids), "probe_case_count", label)
        self.report.expect(all(self.case_map.get(case_id, {}).get("split") == "development" for case_id in case_ids),
                           "probe_case_split", label)
        self.report.expect(len({self.case_map[case_id]["expected"] for case_id in case_ids if case_id in self.case_map}) >= 2,
                           "probe_case_grades", label)
        self.report.expect(receipt["detector_summary_varies"] is True, "probe_summary_variation", label)
        self.report.expect(all(not result["error"] for result in receipt["results"]), "probe_result_errors", label)
        self.report.expect(equivalent(score(receipt["results"], receipt["metrics"]["elapsed_ms"], self.grades),
                                      receipt["metrics"]), "probe_metrics_recompute", label)
        audit = candidate.get("design_audit") or {}
        if audit.get("parent_training_run_id"):
            parent = next((item for item in self.experiment["versions"]
                           if item["version"] == candidate["parent_version"]), None)
            completed = [run for run in (parent or {}).get("training_runs", []) if run["status"] == "completed"]
            self.report.expect(bool(completed) and audit["parent_training_run_id"] == completed[-1]["id"],
                               "probe_parent_run", label)

    def verify_process_receipts(self) -> None:
        contract = self.experiment.get("exploration_contract")
        for path in sorted((self.root / "process").glob("*.json")):
            record = json.loads(path.read_text())
            self.counts["process_receipts"] += 1
            label = record["id"]
            self.report.expect(record["prompt_digest"] == hashlib.sha256(record["prompt"].encode()).hexdigest(),
                               "process_prompt_digest", label)
            self.report.expect(record["implementation_digest"] == self.experiment["implementation_digest"],
                               "process_implementation_digest", label)
            self.report.expect(record["process_contract"] == self.experiment["process_contract"],
                               "process_contract_pin", label)
            if contract:
                skill = record.get("skill")
                if self.report.expect(isinstance(skill, dict), "process_skill_missing", label):
                    computed = hashlib.sha256(skill["content"].encode()).hexdigest()
                    self.report.expect(skill["digest"] == computed == contract["skill_digest"],
                                       "process_skill_digest", label)
                self.report.expect(record.get("exploration_contract") == contract, "process_exploration_contract", label)
            capabilities = record.get("capabilities")
            if isinstance(capabilities, dict) and "digest" in capabilities:
                value = {key: item for key, item in capabilities.items() if key != "digest"}
                self.report.expect(capabilities["digest"] == digest(value), "process_capability_digest", label)
            lowered = json.dumps(record).lower()
            if any(marker in lowered for marker in SECRET_MARKERS):
                self.report.fail("process_receipt_secret_shaped", label)

    def lever_coverage(self) -> dict:
        configurations, bundles, prompts = set(), set(), set()
        for candidate in self.experiment["versions"]:
            if not candidate.get("process_contract"):
                continue
            detector = json.loads((self.root / "detectors" / f"{candidate['situation_detector_version']}.json").read_text())
            configurations.add(digest({key: value for key, value in detector["configuration"].items() if key != "version"}))
            bundles.add(tuple(sorted(self.tools[identifier]["source_digest"] for identifier in candidate["tool_ids"]
                                     if identifier in self.tools)))
            prompts.add(candidate["system_prompt"])
        return {"detector_rulesets": len(configurations), "tools": len(bundles), "investigator_prompt": len(prompts)}

    def scan(self) -> None:
        self.verify_cases()
        self.pin_baseline()
        for candidate in self.experiment["versions"]:
            config = self.verify_version(candidate)
            if candidate.get("parent_version") is not None:
                self.verify_probe(candidate, config)
            for stage, key in (("training", "training_runs"), ("evaluation", "evaluations")):
                for run in candidate.get(key, []):
                    self.verify_run(candidate, run, stage, config)
        self.verify_process_receipts()

    def trajectory(self) -> list[dict]:
        rows = []
        best_prior = None
        baseline = next((item["macro_f1"] for item in self.stages
                         if item["stage"] == "evaluation" and item["version"] == 1), None)
        for stage in sorted(self.stages, key=lambda item: (item["version"], item["stage"] != "training")):
            row = {column: stage.get(column) for column in TRAJECTORY_COLUMNS if column in stage}
            row["best_prior_evaluation_macro_f1"] = best_prior
            row["delta_vs_best_prior"] = None if best_prior is None else stage["macro_f1"] - best_prior
            row["delta_vs_baseline"] = None if baseline is None else stage["macro_f1"] - baseline
            rows.append({column: row.get(column) for column in TRAJECTORY_COLUMNS})
            if stage["stage"] == "evaluation":
                best_prior = stage["macro_f1"] if best_prior is None else max(best_prior, stage["macro_f1"])
        return rows

    def completion(self) -> dict:
        experiment = self.experiment
        versions = experiment["versions"]
        expected_versions = experiment["limits"]["min_versions"]
        stage_counts = experiment.get("stage_counts", {})
        expected_outcomes = expected_versions * sum(stage_counts.values()) if stage_counts else None
        gates = {
            "status_completed": experiment["status"] == "completed",
            "version_count": len(versions) == expected_versions,
            "training_stages": self.counts["training"] == expected_versions,
            "evaluation_stages": self.counts["evaluation"] == expected_versions,
            "outcomes": expected_outcomes is not None and self.counts["outcomes"] == expected_outcomes,
            "exemplars": self.counts["exemplars"] == 2 * (self.counts["training"] + self.counts["evaluation"])
                          and self.counts["exemplars"] == 4 * expected_versions,
            "latest_stages_full": all(
                candidate.get(key) and candidate[key][-1]["status"] == "completed"
                and candidate[key][-1]["cases_finished"] == stage_counts.get(stage)
                for candidate in versions for stage, key in (("training", "training_runs"), ("evaluation", "evaluations"))),
            "attempts_retained": all(item["status"] in {"failed", "cancelled"} for item in self.incomplete),
            "successor_probes": all(candidate.get("probe_receipt") for candidate in versions[1:]),
        }
        minimum = 2 if experiment["protocol"] == "joint-smoke" else 3
        coverage = self.lever_coverage()
        gates["lever_coverage"] = all(count >= minimum for count in coverage.values())
        contract = experiment.get("exploration_contract")
        creative = None
        if contract:
            creative = creative_coverage(versions, list(self.tools.values()))
            try:
                require_creative_coverage(creative, contract)
                gates["creative_coverage"] = True
            except ValueError as error:
                gates["creative_coverage"] = False
                self.report.line(f"creative coverage incomplete: {error}")
        return {"gates": gates, "lever_coverage": coverage, "lever_minimum": minimum,
                "creative_coverage": creative, "expected_outcomes": expected_outcomes,
                "expected_versions": expected_versions}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a recorded optimization campaign, read-only.")
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--complete", action="store_true")
    arguments = parser.parse_args(argv)
    root = arguments.experiment.resolve()
    proof = arguments.out.resolve()
    proof.mkdir(parents=True, exist_ok=True)
    report = Report()
    campaign = Campaign(root, proof, report)
    campaign.scan()
    completion = campaign.completion()
    failed_gates = sorted(name for name, passed in completion["gates"].items() if not passed)
    if arguments.complete:
        for name in failed_gates:
            report.fail("completion_gate", name)
    trajectory = campaign.trajectory()
    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": campaign.experiment["id"],
        "protocol": campaign.experiment["protocol"],
        "campaign_status": campaign.experiment["status"],
        "complete_requested": bool(arguments.complete),
        "grades": campaign.grades,
        "imports": ["agent_optimization"],
        "baseline_pins": {"count": len(campaign.pins.get("hashes", {})), "created_this_run": campaign.pins_created,
                          "pinned_at": campaign.pins.get("pinned_at")},
        "counts": dict(campaign.counts),
        "versions_recorded": len(campaign.experiment["versions"]),
        "tools": {"used": len(campaign.tools),
                  "families": sorted({tool["family"] for tool in campaign.tools.values()}),
                  "sources": len({tool["source_digest"] for tool in campaign.tools.values()}),
                  "revisions": {identifier: tool["revision"] for identifier, tool in campaign.tools.items()},
                  "usage": {identifier: {"first_agent_version": min(numbers), "last_agent_version": max(numbers)}
                            for identifier, numbers in campaign.usage.items()}},
        "incomplete_attempts": campaign.incomplete,
        "completion": completion,
        "failed_completion_gates": failed_gates,
        "trajectory": trajectory,
        "violations": report.violations,
        "unverified": report.unverified,
        "measurement_claim": "Recorded artifacts re-read and recomputed; no run was executed by this verifier.",
    }
    (proof / "ledger-integrity.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (proof / "trajectory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TRAJECTORY_COLUMNS))
        writer.writeheader()
        writer.writerows(trajectory)
    status = "PASS" if not report.violations else "FAIL"
    report.line(f"{status} violations={len(report.violations)} unverified={len(report.unverified)} "
                f"stages={len(campaign.stages)} outcomes={campaign.counts['outcomes']}")
    (proof / "ledger-check.log").write_text("\n".join(report.log) + "\n")
    print(json.dumps({key: summary[key] for key in ("experiment_id", "campaign_status", "complete_requested",
                                                    "baseline_pins", "counts", "failed_completion_gates",
                                                    "violations", "unverified")}, indent=2))
    return 1 if report.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
