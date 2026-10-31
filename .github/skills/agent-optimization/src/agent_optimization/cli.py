from __future__ import annotations

import json
import threading
from pathlib import Path

from copilot_terminal import ProviderConfig, TerminalService

from .profile import TerminalTasks
from .service import OptimizationService, PROTOCOLS
from .process import CREATIVE_SKILL_PATH, JOINT_TASK, creative_task
from .scripts.install_helper import HELPER, generate

class OptimizationTerminal:
    def __init__(self, service: OptimizationService, *, cli: str, endpoint: str, model: str,
                 workspace_root: Path, token_provider, path: str, api_origin: str,
                 tasks: TerminalTasks, api_path: str) -> None:
        self.service = service
        self.tasks = tasks
        self.creative_skill_name = "creative-agent-optimization"
        self.creative_skill = CREATIVE_SKILL_PATH.read_text()
        self.api_path = api_path
        self.origin = api_origin.rstrip("/")
        self.bindings = {}
        self.owners = {}
        self.archived = {}
        self.lock = threading.RLock()
        self.terminal = TerminalService(cli, ProviderConfig(endpoint, model), workspace_root,
                                        token_provider, path=path)
        self.terminal.workspace_initializer = self.initialize
        self.terminal.allowed_executables = lambda workspace: (workspace / "opt",)
        self.terminal.operations["prepare"] = self.prepare
        for name in ("describe", "capabilities", "query", "probe", "publish", "tune", "evaluate", "wait", "feedback", "tools", "detector", "knowledge", "finish"):
            self.terminal.task_operations[name] = self.operation(name)

    def initialize(self, workspace: Path):
        generate(workspace, self.origin, self.api_path)
        skill = workspace / f".github/skills/{self.tasks.skill_name}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {self.tasks.skill_name}\ndescription: {self.tasks.skill_description}\n---\n\n" + self.tasks.task)
        creative = workspace / ".github/skills" / self.creative_skill_name
        creative.mkdir(parents=True)
        (creative / "SKILL.md").write_text(self.creative_skill)
        (workspace / "TASK.md").write_text(self.tasks.task)

    def prepare(self, workspace, payload, headers):
        owner = self.owners.get(workspace.parent.name)
        if owner is None:
            raise PermissionError("Terminal owner not found")
        experiment_id = payload.get("experiment_id", "")
        experiment = self.service.get(owner, experiment_id)
        if not experiment["versions"][0]["metrics"]:
            raise ValueError("Baseline evaluation must finish before optimization")
        if experiment["status"] in {"completed", "cancelled", "running"}:
            raise ValueError("Experiment cannot start optimization in this state")
        self.bindings[str(workspace)] = (owner, experiment_id)
        self.service.event(owner, experiment_id, "cli_started", f"Native Copilot session {workspace.parent.name}; limited helper permissions")
        objective = self.tasks.objective(experiment.get("protocol", "smoke"))
        if experiment.get("workflow"):
            objective += "\n" + self.tasks.workflow_objective
        if experiment.get("process_contract"):
            objective = JOINT_TASK + "\n" + self.creative_skill + "\n" + self.tasks.joint_objective
        if experiment.get("exploration_contract"):
            objective += creative_task(experiment["exploration_contract"])
        capabilities = self.service.capabilities(owner, experiment_id)
        (workspace / "CAPABILITIES.json").write_text(json.dumps(capabilities, indent=2))
        prompt = self.tasks.task + "\n" + objective + "\nBegin with ./opt capabilities, ./opt describe and ./opt feedback. Capability discovery distinguishes available operations from registered but inaccessible sources/tools. It grants no new access. Continue from existing generations if this is a resumed session. Do not ask the user to perform the steps."
        (workspace / "TASK.md").write_text(prompt)
        self.service.record_process_task(owner, experiment_id, prompt, workspace.parent.name, skill=self.creative_skill, capabilities=capabilities)
        return {"experiment_id": experiment_id, "prompt": prompt}

    def operation(self, action):
        def execute(workspace, payload, headers):
            binding = self.bindings.get(str(workspace))
            if binding is None:
                raise PermissionError("No experiment bound to terminal")
            owner, identifier = binding
            experiment = self.service.get(owner, identifier)
            if experiment["status"] == "cancelled":
                raise ValueError("Experiment is cancelled")
            if action == "describe":
                cases = [{key: value for key, value in case.items() if key != "expected"}
                         for case in self.service.experiment_cases(owner, identifier) if case["split"] == "development"]
                if experiment.get("protocol") in {"full-10", "joint-10", "joint-12"}:
                    offset = payload.get("offset", 0)
                    if type(offset) is not int or not 0 <= offset <= len(cases):
                        raise ValueError("Invalid development case offset")
                    cases = cases[offset:offset + 36]
                return {"dataset": self.service.dataset_info, "development_cases": cases,
                    "capabilities": self.service.capabilities(owner, identifier),
                        "profiles": self.service.dataset.profiles(), "contract": JOINT_TASK if experiment.get("process_contract") else self.tasks.contract(experiment.get("protocol", "smoke")),
                    "workflow_contract": JOINT_TASK if experiment.get("process_contract") else self.tasks.workflow_objective if experiment.get("workflow") else None,
                    "process_contract": experiment.get("process_contract"),
                    "exploration_contract": experiment.get("exploration_contract"),
                    "exploration_task": creative_task(experiment["exploration_contract"]) if experiment.get("exploration_contract") else None,
                    "stage_counts": experiment.get("stage_counts"), "workflow": experiment.get("workflow"),
                    "knowledge_reference": experiment.get("knowledge_reference"),
                        "limits": experiment.get("limits", PROTOCOLS["smoke"]), "tool_families": self.service.profile.tool_families}
            if action == "feedback":
                number = payload.get("version")
                if number is not None and (type(number) is not int or not any(version["version"] == number for version in experiment["versions"])):
                    raise ValueError("Feedback requires an existing integer version")
                result = self.service.feedback(owner, identifier, number)
                version = next(version for version in experiment["versions"] if version["version"] == result["version"])
                result["agent_configuration"] = {field: version.get(field) for field in (
                    "version", "system_prompt", "tool_ids", "situation_detector_version",
                    "situation_detector_digest", "knowledge_access")}
                return result
            if action == "capabilities":
                return self.service.capabilities(owner, identifier)
            if action == "probe":
                return self.service.probe(owner, identifier, payload.get("proposal"), payload.get("case_ids"))
            if action == "detector":
                if "case_id" in payload:
                    return self.service.test_detector(owner, identifier, payload["case_id"], payload.get("detector"))
                return {"versions": self.service.detectors(owner, identifier), "scope": experiment.get("workflow")}
            if action == "knowledge":
                arguments = {key: value for key, value in payload.items() if key not in {"session_id", "key", "task_key"}}
                return self.service.knowledge(owner, identifier, arguments)
            if action == "tools":
                tools = [tool for tool in self.service.snapshot(owner)["tools"] if tool["experiment_id"] == identifier]
                if payload.get("id"):
                    return next((tool for tool in tools if tool["id"] == payload["id"]), {"error": "Tool not found"})
                return {"tools": [{key: value for key, value in tool.items() if key not in {"code", "sql"}} for tool in tools]}
            if action == "query":
                allowed = {case["case_id"] for case in self.service.experiment_cases(owner, identifier) if case["split"] == "development"}
                case_id = payload.get("case_id")
                if case_id not in allowed:
                    raise PermissionError("Only development case queries are exposed")
                if "code" in payload:
                    return self.service.dataset.run_tool(case_id, {"code": payload["code"], "language": "python"})
                return self.service.dataset.query(case_id, payload.get("sql", ""))
            if action == "publish":
                proposal = {key: payload[key] for key in ("name", "parent_version", "rationale", "system_prompt", "tools", "design_audit", "improvements", "situation_detector", "knowledge_access", "probe_id") if key in payload}
                return self.service.publish(owner, identifier, proposal)
            if action == "tune":
                self.service.measure(owner, identifier, int(payload.get("version", 0)), "training", wait=True)
                return self.service.feedback(owner, identifier, int(payload.get("version", 0)))
            if action == "wait":
                return self.service.wait_for_run(owner, identifier)
            if action == "evaluate":
                self.service.evaluate(owner, identifier, int(payload.get("version", 0)), wait=True)
                return self.service.feedback(owner, identifier, int(payload.get("version", 0)))
            if action == "finish":
                return self.service.finish(owner, identifier)
            raise ValueError("Unknown task operation")
        return execute

    def handle(self, caller, action, headers, payload):
        self.service.authorize(caller)
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
        if action not in {"info", "start"}:
            owner = self.owners.get(session_id)
            if owner is None or self.service.identify(owner) != self.service.identify(caller):
                return 404, {"detail": "Terminal not found", "error": "not_found"}
        status, result = self.terminal.handle(action, headers, payload)
        if action == "start" and status == 201:
            self.owners[result["session_id"]] = caller
        if action == "output" and status == 200:
            try:
                session = self.terminal._lookup(payload)
            except PermissionError:
                return 404, {"detail": "Terminal not found", "error": "not_found"}
            binding = self.bindings.get(str(session.terminal.workspace))
            if binding:
                with self.lock:
                    previous = self.archived.get(session_id, 0)
                    delta = result["cursor"] - previous
                    if delta > 0:
                        trace = self.service.directory(*binding) / "terminal.log"
                        with trace.open("a", encoding="utf-8") as output:
                            output.write(result["output"][-delta:])
                        self.archived[session_id] = result["cursor"]
        if action == "stop" and status == 200:
            self.owners.pop(session_id, None)
        return status, result

    def close(self):
        self.terminal.close()

    def cancel_experiment(self, identifier):
        for workspace, (_, experiment_id) in list(self.bindings.items()):
            if experiment_id != identifier:
                continue
            session_id = Path(workspace).parent.name
            with self.terminal._lock:
                record = self.terminal._sessions.pop(session_id, None)
            if record:
                record.terminal.close()
            self.owners.pop(session_id, None)