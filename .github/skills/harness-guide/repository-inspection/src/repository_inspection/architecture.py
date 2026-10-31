#!/usr/bin/env python3
"""Check the repository against its declared architecture.

Principles are only real if something can fail on them. Reads `architecture.json` at the project
root and proves four against actual source: one owner per path, dependencies in the declared
direction, no cycles, boundary internals kept private.

Advisory by design. A repository declaring no boundaries passes: the harness does not know what
shape a project should be, only that whatever shape it declares should hold.

Usage:
    python3 scripts/arch.py --root /path/to/project
    python3 scripts/arch.py --root /path/to/project --json
    python3 scripts/arch.py --root /path/to/project --graph

`architecture.json`:

    {
      "boundaries": [
        {"name": "core",  "paths": ["src/core/**"], "may_depend_on": [],
         "public": ["src/core/index.ts"]},
        {"name": "app",   "paths": ["src/app/**"],  "may_depend_on": ["core"]}
      ],
      "aliases": {"@/": "src/"}
    }

Resolution is deliberately narrow and says so: relative imports and configured aliases resolve,
bare specifiers count as external and are ignored. An unresolvable import is reported as unknown,
never as a pass.

Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

MANIFEST_NAME = "architecture.json"

PY_SUFFIXES = (".py", ".pyi")
TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SOURCE_SUFFIXES = PY_SUFFIXES + TS_SUFFIXES
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "site-packages", ".next", ".vite", ".turbo", ".cache",
    "coverage", "playwright-report", "test-results", ".vocs", ".parcel-cache", "htmlcov",
    ".tox", "target", "out", "__snapshots__", ".ipynb_checkpoints", ".agent-harness",
}

PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*)([\w.]*)\s+import\b|import\s+([\w.]+))", re.M)
TS_IMPORT = re.compile(
    r"""(?:^|\s)(?:import|export)\s+(?:[^'"]*?\bfrom\s*)?['"]([^'"]+)['"]"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)


class ArchError(Exception):
    pass


def load_manifest(root: Path) -> dict[str, Any] | None:
    path = root / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ArchError(f"{MANIFEST_NAME} is not valid JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise ArchError(f"{MANIFEST_NAME} must be an object")
    return manifest


def boundaries_of(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    declared = manifest.get("boundaries") or []
    names = [b.get("name", "") for b in declared]
    for name in names:
        if not name:
            raise ArchError("every boundary needs a name")
    if len(set(names)) != len(names):
        raise ArchError("boundary names must be unique")
    known = set(names)
    for boundary in declared:
        for target in boundary.get("may_depend_on") or []:
            if target not in known:
                raise ArchError(
                    f"boundary {boundary['name']!r} may_depend_on unknown boundary {target!r}"
                )
    return declared


def source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in SKIP_DIRS and not entry.is_symlink():
                    stack.append(entry)
            elif entry.suffix in SOURCE_SUFFIXES:
                found.append(entry)
    return sorted(found)


def matches(rel: str, patterns: Iterable[str]) -> bool:
    # fnmatch is used deliberately: `*` crosses directory separators, so `src/core/**` and
    # `src/core/*` both mean "everything beneath". Simpler to predict than pathlib globbing.
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def owners(rel: str, boundaries: list[dict[str, Any]]) -> list[str]:
    return [b["name"] for b in boundaries if matches(rel, b.get("paths") or [])]


def resolve_python(importing: Path, dots: str, module: str, root: Path) -> Path | None:
    if dots:
        base = importing.parent
        for _ in range(len(dots) - 1):
            base = base.parent
        candidate_root = base
        parts = module.split(".") if module else []
    else:
        candidate_root = root
        parts = module.split(".")
    if not parts:
        return candidate_root if candidate_root.is_dir() else None
    target = candidate_root.joinpath(*parts)
    for candidate in (target.with_suffix(".py"), target / "__init__.py", target.with_suffix(".pyi")):
        if candidate.is_file():
            return candidate
    return None


def resolve_ts(importing: Path, specifier: str, root: Path, aliases: dict[str, str]) -> Path | None:
    if specifier.startswith("."):
        base = (importing.parent / specifier).resolve()
    else:
        for prefix, replacement in aliases.items():
            if specifier.startswith(prefix):
                base = (root / replacement / specifier[len(prefix):]).resolve()
                break
        else:
            return None  # bare specifier: a package, not a boundary
    for candidate in [base, *(base.with_suffix(s) for s in TS_SUFFIXES),
                      *(base / f"index{s}" for s in TS_SUFFIXES)]:
        if candidate.is_file():
            return candidate
    return None


def edges(root: Path, files: list[Path], aliases: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Every resolvable import as (from file, to file). Unresolvable ones are reported, not hidden."""
    found: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        if path.suffix in PY_SUFFIXES:
            for dots, module, plain in PY_IMPORT.findall(text):
                target = resolve_python(path, dots, module or plain, root)
                if target is None and dots:
                    unresolved.append(f"{rel}: relative import {dots}{module} did not resolve")
                if target is not None:
                    found.append({"from": rel, "to": target.resolve()})
        else:
            for specifier, required in TS_IMPORT.findall(text):
                spec = specifier or required
                if not spec:
                    continue
                target = resolve_ts(path, spec, root, aliases)
                if target is None and (spec.startswith(".") or any(spec.startswith(a) for a in aliases)):
                    unresolved.append(f"{rel}: import {spec!r} did not resolve")
                if target is not None:
                    found.append({"from": rel, "to": target})
    return found, unresolved


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        for neighbour in sorted(graph.get(node, ())):
            if state.get(neighbour, 0) == 0:
                visit(neighbour, stack + [neighbour])
            elif state.get(neighbour) == 1:
                start = stack.index(neighbour) if neighbour in stack else 0
                cycle = stack[start:] + [neighbour]
                key = tuple(sorted(set(cycle)))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cycle)
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            visit(node, [node])
    return cycles


def check(root: Path) -> dict[str, Any]:
    manifest = load_manifest(root)
    if manifest is None:
        return {"declared": False, "reason": f"no {MANIFEST_NAME} at the project root",
                "violations": [], "notes": []}
    boundaries = boundaries_of(manifest)
    if not boundaries:
        return {"declared": False, "reason": f"{MANIFEST_NAME} declares no boundaries",
                "violations": [], "notes": []}

    aliases: dict[str, str] = manifest.get("aliases") or {}
    files = source_files(root)
    violations: list[dict[str, str]] = []
    notes: list[str] = []

    # Principle: one owner per path.
    ownership: dict[str, list[str]] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        holders = owners(rel, boundaries)
        if len(holders) > 1:
            violations.append({"principle": "one-owner-per-path", "where": rel,
                               "detail": f"claimed by {', '.join(holders)}"})
        if holders:
            ownership[str(path.resolve())] = holders

    allowed = {b["name"]: set(b.get("may_depend_on") or []) for b in boundaries}
    public = {b["name"]: (b.get("public") or []) for b in boundaries}

    observed: dict[str, set[str]] = {name: set() for name in allowed}
    found, unresolved = edges(root, files, aliases)
    for edge in found:
        source_owners = ownership.get(str((root / edge["from"]).resolve()), [])
        target_path = Path(edge["to"])
        target_owners = ownership.get(str(target_path), [])
        if not source_owners or not target_owners:
            continue
        source, target = source_owners[0], target_owners[0]
        if source == target:
            continue
        observed[source].add(target)
        try:
            target_rel = target_path.relative_to(root).as_posix()
        except ValueError:
            continue
        if target not in allowed[source]:
            violations.append({
                "principle": "declared-dependency-direction", "where": edge["from"],
                "detail": f"{source} -> {target} is not declared; {target_rel}",
            })
        elif public[target] and not matches(target_rel, public[target]):
            violations.append({
                "principle": "public-surface-only", "where": edge["from"],
                "detail": f"{target_rel} is internal to {target}; import its public surface",
            })

    for cycle in find_cycles({name: set(targets) for name, targets in allowed.items()}):
        violations.append({"principle": "no-cycles", "where": MANIFEST_NAME,
                           "detail": "declared cycle " + " -> ".join(cycle)})
    for cycle in find_cycles(observed):
        violations.append({"principle": "no-cycles", "where": "source",
                           "detail": "observed cycle " + " -> ".join(cycle)})

    if unresolved:
        notes.append(f"{len(unresolved)} import(s) did not resolve and were not checked")
        notes.extend(unresolved[:10])
    unowned = sum(1 for p in files if not owners(p.relative_to(root).as_posix(), boundaries))
    if unowned:
        notes.append(f"{unowned} source file(s) belong to no declared boundary")

    return {
        "declared": True,
        "boundaries": [b["name"] for b in boundaries],
        "files_scanned": len(files),
        "edges_resolved": len(found),
        "observed_edges": {k: sorted(v) for k, v in observed.items() if v},
        "violations": violations,
        "notes": notes,
    }


def hotspots(root: Path, limit: int = 15) -> dict[str, Any]:
    """Fan-in and fan-out per file. A module most of the system imports is a coupling risk
    whatever the folder names suggest, and it is only visible as a count."""
    manifest = load_manifest(root) or {}
    files = source_files(root)
    found, _ = edges(root, files, manifest.get("aliases") or {})
    fan_in: dict[str, int] = {}
    fan_out: dict[str, int] = {}
    for edge in found:
        try:
            target = Path(edge["to"]).relative_to(root).as_posix()
        except ValueError:
            continue
        fan_in[target] = fan_in.get(target, 0) + 1
        fan_out[edge["from"]] = fan_out.get(edge["from"], 0) + 1
    rank = lambda counts: [  # noqa: E731
        {"path": path, "count": count}
        for path, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    ]
    return {"files": len(files), "edges": len(found),
            "most_imported": rank(fan_in), "imports_most": rank(fan_out)}


def render(result: dict[str, Any]) -> str:
    if not result["declared"]:
        return (f"architecture: not declared ({result['reason']}).\n"
                f"Declare boundaries in {MANIFEST_NAME} to turn the principles into a gate.")
    lines = [
        f"boundaries  {', '.join(result['boundaries'])}",
        f"scanned     {result['files_scanned']} files, {result['edges_resolved']} imports resolved",
    ]
    for name, targets in sorted(result.get("observed_edges", {}).items()):
        lines.append(f"  {name} -> {', '.join(targets)}")
    if result["violations"]:
        lines.append(f"\n{len(result['violations'])} VIOLATION(S)")
        for violation in result["violations"]:
            lines.append(f"  [{violation['principle']}] {violation['where']}")
            lines.append(f"      {violation['detail']}")
    else:
        lines.append("\nno violations")
    for note in result["notes"]:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check source against architecture.json.")
    parser.add_argument("--root", required=True, help="target project root, never the plugin directory")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--graph", action="store_true", help="print observed edges only")
    parser.add_argument("--hotspots", action="store_true",
                        help="rank files by fan-in and fan-out; needs no architecture.json")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error("--root must name an existing project directory")
    if args.hotspots:
        print(json.dumps(hotspots(root), indent=2))
        return 0

    try:
        result = check(root)
    except ArchError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2

    if args.graph:
        print(json.dumps(result.get("observed_edges", {}), indent=2))
    elif args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(render(result))
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
