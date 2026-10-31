"""Host-supplied domain configuration. The component holds no label, prompt or task text."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OptimizationProfile:
    """Every domain fact the optimization process needs, supplied by its host."""

    grades: Sequence[str]
    scorer_version: str
    tool_runtime: str
    tool_families: Sequence[str]
    objective: str
    baseline_proposal: Mapping
    model_request: Callable[[str, dict, str], dict]
    runtime: Mapping
    workflow_runtime: Mapping = field(default_factory=dict)
    baseline_detector: Mapping | None = None
    joint_baseline_detector: Mapping | None = None
    workflow_contract: Mapping | None = None
    knowledge_tool: str = ""
    knowledge_behaviour_classes: frozenset[str] = frozenset()
    staged_evaluation_policy: str = ""
    smoke_evaluation_policy: str = ""
    datasource: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalTasks:
    """The CLI's task text. The process is the component's; the words are the host's."""

    task: str
    skill_name: str
    skill_description: str
    objectives: Mapping[str, str]
    contracts: Mapping[str, str]
    workflow_objective: str = ""
    joint_objective: str = ""

    def objective(self, protocol: str) -> str:
        return self.objectives.get(protocol, self.objectives["default"])

    def contract(self, protocol: str) -> str:
        return self.contracts.get(protocol, self.contracts["default"])
