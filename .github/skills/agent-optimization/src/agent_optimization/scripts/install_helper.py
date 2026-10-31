"""Generate the bounded `./opt` helper and its draft module into one private workspace.

`generate` is what workspace initialization calls. `install_helper` is the operator path for a
workspace that already exists and whose live process still runs an older generator: it proves the
directory is an initialized session, reads the installed helper's request target with `ast` rather
than importing it, refuses any retarget, and writes the two files atomically with a digest receipt.
It never reads, requests or copies the session's credentials.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import sys
from pathlib import Path

HELPER = '''#!/usr/bin/python3
import json, sys, urllib.request
from pathlib import Path
from optimization_draft import draft_operation, record_probe_rejection
workspace = Path(__file__).resolve().parent
allowed = {"draft", "describe", "capabilities", "query", "probe", "publish", "tune", "evaluate", "wait", "feedback", "tools", "detector", "knowledge", "finish"}
if len(sys.argv) < 2 or sys.argv[1] not in allowed:
    raise SystemExit("Usage: ./opt draft|describe|capabilities|query|probe|publish|tune|evaluate|wait|feedback|tools|detector|knowledge|finish '[JSON object]'")
payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
if not isinstance(payload, dict): raise SystemExit("Expected a JSON object")
fields = payload.pop("fields", None)
if fields is not None and (sys.argv[1] != "feedback" or not isinstance(fields, list)
        or not fields or len(fields) > 12 or any(not isinstance(field, str) for field in fields)):
    raise SystemExit("fields requires 1-12 feedback field names")
payload = draft_operation(workspace, sys.argv[1], payload)
if sys.argv[1] == "draft":
    print(json.dumps(payload)); raise SystemExit(0)
access = json.loads((workspace.parent / "task-access.json").read_text())
payload.update(access)
def call(action):
    request = urllib.request.Request(BASE + "/" + action, data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json", "X-Copilot-Terminal":"1", "Origin":ORIGIN})
    with urllib.request.urlopen(request, timeout=660) as response:
        return json.loads(response.read())
def feedback_view(result):
    if fields is not None:
        if any(field not in result for field in fields):
            raise SystemExit("Unknown feedback field")
        return {field: result[field] for field in fields}
    if not result.get("stage_counts"):
        return result
    selected = {field: result.get(field) for field in (
        "experiment_id", "version", "version_status", "status", "training_run_id", "evaluation_id")}
    samples, grades = [], set()
    for case in result.get("development_failures", []):
        if case.get("expected") in grades:
            continue
        grades.add(case.get("expected"))
        samples.append({field: case.get(field) for field in ("case_id", "expected", "predicted", "correct")})
    selected["development_examples"] = samples
    selected["agent_configuration"] = result.get("agent_configuration")
    selected["latest_operator_guidance"] = next(iter(result.get("operator_guidance", [])[::-1]), None)
    selected.update({field: result.get(field) for field in (
        "stage", "cases_finished", "case_count", "stage_counts", "situation_detector_version",
        "knowledge_access", "limits", "lever_coverage", "exploration_coverage")})
    for stage in ("training_metrics", "evaluation_metrics"):
        metrics = result.get(stage)
        selected[stage] = ({field: metrics[field] for field in (
            "macro_f1", "accuracy", "case_count", "error_rate", "mean_ms", "p95_ms") if field in metrics}
            if isinstance(metrics, dict) else metrics)
    selected["available_fields"] = list(result)
    selected["more"] = 'Read a full section with ./opt feedback {"version":N,"fields":["training_audit"]}; full training_metrics, evaluation_metrics, operator_guidance, versions and development_failures remain available.'
    return selected
def existing_stage(feedback, action):
    return (feedback.get("version") == payload["version"] and feedback.get("stage_counts")
            and (feedback.get("training_run_id" if action == "tune" else "evaluation_id")
                 or feedback.get("version_status") in {"running", "tuning"}))
def reuse_stage(feedback):
    print(json.dumps({**feedback_view(feedback), "stage_reused": True,
                      "continuation": "Existing stage retained. Use wait for running work; only an operator may request a recorded retry."}))
    raise SystemExit(0)
try:
    action = sys.argv[1]
    if action in {"tune", "evaluate"}:
        if type(payload.get("version")) is not int or payload["version"] < 1:
            raise SystemExit("A saved positive integer version is required")
        feedback = call("feedback")
        if feedback.get("version") != payload["version"]:
            raise SystemExit("Requested version is not the returned saved version")
        if existing_stage(feedback, action):
            reuse_stage(feedback)
    result = call(action)
    print(json.dumps(feedback_view(result) if action == "feedback" else result))
except urllib.error.HTTPError as error:
    if sys.argv[1] == "probe":
        record_probe_rejection(workspace, payload, error.code)
    if sys.argv[1] in {"tune", "evaluate"} and error.code in {400, 409}:
        try:
            feedback = call("feedback")
        except urllib.error.HTTPError:
            feedback = {}
        if existing_stage(feedback, sys.argv[1]):
            reuse_stage(feedback)
    print(error.read().decode()); raise SystemExit(1)
'''

DRAFT_SOURCE = Path(__file__).resolve().with_name("draft_payload.py")
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SESSION = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^[0-9a-f]{32}$")
LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:[0-9]+)?$")
DEFAULT_API_PATH = "/api/optimization/terminal"


def render(origin: str, api_path: str) -> str:
    return (HELPER.replace("BASE +", repr(origin.rstrip("/") + api_path) + " +")
            .replace('"Origin":ORIGIN', '"Origin":' + repr(origin.rstrip("/"))))


def helper_targets(source: str):
    """The request URL and Origin an installed helper names, read without executing it."""
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Request" and node.args):
            continue
        base = node.args[0]
        while isinstance(base, ast.BinOp):
            base = base.left
        origin = None
        for keyword in node.keywords:
            if keyword.arg == "headers" and isinstance(keyword.value, ast.Dict):
                for key, value in zip(keyword.value.keys, keyword.value.values):
                    if isinstance(key, ast.Constant) and key.value == "Origin":
                        origin = value
        if isinstance(base, ast.Constant) and isinstance(origin, ast.Constant):
            return base.value, origin.value
    raise ValueError("Installed helper does not name one literal request target")


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def write(path: Path, content: str, mode: int) -> str:
    if path.is_symlink():
        raise ValueError(f"{path.name} is a symbolic link")
    staged = path.with_name(path.name + ".install")
    staged.unlink(missing_ok=True)
    with os.fdopen(os.open(staged, os.O_CREAT | os.O_WRONLY | os.O_EXCL | os.O_NOFOLLOW, mode), "w") as handle:
        handle.write(content)
    os.chmod(staged, mode)
    os.replace(staged, path)
    return hashlib.sha256(content.encode()).hexdigest()


def generate(workspace, origin: str, api_path: str) -> dict:
    """Write the two helper files. Used by workspace initialization and by the operator path."""
    workspace = Path(workspace)
    content = render(origin, api_path)
    compile(content, "opt", "exec")
    return {"draft_digest": write(workspace / "optimization_draft.py", DRAFT_SOURCE.read_text(), 0o400),
            "helper_digest": write(workspace / "opt", content, 0o500)}


def install_helper(workspace, origin: str, api_path: str = DEFAULT_API_PATH) -> dict:
    workspace = Path(workspace).resolve()
    origin = origin.rstrip("/")
    if not LOOPBACK.match(origin):
        raise ValueError("Origin must be a loopback address with no credentials or query string")
    if workspace.name != "workspace" or not SESSION.match(workspace.parent.name):
        raise ValueError("Expected an initialized <session-uuid>/workspace directory")
    if workspace == PACKAGE_ROOT or PACKAGE_ROOT in workspace.parents:
        raise ValueError("Refusing to install inside the runtime package")
    helper, draft, task = workspace / "opt", workspace / "optimization_draft.py", workspace / "TASK.md"
    for path in (helper, draft, task):
        if path.is_symlink():
            raise ValueError(f"{path.name} is a symbolic link")
    if not (helper.is_file() and task.is_file()):
        raise ValueError("Workspace has no initialized helper and TASK.md to replace")
    installed = helper_targets(helper.read_text())
    if installed != (origin + api_path, origin):
        raise ValueError(f"Installed helper targets {installed[0]} from {installed[1]}; refusing to retarget")
    receipt = {"workspace": str(workspace), "session": workspace.parent.name, "origin": origin,
               "api_path": api_path, "helper_before": digest(helper), "draft_before": digest(draft)}
    written = generate(workspace, origin, api_path)
    receipt["draft_after"], receipt["helper_after"] = written["draft_digest"], written["helper_digest"]
    if (receipt["draft_after"], receipt["helper_after"]) != (digest(draft), digest(helper)):
        raise ValueError("Read-back digest does not match what was written")
    receipt["unchanged"] = (receipt["helper_before"] == receipt["helper_after"]
                            and receipt["draft_before"] == receipt["draft_after"])
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Install the current optimization helper into one existing private workspace")
    parser.add_argument("workspace", help="an existing <session-uuid>/workspace directory outside the runtime package")
    parser.add_argument("--url", required=True, help="the loopback origin the installed helper already targets")
    parser.add_argument("--api-path", default=DEFAULT_API_PATH)
    arguments = parser.parse_args(argv)
    try:
        receipt = install_helper(arguments.workspace, arguments.url, arguments.api_path)
    except ValueError as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2
    for name, value in receipt.items():
        print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
