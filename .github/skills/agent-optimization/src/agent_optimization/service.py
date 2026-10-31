from __future__ import annotations

import ast
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, wait as wait_futures
from contextvars import copy_context
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from .evaluation import GradeEvaluator, audit_results, score
from .profile import OptimizationProfile
from .persistence import write_json
from .process import (CREATIVE_CONTRACT, CREATIVE_SKILL_PATH, creative_coverage,
                      require_creative_coverage, validate_creative_experiment, validate_investigation_plan)
from .python_tools import PythonToolRunner
from .runs import measure_run
from .workflow import detect, detector_version, knowledge_arguments, verify_detector
from .joint import PROCESS_CONTRACT, PROCESS_VERSION, fingerprint


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


PROTOCOLS = {
    "smoke": {"max_versions": 5, "min_versions": 3, "max_tools": 3, "workers": 1, "min_families": 1},
    "stress-10": {"max_versions": 11, "min_versions": 11, "max_tools": 5, "workers": 4, "min_families": 6},
    "full-10": {"max_versions": 11, "min_versions": 11, "max_tools": 5, "workers": 32, "min_families": 6},
    "joint-10": {"max_versions": 11, "min_versions": 11, "max_tools": 5, "workers": 16, "min_families": 1},
    "joint-12": {"max_versions": 13, "min_versions": 13, "max_tools": 5, "workers": 16, "min_families": 1},
    "joint-smoke": {"max_versions": 3, "min_versions": 3, "max_tools": 5, "workers": 1, "min_families": 1},
}


def compare_evaluation(experiment, candidate, evaluation, grades):
    if not evaluation.get("metrics") or candidate["parent_version"] is None:
        return None
    parent = next(version for version in experiment["versions"] if version["version"] == candidate["parent_version"])
    references = [run for run in parent["evaluations"] if run.get("metrics")
                  and run.get("completed_at", "") <= evaluation["started_at"]]
    if not references:
        return None
    reference = references[-1]
    current_cases = [case for case in evaluation["cases"] if case.get("split") == "validation"]
    reference_cases = [case for case in reference["cases"] if case.get("split") == "validation"]
    if not current_cases or not reference_cases:
        return None
    metrics = score(current_cases, sum(case["elapsed_ms"] for case in current_cases), grades)
    previous = score(reference_cases, sum(case["elapsed_ms"] for case in reference_cases), grades)
    quality = metrics["macro_f1"] - previous["macro_f1"]
    latency = metrics["median_ms"] - previous["median_ms"]
    errors = metrics["error_rate"] - previous["error_rate"]
    verdict = "quality-improved" if quality > 0 else "quality-regressed" if quality < 0 else "quality-unchanged"
    return {"reference_version": parent["version"], "reference_evaluation_id": reference["id"],
            "validation_macro_f1_delta": quality, "median_ms_delta": latency, "error_rate_delta": errors,
            "verdict": verdict, "reason": f"Against v{parent['version']}: validation macro-F1 {quality:+.3f}, validation median {latency:+.0f} ms, validation error rate {errors:+.3f}. Single-run observation; no promotion."}


class OptimizationService:
    def __init__(self, dataset, root: Path, model: str, predict, *, authorize, profile: OptimizationProfile,
                 identify=lambda caller: caller, knowledge_search=None, detector_reference=None,
                 knowledge_reference=None, capability_catalogue=None) -> None:
        self.dataset = dataset
        self.root = root
        self.model = model
        self.profile = profile
        self._authorize = authorize
        self._identify = identify
        self.knowledge_search = knowledge_search
        self.knowledge_reference = knowledge_reference
        self.detector_reference = detector_reference
        if capability_catalogue is not None and not callable(capability_catalogue):
            raise ValueError("capability_catalogue must be a host callback")
        self.capability_catalogue = capability_catalogue
        self.creative_skill_digest = hashlib.sha256(CREATIVE_SKILL_PATH.read_bytes()).hexdigest()
        self.implementation_digest = hashlib.sha256(b"".join(path.read_bytes() for path in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()
        self.evaluator = GradeEvaluator(dataset, predict, profile, knowledge_search=knowledge_search)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="optimization-evaluation")
        self._closing = False
        self._owned_futures = set()
        self.futures = {}
        self.stops = {}
        self.dataset_info = dataset.describe()
        self.case_set = dataset.cases()
        self.case_digest = digest(self.case_set)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in self.root.glob("*/*/experiment.json"):
            record = json.loads(path.read_text())
            if record["status"] in {"running", "baseline_running"}:
                record["status"] = "failed"
                record["error"] = "Host restarted before the iteration reached a terminal state"
                for version in record["versions"]:
                    if version["status"] in {"pending", "running", "tuning"}:
                        version["status"] = "failed"
                        version["error"] = record["error"]
                        for evaluation in [*version.get("training_runs", []), *version["evaluations"]]:
                            if evaluation["status"] == "running":
                                evaluation.update(status="failed", error=record["error"], completed_at=now())
                write_json(path, record)

    def authorize(self, caller) -> str:
        """Host-owned: it decides who may optimize and what owns the resulting directory."""
        return self._authorize(caller)

    def identify(self, caller):
        """Host-owned: the value persisted as a record's owner, checked on every read."""
        return self._identify(caller)

    def directory(self, caller, experiment_id: str) -> Path:
        if len(experiment_id) != 32 or any(character not in "0123456789abcdef" for character in experiment_id):
            raise KeyError("Experiment not found")
        return self.root / self.authorize(caller) / experiment_id

    def get(self, caller, experiment_id: str) -> dict:
        with self.lock:
            path = self.directory(caller, experiment_id) / "experiment.json"
            if not path.exists():
                raise KeyError("Experiment not found")
            record = json.loads(path.read_text())
            if record["owner_id"] != self.identify(caller):
                raise KeyError("Experiment not found")
            if record.get("stage_counts") and record["status"] not in {"failed", "cancelled"}:
                record.pop("error", None)
            for candidate in record["versions"]:
                if record.get("stage_counts"):
                    if candidate["status"] not in {"failed", "cancelled"}:
                        candidate.pop("error", None)
                    training = candidate.get("training_runs", [])
                    evaluation = candidate["evaluations"]
                    candidate["training_metrics"] = training[-1].get("metrics") if training else None
                    candidate["evaluation_metrics"] = evaluation[-1].get("metrics") if evaluation else None
                    measured = [metrics for metrics in (candidate["training_metrics"], candidate["evaluation_metrics"]) if metrics]
                    total = sum(metrics["case_count"] for metrics in measured)
                    candidate["mean_latency_ms"] = sum(metrics["mean_ms"] * metrics["case_count"] for metrics in measured) / total if total else None
                    continue
                for evaluation in candidate["evaluations"]:
                    validation = [case for case in evaluation["cases"] if case.get("split") == "validation"]
                    if evaluation.get("metrics") and validation and "validation_metrics" not in evaluation:
                        evaluation["validation_metrics"] = score(validation, sum(case["elapsed_ms"] for case in validation), self.profile.grades)
                    if "comparison" not in evaluation:
                        evaluation["comparison"] = compare_evaluation(record, candidate, evaluation, self.profile.grades)
                    if "validation_comparison" not in evaluation:
                        evaluation["validation_comparison"] = compare_evaluation(record, candidate, evaluation, self.profile.grades)
                candidate["validation_metrics"] = candidate["evaluations"][-1].get("validation_metrics") if candidate["evaluations"] else None
            record["rejections"] = sorted(
                [{**json.loads(rejection.read_text()), "id": rejection.stem} for rejection in (path.parent / "rejections").glob("*.json")],
                key=lambda rejection: rejection["at"])
            return record

    def _store(self, caller, experiment):
        write_json(self.directory(caller, experiment["id"]) / "experiment.json", experiment)

    def _check_contract(self, experiment):
        if experiment.get("exploration_contract") and experiment["exploration_contract"]["skill_digest"] != self.creative_skill_digest:
            raise ValueError("Creative skill changed; create a new experiment")
        expected_digest = digest([{**case, "stage": "training" if case["split"] == "development" else "evaluation"}
                                  for case in self.case_set]) if experiment.get("workflow") else self.case_digest
        if (experiment.get("tool_runtime") != self.profile.tool_runtime
            or experiment["dataset_id"] != self.dataset_info["dataset_id"]
                or (experiment.get("protocol", "smoke") in {"smoke", "joint-smoke"} and experiment["case_digest"] != expected_digest)
                or experiment["scorer_version"] != self.profile.scorer_version
                or experiment.get("profile_digest", self.dataset.profile_digest) != self.dataset.profile_digest
                or (experiment.get("workflow") and experiment.get("knowledge_reference") != self.knowledge_reference)
                or experiment["versions"][0]["model"] != self.model):
            raise ValueError("Tool runtime, dataset, cases, scorer or model changed; create a new experiment")

    def experiment_cases(self, caller, identifier):
        experiment = self.get(caller, identifier)
        cases = json.loads((self.directory(caller, identifier) / "cases.json").read_text())
        if digest(cases) != experiment["case_digest"]:
            raise ValueError("Frozen case manifest changed")
        return cases

    def capabilities(self, caller, identifier):
        experiment = self.get(caller, identifier)
        value = self.capability_catalogue(caller, experiment) if self.capability_catalogue else {
            "version": 1, "sources": [], "tools": [],
            "limitations": ["This host has not supplied an external capability catalogue."]}
        if not isinstance(value, dict) or value.get("version") != 1 or any(
                not isinstance(value.get(field), list) for field in ("sources", "tools", "limitations")):
            raise ValueError("Capability catalogue requires version 1, sources, tools and limitations")
        encoded = json.dumps(value, allow_nan=False)
        if len(encoded.encode()) > 131072:
            raise ValueError("Capability catalogue exceeds 128 KiB")
        return {**json.loads(encoded), "digest": digest(value)}

    def event(self, caller, experiment_id, event, detail):
        with self.lock:
            experiment = self.get(caller, experiment_id)
            experiment["events"].append({"at": now(), "event": event, "detail": detail})
            self._store(caller, experiment)

    def record_process_task(self, caller, identifier, prompt, session_id, *, skill=None, capabilities=None):
        experiment = self.get(caller, identifier)
        if not experiment.get("process_contract"):
            return
        self._check_contract(experiment)
        record = {"id": uuid.uuid4().hex, "at": now(), "session_id": session_id,
                  "prompt": prompt, "prompt_digest": hashlib.sha256(prompt.encode()).hexdigest(),
                  "implementation_digest": self.implementation_digest, "process_contract": experiment["process_contract"]}
        if capabilities is not None:
            record["capabilities"] = capabilities
        if skill is not None:
            skill_digest = hashlib.sha256(skill.encode()).hexdigest()
            if experiment.get("exploration_contract") and skill_digest != experiment["exploration_contract"]["skill_digest"]:
                raise ValueError("Installed creative skill differs from the campaign pin")
            record["skill"] = {"name": "creative-agent-optimization", "content": skill, "digest": skill_digest}
        if experiment.get("exploration_contract"):
            if skill is None:
                raise ValueError("Creative campaign requires its installed skill receipt")
            record["exploration_contract"] = experiment["exploration_contract"]
        write_json(self.directory(caller, identifier) / "process" / f"{record['id']}.json", record, immutable=True)
        self.event(caller, identifier, "process_contract_loaded", f"{record['id']}: task {record['prompt_digest']}")

    def intervene(self, caller, identifier, guidance):
        with self.lock:
            experiment = self.get(caller, identifier)
            if experiment["status"] in {"completed", "cancelled"}:
                raise ValueError("Cannot intervene after the experiment has ended")
            if not isinstance(guidance, str) or not 20 <= len(guidance.strip()) <= 4000:
                raise ValueError("Guidance requires 20 to 4000 characters")
            note = {"id": uuid.uuid4().hex, "at": now(), "after_version": len(experiment["versions"]),
                    "guidance": guidance.strip(), "actor": "local-operator"}
            write_json(self.directory(caller, identifier) / "interventions" / f"{note['id']}.json", note, immutable=True)
            experiment.setdefault("interventions", []).append(note)
            experiment["events"].append({"at": note["at"], "event": "operator_guidance", "detail": note["guidance"]})
            self._store(caller, experiment)
            return note

    def snapshot(self, caller) -> dict:
        owner = self.authorize(caller)
        experiments = [self.get(caller, path.parent.name) for path in sorted((self.root / owner).glob("*/experiment.json"))]
        experiments.sort(key=lambda experiment: experiment["created_at"])
        tools = []
        for experiment in experiments:
            for path in sorted((self.directory(caller, experiment["id"]) / "tools").glob("*.json")):
                tool = json.loads(path.read_text())
                tool.setdefault("language", "sql")
                tool["agent_versions"] = [version["version"] for version in experiment["versions"] if tool["id"] in version["tool_ids"]]
                tool["first_agent_version"] = min(tool["agent_versions"], default=None)
                tool["last_agent_version"] = max(tool["agent_versions"], default=None)
                tool.setdefault("revision", 1)
                tools.append(tool)
            tools.sort(key=lambda tool: (tool["created_at"], tool["id"]))
        detectors = []
        for experiment in experiments:
            for detector in self.detectors(caller, experiment["id"]):
                using = [version["version"] for version in experiment["versions"] if version.get("situation_detector_version") == detector["version"]]
                detectors.append({**detector, "experiment_id": experiment["id"], "agent_versions": using,
                                  "first_agent_version": min(using, default=None), "last_agent_version": max(using, default=None)})
        return {"available": True, "creative_supported": True, "dataset": self.dataset_info, "experiments": experiments, "tools": tools,
                "detectors": detectors, "detector_reference": self.detector_reference,
                "knowledge_configured": self.knowledge_search is not None}

    def detectors(self, caller, identifier):
        self.get(caller, identifier)
        return sorted([json.loads(path.read_text()) for path in (self.directory(caller, identifier) / "detectors").glob("*.json")],
                      key=lambda item: item["version"])

    def detector(self, caller, identifier, number):
        if type(number) is not int:
            raise ValueError("Unknown detector version")
        value = next((item for item in self.detectors(caller, identifier) if item["version"] == number), None)
        if value is None:
            raise ValueError("Unknown detector version")
        verify_detector(value)
        return value

    def test_detector(self, caller, identifier, case_id, definition):
        experiment = self.get(caller, identifier)
        if not experiment.get("workflow") or experiment["status"] in {"cancelled", "completed"}:
            raise ValueError("Detector testing requires an active workflow experiment")
        allowed = {case["case_id"] for case in self.experiment_cases(caller, identifier) if case["split"] == "development"}
        if case_id not in allowed:
            raise PermissionError("Only development case queries are exposed")
        value = self.detector(caller, identifier, definition) if type(definition) is int else self._detector_version(definition, self.detectors(caller, identifier))
        case = next(case for case in self.experiment_cases(caller, identifier) if case["case_id"] == case_id)
        return detect(self.dataset, case_id, value, {"start": case["start_time"], "end": case["end_time"]})

    def _detector_version(self, definition, history):
        scope = (self.profile.workflow_contract or {}).get("input", "")
        return detector_version(definition, history, now(), scope)

    def probe(self, caller, identifier, proposal, case_ids):
        with self.lock:
            experiment = self.get(caller, identifier)
            self._check_contract(experiment)
            if not experiment.get("process_contract") or experiment["status"] in {"completed", "cancelled", "running", "baseline_running"}:
                raise ValueError("Joint probes require an idle active joint experiment")
            if len(list((self.directory(caller, identifier) / "probes").glob("*.json"))) >= 60:
                raise ValueError("Joint campaign probe budget is 60 recorded attempts")
            self._process_audit(experiment, proposal)
            if not isinstance(case_ids, list) or not 2 <= len(case_ids) <= 4 or len(set(case_ids)) != len(case_ids):
                raise ValueError("Probe requires 2 to 4 distinct development cases")
            cases = {case["case_id"]: case for case in self.experiment_cases(caller, identifier) if case["split"] == "development"}
            if any(identifier not in cases for identifier in case_ids):
                raise PermissionError("Only development case probes are exposed")
            selected = [cases[case_id] for case_id in case_ids]
            if len({case["expected"] for case in selected}) < 2:
                raise ValueError("Choose contrasting development cases from at least two grades")
            if not isinstance(proposal.get("system_prompt"), str) or not 1 <= len(proposal["system_prompt"]) <= 8000:
                raise ValueError("Probe requires the proposed investigator prompt")
            definitions = proposal.get("tools")
            if not isinstance(definitions, list) or not 1 <= len(definitions) <= experiment["limits"]["max_tools"]:
                raise ValueError("Probe requires the exact proposed tool set")
            tools = []
            for definition in definitions:
                if "id" in definition:
                    tools.append(self._tool(caller, identifier, definition, len(experiment["versions"]) + 1))
                else:
                    PythonToolRunner.validate(definition.get("code", ""))
                    tools.append({**definition, "id": "probe_" + fingerprint(definition)[:20], "language": "python"})
            selection = proposal.get("situation_detector")
            detector = self.detector(caller, identifier, selection) if type(selection) is int else self._detector_version(selection, self.detectors(caller, identifier))
            if detector.get("schema_version") != 2:
                raise ValueError("Joint generations require standardized query rulesets")
            candidate = {"version": len(experiment["versions"]) + 1, "system_prompt": proposal["system_prompt"], "model": self.model,
                         "situation_detector_version": detector["version"], "_detector": detector,
                         "knowledge_access": proposal.get("knowledge_access", True), "process_contract": PROCESS_CONTRACT}
            if type(candidate["knowledge_access"]) is not bool:
                raise ValueError("knowledge_access must be boolean")
        results, metrics = self.evaluator.run(candidate, tools, selected, lambda: False, lambda result: None, capture=True)
        summaries = [result["transcript"]["evidence"].get("situation_detector", {}).get("summary") for result in results]
        varied = len({fingerprint(summary) for summary in summaries}) > 1
        receipt = {"id": uuid.uuid4().hex, "created_at": now(), "process_version": PROCESS_VERSION,
                   "proposal": proposal,
                   "proposal_digest": fingerprint({key: value for key, value in proposal.items() if key != "probe_id"}),
                   "parent_version": proposal["parent_version"], "case_ids": case_ids,
                   "detector_digest": detector["digest"], "detector_configuration_digest": detector["configuration_digest"],
                   "metrics": metrics, "detector_summary_varies": varied, "results": results,
                   "status": "passed" if varied and all(not result["error"] for result in results) else "failed"}
        with self.lock:
            write_json(self.directory(caller, identifier) / "probes" / f"{receipt['id']}.json", receipt, immutable=True)
            self.event(caller, identifier, "development_probe", f"{receipt['id']}: {receipt['status']}; {len(results)} cases")
        return {key: value for key, value in receipt.items() if key not in {"results", "proposal"}} | {
            "cases": [{key: result[key] for key in ("case_id", "expected", "predicted", "correct", "error")} for result in results],
            "detector_summaries": summaries}

    def _process_audit(self, experiment, proposal):
        if not isinstance(proposal, dict):
            raise ValueError("Probe proposal must be a JSON object")
        ancestor = next((version for version in experiment["versions"] if type(proposal.get("parent_version")) is int and version["version"] == proposal["parent_version"]), None)
        audit = proposal.get("design_audit")
        if ancestor is None or ancestor["status"] != "completed" or not isinstance(audit, dict) or audit.get("parent_training_run_id") != ancestor["training_runs"][-1]["id"]:
            raise ValueError("Joint audit must cite a completed parent's latest development run")
        if not isinstance(audit.get("hypothesis"), str) or not 20 <= len(audit["hypothesis"]) <= 800:
            raise ValueError("Joint audit requires a falsifiable hypothesis (20 to 800 characters)")
        decisions = audit.get("levers")
        if not isinstance(decisions, dict) or set(decisions) != set(PROCESS_CONTRACT["levers"]) or any(not isinstance(value, str) or not 15 <= len(value) <= 500 for value in decisions.values()):
            raise ValueError("Audit each lever: detector_rulesets, tools, investigator_prompt; explain change or retain")
        validate_investigation_plan(proposal)
        if experiment.get("exploration_contract"):
            validate_creative_experiment(proposal, ancestor, experiment["exploration_contract"])
            if len(experiment["versions"]) == 1 and len(proposal["tools"]) < experiment["exploration_contract"]["first_successor_min_tools"]:
                raise ValueError("The first creative successor requires at least two specialized tools")
        return ancestor, audit

    def _probe_receipt(self, caller, experiment, proposal):
        self._process_audit(experiment, proposal)
        identifier = proposal.get("probe_id", "")
        if not isinstance(identifier, str) or len(identifier) != 32 or any(character not in "0123456789abcdef" for character in identifier):
            raise ValueError("Joint publication requires a successful probe_id for this exact proposal")
        path = self.directory(caller, experiment["id"]) / "probes" / f"{identifier}.json"
        if not path.is_file():
            raise ValueError("Unknown development probe receipt")
        receipt = json.loads(path.read_text())
        if receipt["status"] != "passed" or receipt["proposal_digest"] != fingerprint({key: value for key, value in proposal.items() if key != "probe_id"}):
            raise ValueError("Probe failed or proposal changed; probe the exact candidate again")
        return {key: receipt[key] for key in ("id", "created_at", "process_version", "proposal_digest", "case_ids", "metrics", "detector_summary_varies", "detector_configuration_digest")}

    def lever_coverage(self, caller, experiment):
        configurations, tools, prompts = set(), set(), set()
        directory = self.directory(caller, experiment["id"])
        for candidate in experiment["versions"]:
            if not candidate.get("process_contract"):
                continue
            detector = self.detector(caller, experiment["id"], candidate["situation_detector_version"])
            configurations.add(fingerprint({key: value for key, value in detector["configuration"].items() if key != "version"}))
            tools.add(tuple(sorted(json.loads((directory / "tools" / f"{identifier}.json").read_text())["source_digest"] for identifier in candidate["tool_ids"])))
            prompts.add(candidate["system_prompt"])
        return {"detector_rulesets": len(configurations), "tools": len(tools), "investigator_prompt": len(prompts)}

    def knowledge(self, caller, identifier, payload):
        experiment = self.get(caller, identifier)
        if not experiment.get("workflow") or self.knowledge_search is None:
            raise ValueError("Knowledge access requires a configured workflow experiment")
        if experiment["status"] in {"completed", "cancelled"}:
            raise ValueError("This experiment has ended")
        return self.knowledge_search(knowledge_arguments(payload, self.profile.knowledge_behaviour_classes))

    def _tool(self, caller, experiment_id, definition, version):
        if "id" in definition:
            identity = definition["id"]
            if not isinstance(identity, str) or len(identity) != 25 or not identity.startswith("tool_") or any(character not in "0123456789abcdef" for character in identity[5:]):
                raise ValueError("Invalid pinned tool id")
            return json.loads((self.directory(caller, experiment_id) / "tools" / f"{identity}.json").read_text())
        code = definition.get("code", "")
        name = str(definition.get("name", "")).strip()
        if not name or len(name) > 80:
            raise ValueError("Tools require a short name")
        PythonToolRunner.validate(code)
        descriptions = {field: str(definition.get(field, "")).strip() for field in ("queries", "returns", "logic")}
        if any(not value or len(value) > 1000 for value in descriptions.values()):
            raise ValueError("Describe what the Python tool queries, returns and computes in 1 to 1000 characters each")
        family = definition.get("family", "sampling")
        if family not in self.profile.tool_families:
            raise ValueError("Choose a declared tool family: " + ", ".join(self.profile.tool_families))
        previous = None
        if definition.get("supersedes"):
            previous = self._tool(caller, experiment_id, {"id": definition["supersedes"]}, version)
            if previous["name"] != name or previous.get("family") != family:
                raise ValueError("A tool revision must keep its predecessor's name and family")
            siblings = [json.loads(path.read_text()) for path in (self.directory(caller, experiment_id) / "tools").glob("*.json")]
            if any(tool.get("supersedes") == previous["id"] for tool in siblings):
                raise ValueError("Revise the latest tool revision, not an already superseded source")
        else:
            for path in (self.directory(caller, experiment_id) / "tools").glob("*.json"):
                existing = json.loads(path.read_text())
                if existing["name"] != name:
                    continue
                expected = {"code": code, "family": family, **descriptions,
                            "change_rationale": definition.get("change_rationale", [])}
                if all(existing.get(field, [] if field == "change_rationale" else None) == value for field, value in expected.items()):
                    return existing
                raise ValueError("A changed tool with an existing name must name the previous tool id in supersedes")
        self.dataset.run_tool(self.case_set[0]["case_id"], {"code": code, "language": "python"})
        identity = digest({"name": name, "code": code, "family": family, **descriptions,
                           "supersedes": previous["id"] if previous else None, "change_rationale": definition.get("change_rationale", [])})
        tool = {"id": "tool_" + identity[:20], "name": name, "version": version,
                "description": str(definition.get("description", "Case-scoped Python evidence tool"))[:1000],
                "code": code, "language": "python", **descriptions, "digest": identity, "experiment_id": experiment_id,
                "family": family, "source_digest": digest(ast.dump(ast.parse(code), include_attributes=False)),
                "revision": previous.get("revision", 1) + 1 if previous else 1,
                "lineage_id": previous.get("lineage_id", previous["id"]) if previous else "lineage_" + identity[:20],
                "supersedes": previous["id"] if previous else None,
                "change_rationale": definition.get("change_rationale", []), "introduced_agent_version": version,
                "agent_versions": [version], "status": "validated", "created_at": now()}
        path = self.directory(caller, experiment_id) / "tools" / f"{tool['id']}.json"
        if path.exists():
            return json.loads(path.read_text())
        write_json(path, tool, immutable=True)
        with path.with_suffix(".py").open("x") as output:
            output.write(code)
        return tool

    def create(self, caller, name: str, protocol: str = "smoke", *, workflow: bool = False, creative: bool = False) -> dict:
        owner = self.authorize(caller)
        if protocol not in PROTOCOLS:
            raise ValueError("Unknown optimization protocol")
        if type(creative) is not bool or (creative and protocol not in {"joint-10", "joint-12"}):
            raise ValueError("Creative exploration requires joint-10 or joint-12")
        joint = protocol in {"joint-10", "joint-12", "joint-smoke"}
        workflow = workflow or joint
        if joint and self.profile.joint_baseline_detector is None:
            raise ValueError("Host has not configured a joint detector baseline")
        if type(workflow) is not bool or (workflow and (protocol == "stress-10" or self.knowledge_search is None)):
            raise ValueError("Workflow needs configured knowledge access and smoke or full-10 protocol")
        cases = self.dataset.full_cases() if protocol in {"full-10", "joint-10", "joint-12"} else self.dataset.stress_cases() if protocol == "stress-10" else self.case_set
        if workflow:
            cases = [{**case, "stage": "training" if case["split"] == "development" else "evaluation"} for case in cases]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Experiment name must contain 1 to 100 characters")
        if len(list((self.root / owner).glob("*/experiment.json"))) >= 20:
            raise ValueError("Local experiment limit reached")
        identifier = uuid.uuid4().hex
        experiment = {"id": identifier, "name": name.strip(), "owner_id": self.identify(caller),
                      "agent_id": "opt_" + identifier, "created_at": now(),
                      "dataset_id": self.dataset_info["dataset_id"], "case_digest": digest(cases),
                      "protocol": protocol, "limits": PROTOCOLS[protocol],
                      "profile_digest": self.dataset.profile_digest,
                      "tool_runtime": self.profile.tool_runtime,
                      "scorer_version": self.profile.scorer_version, "status": "baseline_running",
                      "objective": self.profile.objective,
                      "case_count": len(cases), "versions": [], "events": []}
        if workflow:
            experiment["workflow"] = self.profile.workflow_contract
            experiment["knowledge_reference"] = self.knowledge_reference
        if joint:
            experiment["process_contract"] = PROCESS_CONTRACT
            experiment["implementation_digest"] = self.implementation_digest
        if creative:
            experiment["exploration_contract"] = {**CREATIVE_CONTRACT, "skill_digest": self.creative_skill_digest}
            experiment["limits"] = {**experiment["limits"], "workers": CREATIVE_CONTRACT["workers"]}
        if protocol == "full-10" or workflow:
            experiment["stage_counts"] = {stage: sum(case["stage"] == stage for case in cases) for stage in ("training", "evaluation")}
            experiment["evaluation_policy"] = (self.profile.staged_evaluation_policy
                                               if protocol in {"full-10", "joint-10", "joint-12"} else self.profile.smoke_evaluation_policy)
        with self.lock:
            if self._closing:
                raise RuntimeError("optimization_service_closing")
            self._publish(caller, experiment, dict(self.profile.baseline_proposal), "baseline")
            write_json(self.directory(caller, identifier) / "cases.json", cases, immutable=True)
            if protocol == "stress-10":
                write_json(self.directory(caller, identifier) / "final-cases.json", self.dataset.stress_cases(final=True), immutable=True)
            if protocol == "full-10" or workflow:
                self.measure(caller, identifier, 1, "training")
            else:
                self.evaluate(caller, identifier, 1)
        return self.get(caller, identifier)

    def _publish(self, caller, experiment, proposal, origin):
        versions = experiment["versions"]
        limits = experiment.get("limits", PROTOCOLS["smoke"])
        if len(versions) >= limits["max_versions"]:
            raise ValueError(f"Experiment version budget is {limits['max_versions']}, including baseline")
        number = len(versions) + 1
        prompt = proposal.get("system_prompt", "")
        definitions = proposal.get("tools", [])
        name = proposal.get("name", "")
        rationale = proposal.get("rationale", "")
        parent = proposal.get("parent_version")
        if (not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 8000
            or not isinstance(definitions, list) or not 1 <= len(definitions) <= limits["max_tools"]
            or any(not isinstance(definition, dict) for definition in definitions)):
            raise ValueError(f"Candidate needs instructions and 1 to {limits['max_tools']} Python tools")
        if not isinstance(name, str) or not 1 <= len(name) <= 80 or not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("Candidate needs a name and improvement rationale")
        if origin != "baseline" and (type(parent) is not int or parent not in [version["version"] for version in versions]):
            raise ValueError("Parent must be a saved candidate version")
        design = proposal.get("design_audit")
        improvements = proposal.get("improvements", [])
        receipt = self._probe_receipt(caller, experiment, proposal) if experiment.get("process_contract") and origin != "baseline" else None
        if origin != "baseline" and (experiment.get("protocol") == "full-10" or experiment.get("workflow")):
            ancestor = next(version for version in versions if version["version"] == parent)
            if ancestor["status"] != "completed" or not ancestor.get("training_runs"):
                raise ValueError("Parent must have completed training and evaluation")
            if not isinstance(design, dict) or design.get("parent_training_run_id") != ancestor["training_runs"][-1]["id"]:
                raise ValueError("Design audit must cite the parent's completed training run id")
            if not isinstance(improvements, list) or not 3 <= len(improvements) <= 6 or any(not isinstance(item, str) or not 15 <= len(item) <= 260 for item in improvements):
                raise ValueError("Provide 3 to 6 concise improvement bullets, 15 to 260 characters each")
            for field in ("observed_gaps", "changes", "expected_tradeoffs"):
                if not isinstance(design.get(field), list) or not 1 <= len(design[field]) <= 4 or any(not isinstance(item, str) or not 15 <= len(item) <= 260 for item in design[field]):
                    raise ValueError(f"Design audit {field} needs 1 to 4 concise evidence/action bullets")
            extra = ("hypothesis", "levers") if experiment.get("process_contract") else ()
            if experiment.get("process_contract") and "investigation_plan" in design:
                extra += ("investigation_plan",)
            if experiment.get("exploration_contract"):
                extra += ("experiment",)
            design = {field: design[field] for field in ("parent_training_run_id", "observed_gaps", "changes", "expected_tradeoffs", *extra)}
            for definition in definitions:
                if "id" in definition:
                    continue
                reasons = definition.get("change_rationale")
                if "family" not in definition or not isinstance(reasons, list) or not 1 <= len(reasons) <= 4 or any(not isinstance(item, str) or not 15 <= len(item) <= 260 for item in reasons):
                    raise ValueError("Each new or revised tool needs a family and 1 to 4 change_rationale bullets")
            rationale = "\n".join("- " + item for item in improvements)
        if origin != "baseline" and experiment.get("protocol") == "stress-10":
            ancestor = next(version for version in versions if version["version"] == parent)
            if any("id" not in definition and "family" not in definition for definition in definitions):
                raise ValueError("Every new stress tool needs an explicit family field; choose from " + ", ".join(self.profile.tool_families))
            if not isinstance(design, dict) or not ancestor["evaluations"] or design.get("parent_evaluation_id") != ancestor["evaluations"][-1]["id"]:
                raise ValueError("Design audit must cite the parent's latest evaluation id")
            for field in ("approach", "observed_gaps", "changes", "expected_tradeoffs", "lesson_from_parent"):
                if not isinstance(design.get(field), str) or not 40 <= len(design[field]) <= 5000:
                    raise ValueError(f"Design audit {field} requires 40 to 5000 characters with specific evidence")
            if not 400 <= len(rationale) <= 12_000:
                raise ValueError("Stress candidate rationale requires 400 to 12000 characters explaining measured gaps and response")
            design = {field: design[field] for field in ("parent_evaluation_id", "approach", "observed_gaps", "changes", "expected_tradeoffs", "lesson_from_parent")}
        tools = [self._tool(caller, experiment["id"], definition, number) for definition in definitions]
        detector = None
        knowledge_access = False
        if experiment.get("workflow"):
            history = self.detectors(caller, experiment["id"]) if versions else []
            ancestor = versions[parent - 1] if parent is not None else None
            baseline_detector = self.profile.joint_baseline_detector if experiment.get("process_contract") else self.profile.baseline_detector
            selection = proposal.get("situation_detector", ancestor["situation_detector_version"] if ancestor else baseline_detector)
            knowledge_access = proposal.get("knowledge_access", ancestor["knowledge_access"] if ancestor else True)
            if type(knowledge_access) is not bool:
                raise ValueError("knowledge_access must be boolean")
            if type(selection) is int:
                detector = self.detector(caller, experiment["id"], selection)
            else:
                detector = self._detector_version(selection, history)
                first = self.case_set[0]
                detect(self.dataset, first["case_id"], detector, {"start": first["start_time"], "end": first["end_time"]})
                write_json(self.directory(caller, experiment["id"]) / "detectors" / f"{detector['version']}.json", detector, immutable=True)
        elif "situation_detector" in proposal or "knowledge_access" in proposal:
            raise ValueError("Create a workflow experiment before changing detector or knowledge access")
        candidate = {"version": number, "name": name, "parent_version": parent,
                     "system_prompt": prompt, "model": self.model,
                     "runtime": dict(self.profile.runtime),
                     "tool_ids": [tool["id"] for tool in tools], "created_at": now(),
                     "status": "pending", "rationale": rationale[:12_000], "origin": origin,
                     "improvements": improvements, "training_runs": [],
                     "design_audit": design, "generation": number - 1,
                     "metrics": None, "evaluations": []}
        if detector is not None:
            candidate.update(situation_detector_version=detector["version"], situation_detector_digest=detector["digest"], knowledge_access=knowledge_access)
            candidate["runtime"].update(self.profile.workflow_runtime)
        if experiment.get("process_contract"):
            if detector is None or detector.get("schema_version") != 2:
                raise ValueError("Joint generations require query ruleset detectors")
            candidate.update(process_contract=PROCESS_CONTRACT, probe_receipt=receipt)
            if experiment.get("exploration_contract"):
                candidate["exploration_contract"] = experiment["exploration_contract"]
            if parent is not None:
                ancestor = versions[parent - 1]
                old_detector = self.detector(caller, experiment["id"], ancestor["situation_detector_version"])
                candidate["lever_changes"] = {
                    "detector_rulesets": fingerprint({key: value for key, value in detector["configuration"].items() if key != "version"}) != fingerprint({key: value for key, value in old_detector["configuration"].items() if key != "version"}),
                    "tools": candidate["tool_ids"] != ancestor["tool_ids"],
                    "investigator_prompt": prompt != ancestor["system_prompt"],
                }
        write_json(self.directory(caller, experiment["id"]) / "versions" / f"{number}.json", candidate, immutable=True)
        experiment["versions"].append(candidate)
        experiment["events"].append({"at": now(), "event": "candidate_saved", "detail": f"v{number}: {name}; {origin}"})
        self._store(caller, experiment)
        return candidate

    def publish(self, caller, experiment_id: str, proposal: dict) -> dict:
        with self.lock:
            experiment = self.get(caller, experiment_id)
            self._check_contract(experiment)
            if experiment["status"] in {"cancelled", "completed"}:
                raise ValueError("This experiment has ended")
            if any(version["status"] in {"running", "tuning", "pending", "tuned"} for version in experiment["versions"]):
                raise ValueError("Wait for the running evaluation")
            if experiment.get("process_contract") and isinstance(proposal, dict) and set(proposal) == {"probe_id"}:
                identifier = proposal["probe_id"]
                if not isinstance(identifier, str) or len(identifier) != 32 or any(character not in "0123456789abcdef" for character in identifier):
                    raise ValueError("Invalid probe_id")
                path = self.directory(caller, experiment_id) / "probes" / f"{identifier}.json"
                if not path.is_file():
                    raise ValueError("Unknown development probe receipt")
                proposal = {**json.loads(path.read_text())["proposal"], "probe_id": identifier}
            proposal = {field: proposal[field] for field in ("name", "parent_version", "rationale", "system_prompt", "tools", "design_audit", "improvements", "situation_detector", "knowledge_access", "probe_id")
                        if isinstance(proposal, dict) and field in proposal}
            if isinstance(proposal.get("tools"), list):
                proposal["tools"] = [{field: definition[field] for field in ("id", "name", "description", "code", "queries", "returns", "logic", "family", "supersedes", "change_rationale") if field in definition}
                                     if isinstance(definition, dict) else None for definition in proposal["tools"]]
            try:
                return self._publish(caller, experiment, proposal, "copilot-cli")
            except Exception as exc:
                identifier = uuid.uuid4().hex
                invalid = isinstance(exc, ValueError)
                code = "candidate_rejected" if invalid else "publish_failed"
                failure = {"code": code, "category": "invalid" if invalid else "failed",
                           "capability_id": "agent-optimization", "operation": "publish",
                           "experiment_id": experiment_id, "rejection_id": identifier,
                           "effect": "unknown", "retry": "read_back_first", "action": "inspect_record"}
                write_json(self.directory(caller, experiment_id) / "rejections" / f"{identifier}.json",
                           {"at": now(), "proposal": proposal, "error": code, "failure": failure}, immutable=True)
                experiment["events"].append({"at": now(), "event": "candidate_rejected", "detail": code, "failure": failure})
                self._store(caller, experiment)
                raise

    def evaluate(self, caller, experiment_id: str, number: int, *, wait: bool = False) -> dict:
        if self.get(caller, experiment_id).get("stage_counts"):
            return self.measure(caller, experiment_id, number, "evaluation", wait=wait)
        with self.lock:
            if self._closing:
                raise RuntimeError("optimization_service_closing")
            experiment = self.get(caller, experiment_id)
            self._check_contract(experiment)
            if experiment["status"] in {"cancelled", "completed"}:
                raise ValueError("This experiment has ended")
            if any(version["status"] == "running" for version in experiment["versions"]):
                raise ValueError("An evaluation is already running")
            if type(number) is not int or not 1 <= number <= len(experiment["versions"]):
                raise ValueError("Unknown candidate version")
            version = experiment["versions"][number - 1]
            if len(version["evaluations"]) >= 3:
                raise ValueError("Three evaluations per version is the demonstration budget")
            evaluation = {"id": uuid.uuid4().hex, "status": "running", "started_at": now(),
                          "metrics": None, "cases": [], "case_digest": experiment["case_digest"],
                          "scorer_version": self.profile.scorer_version, "experiment_id": experiment_id,
                          "workers": experiment.get("limits", PROTOCOLS["smoke"])["workers"],
                          "agent_id": experiment["agent_id"], "agent_version": number,
                          "tool_ids": version["tool_ids"], "model": version["model"],
                          "dataset_id": experiment["dataset_id"], "profile_digest": self.dataset.profile_digest,
                          "config_digest": digest(json.loads((self.directory(caller, experiment_id) / "versions" / f"{number}.json").read_text()))}
            version["evaluations"].append(evaluation)
            version["status"] = "running"
            experiment["status"] = "baseline_running" if number == 1 else "running"
            stop = self.stops.setdefault(experiment_id, threading.Event())
            self._store(caller, experiment)
            future = self.pool.submit(copy_context().run, self._evaluate, caller, experiment_id, number, evaluation["id"], stop)
            self._owned_futures.add(future)
            self.futures[experiment_id] = future
        if wait:
            future.result(timeout=600)
        return self.get(caller, experiment_id)

    def measure(self, caller, identifier, number, stage, *, wait=False):
        with self.lock:
            if self._closing:
                raise RuntimeError("optimization_service_closing")
            experiment = self.get(caller, identifier)
            self._check_contract(experiment)
            if not experiment.get("stage_counts") or stage not in {"training", "evaluation"}:
                raise ValueError("Staged measurement requires full-10 or a workflow experiment")
            if experiment["status"] in {"cancelled", "completed"}:
                raise ValueError("This experiment has ended")
            if any(version["status"] in {"running", "tuning"} for version in experiment["versions"]):
                raise ValueError("A measurement is already running")
            if type(number) is not int or not 1 <= number <= len(experiment["versions"]):
                raise ValueError("Unknown candidate version")
            candidate = experiment["versions"][number - 1]
            if experiment.get("workflow"):
                detector = self.detector(caller, identifier, candidate["situation_detector_version"])
                if detector.get("schema_version") != 2:
                    raise ValueError("Schema-1 detectors are read-only; create a new experiment with schema-2 configuration")
                if detector["digest"] != candidate["situation_detector_digest"]:
                    raise ValueError("Pinned detector digest changed")
            if stage == "evaluation" and (not candidate["training_runs"] or candidate["training_runs"][-1]["status"] != "completed"):
                raise ValueError("Complete the full development tuning pass before evaluation")
            if stage == "training" and candidate["evaluations"]:
                raise ValueError("This version is frozen for evaluation; tune a new generation")
            runs = candidate["training_runs"] if stage == "training" else candidate["evaluations"]
            if len(runs) >= 3:
                raise ValueError("Three recorded attempts per stage and version")
            cases = [case for case in self.experiment_cases(caller, identifier) if case["stage"] == stage]
            record = {"id": uuid.uuid4().hex, "stage": stage, "status": "running", "started_at": now(),
                      "metrics": None, "cases": [], "cases_finished": 0, "case_count": len(cases),
                      "case_digest": digest(cases), "config_digest": digest(json.loads((self.directory(caller, identifier) / "versions" / f"{number}.json").read_text())),
                      "workers": experiment["limits"]["workers"], "agent_version": number,
                      "tool_ids": candidate["tool_ids"], "model": candidate["model"], "dataset_id": experiment["dataset_id"],
                      "profile_digest": experiment["profile_digest"], "scorer_version": self.profile.scorer_version}
            if experiment.get("workflow"):
                record.update(situation_detector_version=candidate["situation_detector_version"],
                              situation_detector_digest=candidate["situation_detector_digest"], knowledge_access=candidate["knowledge_access"])
            runs.append(record)
            candidate["status"] = "tuning" if stage == "training" else "running"
            experiment["status"] = "baseline_running" if number == 1 else "running"
            self._store(caller, experiment)
            stop = self.stops.setdefault(identifier, threading.Event())
            future = self.pool.submit(copy_context().run, self._full_run, caller, identifier, number, stage, record, cases, stop)
            self._owned_futures.add(future)
            self.futures[identifier] = future
        if wait:
            try:
                future.result(timeout=540)
            except FutureTimeout:
                pass
        return self.get(caller, identifier)

    def wait_for_run(self, caller, identifier):
        self.get(caller, identifier)
        future = self.futures.get(identifier)
        if future:
            try:
                future.result(timeout=540)
            except FutureTimeout:
                pass
        return self.feedback(caller, identifier)

    def _full_run(self, caller, identifier, number, stage, record, cases, stop):
        key = "training_runs" if stage == "training" else "evaluations"
        def progress(count):
            with self.lock:
                experiment = self.get(caller, identifier)
                experiment["versions"][number - 1][key][-1]["cases_finished"] = count
                self._store(caller, experiment)
        experiment = self.get(caller, identifier)
        candidate = experiment["versions"][number - 1]
        directory = self.directory(caller, identifier)
        if experiment.get("workflow"):
            detector = self.detector(caller, identifier, candidate["situation_detector_version"])
            if detector["digest"] != candidate["situation_detector_digest"]:
                raise ValueError("Pinned detector digest changed")
            candidate = {**candidate, "_detector": detector}
        tools = [json.loads((directory / "tools" / f"{identity}.json").read_text()) for identity in candidate["tool_ids"]]
        measured = measure_run(self.evaluator, candidate, tools, cases, record, directory / "runs" / record["id"], stop.is_set, progress)
        with self.lock:
            experiment = self.get(caller, identifier)
            candidate = experiment["versions"][number - 1]
            candidate[key][-1] = measured
            candidate["status"] = "tuned" if stage == "training" and measured["status"] == "completed" else measured["status"]
            if stage == "evaluation":
                candidate["metrics"] = measured.get("metrics")
            experiment["status"] = "cancelled" if stop.is_set() else "ready" if measured["status"] == "completed" else measured["status"]
            experiment["events"].append({"at": now(), "event": f"{stage}_finished",
                                         "detail": f"v{number}: {measured['status']}; {measured['cases_finished']}/{len(cases)} cases"})
            self._store(caller, experiment)
            if number == 1 and stage == "training" and measured["status"] == "completed" and not stop.is_set():
                self.measure(caller, identifier, number, "evaluation")

    def exemplar(self, caller, identifier, number, run_id, kind):
        experiment = self.get(caller, identifier)
        candidate = next((version for version in experiment["versions"] if version["version"] == number), None)
        if candidate is None or kind not in {"best", "worst"}:
            raise KeyError("Run example not found")
        run = next((run for run in [*candidate.get("training_runs", []), *candidate["evaluations"]] if run["id"] == run_id), None)
        if run is None or kind not in run.get("exemplars", {}):
            raise KeyError("Run example not found")
        return json.loads((self.directory(caller, identifier) / "runs" / run["id"] / f"{kind}.json").read_text())

    def _evaluate(self, caller, identifier, number, evaluation_id, stop):
        def progress(result):
            with self.lock:
                experiment = self.get(caller, identifier)
                version = experiment["versions"][number - 1]
                version["evaluations"][-1]["cases"].append(result)
                self._store(caller, experiment)
        try:
            if stop.is_set():
                raise InterruptedError("measurement_cancelled")
            experiment = self.get(caller, identifier)
            candidate = experiment["versions"][number - 1]
            tools = [json.loads((self.directory(caller, identifier) / "tools" / f"{tool_id}.json").read_text()) for tool_id in candidate["tool_ids"]]
            cases = self.experiment_cases(caller, identifier)
            results, metrics = self.evaluator.run(candidate, tools, cases, stop.is_set, progress,
                                                 workers=experiment.get("limits", PROTOCOLS["smoke"])["workers"])
            status = "cancelled" if stop.is_set() else "completed"
            error = ""
        except Exception:
            results, metrics = [], None
            status = "cancelled" if stop.is_set() else "failed"
            error = "measurement_cancelled" if stop.is_set() else "measurement_failed"
        with self.lock:
            experiment = self.get(caller, identifier)
            version = experiment["versions"][number - 1]
            evaluation = version["evaluations"][-1]
            evaluation.update(status=status, completed_at=now(), metrics=metrics)
            if error:
                evaluation["error"] = error
                version["error"] = error
                evaluation["failure"] = {
                    "code": error, "category": "interrupted" if status == "cancelled" else "failed",
                    "capability_id": "agent-optimization", "operation": "evaluate", "run_id": evaluation_id,
                    "effect": "unknown", "retry": "read_back_first", "action": "inspect_record",
                }
                version["failure"] = evaluation["failure"]
            if results:
                evaluation["cases"] = results
            evaluation["comparison"] = compare_evaluation(experiment, version, evaluation, self.profile.grades)
            validation = [case for case in evaluation["cases"] if case.get("split") == "validation"]
            if metrics and validation:
                evaluation["validation_metrics"] = score(validation, sum(case["elapsed_ms"] for case in validation), self.profile.grades)
            evaluation["audit"] = audit_results(evaluation["cases"], self.profile.grades) if metrics else None
            version["status"] = status
            version["metrics"] = metrics
            experiment["status"] = "cancelled" if stop.is_set() else "ready" if status == "completed" else status
            detail = f"v{number}: {status}"
            if metrics:
                detail += f"; macro-F1 {metrics['macro_f1']:.3f}; accuracy {metrics['accuracy']:.3f}; median {metrics['median_ms']:.0f} ms"
            experiment["events"].append({"at": now(), "event": "evaluation_finished", "detail": detail})
            write_json(self.directory(caller, identifier) / "evaluations" / f"{evaluation_id}.json", evaluation, immutable=True)
            self._store(caller, experiment)

    def feedback(self, caller, experiment_id, number=None) -> dict:
        experiment = self.get(caller, experiment_id)
        latest = next((version for version in experiment["versions"] if version["version"] == number), experiment["versions"][-1])
        evaluation = latest["evaluations"][-1] if latest["evaluations"] else {}
        failures = [case for case in evaluation.get("cases", []) if case["split"] == "development" and not case["correct"]]
        samples = []
        for grade in self.profile.grades:
            samples.extend([case for case in failures if case["expected"] == grade][:6])
        tools = [json.loads(path.read_text()) for path in (self.directory(caller, experiment_id) / "tools").glob("*.json")]
        families = sorted({tool.get("family", "sampling") for tool in tools})
        if experiment.get("stage_counts"):
            training = latest["training_runs"][-1] if latest.get("training_runs") else {}
            active = evaluation if evaluation else training
            return {"experiment_id": experiment_id, "version": latest["version"], "status": experiment["status"],
                "process_contract": experiment.get("process_contract"),
                "lever_coverage": self.lever_coverage(caller, experiment) if experiment.get("process_contract") else None,
                "exploration_contract": experiment.get("exploration_contract"),
                "exploration_coverage": creative_coverage(experiment["versions"], tools) if experiment.get("exploration_contract") else None,
                "workflow": experiment.get("workflow"), "situation_detector_version": latest.get("situation_detector_version"),
                "knowledge_access": latest.get("knowledge_access", False),
                "version_status": latest["status"], "operator_guidance": experiment.get("interventions", []),
                "training_run_id": training.get("id"), "evaluation_id": evaluation.get("id"),
                "training_metrics": latest.get("training_metrics"), "evaluation_metrics": latest.get("evaluation_metrics"),
                "stage": active.get("stage"), "cases_finished": active.get("cases_finished", 0),
                "case_count": active.get("case_count", 0), "stage_counts": experiment["stage_counts"],
                "limits": experiment["limits"], "evaluation_policy": experiment["evaluation_policy"],
                "development_failures": training.get("development_failures", []),
                "training_audit": training.get("audit"), "evaluation_audit": evaluation.get("audit"),
                "tool_coverage": {"families": families, "required_distinct_families": experiment["limits"]["min_families"],
                          "not_yet_tried": [family for family in self.profile.tool_families if family not in families]},
                "versions": [{"version": version["version"], "name": version["name"], "status": version["status"],
                      "tool_ids": version["tool_ids"], "training_metrics": version.get("training_metrics"),
                      "evaluation_metrics": version.get("evaluation_metrics")} for version in experiment["versions"]]}
        return {"experiment_id": experiment_id, "version": latest["version"],
                "evaluation_id": evaluation.get("id"), "status": experiment["status"], "limits": experiment.get("limits", PROTOCOLS["smoke"]),
                "cases_finished": len(evaluation.get("cases", [])), "case_count": experiment["case_count"],
                "operator_guidance": experiment.get("interventions", []),
            "validation_metrics": latest.get("validation_metrics"),
                "tool_coverage": {"families": families, "required_distinct_families": experiment.get("limits", PROTOCOLS["smoke"])["min_families"],
                                  "not_yet_tried": [family for family in self.profile.tool_families if family not in families],
                                  "tools": [{"id": tool["id"], "name": tool["name"], "family": tool.get("family", "sampling")} for tool in tools]},
            "metrics": latest["metrics"],
            "audit": evaluation.get("audit") or (audit_results(evaluation["cases"], self.profile.grades) if evaluation.get("metrics") else None),
            "development_failures": samples, "development_failure_count": len(failures),
                "versions": [{"version": version["version"], "name": version["name"], "metrics": version["metrics"],
                      "validation_metrics": version.get("validation_metrics"),
                              "evaluation_id": version["evaluations"][-1]["id"] if version["evaluations"] else None,
                              "tool_ids": version["tool_ids"]} for version in experiment["versions"]]}

    def cancel(self, caller, identifier):
        with self.lock:
            experiment = self.get(caller, identifier)
            if experiment["status"] in {"completed", "cancelled"}:
                return experiment
            self.stops.setdefault(identifier, threading.Event()).set()
            experiment["status"] = "cancelled"
            for version in experiment["versions"]:
                if version["status"] in {"pending", "tuned"}:
                    version["status"] = "cancelled"
            experiment["events"].append({"at": now(), "event": "cancelled", "detail": "Operator stopped experiment"})
            self._store(caller, experiment)
            return experiment

    def verify_final(self, caller, identifier):
        with self.lock:
            if self._closing:
                raise RuntimeError("optimization_service_closing")
            experiment = self.get(caller, identifier)
            self._check_contract(experiment)
            if experiment.get("protocol") != "stress-10" or experiment["status"] != "completed":
                raise ValueError("Reserved final cases are available only after the ten-generation campaign completes")
            if experiment.get("final_verification"):
                return experiment
            measured = [version for version in experiment["versions"] if version.get("validation_metrics")]
            candidate = max(measured, key=lambda version: version["validation_metrics"]["macro_f1"])
            record = {"id": uuid.uuid4().hex, "agent_version": candidate["version"], "status": "running", "started_at": now(),
                      "selection": "Highest latest validation macro-F1 after the campaign; final labels never used to select"}
            experiment["final_verification"] = record
            stop = self.stops.setdefault(identifier, threading.Event())
            self._store(caller, experiment)
            future = self.pool.submit(copy_context().run, self._verify_final, caller, identifier, candidate, record, stop)
            self._owned_futures.add(future)
            self.futures[identifier] = future
            return experiment

    def _verify_final(self, caller, identifier, candidate, record, stop):
        try:
            if stop.is_set():
                raise InterruptedError("measurement_cancelled")
            directory = self.directory(caller, identifier)
            cases = json.loads((directory / "final-cases.json").read_text())
            tools = [json.loads((directory / "tools" / f"{tool_id}.json").read_text()) for tool_id in candidate["tool_ids"]]
            results, metrics = self.evaluator.run(candidate, tools, cases, stop.is_set, lambda result: None, workers=4)
            record.update(status="cancelled" if stop.is_set() else "completed", completed_at=now(), metrics=metrics, cases=results, case_digest=digest(cases),
                          tool_ids=candidate["tool_ids"], model=candidate["model"], scorer_version=self.profile.scorer_version)
        except Exception:
            error = "measurement_cancelled" if stop.is_set() else "measurement_failed"
            record.update(status="cancelled" if stop.is_set() else "failed", completed_at=now(), error=error, failure={
                "code": error, "category": "interrupted" if stop.is_set() else "failed", "capability_id": "agent-optimization",
                "operation": "verify_final", "run_id": record["id"], "effect": "unknown",
                "retry": "read_back_first", "action": "inspect_record",
            })
        with self.lock:
            experiment = self.get(caller, identifier)
            experiment["final_verification"] = {key: value for key, value in record.items() if key != "cases"}
            write_json(self.directory(caller, identifier) / "final-evaluations" / f"{record['id']}.json", record, immutable=True)
            self._store(caller, experiment)

    def agent_summaries(self, caller):
        return [{"id": item["agent_id"], "name": item["name"], "experiment_id": item["id"],
                 "versions": item["versions"]} for item in self.snapshot(caller)["experiments"]]


    def finish(self, caller, identifier):
        with self.lock:
            experiment = self.get(caller, identifier)
            if experiment["status"] == "cancelled":
                raise ValueError("Experiment is cancelled")
            if experiment["status"] == "completed":
                return self.feedback(caller, identifier)
            if any(version["status"] in {"running", "pending", "tuning", "tuned"} for version in experiment["versions"]):
                raise ValueError("Evaluate every saved candidate before completing")
            if experiment.get("exploration_contract"):
                tools = [json.loads(path.read_text()) for path in (self.directory(caller, identifier) / "tools").glob("*.json")]
                require_creative_coverage(creative_coverage(experiment["versions"], tools), experiment["exploration_contract"])
            if experiment.get("process_contract"):
                minimum = 2 if experiment["protocol"] == "joint-smoke" else 3
                if any(count < minimum for count in self.lever_coverage(caller, experiment).values()):
                    raise ValueError(f"Joint campaign requires at least {minimum} exercised configurations per lever")
                if any(not candidate.get("probe_receipt") for candidate in experiment["versions"][1:]):
                    raise ValueError("Every successor needs its successful development probe receipt")
            if experiment.get("stage_counts"):
                if len(experiment["versions"]) < experiment["limits"]["min_versions"]:
                    raise ValueError("Complete the required baseline and successor generations before finishing")
                for version in experiment["versions"]:
                    for stage, key in (("training", "training_runs"), ("evaluation", "evaluations")):
                        runs = version.get(key, [])
                        if not runs or runs[-1]["status"] != "completed" or runs[-1]["cases_finished"] != experiment["stage_counts"][stage]:
                            raise ValueError("Every generation must complete both full-case stages")
                tools = [json.loads(path.read_text()) for path in (self.directory(caller, identifier) / "tools").glob("*.json")]
                used = {identity for version in experiment["versions"] for identity in version["tool_ids"]}
                tools = [tool for tool in tools if tool["id"] in used]
                minimum = experiment["limits"]["min_families"]
                if len({tool["family"] for tool in tools}) < minimum or len({tool["source_digest"] for tool in tools}) < minimum:
                    raise ValueError("Full campaign needs six distinct implemented tool families")
            if experiment.get("protocol") == "stress-10":
                if len(experiment["versions"]) != 11:
                    raise ValueError("Complete baseline plus ten generations before finishing")
                if any(version["status"] != "completed" or len(version["evaluations"][-1]["cases"]) != experiment["case_count"] for version in experiment["versions"]):
                    raise ValueError("Every stress generation must finish the complete frozen battery")
                tools = [json.loads(path.read_text()) for path in (self.directory(caller, identifier) / "tools").glob("*.json")]
                used = {identity for version in experiment["versions"] for identity in version["tool_ids"]}
                tools = [tool for tool in tools if tool["id"] in used]
                if len({tool.get("family") for tool in tools}) < 6 or len({tool.get("source_digest") for tool in tools}) < 6:
                    raise ValueError("Stress campaign requires six genuinely different Python tool sources spanning six families")
                strongest = max(experiment["versions"][1:], key=lambda version: version["evaluations"][0]["metrics"]["validation_macro_f1"])
                if len(experiment["versions"][0]["evaluations"]) < 2 or len(strongest["evaluations"]) < 2:
                    raise ValueError(f"Repeat unchanged baseline v1 and strongest first-pass candidate v{strongest['version']} before finishing")
                experiment["repeat_comparison"] = {"baseline_version": 1, "candidate_version": strongest["version"],
                    "baseline_validation_f1": [run["metrics"]["validation_macro_f1"] for run in experiment["versions"][0]["evaluations"]],
                    "candidate_validation_f1": [run["metrics"]["validation_macro_f1"] for run in strongest["evaluations"]]}
            experiment["status"] = "completed"
            experiment["events"].append({"at": now(), "event": "completed", "detail": "CLI completed the bounded experiment; no Investigator reassignment"})
            self._store(caller, experiment)
            return self.feedback(caller, identifier)

    def close(self, *, timeout: float = 5.0) -> None:
        if type(timeout) not in (int, float) or not 0 <= timeout <= threading.TIMEOUT_MAX:
            raise ValueError("invalid_close_timeout")
        deadline = monotonic() + timeout
        if not self.lock.acquire(timeout=timeout):
            raise FutureTimeout("optimization_close_lock_timeout")
        try:
            self._closing = True
            for stop in self.stops.values():
                stop.set()
            self.pool.shutdown(wait=False)
            futures = tuple(self._owned_futures)
        finally:
            self.lock.release()
        _, pending = wait_futures(futures, timeout=max(0, deadline - monotonic()))
        if pending:
            raise FutureTimeout("optimization_close_timeout")