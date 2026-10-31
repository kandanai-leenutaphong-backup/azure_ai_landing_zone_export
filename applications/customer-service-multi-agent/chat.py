"""Replica-local, non-durable synthetic chat. No simulation/financial tools."""
from contextlib import nullcontext
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from opentelemetry import baggage, trace
from opentelemetry.propagate import inject
from settings import PROJECT
from telemetry import LOGGER, SESSION_BAGGAGE
from hosted.validation import validate_message

MAX_TURNS = 8
REPLAY_TURNS = 50
RESPONSE_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def _text(content):
    if isinstance(content, str):
        return content
    return "".join(getattr(part, "text", None) or "" for part in content or [])


class ChatUnavailable(RuntimeError):
    """Composition maps this safe failure to HTTP 503."""


class HostedClient:
    """Dedicated Hosted endpoint, explicit credential mode, zero retries/fallback."""

    def __init__(self, settings):
        from azure.ai.projects import AIProjectClient
        from azure.identity import AzureCliCredential, ManagedIdentityCredential
        self.name, self.version = settings.hosted_agent_name, settings.hosted_agent_version
        if self.name != "cs-customer-service-chat" or not self.version:
            raise ChatUnavailable("hosted_agent_unconfigured")
        mode = getattr(settings, "credential_mode", "managed_identity")
        if mode == "managed_identity":
            self.credential = ManagedIdentityCredential(client_id=settings.client_id)
        elif mode == "azure_cli":
            self.credential = AzureCliCredential(tenant_id=settings.tenant_id)
        else:
            raise ValueError("Unsupported Azure credential mode")
        self.project = AIProjectClient(
            endpoint=PROJECT, credential=self.credential, allow_preview=True,
            retry_total=0, connection_timeout=5, read_timeout=150,
        )
        self.client = self.project.get_openai_client(
            agent_name=self.name, max_retries=0, timeout=150,
        )
        self.verified = False

    def respond(self, message, previous_response_id, headers):
        if not self.verified:
            version = self.project.agents.get_version(
                agent_name=self.name, agent_version=self.version)
            if version.definition.kind != "hosted":
                raise ChatUnavailable("hosted_definition_required")
            self.verified = True
        args = {"previous_response_id": previous_response_id} if previous_response_id else {}
        response = self.client.responses.create(
            input=message, stream=False, store=True, extra_headers=headers,
            extra_body={"agent_reference": {
                "type": "agent_reference", "name": self.name, "version": self.version}},
            **args,
        )
        if response.status != "completed" or not response.id or not response.output_text:
            raise ChatUnavailable("hosted_response_incomplete")
        if len(response.output_text) > 6000:
            raise ChatUnavailable("hosted_output_limit")
        return {"response_id": response.id, "content": response.output_text}

    def replay(self, response_id):
        """Walk previous_response_id back to the first turn; return turns oldest first."""
        turns, current = [], response_id
        while current and len(turns) < REPLAY_TURNS:
            response = self.client.responses.retrieve(current)
            user = [_text(item.content) for item in self.client.responses.input_items.list(current, order="asc")
                    if getattr(item, "type", "") == "message" and getattr(item, "role", "") == "user"]
            turns.append({"response_id": response.id, "created_at": response.created_at,
                          "status": response.status, "user": user[-1] if user else None,
                          "assistant": response.output_text})
            current = response.previous_response_id
        return list(reversed(turns))

    def close(self):
        self.client.close()
        self.project.close()
        self.credential.close()


class ChatService:
    """submit raises KeyError (404), BlockingIOError (429), ValueError (422).

    get returns None for missing/cross-owner UUID. No caller-supplied Foundry IDs.
    Injected client: respond(message, previous_response_id, headers) -> dict with
    response_id/content; close(). Composition owns route authentication.
    """

    def __init__(self, settings, busy, telemetry=None, hosted_client=None):
        self.settings, self.busy, self.telemetry = settings, busy, telemetry
        self.client = hosted_client
        self.db = sqlite3.connect(settings.database, check_same_thread=False)
        self.lock = threading.RLock()
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS chat_conversations "
                "(id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL)")
            for cid, data in self.db.execute("SELECT id,data FROM chat_conversations").fetchall():
                row = json.loads(data)
                if row["status"] in ("queued", "running"):
                    row.update(status="failed", error_code="worker_interrupted")
                    self.db.execute("UPDATE chat_conversations SET data=? WHERE id=?",
                                    (json.dumps(row), cid))

    @staticmethod
    def _id(value):
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("invalid_conversation_id") from None

    def _read(self, owner, cid):
        found = self.db.execute(
            "SELECT data FROM chat_conversations WHERE id=? AND owner=?",
            (cid, owner)).fetchone()
        return json.loads(found[0]) if found else None

    def _save(self, owner, row):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO chat_conversations VALUES (?,?,?)",
                            (row["conversation_id"], owner, json.dumps(row)))

    def submit(self, owner, message, conversation_id=None):
        validate_message(message)
        if not isinstance(owner, str) or not owner:
            raise ValueError("owner_required")
        cid = self._id(conversation_id) if conversation_id is not None else str(uuid.uuid4())
        with self.lock:
            if self.closed:
                raise ChatUnavailable("chat_closed")
            row = self._read(owner, cid) if conversation_id is not None else None
            if conversation_id is not None and row is None:
                raise KeyError(cid)
            if row and row["status"] == "failed":
                raise ValueError("failed_conversation_start_new")
            if row and len(row["messages"]) // 2 >= MAX_TURNS:
                raise ValueError("conversation_turn_limit")
            if self.client is None:
                if not self.settings.hosted_agent_name or not self.settings.hosted_agent_version:
                    raise ChatUnavailable("hosted_agent_unconfigured")
            if not self.busy.acquire(blocking=False):
                raise BlockingIOError("model_busy")
            try:
                if self.client is None:
                    self.client = HostedClient(self.settings)
                turn_id = str(uuid.uuid4())
                row = row or {"conversation_id": cid, "messages": [], "previous_response_id": None}
                row.update(status="queued", error_code=None, turn_id=turn_id)
                row["messages"].append({"role": "user", "content": message})
                self._save(owner, row)  # Durable locally before first remote operation.
                context = trace.get_current_span().get_span_context()
                headers = {}
                inject(headers)
                if context.is_valid:
                    row["trace_id"] = f"{context.trace_id:032x}"
                self.executor.submit(self._work, owner, row, message, headers)
            except Exception:
                self.busy.release()
                raise ChatUnavailable("chat_submit_failed") from None
        return {"conversation_id": cid, "turn_id": turn_id, "status": "queued"}

    def get(self, owner, conversation_id):
        cid = self._id(conversation_id)
        with self.lock:
            row = self._read(owner, cid)
        if row is None:
            return None
        return {k: row[k] for k in
                ("conversation_id", "status", "messages", "error_code", "trace_id") if k in row}

    def replay(self, response_id):
        """Stored Foundry turns ending at response_id. Caller authorizes. KeyError -> 404."""
        if not isinstance(response_id, str) or not RESPONSE_ID.match(response_id):
            raise ValueError("invalid_response_id")
        with self.lock:
            if self.client is None:
                if not self.settings.hosted_agent_name or not self.settings.hosted_agent_version:
                    raise ChatUnavailable("hosted_agent_unconfigured")
                self.client = HostedClient(self.settings)
        try:
            turns = self.client.replay(response_id)
        except Exception as error:
            status = getattr(error, "status_code", None)
            LOGGER.info(json.dumps({"operation_type": "chat.replay", "status": "error",
                                    "error_code": f"{type(error).__name__}:{status}"}))
            if status in (400, 403, 404):
                raise KeyError("not_found") from None
            raise ChatUnavailable("replay_failed") from None
        LOGGER.info(json.dumps({"operation_type": "chat.replay", "status": "ok",
                                "response_id": response_id, "turn_count": len(turns)}))
        return {"response_id": response_id, "turns": turns}

    def _work(self, owner, row, message, headers):
        from opentelemetry.propagate import extract
        session = hashlib.sha256(row["conversation_id"].encode()).hexdigest()
        pin = {"name": self.settings.hosted_agent_name or "hosted-chat",
               "version": self.settings.hosted_agent_version or "test"}
        event = (self.telemetry.event("chat.turn", session, agent=pin,
                                     context=extract(headers), journey_type="synthetic_chat")
                 if self.telemetry else nullcontext({}))
        try:
            with event as values:
                try:
                    inject(headers, context=baggage.set_baggage(SESSION_BAGGAGE, session))
                    context = trace.get_current_span().get_span_context()
                    if context.is_valid:
                        row["trace_id"] = f"{context.trace_id:032x}"
                    with self.lock:
                        row["status"] = "running"
                        self._save(owner, row)
                    result = self.client.respond(message, row["previous_response_id"], headers)
                    content, response_id = result["content"], result["response_id"]
                    if not isinstance(content, str) or not content.strip() or len(content) > 6000:
                        raise ValueError("hosted_output_invalid")
                    if not isinstance(response_id, str) or not response_id:
                        raise ValueError("hosted_response_invalid")
                    values["response_id"] = response_id
                    row["messages"].append({"role": "assistant", "content": content})
                    row.update(status="completed", previous_response_id=response_id)
                except Exception:
                    row.update(status="failed", error_code="hosted_turn_failed")
                    values.update(status="failed", error_code="hosted_turn_failed")
                finally:
                    with self.lock:
                        self._save(owner, row)
        finally:
            self.busy.release()

    def close(self):
        with self.lock:
            self.closed = True
        # One synchronous Responses call, 150s transport timeout, no retries/poll loop.
        self.executor.shutdown(wait=True)
        if self.client:
            self.client.close()
        self.db.close()
