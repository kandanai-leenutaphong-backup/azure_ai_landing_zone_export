from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from agentcraft import catalogue


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="framework-catalogue-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.artifact = self.directory / "installed" / "agentcraft"
        self.root = self.artifact / "guidance"
        skill = self.root / "skills/harness-guide/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Installed harness guide\n")
        protocol = self.root / "protocols/protocol-cleanup/SKILL.md"
        protocol.parent.mkdir(parents=True)
        protocol.write_text("# Installed cleanup\n")
        self.skills = [{"name": "harness-guide", "summary": "Find composition guidance", "access": "reader",
                        "aliases": ["guide"]}]
        self.protocols = [{"name": "protocol-cleanup", "path": "protocol-cleanup/SKILL.md",
                           "summary": "Clean unused code", "access": "workflow"}]
        self.snapshot = {"schema_version": 1, "capabilities": [{"id": "framework", "dependencies": []}],
                         "skills": self.skills, "protocols": self.protocols,
                         "generation": {"source": "libraries/capabilities.json", "sha256": "a" * 64}}
        (self.artifact / "capabilities.json").write_text(json.dumps(self.snapshot))
        (self.root / "skills/catalogue.json").write_text(json.dumps({"schema_version": 1, "skills": self.skills}))
        (self.root / "protocols/catalogue.json").write_text(json.dumps({"schema_version": 1, "protocols": self.protocols}))
        (self.root / "native-manifest.json").write_text(json.dumps({"schema_version": 1,
            "files": {"skills/harness-guide/SKILL.md": hashlib.sha256(skill.read_bytes()).hexdigest()}}))
        self.source_patch = patch.object(catalogue, "_source_root", return_value=None)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        resource_patch = patch.object(catalogue.resources, "files", return_value=self.artifact)
        resource_patch.start()
        self.addCleanup(resource_patch.stop)

    def test_installed_snapshot_has_one_owner_and_safe_status(self):
        document = catalogue.load_catalogue()
        capabilities = document["capabilities"]
        identifiers = {entry["id"] for entry in capabilities}
        self.assertEqual(len(capabilities), len(identifiers))
        self.assertTrue(all(set(entry["dependencies"]) <= identifiers for entry in capabilities))
        self.assertEqual("libraries/capabilities.json", document["generation"]["source"])
        self.assertEqual(64, len(document["generation"]["sha256"]))

    def test_snapshot_reads_are_independent(self):
        document = catalogue.load_catalogue()
        count = len(document["skills"])
        document["skills"].clear()
        self.assertEqual(count, len(catalogue.load_catalogue()["skills"]))

    def test_all_tasks_components_and_aliases_are_readable(self):
        document = catalogue.load_catalogue()
        result = catalogue.report()
        self.assertEqual({"skills": 1, "protocols": 1, "embedded_skills": 0, "source_only_skills": 0}, result["totals"])
        self.assertEqual("harness-guide", catalogue.report(name="guide")["entries"][0]["name"])
        names = []
        for skill in document["skills"]:
            names.extend([skill["name"], *skill.get("aliases", [])])
            names.extend(component["name"] for component in skill.get("components", []))
        for protocol in document["protocols"]:
            names.append(protocol["name"])
        root = catalogue.guidance_root().resolve()
        for name in names:
            with self.subTest(name=name):
                entry = catalogue.report(name=name)["entries"][0]
                self.assertTrue(entry["content"])
                self.assertTrue(Path(entry["read_path"]).resolve().is_relative_to(root))
        self.assertTrue(catalogue.report(query="composition")["entries"])

    def test_unknown_names_invalid_search_and_root_injection_refuse(self):
        for arguments in ({"name": "missing-capability"}, {"name": "../../private"},
                          {"query": "the and"}, {"query": "composition", "limit": 0},
                          {"name": "harness-guide", "query": "composition"}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                catalogue.report(**arguments)
        with self.assertRaises(TypeError):
            catalogue.report(root=Path("/tmp"))

    def test_guidance_is_data_only_and_integrity_checked(self):
        root = catalogue.guidance_root()
        self.assertFalse(any(path.suffix in {".py", ".pyc", ".js", ".mjs", ".ts", ".tsx", ".whl"}
                             for path in root.rglob("*") if path.is_file()))
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "guidance"
            shutil.copytree(root, copied)
            document = copied / "skills/harness-guide/SKILL.md"
            document.write_text("tampered", encoding="utf-8")
            with patch.object(catalogue, "guidance_root", return_value=copied):
                with self.assertRaisesRegex(ValueError, "Native package projection changed"):
                    catalogue.report(name="harness-guide")

    def test_missing_tooling_dependency_fails_without_fallback(self):
        with patch.dict(sys.modules, {"repository_inspection.catalogue": None}):
            with self.assertRaisesRegex(RuntimeError, "requires repository-inspection"):
                catalogue.report()

    def test_reading_never_opens_network_or_starts_processes(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            self.assertTrue(catalogue.load_catalogue()["capabilities"])
            self.assertTrue(catalogue.report(name="harness-guide")["entries"])

    def test_workspace_uses_canonical_source_without_mirror_or_cwd_lookup(self):
        source = self.directory / "workspace"
        package = source / ".github"
        shutil.copytree(self.root, package, ignore=shutil.ignore_patterns("native-manifest.json"))
        (source / "libraries").mkdir()
        authority = source / "libraries/capabilities.json"
        authority.write_text(json.dumps(self.snapshot))
        generator = package / "tools/package_native.py"
        generator.parent.mkdir()
        generator.write_text("fixture generator\n")
        skill = ".github/skills/harness-guide/SKILL.md"
        protocol = ".github/protocols/protocol-cleanup/SKILL.md"
        (source / skill).write_text("# Canonical source guide\n")
        generation = {"source": "libraries/capabilities.json",
            "sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
            "source_hashes": {relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
                              for relative in (skill, protocol)},
            "generator": ".github/tools/package_native.py",
            "generator_sha256": hashlib.sha256(generator.read_bytes()).hexdigest()}
        view = {"schema_version": 2, "discovery": "workspace-source", "workspace_root": "../..",
            "generation": generation, "skills": [dict(self.skills[0], source=skill, guidance=skill),
                dict(self.protocols[0], protocol="protocol-cleanup", source=protocol, guidance=protocol)]}
        (package / "skills/catalogue.json").write_text(json.dumps(view))
        with patch.object(catalogue, "_source_root", return_value=source), \
                patch.object(catalogue.resources, "files", side_effect=AssertionError("mirror forbidden")), \
                patch("pathlib.Path.cwd", side_effect=AssertionError("cwd lookup forbidden")), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            self.assertEqual(catalogue.load_catalogue()["capabilities"], self.snapshot["capabilities"])
            result = catalogue.report(name="guide")
            self.assertEqual(result["entries"][0]["content"], "# Canonical source guide\n")
            self.assertEqual(result["entries"][0]["read_path"], str(source / skill))
            self.assertEqual(result["generation"], generation)
            view["schema_version"] = 1
            (package / "skills/catalogue.json").write_text(json.dumps(view))
            with self.assertRaisesRegex(ValueError, "schema_version"):
                catalogue.report()

    def test_fixed_layout_detection_and_real_source_metadata(self):
        self.source_patch.stop()
        root = catalogue._source_root()
        self.assertIsNotNone(root)
        self.assertEqual(catalogue.guidance_root(), root / ".github")
        document = catalogue.load_catalogue()
        self.assertEqual(document["skills"], json.loads((root / "libraries/capabilities.json").read_text())["skills"])
        self.assertEqual(document["generation"]["discovery"], "workspace-source")
        with patch.object(catalogue, "__file__", str(self.artifact / "catalogue.py")):
            self.assertIsNone(catalogue._source_root())
            self.assertEqual(catalogue.guidance_root(), self.root)


if __name__ == "__main__":
    unittest.main()