#!/usr/bin/env python3
"""Exercise discovery from temporary packages, including stale and escaping metadata."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from repository_inspection import catalogue


class Discovery(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="catalogue-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.package = self.directory / "copied package"
        self.working = self.directory / "unrelated project"
        self.working.mkdir()
        self.skills = {"schema_version": 1, "skills": [
            {"name": "harness-guide", "summary": "Find existing skills and protocols", "access": "guidance and CLI"},
        ], "source_skills": []}
        self.protocols = {"schema_version": 1, "protocols": [
            {"name": "protocol-garbage-collect", "path": "protocol-garbage-collect/SKILL.md",
             "summary": "Prove dead code before deleting it", "access": "protocol",
             "keywords": ["cleanup", "remove dead code"]},
        ]}
        self.write("skills/harness-guide/SKILL.md", "# Harness Guide\n")
        self.write("protocols/protocol-garbage-collect/SKILL.md", "# Cleanup\nExplicit deletion authority required.\n")
        self.sync()

    def write(self, relative: str, text: str) -> None:
        target = self.package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def sync(self) -> None:
        self.write("skills/catalogue.json", json.dumps(self.skills))
        self.write("protocols/catalogue.json", json.dumps(self.protocols))

    def workspace(self) -> Path:
        self.package = self.directory / "workspace" / ".github"
        self.write("skills/harness-guide/SKILL.md", "# Canonical skill\n")
        self.write("skills/harness-guide/reference.md", "# Embedded reference\n")
        self.write("protocols/protocol-garbage-collect/SKILL.md", "# Canonical protocol\n")
        self.write("tools/package_native.py", "generator fixture\n")
        root = self.package.parent
        (root / "libraries").mkdir()
        (root / "libraries/capabilities.json").write_text(json.dumps({"schema_version": 1,
            "capabilities": [{"id": "library", "tasks": [{"name": "library-task"}]}]}))
        skill = ".github/skills/harness-guide/SKILL.md"
        protocol = ".github/protocols/protocol-garbage-collect/SKILL.md"
        embedded = ".github/skills/harness-guide/reference.md"
        self.skills = {"schema_version": 2, "discovery": "workspace-source", "workspace_root": "../..",
            "skills": [{"name": "harness-guide", "summary": "Find guidance", "access": "reader",
                "source": skill, "guidance": skill, "aliases": ["child"],
                "embedded_guidance": [{"name": "child", "summary": "Embedded guide", "access": "read",
                                       "guidance": embedded}]},
                {"name": "protocol-garbage-collect", "summary": "Cleanup", "access": "workflow",
                 "protocol": "protocol-garbage-collect", "source": protocol, "guidance": protocol}],
            "generation": {"source": "libraries/capabilities.json",
                "sha256": hashlib.sha256((root / "libraries/capabilities.json").read_bytes()).hexdigest(),
                "source_hashes": {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                                  for path in (skill, protocol, embedded)},
                "generator": ".github/tools/package_native.py",
                "generator_sha256": hashlib.sha256((self.package / "tools/package_native.py").read_bytes()).hexdigest()}}
        self.sync()
        return root

    def test_workspace_reads_canonical_sources_and_not_library_tasks(self) -> None:
        root = self.workspace()
        result = catalogue.report(self.package, name="child")
        self.assertEqual(result["entries"][0]["content"], "# Canonical skill\n")
        self.assertEqual(result["entries"][0]["read_path"], str(root / self.skills["skills"][0]["guidance"]))
        self.assertEqual(result["totals"], {"skills": 2, "protocols": 1, "embedded_skills": 0, "source_only_skills": 0})
        self.assertEqual(catalogue.report(self.package, name="protocol-garbage-collect")["entries"][0]["content"],
                         "# Canonical protocol\n")
        for name in ("library-task", "missing", "../../private"):
            with self.assertRaisesRegex(ValueError, "Unknown"):
                catalogue.report(self.package, name=name)

    def test_workspace_hashes_and_native_manifest_refuse_tampering(self) -> None:
        root = self.workspace()
        for relative in [*self.skills["generation"]["source_hashes"], "libraries/capabilities.json",
                         ".github/tools/package_native.py"]:
            target = root / relative
            original = target.read_bytes()
            target.write_text("changed")
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "Workspace source changed"):
                catalogue.report(self.package)
            target.write_bytes(original)
        self.write("native-manifest.json", json.dumps({"schema_version": 1, "files": {"skills/catalogue.json": "bad"}}))
        with self.assertRaisesRegex(ValueError, "Native package projection changed"):
            catalogue.report(self.package)

    def test_workspace_contract_aliases_protocols_and_paths_refuse(self) -> None:
        self.workspace()
        original = json.dumps(self.skills)
        for field, value in (("workspace_root", "../../.."), ("discovery", "guessed")):
            self.skills[field] = value
            self.sync()
            with self.assertRaises(ValueError):
                catalogue.report(self.package)
            self.skills = json.loads(original)
        for mutation in (lambda: self.skills["skills"][0].update(aliases=["protocol-garbage-collect"]),
                         lambda: self.skills["skills"].append(dict(self.skills["skills"][1], name="other")),
                         lambda: self.skills["skills"][1].update(protocol="unknown"),
                         lambda: self.skills["skills"][0].update(guidance="../outside"),
                         lambda: self.skills["generation"]["source_hashes"].pop(".github/skills/harness-guide/reference.md")):
            mutation()
            self.sync()
            with self.assertRaises(ValueError):
                catalogue.report(self.package)
            self.skills = json.loads(original)
        self.sync()
        target = self.package / "skills/harness-guide/SKILL.md"
        target.unlink()
        target.symlink_to(self.working / "outside.md")
        (self.working / "outside.md").write_text("outside")
        with self.assertRaisesRegex(ValueError, "escapes"):
            catalogue.report(self.package)

    def test_workspace_protocol_alias_cannot_collide_with_skill(self) -> None:
        self.workspace()
        self.protocols["protocols"][0]["name"] = "harness-guide"
        self.skills["skills"][1]["protocol"] = "harness-guide"
        self.sync()
        with self.assertRaisesRegex(ValueError, "colliding capability name"):
            catalogue.report(self.package)

    def test_list_search_and_exact_read(self) -> None:
        result = catalogue.report(self.package)
        self.assertEqual(result["totals"], {"skills": 1, "protocols": 1, "embedded_skills": 0, "source_only_skills": 0})
        found = catalogue.report(self.package, query="remove dead code")
        self.assertEqual(found["entries"][0]["name"], "protocol-garbage-collect")
        self.assertEqual(found["entries"][0]["missing_terms"], [])
        read = catalogue.report(self.package, name="protocol:protocol-garbage-collect")
        self.assertEqual(read["entries"][0]["content"], (self.package / "protocols/protocol-garbage-collect/SKILL.md").read_text())

    def test_native_workflow_entry_lives_with_protocols(self) -> None:
        self.skills["skills"].append({
            "name": "protocol-garbage-collect",
            "summary": "Prove dead code before deleting it",
            "access": "native workflow skill",
            "protocol": "protocol-garbage-collect",
        })
        self.sync()

        result = catalogue.report(self.package, name="protocol:protocol-garbage-collect")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entries"][0]["native_entrypoint"],
                         "protocols/protocol-garbage-collect/SKILL.md")
        self.assertEqual(result["entries"][0]["native_read_path"],
                         str(self.package / "protocols/protocol-garbage-collect/SKILL.md"))
        self.assertEqual(result["entries"][0]["native_read_path"], result["entries"][0]["read_path"])
        self.assertEqual(result["entries"][0]["content"], "# Cleanup\nExplicit deletion authority required.\n")

    def test_superseded_protocol_document_refuses(self) -> None:
        self.write("protocols/protocol-garbage-collect.md", "# Superseded cleanup procedure\n")

        with self.assertRaisesRegex(ValueError, "Protocol catalogue disagrees"):
            catalogue.report(self.package)

    def test_exact_alias_reads_one_canonical_entry(self) -> None:
        self.skills["skills"][0]["aliases"] = ["harness_guide"]
        self.sync()
        result = catalogue.report(self.package, name="harness_guide")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entries"][0]["id"], "skill:harness-guide")
        self.assertEqual(result["entries"][0]["content"], "# Harness Guide\n")
        self.assertEqual(catalogue.report(self.package, query="harness_guide")["entries"][0]["name"], "harness-guide")
        for aliases in (["../private"], ["harness-guide"], ["protocol-garbage-collect"],
                        ["same_alias", "same_alias"], "not-an-array"):
            self.skills["skills"][0]["aliases"] = aliases
            self.sync()
            with self.subTest(aliases=aliases), self.assertRaisesRegex(ValueError, "alias"):
                catalogue.report(self.package)

    def test_no_match_is_not_an_invented_recommendation(self) -> None:
        result = catalogue.report(self.package, query="zzunavailablezz")
        self.assertEqual(result["count"], 0)
        self.assertIn("--list", result["next"])
        for query in ("", "   ", "!!", "the and a"):
            with self.assertRaises(ValueError):
                catalogue.report(self.package, query=query)
        with self.assertRaises(ValueError):
            catalogue.report(self.package, query="cleanup", limit=0)

    def test_missing_duplicate_and_invented_entries_refuse(self) -> None:
        self.protocols["protocols"] = []
        self.sync()
        with self.assertRaisesRegex(ValueError, "disagrees"):
            catalogue.report(self.package)
        self.skills["skills"].append(dict(self.skills["skills"][0]))
        self.sync()
        with self.assertRaisesRegex(ValueError, "disagrees"):
            catalogue.report(self.package)
        self.skills["skills"] = [{"name": "absent", "summary": "Absent", "access": "guidance"}]
        self.sync()
        with self.assertRaisesRegex(ValueError, "disagrees"):
            catalogue.report(self.package)

    def test_invalid_schema_and_metadata_refuse(self) -> None:
        self.write("skills/catalogue.json", "[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            catalogue.report(self.package)
        self.skills["schema_version"] = True
        self.sync()
        with self.assertRaisesRegex(ValueError, "schema_version"):
            catalogue.report(self.package)
        self.skills["schema_version"] = 1
        self.skills["skills"][0]["keywords"] = "not an array"
        self.sync()
        with self.assertRaisesRegex(ValueError, "keywords"):
            catalogue.report(self.package)

    def test_paths_and_unknown_names_cannot_read_arbitrary_files(self) -> None:
        for name in ("../outside.md", "/etc/passwd", "missing"):
            with self.assertRaisesRegex(ValueError, "Unknown"):
                catalogue.report(self.package, name=name)
        self.protocols["protocols"][0]["path"] = "../../outside.md"
        self.sync()
        with self.assertRaisesRegex(ValueError, "escapes"):
            catalogue.report(self.package)

    def test_escaping_symlink_refuses(self) -> None:
        outside = self.directory / "outside.md"
        outside.write_text("Outside fixture", encoding="utf-8")
        path = self.package / "protocols/protocol-garbage-collect/SKILL.md"
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            catalogue.report(self.package)

    def test_mcp_inventory_is_still_validated(self) -> None:
        self.write("mcp.json", json.dumps({"mcpServers": {"example": {"type": "stdio"}}}))
        with self.assertRaisesRegex(ValueError, "every declared server"):
            catalogue.report(self.package)
        self.skills["skills"][0]["mcp"] = {"server": "example", "tools": ["status"],
                                           "status_tool": "status", "environment": "example/venv"}
        self.sync()
        self.assertEqual(catalogue.report(self.package)["totals"]["skills"], 1)
        self.skills["skills"][0]["mcp"]["environment"] = "../outside"
        self.sync()
        with self.assertRaisesRegex(ValueError, "contained runtime"):
            catalogue.report(self.package)

    def test_source_only_skill_is_explicit_and_requires_a_source_root(self) -> None:
        relative = "modules/motion/skills/motion/SKILL.md"
        self.skills["source_skills"] = [{"name": "motion", "summary": "Render motion", "access": "guidance",
                                         "source_path": relative, "requires": "Approved local renderer"}]
        self.sync()
        result = catalogue.report(self.package, query="motion")
        self.assertEqual(result["entries"][0]["availability"], "source-only")
        self.assertIsNone(result["entries"][0]["read_path"])
        with self.assertRaisesRegex(ValueError, "not bundled"):
            catalogue.report(self.package, name="motion")
        source = self.directory / "source"
        path = source / relative
        path.parent.mkdir(parents=True)
        path.write_text("# Motion fixture\n", encoding="utf-8")
        read = catalogue.report(self.package, name="motion", source_root=source)
        self.assertEqual(read["entries"][0]["content"], "# Motion fixture\n")
        self.skills["source_skills"] = []
        self.sync()
        with self.assertRaisesRegex(ValueError, "disagrees"):
            catalogue.report(self.package, source_root=source)

    def test_promoted_source_entry_routes_to_one_bundled_owner(self) -> None:
        self.skills["source_skills"] = [{"name": "harness-guide", "summary": "Former module entry", "access": "compatibility pointer",
                                         "source_path": "modules/legacy/skills/harness-guide/SKILL.md",
                                         "requires": "Use the bundled skill", "superseded_by": "harness-guide"}]
        self.sync()
        result = catalogue.report(self.package, name="harness-guide")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entries"][0]["availability"], "bundled")
        self.assertEqual(result["totals"]["source_only_skills"], 0)
        self.assertEqual(len(result["entries"][0]["source_aliases"]), 1)
        self.skills["source_skills"][0]["superseded_by"] = "missing"
        self.sync()
        with self.assertRaisesRegex(ValueError, "replacement"):
            catalogue.report(self.package)

    def test_embedded_skills_are_catalogued_under_their_owner(self) -> None:
        self.write("skills/harness-guide/modules/child/SKILL.md", "# Embedded skill\n")
        with self.assertRaisesRegex(ValueError, "Embedded.*disagrees"):
            catalogue.report(self.package)
        self.skills["skills"][0]["components"] = [
            {"name": "child", "path": "modules/child/SKILL.md", "summary": "An embedded skill", "access": "guidance"},
        ]
        self.sync()
        result = catalogue.report(self.package, name="skill:harness-guide/child")
        self.assertEqual(result["totals"]["embedded_skills"], 1)
        self.assertEqual(result["entries"][0]["parent"], "harness-guide")
        self.assertEqual(result["entries"][0]["content"], "# Embedded skill\n")
        self.skills["skills"][0]["components"][0]["path"] = "../../protocols/protocol-garbage-collect/SKILL.md"
        self.sync()
        with self.assertRaises(ValueError):
            catalogue.report(self.package)

    def test_installed_cli_works_outside_project_without_writes(self) -> None:
        before = {path.relative_to(self.package): path.read_bytes() for path in self.package.rglob("*") if path.is_file()}
        command = [sys.executable, "-I", "-m", "repository_inspection.catalogue", "--root", str(self.package)]
        environment = {**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
        for arguments in (("--find", "dead code", "--json"), ("--show", "protocol-garbage-collect", "--json"),
                          ("--list", "--kind", "skill", "--json")):
            result = subprocess.run([*command, *arguments], cwd=self.working, env=environment,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["count"], 1)
        after = {path.relative_to(self.package): path.read_bytes() for path in self.package.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(list(self.working.iterdir()), [])

    def test_cli_refuses_an_implicit_catalogue_root(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", "-m", "repository_inspection.catalogue", "--list"],
            cwd=self.working, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--root", result.stderr)
        self.assertEqual(list(self.working.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)