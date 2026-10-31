#!/usr/bin/env python3
"""Preserve and inspect completed output through a bounded local MCP adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
from itertools import islice
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ConfigDict, Field

from workrecovery import ArtifactStore, RecoveryError, artifact_ceiling, encode_payload


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    recovery_root: str = ""
    allow_stage: bool = False
    allow_inspect: bool = False
    allow_payload_reads: bool = False
    max_payload_bytes: int = Field(default=131072, ge=1, le=1048576)
    max_scan_entries: int = Field(default=200, ge=1, le=2000)


class RecoveryTools:
    def __init__(self, settings: Settings, config: Path) -> None:
        self.settings = settings
        directory = Path(settings.recovery_root) if settings.recovery_root else config.parent / "artifacts"
        if not directory.is_absolute():
            raise ValueError("recovery_root must be absolute")
        self.store = ArtifactStore(directory, max_artifact_bytes=artifact_ceiling(settings.max_payload_bytes))

    def status(self) -> dict[str, Any]:
        return {"recovery_root": str(self.store.root), "allow_stage": self.settings.allow_stage,
                "allow_inspect": self.settings.allow_inspect,
                "allow_payload_reads": self.settings.allow_payload_reads,
                "destination_store_configured": False, "max_payload_bytes": self.settings.max_payload_bytes}

    def bound_scan(self) -> None:
        if self.store.root.is_symlink():
            raise PermissionError("Recovery root must not be a symlink")
        if self.store.root.exists():
            entries = list(islice(self.store.root.iterdir(), self.settings.max_scan_entries + 1))
            if len(entries) > self.settings.max_scan_entries:
                raise PermissionError("Recovery directory exceeds the configured scan bound")

    def stage(self, run_id: str, payload_json: str) -> dict[str, Any]:
        if not self.settings.allow_stage:
            raise PermissionError("Staging needs the operator's allow_stage grant")
        self.bound_scan()
        if len(payload_json.encode("utf-8")) > self.settings.max_payload_bytes:
            raise PermissionError("Payload exceeds the configured byte limit")
        payload = json.loads(payload_json)
        content, _ = encode_payload(payload)
        if len(content) > self.settings.max_payload_bytes:
            raise PermissionError("Encoded payload exceeds the configured byte limit")
        artifact = self.store.stage(run_id, payload)
        return {"state": "preserved", "saved": False, "artifact": artifact.summary()}

    def listing(self) -> dict[str, Any]:
        if not self.settings.allow_inspect:
            raise PermissionError("Inspection needs the operator's allow_inspect grant")
        self.bound_scan()
        return {"artifacts": [artifact.summary() for artifact in self.store.list()],
                "unreadable_count": len(self.store.problems()), "saved": False}

    def read(self, run_id: str) -> dict[str, Any]:
        if not self.settings.allow_payload_reads:
            raise PermissionError("Payload reads need the operator's allow_payload_reads grant")
        self.bound_scan()
        artifact = self.store.read_run(run_id)
        if artifact.content_type != "application/json":
            raise PermissionError("MCP reads JSON artifacts only; use the Python API for bytes")
        return {"artifact": artifact.summary(), "payload": artifact.payload}


RUN_ID = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$"}
TOOLS = [
    types.Tool(name="recovery_status", description="Report local recovery settings without creating artifacts.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="recovery_list", description="List bounded recovery metadata; unreadable artifacts are reported, not deleted.",
               inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
    types.Tool(name="recovery_stage", description="Preserve completed JSON output locally without overwriting an existing run ID. This is not a destination-store commit.",
               inputSchema={"type": "object", "properties": {
                   "run_id": RUN_ID, "payload_json": {"type": "string", "minLength": 1, "maxLength": 1048576}},
                   "required": ["run_id", "payload_json"], "additionalProperties": False}),
    types.Tool(name="recovery_read", description="Read and verify one preserved JSON artifact by run ID, never by a caller-supplied path.",
               inputSchema={"type": "object", "properties": {"run_id": RUN_ID},
                   "required": ["run_id"], "additionalProperties": False}),
]


async def serve(application: RecoveryTools, config: Path) -> None:
    server = Server("recoverable-jobs", version="1.0.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return TOOLS

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if name == "recovery_status":
                payload = {**application.status(), "config_file": str(config)}
            elif name == "recovery_list":
                payload = await asyncio.to_thread(application.listing)
            elif name == "recovery_stage":
                payload = await asyncio.to_thread(application.stage, **arguments)
            elif name == "recovery_read":
                payload = await asyncio.to_thread(application.read, **arguments)
            else:
                payload = {"error": "unknown_tool"}
        except PermissionError as error:
            payload = {"error": "permission_denied", "detail": str(error)}
        except RecoveryError as error:
            payload = {"error": type(error).__name__}
        except Exception:
            payload = {"error": "invalid_artifact"}
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload, allow_nan=False))],
                                    isError=bool(payload.get("error")))

    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    options = parser.parse_args()
    if options.config is None:
        parser.error("--config is required")
    config = options.config.resolve()
    try:
        values = json.loads(config.read_text()) if config.exists() else {}
        application = RecoveryTools(Settings.model_validate(values), config)
    except (OSError, ValueError):
        parser.exit(2, "Invalid recovery MCP configuration\n")
    asyncio.run(serve(application, config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())