"""Single specialized-judge owner for runtime, consensus and SDK batch adapters."""
from pydantic import Field, StrictInt, StrictBool
from simulation_schema import StrictResult
from settings import CRITERIA

VARIANTS = (
    "Evaluate directly against rubric and supplied evidence.",
    "First identify unsupported claims and unmet requirements, then apply identical rubric.",
    "Check final state first, then trace each candidate claim backward to supplied ground truth.",
)


class SpecializedScore(StrictResult):
    score: StrictInt = Field(ge=0, le=10)
    reasoning: str = Field(min_length=1, max_length=1000)
    missing_requirements: list[str] = Field(default_factory=list, max_length=10)


class TaskScore(SpecializedScore):
    criteria: list[StrictBool] = Field(min_length=3, max_length=3)


class SpecializedJudges:
    def __init__(self, invoke):
        """invoke(role, payload, schema) returns validated dict."""
        self.invoke = invoke

    def evaluate(self, context, consensus=False):
        results = {}
        for criterion in CRITERIA:
            schema = TaskScore if criterion == "task_completion" else SpecializedScore
            samples = [self.invoke("judge_" + criterion,
                                   {**context, "evaluation_approach": variant}, schema)
                       for variant in (VARIANTS if consensus else VARIANTS[:1])]
            scores = [s["score"] for s in samples]
            result = {"score": sum(scores) / len(scores), "spread": max(scores) - min(scores),
                      "human_review_required": max(scores) - min(scores) > 3, "samples": samples}
            if criterion == "task_completion":
                # Conservative binary consensus: all variants must evidence each requirement.
                result["criteria"] = [all(s["criteria"][i] for s in samples) for i in range(3)]
            results[criterion] = result
        return {"specialized": results, "criteria": results["task_completion"]["criteria"],
                "coherence": results["consistency"]["score"],
                "coherence_definition": "Specialized consistency judge's holistic journey-coherence score",
                "consensus": consensus,
                "model_independence": "Same gpt-4.1-mini regional deployment; prompt variants are not independent models",
                "human_review_required": any(r["human_review_required"] for r in results.values()),
                "calibration_status": "calibration_not_established", "release_ready": False}


def cohen_kappa(human, model):
    """Unweighted Cohen kappa on exact integer rubric-score categories."""
    if len(human) != len(model) or not human:
        return None
    n = len(human)
    observed = sum(a == b for a, b in zip(human, model)) / n
    expected = sum(human.count(k) * model.count(k) for k in range(11)) / (n * n)
    return (observed - expected) / (1 - expected) if expected < 1 else None


def calibrate(rows):
    for row in rows:
        for key in ("human_scores", "judge_scores"):
            if set(row[key]) != set(CRITERIA):
                raise ValueError("Each calibration row requires all four criterion scores")
            if any(type(v) is not int or not 0 <= v <= 10 for v in row[key].values()):
                raise ValueError("Calibration scores must be integers 0..10")
    count = len(rows)
    kappas = {c: cohen_kappa([r["human_scores"][c] for r in rows],
                             [r["judge_scores"][c] for r in rows]) for c in CRITERIA}
    established = 50 <= count <= 100 and all(k is not None and k > .7 for k in kappas.values())
    return {"sample_count": count, "required_sample_range": [50, 100], "threshold_exclusive": .7,
            "agreement_method": "unweighted Cohen kappa, exact integer score categories",
            "kappa": kappas, "calibration_status": "established_on_supplied_labels" if established else "calibration_not_established",
            "insufficient_sample": count < 50, "release_ready": False,
            "limitation": "Supplied labels only; no claim of representative human agreement or production readiness"}
