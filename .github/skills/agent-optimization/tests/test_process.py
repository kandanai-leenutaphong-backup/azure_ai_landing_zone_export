from copy import deepcopy

import pytest

from agent_optimization.process import (CREATIVE_CONTRACT, JOINT_TASK, creative_coverage,
                                                      require_creative_coverage, validate_creative_experiment,
                                                      validate_investigation_plan)


def planned_proposal():
    return {
        "tools": [{"id": "tool_existing"}, {"name": "duration_distribution"}],
        "design_audit": {"investigation_plan": {
            "version": "question-evidence-tools-v1",
            "questions": [
                {"id": "inventory", "question": "Which work items exist?", "decision": "Choose items to inspect.",
                 "data": "evidence(item_type)", "view": "Inventory table", "tool": "tool_existing", "status": "tool",
                 "limits": "Only items recorded inside this case window."},
                {"id": "duration", "question": "Which work items take longest?", "decision": "Separate routine work from delays.",
                 "data": "evidence(duration)", "view": "Duration distribution", "tool": "duration_distribution", "status": "tool",
                 "limits": "Duration does not prove the cause of a delay."},
                {"id": "dependencies", "question": "Which external dependency blocked work?", "decision": "Identify dependency owners.",
                 "data": "No dependency identifiers in this fixture", "view": "Dependency table unavailable", "tool": None,
                 "status": "unavailable", "limits": "Do not invent dependency edges from item types."},
            ],
            "code_changes": ["Add a bounded duration-distribution query."],
            "agent_changes": ["Compare inventory and duration before deciding."],
            "held_fixed": ["Parent detector, model, case windows and rubric."],
            "acceptance_checks": ["Two contrasting cases produce different duration distributions."],
        }},
    }


def test_question_led_plan_is_domain_neutral_and_does_not_mutate_the_proposal():
    proposal = planned_proposal()
    original = deepcopy(proposal)
    validate_investigation_plan(proposal)
    assert proposal == original
    validate_investigation_plan({"design_audit": {}, "tools": []})
    assert "QUESTION-LED TOOL DESIGN" in JOINT_TASK
    assert "design_audit.investigation_plan" in JOINT_TASK
    assert "does not let" in JOINT_TASK


@pytest.mark.parametrize("mutation, message", [
    (lambda plan: plan.update(version="unknown"), "record fields"),
    (lambda plan: plan.update(questions=[]), "1 to 12"),
    (lambda plan: plan["questions"][0].update(tool="unselected_tool"), "selected tool"),
    (lambda plan: plan["questions"].pop(1), "Every selected tool"),
    (lambda plan: plan["questions"][1].update(id="inventory"), "unique"),
    (lambda plan: plan["questions"][2].update(tool="tool_existing"), "cannot claim"),
    (lambda plan: plan["questions"][0].update(view=""), "1 to 600"),
    (lambda plan: plan["questions"][0].update(status="inferred"), "status"),
    (lambda plan: plan.update(code_changes="Changed code"), "code_changes"),
    (lambda plan: plan.update(held_fixed=[]), "held_fixed"),
    (lambda plan: plan.update(acceptance_checks=[]), "acceptance_checks"),
])
def test_plan_refuses_untraceable_tools_and_missing_change_controls(mutation, message):
    proposal = planned_proposal()
    mutation(proposal["design_audit"]["investigation_plan"])
    with pytest.raises(ValueError, match=message):
        validate_investigation_plan(proposal)


def test_creative_plan_requires_alternatives_and_controlled_ablation():
    proposal = planned_proposal()
    parent = {"tool_ids": ["tool_existing", "tool_removed"], "system_prompt": "Fixed interpretation",
              "situation_detector_version": 1, "knowledge_access": True}
    proposal.update(system_prompt=parent["system_prompt"], situation_detector=1, knowledge_access=True)
    with pytest.raises(ValueError, match="Creative experiment"):
        validate_creative_experiment(proposal, parent, CREATIVE_CONTRACT)
    proposal["design_audit"]["experiment"] = {
        "approach_id": "duration_first", "kind": "new-evidence",
        "mechanism": "Use a separate duration view to distinguish delays from routine work.",
        "alternatives": ["Inspect an ordered event timeline instead.", "Prioritize evidence reliability before duration."],
        "disconfirmation": "The duration view is constant across cases with different observed durations."}
    validate_creative_experiment(proposal, parent, CREATIVE_CONTRACT)
    proposal["design_audit"]["experiment"]["kind"] = "ablation"
    with pytest.raises(ValueError, match="strict subset"):
        validate_creative_experiment(proposal, parent, CREATIVE_CONTRACT)
    proposal["tools"] = [{"id": "tool_existing"}]
    proposal["design_audit"]["investigation_plan"]["questions"].pop(1)
    validate_creative_experiment(proposal, parent, CREATIVE_CONTRACT)
    proposal["system_prompt"] = "Changed interpretation"
    with pytest.raises(ValueError, match="held fixed"):
        validate_creative_experiment(proposal, parent, CREATIVE_CONTRACT)


def test_creative_coverage_counts_completed_sources_and_refuses_cosmetic_bundles():
    tools = [{"id": "tool_a", "source_digest": "source_a", "family": "inventory"},
             {"id": "tool_renamed", "source_digest": "source_a", "family": "inventory"},
             {"id": "tool_b", "source_digest": "source_b", "family": "duration"}]
    candidates = [{"status": "completed", "tool_ids": ["tool_a", "tool_b"],
                   "design_audit": {"experiment": {"approach_id": "duration", "kind": "combination"}}},
                  {"status": "completed", "tool_ids": ["tool_renamed", "tool_b"],
                   "design_audit": {"experiment": {"approach_id": "duration", "kind": "refinement"}}},
                  {"status": "tuning", "tool_ids": ["tool_a"],
                   "design_audit": {"experiment": {"approach_id": "inventory", "kind": "ablation"}}}]
    coverage = creative_coverage(candidates, tools)
    assert coverage["measured_versions"] == 2
    assert coverage["counts"] == {"approaches": 1, "tool_families": 2, "tool_sources": 2,
                                  "tool_sets": 1, "multi_tool_versions": 2, "experiment_kinds": 2}
    with pytest.raises(ValueError, match="missing ablation"):
        require_creative_coverage(coverage, CREATIVE_CONTRACT)
    require_creative_coverage({"counts": dict(CREATIVE_CONTRACT["minimums"]),
                               "kinds": ["combination", "ablation"]}, CREATIVE_CONTRACT)