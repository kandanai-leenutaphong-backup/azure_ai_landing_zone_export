#!/usr/bin/env python3
"""Architecture fitness functions for the agent harness.

Structural, relational, directional and capability checks over `.github/` and the installed
notebook. Live checks only by default. `--self-test` additionally copies the tree into a
temporary directory, breaks one rule at a time, and asserts the matching check fails — the
checker's own tests, not a gate on the repository. Live files are never mutated.
Run: python3 tests/fitness.py --root /path/to/legacy-harness-project [--self-test]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from repository_inspection import architecture

REPO = Path.cwd()


def notebook_rel(root: Path) -> str:
    try:
        config = json.loads((root / ".agent-harness.json").read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return "docs/notebook"
    return str(config.get("notebook_root") or "docs/notebook").strip("/")


NOTEBOOK_REL = notebook_rel(REPO)
WRITER_AGENTS = {
    "general-overseer",
    "general-orchestrator",
    "developer",
    "frontend-developer",
    "documentation_curator",
}
# Present only when the module that provides them is enabled.
OPTIONAL_AGENTS = {"hyperframes-motion-smith"}
CARTOGRAPHER = "architecture-cartographer"
OVERSEER = "general-overseer"
CARTOGRAPHER_TOOLS = {"read", "edit", "search", "execute"}
POLICY_FILES = (".github/skills/investigation-notebook/SKILL.md",
                ".github/skills/investigation-notebook/references/agent-stanza.md",
                ".github/instructions/investigation-notebook.instructions.md")
# The ceremony this harness removed: no file may reintroduce it as a path.
FORBIDDEN_PATHS = (".github/hooks", ".github/work-orders", ".github/ISSUE_TEMPLATE",
                   ".github/instructions/ticketing-hook.instructions.md",
                   ".github/instructions/autonomous-work.instructions.md")
SKILL_LINK_RE = re.compile(r"\]\(\.\./skills/([a-z0-9-]+)/SKILL\.md\)")
IGNORE = shutil.ignore_patterns("__pycache__", "notes", "drafts", "*.sqlite3")

checks = 0
failures: list[str] = []

def check(condition: bool, label: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(label)

def frontmatter(path: Path) -> dict[str, str]:
    """Parse the leading `---` fenced key/value block of an agent definition."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    fields: dict[str, str] = {}
    key = ""
    for line in text.split("\n---\n", 1)[0][4:].splitlines():
        if re.match(r"^[a-z-]+:", line):
            key, _, value = line.partition(":")
            fields[key] = value.strip()
        elif key:
            fields[key] += " " + line.strip()
    return fields

def listed(value: str) -> list[str]:
    inner = value.strip().removeprefix("[").removesuffix("]")
    return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]

def agents_of(root: Path) -> dict[str, dict[str, str]]:
    return {p.name.removesuffix(".agent.md"): frontmatter(p)
            for p in sorted((root / ".github/agents").glob("*.agent.md"))}

def notebook_parity(root: Path) -> list[str]:
    bad = []
    packaged = root / ".github/skills/investigation-notebook/mechanism/notebook.py"
    installed = root / NOTEBOOK_REL / "notebook.py"
    if not (packaged.exists() and installed.exists()):
        bad.append("notebook.py missing from mechanism or installation")
    elif packaged.read_bytes() != installed.read_bytes():
        bad.append("notebook.py drifted between mechanism and installation")

    # The schema is scaffolded once, so `system` is the project's to extend; every other
    # axis must still match the mechanism or the engine and its registry have diverged.
    def axes(path: Path) -> dict[str, Any] | None:
        try:
            properties = json.loads(path.read_text(encoding="utf-8"))["properties"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return None
        return {k: v for k, v in properties.items() if k != "system"}

    packaged_schema = axes(root / ".github/skills/investigation-notebook/mechanism/note.schema.json")
    installed_schema = axes(root / NOTEBOOK_REL / "note.schema.json")
    if packaged_schema is None or installed_schema is None:
        bad.append("note.schema.json missing or unreadable in mechanism or installation")
    elif packaged_schema != installed_schema:
        bad.append("note.schema.json drifted outside the project-owned system vocabulary")
    return bad

def taxonomy_registered(root: Path) -> list[str]:
    try:
        enum = json.loads((root / NOTEBOOK_REL / "note.schema.json")
                          .read_text(encoding="utf-8"))["properties"]["type"]["enum"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return ["type enum unreadable from the installed schema"]
    bad = [f"type enum omits {k}" for k in ("principle", "architecture", "work-issue")
           if k not in enum]
    for rel in POLICY_FILES:
        if not (root / rel).is_file():
            bad.append(f"{rel} is missing; the notebook taxonomy has no documented authority")
    return bad

def agent_definitions(root: Path) -> list[str]:
    defined = agents_of(root)
    bad = [f"{name}: frontmatter name, parse, or tools declaration is wrong"
           for name, fields in defined.items()
           if fields.get("name") != name or "tools" not in fields]
    for required in (CARTOGRAPHER, OVERSEER):
        if required not in defined:
            bad.append(f"{required} is not defined")
    return bad

def roster_resolves(root: Path) -> list[str]:
    defined = agents_of(root)
    bad = [f"{name}: rosters undefined agent {ref}"
           for name, fields in defined.items()
           for ref in listed(fields.get("agents", "[]")) if ref not in defined]
    if CARTOGRAPHER not in listed(defined.get("general-orchestrator", {}).get("agents", "[]")):
        bad.append(f"general-orchestrator does not roster {CARTOGRAPHER}")
    if listed(defined.get(OVERSEER, {}).get("agents", "[]")) != ["general-orchestrator"]:
        bad.append("general-overseer must roster only general-orchestrator")
    if OVERSEER in listed(defined.get("general-orchestrator", {}).get("agents", "[]")):
        bad.append("general-orchestrator must not roster general-overseer")
    return bad

def skills_resolve(root: Path) -> list[str]:
    return [f"{path.name}: links missing skill {skill}"
            for path in sorted((root / ".github/agents").glob("*.agent.md"))
            for skill in SKILL_LINK_RE.findall(path.read_text(encoding="utf-8"))
            if not (root / ".github/skills" / skill / "SKILL.md").exists()]

def capability_boundaries(root: Path) -> list[str]:
    bad = []
    for name, fields in agents_of(root).items():
        tools = set(listed(fields.get("tools", "[]")))
        body = (root / ".github/agents" / f"{name}.agent.md").read_text(encoding="utf-8")
        if any(tool.startswith("github-issues") for tool in tools):
            bad.append(f"{name}: declares a removed issue tool")
        if "edit" in tools and name not in WRITER_AGENTS | OPTIONAL_AGENTS and name != CARTOGRAPHER:
            bad.append(f"{name}: declares edit outside the writer roster")
        if "Read only" in body and "edit" in tools:
            bad.append(f"{name}: declares itself read only but holds edit")
        if name == CARTOGRAPHER and tools != CARTOGRAPHER_TOOLS:
            bad.append(f"{name}: tools differ from its narrow status-writer contract")
    return bad

def harness_files(root: Path) -> list[str]:
    """The deleted ceremony stays deleted."""
    return [f"{rel}: the removed ceremony path exists again"
            for rel in FORBIDDEN_PATHS if (root / rel).exists()]

def project_boundaries(root: Path) -> list[str]:
    """Advisory until the project declares boundaries, then a gate."""
    try:
        result = architecture.check(root)
    except architecture.ArchError as error:
        return [f"architecture.json is unusable: {error}"]
    return [f"{v['principle']}: {v['where']}: {v['detail']}" for v in result["violations"]]


SECRET_ASSIGNMENT = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*(?:PASSWORD|SECRET|TOKEN|APIKEY|API_KEY|CONNECTION_STRING"
    r"|ACCOUNT_KEY|PRIVATE_KEY))\s*=\s*(\S+)", re.M)


def deployment_runbook(root: Path) -> list[str]:
    """A project that deploys must do it from one documented, secret-free entry point."""
    deploy = root / "deploy"
    if not deploy.is_dir():
        return []
    bad = []
    entry = deploy / "deploy.sh"
    if not entry.is_file():
        bad.append("deploy/ exists without deploy/deploy.sh, the single entry point")
    elif not os.access(entry, os.X_OK):
        bad.append("deploy/deploy.sh is not executable")
    if not (deploy / "README.md").is_file():
        bad.append("deploy/ has no README.md holding the sequence and the failure playbook")
    if not (deploy / "env" / "example.env").is_file():
        bad.append("deploy/env/example.env is missing, so targets have no documented template")
    for path in sorted(deploy.rglob("*")):
        if not path.is_file() or path.suffix in {".png", ".jpg", ".zip"}:
            continue
        for name, value in SECRET_ASSIGNMENT.findall(path.read_text(encoding="utf-8", errors="ignore")):
            if value.startswith(("$", "'$", '"$', "@", "<")) or value in {'""', "''"}:
                continue
            bad.append(f"{path.relative_to(root)}: {name} carries a literal value; secrets never enter the repository")
    return bad


def skills_indexed(root: Path) -> list[str]:
    """An index that can drift is worse than none, because it is read instead of the tree.

    Module-supplied skills are exempt: the index is core's, and core cannot know what an
    optional module adds."""
    skills_dir = root / ".github/skills"
    index = skills_dir / "README.md"
    if not index.is_file():
        return ["skills/README.md is missing; the index is what makes the skill set selectable"]
    manifest = json.loads((root / ".github/.harness-manifest.json").read_text(encoding="utf-8")) \
        if (root / ".github/.harness-manifest.json").is_file() else {}
    from_modules = {rel.split("/")[2] for rel in manifest.get("module_files", [])
                    if rel.startswith(".github/skills/")}
    text = index.read_text(encoding="utf-8")
    present = {p.name for p in skills_dir.iterdir() if p.is_dir()} - from_modules
    listed = set(re.findall(r"\]\(([a-z0-9-]+)/SKILL\.md\)", text))
    return ([f"skills/README.md omits {name}" for name in sorted(present - listed)]
            + [f"skills/README.md lists {name}, which does not exist"
               for name in sorted(listed - present)])


CHECKS = (notebook_parity, taxonomy_registered, agent_definitions, roster_resolves,
          skills_resolve, capability_boundaries, harness_files,
          project_boundaries, deployment_runbook, skills_indexed)

def fixture(tmp: Path, label: str) -> Path:
    root = tmp / label
    root.mkdir()
    shutil.copytree(REPO / ".github", root / ".github", ignore=IGNORE)
    shutil.copytree(REPO / NOTEBOOK_REL, root / NOTEBOOK_REL,
                    ignore=IGNORE)
    return root

def rewrite(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")

def main() -> int:
    global REPO, NOTEBOOK_REL
    parser = argparse.ArgumentParser(description="Optional audit of a legacy harness installation.")
    parser.add_argument("--root", required=True, type=Path, help="legacy harness project root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    REPO = args.root.resolve()
    if not (REPO / ".github/agents").is_dir():
        parser.error("--root must contain the legacy .github/agents installation")
    NOTEBOOK_REL = notebook_rel(REPO)
    for fn in CHECKS:
        check(not (problems := fn(REPO)), f"{fn.__name__}: " + "; ".join(problems))
    if args.self_test:
        self_test()
    print(f"{checks - len(failures)}/{checks} checks passed")
    for failure in failures:
        print(f"  FAIL  {failure}")
    return 1 if failures else 0


def self_test() -> None:
    """The checker's own tests: each check must fail on a deliberately broken copy."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        drift = fixture(tmpdir, "schema-drift")
        rewrite(drift / NOTEBOOK_REL / "note.schema.json", '"principle",\n        ', "")
        check(notebook_parity(drift) and taxonomy_registered(drift),
              "a drifted schema copy fails parity and taxonomy registration")
        breached = fixture(tmpdir, "boundary-breach")
        (breached / "src/core").mkdir(parents=True)
        (breached / "src/app").mkdir(parents=True)
        (breached / "src/core/engine.py").write_text("from src.app.main import go\n", encoding="utf-8")
        (breached / "src/app/main.py").write_text("go = 1\n", encoding="utf-8")
        (breached / "architecture.json").write_text(json.dumps({"boundaries": [
            {"name": "core", "paths": ["src/core/*"], "may_depend_on": []},
            {"name": "app", "paths": ["src/app/*"], "may_depend_on": ["core"]},
        ]}), encoding="utf-8")
        check(bool(project_boundaries(breached)),
              "a reversed dependency edge fails the boundary check")
        leaked = fixture(tmpdir, "leaked-secret")
        (leaked / "deploy/env").mkdir(parents=True)
        (leaked / "deploy/deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (leaked / "deploy/deploy.sh").chmod(0o755)
        (leaked / "deploy/README.md").write_text("# deploy\n", encoding="utf-8")
        (leaked / "deploy/env/example.env").write_text("AZURE_SUBSCRIPTION_ID=\n", encoding="utf-8")
        check(not deployment_runbook(leaked), "a clean deployment directory passes")
        (leaked / "deploy/env/dev.env").write_text("DB_PASSWORD=hunter2\n", encoding="utf-8")
        check(bool(deployment_runbook(leaked)), "a committed secret fails the deployment check")
        unindexed = fixture(tmpdir, "unindexed-skill")
        (unindexed / ".github/skills/invented-skill").mkdir(parents=True)
        (unindexed / ".github/skills/invented-skill/SKILL.md").write_text("x", encoding="utf-8")
        check(bool(skills_indexed(unindexed)), "a skill missing from the index fails the check")
        dangling = fixture(tmpdir, "dangling-agent")
        rewrite(dangling / ".github/agents/general-orchestrator.agent.md",
                "\nagents: [", "\nagents: [ghost-agent, ")
        check(roster_resolves(dangling), "a dangling roster reference fails")
        removed = fixture(tmpdir, "escalated-cartographer")
        rewrite(removed / f".github/agents/{CARTOGRAPHER}.agent.md",
            "tools: [read, edit, search, execute]",
            "tools: [read, edit, search, execute, agent]")
        check(capability_boundaries(removed),
              "an extra cartographer tool fails the narrow status-writer contract")
        revived = fixture(tmpdir, "revived-hooks")
        (revived / ".github/hooks").mkdir(parents=True, exist_ok=True)
        check(harness_files(revived), "a revived .github/hooks directory fails")
        broken = fixture(tmpdir, "missing-skill")
        shutil.rmtree(broken / ".github/skills/architecture-placement")
        check(skills_resolve(broken), "an agent linking a missing skill fails")
        unnamed = fixture(tmpdir, "bad-frontmatter")
        rewrite(unnamed / ".github/agents/solution-architect.agent.md",
                "name: solution-architect", "name: architect")
        check(agent_definitions(unnamed), "a frontmatter name mismatch fails")

if __name__ == "__main__":
    raise SystemExit(main())
