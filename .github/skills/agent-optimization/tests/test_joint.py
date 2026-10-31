from copy import deepcopy
import hashlib
import json
from unittest.mock import Mock

import pytest

from agent_optimization import detect, detector_version, verify_detector


def definition():
    rule = {"id": "volume", "name": "Window volume", "query": "SELECT count(*) AS total FROM evidence", "enabled": True,
            "parameters": {"threshold": 1}, "processing": {"max_rows": 1, "code": "def process(rows, parameters):\n    return rows[0]"}}
    return {"name": "Window detector", "parent_version": None, "change_rationale": ["Measure window evidence before classification."],
            "configuration": {"version": "1", "max_window_seconds": 3600,
                              "rule_sets": [{"id": "evidence", "name": "Evidence", "enabled": True, "rules": [rule]}]}}


def test_ruleset_versions_pin_queries_processing_and_disabled_sets():
    first = detector_version(definition(), [], "first")
    verify_detector(first)
    proposal = definition()
    proposal["parent_version"] = 1
    proposal["configuration"]["rule_sets"][0]["rules"][0]["parameters"]["threshold"] = 3
    second = detector_version(proposal, [first], "second")
    assert second["rules"][0]["revision"] == 2
    assert first["rules"][0]["parameters"]["threshold"] == 1
    second["configuration"]["rule_sets"][0]["enabled"] = False
    with pytest.raises(ValueError, match="content changed"):
        verify_detector(second)


def test_joint_pipeline_uses_battery_and_preserves_window_and_summaries():
    class Dataset:
        calls = []

        def detector_query(self, case_id, rule, window):
            self.calls.append((case_id, rule["id"], window))
            return {"rows": [{"total": 4}]}

        def detector_process(self, case_id, rule, result, window):
            return {"matched": True, "facts": ["Four observations in window"], "technique_ids": [], "summary": result["rows"][0]}

    dataset = Dataset()
    proposal = definition()
    second = deepcopy(proposal["configuration"]["rule_sets"][0]["rules"][0])
    second["id"] = "another"
    proposal["configuration"]["rule_sets"][0]["rules"].append(second)
    disabled = deepcopy(proposal["configuration"]["rule_sets"][0])
    disabled.update(id="disabled", enabled=False)
    disabled["rules"] = disabled["rules"][:1]
    disabled["rules"][0]["id"] = "unused"
    proposal["configuration"]["rule_sets"].append(disabled)
    detector = detector_version(proposal, [], "first")
    window = {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T00:30:00Z"}
    result = detect(dataset, "case", detector, window)
    assert len(dataset.calls) == result["summary"]["tests_run"] == 2
    assert [entry["rule_id"] for entry in result["rule_results"]] == ["volume", "another"]
    assert [entry["rule_id"] for entry in result["situations"]] == ["volume", "another"]
    assert all(call[2] is window for call in dataset.calls)
    assert result["summary"]["observations"][0]["summary"] == {"total": 4}
    assert result["configuration_digest"] == detector["configuration_digest"]
    with pytest.raises(ValueError, match="exceeds"):
        detect(dataset, "case", detector, {"start": "2024-01-01T00:00:00Z", "end": "2024-01-02T00:00:00Z"})


@pytest.mark.parametrize("schema_version", [None, 1])
def test_schema_one_is_verifiable_but_read_only(schema_version):
    rule = {"id": "historical", "name": "Historical rule", "description": "Retained source",
            "code": "def run(ctx):\n    return {'matched': True, 'facts': ['Retained'], 'technique_ids': []}\n"}
    legacy = {"name": "Historical detector", "parent_version": None,
              "change_rationale": ["Preserve historical records without running retired rules."],
              "rules": [{**rule, "revision": 1,
                         "digest": hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()}]}
    legacy["digest"] = hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()
    legacy["version"] = 1
    if schema_version is not None:
        legacy["schema_version"] = schema_version
    original = deepcopy(legacy)
    verify_detector(legacy)
    dataset = Mock()
    with pytest.raises(ValueError, match="schema-1 records are read-only"):
        detect(dataset, "case", legacy, {"start": "2024-01-01", "end": "2024-01-02"})
    with pytest.raises(ValueError, match="read-only"):
        detector_version({"name": legacy["name"], "parent_version": None,
                          "change_rationale": legacy["change_rationale"], "rules": [rule]}, [], "new")
    assert dataset.mock_calls == []
    assert legacy == original
    legacy["rules"][0]["code"] += "\n"
    with pytest.raises(ValueError, match="content changed"):
        verify_detector(legacy)