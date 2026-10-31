#!/usr/bin/env python3
"""Validate, list, search and read a local harness capability package without side effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

MAX_DOCUMENT_BYTES = 1_000_000
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ALIAS = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*\Z")
STOPWORDS = frozenset("a an and are as at be can do for from how i in is it me my of on or our the this to use we what which with you".split())


def contained_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Catalogue needs a contained relative file path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError("Catalogue path escapes its root")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Catalogue path escapes its root")
    if not path.is_file():
        raise ValueError(f"Catalogue file is missing: {relative}")
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Catalogue file is too large: {relative}")
    return path


def document(package: Path, relative: str, *, versions: tuple[int, ...] = (1,)) -> dict[str, Any]:
    loaded = json.loads(contained_file(package, relative).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Catalogue must be a JSON object")
    if type(loaded.get("schema_version")) is not int or loaded["schema_version"] not in versions:
        raise ValueError(f"Catalogue must declare schema_version in {versions}")
    return loaded


def entry_names(entries: Any, kind: str) -> list[str]:
    if not isinstance(entries, list):
        raise ValueError(f"Catalogue must declare a {kind} array")
    names = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not NAME.fullmatch(entry["name"]):
            raise ValueError(f"Every {kind} catalogue entry needs a valid name")
        if not all(isinstance(entry.get(field), str) and entry[field].strip() for field in ("summary", "access")):
            raise ValueError(f"{entry['name']} needs a summary and access method")
        keywords = entry.get("keywords", [])
        if not isinstance(keywords, list) or not all(isinstance(word, str) and word.strip() for word in keywords):
            raise ValueError(f"{entry['name']} needs a string array of keywords")
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(alias, str) and len(alias) <= 64
                                                   and ALIAS.fullmatch(alias) for alias in aliases):
            raise ValueError(f"{entry['name']} needs valid lookup aliases")
        names.append(entry["name"])
    return names


def skill_catalogue(package: Path) -> list[dict[str, Any]]:
    entries = document(package, "skills/catalogue.json").get("skills")
    names = entry_names(entries, "skills")
    authored_names = {entry["name"] for entry in entries if not entry.get("protocol")}
    discovered = {path.parent.name for path in (package / "skills").glob("*/SKILL.md") if path.is_file()}
    if len(set(names)) != len(names) or authored_names != discovered:
        raise ValueError(f"Skill catalogue disagrees with discovery: uncatalogued={sorted(discovered - authored_names)}; absent={sorted(authored_names - discovered)}")
    config_path = package / "mcp.json"
    config = json.loads(contained_file(package, "mcp.json").read_text(encoding="utf-8")) if config_path.exists() else {}
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("MCP configuration must declare a server object")
    servers = config.get("mcpServers", {})
    declared_servers = []
    for entry in entries:
        if not entry.get("protocol"):
            contained_file(package, f"skills/{entry['name']}/SKILL.md")
        mcp = entry.get("mcp")
        if mcp is None:
            continue
        if not isinstance(mcp, dict) or not isinstance(mcp.get("server"), str) or mcp["server"] not in servers:
            raise ValueError(f"Skill {entry['name']} names an undeclared MCP server")
        tools = mcp.get("tools")
        if not isinstance(tools, list) or not tools or not all(isinstance(tool, str) and tool for tool in tools):
            raise ValueError(f"Skill {entry['name']} needs a nonempty MCP tool list")
        if len(set(tools)) != len(tools) or mcp.get("status_tool") not in tools:
            raise ValueError(f"Skill {entry['name']} has invalid MCP tools or status tool")
        environment = mcp.get("environment")
        if not isinstance(environment, str) or not environment or "\\" in environment or PurePosixPath(environment).is_absolute() or ".." in PurePosixPath(environment).parts:
            raise ValueError(f"Skill {entry['name']} needs a contained runtime environment path")
        declared_servers.append(mcp["server"])
    if len(set(declared_servers)) != len(declared_servers) or set(declared_servers) != set(servers):
        raise ValueError("MCP server catalogue must cover every declared server exactly once")
    return sorted(entries, key=lambda entry: entry["name"])


def protocol_catalogue(package: Path) -> list[dict[str, Any]]:
    entries = document(package, "protocols/catalogue.json").get("protocols")
    names = entry_names(entries, "protocols")
    paths = []
    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str) or PurePosixPath(relative).suffix != ".md" or relative == "README.md":
            raise ValueError(f"Protocol {entry['name']} needs a Markdown entry point")
        contained_file(package, f"protocols/{relative}")
        paths.append(relative)
    discovered = {path.relative_to(package / "protocols").as_posix()
                  for path in (package / "protocols").rglob("*.md")
                  if path.name != "README.md"}
    if len(set(names)) != len(names) or len(set(paths)) != len(paths) or set(paths) != discovered:
        raise ValueError("Protocol catalogue disagrees with discovery")
    return sorted(entries, key=lambda entry: entry["name"])


def workspace_root(package: Path, view: dict[str, Any]) -> Path:
    package = package.resolve()
    if (view.get("discovery") != "workspace-source" or view.get("workspace_root") != "../.."
            or package.name != ".github"):
        raise ValueError("Workspace catalogue needs the fixed .github/skills source layout")
    root = (package / "skills" / view["workspace_root"]).resolve()
    if root != package.parent:
        raise ValueError("Workspace catalogue root disagrees with fixed source layout")
    return root


def workspace_catalogue(package: Path, view: dict[str, Any]) -> list[dict[str, Any]]:
    root = workspace_root(package, view)
    generation = view.get("generation")
    if (not isinstance(generation, dict) or generation.get("source") != "libraries/capabilities.json"
            or generation.get("generator") != ".github/tools/package_native.py"
            or not isinstance(generation.get("source_hashes"), dict)):
        raise ValueError("Workspace catalogue needs source and generator provenance")
    hashes = generation["source_hashes"]
    for relative, expected in [*hashes.items(), (generation["source"], generation.get("sha256")),
                               (generation["generator"], generation.get("generator_sha256"))]:
        if hashlib.sha256(contained_file(root, relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Workspace source changed: {relative}; regenerate from its authority")
    entries = view.get("skills")
    names = entry_names(entries, "skills")
    if len(set(names)) != len(names):
        raise ValueError("Duplicate workspace skill names")
    protocols = {entry["name"]: entry for entry in protocol_catalogue(package)}
    workflows = set()
    results = []
    for entry in entries:
        protocol = entry.get("protocol")
        if protocol is not None:
            if not isinstance(protocol, str) or protocol not in protocols or protocol in workflows:
                raise ValueError("Workflow skill must have one unique known protocol owner")
            workflows.add(protocol)
            relative = f".github/protocols/{protocols[protocol]['path']}"
            if entry["name"] != Path(relative).parent.name:
                raise ValueError("Workflow name disagrees with canonical protocol")
        else:
            relative = f".github/skills/{entry['name']}/SKILL.md"
        if entry.get("source") != relative:
            raise ValueError("Workspace source disagrees with canonical owner")
        embedded = entry.get("embedded_guidance", [])
        component_names = entry_names(embedded, "embedded_guidance")
        if len(set(component_names)) != len(component_names):
            raise ValueError("Duplicate embedded guidance names")
        for path in [entry.get("source"), entry.get("guidance"),
                     *(component.get("guidance") for component in embedded)]:
            contained_file(root, path)
            if path not in hashes:
                raise ValueError("Workspace guidance needs a source hash")
        if protocol is not None and entry.get("guidance") != relative:
            raise ValueError("Workflow guidance disagrees with canonical protocol")
        guidance = entry["guidance"]
        result = {**entry, "id": f"protocol:{protocol}" if protocol else f"skill:{entry['name']}",
                  "kind": "protocol" if protocol else "skill", "availability": "workspace-source",
                  "entrypoint": guidance, "read_path": str(contained_file(root, guidance))}
        if protocol is not None:
            result.update(name=protocol, native_name=entry["name"], native_entrypoint=relative,
                          native_read_path=str(contained_file(root, relative)))
        results.append(result)
    if workflows != set(protocols):
        raise ValueError("Workspace protocol catalogue disagrees with discovery")
    lookup_owners = {}
    for entry in results:
        for name in {entry["id"], entry["name"], entry.get("native_name", entry["name"])}:
            if name in lookup_owners:
                raise ValueError("Duplicate or colliding capability name")
            lookup_owners[name] = entry["id"]
    discovered = {path.parent.name for path in (package / "skills").glob("*/SKILL.md") if path.is_file()}
    authored = {entry["name"] for entry in entries if not entry.get("protocol")}
    if not authored <= discovered or discovered - set(names):
        raise ValueError("Workspace skill catalogue disagrees with discovery")
    reserved = {entry["id"] for entry in results} | set(names) | set(protocols)
    for entry in results:
        for alias in entry.get("aliases", []):
            if alias in reserved:
                raise ValueError("Duplicate or colliding capability alias")
            reserved.add(alias)
    return sorted(results, key=lambda entry: entry["id"])


def capability_catalogue(package: Path, source_root: Path | None = None) -> list[dict[str, Any]]:
    package = package.resolve()
    native = package / "native-manifest.json"
    if native.exists():
        manifest = json.loads(contained_file(package, "native-manifest.json").read_text())
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
            raise ValueError("Invalid native package manifest")
        for relative, expected in manifest["files"].items():
            actual = hashlib.sha256(contained_file(package, relative).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Native package projection changed: {relative}; regenerate from its authority")
    view = document(package, "skills/catalogue.json", versions=(1, 2))
    if view["schema_version"] == 2:
        return workspace_catalogue(package, view)
    results = []
    declared_skill_paths = []
    workflow_entries = {}
    for kind, entries in (("skill", skill_catalogue(package)), ("protocol", protocol_catalogue(package))):
        for entry in entries:
            if kind == "skill" and entry.get("protocol"):
                relative = f"protocols/{entry['name']}/SKILL.md"
            else:
                relative = f"skills/{entry['name']}/SKILL.md" if kind == "skill" else f"protocols/{entry['path']}"
            if kind == "skill" and entry.get("protocol"):
                protocol = entry["protocol"]
                if not isinstance(protocol, str) or protocol in workflow_entries:
                    raise ValueError("Workflow skill must have one unique protocol owner")
                workflow_entries[protocol] = relative
            else:
                results.append({**entry, "id": f"{kind}:{entry['name']}", "kind": kind,
                                "availability": "bundled", "entrypoint": relative,
                                "read_path": str(contained_file(package, relative))})
            if kind == "skill" and not entry.get("protocol"):
                declared_skill_paths.append(relative)
                components = entry.get("components", [])
                names = entry_names(components, "components")
                if len(set(names)) != len(names):
                    raise ValueError("Duplicate embedded skill names")
                for component in components:
                    path = component.get("path")
                    if not isinstance(path, str) or PurePosixPath(path).name != "SKILL.md" or path == "SKILL.md":
                        raise ValueError("Embedded skill needs its own SKILL.md entry point")
                    owned_path = contained_file(package / "skills" / entry["name"], path)
                    relative = f"skills/{entry['name']}/{path}"
                    declared_skill_paths.append(relative)
                    results.append({**component, "id": f"skill:{entry['name']}/{component['name']}",
                                    "kind": "skill", "parent": entry["name"],
                                    "availability": "bundled-component", "entrypoint": relative,
                                    "read_path": str(owned_path)})
    discovered_paths = set()
    for directory, children, filenames in os.walk(package / "skills"):
        children[:] = [name for name in children if name not in {
            ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "site-packages",
        }]
        if "SKILL.md" in filenames:
            discovered_paths.add((Path(directory) / "SKILL.md").relative_to(package).as_posix())
    if len(set(declared_skill_paths)) != len(declared_skill_paths) or set(declared_skill_paths) != discovered_paths:
        raise ValueError("Embedded skill catalogue disagrees with discovery")
    for name, relative in workflow_entries.items():
        protocol = next((entry for entry in results if entry["id"] == f"protocol:{name}"), None)
        if protocol is None:
            raise ValueError("Native workflow refers to an absent protocol")
        protocol["native_entrypoint"] = relative
        protocol["native_name"] = Path(relative).parent.name
        protocol["native_read_path"] = str(contained_file(package, relative))
    source_entries = document(package, "skills/catalogue.json").get("source_skills", [])
    names = entry_names(source_entries, "source_skills")
    if len(set(names)) != len(names):
        raise ValueError("Source skill catalogue disagrees with discovery")
    declared_paths = set()
    for entry in source_entries:
        relative = entry.get("source_path")
        if not isinstance(relative, str) or "\\" in relative:
            raise ValueError("Source skill needs a module source_path")
        parts = PurePosixPath(relative).parts
        if len(parts) != 5 or parts[0] != "modules" or not NAME.fullmatch(parts[1]) or parts[2:] != ("skills", entry["name"], "SKILL.md"):
            raise ValueError("Source skill path escapes the declared module layout")
        if not isinstance(entry.get("requires"), str) or not entry["requires"].strip():
            raise ValueError("Source skill must state its prerequisites")
        declared_paths.add(relative)
        path = contained_file(source_root, relative) if source_root is not None else None
        if "superseded_by" in entry:
            replacement = next((item for item in results if item["id"] == f"skill:{entry['superseded_by']}"
                                and item["availability"] == "bundled"), None)
            if replacement is None or entry["superseded_by"] != entry["name"]:
                raise ValueError("Source alias needs a same-name bundled replacement")
            replacement.setdefault("source_aliases", []).append(relative)
            continue
        results.append({**entry, "id": f"skill:{entry['name']}", "kind": "skill",
                        "availability": "source-only", "entrypoint": relative,
                        "read_path": str(path) if path is not None else None})
    if source_root is not None:
        discovered = {path.relative_to(source_root).as_posix()
                      for path in source_root.glob("modules/*/skills/*/SKILL.md") if path.is_file()}
        if declared_paths != discovered:
            raise ValueError("Source skill catalogue disagrees with discovery")
    identifiers = [entry["id"] for entry in results]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate capability identifiers")
    reserved = set(identifiers) | {entry["name"] for entry in results}
    for entry in results:
        for alias in entry.get("aliases", []):
            if alias in reserved:
                raise ValueError("Duplicate or colliding capability alias")
            reserved.add(alias)
    return sorted(results, key=lambda entry: entry["id"])


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def search(entries: list[dict[str, Any]], query: str, limit: int = 5) -> list[dict[str, Any]]:
    terms = words(query) - STOPWORDS
    if not terms:
        raise ValueError("Search needs at least one concrete word or number; use --list for everything")
    if not 1 <= limit <= 50:
        raise ValueError("Search limit must be between 1 and 50")
    ranked = []
    for entry in entries:
        fields = ((entry["name"], 20), (" ".join(entry.get("aliases", [])), 20), (" ".join(entry.get("keywords", [])), 12),
                  (entry["summary"], 4), (entry["access"], 1))
        matched = set()
        score = 0
        for text, weight in fields:
            hits = terms & words(text)
            matched.update(hits)
            score += len(hits) * weight
        if matched:
            exact = query.strip().casefold() in {entry["name"], entry["id"], *entry.get("aliases", [])}
            ranked.append((not exact, -len(matched), -score, entry["id"],
                           {**entry, "matched_terms": sorted(matched), "missing_terms": sorted(terms - matched)}))
    ranked.sort(key=lambda match: match[:4])
    return [match[4] for match in ranked[:limit]]


def report(package: Path, *, query: str | None = None, name: str | None = None,
           kind: str | None = None, limit: int = 5, source_root: Path | None = None) -> dict[str, Any]:
    entries = capability_catalogue(package, source_root)
    totals = {"skills": sum((entry["kind"] == "skill" and entry["availability"] in {"bundled", "workspace-source"})
                             or bool(entry.get("native_entrypoint")) for entry in entries),
              "protocols": sum(entry["kind"] == "protocol" for entry in entries),
              "embedded_skills": sum(entry["availability"] == "bundled-component" for entry in entries),
              "source_only_skills": sum(entry["availability"] == "source-only" for entry in entries)}
    if kind is not None and kind not in {"skill", "protocol"}:
        raise ValueError("Unknown capability kind")
    if query is not None and name is not None:
        raise ValueError("Choose search or exact-name read, not both")
    selected = [entry for entry in entries if kind is None or entry["kind"] == kind]
    if query is not None:
        selected = search(selected, query, limit)
    if name is not None:
        selected = [entry for entry in selected if name in {entry["name"], entry["id"], entry.get("native_name"), *entry.get("aliases", [])}]
        if len(selected) != 1:
            raise ValueError("Unknown or ambiguous capability name; use --list")
        entry = selected[0]
        if entry["read_path"] is None:
            raise ValueError("Source-only skill is not bundled; supply a reviewed --source-root to read it")
        root = source_root if entry["availability"] == "source-only" else package
        if entry["availability"] == "workspace-source":
            root = workspace_root(package, document(package, "skills/catalogue.json", versions=(2,)))
        selected = [{**entry, "content": contained_file(root, entry["entrypoint"]).read_text(encoding="utf-8")}]
    return {"schema_version": 1, "totals": totals, "query": query, "count": len(selected),
            "entries": selected,
            "next": "Read a candidate with --show NAME; if wording missed, use --list. A match grants no authority."}


def print_report(result: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    totals = result["totals"]
    print(f"{totals['skills']} bundled skills; {totals['protocols']} protocols; {totals['embedded_skills']} embedded skills; {totals['source_only_skills']} source-only skills")
    for entry in result["entries"]:
        print(f"\n{entry['id']} [{entry['availability']}; {entry['access']}]\n  {entry['summary']}")
        print(f"  Read: {entry['read_path'] or entry['entrypoint']}")
        if entry.get("aliases"):
            print(f"  Also known as: {', '.join(entry['aliases'])}")
        if entry.get("parent"):
            print(f"  Parent skill: {entry['parent']}; read its integration contract too.")
        if entry.get("requires"):
            print(f"  Requires: {entry['requires']}")
        if "matched_terms" in entry:
            print(f"  Matched: {', '.join(entry['matched_terms'])}; missing: {', '.join(entry['missing_terms']) or 'none'}")
        if "content" in entry:
            print(entry["content"])
    if not result["entries"]:
        print("No catalogue match. Try fewer concrete terms or list all entries.")
    print(f"\n{result['next']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="explicit catalogue package root; never inferred from installed code")
    parser.add_argument("--source-root", type=Path, help="explicit optional-module source checkout")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--list", action="store_true", help="list every entry (default)")
    actions.add_argument("--find", metavar="QUERY", help="rank literal catalogue keyword matches")
    actions.add_argument("--show", metavar="NAME", help="read one exact registered entry")
    actions.add_argument("--check", action="store_true", help="validate full catalogue coverage")
    parser.add_argument("--kind", choices=("skill", "protocol"))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args(argv)
    try:
        result = report(options.root, query=options.find, name=options.show, kind=options.kind,
                        limit=options.limit, source_root=options.source_root)
        if options.check and not options.json:
            print(f"Catalogue PASS: {json.dumps(result['totals'], sort_keys=True)}")
        else:
            print_report(result, as_json=options.json)
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Discovery refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())