#!/usr/bin/env python3
"""Prove recovery across MCP process restarts, and refusal to overwrite or traverse."""

import asyncio
import json
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

@asynccontextmanager
async def session(config):
    parameters = StdioServerParameters(command=sys.executable,
        args=["-I", "-B", "-m", "workrecovery.mcp", "--config", str(config)], cwd=str(config.parent))
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
            assert (await client.initialize()).serverInfo.name == "recoverable-jobs"
            yield client


async def check():
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        async with session(config) as client:
            assert {tool.name for tool in (await client.list_tools()).tools} == {
                "recovery_status", "recovery_stage", "recovery_list", "recovery_read",
            }
            assert not (await client.call_tool("recovery_status", {})).isError
            assert (await client.call_tool("recovery_stage", {"run_id": "one", "payload_json": "{}"})).isError
            assert (await client.call_tool("recovery_list", {})).isError
            assert not (Path(directory) / "artifacts").exists()
        config.write_text(json.dumps({"allow_stage": True, "allow_inspect": True,
                                      "allow_payload_reads": True, "max_payload_bytes": 256}))
        async with session(config) as client:
            staged = await client.call_tool("recovery_stage", {"run_id": "one", "payload_json": '{"rows": [1, 2]}'})
            assert not staged.isError, staged
            assert json.loads(staged.content[0].text)["saved"] is False
            assert (await client.call_tool("recovery_stage", {"run_id": "one", "payload_json": '{"different": true}'})).isError
            for name, arguments in [
                ("recovery_read", {"run_id": "../outside"}),
                ("recovery_read", {"run_id": "one", "path": "/outside"}),
                ("recovery_stage", {"run_id": "large", "payload_json": '"' + "x" * 300 + '"'}),
                ("recovery_delete", {"run_id": "one"}),
            ]:
                assert (await client.call_tool(name, arguments)).isError
        async with session(config) as client:
            recovered = await client.call_tool("recovery_read", {"run_id": "one"})
            assert not recovered.isError, recovered
            assert json.loads(recovered.content[0].text)["payload"] == {"rows": [1, 2]}
            listing = await client.call_tool("recovery_list", {})
            assert len(json.loads(listing.content[0].text)["artifacts"]) == 1
            artifact_path = Path(directory) / "artifacts/one.artifact.json"
            document = json.loads(artifact_path.read_text())
            document["content_sha256"] = "0" * 64
            artifact_path.write_text(json.dumps(document))
            assert (await client.call_tool("recovery_read", {"run_id": "one"})).isError
            assert artifact_path.exists()
            assert not (await client.call_tool("recovery_status", {})).isError
    print("MCP selftest: PASS (recovery grants, stage/restart/read, no-clobber, bounds, integrity, no deletion)")


if __name__ == "__main__":
    asyncio.run(check())