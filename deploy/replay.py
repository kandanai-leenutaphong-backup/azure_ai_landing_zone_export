"""Trace or span ID -> multi-agent span tree -> stored Foundry conversation, read-only.

    bash deploy/deploy.sh -e sea replay --trace-id <32 hex>
    bash deploy/deploy.sh -e sea replay --span-id <16 hex>   # any span in the tree
    ... --json                                                # machine-readable output

Spans come from Application Insights (`APP_INSIGHTS_NAME`), falling back to the SEA Log
Analytics console rows for turns older than the export. Turns are ordered by the session's
`chat.turn` spans (`session_id`); each turn's text comes from Foundry stored Responses, read through the
app's authenticated `/api/chat/replay/{response_id}` with your delegated token: Foundry binds
stored responses to the app identity, and the app serves them only to Entra object IDs in
`REPLAY_OPERATOR_OBJECT_IDS`. Each sub-agent's own input/output (hosted v3+) comes from the
Foundry Cosmos `run-state-v1` container (`FOUNDRY_COSMOS_*`), matched by `trace_id` and
joined to spans by `span_id`; it needs the VPN and Cosmos data reader role. Printed,
never written to disk. No inference, no writes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from manage import az, config

TRACE = re.compile(r"^[0-9a-f]{32}$")
SPAN = re.compile(r"^[0-9a-f]{16}$")
RESPONSE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
SESSION = re.compile(r"^[0-9a-f]{64}$")
MAX_TURNS = 50
FIELDS = ("agent_id", "agent_step", "session_id", "response_id", "model_id", "input_token_count",
          "output_token_count", "status", "error_code")


def appinsights_query(span_filter: str) -> str:
    return f"""dependencies | where timestamp > ago(90d) | where {span_filter}
| where name in ("chat.turn", "chat.workflow", "chat.agent")
| project timestamp, trace_id=operation_Id, span_id=id, parent_span_id=operation_ParentId,
    service=cloud_RoleName, operation=name, duration_ms=duration, d=customDimensions"""


def workspace_query(span_filter: str) -> str:
    return f"""ContainerAppConsoleLogs_CL | where TimeGenerated > ago(90d)
| where ContainerAppName_s == "customer-service-multi-agent"
| extend d = parse_json(Log_s) | extend trace_id=tostring(d.trace_id), span_id=tostring(d.span_id)
| where {span_filter}
| where tostring(d.operation_type) in ("chat.turn", "chat.workflow", "chat.agent")
| project timestamp=TimeGenerated, trace_id, span_id, parent_span_id=tostring(d.parent_span_id),
    service=tostring(d.service_name), operation=tostring(d.operation_type),
    duration_ms=todouble(d.latency_ms), d"""


def rows(result) -> list[dict]:
    """App Insights returns {tables:[...]}; Log Analytics CLI returns a list of dicts."""
    if isinstance(result, dict):
        table = result["tables"][0]
        names = [c["name"] for c in table["columns"]]
        result = [dict(zip(names, raw)) for raw in table["rows"]]
    out = []
    for row in result or []:
        row = {k: v for k, v in row.items() if k != "TableName"}
        dims = row.pop("d", None) or {}
        dims = json.loads(dims) if isinstance(dims, str) else dims
        row.update({k: dims.get(k) for k in FIELDS})
        if row.get("agent_step") not in (None, ""):
            row["agent_step"] = int(row["agent_step"])
        out.append(row)
    return out


def spans(c: dict, *, trace_id=None, span_id=None, session_id=None) -> tuple[list[dict], str]:
    """Return spans and their source; App Insights first, Log Analytics fallback."""
    if trace_id:
        ai, la = f'operation_Id == "{trace_id}"', f'trace_id == "{trace_id}"'
    elif span_id:
        ai, la = f'id == "{span_id}"', f'span_id == "{span_id}"'
    else:
        ai = f'name == "chat.turn" and tostring(customDimensions.session_id) == "{session_id}"'
        la = f'tostring(d.operation_type) == "chat.turn" and tostring(d.session_id) == "{session_id}"'
    app = az("monitor", "app-insights", "component", "show", "--subscription", c["APP_SUBSCRIPTION_ID"],
             "-g", c["APP_RESOURCE_GROUP"], "-a", c["APP_INSIGHTS_NAME"], "--query", "appId")
    # CLI default --offset is 1h; match the 90d KQL window.
    found = rows(az("monitor", "app-insights", "query", "--app", app, "--offset", "90d",
                    "--analytics-query", appinsights_query(ai)))
    if found:
        return found, "application_insights"
    found = rows(az("monitor", "log-analytics", "query", "-w", c["LOG_ANALYTICS_WORKSPACE_ID"],
                    "--analytics-query", workspace_query(la)))
    return found, "log_analytics"


def tree(found: list[dict]) -> list[tuple[int, dict]]:
    """Order spans parent-first; unknown parents (gateway hop) become roots."""
    ids = {s["span_id"] for s in found}
    children: dict = {}
    for s in found:
        children.setdefault(s["parent_span_id"] if s["parent_span_id"] in ids else None, []).append(s)
    order = {"chat.turn": 0, "chat.workflow": 1, "chat.agent": 2}
    key = lambda s: (order.get(s["operation"], 9), s.get("agent_step") or 0, str(s["timestamp"]))
    out = []

    def walk(parent, depth):
        for s in sorted(children.get(parent, []), key=key):
            out.append((depth, s))
            walk(s["span_id"], depth + 1)
    walk(None, 0)
    return out


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(getattr(p, "text", None) or (p.get("text", "") if isinstance(p, dict) else "")
                   for p in content or [])


def conversation(c: dict, response_id: str) -> list[dict]:
    """Stored turns through the app's owner-checked API (Foundry binds responses to the app identity)."""
    import httpx
    from azure.identity import AzureCliCredential
    if not RESPONSE.match(response_id):
        raise SystemExit("Logged response_id has an unexpected shape.")
    with AzureCliCredential(tenant_id=c["TENANT_ID"]) as credential:
        token = credential.get_token(f"api://{c['AUTH_CLIENT_ID']}/.default").token
    try:
        with httpx.Client(base_url=f"https://{c['PUBLIC_HOST']}", timeout=httpx.Timeout(90, connect=10),
                          headers={"Authorization": "Bearer " + token}) as client:
            answer = client.get(f"/api/chat/replay/{response_id}")
    except httpx.TransportError:
        raise SystemExit(f"Cannot reach https://{c['PUBLIC_HOST']}. The hub WAF gateway is probably "
                         "stopped: run `bash deploy/deploy.sh -e sea status`, then "
                         "`bash deploy/deploy.sh -e sea start-gateway`.") from None
    if answer.status_code == 403:
        raise LookupError("You are not a replay operator: add your Entra object ID to "
                          "REPLAY_OPERATOR_OBJECT_IDS in deploy/env/sea.env, then release.")
    if answer.status_code == 404:
        raise LookupError("Stored response not found in Foundry (deleted, or not created by this app).")
    answer.raise_for_status()
    return answer.json()["turns"]


def cosmos_query(trace_id: str) -> str:
    return ('SELECT c.partition_id, c["object"].metadata AS m FROM c '
            f'WHERE c["object"].metadata.trace_id = "{trace_id}"')


def agent_steps(c: dict, trace_id: str) -> list[dict]:
    """Each sub-agent's stored input/output, tagged with trace_id/span_id (hosted v3+)."""
    from azure.cosmos import CosmosClient
    from azure.identity import AzureCliCredential
    client = CosmosClient(f"https://{c['FOUNDRY_COSMOS_ACCOUNT']}.documents.azure.com:443/",
                          AzureCliCredential(tenant_id=c["TENANT_ID"]), connection_timeout=10)
    container = client.get_database_client("enterprise_memory").get_container_client(c["FOUNDRY_COSMOS_CONTAINER"])
    steps = []
    for doc in container.query_items(cosmos_query(trace_id), enable_cross_partition_query=True):
        items = container.query_items(
            'SELECT c._ts, c["object"].item_resource AS item FROM c WHERE c.partition_id = @p '
            'AND IS_DEFINED(c["object"].item_resource)',
            parameters=[{"name": "@p", "value": doc["partition_id"]}], partition_key=doc["partition_id"])
        text = {}
        for row in sorted(items, key=lambda r: r["_ts"]):
            text.setdefault(row["item"].get("role"), text_of(row["item"].get("content")))
        m = doc["m"]
        steps.append({"agent_id": m.get("agent_id"), "agent_step": int(m.get("agent_step") or 0),
                      "span_id": m.get("span_id"), "partition_id": doc["partition_id"],
                      "input": text.get("user"), "output": text.get("assistant")})
    return sorted(steps, key=lambda s: s["agent_step"])


def replay(c: dict, trace_id=None, span_id=None) -> dict:
    found, source = spans(c, trace_id=trace_id, span_id=span_id)
    if span_id:
        if not found:
            raise SystemExit(f"Span {span_id} not found in Application Insights or Log Analytics.")
        trace_id = found[0]["trace_id"]
        found, source = spans(c, trace_id=trace_id)
    if not found:
        raise SystemExit(f"Trace {trace_id} not found (ingestion can lag ~5 min).")
    turn = next((s for s in found if s["operation"] == "chat.turn" and s.get("response_id")), None)
    result = {"trace_id": trace_id, "span_source": source,
              "spans": [dict(s, depth=d) for d, s in tree(found)], "turns": [], "agents": []}
    if c.get("FOUNDRY_COSMOS_ACCOUNT") and c.get("FOUNDRY_COSMOS_CONTAINER"):
        try:
            result["agents"] = agent_steps(c, trace_id)
        except Exception as error:  # Private endpoint: needs VPN; reader role per README.
            result["agents_note"] = f"Cosmos per-agent lookup unavailable ({type(error).__name__}); connect VPN."
    if not turn:
        result["note"] = "No chat.turn span with response_id in this trace (pre-response_id logging or failed turn)."
        return result
    try:
        session = turn.get("session_id") or ""
        if SESSION.match(session):
            # Foundry's stored hosted responses drop previous_response_id; the session's
            # chat.turn spans are the turn ledger.
            ledger, _ = spans(c, session_id=session)
        else:
            ledger = [turn]
        ledger = sorted({s["response_id"]: s for s in ledger if s.get("response_id")}.values(),
                        key=lambda s: str(s["timestamp"]))[-MAX_TURNS:]
        for s in ledger:
            stored = conversation(c, s["response_id"])[-1]
            result["turns"].append(dict(stored, trace_id=s["trace_id"],
                                        selected=s["response_id"] == turn["response_id"]))
    except LookupError as error:
        result["note"] = str(error)
    return result


def render(r: dict) -> str:
    lines = [f"Trace {r['trace_id']}  (spans from {r['span_source']})", ""]
    for s in r["spans"]:
        label = s["operation"] + (f" step {s['agent_step']} {s['agent_id']}" if s["operation"] == "chat.agent" else "")
        extra = f"  response_id={s['response_id']}" if s.get("response_id") else ""
        tokens = (f"  tokens={s['input_token_count']}/{s['output_token_count']}"
                  if s.get("input_token_count") is not None else "")
        lines.append(f"{'   ' * s['depth']}{'└─ ' if s['depth'] else ''}{label}  [{s['service']}]  "
                     f"span={s['span_id']} parent={s['parent_span_id']}  {float(s['duration_ms'] or 0):.0f}ms  "
                     f"{s['status']}{' ' + s['error_code'] if s.get('error_code') else ''}{tokens}{extra}")
    if r.get("note"):
        lines += ["", r["note"]]
    if r.get("agents"):
        lines += ["", f"Per-agent records ({len(r['agents'])}, from Cosmos run-state; join key span_id)", ""]
        for a in r["agents"]:
            lines.append(f"--- step {a['agent_step']} {a['agent_id']}  span={a['span_id']}  "
                         f"partition={a['partition_id'].rsplit('/', 1)[-1]}  input={len(a['input'] or '')} chars")
            lines.append(f"OUTPUT: {a['output']}")
            lines.append("")
    elif r.get("agents_note"):
        lines += ["", r["agents_note"]]
    if r["turns"]:
        lines += ["", f"Conversation replay ({len(r['turns'])} turns, from Foundry stored Responses)", ""]
        for i, t in enumerate(r["turns"], 1):
            mark = "  <== this trace" if t["selected"] else ""
            lines.append(f"--- turn {i}  response_id={t['response_id']}  trace={t['trace_id'] or 'unknown'}{mark}")
            lines.append(f"USER:      {t['user'] if t['user'] is not None else '(not returned by input_items)'}")
            lines.append(f"ASSISTANT: {t['assistant']}")
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trace-id")
    group.add_argument("--span-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    trace_id = args.trace_id.lower().strip() if args.trace_id else None
    span_id = args.span_id.lower().strip() if args.span_id else None
    if trace_id and not TRACE.match(trace_id) or span_id and not SPAN.match(span_id):
        parser.error("trace ID must be 32 hex characters; span ID 16 hex characters.")
    result = replay(config("sea"), trace_id=trace_id, span_id=span_id)
    print(json.dumps(result, indent=2, default=str) if args.json else render(result))


if __name__ == "__main__":
    sys.exit(main())
