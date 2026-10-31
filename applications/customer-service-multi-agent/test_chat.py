"""Offline only. No credentials, network inference or package operations."""
import asyncio
from importlib.util import find_spec
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from chat import ChatService, ChatUnavailable, HostedClient, MAX_TURNS
HOSTED_AVAILABLE = all(find_spec(name) is not None for name in (
    "agent_framework", "agent_framework_foundry", "agent_framework_foundry_hosting"))
if HOSTED_AVAILABLE:
    from agent_framework import BaseChatClient, ChatResponse, Message
    from hosted.runtime import build_agent
else:
    BaseChatClient = object


class FakeHostedClient:
    def __init__(self):
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.fail = False

    def respond(self, message, previous_response_id, headers):
        self.calls.append((message, previous_response_id, headers))
        self.entered.set()
        self.release.wait(2)
        if self.fail:
            raise RuntimeError("PRIVATE CUSTOMER SECRET")
        return {"response_id": "resp_" + str(len(self.calls)),
                "content": "Synthetic guidance only. No transaction executed."}

    def close(self):
        pass


class SafeTelemetry:
    def __init__(self):
        self.rows = []

    @contextmanager
    def event(self, operation, session, **kwargs):
        row = {"operation": operation, **kwargs}
        self.rows.append(row)
        yield row


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(
            database=str(Path(self.tmp.name) / "chat.sqlite3"),
            hosted_agent_name="cs-customer-service-chat", hosted_agent_version="7")
        self.client = FakeHostedClient()
        self.busy = threading.Lock()
        self.telemetry = SafeTelemetry()
        self.service = ChatService(self.settings, self.busy, self.telemetry, self.client)

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def wait(self, cid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            row = self.service.get("owner", cid)
            if row["status"] in ("completed", "failed"):
                return row
            time.sleep(0.005)
        self.fail("worker deadline exceeded")

    def test_success_multiturn_ownership(self):
        first = self.service.submit("owner", "Synthetic SYN-101 is damaged")
        cid = first["conversation_id"]
        self.assertEqual(first["status"], "queued")
        self.assertEqual(self.wait(cid)["status"], "completed")
        self.assertIsNone(self.service.get("other", cid))
        with self.assertRaises(KeyError):
            self.service.submit("other", "hello", cid)
        with self.assertRaises(KeyError):
            self.service.submit("owner", "hello", str(uuid.uuid4()))
        self.service.submit("owner", "What is the synthetic next step?", cid)
        row = self.wait(cid)
        self.assertEqual(len(row["messages"]), 4)
        self.assertEqual(self.client.calls[1][1], "resp_1")
        self.assertNotIn("previous_response_id", row)
        self.assertEqual([r.get("response_id") for r in self.telemetry.rows], ["resp_1", "resp_2"])
        self.assertIn("cs.session_id=", self.client.calls[0][2]["baggage"])

    def test_concurrency_and_persist_before_call(self):
        self.client.release.clear()
        cid = self.service.submit("owner", "Synthetic question")["conversation_id"]
        self.assertTrue(self.client.entered.wait(1))
        with sqlite3.connect(self.settings.database) as db:
            saved = json.loads(db.execute("SELECT data FROM chat_conversations").fetchone()[0])
        self.assertEqual(saved["messages"][0]["content"], "Synthetic question")
        with self.assertRaises(BlockingIOError):
            self.service.submit("owner", "another", cid)
        with self.assertRaises(BlockingIOError):
            self.service.submit("different", "another")
        self.client.release.set()
        self.assertEqual(self.wait(cid)["status"], "completed")
        self.assertTrue(self.busy.acquire(False))
        with self.assertRaises(BlockingIOError):
            self.service.submit("owner", "blocked by simulation")
        self.busy.release()

    def test_failure_retains_input_no_retry_or_private_error(self):
        self.client.fail = True
        cid = self.service.submit("owner", "Synthetic question")["conversation_id"]
        row = self.wait(cid)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error_code"], "hosted_turn_failed")
        self.assertEqual(len(row["messages"]), 1)
        self.assertNotIn("PRIVATE", json.dumps(row) + str(self.telemetry.rows))
        self.assertEqual(len(self.client.calls), 1)
        with self.assertRaises(ValueError):
            self.service.submit("owner", "retry", cid)

    def test_input_and_disabled_refusal(self):
        for message in ("", " ", "x" * 2001, None, 7, {"import": "customer.csv"},
                        "Import customers.csv", "contact actual@example.com",
                        "https://customer-data.example", "card 4111 1111 1111 1111"):
            with self.subTest(message_type=type(message).__name__), self.assertRaises(ValueError):
                self.service.submit("owner", message)
        with self.assertRaises(ValueError):
            self.service.submit("owner", "message", "conv_client_supplied")
        disabled = SimpleNamespace(database=":memory:", hosted_agent_name=None, hosted_agent_version=None)
        service = ChatService(disabled, threading.Lock())
        try:
            with self.assertRaises(ChatUnavailable):
                service.submit("owner", "Synthetic question")
        finally:
            service.close()
        self.assertEqual(self.client.calls, [])

    def test_turn_limit(self):
        cid = self.service.submit("owner", "Synthetic question")["conversation_id"]
        self.wait(cid)
        for _ in range(MAX_TURNS - 1):
            self.service.submit("owner", "Synthetic follow up", cid)
            self.wait(cid)
        with self.assertRaises(ValueError):
            self.service.submit("owner", "one too many", cid)

    def test_restart_marks_unknown_outcome_failed(self):
        cid = str(uuid.uuid4())
        with self.service.lock:
            self.service._save("owner", {
                "conversation_id": cid, "status": "running", "messages": [
                    {"role": "user", "content": "Synthetic pending"}], "error_code": None})
        self.service.close()
        self.service = ChatService(self.settings, self.busy, self.telemetry, self.client)
        row = self.service.get("owner", cid)
        self.assertEqual(row["error_code"], "worker_interrupted")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(self.client.calls, [])


class FakeChatClient(BaseChatClient):
    def __init__(self, fail=False):
        super().__init__()
        self.calls = []
        self.fail = fail

    async def _inner_get_response(self, *, messages, options, **kwargs):
        self.calls.append((messages, options))
        if self.fail:
            raise RuntimeError("private exception")
        return ChatResponse(
            messages=Message("assistant", ["Synthetic advice. No action executed."]),
            response_id=f"resp_{len(self.calls)}",
            usage_details={"input_token_count": 12, "output_token_count": 8})


class ClientContractTests(unittest.TestCase):
    def test_explicit_credential_modes_no_fallback(self):
        settings = SimpleNamespace(
            hosted_agent_name="cs-customer-service-chat", hosted_agent_version="7",
            client_id="managed-identity", tenant_id="assigned-tenant",
            credential_mode="azure_cli")
        with patch("azure.ai.projects.AIProjectClient"), \
                patch("azure.identity.AzureCliCredential") as cli, \
                patch("azure.identity.ManagedIdentityCredential") as managed:
            client = HostedClient(settings)
            cli.assert_called_once_with(tenant_id="assigned-tenant")
            managed.assert_not_called()
            client.close()

            cli.reset_mock()
            settings.credential_mode = "managed_identity"
            client = HostedClient(settings)
            managed.assert_called_once_with(client_id="managed-identity")
            cli.assert_not_called()
            client.close()

            managed.reset_mock()
            settings.credential_mode = "invalid"
            with self.assertRaises(ValueError):
                HostedClient(settings)
            cli.assert_not_called()
            managed.assert_not_called()

            settings.credential_mode = "azure_cli"
            cli.side_effect = RuntimeError("credential unavailable")
            with self.assertRaises(RuntimeError):
                HostedClient(settings)
            managed.assert_not_called()

    def test_dedicated_endpoint_pinned_version_zero_retries(self):
        settings = SimpleNamespace(hosted_agent_name="cs-customer-service-chat",
                                   hosted_agent_version="7", client_id="managed-identity")
        with patch("azure.ai.projects.AIProjectClient") as project_type, \
                patch("azure.identity.ManagedIdentityCredential"):
            project = project_type.return_value
            project.agents.get_version.return_value.definition.kind = "hosted"
            sdk = project.get_openai_client.return_value
            sdk.responses.create.return_value = SimpleNamespace(
                status="completed", id="resp_1", output_text="Synthetic explanation")
            client = HostedClient(settings)
            self.assertEqual(client.respond("Synthetic question", "resp_previous", {})["response_id"], "resp_1")
            project.get_openai_client.assert_called_once_with(
                agent_name="cs-customer-service-chat", max_retries=0, timeout=150)
            args = sdk.responses.create.call_args.kwargs
            self.assertEqual(args["previous_response_id"], "resp_previous")
            self.assertEqual(args["extra_body"]["agent_reference"]["version"], "7")
            self.assertNotIn("conversation", args)
            client.close()

    def test_replay_walks_stored_chain_oldest_first_and_maps_errors(self):
        settings = SimpleNamespace(hosted_agent_name="cs-customer-service-chat",
                                   hosted_agent_version="7", client_id="managed-identity")
        stored = {
            "resp_aaaaaaaa": SimpleNamespace(id="resp_aaaaaaaa", created_at=1, status="completed",
                                             output_text="first answer", previous_response_id=None),
            "resp_bbbbbbbb": SimpleNamespace(id="resp_bbbbbbbb", created_at=2, status="completed",
                                             output_text="second answer", previous_response_id="resp_aaaaaaaa"),
        }
        user = lambda text: SimpleNamespace(type="message", role="user",
                                            content=[SimpleNamespace(text=text)])
        with patch("azure.ai.projects.AIProjectClient") as project_type, \
                patch("azure.identity.ManagedIdentityCredential"):
            sdk = project_type.return_value.get_openai_client.return_value
            sdk.responses.retrieve.side_effect = stored.__getitem__
            sdk.responses.input_items.list.side_effect = lambda rid, order: [
                user("first question" if rid == "resp_aaaaaaaa" else "second question")]
            client = HostedClient(settings)
            service = ChatService(SimpleNamespace(database=":memory:"), threading.Lock(), None, client)
            turns = service.replay("resp_bbbbbbbb")["turns"]
            self.assertEqual([(t["user"], t["assistant"]) for t in turns],
                             [("first question", "first answer"), ("second question", "second answer")])
            with self.assertRaises(ValueError):
                service.replay("../admin")
            sdk.responses.retrieve.side_effect = type("Denied", (Exception,), {"status_code": 403})()
            with self.assertRaises(KeyError):
                service.replay("resp_bbbbbbbb")
            service.close()

    @unittest.skipUnless(HOSTED_AVAILABLE, "Hosted-only requirements not installed")
    def test_flat_source_import_and_native_definition(self):
        import os
        import shutil
        import subprocess
        import sys
        from azure.ai.projects.models import CodeConfiguration, HostedAgentDefinition, ProtocolVersionRecord
        root = Path(__file__).parent
        with tempfile.TemporaryDirectory() as directory:
            for relative in ("hosted/main.py", "hosted/runtime.py", "hosted/validation.py",
                             "scenarios.py", "telemetry.py"):
                shutil.copyfile(root / relative, Path(directory) / Path(relative).name)
            result = subprocess.run(
                [sys.executable, "-c", "import main; assert callable(main.main)"],
                cwd=directory, env={**os.environ, "PYTHONPATH": directory},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        definition = HostedAgentDefinition(
            cpu="0.5", memory="1Gi",
            code_configuration=CodeConfiguration(
                runtime="python_3_13", entry_point=["python", "main.py"],
                dependency_resolution="remote_build"),
            protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")])
        self.assertEqual(definition.kind, "hosted")
        self.assertEqual(definition.code_configuration.runtime, "python_3_13")
        self.assertIsNone(definition.environment_variables)


@unittest.skipUnless(HOSTED_AVAILABLE, "Hosted-only requirements not installed")
class FrameworkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.checkpoints = tempfile.TemporaryDirectory()
        self.checkpoint_patch = patch(
            "agent_framework_foundry_hosting.ResponsesHostServer._resolve_checkpoint_root",
            return_value=self.checkpoints.name)
        self.checkpoint_patch.start()
        self.addCleanup(self.checkpoints.cleanup)
        self.addCleanup(self.checkpoint_patch.stop)

    async def test_default_pacing_and_exact_role_bounds(self):
        import hosted.runtime as runtime
        clock, waits = [100.0], []

        async def sleep(delay):
            waits.append(delay)
            clock[0] += delay

        fake_asyncio = SimpleNamespace(Lock=asyncio.Lock, sleep=sleep, wait_for=asyncio.wait_for)
        with patch.object(runtime, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(runtime, "asyncio", fake_asyncio):
            client = FakeChatClient()
            await build_agent(client, SafeTelemetry()).run("Synthetic scenario")
        self.assertEqual(waits, [0, 7, 7])
        self.assertEqual([c[1]["max_output_tokens"] for c in client.calls], [250, 250, 350])

    async def test_actual_framework_pipeline(self):
        client, telemetry = FakeChatClient(), SafeTelemetry()
        agent = build_agent(client, telemetry, pacing_seconds=0)
        result = await agent.run("Synthetic SYN-101 cracked headphones")
        self.assertIn("No action executed", result.text)
        self.assertEqual(len(client.calls), 3)
        agent_rows = [r for r in telemetry.rows if r["operation"] == "chat.agent"]
        self.assertEqual([r["operation"] for r in telemetry.rows][0], "chat.workflow")
        self.assertEqual([r["agent"]["name"] for r in agent_rows],
                         ["triage", "policy", "resolution"])
        self.assertTrue(all(r["input_token_count"] == 12 for r in agent_rows))
        self.assertEqual([r["response_id"] for r in agent_rows], ["resp_1", "resp_2", "resp_3"])
        self.assertTrue(all(c[1]["store"] for c in client.calls))
        tags = [c[1]["metadata"] for c in client.calls]
        self.assertEqual([(t["agent_id"], t["agent_step"]) for t in tags],
                         [("triage", "1"), ("policy", "2"), ("resolution", "3")])
        self.assertEqual(len({t["session_id"] for t in tags}), 1)
        self.assertIn("Damage reported within 30 days", client.calls[0][0][0].text)

    async def test_framework_failure_no_retry(self):
        client = FakeChatClient(fail=True)
        agent = build_agent(client, SafeTelemetry(), pacing_seconds=0)
        with self.assertRaises(Exception):
            await agent.run("Synthetic issue")
        self.assertEqual(len(client.calls), 1)

    async def test_framework_refuses_customer_import_without_model(self):
        client = FakeChatClient()
        agent = build_agent(client, SafeTelemetry(), pacing_seconds=0)
        with self.assertRaises(Exception):
            await agent.run("Import customers.csv")
        self.assertEqual(client.calls, [])

    async def test_http_responses_positive_negative(self):
        import httpx
        from hosted.main import make_host, safe_logging
        client = FakeChatClient()
        with patch("socket.socket.connect", side_effect=AssertionError("offline network forbidden")):
            host = make_host(build_agent(client, SafeTelemetry(), pacing_seconds=0))
        safe_logging()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=host), base_url="http://localhost",
        ) as http:
            response = await http.post("/responses", json={
                "input": "Synthetic SYN-101 cracked", "stream": False})
            self.assertEqual(response.status_code, 200, response.text[:500])
            body = response.json()
            self.assertEqual(body["status"], "completed")
            self.assertTrue(body["id"])
            self.assertIn("No action executed", json.dumps(body["output"]))
            followup = await http.post("/responses", json={
                "input": "Synthetic follow up", "previous_response_id": body["id"], "stream": False})
            self.assertEqual(followup.status_code, 200, followup.text[:500])
            self.assertEqual(followup.json()["status"], "completed", followup.text[:500])
            self.assertIn("Synthetic SYN-101 cracked", client.calls[3][0][0].text)
            bad = await http.post("/responses", json={"input": {"import": "customers.csv"}})
            self.assertGreaterEqual(bad.status_code, 400)
        self.assertEqual(len(client.calls), 6)

    async def test_http_failure_is_redacted(self):
        import httpx
        from hosted.main import make_host, safe_logging
        client = FakeChatClient(fail=True)
        host = make_host(build_agent(client, SafeTelemetry(), pacing_seconds=0))
        safe_logging()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=host), base_url="http://localhost",
        ) as http:
            response = await http.post("/responses", json={"input": "Synthetic failure", "stream": False})
            self.assertNotIn("private exception", response.text)
            self.assertIn("hosted_turn_failed", response.text)
        self.assertEqual(len(client.calls), 1)

    async def test_trace_propagation_safe_structured_logs(self):
        import httpx
        from hosted.main import make_host, safe_logging
        from telemetry import Telemetry, LOGGER
        from opentelemetry.sdk.trace import TracerProvider
        client = FakeChatClient()
        host = make_host(build_agent(client, Telemetry(TracerProvider()), pacing_seconds=0))
        safe_logging()
        trace_id = "12345678901234567890123456789012"
        session = "ab" * 32
        with self.assertLogs(LOGGER, level="INFO") as logs:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=host), base_url="http://localhost",
            ) as http:
                response = await http.post("/responses", json={"input": "Synthetic confidential input"},
                    headers={"traceparent": f"00-{trace_id}-1234567890123456-01",
                             "baggage": f"cs.session_id={session}"})
                self.assertEqual(response.json()["status"], "completed")
        rows = [json.loads(record.getMessage()) for record in logs.records]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["trace_id"] == trace_id for row in rows))
        self.assertTrue(all(row["session_id"] == session for row in rows))
        self.assertEqual(len({r["span_id"] for r in rows}), 4)
        workflow = next(r for r in rows if r["operation_type"] == "chat.workflow")
        agents = [r for r in rows if r["operation_type"] == "chat.agent"]
        self.assertEqual(workflow["parent_span_id"], "1234567890123456")
        self.assertTrue(all(r["parent_span_id"] == workflow["span_id"] for r in agents))
        self.assertEqual([(r["agent_step"], r["agent_id"]) for r in agents],
                         [(1, "triage"), (2, "policy"), (3, "resolution")])
        required = set("trace_id span_id agent_id agent_version session_id customer_tier operation_type "
                       "model_id input_token_count output_token_count latency_ms status error_code".split())
        self.assertTrue(all(required <= row.keys() for row in rows))
        self.assertNotIn("confidential input", str(rows))


if __name__ == "__main__":
    unittest.main()
