from __future__ import annotations

import json

from manage import ROOT, STATE, az, config

FIELDS = (
    "trace_id", "span_id", "agent_id", "agent_version", "session_id", "customer_tier",
    "operation_type", "model_id", "input_token_count", "output_token_count",
    "latency_ms", "status", "error_code",
)
OPERATIONS = {
    "triage", "policy", "resolution", "judge_factual_accuracy", "judge_task_completion",
    "judge_tone", "judge_consistency", "tool.execute", "tool.readback", "simulation.snapshot",
}


def query(text: str) -> list[dict]:
    workspace = config("sea")["LOG_ANALYTICS_WORKSPACE_ID"]
    response = az(
        "rest", "--method", "post", "--resource", "https://api.loganalytics.io",
        "--url", f"https://api.loganalytics.azure.com/v1/workspaces/{workspace}/query",
        "--body", json.dumps({"query": text}),
    )
    if response.get("error") or len(response.get("tables", [])) != 1:
        raise RuntimeError("Log Analytics did not return one complete metric table.")
    table = response["tables"][0]
    return [{
        column["name"]: json.loads(value) if column["type"] == "dynamic" and isinstance(value, str) else value
        for column, value in zip(table["columns"], row, strict=True)
    } for row in table["rows"]]


def trace_summary(trace_id: str, operations: set[str]) -> dict:
    if not isinstance(trace_id, str) or len(trace_id) != 32 or any(c not in "0123456789abcdef" for c in trace_id):
        raise ValueError("Native trace receipt contains an invalid trace ID.")
    absent = " or ".join(f"not(bag_has_key(event, '{field}'))" for field in FIELDS)
    trace = query(f"""
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(7d) and ContainerAppName_s == "customer-service-multi-agent"
| extend event=parse_json(Log_s)
| where tostring(event.trace_id) == "{trace_id}"
| summarize event_count=count(), missing_fields=countif({absent}),
    operations=make_set(tostring(event.operation_type))
""")
    if len(trace) != 1 or not trace[0]["event_count"]:
        raise RuntimeError("Native trace not ingested yet. Rerun verify-logs; do not rerun inference.")
    if trace[0]["missing_fields"] or not operations.issubset(set(trace[0]["operations"])):
        raise RuntimeError("Ingested trace lacks required structured fields or expected operations.")
    return trace[0]


def verify() -> dict:
    browser = STATE / "browser-verification.json"
    smoke = STATE / "smoke.json"
    if browser.is_file():
        trace_id = json.loads(browser.read_text())["trace_id"]
    elif smoke.is_file():
        trace_id = json.loads(smoke.read_text())["results"][0]["trace_id"]
    else:
        raise RuntimeError("Run exercise first; no completed simulation trace receipt exists.")
    trace = trace_summary(trace_id, OPERATIONS)
    chat_traces = []
    chat_path = STATE / "chat-browser-verification.json"
    if chat_path.is_file():
        chat = json.loads(chat_path.read_text())
        if chat.get("status") != "passed" or not chat.get("turns"):
            raise RuntimeError("Chat browser receipt does not prove completed turns.")
        for turn in chat["turns"]:
            if turn.get("status") != "completed":
                raise RuntimeError("Chat browser receipt contains an incomplete turn.")
            chat_traces.append({"trace_id": turn["trace_id"],
                                **trace_summary(turn["trace_id"], {"chat.turn"})})
    metrics = query((ROOT / "deploy/metric-hierarchy.kql").read_text())
    if {row["tier"] for row in metrics} != {"system", "journey", "agent"}:
        raise RuntimeError("Persisted scorecards do not contain all three aggregation tiers.")
    receipt = {"trace_id": trace_id, "trace": trace, "metrics": metrics, "chat_traces": chat_traces}
    (STATE / "metrics-readback.json").write_text(json.dumps(receipt, indent=2))
    return {"trace_id": trace_id, "event_count": trace["event_count"], "missing_fields": 0,
            "tiers": ["system", "journey", "agent"], "metric_rows": len(metrics),
            "chat_traces": chat_traces}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
