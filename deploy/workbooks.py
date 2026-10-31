"""Publish two owned, shared Workbooks over existing structured application logs."""
from __future__ import annotations

import json
import tempfile
import uuid
from urllib.parse import quote

from manage import OWNER, ROOT, STATE, az, config
from verify_logs import FIELDS, query

API = "2023-06-01"
BASE = """
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(7d)
| where ContainerAppName_s == "customer-service-multi-agent"
| extend event=parse_json(Log_s)
| where isnotempty(event.trace_id)
"""


def read_workbook(url):
    return az("rest", "--method", "get", "--url", url + "&canFetchContent=true")


def text(name, markdown):
    return {"type": 1, "name": name, "content": {"json": markdown}}


def panel(name, title, kql, workspace, visualization="table"):
    return {"type": 3, "name": name, "content": {
        "version": "KqlItem/1.0", "title": title, "query": kql,
        "queryType": 0, "resourceType": "microsoft.operationalinsights/workspaces",
        "crossComponentResources": [workspace], "visualization": visualization,
        "showExportToExcel": False,
    }}


def definitions(workspace):
    hierarchy = (ROOT / "deploy/metric-hierarchy.kql").read_text()
    quality = [text("quality-intro", """# Customer service: quality hierarchy
**Window: last 7 days.** Read top to bottom: system, journey type, component.
These are synthetic simulation scorecards, not automatic chat-quality evaluations.
Task completion is fixture/tool verified. Judges remain uncalibrated: no accepted
gold baseline or measured human agreement. Business resolution/reopen impact is unknown.
Empty tables mean no matching telemetry, not a passing score. No alert or drift schedule
is created. Use journey and agent columns to locate the component affecting a scenario.""")]
    for tier, title in (("system", "Tier 1: system outcomes"),
                        ("journey", "Tier 2: journey-type breakdown"),
                        ("agent", "Tier 3: agent correctness, latency, errors and tokens")):
        quality.append(panel(tier, title, hierarchy + f'\n| where tier == "{tier}"', workspace))
    absent = " or ".join(f"not(bag_has_key(event, '{field}'))" for field in FIELDS)
    string_fields = {
        "trace_id", "span_id", "agent_id", "agent_version", "session_id", "customer_tier",
        "operation_type", "model_id", "status", "error_code",
    }
    converters = {field: "tostring" for field in string_fields}
    converters.update({"input_token_count": "tolong", "output_token_count": "tolong",
                       "latency_ms": "todouble"})
    projections = ", ".join(
        f"{field}={converters[field]}(event.{field})" for field in FIELDS
    )
    operations = [
        text("operations-intro", """# Customer service: operations and correlated logs
**Window: last 7 days.** SEA Container App structured events only.
Chat-turn outcomes are operational signals, not quality scores. Native Hosted Agent
triage/policy/resolution console logs are separate and are not ingested into this table.
Use `deploy.sh -e sea verify-hosted-logs` for those logs. Application Insights/OTLP trace
export and gateway access/firewall diagnostics are not configured.
All tables expose allowlisted telemetry fields only, never raw log payloads or messages.
Token usage absent from a provider event is unknown, not zero.
Trace rows are sorted by trace ID then time to group correlated operations."""),
        panel("volume", "Structured events over time", BASE + """
| summarize events=count() by bin(TimeGenerated, 1h), operation=tostring(event.operation_type)
| order by TimeGenerated asc
""", workspace, "timechart"),
        panel("outcomes", "Operation outcomes and latency", BASE + """
| summarize events=count(), errors=countif(tostring(event.status) == "error"),
    latency_avg_ms=avg(todouble(event.latency_ms)),
    latency_p95_ms=percentile(todouble(event.latency_ms),95)
    by operation=tostring(event.operation_type), agent=tostring(event.agent_id)
| extend error_rate=todouble(errors)/events
| order by errors desc, events desc
""", workspace),
        panel("tokens", "Reported provider token consumption", BASE + """
| where isnotnull(event.input_token_count) or isnotnull(event.output_token_count)
| summarize events_with_usage=count(), input_tokens=sum(tolong(event.input_token_count)),
    output_tokens=sum(tolong(event.output_token_count))
    by agent=tostring(event.agent_id), version=tostring(event.agent_version),
       model=tostring(event.model_id)
| order by input_tokens desc
""", workspace),
        panel("schema", "Required-field completeness", BASE + f"""
| summarize events=count(), missing_required_fields=countif({absent}),
    latest_event=max(TimeGenerated) by operation=tostring(event.operation_type)
| order by missing_required_fields desc
""", workspace),
        panel("errors", "Recent structured errors", BASE + f"""
| where tostring(event.status) == "error" or isnotempty(event.error_code)
| project TimeGenerated, {projections}
| top 100 by TimeGenerated desc
""", workspace),
        panel("trace", "Correlated operation timeline (latest 200 events)", BASE + f"""
| top 200 by TimeGenerated desc
| project TimeGenerated, {projections}, parent_span_id=tostring(event.parent_span_id),
    service=tostring(event.service_name), agent_step=tolong(event.agent_step),
    response_id=tostring(event.response_id)
| order by trace_id asc, TimeGenerated asc
""", workspace),
    ]
    return {key: {"version": "Notebook/1.0", "items": items,
                  "fallbackResourceIds": [workspace], "isLocked": False}
            for key, items in (("quality", quality), ("operations", operations))}


def assert_owned(resource, workspace):
    if (resource.get("tags", {}).get("project") != OWNER
            or resource.get("tags", {}).get("capability") != "observability-workbooks"
            or resource.get("properties", {}).get("sourceId", "").lower() != workspace.lower()):
        raise RuntimeError("Existing workbook is not owned by this deployment/workspace.")


def put_workbook(url, body, etag=None):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json") as request_body:
        json.dump(body, request_body)
        request_body.flush()
        request = ["rest", "--method", "put", "--url", url]
        if etag:
            request.extend(["--headers", f"If-Match={etag}"])
        request.extend(["--body", f"@{request_body.name}"])
        return az(*request)


def deploy():
    settings = config("sea")
    account = az("account", "show")
    if (account["tenantId"] != settings["TENANT_ID"]
            or account["id"] != settings["HUB_SUBSCRIPTION_ID"]
            or account["environmentName"] != "AzureCloud"):
        raise RuntimeError("Select the configured tenant/hub subscription in AzureCloud first.")
    workspace = az("monitor", "log-analytics", "workspace", "show",
                   "--subscription", settings["APP_SUBSCRIPTION_ID"],
                   "-g", settings["APP_RESOURCE_GROUP"], "-n", "workspace-spoke-app-sea")
    if workspace["customerId"] != settings["LOG_ANALYTICS_WORKSPACE_ID"]:
        raise RuntimeError("Workbook workspace differs from configured log destination.")
    existing = az("resource", "list", "--subscription", settings["APP_SUBSCRIPTION_ID"],
                  "-g", settings["APP_RESOURCE_GROUP"], "--resource-type", "Microsoft.Insights/workbooks")
    ids = {row["id"].lower() for row in existing}
    documents = definitions(workspace["id"])
    # Query every panel before cloud writes; partial errors fail through the existing query owner.
    counts = {key: {item["name"]: len(query(item["content"]["query"]))
                    for item in document["items"] if item["type"] == 3}
              for key, document in documents.items()}
    receipts = []
    for key, document in documents.items():
        name = str(uuid.uuid5(uuid.NAMESPACE_URL, workspace["id"].lower() + "/" + OWNER + "/" + key))
        resource_id = (f"/subscriptions/{settings['APP_SUBSCRIPTION_ID']}/resourceGroups/"
                       f"{settings['APP_RESOURCE_GROUP']}/providers/Microsoft.Insights/workbooks/{name}")
        url = f"https://management.azure.com{resource_id}?api-version={API}"
        current = read_workbook(url) if resource_id.lower() in ids else None
        if current:
            assert_owned(current, workspace["id"])
        title = f"Customer service multi-agent - {key.title()}"
        desired = {"location": workspace["location"], "kind": "shared",
                   "tags": {"project": OWNER, "capability": "observability-workbooks"},
                   "properties": {"displayName": title, "category": "workbook",
                                  "sourceId": workspace["id"], "version": "Notebook/1.0",
                                  "serializedData": json.dumps(document)}}
        matches = current and all(
            (current.get("properties", {}).get(field, "").lower() == value.lower())
            if field == "sourceId"
            else current.get("properties", {}).get(field) == value
            for field, value in desired["properties"].items())
        if not matches:
            put_workbook(url, desired, current["etag"] if current else None)
        actual = read_workbook(url)
        assert_owned(actual, workspace["id"])
        if (actual.get("kind") != "shared"
                or actual["properties"]["displayName"] != title
                or actual["properties"].get("version") != "Notebook/1.0"
                or json.loads(actual["properties"]["serializedData"]) != document):
            raise RuntimeError("Workbook readback differs from accepted definition.")
        receipts.append({"name": title, "id": resource_id,
                         "url": "https://portal.azure.com/#resource" + quote(resource_id, safe="/"),
                         "query_rows": counts[key], "definition_verified": True,
                         "changed": not bool(matches)})
    result = {"workspace_id": workspace["id"], "window": "7 days", "workbooks": receipts,
              "portal_render_verified": False}
    STATE.mkdir(exist_ok=True)
    (STATE / "workbooks.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(deploy(), indent=2))
