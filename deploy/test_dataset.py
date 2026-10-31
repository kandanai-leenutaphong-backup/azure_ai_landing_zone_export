from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dataset import canonical_hash
from validate_dataset import APP, validate


def test_generated_twenty_case_cohort_preserves_authoritative_ground_truth():
    result = validate()
    assert result["cases"] == 20
    assert result["calibration"] == "not_established"


@pytest.mark.parametrize("mutation", ["amount", "cohort", "contact"])
def test_rehashed_unsafe_dataset_is_still_refused(tmp_path, mutation):
    root = APP / "datasets"
    rows = [json.loads(line) for line in (root / "synthetic-customer-issues.jsonl").read_text().splitlines()]
    manifest = json.loads((root / "manifest.json").read_text())
    if mutation == "amount":
        rows[0]["ground_truth"]["expected_system_state"]["amount_sgd"] = 999
    elif mutation == "cohort":
        rows[0]["case_id"] = "not-in-the-frozen-taxonomy"
    else:
        rows[0]["customer_request"] = "Contact me at synthetic@example.com to process my return."
    rows[0]["case_sha256"] = canonical_hash({k: v for k, v in rows[0].items() if k != "case_sha256"})
    payload = "".join(json.dumps(row) + "\n" for row in rows)
    manifest["dataset_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    (tmp_path / "synthetic-customer-issues.jsonl").write_text(payload)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        validate(tmp_path)
