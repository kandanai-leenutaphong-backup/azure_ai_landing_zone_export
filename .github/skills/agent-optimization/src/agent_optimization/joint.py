from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping

from situation_detector import configuration_digest, normalize_config, run_battery, selected_rules


PROCESS_VERSION = "joint-query-battery-v1"
PROCESS_CONTRACT = {
    "version": PROCESS_VERSION,
    "sequence": ["parent development feedback", "hypothesis and lever audit", "contrasting development probes",
                 "immutable publication", "full development tuning", "frozen evaluation", "readback and next parent"],
    "levers": ["detector_rulesets", "tools", "investigator_prompt"],
    "probe_cases_min": 2,
    "probe_cases_max": 4,
    "action_policy": "recommendations-only",
}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def processing_code(source: str) -> None:
    if not isinstance(source, str) or not 1 <= len(source) <= 12000:
        raise ValueError("Processing source requires 1 to 12000 characters")
    try:
        module = ast.parse(source)
    except SyntaxError as error:
        raise ValueError("Invalid rule processing Python") from error
    entries = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "process"]
    if len(entries) != 1 or [argument.arg for argument in entries[0].args.args] != ["rows", "parameters"]:
        raise ValueError("Rule processing must define process(rows, parameters)")


def normalize_rulesets(value: dict) -> dict:
    config = normalize_config(value)
    if len(config["rule_sets"]) > 8 or sum(len(rule_set["rules"]) for rule_set in config["rule_sets"]) > 16:
        raise ValueError("Joint detector is capped at 8 rulesets and 16 declared rules")
    if not 1 <= len(selected_rules(config)) <= 6:
        raise ValueError("Joint detector requires 1 to 6 enabled query tests")
    if config["max_window_seconds"] > 366 * 86400:
        raise ValueError("Joint detector window limit exceeds one year")
    for rule_set in config["rule_sets"]:
        for rule in rule_set["rules"]:
            if len(rule["query"]) > 12000 or not rule["query"].lstrip().lower().startswith(("select", "with")):
                raise ValueError("Detector tests require bounded SELECT queries")
            processing = rule["processing"]
            if set(processing) - {"code", "max_rows"} or type(processing.get("max_rows", 100)) is not int or not 1 <= processing.get("max_rows", 100) <= 200:
                raise ValueError("Rule processing declares code and max_rows (1 to 200) only")
            processing_code(processing.get("code", ""))
    return config


def version_rulesets(definition: dict, history: list[dict], created_at: str, scope: str) -> dict:
    if not isinstance(definition, dict) or set(definition) != {"name", "parent_version", "change_rationale", "configuration"}:
        raise ValueError("Joint detector needs name, parent_version, change_rationale, configuration")
    parent_number = definition["parent_version"]
    parent = next((item for item in history if type(parent_number) is int and item["version"] == parent_number), None)
    if (history and parent is None) or (not history and parent_number is not None):
        raise ValueError("Unknown detector parent version")
    reasons = definition["change_rationale"]
    if not isinstance(definition["name"], str) or not 1 <= len(definition["name"]) <= 80:
        raise ValueError("Detector requires a short name")
    if not isinstance(reasons, list) or not 1 <= len(reasons) <= 4 or any(not isinstance(reason, str) or not 15 <= len(reason) <= 260 for reason in reasons):
        raise ValueError("Detector rationale needs 1 to 4 bounded bullets")
    config = normalize_rulesets(definition["configuration"])
    previous = {rule["id"]: rule for rule in parent["rules"]} if parent else {}
    rules = []
    for rule_set in config["rule_sets"]:
        for declaration in rule_set["rules"]:
            identity = fingerprint({"rule_set_id": rule_set["id"], **declaration})
            old = previous.get(declaration["id"])
            revision = old["revision"] + (old["digest"] != identity) if old else 1
            rules.append({"id": declaration["id"], "name": declaration["name"], "description": declaration.get("metadata", {}).get("description", ""),
                          "rule_set_id": rule_set["id"], "enabled": rule_set["enabled"] and declaration["enabled"],
                          "query": declaration["query"], "parameters": declaration["parameters"],
                          "code": declaration["processing"]["code"], "processing": declaration["processing"],
                          "digest": identity, "revision": revision})
    payload = {"name": definition["name"], "parent_version": parent_number, "change_rationale": reasons,
               "configuration": config, "rules": rules, "schema_version": 2}
    return {**payload, "version": len(history) + 1, "created_at": created_at, "scope": scope,
            "configuration_digest": configuration_digest(config), "digest": fingerprint(payload)}


def verify_rulesets(detector: dict) -> None:
    payload = {field: detector[field] for field in ("name", "parent_version", "change_rationale", "configuration", "rules", "schema_version")}
    if detector["digest"] != fingerprint(payload) or detector["configuration_digest"] != configuration_digest(detector["configuration"]):
        raise ValueError("Pinned detector ruleset content changed")


def detect_rulesets(dataset, case_id: str, detector: dict, window: dict) -> dict:
    verify_rulesets(detector)
    if not isinstance(window, dict) or not window.get("start") or not window.get("end"):
        raise ValueError("Joint detection requires an explicit time window")
    revisions = {rule["id"]: rule["revision"] for rule in detector["rules"]}

    def execute(rule, bounded_window):
        return dataset.detector_query(case_id, rule, bounded_window)

    def process(rule, envelope, bounded_window):
        response = dataset.detector_process(case_id, rule, envelope, bounded_window)
        if not isinstance(response, dict) or set(response) != {"matched", "facts", "technique_ids", "summary"} or type(response["matched"]) is not bool:
            raise ValueError("Processing returns matched (boolean), facts, technique_ids and summary only")
        if not isinstance(response["facts"], list) or not 1 <= len(response["facts"]) <= 8 or any(not isinstance(fact, str) or not 1 <= len(fact) <= 500 for fact in response["facts"]):
            raise ValueError("Rule facts require 1 to 8 bounded strings")
        if not isinstance(response["summary"], Mapping) or len(json.dumps(response["summary"], allow_nan=False)) > 4000:
            raise ValueError("Rule summary requires a bounded JSON object")
        if not isinstance(response["technique_ids"], list) or len(response["technique_ids"]) > 16 or any(not isinstance(item, str) or len(item) > 20 for item in response["technique_ids"]):
            raise ValueError("Rule technique_ids must be a bounded list")
        return dict(response)

    battery = run_battery(detector["configuration"], window, execute, process)
    patterns = [{"rule_id": result["rule_id"], "rule_set_id": result["rule_set_id"], "rule_revision": revisions[result["rule_id"]],
                 "name": result["name"], "query_truncated": bool(result["query_result"].get("truncated", False)),
                 "query_rows": len(result["query_result"].get("rows", [])), **result["processed"]} for result in battery["rules"]]
    matched = [pattern for pattern in patterns if pattern["matched"]]
    return {"schema_version": 2, "version": detector["version"], "digest": detector["digest"], "configuration_digest": battery["configuration_digest"],
            "window": battery["window"], "rule_results": patterns, "situations": matched,
            "summary": {"tests_run": len(patterns), "patterns_matched": len(matched),
                        "observations": [{"rule_id": pattern["rule_id"], "facts": pattern["facts"], "summary": pattern["summary"],
                                          "query_truncated": pattern["query_truncated"]} for pattern in matched]}}