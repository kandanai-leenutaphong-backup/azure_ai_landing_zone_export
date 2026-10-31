"""Explicit synthetic evaluation and offline human-label calibration."""
import argparse
from copy import deepcopy
import json
import threading
import time
from pathlib import Path
from scenarios import SCENARIOS


def jsonl(path):
    with open(path, encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


class SimulationEvaluator:
    """SDK callable, serialized to respect shared regional quota."""
    def __init__(self, service, consensus=False, result_sink=None):
        self.service, self.consensus = service, consensus
        self.result_sink = result_sink
        self.lock = threading.Lock()

    def __call__(self, *, scenario_id: str, customer_request: str | None = None, **kwargs):
        if scenario_id not in SCENARIOS:
            raise ValueError("Only immutable synthetic scenario IDs are accepted")
        with self.lock:
            # Dataset taxonomy, expected states/rubrics and arbitrary metadata are never forwarded.
            row = self.service.submit("evaluation-cli", scenario_id, consensus=self.consensus,
                                      customer_request=customer_request)
            while True:
                current = self.service.store.get("evaluation-cli", row["id"])
                if current["status"] not in ("queued", "running") and not self.service.busy.locked():
                    break
                time.sleep(.1)
            if self.result_sink is not None:
                # Parent may freeze provenance-bound raw evidence, including failed calls.
                # A sink cannot mutate the evaluator's actual outcome or local ledger.
                self.result_sink(deepcopy(current))
            if current["status"] != "completed":
                raise RuntimeError("Evaluation failed; not a passing sample")
            judge = current["judge"]
            return {"run_id": current["id"], "status": current["status"],
                    "action": current["ledger"]["action"], "state": current["ledger"]["state"],
                    "goal_index": current["goal_index"], "coherence": judge["coherence"],
                    **{c + "_score": r["score"] for c, r in judge["specialized"].items()},
                    "human_review_required": judge["human_review_required"],
                    "calibrated": False, "release_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    calibration = sub.add_parser("calibrate", help="Offline only, no model calls")
    calibration.add_argument("--data", required=True, type=Path)
    for name in ("simulate", "batch"):
        command = sub.add_parser(name)
        command.add_argument("--consensus", action="store_true")
        command.add_argument("--allow-model-calls", action="store_true", required=True)
        if name == "simulate":
            command.add_argument("--scenario-id", choices=tuple(SCENARIOS), required=True)
        else:
            command.add_argument("--data", required=True, type=Path, help="Synthetic JSONL file: scenario_id, optional customer_request and ignored offline metadata")
            command.add_argument("--max-cases", type=int, choices=range(1, 21), default=1,
                                 help="Explicit billable case limit, default one smoke case")
            command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "calibrate":
        from evaluation import calibrate
        print(json.dumps(calibrate(jsonl(args.data)), indent=2))
        return
    if args.command == "batch":
        # Inspect actual installed API before making a billable call.
        try:
            from azure.ai.evaluation import evaluate
        except ImportError:
            raise SystemExit("Optional azure-ai-evaluation SDK missing. See requirements-evaluation.txt.") from None
        import inspect
        if not {"data", "evaluators"}.issubset(inspect.signature(evaluate).parameters):
            raise SystemExit("Installed evaluate API is incompatible; no model calls made.")
        rows = jsonl(args.data)
        if not 1 <= len(rows) <= args.max_cases or any(
            r.get("scenario_id") not in SCENARIOS or
            ("customer_request" in r and (not isinstance(r["customer_request"], str) or
                                         not 1 <= len(r["customer_request"].strip()) <= 2000))
            for r in rows
        ):
            raise SystemExit("Batch requires known synthetic scenario IDs, bounded request variants, and explicit --max-cases limit.")
        output = args.output.resolve()
        root = Path(__file__).parent.resolve()
        if not output.is_relative_to(root):
            raise SystemExit("Evaluation output must remain inside application boundary.")
    from settings import Settings
    from native import NativeAgents
    from simulation import SimulationService, Store
    from telemetry import Telemetry, configure
    settings = Settings.from_env()
    provider = configure(settings)
    service = SimulationService(Store(settings.database), NativeAgents(settings), Telemetry(provider), settings.pins)
    evaluator = SimulationEvaluator(service, args.consensus)
    try:
        if args.command == "simulate":
            print(json.dumps(evaluator(scenario_id=args.scenario_id), indent=2))
        else:
            # SDK requires a file path, not an in-memory list. Callable uses same native judge owner.
            result = evaluate(data=str(args.data), evaluators={"synthetic_journey": evaluator},
                              output_path=str(output), fail_on_evaluator_errors=True)
            print(json.dumps({"metrics": result.get("metrics"), "calibrated": False,
                              "release_ready": False}, default=str, indent=2))
    finally:
        service.close()
        provider.shutdown()


if __name__ == "__main__":
    main()
