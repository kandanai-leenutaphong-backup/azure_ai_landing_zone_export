from __future__ import annotations

import math
import statistics
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context

from .profile import OptimizationProfile
from .workflow import detect, knowledge_arguments


def score(cases: list[dict], elapsed_ms: float, grades: Sequence[str]) -> dict:
    per_class = {}
    for grade in grades:
        correct = sum(case["expected"] == grade and case["predicted"] == grade for case in cases)
        predicted = sum(case["predicted"] == grade for case in cases)
        support = sum(case["expected"] == grade for case in cases)
        precision = correct / predicted if predicted else 0.0
        recall = correct / support if support else 0.0
        per_class[grade] = {"precision": precision, "recall": recall,
                            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                            "support": support, "tp": correct, "fp": predicted - correct, "fn": support - correct,
                            "tn": len(cases) - support - predicted + correct}
    durations = sorted(case["elapsed_ms"] for case in cases)
    count = len(cases)
    metrics = {"macro_f1": sum(item["f1"] for item in per_class.values()) / len(grades),
               "accuracy": sum(case["correct"] for case in cases) / count if count else 0.0,
               "median_ms": statistics.median(durations) if durations else 0.0,
               "mean_ms": statistics.mean(durations) if durations else 0.0,
               "p95_ms": durations[max(0, math.ceil(count * .95) - 1)] if durations else 0.0,
               "elapsed_ms": elapsed_ms, "error_rate": sum(bool(case.get("error")) for case in cases) / count if count else 0.0,
               "case_count": count, "per_class": per_class}
    metrics["macro_precision"] = statistics.mean(item["precision"] for item in per_class.values())
    metrics["macro_recall"] = statistics.mean(item["recall"] for item in per_class.values())
    metrics["weighted_f1"] = sum(item["f1"] * item["support"] for item in per_class.values()) / count if count else 0.0
    metrics["confusion_matrix"] = {grade: {predicted: sum(case["expected"] == grade and (case["predicted"] or "Error") == predicted for case in cases)
                                          for predicted in (*grades, "Error")} for grade in grades}
    for split in ("development", "validation"):
        subset = [case for case in cases if case.get("split") == split]
        if subset and len(subset) != len(cases):
            metrics[f"{split}_macro_f1"] = score(subset, 0, grades)["macro_f1"]
        else:
            metrics[f"{split}_macro_f1"] = metrics["macro_f1"]
    return metrics


class GradeEvaluator:
    def __init__(self, dataset, predict: Callable[[str, dict, str], dict], profile: OptimizationProfile, *, knowledge_search=None) -> None:
        self.dataset = dataset
        self.predict = predict
        self.profile = profile
        self.knowledge_search = knowledge_search

    def run(self, candidate: dict, tools: list[dict], cases: list[dict], cancelled: Callable[[], bool],
            progress: Callable[[dict], None], *, workers: int = 1, capture: bool = False) -> tuple[list[dict], dict]:
        started = time.perf_counter()

        def evaluate_case(case):
            if cancelled():
                raise InterruptedError("Experiment cancelled")
            before = time.perf_counter()
            predicted, rationale, error = None, "", ""
            evidence = {"time_window": {"start": case["start_time"], "end": case["end_time"]}, "tools": []}
            answer = None
            model_call_attempted = False
            tool_calls = 0
            error_code = "detection_failed"
            try:
                if candidate.get("situation_detector_version") is not None:
                    evidence["situation_detector"] = detect(self.dataset, case["case_id"], candidate["_detector"], evidence["time_window"])
                    if not evidence["situation_detector"]["situations"]:
                        error_code = "no_situation"
                        raise ValueError("No situation proposed; incident remains a scored detection miss")
                for tool in tools:
                    error_code = "tool_failed"
                    tool_name = tool["name"]
                    tool_scope = {**evidence["time_window"], "windowed": True} if candidate.get("process_contract") else evidence["time_window"]
                    tool_calls += 1
                    tool_result = self.dataset.run_tool(case["case_id"], tool, tool_scope)
                    evidence["tools"].append({"name": tool_name, "result": tool_result})
                if candidate.get("knowledge_access"):
                    error_code = "knowledge_unavailable"
                    if self.knowledge_search is None:
                        raise ValueError("Configured knowledge tool is unavailable")
                    error_code = "knowledge_failed"
                    situations = evidence["situation_detector"]["situations"]
                    techniques = sorted({technique for situation in situations for technique in situation["technique_ids"]})[:16]
                    arguments = knowledge_arguments({"question": " ".join(situation["name"] + " " + " ".join(situation["facts"]) for situation in situations)[:2000],
                                                     "technique_ids": techniques}, self.profile.knowledge_behaviour_classes)
                    evidence["knowledge"] = {"tool": self.profile.knowledge_tool, "arguments": arguments,
                                              "result": self.knowledge_search(arguments)}
                error_code = "prediction_failed"
                prompt, model = candidate["system_prompt"], candidate["model"]
                model_call_attempted = True
                answer = self.predict(prompt, evidence, model)
                error_code = "invalid_grade"
                if answer.get("grade") not in self.profile.grades:
                    raise ValueError("Model did not return an allowed incident grade")
                if "situation_detector" in evidence:
                    error_code = "invalid_diagnosis"
                    if not isinstance(answer.get("diagnosis"), str) or not answer["diagnosis"] or len(answer["diagnosis"]) > 4000:
                        raise ValueError("Workflow response requires a bounded evidence-grounded diagnosis")
                    for field in ("proposed_actions", "citations"):
                        error_code = f"invalid_{field}"
                        if not isinstance(answer.get(field), list) or len(answer[field]) > 8 or any(not isinstance(value, str) or len(value) > 1000 for value in answer[field]):
                            raise ValueError("Workflow actions and citations must be bounded string lists")
                    error_code = "invalid_citations"
                    documents = evidence.get("knowledge", {}).get("result", {}).get("rows", [])
                    allowed_citations = {str(document.get(key)) for document in documents if isinstance(document, dict) for key in ("doc_id", "path") if document.get(key)}
                    if set(answer["citations"]) - allowed_citations:
                        raise ValueError("Workflow citations must name returned knowledge documents")
                error_code = "invalid_rationale"
                rationale = str(answer.get("rationale", ""))[:2000]
                predicted = answer["grade"]
            except Exception:
                error = error_code
            result = {**case, "predicted": predicted, "correct": predicted == case["expected"],
                      "elapsed_ms": round((time.perf_counter() - before) * 1000, 3),
                      "rationale": rationale, "error": error, "tool_calls": tool_calls}
            if candidate.get("situation_detector_version") is not None:
                result.update(situation_detector_version=candidate["situation_detector_version"],
                              situation_count=len(evidence.get("situation_detector", {}).get("situations", [])), actions_executed=False)
            if capture:
                result["transcript"] = {"request": self.profile.model_request(candidate["system_prompt"], evidence, candidate["model"]),
                                        "evidence": evidence, "response": answer, "error": error,
                                        "model_call_attempted": model_call_attempted,
                                        "tool_ids": [tool.get("id") for tool in tools]}
            return result

        results = []
        if workers == 1:
            for case in cases:
                result = evaluate_case(case)
                results.append(result)
                progress(result)
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="optimization-case") as pool:
                pending = {pool.submit(copy_context().run, evaluate_case, case): index for index, case in enumerate(cases)}
                completed = {}
                for future in as_completed(pending):
                    result = future.result()
                    completed[pending[future]] = result
                    progress(result)
                results = [completed[index] for index in range(len(cases))]
        return results, score(results, round((time.perf_counter() - started) * 1000, 3), self.profile.grades)


def audit_results(cases: list[dict], grades: Sequence[str]) -> dict:
    audits = {}
    for split in ("development", "validation", "final"):
        selected = [case for case in cases if case["split"] == split]
        if not selected:
            continue
        metrics = score(selected, sum(case["elapsed_ms"] for case in selected), grades)
        bands = {}
        for band in ("sparse", "ordinary", "dense", "large"):
            subset = [case for case in selected if case.get("evidence_band") == band]
            if subset:
                bands[band] = score(subset, sum(case["elapsed_ms"] for case in subset), grades)
        confusions = [{"actual": actual, "predicted": predicted, "count": count}
                      for actual, predictions in metrics["confusion_matrix"].items()
                      for predicted, count in predictions.items() if actual != predicted and count]
        audits[split] = {"metrics": metrics, "evidence_bands": bands,
                         "confusions": sorted(confusions, key=lambda item: -item["count"]),
                         "errors": sum(bool(case.get("error")) for case in selected)}
    return audits