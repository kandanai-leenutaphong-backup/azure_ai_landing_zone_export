from __future__ import annotations

import hashlib
import json
import re

from .joint import detect_rulesets, verify_rulesets, version_rulesets


def verify_detector(detector: dict) -> None:
    if detector.get("schema_version") == 2:
        verify_rulesets(detector)
        return
    if detector.get("schema_version", 1) != 1:
        raise ValueError("Unsupported detector schema")
    for rule in detector["rules"]:
        definition = {field: rule[field] for field in ("id", "name", "description", "code")}
        if rule["digest"] != hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest():
            raise ValueError("Pinned detector rule content changed")
    payload = {field: detector[field] for field in ("name", "parent_version", "change_rationale", "rules")}
    if detector["digest"] != hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest():
        raise ValueError("Pinned detector content changed")


def detector_version(definition: dict, history: list[dict], created_at: str, scope: str = "") -> dict:
    if isinstance(definition, dict) and "rules" in definition and "configuration" not in definition:
        raise ValueError("Schema-1 detector definitions are read-only; supply a schema-2 configuration")
    return version_rulesets(definition, history, created_at, scope)


def detect(dataset, case_id: str, detector: dict, scope: dict | None = None) -> dict:
    if detector.get("schema_version") != 2:
        raise ValueError("Detector execution requires schema-2 configuration; schema-1 records are read-only")
    return detect_rulesets(dataset, case_id, detector, scope)


def knowledge_arguments(payload: dict, behaviour_classes=frozenset()) -> dict:
    allowed = {"question", "technique_ids", "behaviour_classes", "platforms", "max_results"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("Unknown knowledge search arguments")
    result = {"question": "", "technique_ids": [], "behaviour_classes": [], "platforms": [], "max_results": 3, **payload}
    if not isinstance(result["question"], str) or len(result["question"]) > 2000:
        raise ValueError("Knowledge question is capped at 2000 characters")
    for key, limit in (("technique_ids", 16), ("behaviour_classes", 5), ("platforms", 6)):
        values = result[key]
        if not isinstance(values, list) or len(values) > limit or any(not isinstance(value, str) or not 1 <= len(value) <= 100 for value in values):
            raise ValueError("Knowledge filters must be bounded string lists")
    if any(not re.fullmatch(r"T\d{4}(?:\.\d{3})?", value) for value in result["technique_ids"]):
        raise ValueError("Invalid ATT&CK technique filter")
    if set(result["behaviour_classes"]) - set(behaviour_classes):
        raise ValueError("Invalid knowledge behaviour filter")
    if type(result["max_results"]) is not int or not 1 <= result["max_results"] <= 10:
        raise ValueError("Knowledge result count must be 1 to 10")
    return result