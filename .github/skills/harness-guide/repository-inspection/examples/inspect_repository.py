"""Exercise the three public inspection modules with temporary synthetic inputs."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from repository_inspection import architecture, catalogue, filesystem


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory) / "project"
        (root / "core").mkdir(parents=True)
        (root / "app").mkdir()
        (root / "core/api.py").write_text("value = 1\n", encoding="utf-8")
        (root / "app/main.py").write_text("from core.api import value\n", encoding="utf-8")
        manifest = {"boundaries": [
            {"name": "core", "paths": ["core/*"], "may_depend_on": []},
            {"name": "app", "paths": ["app/*"], "may_depend_on": ["core"]},
        ]}
        (root / "architecture.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert architecture.check(root)["violations"] == []
        manifest["boundaries"][1]["may_depend_on"] = []
        (root / "architecture.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert architecture.check(root)["violations"]

        before = filesystem.scan(root)
        (root / "added.py").write_text("value = 2\n", encoding="utf-8")
        after = filesystem.scan(root)
        assert filesystem.compare(before, after)["net_removed"]["files"] == -1

        package = Path(directory) / "catalogue"
        (package / "skills/example").mkdir(parents=True)
        (package / "protocols").mkdir()
        (package / "skills/example/SKILL.md").write_text("# Synthetic inspection entry\n", encoding="utf-8")
        skills = {"schema_version": 1, "skills": [{
            "name": "example", "summary": "Inspect a synthetic repository",
            "access": "guidance", "keywords": ["inspection"],
        }]}
        (package / "skills/catalogue.json").write_text(json.dumps(skills), encoding="utf-8")
        (package / "protocols/catalogue.json").write_text(
            json.dumps({"schema_version": 1, "protocols": []}), encoding="utf-8",
        )
        assert catalogue.report(package, query="inspection")["count"] == 1
        assert catalogue.report(package, name="example")["entries"][0]["content"].startswith("# Synthetic")
    print("PASS: public architecture, filesystem and catalogue APIs; temporary synthetic inputs only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())