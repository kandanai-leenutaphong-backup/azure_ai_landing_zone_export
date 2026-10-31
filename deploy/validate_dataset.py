from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from manage import APP

sys.path.insert(0, str(APP))
from scenarios import SCENARIOS
from generate_dataset import VARIANTS, canonical_hash, validate_generated


def validate(root: Path | None = None) -> dict:
    root = root or APP / "datasets"
    payload = (root / "synthetic-customer-issues.jsonl").read_bytes()
    manifest = json.loads((root / "manifest.json").read_text())
    rows = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    if hashlib.sha256(payload).hexdigest() != manifest["dataset_sha256"]:
        raise ValueError("Frozen dataset bytes differ from the manifest.")
    if len(rows) != 20 or manifest["case_count"] != 20 or len({row["case_id"] for row in rows}) != 20:
        raise ValueError("Expected exactly 20 distinct test cases.")
    expected_ids = {f"{fixture_id}-{number:02d}" for fixture_id in SCENARIOS for number in range(1, 6)}
    if {row["case_id"] for row in rows} != expected_ids:
        raise ValueError("Frozen cohort requires five stratified variations of every supported journey.")
    fixtures = [scenario.public() for scenario in SCENARIOS.values()]
    if canonical_hash(fixtures) != manifest["fixture_catalog_sha256"]:
        raise ValueError("Fixture/catalog drift detected. Review the frozen dataset before evaluating.")
    if canonical_hash([fixture["policy"] for fixture in fixtures]) != manifest["policy_sha256"]:
        raise ValueError("Policy drift detected.")
    if date.today() > date.fromisoformat(manifest["review_due"]):
        raise ValueError("Quarterly dataset review is overdue.")
    for row in rows:
        expected_hash = row["case_sha256"]
        if canonical_hash({key: value for key, value in row.items() if key != "case_sha256"}) != expected_hash:
            raise ValueError(f"Case changed without a new content pin: {row['case_id']}")
        fixture = SCENARIOS[row["fixture_id"]].public()
        if row["scenario_id"] != fixture["id"] or row["fixture_sha256"] != canonical_hash(fixture):
            raise ValueError("Case fixture binding differs from the authoritative scenario.")
        if row["synthetic"] is not True or row["provenance"]["human_labeled"] is not False:
            raise ValueError("Generated interactions cannot masquerade as real customers or human calibration.")
        state = row["ground_truth"]["expected_system_state"]
        expected = {
            "action": fixture["action"], "simulation": True, "real_transaction": False, "state": "recorded",
            "amount_sgd": 49 if fixture["id"] == "duplicate-charge" else None,
        }
        if state != expected or row["ground_truth"]["policy"] != fixture["policy"]:
            raise ValueError("Generated language may not change authoritative expected state or policy.")
        breakdown = row["ground_truth"]["goal_achievement_breakdown"]
        if [breakdown[key]["max_points"] for key in ("information_accuracy", "action_correctness", "customer_effort_minimization")] != [3, 4, 3]:
            raise ValueError("Expected the explicit 3/4/3 goal-achievement rubric.")
        taxonomy = row["taxonomy"]
        if set(taxonomy) != {"interaction_category", "complexity_variant", "customer_persona", "customer_tier", "adversarial_condition"}:
            raise ValueError("Missing four-level taxonomy or customer tier.")
        if taxonomy["interaction_category"] != fixture["category"]:
            raise ValueError("Unsupported interaction category cannot be claimed as covered.")
        variant = VARIANTS[int(row["case_id"].rsplit("-", 1)[1]) - 1]
        if tuple(taxonomy[key] for key in ("complexity_variant", "customer_persona", "customer_tier", "adversarial_condition")) != variant:
            raise ValueError("Case taxonomy differs from its frozen stratified specification.")
    language_rows = [{key: row[key] for key in ("case_id", "customer_request", "customer_follow_ups", "expected_behavior")} for row in rows]
    validate_generated(language_rows, {row["case_id"] for row in rows})
    return {
        "cases": len(rows), "dataset_sha256": manifest["dataset_sha256"],
        "categories": manifest["coverage"]["interaction_categories"],
        "human_review": manifest["human_quality_review"], "calibration": manifest["calibration"],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
