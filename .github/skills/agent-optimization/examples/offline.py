"""Temporary synthetic ledger, measured without a model or external service."""

import json
import tempfile
from pathlib import Path

from agent_optimization import OptimizationProfile, OptimizationService


class Dataset:
    profile_digest = "synthetic-example-v1"

    def describe(self):
        return {"dataset_id": "synthetic-example"}

    def cases(self):
        return [{"case_id": "a" * 16, "expected": "accept", "split": "development",
                 "start_time": "2024-01-01", "end_time": "2024-01-02"}]

    def run_tool(self, case_id, tool, scope=None):
        return {"rows": [["synthetic observation"]]}


def authorize(caller):
    if caller != "example-owner":
        raise PermissionError("Caller is not the example owner")
    return "example-owner"


def predict(prompt, evidence, model):
    assert "expected" not in json.dumps(evidence)
    return {"grade": "accept", "rationale": "Synthetic fixture, not model inference"}


def main():
    profile = OptimizationProfile(
        grades=("accept", "review"), scorer_version="synthetic-macro-f1-v1",
        tool_runtime="synthetic-tool-v1", tool_families=("sampling",), objective="Synthetic triage",
        baseline_proposal={"name": "Control", "system_prompt": "Use only evidence", "rationale": "Fixture",
                           "parent_version": None, "tools": [{"name": "observations", "description": "Read fixture",
                           "code": "def run(ctx):\n    return {'rows': []}\n", "queries": "Fixture rows",
                           "returns": "Rows", "logic": "No external execution"}]},
        model_request=lambda prompt, evidence, model: {"model": model, "instructions": prompt, "input": json.dumps(evidence)},
        runtime={"tool_runtime": "synthetic-tool-v1"},
    )
    with tempfile.TemporaryDirectory(prefix="optimization-example-") as temporary:
        service = OptimizationService(Dataset(), Path(temporary), "synthetic-model", predict,
                                      authorize=authorize, profile=profile)
        try:
            experiment = service.create("example-owner", "Offline fixture")
            service.futures[experiment["id"]].result(timeout=10)
            result = service.get("example-owner", experiment["id"])
            assert result["versions"][0]["evaluations"][-1]["status"] == "completed"
            try:
                service.get("other", experiment["id"])
            except PermissionError:
                pass
            else:
                raise AssertionError("Foreign owner was admitted")
            print("PASS synthetic ledger: completed read-back, label isolation, owner refusal")
        finally:
            service.close()


if __name__ == "__main__":
    main()