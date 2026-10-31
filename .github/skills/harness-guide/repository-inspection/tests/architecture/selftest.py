#!/usr/bin/env python3
"""Prove the bundled checker with isolated positive and negative repositories."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from repository_inspection import architecture


def main() -> None:
    check = architecture.check
    with tempfile.TemporaryDirectory(prefix="architecture-placement-") as temporary:
        root = Path(temporary) / "project"
        root.mkdir()
        assert check(root)["declared"] is False
        (root / "src/core").mkdir(parents=True)
        (root / "src/app").mkdir(parents=True)
        (root / "src/core/api.py").write_text("value = 1\n", encoding="utf-8")
        (root / "src/app/main.py").write_text("from src.core.api import value\n", encoding="utf-8")
        manifest = {
            "boundaries": [
                {"name": "core", "paths": ["src/core/*"], "may_depend_on": [], "public": ["src/core/api.py"]},
                {"name": "app", "paths": ["src/app/*"], "may_depend_on": ["core"]},
            ],
            "aliases": {},
        }
        manifest_path = root / "architecture.json"

        def write_manifest(value: dict) -> None:
            manifest_path.write_text(json.dumps(value), encoding="utf-8")

        def principles() -> set[str]:
            return {entry["principle"] for entry in check(root)["violations"]}

        write_manifest(manifest)
        result = check(root)
        assert result["declared"] and not result["violations"]
        assert result["observed_edges"] == {"app": ["core"]}

        altered = copy.deepcopy(manifest)
        altered["boundaries"][1]["may_depend_on"] = []
        write_manifest(altered)
        assert "declared-dependency-direction" in principles()

        altered = copy.deepcopy(manifest)
        altered["boundaries"][1]["paths"].append("src/core/*")
        write_manifest(altered)
        assert "one-owner-per-path" in principles()

        altered = copy.deepcopy(manifest)
        altered["boundaries"][0]["may_depend_on"] = ["app"]
        write_manifest(altered)
        assert "no-cycles" in principles()

        write_manifest(manifest)
        (root / "src/core/internal.py").write_text("value = 1\n", encoding="utf-8")
        (root / "src/app/main.py").write_text("from src.core.internal import value\n", encoding="utf-8")
        assert "public-surface-only" in principles()

        (root / "src/app/main.py").write_text("from .missing import value\n", encoding="utf-8")
        assert any("did not resolve" in note for note in check(root)["notes"])
        (root / "src/app/main.py").write_text("from src.core.api import value\n", encoding="utf-8")

        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ""}
        command = [sys.executable, "-I", "-m", "repository_inspection.architecture"]
        arguments = [*command, "--root", str(root), "--json"]
        result = subprocess.run(arguments, cwd=temporary, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["violations"] == []

        manifest_path.write_text("{invalid", encoding="utf-8")
        result = subprocess.run(arguments, cwd=temporary, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 2 and "not valid JSON" in result.stderr
        result = subprocess.run(command, cwd=temporary, env=environment,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 2 and "--root" in result.stderr
    print("architecture-placement selftest: PASS (positive graph, five negative fixtures, CLI isolation)")


if __name__ == "__main__":
    main()