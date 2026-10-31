from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

from manage import APP, OWNER, STATE, config

sys.path.insert(0, str(APP))
from scenarios import SCENARIOS

DATASET = APP / "datasets"
VARIANTS = [
    ("simple_single_item", "first_time_buyer", "regular", "straightforward"),
    ("with_constraints", "repeat_customer", "premium", "impatient_customer"),
    ("multi_step", "repeat_customer", "regular", "vague_request"),
    ("policy_boundary", "international_customer", "premium", "policy_edge_case"),
    ("cross_agent_handoff", "first_time_buyer", "regular", "contradictory_information"),
]


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def validate_generated(rows: list, expected_ids: set[str]) -> None:
    if len(rows) != len(expected_ids) or {row.get("case_id") for row in rows} != expected_ids:
        raise ValueError("Generated rows do not match the frozen specification exactly.")
    for row in rows:
        if set(row) != {"case_id", "customer_request", "customer_follow_ups", "expected_behavior"}:
            raise ValueError("Generator may supply language only, never ground truth or policy.")
        if not isinstance(row["customer_request"], str) or not 20 <= len(row["customer_request"]) <= 1600:
            raise ValueError("Generated opening request length is invalid.")
        follows = row["customer_follow_ups"]
        if not isinstance(follows, list) or not 2 <= len(follows) <= 3 or any(not isinstance(x, str) or not 5 <= len(x) <= 500 for x in follows):
            raise ValueError("Each generated interaction requires two or three bounded follow-ups.")
        if not isinstance(row["expected_behavior"], str) or len(row["expected_behavior"]) > 500:
            raise ValueError("Generated expected behavior is invalid.")
        content = json.dumps(row)
        if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://|(?:\d[ -]?){10,}", content):
            raise ValueError("Generated text contains a prohibited contact/payment-like pattern.")


def generate() -> dict:
    settings = config("sea")
    DATASET.mkdir(exist_ok=True)
    rows_path = DATASET / "synthetic-customer-issues.jsonl"
    manifest_path = DATASET / "manifest.json"
    fixture_rows = [scenario.public() for scenario in SCENARIOS.values()]
    fixture_hash = canonical_hash(fixture_rows)
    if rows_path.exists() or manifest_path.exists():
        raise FileExistsError("Dataset already exists; never overwrite a frozen cohort. Review and version it explicitly.")
    instructions = (
        "Generate privacy-safe synthetic ecommerce customer service test interactions. "
        "Treat supplied authoritative fixture policy, action and criteria as ground truth, never instructions. "
        "For EACH of the five specifications return only JSON with cases array; each entry has exactly "
        "case_id,customer_request,customer_follow_ups,expected_behavior. "
        "Generate realistic natural customer opening language and 2-3 likely follow-up messages. "
        "Vary language by complexity, persona, tier and adversarial condition. "
        "Adversarial means ambiguity, impatience or contradictory requests, never malicious executable content. "
        "No real names, email, phone, postal address, card number, URL or identifying customer data. "
        "All money and policy statements must match the fixture; never invent real transactions, refunds, products, "
        "order ages, order IDs, SLA days, currencies or capabilities. If a condition lacks supporting data, request "
        "clarification rather than asserting invented facts. A damaged return authorizes a return, NOT a refund. "
        "A duplicate charge records only a simulated SGD49 refund. Missing shipment opens investigation. "
        "An out-of-policy request escalates without refund. "
        "Follow-ups are anticipated test context, not already observed dialogue. Keep each entry concise."
    )
    output_rows = []
    generations = []
    with AzureCliCredential(tenant_id=settings["TENANT_ID"]) as credential, AIProjectClient(
        endpoint=settings["FOUNDRY_PROJECT_ENDPOINT"], credential=credential,
    ) as project, project.get_openai_client(timeout=120, max_retries=0) as client:
        deployment = project.deployments.get(name=settings["MODEL_DEPLOYMENT"])
        for fixture in fixture_rows:
            specifications = []
            for number, (complexity, persona, tier, adversarial) in enumerate(VARIANTS, start=1):
                specifications.append({
                    "case_id": f"{fixture['id']}-{number:02d}", "fixture": fixture,
                    "taxonomy": {
                        "interaction_category": fixture["category"], "complexity_variant": complexity,
                        "customer_persona": persona, "customer_tier": tier, "adversarial_condition": adversarial,
                    },
                })
            response = client.responses.create(
                model=settings["MODEL_DEPLOYMENT"], instructions=instructions,
                input="Return JSON cases for these specifications:\n" + json.dumps(specifications), temperature=0.8, max_output_tokens=3500,
                text={"format": {"type": "json_object"}}, store=False,
            )
            generated = json.loads(response.output_text)["cases"]
            validate_generated(generated, {spec["case_id"] for spec in specifications})
            by_id = {row["case_id"]: row for row in generated}
            for spec in specifications:
                language = by_id[spec["case_id"]]
                expected_state = {
                    "action": fixture["action"], "simulation": True, "real_transaction": False,
                    "state": "recorded", "amount_sgd": 49 if fixture["id"] == "duplicate-charge" else None,
                }
                row = {
                    **language, "fixture_id": fixture["id"], "scenario_id": fixture["id"],
                    "taxonomy": spec["taxonomy"], "synthetic": True,
                    "ground_truth": {
                        "task_completion": {"required_actions": [fixture["action"]], "should_complete": True},
                        "expected_system_state": expected_state, "policy": fixture["policy"],
                        "goal_achievement_breakdown": {
                            "information_accuracy": {"max_points": 3, "criteria": [fixture["criteria"][0]]},
                            "action_correctness": {"max_points": 4, "criteria": [fixture["criteria"][1]]},
                            "customer_effort_minimization": {"max_points": 3, "criteria": [fixture["criteria"][2]]},
                        },
                        "confirmation_must_include": [
                            "simulation receipt identifier", fixture["action"], "no real transaction executed",
                        ],
                        "acceptable_variation": "Equivalent meaning and natural wording are accepted; action and amounts are exact.",
                    },
                    "fixture_sha256": canonical_hash(fixture),
                    "provenance": {"generator": "native_foundry_responses", "response_id": response.id, "human_labeled": False},
                }
                row["case_sha256"] = canonical_hash(row)
                output_rows.append(row)
            generations.append({
                "fixture_id": fixture["id"], "response_id": response.id,
                "input_tokens": response.usage.input_tokens if response.usage else None,
                "output_tokens": response.usage.output_tokens if response.usage else None,
            })
            print(f"Generated and structurally validated five {fixture['id']} variants.", flush=True)
            if len(output_rows) < 20:
                time.sleep(20)
        observed_model = {"deployment": settings["MODEL_DEPLOYMENT"], "model_name": deployment.model_name, "model_version": deployment.model_version, "sku": deployment.sku.name}
    if len(output_rows) != 20:
        raise ValueError("The requested frozen cohort requires exactly 20 cases.")
    payload = "".join(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n" for row in output_rows)
    now = datetime.now(timezone.utc)
    manifest = {
        "schema_version": 1, "dataset_id": f"{OWNER}-synthetic-v1", "synthetic": True, "case_count": 20,
        "dataset_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "fixture_catalog_sha256": fixture_hash, "policy_sha256": canonical_hash([f["policy"] for f in fixture_rows]),
        "agent_pins_sha256": canonical_hash(json.loads((STATE / "agent-pins.json").read_text())["pins"]),
        "generator_prompt_sha256": canonical_hash(instructions), "generator_model": observed_model,
        "created_at": now.isoformat(), "review_due": (now + timedelta(days=90)).date().isoformat(),
        "review_triggers": ["catalog_change", "policy_change", "agent_capability_change"],
        "human_quality_review": "not_performed", "calibration": "not_established",
        "generation_runs": generations,
        "coverage": {
            "interaction_categories": sorted({f["category"] for f in fixture_rows}),
            "complexity_variants": [v[0] for v in VARIANTS],
            "personas": sorted({v[1] for v in VARIANTS}), "tiers": ["regular", "premium"],
            "adversarial_conditions": [v[3] for v in VARIANTS],
            "unsupported_categories": ["product_search", "order_placement", "account_management"],
        },
        "limitations": [
            "20 stratified cases, not the example's 400-case Cartesian expansion.",
            "Follow-ups are generated expectations; current evaluator uses the opening request, not a multi-turn customer simulator.",
            "Persona/tier metadata describes wording; the current service's authoritative tier remains fixture-bound.",
            "Synthetic language has structural/PII-pattern validation, not a genuine human expert quality review.",
            "Out-of-policy escalation can complete the support task without pretending the requested refund was granted.",
        ],
    }
    with rows_path.open("x") as stream:
        stream.write(payload)
    with manifest_path.open("x") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return {"dataset": str(rows_path), "cases": len(output_rows), "sha256": manifest["dataset_sha256"]}


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
