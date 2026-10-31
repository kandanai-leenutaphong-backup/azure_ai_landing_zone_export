"""Real SDK round trips against installed public owners, with network refused."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx
from appcompose import CompositionError, DocumentInvalid, UnsupportedVersion
from appcompose.mcp import TOOLS, Settings
from azdata import (
    ConnectorConfig, ContentValue, ErrorInfo, HttpResponse, ItemResult, Limits,
    OperationResult, Policy, RecordKey, ResourceAddress, connect,
)
from azure.core.credentials import AccessToken
from llm_interface import Limits as ModelLimits, LlmError, connect as connect_model
from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from resource_explorer import (
    InventoryRegistry, InventoryService, InventorySource, ProbeReport,
    SourceBinding, UseCase, parse_selection, source_node,
)
from resource_explorer.content import ContentPayload, ContentResult, collected_now
from workrecovery import (
    ArtifactCorrupt, ArtifactExists, ArtifactMissing, InvalidRunId, PayloadNotSupported,
    PayloadTooLarge, RecoveryError, StagingFailed, StaleArtifact, StoreError,
    StoreOccupied, StoreRefused, StoreTimeout, StoreUnavailable,
)
from workrecovery.mcp import RecoveryTools, Settings as RecoverySettings

from agentcraft import Binding, CallerContext, ExecutionContext, FrameworkError
from agentcraft.mcp import create_server


def execution(**limits):
    return ExecutionContext.create(CallerContext("fixture-principal"),
                                   limits={"tool_calls": 100, **limits})


def composition_server(context=None, grants=None):
    return create_server(
        bindings={"local": Binding("composition", Settings(max_document_bytes=2048))},
        grants={"local": tuple(tool.name for tool in TOOLS)} if grants is None else grants,
        principal="fixture-principal", context=context or execution(),
    )


def contents(result):
    return json.loads(result.content[0].text)


class Credential:
    def __init__(self):
        self.calls = 0
        self.closed = 0

    def get_token(self, scope, **kwargs):
        self.calls += 1
        return AccessToken("fixture-token", 2**31)

    def close(self):
        self.closed += 1


class SearchTransport:
    def __init__(self):
        self.requests = []
        self.closed = 0

    async def request(self, request):
        self.requests.append(request)
        return HttpResponse(200, {"value": [{"id": "one", "title": "Fixture"}]})

    async def aclose(self):
        self.closed += 1


def data_connector(transport, credential, grants=frozenset({"query"})):
    return connect("search", ConnectorConfig("https://fixture.search.windows.net",
        ResourceAddress({"index": "fixed"}), ("fixture.search.windows.net",)),
        credential=credential, transport=transport,
        policy=Policy("fixture-principal", grants=grants, limits=Limits(max_items=3)))


class ModelTransport(httpx.MockTransport):
    def __init__(self):
        self.requests = []
        self.closed = 0
        super().__init__(self.respond)

    async def respond(self, request):
        self.requests.append(request)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"object": "list", "model": "fixture-vectors", "data": [
                {"object": "embedding", "index": index, "embedding": [float(index), 1.0]} for index in (1, 0)],
                "usage": {"prompt_tokens": 2, "total_tokens": 2}})
        return httpx.Response(200, json={
            "id": "fixture-response", "object": "chat.completion", "created": 1, "model": "fixture-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Fixture answer"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        })

    async def aclose(self):
        self.closed += 1
        await super().aclose()


def model_connection(transport, credential, *, allow=True):
    return connect_model("https://fixture.invalid", "fixture-model", credential=credential,
        provider="azure_completions", embedding_model="fixture-vectors", allow_model_calls=allow,
        transport=transport, limits=ModelLimits(max_output_tokens=64))


class InventoryProbe:
    def __init__(self):
        self.calls = []

    async def metadata(self, source):
        self.calls.append(("metadata", source.source_id))
        return ProbeReport(status="ok", total_rows=3, schema_fields=({"name": "id", "type": "string"},))

    async def preview(self, source, *, limit):
        self.calls.append(("preview", source.source_id, limit))
        return ContentResult(service="fixture", kind="rows", status="ok", collected_at=collected_now(),
            payload=ContentPayload(form="rows", media_type="application/json",
                rows=tuple({"id": str(index)} for index in range(min(3, limit))), columns=("id",), size_bytes=3))


def inventory_service(probe):
    sources = tuple(InventorySource(identifier, "fixture", identifier, "local_table", "Synthetic rows",
        ("metadata", "preview") if identifier == "rows" else ("metadata",),
        SourceBinding("fixture", coordinates={"table": "fixed"}), provenance="Synthetic test fixture.")
        for identifier in ("rows", "metadata"))
    return InventoryService(InventoryRegistry([UseCase("fixture", "Fixture", "", sources)]), {"fixture": probe})


class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("network forbidden")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("network forbidden")))

    def assert_failure(self, result, context, capability, operation, *, code, category,
                       effect, retry, key="error", index=0):
        self.assertTrue(result.isError, result)
        payload = contents(result)
        self.assertEqual(payload, result.structuredContent)
        failure = payload[key][index] if isinstance(payload[key], list) else payload[key]
        self.assertEqual(failure["code"], code)
        self.assertEqual(failure["category"], category)
        self.assertEqual(failure["capability_id"], capability)
        self.assertEqual(failure["operation"], operation)
        self.assertEqual(failure["run_id"], context.run_id)
        for field in ("code", "category", "capability_id", "operation", "run_id", "action"):
            self.assertIsInstance(failure[field], str)
            self.assertTrue(failure[field].strip(), field)
        self.assertEqual(failure["effect"], effect)
        self.assertEqual(failure["retry"], retry)
        self.assertNotIn("private-provider-payload", json.dumps(failure))
        return failure

    async def test_host_failure_routes_and_document_fields(self):
        for error, code, category, effect, retry, field in (
            (DocumentInvalid("members[2].requires[0]", "private-provider-payload"),
             "invalid_document", "invalid", "none", "safe_after_correction", "members[2].requires[0]"),
            (DocumentInvalid("members[private-provider-payload].settings", "private-provider-payload"),
             "invalid_document", "invalid", "none", "safe_after_correction", "document"),
            (DocumentInvalid("members" + ".settings" * 100, "private-provider-payload"),
             "invalid_document", "invalid", "none", "safe_after_correction", "document"),
            (UnsupportedVersion("schemaVersion", "private-provider-payload"),
             "unsupported_version", "unsupported", "none", "never", "schemaVersion"),
            (CompositionError("private-provider-payload"),
             "composition_failed", "failed", "unknown", "unspecified", None),
            (PermissionError("private-provider-payload"),
             "permission_denied", "denied", "none", "safe_after_correction", None),
            (TimeoutError("private-provider-payload"),
             "deadline_exceeded", "interrupted", "unknown", "unspecified", None),
            (FrameworkError("deadline_exceeded", category="interrupted"),
             "deadline_exceeded", "interrupted", "unknown", "unspecified", None),
            (RuntimeError("private-provider-payload"),
             "operation_failed", "failed", "unknown", "unspecified", None),
        ):
            with self.subTest(code=code, field=field), patch("appcompose.mcp.validate", side_effect=error):
                context = execution()
                async with create_connected_server_and_client_session(composition_server(context)) as client:
                    result = await client.call_tool("composition_validate", {"binding": "local", "document": "{}"})
                    failure = self.assert_failure(result, context, "composition", "composition_validate",
                        code=code, category=category, effect=effect, retry=retry)
                    self.assertEqual(failure["field"], field)
                    self.assertNotIn("private-provider-payload", result.model_dump_json())

    async def test_native_call_tool_result_keeps_error_flag_and_content(self):
        for is_error, structured in ((False, True), (True, True), (False, False), (True, False)):
            body = {"error": "native_status", "rows": [{"text": "private-provider-payload"}]}
            native = types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(body)),
                         types.TextContent(type="text", text="authorized non-body text")],
                structuredContent=body if structured else None, isError=is_error,
            )
            context = execution()
            with patch("appcompose.mcp.validate", return_value=native):
                async with create_connected_server_and_client_session(composition_server(context)) as client:
                    result = await client.call_tool("composition_validate", {"binding": "local", "document": "{}"})
                    self.assertEqual(result.isError, is_error)
                    self.assertEqual(contents(result) if structured or is_error else None, result.structuredContent)
                    self.assertEqual(contents(result)["rows"], body["rows"])
                    self.assertEqual(result.content[1].text, "authorized non-body text")
                    if is_error:
                        self.assert_failure(result, context, "composition", "composition_validate",
                            code="operation_failed", category="failed", effect="unknown", retry="unspecified", key="failure")
                    else:
                        self.assertEqual(contents(result), body)

    async def test_composition_discover_validate_demo_and_refusals(self):
        server = composition_server()
        async with create_connected_server_and_client_session(server) as client:
            self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                             {tool.name for tool in TOOLS})
            document = {"schemaVersion": 1, "kind": "portable.app-composition", "name": "Fixture",
                        "members": [{"id": "notes", "capability": "notes.store"}]}
            result = await client.call_tool("composition_validate", {
                "binding": "local", "document": json.dumps(document),
            })
            self.assertFalse(result.isError, result)
            self.assertEqual(contents(result)["dependency_order"], ["notes"])
            again = await client.call_tool("composition_validate", {
                "binding": "local", "document": contents(result)["canonical_json"],
            })
            self.assertEqual(contents(again)["sha256"], contents(result)["sha256"])
            for request in (
                {"binding": "missing", "document": "{}"},
                {"binding": "local", "document": "{}", "resolve": "os.system"},
                {"binding": "local", "document": "{}", "format": "python"},
                {"binding": "local", "document": "a" * 2049},
                {"binding": "local", "document": json.dumps({**document, "entrypoint": "os.system"})},
                {"binding": "local", "document": "schemaVersion: 1\nschemaVersion: 1\n", "format": "yaml"},
            ):
                with self.subTest(request=request):
                    self.assertTrue((await client.call_tool("composition_validate", request)).isError)
            demonstration = await client.call_tool("composition_demo", {"binding": "local"})
            self.assertFalse(demonstration.isError, demonstration)
            payload = contents(demonstration)
            self.assertTrue(payload["fixtures"])
            self.assertEqual(payload["stopped"], list(reversed(payload["started"])))
            self.assertEqual(payload["second_shutdown"], [])

    async def test_grants_and_shared_tool_budget(self):
        context = execution(tool_calls=1)
        server = composition_server(context, {"local": ("composition_status",)})
        async with create_connected_server_and_client_session(server) as client:
            self.assertEqual([tool.name for tool in (await client.list_tools()).tools], ["composition_status"])
            for tool, request in (("composition_demo", {"binding": "local"}),
                                  ("unknown", {}),
                                  ("composition_status", {"binding": "local", "principal": "other"})):
                self.assertTrue((await client.call_tool(tool, request)).isError)
            for tool, request, capability, operation in (
                ("composition_demo", {"binding": "local"}, "composition", "composition_demo"),
                ("unknown", {}, "framework", "unknown_tool"),
            ):
                result = await client.call_tool(tool, request)
                self.assert_failure(result, context, capability, operation, code="tool_not_granted",
                    category="denied", effect="none", retry="safe_after_correction")
            self.assertEqual(context.budget.snapshot()["reserved"]["tool_calls"], 0)
            self.assertFalse((await client.call_tool("composition_status", {"binding": "local"})).isError)
            exhausted = await client.call_tool("composition_status", {"binding": "local"})
            self.assertTrue(exhausted.isError)
            self.assertEqual(contents(exhausted)["error"]["code"], "budget_exhausted")
            self.assertEqual(contents(exhausted), exhausted.structuredContent)
            failure = contents(exhausted)["error"]
            self.assertEqual(failure["capability_id"], "composition")
            self.assertEqual(failure["operation"], "composition_status")
            self.assertEqual(failure["run_id"], context.run_id)
            self.assertEqual(failure["effect"], "none")
            self.assertEqual(failure["retry"], "safe_after_correction")
            self.assertTrue(failure["action"])
            self.assertEqual(context.budget.snapshot()["reserved"]["tool_calls"], 1)

    async def test_malformed_domain_input_refusals_are_correlated(self):
        context = execution()
        async with create_connected_server_and_client_session(composition_server(context)) as client:
            for document in (
                "{private-provider-payload",
                json.dumps({"schemaVersion": 1, "kind": "portable.app-composition", "name": "Fixture",
                            "members": [{"id": [], "capability": "private-provider-payload"}]}),
                json.dumps({"schemaVersion": 1, "kind": "portable.app-composition", "name": "Fixture",
                            "private-provider-payload": "secret", "members": [{"id": "notes", "capability": "notes.store"}]}),
            ):
                result = await client.call_tool("composition_validate", {"binding": "local", "document": document})
                self.assert_failure(result, context, "composition", "composition_validate", code="invalid_document",
                    category="invalid", effect="none", retry="safe_after_correction")
                self.assertNotIn("private-provider-payload", result.model_dump_json())
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            root = Path(directory) / "artifacts"
            application = RecoveryTools(RecoverySettings(recovery_root=str(root), allow_stage=True), Path(directory) / "config.json")
            server = create_server(bindings={"recovery": Binding("recovery", application)},
                grants={"recovery": ("recovery_stage",)}, principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool("recovery_stage", {
                    "binding": "recovery", "run_id": "one", "payload_json": "{private-provider-payload",
                })
                failure = self.assert_failure(result, context, "recovery", "recovery_stage", code="invalid_payload_json",
                    category="invalid", effect="none", retry="safe_after_correction")
                self.assertEqual(failure["field"], "payload_json")
                self.assertNotIn("private-provider-payload", result.model_dump_json())
                self.assertFalse(root.exists())

    async def test_sdk_schema_validator_remains_a_protocol_refusal(self):
        context = execution()
        with patch("appcompose.mcp.validate") as validate:
            async with create_connected_server_and_client_session(composition_server(context)) as client:
                result = await client.call_tool("composition_validate", {"binding": "local", "document": 42})
                self.assertTrue(result.isError)
                self.assertIsNone(result.structuredContent)
                validate.assert_not_called()
                self.assertEqual(context.budget.snapshot()["reserved"]["tool_calls"], 0)

    async def test_data_public_engine_success_refusals_budget_and_owned_cleanup(self):
        credential, transport = Credential(), SearchTransport()
        connector = data_connector(transport, credential)
        context = execution(data_calls=1)
        server = create_server(bindings={"search": Binding("data", connector, owned=True)},
            grants={"search": ("data_status", "data_query")}, principal="fixture-principal", context=context)
        self.assertEqual(credential.calls, 0)
        async with create_connected_server_and_client_session(server) as client:
            self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                             {"data_status", "data_query"})
            status = await client.call_tool("data_status", {"binding": "search"})
            self.assertEqual(contents(status)["availability"], "unverified")
            self.assertEqual(credential.calls, 0)
            request = {"binding": "search", "dialect": "search", "expression": "*"}
            for invalid in (
                {**request, "binding": "missing"}, {**request, "dialect": "kql"},
                {**request, "expression": 42}, {**request, "target": {"index": "other"}},
                {**request, "endpoint": "https://other.example"}, {**request, "credential": "secret"},
                {**request, "grants": ["create"]}, {**request, "limits": {"max_items": 4}},
                {**request, "service_options": {"search": {"index": "other"}}},
            ):
                with self.subTest(invalid=invalid):
                    self.assertTrue((await client.call_tool("data_query", invalid)).isError)
            self.assertEqual(transport.requests, [])
            self.assertEqual(credential.calls, 0)
            result = await client.call_tool("data_query", {**request, "limits": {"max_items": 1}})
            self.assertFalse(result.isError, result)
            self.assertEqual(contents(result)["items"][0]["content"]["data"]["id"], "one")
            self.assertEqual(contents(result)["target"]["coordinates"], {"index": "fixed"})
            self.assertEqual(len(transport.requests), 1)
            self.assertIn("fixture.search.windows.net", transport.requests[0].url)
            exhausted = await client.call_tool("data_query", request)
            self.assertTrue(exhausted.isError)
            self.assertEqual(contents(exhausted)["errors"][0]["code"], "budget_exhausted")
            self.assert_failure(exhausted, context, "data", "data_query", code="budget_exhausted",
                category="denied", effect="none", retry="safe_after_correction", key="failures")
            self.assertEqual(context.budget.snapshot()["reserved"]["data_calls"], 1)
            self.assertEqual(len(transport.requests), 1)
        self.assertEqual((credential.closed, transport.closed), (0, 0))
        from azdata import QueryRequest
        closed = await connector.query(QueryRequest(dialect="search", expression="*"))
        self.assertEqual(closed.errors[0].code, "connector_closed")
        await connector.aclose()

    async def test_data_host_grant_and_native_policy_both_required(self):
        credential, transport = Credential(), SearchTransport()
        connector = data_connector(transport, credential, grants=frozenset())
        for grants in ({}, {"search": ("data_query",)}):
            context = execution(data_calls=1)
            server = create_server(bindings={"search": Binding("data", connector)},
                grants=grants, principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool("data_query", {
                    "binding": "search", "dialect": "search", "expression": "*",
                })
                self.assertTrue(result.isError)
                if grants:
                    self.assertEqual(contents(result)["status"], "denied")
                    self.assertEqual(contents(result)["errors"][0]["code"], "operation_not_granted")
                    self.assert_failure(result, context, "data", "data_query", code="operation_not_granted",
                        category="denied", effect="none", retry="safe_after_correction", key="failures")
                else:
                    self.assertEqual((await client.list_tools()).tools, [])
                self.assertEqual(context.budget.snapshot()["reserved"]["data_calls"], 0)
        self.assertEqual((credential.calls, transport.requests), (0, []))
        await connector.aclose()

    async def test_data_native_partial_effects_and_retry_metadata(self):
        credential, transport = Credential(), SearchTransport()
        connector = data_connector(transport, credential)
        items = (
            ItemResult(4, RecordKey({"id": "first"}), "success",
                       content=ContentValue({"error": "private-provider-payload"}), effect="accepted"),
            ItemResult(1, RecordKey({"id": "second"}), "unknown",
                       error=ErrorInfo("transport_unavailable", "unknown"), effect="unknown"),
            ItemResult(9, RecordKey({"id": "tail"}), "failed",
                       error=ErrorInfo("not_attempted", "failed"), effect="none"),
        )
        native = OperationResult("native-request", "upsert", "search", ResourceAddress({"index": "fixed"}),
            "partial", items=items, errors=(items[1].error,), metrics={"attempts": 1})
        context = execution(data_calls=1)
        with patch.object(connector, "query", return_value=native):
            server = create_server(bindings={"fixed-search": Binding("data", connector)},
                grants={"fixed-search": ("data_query",)}, principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool("data_query", {
                    "binding": "fixed-search", "dialect": "search", "expression": "*",
                })
                self.assertEqual({key: value for key, value in contents(result).items() if key != "failures"}, native.to_dict())
                for index, field in ((0, "errors[0]"), (1, "items[1]")):
                    failure = self.assert_failure(result, context, "data", "data_query", code="transport_unavailable",
                        category="unavailable", effect="unknown", retry="read_back_first", key="failures", index=index)
                    self.assertEqual(failure["field"], field)
                self.assert_failure(result, context, "data", "data_query", code="not_attempted",
                    category="failed", effect="none", retry="never", key="failures", index=2)
                self.assertEqual([item["index"] for item in contents(result)["items"]], [4, 1, 9])
                self.assertIn("private-provider-payload", result.model_dump_json())
        self.assertEqual((credential.calls, transport.requests), (0, []))
        await connector.aclose()

    async def test_data_native_status_and_retryable_boolean_mapping(self):
        connector = data_connector(SearchTransport(), Credential())
        cases = (
            ("query", "unsupported", ErrorInfo("dialect_unsupported", "unsupported", True), "none", "unsupported", "never"),
            ("query", "invalid", ErrorInfo("invalid_request", "invalid"), "none", "invalid", "safe_after_correction"),
            ("query", "failed", ErrorInfo("rate_limited", "failed", True), "none", "rate-limit", "unspecified"),
            ("query", "failed", ErrorInfo("rate_limited", "failed", False), "none", "rate-limit", "never"),
            ("read", "not_found", ErrorInfo("record_not_found", "not_found"), "none", "failed", "never"),
            ("upsert", "unknown", ErrorInfo("transport_unavailable", "unknown"), "unknown", "unavailable", "read_back_first"),
            ("upsert", "pending", None, "accepted", "failed", "read_back_first"),
        )
        for operation, status, error, effect, category, retry in cases:
            with self.subTest(operation=operation, status=status, retry=retry):
                items = (ItemResult(0, RecordKey({"id": "one"}), "pending", effect="accepted"),) if status == "pending" else ()
                native = OperationResult("native-request", operation, "search", ResourceAddress({"index": "fixed"}),
                    status, items=items, errors=(error,) if error else (), metrics={"attempts": 1})
                context = execution()
                with patch.object(connector, "query", return_value=native):
                    server = create_server(bindings={"search": Binding("data", connector)},
                        grants={"search": ("data_query",)}, principal="fixture-principal", context=context)
                    async with create_connected_server_and_client_session(server) as client:
                        result = await client.call_tool("data_query", {"binding": "search", "dialect": "search", "expression": "*"})
                        self.assert_failure(result, context, "data", "data_query", code=error.code if error else status,
                            category=category, effect=effect, retry=retry, key="failures")
                        self.assertEqual({key: value for key, value in contents(result).items() if key != "failures"}, native.to_dict())
        await connector.aclose()

    async def test_data_provider_failure_has_safe_native_code_and_correlation(self):
        for response, code, category, retry in (
            (HttpResponse(429, {"error": "private-provider-payload"}), "rate_limited", "rate-limit", "never"),
            (HttpResponse(500, {"error": "private-provider-payload"}), "provider_failure", "failed", "never"),
        ):
            transport = SearchTransport()
            connector = data_connector(transport, Credential())
            context = execution(data_calls=1)
            with patch.object(transport, "request", return_value=response) as request:
                server = create_server(bindings={"data": Binding("data", connector, owned=True)},
                    grants={"data": ("data_query",)}, principal="fixture-principal", context=context)
                async with create_connected_server_and_client_session(server) as client:
                    result = await client.call_tool("data_query", {"binding": "data", "dialect": "search", "expression": "*"})
                    self.assert_failure(result, context, "data", "data_query", code=code,
                        category=category, effect="none", retry=retry, key="failures")
                    self.assertNotIn("private-provider-payload", result.model_dump_json())
                    request.assert_awaited_once()

    async def test_model_public_engine_chat_embed_and_shared_budget(self):
        credential, transport = Credential(), ModelTransport()
        connection = model_connection(transport, credential)
        context = execution(model_calls=2)
        server = create_server(bindings={"model": Binding("model", connection, owned=True)},
            grants={"model": ("model_status", "model_chat", "model_embed")},
            principal="fixture-principal", context=context)
        self.assertEqual(credential.calls, 0)
        async with create_connected_server_and_client_session(server) as client:
            self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                             {"model_status", "model_chat", "model_embed"})
            status = await client.call_tool("model_status", {"binding": "model"})
            self.assertEqual(contents(status)["availability"], "unverified")
            self.assertEqual((credential.calls, transport.requests), (0, []))
            request = {"binding": "model", "messages": [{"role": "user", "text": "Fixture question"}]}
            for invalid in (
                {**request, "binding": "missing"}, {**request, "messages": "invalid"},
                {**request, "model": "other"}, {**request, "endpoint": "https://other.invalid"},
                {**request, "credential": "fixture"}, {**request, "allow_model_calls": True},
                {**request, "store": True}, {**request, "tools": ["arbitrary"]},
                {**request, "max_tokens": 65}, {**request, "extra_headers": {}},
            ):
                with self.subTest(invalid=invalid):
                    self.assertTrue((await client.call_tool("model_chat", invalid)).isError)
            self.assertEqual((credential.calls, transport.requests), (0, []))
            answer = await client.call_tool("model_chat", {**request, "max_tokens": 32})
            self.assertFalse(answer.isError, answer)
            self.assertIn("Fixture answer", json.dumps(contents(answer)))
            sent = json.loads(transport.requests[0].content)
            self.assertEqual(sent["model"], "fixture-model")
            self.assertFalse(sent["store"])
            self.assertIn(32, (sent.get("max_tokens"), sent.get("max_completion_tokens")))
            embedded = await client.call_tool("model_embed", {
                "binding": "model", "values": ["first", "second"], "dimensions": 2,
            })
            self.assertFalse(embedded.isError, embedded)
            self.assertEqual(contents(embedded)["vectors"], [[0.0, 1.0], [1.0, 1.0]])
            self.assertEqual(json.loads(transport.requests[1].content)["model"], "fixture-vectors")
            exhausted = await client.call_tool("model_chat", request)
            self.assertTrue(exhausted.isError)
            self.assertEqual(contents(exhausted)["error"]["code"], "budget_exhausted")
            self.assert_failure(exhausted, context, "model", "model_chat", code="budget_exhausted",
                category="denied", effect="none", retry="safe_after_correction", key="failure")
            self.assertEqual(context.budget.snapshot()["reserved"]["model_calls"], 2)
            self.assertEqual(len(transport.requests), 2)
        self.assertTrue(connection.describe()["closed"])
        self.assertEqual((credential.closed, transport.closed), (0, 0))
        await connection.aclose()

    async def test_model_native_inference_grant_denies_before_client_creation(self):
        credential, transport = Credential(), ModelTransport()
        connection = model_connection(transport, credential, allow=False)
        context = execution(model_calls=2)
        server = create_server(bindings={"model": Binding("model", connection, owned=True)},
            grants={"model": ("model_chat", "model_embed")}, principal="fixture-principal", context=context)
        async with create_connected_server_and_client_session(server) as client:
            for tool, arguments in (
                ("model_chat", {"messages": [{"role": "user", "text": "fixture"}]}),
                ("model_embed", {"values": ["fixture"]}),
            ):
                result = await client.call_tool(tool, {"binding": "model", **arguments})
                self.assertTrue(result.isError)
                self.assertEqual(contents(result)["error"]["code"], "model_calls_denied")
                self.assert_failure(result, context, "model", tool, code="model_calls_denied",
                    category="denied", effect="none", retry="safe_after_correction", key="failure")
            self.assertEqual(context.budget.snapshot()["reserved"]["model_calls"], 0)
        self.assertEqual((credential.calls, transport.requests), (0, []))

    async def test_model_provider_failures_keep_paid_effect_unknown(self):
        for status, code, category in (
            (400, "provider_rejected_request", "invalid"),
            (401, "provider_access_denied", "auth"),
            (403, "provider_access_denied", "auth"),
            (404, "deployment_not_found", "config"),
            (429, "provider_throttled", "rate-limit"),
            (500, "provider_failure", "failed"),
        ):
            class FailingTransport(ModelTransport):
                async def respond(self, request):
                    self.requests.append(request)
                    return httpx.Response(status, json={"error": {"message": "private-provider-payload"}})

            with self.subTest(status=status):
                transport = FailingTransport()
                connection = model_connection(transport, Credential())
                context = execution(model_calls=1)
                server = create_server(bindings={"fixed-model": Binding("model", connection, owned=True)},
                    grants={"fixed-model": ("model_chat",)}, principal="fixture-principal", context=context)
                async with create_connected_server_and_client_session(server) as client:
                    result = await client.call_tool("model_chat", {
                        "binding": "fixed-model", "messages": [{"role": "user", "text": "private-provider-payload"}],
                    })
                    self.assert_failure(result, context, "model", "model_chat", code=code,
                        category=category, effect="unknown", retry="unspecified", key="failure")
                    self.assertEqual(contents(result)["error"]["category"], "rate_limit" if status == 429 else category)
                    self.assertNotIn("private-provider-payload", result.model_dump_json())
                self.assertEqual(len(transport.requests), 1)
                self.assertEqual(context.budget.snapshot()["reserved"]["model_calls"], 1)

    async def test_model_native_pre_dispatch_refusals_and_safe_diagnostics(self):
        credential, transport = Credential(), ModelTransport()
        connection = connect_model("https://fixture.invalid", "fixture-model", credential=credential,
            provider="azure_completions", allow_model_calls=True, transport=transport,
            limits=ModelLimits(max_output_tokens=64))
        context = execution(model_calls=1)
        server = create_server(bindings={"model": Binding("model", connection, owned=True)},
            grants={"model": ("model_chat", "model_embed")}, principal="fixture-principal", context=context)
        async with create_connected_server_and_client_session(server) as client:
            for tool, arguments, code, category, retry in (
                ("model_embed", {"values": ["private-provider-payload"]}, "embeddings_not_configured", "unsupported", "never"),
                ("model_chat", {"messages": [{"role": "user", "text": "private-provider-payload"}], "max_tokens": 65},
                 "output_token_limit", "invalid", "safe_after_correction"),
            ):
                result = await client.call_tool(tool, {"binding": "model", **arguments})
                self.assert_failure(result, context, "model", tool, code=code,
                    category=category, effect="none", retry=retry, key="failure")
                self.assertNotIn("private-provider-payload", result.model_dump_json())
            with patch.object(connection.chat, "get_response", side_effect=LlmError(
                "provider_failure", category="failed", field="private-provider-payload", action="private-provider-payload",
            )):
                result = await client.call_tool("model_chat", {"binding": "model", "messages": [{"role": "user", "text": "fixture"}]})
                failure = self.assert_failure(result, context, "model", "model_chat", code="provider_failure",
                    category="failed", effect="unknown", retry="unspecified", key="failure")
                self.assertIsNone(failure["field"])
                self.assertNotIn("private-provider-payload", result.model_dump_json())
        self.assertEqual((credential.calls, transport.requests), (0, []))
        self.assertEqual(context.budget.snapshot()["reserved"]["model_calls"], 0)

    async def test_model_native_timeout_is_uncertain_and_not_replayed(self):
        entered, stopped = asyncio.Event(), asyncio.Event()

        class SlowTransport(ModelTransport):
            async def respond(self, request):
                self.requests.append(request)
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        transport = SlowTransport()
        connection = connect_model("https://fixture.invalid", "fixture-model", credential=Credential(),
            provider="azure_completions", allow_model_calls=True, transport=transport,
            limits=ModelLimits(timeout_seconds=5, max_output_tokens=64))
        context = execution(model_calls=1)
        server = create_server(bindings={"model": Binding("model", connection, owned=True)},
            grants={"model": ("model_chat",)}, principal="fixture-principal", context=context)
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("model_chat", {"binding": "model", "messages": [{"role": "user", "text": "fixture"}]})
            self.assert_failure(result, context, "model", "model_chat", code="deadline_exceeded",
                category="interrupted", effect="unknown", retry="unspecified", key="failure")
        self.assertTrue(entered.is_set())
        self.assertTrue(stopped.is_set())
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(context.budget.snapshot()["unknown"]["model_calls"], 1)

    async def test_inventory_registry_success_and_target_refusals(self):
        probe = InventoryProbe()
        service = inventory_service(probe)
        context = execution()
        server = create_server(bindings={"inventory": Binding("inventory", service)},
            grants={"inventory": ("inventory_status", "inventory_tree", "inventory_content")},
            principal="fixture-principal", context=context)
        async with create_connected_server_and_client_session(server) as client:
            self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                             {"inventory_status", "inventory_tree", "inventory_content"})
            status = await client.call_tool("inventory_status", {"binding": "inventory"})
            self.assertEqual(contents(status)["source_count"], 2)
            tree = await client.call_tool("inventory_tree", {"binding": "inventory"})
            self.assertFalse(tree.isError, tree)
            parent = contents(tree)["children"][0]["id"]
            children = await client.call_tool("inventory_tree", {"binding": "inventory", "node": parent})
            self.assertEqual(len(contents(children)["children"]), 2)
            self.assertEqual(probe.calls, [])
            request = {"binding": "inventory", "node": source_node("fixture", "rows"), "limit": 1}
            for invalid in (
                {**request, "binding": "missing"}, {**request, "node": "https://other.invalid"},
                {**request, "node": source_node("other", "rows")},
                {**request, "node": source_node("fixture", "undeclared")},
                {**request, "limit": 101}, {**request, "limit": 0},
                {**request, "endpoint": "https://other.invalid"}, {**request, "subscription": "other"},
                {**request, "selection": "undeclared"},
            ):
                with self.subTest(invalid=invalid):
                    self.assertTrue((await client.call_tool("inventory_content", invalid)).isError)
            denied = await client.call_tool("inventory_content", {
                **request, "node": source_node("fixture", "metadata"),
            })
            self.assertTrue(denied.isError)
            self.assertEqual(contents(denied)["status"], "forbidden")
            self.assert_failure(denied, context, "inventory", "inventory_content", code="forbidden",
                category="denied", effect="none", retry="safe_after_correction", key="failure")
            self.assertEqual(probe.calls, [])
            content = await client.call_tool("inventory_content", request)
            self.assertFalse(content.isError, content)
            self.assertEqual(contents(content)["rows"], [{"id": "0"}])
            self.assertTrue(contents(content)["truncated"])
            self.assertEqual(contents(content)["provenance"], "Synthetic test fixture.")
            self.assertEqual(probe.calls, [("preview", "rows", 1), ("metadata", "rows")])
            self.assertTrue((await client.call_tool("inventory_search", {"query": "*"})).isError)

    async def test_inventory_native_error_models_and_read_statuses(self):
        probe = InventoryProbe()
        service = inventory_service(probe)
        context = execution()
        server = create_server(bindings={"inventory": Binding("inventory", service)},
            grants={"inventory": ("inventory_tree", "inventory_content")}, principal="fixture-principal", context=context)
        async with create_connected_server_and_client_session(server) as client:
            for tool in ("inventory_tree", "inventory_content"):
                result = await client.call_tool(tool, {"binding": "inventory", "node": "private-provider-payload"})
                self.assert_failure(result, context, "inventory", tool, code="invalid_node",
                    category="invalid", effect="none", retry="safe_after_correction", key="failure")
                self.assertEqual(contents(result)["error"], "invalid_node")
                self.assertNotIn("status", contents(result))
                self.assertNotIn("private-provider-payload", result.model_dump_json())
            for status, category, retry in (
                ("forbidden", "denied", "safe_after_correction"),
                ("unconfigured", "config", "safe_after_correction"),
                ("unreachable", "unavailable", "unspecified"),
                ("unavailable", "unavailable", "unspecified"),
                ("empty", None, None),
            ):
                native = ContentResult(service="fixture", kind="rows", status=status,
                    detail="private-provider-payload" if status != "empty" else "",
                    collected_at=collected_now(), payload=ContentPayload(form="rows", media_type="application/json"))
                with self.subTest(status=status), patch.object(probe, "preview", return_value=native):
                    result = await client.call_tool("inventory_content", {
                        "binding": "inventory", "node": source_node("fixture", "rows"),
                    })
                    self.assertEqual(contents(result)["status"], status)
                    self.assertEqual(contents(result), result.structuredContent)
                    if status == "empty":
                        self.assertFalse(result.isError)
                        self.assertNotIn("failure", contents(result))
                    else:
                        self.assert_failure(result, context, "inventory", "inventory_content", code=status,
                            category=category, effect="none", retry=retry, key="failure")
                        self.assertEqual(contents(result)["error"], status)
                        self.assertNotIn("private-provider-payload", result.model_dump_json())
        disabled = parse_selection("none", allowed=service.registry.source_ids())
        with patch("resource_explorer.mcp_adapter.parse_selection", return_value=disabled):
            server = create_server(bindings={"inventory": Binding("inventory", service)},
                grants={"inventory": ("inventory_content",)}, principal="fixture-principal", context=context)
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("inventory_content", {"binding": "inventory", "node": source_node("fixture", "rows")})
            self.assert_failure(result, context, "inventory", "inventory_content", code="source_disabled",
                category="denied", effect="none", retry="safe_after_correction", key="failure")
            self.assertEqual(contents(result)["error"], "source_disabled")
            self.assertNotIn("status", contents(result))

    async def test_host_deadline_before_and_after_dispatch(self):
        entered, stopped = asyncio.Event(), asyncio.Event()

        class SlowProbe(InventoryProbe):
            async def preview(self, source, *, limit):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        for expired in (True, False):
            context = ExecutionContext.create(CallerContext("fixture-principal"), limits={"tool_calls": 1}, timeout_seconds=0.2)
            if expired:
                context = replace(context, deadline=0)
            server = create_server(bindings={"inventory": Binding("inventory", inventory_service(SlowProbe()))},
                grants={"inventory": ("inventory_content",)}, principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool("inventory_content", {"binding": "inventory", "node": source_node("fixture", "rows")})
                self.assert_failure(result, context, "inventory", "inventory_content", code="deadline_exceeded",
                    category="interrupted", effect="none" if expired else "unknown",
                    retry="safe_after_correction" if expired else "unspecified")
            self.assertEqual(entered.is_set(), not expired)
            self.assertEqual(stopped.is_set(), not expired)
            self.assertEqual(context.budget.snapshot()["reserved"]["tool_calls"], 0 if expired else 1)

    async def test_recovery_explicit_grants_stage_restart_read_and_integrity(self):
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            root = Path(directory) / "artifacts"
            application = RecoveryTools(RecoverySettings(recovery_root=str(root), allow_stage=True,
                allow_inspect=True, allow_payload_reads=True, max_payload_bytes=256), Path(directory) / "config.json")
            def server():
                return create_server(bindings={"recovery": Binding("recovery", application)},
                    grants={"recovery": ("recovery_status", "recovery_stage", "recovery_list", "recovery_read")},
                    principal="fixture-principal", context=execution())
            self.assertFalse(root.exists())
            async with create_connected_server_and_client_session(server()) as client:
                self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                                 {"recovery_status", "recovery_stage", "recovery_list", "recovery_read"})
                self.assertFalse((await client.call_tool("recovery_status", {"binding": "recovery"})).isError)
                self.assertFalse(root.exists())
                for tool, invalid in (
                    ("recovery_stage", {"run_id": "../outside", "payload_json": "{}"}),
                    ("recovery_stage", {"run_id": "one", "payload_json": "{}", "recovery_root": "/other"}),
                    ("recovery_stage", {"run_id": "one", "payload_json": "{}", "allow_stage": True}),
                    ("recovery_stage", {"run_id": "large", "payload_json": '"' + "x" * 300 + '"'}),
                    ("recovery_read", {"run_id": "one", "path": "/other"}),
                    ("recovery_delete", {"run_id": "one"}),
                ):
                    self.assertTrue((await client.call_tool(tool, {"binding": "recovery", **invalid})).isError)
                self.assertFalse(root.exists())
                staged = await client.call_tool("recovery_stage", {
                    "binding": "recovery", "run_id": "one", "payload_json": '{"rows": [1, 2]}',
                })
                self.assertFalse(staged.isError, staged)
                self.assertEqual(contents(staged)["state"], "preserved")
                self.assertFalse(contents(staged)["saved"])
                self.assertTrue((await client.call_tool("recovery_stage", {
                    "binding": "recovery", "run_id": "one", "payload_json": '{"other": true}',
                })).isError)
            async with create_connected_server_and_client_session(server()) as client:
                recovered = await client.call_tool("recovery_read", {"binding": "recovery", "run_id": "one"})
                self.assertFalse(recovered.isError, recovered)
                self.assertEqual(contents(recovered)["payload"], {"rows": [1, 2]})
                listing = await client.call_tool("recovery_list", {"binding": "recovery"})
                self.assertEqual(len(contents(listing)["artifacts"]), 1)
                artifact = root / "one.artifact.json"
                damaged = json.loads(artifact.read_text())
                damaged["content_sha256"] = "0" * 64
                artifact.write_text(json.dumps(damaged))
                self.assertTrue((await client.call_tool("recovery_read", {
                    "binding": "recovery", "run_id": "one",
                })).isError)
                self.assertTrue(artifact.exists())

    async def test_recovery_native_grants_deny_and_default_root_refuses(self):
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            root = Path(directory) / "artifacts"
            application = RecoveryTools(RecoverySettings(recovery_root=str(root)), Path(directory) / "config.json")
            context = execution()
            server = create_server(bindings={"recovery": Binding("recovery", application)},
                grants={"recovery": ("recovery_stage", "recovery_list", "recovery_read")},
                principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                for tool, arguments in (("recovery_stage", {"run_id": "one", "payload_json": "{}"}),
                                        ("recovery_list", {}), ("recovery_read", {"run_id": "one"})):
                    result = await client.call_tool(tool, {"binding": "recovery", **arguments})
                    self.assertTrue(result.isError)
                    self.assertEqual(contents(result)["error"]["code"], "permission_denied")
                    self.assert_failure(result, context, "recovery", tool, code="permission_denied",
                        category="denied", effect="none", retry="safe_after_correction")
                self.assertFalse(root.exists())
            default = RecoveryTools(RecoverySettings(), Path(directory) / "config.json")
            with self.assertRaises(FrameworkError):
                create_server(bindings={"recovery": Binding("recovery", default)}, grants={},
                              principal="fixture-principal", context=execution())
            self.assertFalse(root.exists())

    async def test_recovery_native_failure_types_have_truthful_metadata(self):
        cases = (
            (InvalidRunId, "invalid", "none", "safe_after_correction"),
            (PayloadNotSupported, "unsupported", "none", "never"),
            (PayloadTooLarge, "invalid", "none", "safe_after_correction"),
            (ArtifactExists, "denied", "none", "safe_after_correction"),
            (ArtifactMissing, "failed", "none", "safe_after_correction"),
            (ArtifactCorrupt, "failed", "none", "never"),
            (StaleArtifact, "denied", "none", "read_back_first"),
            (StagingFailed, "failed", "unknown", "read_back_first"),
            (StoreRefused, "denied", "none", "safe_after_correction"),
            (StoreUnavailable, "unavailable", "none", "unspecified"),
            (StoreTimeout, "interrupted", "unknown", "read_back_first"),
            (StoreOccupied, "denied", "none", "never"),
            (StoreError, "failed", "unknown", "read_back_first"),
            (RecoveryError, "failed", "unknown", "read_back_first"),
        )
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            application = RecoveryTools(RecoverySettings(recovery_root=str(Path(directory) / "artifacts"), allow_stage=True),
                Path(directory) / "config.json")
            for kind, category, effect, retry in cases:
                with self.subTest(kind=kind.__name__), patch.object(application, "stage", side_effect=kind("private-provider-payload")):
                    context = execution()
                    server = create_server(bindings={"local-artifacts": Binding("recovery", application)},
                        grants={"local-artifacts": ("recovery_stage",)}, principal="fixture-principal", context=context)
                    async with create_connected_server_and_client_session(server) as client:
                        result = await client.call_tool("recovery_stage", {
                            "binding": "local-artifacts", "run_id": "artifact-id", "payload_json": "{}",
                        })
                        self.assert_failure(result, context, "recovery", "recovery_stage", code=kind.__name__,
                            category=category, effect=effect, retry=retry)
                        self.assertNotIn("private-provider-payload", result.model_dump_json())
                        self.assertNotEqual(contents(result)["error"]["run_id"], "artifact-id")
            self.assertFalse(application.store.root.exists())

    async def test_recovery_post_write_timeout_requires_read_back(self):
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            application = RecoveryTools(RecoverySettings(recovery_root=str(Path(directory) / "artifacts"),
                allow_stage=True, allow_payload_reads=True), Path(directory) / "config.json")
            original_stage = application.stage

            def landed_then_timeout(**arguments):
                original_stage(**arguments)
                raise TimeoutError("private-provider-payload")

            context = execution()
            with patch.object(application, "stage", side_effect=landed_then_timeout) as stage:
                server = create_server(bindings={"recovery": Binding("recovery", application)},
                    grants={"recovery": ("recovery_stage", "recovery_read")}, principal="fixture-principal", context=context)
                async with create_connected_server_and_client_session(server) as client:
                    result = await client.call_tool("recovery_stage", {
                        "binding": "recovery", "run_id": "landed", "payload_json": '{"retained": true}',
                    })
                    self.assert_failure(result, context, "recovery", "recovery_stage", code="deadline_exceeded",
                        category="interrupted", effect="unknown", retry="read_back_first")
                    self.assertNotIn("private-provider-payload", result.model_dump_json())
                    stage.assert_called_once()
                    recovered = await client.call_tool("recovery_read", {"binding": "recovery", "run_id": "landed"})
                    self.assertFalse(recovered.isError)
                    self.assertEqual(contents(recovered)["payload"], {"retained": True})
                    self.assertTrue((application.store.root / "landed.artifact.json").exists())

    async def test_sdk_cancellation_reaches_native_data_and_closes_owned_alias_once(self):
        entered, cancelled = asyncio.Event(), asyncio.Event()
        request_ids = []

        class BlockingTransport(SearchTransport):
            async def request(self, request):
                self.requests.append(request)
                request_ids.append(server.request_context.request_id)
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        credential, transport = Credential(), BlockingTransport()
        connector = data_connector(transport, credential)
        context = execution(data_calls=1)
        with patch.object(connector, "aclose", wraps=connector.aclose) as close:
            server = create_server(bindings={"data": Binding("data", connector, owned=True),
                "alias": Binding("data", connector, owned=True)},
                grants={"data": ("data_query", "data_status")}, principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                pending = asyncio.create_task(client.call_tool("data_query", {
                    "binding": "data", "dialect": "search", "expression": "*",
                }))
                try:
                    with anyio.fail_after(5):
                        await entered.wait()
                        await client.send_notification(types.ClientNotification(types.CancelledNotification(
                            params=types.CancelledNotificationParams(requestId=request_ids[0], reason="fixture cancellation"))))
                        await cancelled.wait()
                    status = await client.call_tool("data_status", {"binding": "data"})
                    self.assertFalse(status.isError, status)
                    self.assertEqual(context.budget.snapshot()["unknown"]["data_calls"], 1)
                finally:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
            close.assert_awaited_once()
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual((credential.closed, transport.closed), (0, 0))

    async def test_sdk_cancellation_reaches_native_model_and_owned_cleanup(self):
        entered, cancelled = asyncio.Event(), asyncio.Event()
        request_ids = []

        class BlockingTransport(ModelTransport):
            async def respond(self, request):
                self.requests.append(request)
                request_ids.append(server.request_context.request_id)
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        credential, transport = Credential(), BlockingTransport()
        connection = model_connection(transport, credential)
        context = execution(model_calls=1)
        with patch.object(connection, "aclose", wraps=connection.aclose) as close:
            server = create_server(bindings={"model": Binding("model", connection, owned=True)},
                grants={"model": ("model_chat", "model_status")}, principal="fixture-principal", context=context)
            async with create_connected_server_and_client_session(server) as client:
                pending = asyncio.create_task(client.call_tool("model_chat", {
                    "binding": "model", "messages": [{"role": "user", "text": "fixture"}],
                }))
                try:
                    with anyio.fail_after(5):
                        await entered.wait()
                        await client.send_notification(types.ClientNotification(types.CancelledNotification(
                            params=types.CancelledNotificationParams(requestId=request_ids[0], reason="fixture cancellation"))))
                        await cancelled.wait()
                    status = await client.call_tool("model_status", {"binding": "model"})
                    self.assertFalse(status.isError, status)
                    self.assertEqual(context.budget.snapshot()["unknown"]["model_calls"], 1)
                finally:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
            close.assert_awaited_once()
        self.assertTrue(connection.describe()["closed"])
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual((credential.closed, transport.closed), (0, 0))

    async def test_cancelled_recovery_write_settles_and_remains_readable(self):
        for allow_stage in (True, False):
            with self.subTest(allow_stage=allow_stage):
                await self.check_cancelled_recovery(allow_stage)

    async def check_cancelled_recovery(self, allow_stage):
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            application = RecoveryTools(RecoverySettings(recovery_root=str(Path(directory) / "artifacts"),
                allow_stage=allow_stage, allow_payload_reads=True), Path(directory) / "config.json")
            entered, finished = asyncio.Event(), asyncio.Event()
            release = threading.Event()
            request_ids = []
            loop = asyncio.get_running_loop()
            original_stage = application.stage

            def slow_stage(**arguments):
                request_ids.append(server.request_context.request_id)
                loop.call_soon_threadsafe(entered.set)
                try:
                    if not release.wait(timeout=5):
                        raise TimeoutError("fixture worker was not released")
                    return original_stage(**arguments)
                finally:
                    loop.call_soon_threadsafe(finished.set)

            with patch.object(application, "stage", side_effect=slow_stage):
                server = create_server(bindings={"recovery": Binding("recovery", application)},
                    grants={"recovery": ("recovery_stage", "recovery_status")},
                    principal="fixture-principal", context=execution())
                async with create_connected_server_and_client_session(server) as client:
                    pending = asyncio.create_task(client.call_tool("recovery_stage", {
                        "binding": "recovery", "run_id": "cancelled", "payload_json": '{"finished": true}',
                    }))
                    try:
                        with anyio.fail_after(5):
                            await entered.wait()
                            await client.send_notification(types.ClientNotification(types.CancelledNotification(
                                params=types.CancelledNotificationParams(requestId=request_ids[0], reason="fixture cancellation"))))
                            self.assertFalse((await client.call_tool("recovery_status", {"binding": "recovery"})).isError)
                            self.assertFalse(finished.is_set())
                            release.set()
                            await finished.wait()
                    finally:
                        release.set()
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            self.assertTrue(finished.is_set())
            if not allow_stage:
                self.assertFalse(application.store.root.exists())
                return
            reader = create_server(bindings={"recovery": Binding("recovery", application)},
                grants={"recovery": ("recovery_read",)}, principal="fixture-principal", context=execution())
            async with create_connected_server_and_client_session(reader) as client:
                result = await client.call_tool("recovery_read", {"binding": "recovery", "run_id": "cancelled"})
                self.assertFalse(result.isError, result)
                self.assertEqual(contents(result)["payload"], {"finished": True})

    async def test_unexpected_engine_failure_does_not_echo_provider_payload(self):
        transport = SearchTransport()
        connector = data_connector(transport, Credential())
        server = create_server(bindings={"data": Binding("data", connector, owned=True)},
            grants={"data": ("data_query",)}, principal="fixture-principal", context=execution(data_calls=1))
        with patch.object(transport, "request", side_effect=RuntimeError("private-provider-payload")):
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool("data_query", {"binding": "data", "dialect": "search", "expression": "*"})
                self.assertTrue(result.isError)
                self.assertEqual(contents(result)["error"]["code"], "operation_failed")
                self.assertNotIn("private-provider-payload", result.model_dump_json())

    async def test_one_host_discovers_all_fifteen_tools_and_freezes_grants(self):
        with tempfile.TemporaryDirectory(dir="/tmp/agentcraft-recovery-mcp") as directory:
            root = Path(directory) / "artifacts"
            credential, data_transport, model_transport, probe = Credential(), SearchTransport(), ModelTransport(), InventoryProbe()
            connector = data_connector(data_transport, credential)
            connection = model_connection(model_transport, credential)
            bindings = {
                "composition": Binding("composition", Settings()),
                "data": Binding("data", connector, owned=True),
                "data-denied": Binding("data", connector, owned=True),
                "model": Binding("model", connection, owned=True),
                "inventory": Binding("inventory", inventory_service(probe)),
                "recovery": Binding("recovery", RecoveryTools(RecoverySettings(recovery_root=str(root)),
                                                               Path(directory) / "config.json")),
            }
            grants = {"composition": ["composition_status", "composition_validate", "composition_demo"],
                "data": ["data_status", "data_query"], "model": ["model_status", "model_chat", "model_embed"],
                "inventory": ["inventory_status", "inventory_tree", "inventory_content"],
                "recovery": ["recovery_status", "recovery_list", "recovery_stage", "recovery_read"]}
            expected = {tool for allowed in grants.values() for tool in allowed}
            server = create_server(bindings=bindings, grants=grants,
                principal="fixture-principal", context=execution(data_calls=1, model_calls=1))
            grants["data-denied"] = ["data_query"]
            grants["data"].append("data_delete")
            bindings.clear()
            async with create_connected_server_and_client_session(server) as client:
                listed = (await client.list_tools()).tools
                self.assertEqual({tool.name for tool in listed}, expected)
                self.assertEqual(len(listed), 15)
                for tool in listed:
                    self.assertFalse(tool.inputSchema["additionalProperties"])
                    self.assertIn("binding", tool.inputSchema["required"])
                self.assertTrue((await client.call_tool("data_query", {
                    "binding": "data-denied", "dialect": "search", "expression": "*",
                })).isError)
                for family in ("composition", "data", "model", "inventory", "recovery"):
                    status = await client.call_tool(f"{family}_status", {"binding": family})
                    self.assertFalse(status.isError, status)
            self.assertEqual((credential.calls, data_transport.requests, model_transport.requests, probe.calls), (0, [], [], []))
            self.assertFalse(root.exists())

    def test_installed_import_is_passive_and_does_not_load_optional_engines(self):
        code = """
import json
import os
import socket
import sys
from unittest.mock import patch
with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')), \
     patch.object(os, 'mkdir', side_effect=AssertionError('writes forbidden')):
    import agentcraft.mcp
    print(json.dumps({'path': agentcraft.mcp.__file__, 'optional_loaded': sorted(
        set(sys.modules) & {'azdata', 'llm_interface', 'resource_explorer', 'workrecovery'})}))
"""
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd="/tmp",
                                env=environment, capture_output=True, text=True, timeout=15, check=True)
        payload = json.loads(result.stdout)
        self.assertIn("site-packages/agentcraft/mcp.py", payload["path"])
        self.assertEqual(payload["optional_loaded"], [])
        self.assertEqual(result.stderr, "")

    def test_invalid_configuration_refuses_before_start(self):
        configured = {"local": Binding("composition", Settings())}
        for changes in (
            {"principal": "other"},
            {"bindings": {"bad": Binding("arbitrary.module", object())}},
            {"bindings": {"bad": Binding("composition", object())}},
            {"grants": {"unknown": ("composition_status",)}},
            {"grants": {"local": ("arbitrary_execute",)}},
            {"grants": {"local": "composition_status"}},
        ):
            with self.subTest(changes=changes), self.assertRaises(FrameworkError):
                create_server(**{"bindings": configured, "grants": {}, "principal": "fixture-principal",
                                 "context": execution(), **changes})

    async def test_module_stdio_is_composition_only(self):
        parameters = StdioServerParameters(command=sys.executable,
            args=["-I", "-B", "-m", "agentcraft.mcp"], cwd="/tmp")
        with tempfile.TemporaryFile(mode="w+") as stderr:
            async with stdio_client(parameters, errlog=stderr) as streams:
                async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
                    self.assertEqual((await client.initialize()).serverInfo.name, "agentcraft")
                    self.assertEqual({tool.name for tool in (await client.list_tools()).tools},
                                     {tool.name for tool in TOOLS})
                    result = await client.call_tool("composition_status", {"binding": "composition"})
                    self.assertFalse(result.isError, result)
                    self.assertFalse(contents(result)["network"])
                    refused = await client.call_tool("composition_validate", {
                        "binding": "composition", "document": "{private-provider-payload",
                    })
                    self.assertTrue(refused.isError)
                    self.assertEqual(contents(refused), refused.structuredContent)
                    failure = contents(refused)["error"]
                    self.assertEqual(failure["code"], "invalid_document")
                    self.assertEqual(failure["capability_id"], "composition")
                    self.assertEqual(failure["operation"], "composition_validate")
                    self.assertTrue(failure["run_id"])
                    self.assertNotIn("private-provider-payload", refused.model_dump_json())
            stderr.seek(0)
            self.assertEqual(stderr.read(), "")


if __name__ == "__main__":
    unittest.main()