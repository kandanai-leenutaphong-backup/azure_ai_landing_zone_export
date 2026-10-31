import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path


FIELDS = frozenset({"name", "parent_version", "rationale", "system_prompt", "tools", "situation_detector", "knowledge_access", "improvements", "design_audit"})
MAX_BYTES = 65536


def encoded(value):
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(content.encode()) > MAX_BYTES:
        raise ValueError("Draft exceeds 64 KiB; use compact evidence contracts")
    return content


def merge(target, patch, depth=0):
    if depth > 12:
        raise ValueError("Draft nesting exceeds 12 levels")
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value, depth + 1)
        else:
            target[key] = copy.deepcopy(value)


def record_probe_rejection(workspace, payload, status):
    proposal = payload.get("proposal")
    proposal = proposal if isinstance(proposal, dict) else {}
    audit = proposal.get("design_audit")
    audit = audit if isinstance(audit, dict) else {}
    tools = proposal.get("tools")
    tools = tools if isinstance(tools, list) else []
    record = {"http_status": status, "case_ids": payload.get("case_ids"),
              "parent_version": proposal.get("parent_version"),
              "parent_training_run_id": audit.get("parent_training_run_id"),
              "tool_ids": [tool.get("id") for tool in tools if isinstance(tool, dict)]}
    content = encoded(record)
    target = Path(workspace) / "last-probe-rejection.json"
    if target.is_symlink():
        raise ValueError("Probe rejection path cannot be a symbolic link")
    with os.fdopen(os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as saved:
        saved.write(content)


def draft_operation(workspace, action, payload):
    if action not in {"draft", "probe"} or (action == "probe" and payload.get("draft") is not True):
        return payload
    workspace = Path(workspace)
    target = workspace / "proposal-draft.json"
    lock = workspace / ".proposal-draft.lock"
    if target.is_symlink() or lock.is_symlink():
        raise ValueError("Draft paths cannot be symbolic links")
    with os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        draft = {}
        if target.exists():
            if target.stat().st_size > MAX_BYTES:
                raise ValueError("Draft exceeds 64 KiB")
            with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "r") as saved:
                draft = json.load(saved)
            if not isinstance(draft, dict) or set(draft) - FIELDS:
                raise ValueError("Invalid saved proposal draft")
        if action == "probe":
            if set(payload) != {"draft", "case_ids"} or not draft:
                raise ValueError("Probe a nonempty draft with draft:true and case_ids only")
            encoded(draft)
            return {"proposal": draft, "case_ids": payload["case_ids"]}
        if set(payload) - {"reset", "patch", "append_tool", "show"} or type(payload.get("reset", False)) is not bool:
            raise ValueError("Draft accepts reset, patch, append_tool and show only")
        if payload.get("reset"):
            draft = {}
        patch = payload.get("patch", {})
        if not isinstance(patch, dict) or set(patch) - FIELDS:
            raise ValueError("Draft patch contains unknown proposal fields")
        merge(draft, patch)
        if "append_tool" in payload:
            tool = payload["append_tool"]
            if not isinstance(tool, dict) or not isinstance(draft.setdefault("tools", []), list):
                raise ValueError("append_tool requires a tool object and tools list")
            draft["tools"].append(tool)
        if "tools" in draft and (not isinstance(draft["tools"], list) or len(draft["tools"]) > 5):
            raise ValueError("Draft accepts at most five tools")
        content = encoded(draft)
        with os.fdopen(os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as saved:
            saved.write(content)
        result = {"draft_digest": hashlib.sha256(content.encode()).hexdigest(), "bytes": len(content.encode()),
                  "fields": sorted(draft), "tools": [tool.get("id", tool.get("name")) for tool in draft.get("tools", []) if isinstance(tool, dict)]}
        if payload.get("show"):
            field = payload["show"]
            if field not in FIELDS:
                raise ValueError("show requires one proposal field name")
            result["value"] = draft.get(field)
        return result