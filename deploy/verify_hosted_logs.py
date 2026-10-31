"""Inspect native Hosted console events without retaining arbitrary log payloads."""
from __future__ import annotations

import json
import time

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

from manage import STATE, config
from hosted_agent import NAME
from verify_logs import FIELDS

CORRELATION = ("parent_span_id", "service_name", "agent_step")


def inspect_events(lines) -> list[dict]:
    events = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        try:
            envelope = json.loads(line[5:].strip())
            if not isinstance(envelope, dict):
                continue
            row = json.loads(envelope["message"]) if isinstance(envelope.get("message"), str) else envelope
        except (ValueError, KeyError, TypeError):
            continue
        if isinstance(row, dict) and set(FIELDS).issubset(row):
            events.append({name: row.get(name) for name in FIELDS + CORRELATION})
    return events


def agent_identities(events) -> set:
    return {row["agent_id"] for row in events if row.get("operation_type") == "chat.agent"}


def workflow_complete(events) -> bool:
    # The workflow row is emitted when its span closes, after every agent step.
    return len(agent_identities(events)) >= 3 and any(
        row.get("operation_type") == "chat.workflow" for row in events)


def verify() -> dict:
    settings = config("sea")
    pin = json.loads((STATE / "hosted-agent.json").read_text())
    with AzureCliCredential(tenant_id=settings["TENANT_ID"]) as credential, AIProjectClient(
        endpoint=settings["FOUNDRY_PROJECT_ENDPOINT"], credential=credential, allow_preview=True,
        retry_total=0, connection_timeout=10, read_timeout=20,
    ) as project:
        sessions = [s for s in project.agents.list_sessions(agent_name=NAME)
                    if s.as_dict().get("version_indicator", {}).get("agent_version") == pin["version"]]
        if not sessions:
            raise RuntimeError("No native Hosted session exists. Invoke the bounded chat first.")
        # Service lists oldest first; inspect the newest session on the pinned version.
        session = max(sessions, key=lambda s: s.as_dict().get("created_at") or 0)
        response_holder = []

        def retain_response(pipeline, chunks, headers):
            response_holder.append(pipeline.http_response)
            return chunks

        stream = project.agents.get_session_log_stream(
            agent_name=NAME, agent_version=pin["version"], session_id=session.agent_session_id,
            cls=retain_response,
        )
        buffer = ""
        events = []
        deadline = time.monotonic() + 60
        try:
            for chunk in stream:
                buffer += chunk.decode("utf-8", errors="replace")
                if len(buffer) > 1_000_000:
                    raise RuntimeError("Native log frame exceeds bounded inspection size.")
                lines = buffer.split("\n")
                buffer = lines.pop()
                events.extend(inspect_events(lines))
                if workflow_complete(events):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Native agent telemetry not present in the bounded log read.")
        finally:
            for response in response_holder:
                response.close()
        identities = agent_identities(events)
        if not workflow_complete(events):
            raise RuntimeError("Native logs do not yet prove three agent steps and the workflow row.")
        receipt = {
            "name": NAME, "version": pin["version"], "session_id": session.agent_session_id,
            "event_count": len(events), "required_field_count": len(FIELDS),
            "agent_ids": sorted(identities), "events": events, "raw_logs_retained": False,
        }
        (STATE / "hosted-logs.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return {key: value for key, value in receipt.items() if key != "events"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
