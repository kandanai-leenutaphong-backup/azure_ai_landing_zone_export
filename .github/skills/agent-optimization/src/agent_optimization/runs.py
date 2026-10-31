from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .evaluation import audit_results
from .persistence import RunSaveError, run_recovery


def measure_run(evaluator, candidate, tools, cases, record, directory: Path, cancelled, progress):
    grades = evaluator.profile.grades
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    exemplars = {}
    failures = {grade: [] for grade in grades}
    finished = 0
    with (directory / "cases.jsonl").open("x", encoding="utf-8") as output:
        def capture(result):
            nonlocal finished
            transcript = result.pop("transcript")
            retained = {**result, "transcript": transcript}
            best_key = lambda item: (not item["correct"], item["elapsed_ms"], item["case_id"])
            worst_key = lambda item: (bool(item.get("error")), not item["correct"], item["elapsed_ms"], item["case_id"])
            if "best" not in exemplars or best_key(retained) < best_key(exemplars["best"]):
                exemplars["best"] = retained
            if "worst" not in exemplars or worst_key(retained) > worst_key(exemplars["worst"]):
                exemplars["worst"] = retained
            if not result["correct"] and len(failures[result["expected"]]) < 6:
                failures[result["expected"]].append(dict(result))
            output.write(json.dumps(result, separators=(",", ":")) + "\n")
            finished += 1
            if finished % 32 == 0 or finished == len(cases):
                output.flush()
                os.fsync(output.fileno())
                progress(finished)

        try:
            results, metrics = evaluator.run(candidate, tools, cases, cancelled, capture,
                                             workers=record["workers"], capture=True)
            record.update(status="cancelled" if cancelled() else "completed", metrics=metrics,
                          audit=audit_results(results, grades), cases_finished=len(results))
        except Exception:
            stopped = cancelled()
            record.update(status="cancelled" if stopped else "failed", cases_finished=finished,
                          error="measurement_cancelled" if stopped else "measurement_failed")
        output.flush()
        os.fsync(output.fileno())
    record["completed_at"] = datetime.now(timezone.utc).isoformat()
    record["exemplars"] = {}
    for kind, result in exemplars.items():
        artifact = {"run_id": record["id"], "agent_version": candidate["version"],
                    "stage": record["stage"], "selection": kind, "case": result}
        with (directory / f"{kind}.json").open("x", encoding="utf-8") as output:
            json.dump(artifact, output)
        record["exemplars"][kind] = {key: result[key] for key in ("case_id", "correct", "expected", "predicted", "elapsed_ms", "error")}
    if record["stage"] == "training":
        record["development_failures"] = [case for grade in grades for case in failures[grade]]
    outcome = run_recovery(directory, record["id"]).commit(record["id"], record)
    if not outcome.saved:
        raise RunSaveError(outcome)
    return record