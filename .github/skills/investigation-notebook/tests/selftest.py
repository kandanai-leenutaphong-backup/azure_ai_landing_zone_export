#!/usr/bin/env python3
"""Prove the installed package works with independently owned notebook data."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

def run(repo: Path, *args: str) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, "-I", "-m", "investigation_notebook",
         "--root", str(repo / "docs" / "notebook"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    stream = result.stdout if result.returncode == 0 else result.stderr
    try:
        payload = json.loads(stream)
    except json.JSONDecodeError:
        payload = {"raw": stream}
    return result.returncode, payload


def note_body() -> dict:
    return {
        "schema_version": 3,
        "title": "Fresh notebook installation",
        "question": "Does the copied mechanism work from docs/notebook?",
        "summary": "The copied notebook mechanism supports publication and retrieval.",
        "system": "repository-tooling",
        "type": "method",
        "segment": "agent",
        "content": "## Result\nThe fresh installation works through its CLI.",
        "confidence": "high",
        "tags": ["selftest"],
        "scope": {"repository": "selftest", "paths": ["docs/notebook/notebook.py"]},
        "findings": [
            {
                "statement": "A fresh copied mechanism publishes and retrieves a valid note.",
                "evidence": [
                    {
                        "type": "command",
                        "reference": "python3 docs/notebook/notebook.py check",
                        "detail": "The fresh corpus passed validation.",
                    }
                ],
                "implications": ["The mechanism remains installable without edits."],
            }
        ],
        "open_questions": [],
        "related_notes": [],
        "supersedes": [],
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"ok   {message}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        target = repo / "docs" / "notebook"
        target.mkdir(parents=True)

        require(run(repo, "stats")[1].get("notes") == 0, "fresh notebook starts empty")

        code, created = run(
            repo,
            "new",
            "Draft path check",
            "--question",
            "Does new use the relocated root?",
            "--system",
            "repository-tooling",
            "--type",
            "method",
            "--segment",
            "agent",
        )
        require(code == 0, "new succeeds")
        require((target / created["draft"]).is_file(), "new writes beneath docs/notebook")

        draft = target / "drafts" / "candidate.json"
        draft.write_text(json.dumps(note_body(), indent=2), encoding="utf-8")
        code, published = run(repo, "publish", str(draft))
        require(code == 0 and published.get("id", "").startswith("note-"), "publish assigns an id")

        code, found = run(repo, "search", "copied mechanism")
        require(code == 0 and found.get("count") == 1, "conjunctive search retrieves the note")

        code, checked = run(repo, "check")
        require(code == 0 and checked.get("valid_notes") == 1, "check validates the corpus")

        code, refused = run(repo, "search", "anything", "--system", "not-a-system")
        require(code != 0 and "error" in refused, "unknown category is refused")

        code, closed = run(
            repo,
            "status",
            published["id"],
            "--to",
            "inactive",
            "--reason",
            "Fresh-install lifecycle test completed.",
        )
        require(code == 0 and closed.get("status") == "inactive", "status transition persists")

        require(not (target / "notebook.py").exists(), "data root contains no copied mechanism")
        require(not (target / "note.schema.json").exists(), "schema stays in the installed package")

    print("selftest passed: 10 checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
