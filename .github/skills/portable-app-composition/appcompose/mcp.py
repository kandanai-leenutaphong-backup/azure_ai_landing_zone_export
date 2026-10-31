#!/usr/bin/env python3
"""Validate composition documents and exercise a fixed, in-memory allowlisted demo."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ConfigDict, Field

from appcompose import CompositionError, allowlist, canonical_json, compose, from_json, from_yaml
from appcompose.demo.digest import digest_capability
from appcompose.demo.notes import NoteStore, notes_capability


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    max_document_bytes: int = Field(default=131072, ge=1, le=1048576)


def validate(document: str, format: str, settings: Settings) -> dict[str, Any]:
    if len(document.encode("utf-8")) > settings.max_document_bytes:
        raise PermissionError("Document exceeds the configured byte limit")
    parsed = from_json(document) if format == "json" else from_yaml(document)
    canonical = canonical_json(parsed)
    assert canonical_json(from_json(canonical)) == canonical
    return {"valid": True, "dependency_order": list(parsed.order()),
            "canonical_json": canonical.decode("utf-8"), "sha256": hashlib.sha256(canonical).hexdigest()}


def demo() -> dict[str, Any]:
    document = from_yaml(files("appcompose.demo").joinpath("field-notes.yaml").read_text(encoding="utf-8"))
    store = NoteStore()
    events: list[str] = []
    application = compose(document, resolve=allowlist({
        "notes.store": notes_capability(store, title="Notes"),
        "notes.digest": digest_capability(store.all, title="Digest", events=events),
    }))
    started = application.startup()
    try:
        notes = application.dispatch("GET", "/api/notes")
        digest = application.dispatch("GET", "/api/digest")
        response = {"fixtures": True, "started": started,
                    "notes": json.loads(notes.body), "digest": json.loads(digest.body)}
    finally:
        stopped = application.shutdown()
    return {**response, "stopped": stopped, "second_shutdown": application.shutdown()}


TOOLS = [
    types.Tool(name="composition_status", description="Report the document validation bound; no code execution or network.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="composition_validate", description="Validate a composition document and return canonical JSON and dependency order without importing capabilities.",
               inputSchema={"type": "object", "properties": {
                   "document": {"type": "string", "minLength": 1, "maxLength": 1048576},
                   "format": {"type": "string", "enum": ["json", "yaml"], "default": "json"}},
                   "required": ["document"], "additionalProperties": False}),
    types.Tool(name="composition_demo", description="Run the bundled in-memory notes/digest example with its fixed allowlist, then shut it down.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
]


async def serve(settings: Settings, config: Path) -> None:
    server = Server("portable-app-composition", version="1.1.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "composition_status":
                result = {"config_file": str(config), "max_document_bytes": settings.max_document_bytes,
                          "arbitrary_execution": False, "network": False}
            elif name == "composition_validate":
                result = validate(arguments["document"], arguments.get("format", "json"), settings)
            elif name == "composition_demo":
                result = demo()
            else:
                result = {"error": "unknown_tool"}
        except CompositionError as error:
            result = {"error": type(error).__name__, "field": getattr(error, "field", None)}
        except PermissionError:
            result = {"error": "document_too_large"}
        except Exception:
            result = {"error": "invalid_document"}
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result))],
                                    isError=bool(result.get("error")))

    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    arguments = parser.parse_args()
    if arguments.config is None:
        parser.error("--config is required")
    try:
        settings = Settings.model_validate(json.loads(arguments.config.read_text()) if arguments.config.exists() else {})
    except (OSError, ValueError):
        parser.exit(2, "Invalid composition MCP settings\n")
    asyncio.run(serve(settings, arguments.config.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())