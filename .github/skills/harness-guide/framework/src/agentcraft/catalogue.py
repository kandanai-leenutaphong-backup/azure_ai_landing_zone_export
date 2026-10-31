"""Read installed capability metadata; repository-inspection owns task discovery."""

from __future__ import annotations

from importlib import resources
import hashlib
import json
from pathlib import Path
from typing import Any


def _source_root() -> Path | None:
    module = Path(__file__).resolve()
    layout = Path(".github/skills/harness-guide/framework/src/agentcraft/catalogue.py")
    if len(module.parents) < len(layout.parts):
        return None
    root = module.parents[len(layout.parts) - 1]
    return root if module == root / layout else None


def load_catalogue() -> dict[str, Any]:
    """Read canonical checkout metadata or an external installed snapshot."""
    root = _source_root()
    if root is not None:
        from repository_inspection.catalogue import contained_file

        resource = contained_file(root, "libraries/capabilities.json")
    else:
        resource = resources.files("agentcraft").joinpath("capabilities.json")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Installed capability catalogue must declare schema_version 1")
    if not isinstance(document.get("capabilities"), list) or not isinstance(document.get("skills"), list):
        raise ValueError("Installed capability catalogue is incomplete")
    if root is not None:
        document["generation"] = {"source": "libraries/capabilities.json",
                                  "sha256": hashlib.sha256(resource.read_bytes()).hexdigest(),
                                  "discovery": "workspace-source"}
    return document


def guidance_root() -> Path:
    """Return the fixed checkout catalogue root or external installed guidance."""
    source = _source_root()
    if source is not None:
        return source / ".github"
    root = Path(str(resources.files("agentcraft").joinpath("guidance")))
    if not root.is_dir():
        raise FileNotFoundError("Installed Agentcraft guidance is missing; use a generated wheel installation")
    return root


def report(*, query: str | None = None, name: str | None = None,
           kind: str | None = None, limit: int = 5) -> dict[str, Any]:
    """List/search/read tasks with the existing reader's schema and integrity checks.

    Requires the declared repository-inspection tooling dependency. Unknown names,
    invalid searches and tampered or escaping guidance raise ValueError. No caller
    can supply another root, source path, credential or execution grant.
    """
    try:
        from repository_inspection.catalogue import report as catalogue_report
    except ModuleNotFoundError as error:
        if error.name in {"repository_inspection", "repository_inspection.catalogue"}:
            raise RuntimeError("Catalogue search/read requires repository-inspection from the declared agentcraft[tooling] artifact set") from error
        raise
    root = guidance_root()
    if _source_root() is not None:
        from repository_inspection.catalogue import document

        view = document(root, "skills/catalogue.json", versions=(2,))
        generation = view.get("generation")
    else:
        generation = load_catalogue()["generation"]
    result = catalogue_report(root, query=query, name=name, kind=kind, limit=limit)
    return {**result, "generation": generation}


__all__ = ["load_catalogue", "guidance_root", "report"]