"""SYNTHETIC offline composition; no live credentials, network, or user files."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import BaseModel

from agentcraft import Binding, CallerContext, ExecutionContext, Framework, FrameworkError
from azdata import ConnectorConfig, HttpResponse, Policy, QueryRequest, ResourceAddress, connect
from llm_interface import LlmError, connect as connect_model
from situation_detector import run_battery_async
from workrecovery import (
    ArtifactExists, ArtifactMissing, ArtifactStore, JSON_CONTENT_TYPE, RecoverableJobs,
    StoreOccupied, StoreTimeout, encode_payload,
)


class _Summary(BaseModel):
    rule_ids: list[str]
    matched_counts: list[int]


async def offline_workflow() -> dict:
    """Run real public operations against owned synthetic HTTP and filesystem fixtures."""
    execution = ExecutionContext.create(
        CallerContext("synthetic-example"),
        limits={"data_calls": 2, "model_calls": 1, "store_calls": 5}, timeout_seconds=30,
    )
    configuration = {
        "version": "synthetic-1", "max_window_seconds": 60,
        "rule_sets": [{"id": "readings", "name": "Synthetic readings", "rules": [
            {"id": name, "name": name, "parameters": {"threshold": threshold},
             "query": "Readings | where timestamp between (start .. end) | order by sequence asc"}
            for name, threshold in (("all_readings", 1), ("high_readings", 5))
        ]}],
    }
    window = {"start": "2026-09-16T00:00:00+00:00", "end": "2026-09-16T00:01:00+00:00"}

    async def query_http(request):
        assert request.method == "POST"
        assert request.url == "https://synthetic.kusto.windows.net/v2/rest/query"
        assert request.body["db"] == "Synthetic"
        parameters = json.loads(request.body["properties"])["Parameters"]
        assert parameters == window
        return HttpResponse(200, [
            {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult",
             "TableName": "PrimaryResult", "Columns": [
                 {"ColumnName": "sequence", "ColumnType": "long"},
                 {"ColumnName": "value", "ColumnType": "long"},
             ], "Rows": [[1, 2], [2, 7]]},
            {"FrameType": "DataSetCompletion", "HasErrors": False},
        ])

    model_inputs = []

    async def model_http(request):
        assert request.url.host == "synthetic.openai.azure.com" and request.url.path.endswith("/responses")
        body = json.loads(request.content)
        assert body["store"] is False and not body.get("stream")
        texts = [part["text"] for item in body["input"] if item.get("role") == "user"
                 for part in item["content"] if part["type"] == "input_text"]
        assert len(texts) == 1
        observations = json.loads(texts[0])
        model_inputs.append(observations)
        summary = {"rule_ids": [entry["rule_id"] for entry in observations["rules"]],
                   "matched_counts": [len(entry["matched_sequences"]) for entry in observations["rules"]]}
        return httpx.Response(200, json={
            "id": "resp_synthetic", "object": "response", "created_at": 1,
            "model": "synthetic-chat", "status": "completed", "error": None,
            "incomplete_details": None, "instructions": None, "tools": [], "tool_choice": "auto",
            "parallel_tool_calls": False, "temperature": 1, "top_p": 1, "metadata": {},
            "output": [{"id": "msg_synthetic", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": json.dumps(summary), "annotations": [], "logprobs": []}]}],
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        })

    identity = SimpleNamespace(
        get_token=AsyncMock(return_value=SimpleNamespace(token="SYNTHETIC", expires_on=4_000_000_000)),
        aclose=AsyncMock(return_value=None),
    )
    transport = SimpleNamespace(request=AsyncMock(side_effect=query_http), aclose=AsyncMock(return_value=None))
    config = ConnectorConfig(
        "https://synthetic.kusto.windows.net", ResourceAddress({"database": "Synthetic"}),
        ("synthetic.kusto.windows.net",),
    )
    data = connect("adx", config, credential=identity, policy=Policy("synthetic-example", grants={"query"}), transport=transport)
    denied_data = connect("adx", config, credential=identity, policy=Policy("synthetic-example", grants=set()), transport=transport)
    model_transport = httpx.MockTransport(model_http)
    model_transport.aclose = AsyncMock(wraps=model_transport.aclose)
    model_options = {"credential": identity, "transport": model_transport,
                     "allowed_hosts": ("synthetic.openai.azure.com",)}
    model = connect_model("https://synthetic.openai.azure.com", "synthetic-chat", allow_model_calls=True, **model_options)
    denied_model = connect_model("https://synthetic.openai.azure.com", "synthetic-chat", **model_options)

    with TemporaryDirectory(prefix="agentcraft-offline-") as directory, \
            patch("socket.socket.connect", side_effect=AssertionError("Offline example forbids network")), \
            patch("socket.socket.connect_ex", side_effect=AssertionError("Offline example forbids network")), \
            patch("socket.getaddrinfo", side_effect=AssertionError("Offline example forbids DNS")):
        root = Path(directory)
        destination = ArtifactStore(root / "destination")
        writes = 0
        readable = False

        def save(run_id, content, content_type):
            nonlocal writes
            execution.remaining()
            execution.budget.reserve("store_calls")
            assert content_type == JSON_CONTENT_TYPE
            writes += 1
            try:
                destination.stage(run_id, content)
            except ArtifactExists:
                if destination.read_run(run_id).payload != content:
                    raise StoreOccupied("Synthetic destination already holds different bytes") from None
            if writes == 1:
                execution.budget.mark_unknown("store_calls")
                raise StoreTimeout(operation="write")

        def load(run_id):
            execution.remaining()
            execution.budget.reserve("store_calls")
            try:
                artifact = destination.read_run(run_id)
            except ArtifactMissing:
                return None
            if not readable:
                execution.budget.mark_unknown("store_calls")
                raise StoreTimeout(operation="read-back")
            return artifact.payload

        store = SimpleNamespace(save=save, load=load)
        jobs = RecoverableJobs(store=store, root=root / "recovery", max_attempts=1)
        app = Framework({
            "identity": Binding("example.synthetic_identity", identity, owned=True),
            "http": Binding("example.synthetic_http", transport, owned=True),
            "model_http": Binding("example.synthetic_model_http", model_transport, owned=True),
            "data": Binding("data", data, owned=True, requires=("identity", "http")),
            "denied_data": Binding("data", denied_data, owned=True, requires=("identity", "http")),
            "model": Binding("models", model, owned=True, requires=("identity", "model_http")),
            "denied_model": Binding("models", denied_model, owned=True, requires=("identity", "model_http")),
            "recovery": Binding("recovery", jobs),
        })
        assert app.describe()["readiness"] == "unverified"

        async def model_refusal(name, code):
            try:
                await app.model(name).chat.get_response("Synthetic refusal probe")
            except LlmError as error:
                assert (error.category, error.code) == ("denied", code)
                return error.metadata()
            raise AssertionError("Model operation should have refused")

        async def execute(rule, original_window):
            result = await app.data("data").query(QueryRequest(
                dialect="kql", expression=rule["query"],
                parameters={name: datetime.fromisoformat(value) for name, value in original_window.items()},
            ))
            if result.status != "success" or result.errors or any(
                item.status != "success" or item.content is None for item in result.items
            ):
                raise FrameworkError("query_incomplete", category="failed", operation="query")
            return {"status": result.status, "rows": [dict(item.content.data) for item in result.items]}

        async def process(rule, envelope, original_window):
            return {"matched_sequences": [row["sequence"] for row in envelope["rows"]
                                          if row["value"] >= rule["parameters"]["threshold"]]}

        with execution.activate():
            async with app:
                probe = QueryRequest(dialect="kql", expression="Readings")
                grant = await app.data("denied_data").query(probe)
                assert grant.status == "denied" and grant.errors[0].code == "operation_not_granted"
                model_grant = await model_refusal("denied_model", "model_calls_denied")
                assert identity.get_token.await_count == 0 and transport.request.await_count == 0 and model_inputs == []
                battery = await run_battery_async(configuration, window, execute, process, max_concurrency=2)
                model_input = {"configuration_digest": battery["configuration_digest"],
                               "rules": [{"rule_id": entry["rule_id"], **entry["processed"]} for entry in battery["rules"]]}
                response = await app.model("model").chat.get_response(
                    json.dumps(model_input), options={"response_format": _Summary},
                )
                receipt = response.additional_properties["llm_interface"]
                if receipt["status"] != "completed" or response.finish_reason != "stop":
                    raise LlmError("summary_not_completed", category="interrupted")
                summary = response.value
                assert isinstance(summary, _Summary) and receipt["run_id"] == execution.run_id
                assert model_inputs == [model_input]
                assert summary.rule_ids == [entry["rule_id"] for entry in battery["rules"]]
                assert summary.matched_counts == [len(entry["processed"]["matched_sequences"]) for entry in battery["rules"]]
                budget = await app.data("data").query(probe)
                assert budget.status == "denied" and budget.errors[0].code == "budget_exhausted"
                assert all(item.effect == "none" for refusal in (grant, budget) for item in refusal.items)
                model_budget = await model_refusal("model", "budget_exhausted")
                payload = {"synthetic": True, "run_id": execution.run_id, "battery": battery,
                           "model_summary": summary.model_dump(), "model_run": receipt}
                uncertain = app.get("recovery", RecoverableJobs).commit(execution.run_id, payload)
                assert uncertain.state == "unknown" and not uncertain.verified
                assert isinstance(uncertain.error, StoreTimeout) and uncertain.artifact.path.exists()

                restarted = RecoverableJobs(store=store, root=root / "recovery", max_attempts=1)
                preserved = restarted.read(execution.run_id)
                assert preserved.payload == payload
                try:
                    restarted.commit(execution.run_id, {"synthetic": "different output"})
                except ArtifactExists:
                    assert restarted.read(execution.run_id).content_sha256 == preserved.content_sha256
                else:
                    raise AssertionError("A pending artifact must not be overwritten")
                readable = True
                recovered = restarted.recommit(preserved)
                repeated = restarted.commit(execution.run_id, payload)
                assert recovered.saved and recovered.verified and repeated.saved and repeated.verified
                assert recovered.attempts == repeated.attempts == 0 and writes == 1
                assert restarted.pending() == [] and restarted.problems() == []
                assert destination.read_run(execution.run_id).payload == encode_payload(payload)[0]

        await app.aclose()
        identity.aclose.assert_awaited_once()
        transport.aclose.assert_awaited_once()
        model_transport.aclose.assert_awaited_once()
        closed = await data.query(QueryRequest(dialect="kql", expression="Readings"))
        assert closed.status == "failed" and closed.errors[0].code == "connector_closed"
        assert transport.request.await_count == 2 and len(model_inputs) == 1
        try:
            await model.chat.get_response("Synthetic closed probe")
        except LlmError as error:
            assert error.code == "connection_closed"
        else:
            raise AssertionError("Closed model must refuse")
        report = {
            "synthetic": True,
            "rules": [{"id": entry["rule_id"], "rows": entry["query_result"]["rows"],
                       **entry["processed"]} for entry in battery["rules"]],
            "configuration_digest": battery["configuration_digest"],
            "model": {"summary": summary.model_dump(), "status": receipt["status"],
                      "run_id_shared": receipt["run_id"] == execution.run_id},
            "requests": {"data": transport.request.await_count, "model": len(model_inputs)},
            "refusals": {"data_grant": grant.errors[0].code, "model_grant": model_grant,
                         "data_budget": budget.errors[0].code, "model_budget": model_budget,
                         "pending_overwrite": "ArtifactExists"},
            "recovery": {"initial": uncertain.state, "recovered": recovered.state,
                         "repeated": repeated.state, "verified": recovered.verified,
                         "destination_writes": writes, "pending": len(restarted.pending())},
            "budget": execution.budget.snapshot(),
            "closed": {"framework": app.describe()["closed"], "data": closed.errors[0].code,
                       "model": model.describe()["closed"], "model_http": model_transport.aclose.await_count,
                       "identity": identity.aclose.await_count, "http": transport.aclose.await_count},
        }
    report["temporary_files_removed"] = not root.exists()
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(offline_workflow()), indent=2, sort_keys=True))