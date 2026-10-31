#!/usr/bin/env python3
"""Validate and round-trip the actual MCP server; no hosted application is exposed."""

import asyncio
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def check():
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        config.write_text(json.dumps({"max_document_bytes": 2048}))
        parameters = StdioServerParameters(command=sys.executable,
            args=["-I", "-B", "-m", "appcompose.mcp", "--config", str(config)], cwd=directory)
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
                assert (await client.initialize()).serverInfo.name == "portable-app-composition"
                assert {tool.name for tool in (await client.list_tools()).tools} == {
                    "composition_status", "composition_validate", "composition_demo",
                }
                document = {"schemaVersion": 1, "kind": "portable.app-composition", "name": "Fixture",
                            "members": [{"id": "store", "capability": "notes.store"}]}
                result = await client.call_tool("composition_validate", {"document": json.dumps(document)})
                assert not result.isError, result
                validated = json.loads(result.content[0].text)
                assert validated["dependency_order"] == ["store"]
                again = await client.call_tool("composition_validate", {"document": validated["canonical_json"]})
                assert json.loads(again.content[0].text)["sha256"] == validated["sha256"]
                for arguments in [
                    {"document": json.dumps({**document, "entrypoint": "os.system"})},
                    {"document": "schemaVersion: 1\nschemaVersion: 1\n", "format": "yaml"},
                    {"document": "a" * 2049}, {"document": "{}", "format": "python"},
                    {"document": "{}", "resolve": "os.system"},
                ]:
                    assert (await client.call_tool("composition_validate", arguments)).isError
                demonstration = await client.call_tool("composition_demo", {})
                assert not demonstration.isError, demonstration
                payload = json.loads(demonstration.content[0].text)
                assert payload["fixtures"]
                assert payload["stopped"] == list(reversed(payload["started"]))
                assert payload["second_shutdown"] == []
                assert (await client.call_tool("composition_demo", {"document": "{}"})).isError
                assert not (await client.call_tool("composition_status", {})).isError
    print("MCP selftest: PASS (composition canonical round trip, fixed demo lifecycle, validation refusals)")


if __name__ == "__main__":
    asyncio.run(check())