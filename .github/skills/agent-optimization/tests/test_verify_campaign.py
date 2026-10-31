import hashlib
import json

import pytest

from agent_optimization import audit_results, detector_version, digest, score
from agent_optimization.scripts import verify_campaign

GRADES = ("TruePositive", "FalsePositive")
PROMPTS = {1: "Classify the incident.", 2: "Classify the incident with calibrated priors.",
           3: "Classify the incident with calibrated priors."}
TOOL_CODE = {"a": "def run(case):\n    return {'rows': []}\n",
             "b": "def run(case):\n    return {'rows': [1]}\n"}


def build_cases():
    cases = []
    for index in range(4):
        cases.append({"case_id": f"dev-{index}", "expected": GRADES[index % 2], "split": "development",
                      "stage": "training", "start_time": "2024-01-01T00:00:00Z", "end_time": "2024-01-02T00:00:00Z",
                      "evidence_band": "ordinary", "evidence_count": 5 + index})
    cases.append({"case_id": "val-0", "expected": "TruePositive", "split": "validation", "stage": "evaluation",
                  "start_time": "2024-02-01T00:00:00Z", "end_time": "2024-02-02T00:00:00Z",
                  "evidence_band": "sparse", "evidence_count": 2})
    cases.append({"case_id": "fin-0", "expected": "FalsePositive", "split": "final", "stage": "evaluation",
                  "start_time": "2024-03-01T00:00:00Z", "end_time": "2024-03-02T00:00:00Z",
                  "evidence_band": "dense", "evidence_count": 9})
    return cases


def detector_definition(threshold):
    rule = {"id": "volume", "name": "Window volume", "query": "SELECT count(*) AS total FROM evidence",
            "enabled": True, "parameters": {"threshold": threshold},
            "processing": {"max_rows": 1, "code": "def process(rows, parameters):\n    return rows[0]"}}
    return {"name": "Window detector", "parent_version": None if threshold == 1 else 1,
            "change_rationale": ["Measure window evidence before classification."],
            "configuration": {"version": f"detector-v{threshold}", "max_window_seconds": 3600,
                              "rule_sets": [{"id": "evidence", "name": "Evidence", "enabled": True, "rules": [rule]}]}}


def build_tool(key):
    code = TOOL_CODE[key]
    descriptions = {"queries": "Evidence rows.", "returns": "Rows.", "logic": "Bounded sample."}
    name = f"evidence_{key}"
    identity = digest({"name": name, "code": code, "family": "sampling", **descriptions,
                       "supersedes": None, "change_rationale": ["Establish a control."]})
    return {"id": "tool_" + identity[:20], "name": name, "version": 1, "description": "Sample evidence.",
            "code": code, "language": "python", **descriptions, "digest": identity,
            "family": "sampling", "source_digest": verify_campaign.source_digest(code), "revision": 1,
            "lineage_id": "lineage_" + identity[:20], "supersedes": None,
            "change_rationale": ["Establish a control."], "introduced_agent_version": 1,
            "agent_versions": [1], "status": "validated", "created_at": "2024-01-01T00:00:00+00:00"}


def detector_evidence(detector, case):
    rule = detector["rules"][0]
    pattern = {"rule_id": rule["id"], "rule_set_id": rule["rule_set_id"], "rule_revision": rule["revision"],
               "name": rule["name"], "query_truncated": False, "query_rows": 1, "matched": True,
               "facts": ["One observation in window"], "technique_ids": [], "summary": {"total": 4}}
    return {"schema_version": 2, "version": detector["version"], "digest": detector["digest"],
            "configuration_digest": detector["configuration_digest"],
            "window": {"start": case["start_time"], "end": case["end_time"]},
            "rule_results": [pattern], "situations": [pattern],
            "summary": {"tests_run": 1, "patterns_matched": 1,
                        "observations": [{"rule_id": rule["id"], "facts": pattern["facts"],
                                          "summary": pattern["summary"], "query_truncated": False}]}}


def build_transcript(config, detector, tools, case, row):
    evidence = {"time_window": {"start": case["start_time"], "end": case["end_time"]},
                "tools": [{"name": tool["name"], "result": {"rows": []}} for tool in tools],
                "situation_detector": detector_evidence(detector, case)}
    schema = {"type": "json_schema", "name": "joint_response_v1", "strict": True,
              "schema": {"type": "object", "properties": {"grade": {"type": "string", "enum": list(GRADES)}},
                         "required": ["grade"], "additionalProperties": False}}
    request = {"model": config["model"],
               "instructions": config["system_prompt"] + "\nReturn one JSON object with a grade.",
               "input": "Classify this incident and return JSON.\n" + json.dumps(evidence, separators=(",", ":")),
               "reasoning": {"effort": "none"}, "max_output_tokens": 1200,
               "text": {"format": schema}, "store": False}
    return {"request": request, "evidence": evidence, "error": row["error"],
            "model_call_attempted": True, "tool_ids": config["tool_ids"],
            "response": {"grade": row["predicted"], "rationale": "recorded", "diagnosis": "bounded",
                         "proposed_actions": [], "citations": []}}


def build_outcomes(cases, config, offset):
    rows = []
    for index, case in enumerate(cases):
        predicted = case["expected"] if (index + offset) % 3 else GRADES[(index + 1) % 2]
        rows.append({**case, "predicted": predicted, "correct": predicted == case["expected"],
                     "elapsed_ms": 100.0 + index, "rationale": "recorded", "error": "", "tool_calls": len(config["tool_ids"]),
                     "situation_detector_version": config["situation_detector_version"],
                     "situation_count": 1, "actions_executed": False})
    return rows


def write_run(root, experiment, config, detector, tools, cases, stage, number, run_id):
    rows = build_outcomes(cases, config, number)
    directory = root / "runs" / run_id
    directory.mkdir(parents=True)
    with (directory / "cases.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    metrics = score(rows, 4321.5, sorted(GRADES))
    record = {"id": run_id, "stage": stage, "status": "completed",
              "started_at": f"2024-04-0{number}T0{0 if stage == 'training' else 1}:00:00+00:00",
              "completed_at": f"2024-04-0{number}T0{0 if stage == 'training' else 1}:30:00+00:00",
              "metrics": metrics, "cases": [], "cases_finished": len(rows), "case_count": len(rows),
              "case_digest": digest(cases), "config_digest": digest(config),
              "workers": experiment["limits"]["workers"], "agent_version": number,
              "tool_ids": config["tool_ids"], "model": config["model"], "dataset_id": experiment["dataset_id"],
              "profile_digest": experiment["profile_digest"], "scorer_version": experiment["scorer_version"],
              "situation_detector_version": config["situation_detector_version"],
              "situation_detector_digest": config["situation_detector_digest"],
              "knowledge_access": config["knowledge_access"],
              "audit": audit_results(rows, sorted(GRADES)), "exemplars": {}}
    best = min(rows, key=lambda item: (not item["correct"], item["elapsed_ms"], item["case_id"]))
    worst = max(rows, key=lambda item: (bool(item["error"]), not item["correct"], item["elapsed_ms"], item["case_id"]))
    for kind, row in (("best", best), ("worst", worst)):
        case = next(item for item in cases if item["case_id"] == row["case_id"])
        artifact = {"run_id": run_id, "agent_version": number, "stage": stage, "selection": kind,
                    "case": {**row, "transcript": build_transcript(config, detector, tools, case, row)}}
        (directory / f"{kind}.json").write_text(json.dumps(artifact))
        record["exemplars"][kind] = {key: row[key] for key in ("case_id", "correct", "expected", "predicted", "elapsed_ms", "error")}
    if stage == "training":
        record["development_failures"] = [row for row in rows if not row["correct"]][:6]
    (directory / "run.json").write_text(json.dumps(record, indent=2))
    return record


def build_campaign(tmp_path):
    root = tmp_path / "campaign"
    (root / "detectors").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "versions").mkdir()
    (root / "probes").mkdir()
    (root / "process").mkdir()
    cases = build_cases()
    (root / "cases.json").write_text(json.dumps(cases))
    detectors = {1: detector_version(detector_definition(1), [], "2024-01-01T00:00:00+00:00", "scope")}
    detectors[2] = detector_version(detector_definition(2), [detectors[1]], "2024-01-02T00:00:00+00:00", "scope")
    for number, detector in detectors.items():
        (root / "detectors" / f"{number}.json").write_text(json.dumps(detector))
    tools = {key: build_tool(key) for key in TOOL_CODE}
    for tool in tools.values():
        (root / "tools" / f"{tool['id']}.json").write_text(json.dumps(tool))
        (root / "tools" / f"{tool['id']}.py").write_text(tool["code"])
    contract = {"version": "joint-query-battery-v1", "sequence": ["a"], "levers": ["detector_rulesets", "tools", "investigator_prompt"],
                "probe_cases_min": 2, "probe_cases_max": 4, "action_policy": "recommendations-only"}
    experiment = {"id": "fixture", "name": "fixture", "protocol": "joint-smoke", "status": "completed",
                  "dataset_id": "dataset-1", "case_count": len(cases), "case_digest": digest(cases),
                  "profile_digest": "profile-1", "scorer_version": "scorer-1",
                  "limits": {"max_versions": 3, "min_versions": 3, "max_tools": 5, "workers": 1, "min_families": 1},
                  "stage_counts": {"training": 4, "evaluation": 2}, "implementation_digest": "implementation-1",
                  "process_contract": contract, "workflow": {"version": 1}, "versions": [], "events": []}
    selections = {1: (1, ["a"]), 2: (2, ["b"]), 3: (2, ["a", "b"])}
    for number in (1, 2, 3):
        detector_number, keys = selections[number]
        detector = detectors[detector_number]
        selected = [tools[key] for key in keys]
        config = {"version": number, "name": f"v{number}", "parent_version": None if number == 1 else number - 1,
                  "system_prompt": PROMPTS[number], "model": "model-x", "generation": number - 1,
                  "tool_ids": [tool["id"] for tool in selected], "knowledge_access": True,
                  "situation_detector_version": detector["version"], "situation_detector_digest": detector["digest"],
                  "process_contract": contract, "created_at": f"2024-04-0{number}T00:00:00+00:00"}
        (root / "versions" / f"{number}.json").write_text(json.dumps(config))
        training = write_run(root, experiment, config, detector, selected,
                             [case for case in cases if case["stage"] == "training"], "training", number, f"run-t{number}")
        evaluation = write_run(root, experiment, config, detector, selected,
                               [case for case in cases if case["stage"] == "evaluation"], "evaluation", number, f"run-e{number}")
        candidate = {**config, "status": "completed", "training_runs": [training], "evaluations": [evaluation],
                     "metrics": training["metrics"], "evaluation_metrics": evaluation["metrics"],
                     "probe_receipt": None, "design_audit": None}
        if number > 1:
            parent = experiment["versions"][number - 2]
            probe_cases = [case for case in cases if case["case_id"] in ("dev-0", "dev-1")]
            results = build_outcomes(probe_cases, config, number)
            proposal = {"parent_version": number - 1, "system_prompt": config["system_prompt"],
                        "tools": [{"id": identifier} for identifier in config["tool_ids"]],
                        "situation_detector": detector["version"], "knowledge_access": True,
                        "design_audit": {"hypothesis": "A calibrated prompt improves grading balance on development.",
                                         "parent_training_run_id": parent["training_runs"][-1]["id"]}}
            receipt = {"id": f"probe{number}", "created_at": f"2024-04-0{number}T00:00:00+00:00",
                       "process_version": contract["version"], "proposal": proposal,
                       "proposal_digest": digest(proposal), "parent_version": number - 1,
                       "case_ids": [case["case_id"] for case in probe_cases],
                       "detector_digest": detector["digest"], "detector_configuration_digest": detector["configuration_digest"],
                       "metrics": score(results, 12.5, sorted(GRADES)), "detector_summary_varies": True,
                       "results": results, "status": "passed"}
            (root / "probes" / f"{receipt['id']}.json").write_text(json.dumps(receipt))
            candidate["probe_receipt"] = {"id": receipt["id"], "proposal_digest": receipt["proposal_digest"],
                                          "created_at": receipt["created_at"]}
            candidate["design_audit"] = proposal["design_audit"]
        experiment["versions"].append(candidate)
    task = "Bounded joint optimization task."
    (root / "process" / "record1.json").write_text(json.dumps(
        {"id": "record1", "at": "2024-04-01T00:00:00+00:00", "session_id": "session-1", "prompt": task,
         "prompt_digest": hashlib.sha256(task.encode()).hexdigest(),
         "implementation_digest": experiment["implementation_digest"], "process_contract": contract}))
    (root / "experiment.json").write_text(json.dumps(experiment, indent=2))
    return root


def run_verifier(root, out, complete=False):
    arguments = ["--experiment", str(root), "--out", str(out)] + (["--complete"] if complete else [])
    code = verify_campaign.main(arguments)
    return code, json.loads((out / "ledger-integrity.json").read_text())


def test_completed_fixture_passes_partial_and_complete(tmp_path, capsys):
    root = build_campaign(tmp_path)
    out = tmp_path / "proof"
    code, report = run_verifier(root, out)
    assert code == 0, report["violations"]
    assert report["counts"]["outcomes"] == 18 and report["counts"]["exemplars"] == 12
    assert report["baseline_pins"]["created_this_run"] is True and report["baseline_pins"]["count"] == 5
    assert len(report["trajectory"]) == 6
    assert (out / "trajectory.csv").read_text().startswith("version,generation,stage")
    assert (out / "ledger-check.log").exists()
    code, report = run_verifier(root, out, complete=True)
    assert code == 0, report["violations"]
    assert report["failed_completion_gates"] == []
    capsys.readouterr()


def test_baseline_pin_change_is_detected(tmp_path, capsys):
    root = build_campaign(tmp_path)
    out = tmp_path / "proof"
    assert run_verifier(root, out)[0] == 0
    cases = json.loads((root / "cases.json").read_text())
    cases[0]["expected"] = "FalsePositive"
    (root / "cases.json").write_text(json.dumps(cases))
    code, report = run_verifier(root, out)
    assert code == 1
    checks = {item["check"] for item in report["violations"]}
    assert "baseline_pin_changed" in checks and "case_digest" in checks
    capsys.readouterr()


def test_edited_outcome_row_is_detected(tmp_path, capsys):
    root = build_campaign(tmp_path)
    out = tmp_path / "proof"
    path = root / "runs/run-t1/cases.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    target = next(row for row in rows if not row["correct"])
    target["correct"] = True
    target["predicted"] = target["expected"]
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
    code, report = run_verifier(root, out)
    assert code == 1
    checks = {item["check"] for item in report["violations"]}
    assert "run_metrics_recompute" in checks and "run_audit_recompute" in checks
    capsys.readouterr()


def test_forged_probe_receipt_is_detected(tmp_path, capsys):
    root = build_campaign(tmp_path)
    out = tmp_path / "proof"
    path = root / "probes/probe2.json"
    receipt = json.loads(path.read_text())
    receipt["proposal"]["system_prompt"] = "Untested rewritten prompt."
    path.write_text(json.dumps(receipt))
    code, report = run_verifier(root, out)
    assert code == 1
    checks = {item["check"] for item in report["violations"]}
    assert "probe_proposal_digest" in checks and "probe_prompt" in checks
    capsys.readouterr()


def test_incomplete_campaign_fails_only_under_complete(tmp_path, capsys):
    root = build_campaign(tmp_path)
    experiment = json.loads((root / "experiment.json").read_text())
    experiment["status"] = "running"
    experiment["versions"][2]["evaluations"][0]["status"] = "failed"
    experiment["versions"][2]["evaluations"][0]["cases_finished"] = 1
    (root / "runs/run-e3/run.json").unlink()
    (root / "experiment.json").write_text(json.dumps(experiment))
    out = tmp_path / "proof"
    code, report = run_verifier(root, out)
    assert code == 0, report["violations"]
    assert report["incomplete_attempts"][0]["status"] == "failed"
    code, report = run_verifier(root, out, complete=True)
    assert code == 1
    gates = set(report["failed_completion_gates"])
    assert {"status_completed", "evaluation_stages", "outcomes", "latest_stages_full"} <= gates
    assert "lever_coverage" not in gates
    capsys.readouterr()


def test_detector_tamper_is_detected(tmp_path, capsys):
    root = build_campaign(tmp_path)
    out = tmp_path / "proof"
    path = root / "detectors/2.json"
    detector = json.loads(path.read_text())
    detector["configuration"]["rule_sets"][0]["enabled"] = False
    path.write_text(json.dumps(detector))
    code, report = run_verifier(root, out)
    assert code == 1
    assert "detector_verification" in {item["check"] for item in report["violations"]}
    capsys.readouterr()


@pytest.mark.parametrize("field", ["prompt_digest", "implementation_digest"])
def test_process_receipt_tamper_is_detected(tmp_path, capsys, field):
    root = build_campaign(tmp_path)
    out = tmp_path / "proof"
    path = root / "process/record1.json"
    record = json.loads(path.read_text())
    record[field] = "0" * 64
    path.write_text(json.dumps(record))
    code, report = run_verifier(root, out)
    assert code == 1
    assert f"process_{field}" in {item["check"] for item in report["violations"]}
    capsys.readouterr()
