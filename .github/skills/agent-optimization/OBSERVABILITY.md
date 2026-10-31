# Foundry Agent Metrics And Observability

> Research only: upstream capabilities and historical evidence, not implemented library support.

Evidence reviewed 2026-09-15. No telemetry was enabled, queried, or measured in Azure.
Distinguish documentation guarantees, preview behavior, and recommendations below.

## Time-Sensitive Content Migration

Microsoft documents a **September 30, 2026** change to newly ingested sensitive GenAI
trace values. Before that date, the listed values flow into both existing telemetry tables
and `AppGenAIContent`. From that date, existing-table values become pointers to the new
table. Historical data remains where it was ingested.

Affected attributes:

- `gen_ai.input.messages`
- `gen_ai.output.messages`
- `gen_ai.system_instructions`
- `gen_ai.tool.definitions`
- `gen_ai.tool.call.arguments`
- `gen_ai.tool.call.result`
- `gen_ai.evaluation.explanation`

Custom KQL, alert rules, dashboards, workbooks, and reports reading these values from
`AppDependencies`, `AppTraces`, or `AppEvents` need review. The guide says built-in
Foundry/Application Insights experiences adapt automatically.

Two controls must not be conflated: **routing content into its own table** and **protecting
that table**. Early routing uses the subscription feature `protectGenAISensitiveData`.
Setting the table's protection level to Protected is a separate step. The documented
temporary opt-out is `optOutProtectGenAISensitiveData`, ending September 30, 2027; it is
not a recommended security bypass and was not enabled here.

Once protected, ordinary reader access does not grant content access. The named privilege
is Privileged Monitoring Data Reader; custom roles with the applicable protected-table
DataActions also require review. Historical copies in older tables are not retroactively
removed or protected by routing future data differently.

Sources: [migration and sensitive-content protection](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/traces-sensitive-content),
[protected-table configuration](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/protected-tables-configure),
[log access control](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/manage-access).

## Four Different Measurement Layers

| Layer | What It Answers | What It Does Not Prove |
| --- | --- | --- |
| Platform/model metrics | Request volume, token consumption, server availability, gateway latency, provisioned utilization | Agent task success, correct tool choice, end-user experience |
| Agent traces and application telemetry | Execution path, errors, tool/model calls, span timing, available token measurements | Unobserved steps, unsampled traffic, independent persistence or authorization |
| Evaluation and feedback | Judged quality, safety, task behavior, human ratings | Perfect judge accuracy or representative coverage without an appropriate dataset/sample |
| Billing/Cost Management | Recorded post-consumption charges | Immediate per-span cost or complete attribution from token counts alone |

Foundry's agent Monitor dashboard reads its connected Application Insights telemetry.
Model platform metrics use Azure Monitor's time-series store. These are related but not
interchangeable sources.

References: [agent dashboard](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard),
[model monitoring](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/monitor-models),
[monitor billing](https://learn.microsoft.com/en-us/azure/azure-monitor/cost-usage).

## Collection And Instrumentation

The tracing/data-handling guide says tracing is off until explicitly enabled by connecting
Application Insights. Enabling it starts project-level collection. Disconnecting stops new
collection; it does not delete retained data.

Server-side tracing is the recommended starting point for Foundry-hosted agents. It becomes
available after connecting Application Insights. Client-side/framework instrumentation is
additional work when application logic, external calls, or custom steps need visibility.
Do not interpret server-side collection as proof that every line inside hosted agent code
has been instrumented.

Tracing is documented as GA for prompt and hosted agents, preview for workflow and external
agents. Individual replay, dashboard, feedback, or ingestion-auth features retain their own
preview labels. The Foundry UI's documented 90-day trace browsing window is not a universal
storage-retention guarantee; connected workspace configuration governs retention and cost.

Sources: [tracing setup](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup),
[tracing overview](https://learn.microsoft.com/en-us/azure/foundry/observability/concepts/trace-agent-concept),
[data handling](https://learn.microsoft.com/en-us/azure/foundry/observability/concepts/trace-data),
[retention](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure).

### Framework Integration

Foundry documents integrations for Microsoft Agent Framework, LangChain/LangGraph, and
OpenAI Agents SDK. Use the framework-specific path and preserve parent/child context across
agent, model, and tool calls. Avoid double instrumentation when a framework and SDK both
emit the same operations.

Python client guidance includes `azure-ai-projects`, OpenTelemetry, and
`azure-core-tracing-opentelemetry`; Azure Monitor export adds its documented exporter/distro.
.NET and JavaScript/TypeScript have different switches and client options. Do not combine
snippets from different languages, SDK generations, or instrumentation libraries.

Sources: [framework tracing](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-framework),
[client-side tracing](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-client-side),
[Azure Monitor OpenTelemetry setup](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable).

### Content Capture Has More Than One Switch

The client guide documents `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`, default
false, for SDK message-content capture. **Python `@trace_function` always records its
parameters and return values and is not governed by that switch.** Custom attributes and
application logs are additional content paths.

Recommendation: review every emission path, minimize/redact content before export, and test
that representative sensitive values remain absent under the intended configuration.
Disabling one SDK flag is not a blanket no-content-logging policy.

Source: [custom functions and content recording](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-client-side#trace-custom-functions).

## OpenTelemetry Contract

Trace IDs correlate a workflow; spans represent operations with parent/child relationships.
Relevant documented operations include `invoke_agent`, `invoke_workflow`, `execute_tool`,
`plan`, and memory operations such as `search_memory`. Relevant content fields include tool
definitions, arguments, and results. Retain model/deployment, agent version, response or
conversation identity, and evaluation-run correlation where the emitting API supplies them.

Foundry explicitly describes GenAI semantic conventions as Development status. The old
OpenTelemetry GenAI documentation landing page now identifies itself as moved. Follow the
dedicated upstream GenAI conventions repository and pin conventions with the instrumentation
version; do not treat a copied attribute list as permanently stable.

Sources: [Foundry conventions](https://learn.microsoft.com/en-us/azure/foundry/observability/concepts/trace-agent-concept#extend-opentelemetry-with-multi-agent-observability),
[OpenTelemetry landing page](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
[current GenAI conventions repository](https://github.com/open-telemetry/semantic-conventions-genai).
[W3C Trace Context](https://www.w3.org/TR/trace-context/) is an official linked dependency;
its body was not acquired because the publisher's robots policy refused this fetcher.

## Published Model Metrics

The model guide recommends the **Models** metric category for cross-model coverage; the
older **Azure OpenAI** category applies to Azure OpenAI models. The resource namespace is
`Microsoft.CognitiveServices/accounts`, not an invented agent metric namespace.

| Metric Identifier | Unit / Aggregation | Important Interpretation |
| --- | --- | --- |
| `ModelRequests` | Count / sum | Model API calls; split by status/model/deployment dimensions that exist for this metric |
| `ModelAvailabilityRate` | Percent / min, max, average | `(total calls - server errors) / total calls`; server errors are HTTP >=500, not all application failures |
| `TimeToResponse` | Milliseconds / min, max, average | Gateway-side responsiveness; excludes client network latency; deployment/streaming applicability matters |
| `NormalizedTimeBetweenTokens` | Milliseconds / min, max, average | Streaming generation timing, not complete conversation duration |
| `InputTokens`, `OutputTokens`, `TotalTokens` | Count / sum | Token throughput; not a bill or an independent task-success measure |
| `TokensCacheMatchRate` | Percent / average | Prompt-cache matching for supported provisioned deployment types |
| `ProvisionedUtilization` | Percent / average | Provisioned consumption relative to capacity; applicable throttling can accompany saturation |
| `ProvisionedConsumedTokens` | Count / sum | Provisioned total less cached tokens under the documented deployment rules |
| `AudioInputTokens`, `AudioOutputTokens` | Count / sum | Audio usage on supported deployment types |

Read the generated reference for each metric's exact dimensions, time grain, aggregation,
and diagnostic-settings export flag. The acquired account metric catalogue contains no
agent-named metrics; agent dashboard labels alone do not establish a REST metric identifier
such as `AgentRequests`.

**Documentation discrepancy:** the model-monitoring how-to broadly says all metrics export
through diagnostic settings, but the generated account reference marks
`ModelAvailabilityRate` **DS Export: No**. It marks `ModelRequests`, `InputTokens`, and
`TimeToResponse` exportable. Use the per-metric reference, then verify the actual target
before relying on export. An empty `AzureMetrics` query is not proof of zero activity.

Sources: [model metric definitions](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/monitor-models#metrics-reference),
[generated account metric reference](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-cognitiveservices-accounts-metrics),
[Azure OpenAI monitoring reference](https://learn.microsoft.com/en-us/azure/foundry/openai/monitor-openai-reference).

## Agent Dashboards, Alerts, And Fleet Views

- Foundry's Monitor tab covers token usage, run latency, run success, evaluation scores,
  and configured red-team results. The article's example investigation thresholds are
  guidance, not your application's SLOs or a Microsoft service SLA.
- Application Insights Agents (Preview) provides agent/model/tool drill-down, failed-run
  searches, token-oriented sorting, and end-to-end transaction views.
- Grafana integration provides starting dashboards for Agent Framework, workflows, and
  Foundry. Customize queries and dimensions to the actual telemetry contract.
- Foundry Control Plane aggregates accessible agents and connected telemetry across
  resources. Different readers can see different fleets because access is filtered.
- Agents without connected Application Insights lack the documented health/cost/drill-down
  evidence; presence in inventory is not equivalent to monitoring coverage.
- Alerts need explicit scope, signal, evaluation window, threshold, and action routing.
  Monitor missing telemetry as a separate failure mode from bad measured values.

Sources: [Foundry dashboard](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard),
[Application Insights Agents](https://learn.microsoft.com/en-us/azure/azure-monitor/app/agents-view),
[Grafana dashboards](https://learn.microsoft.com/en-us/azure/azure-monitor/app/grafana-dashboards),
[fleet monitoring](https://learn.microsoft.com/en-us/azure/foundry/control-plane/monitoring-across-fleet),
[Azure Monitor alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview).

## Continuous Evaluation Is A Separate Workload

Scheduled evaluations run on a recurrence. Continuous evaluations sample live response
completions. The Python example uses an evaluation definition plus
`evaluation_rules.create_or_update()`, `EvaluationRuleEventType.RESPONSE_COMPLETED`, an
agent-name filter, and `ContinuousEvaluationRuleAction` with `max_hourly_runs`.

The guide separately uses `beta.schedules` for scheduled runs and documents different
language support. It says JavaScript/TypeScript supports continuous rules, while its
scheduled workflow uses the portal. Do not assume sample `max_hourly_runs=100` is a service
quota or a configured value in this repository.

Rules require project-managed-identity permissions. After an authorized setup, verify
generated traffic, actual evaluation runs, terminal outcomes, and item results; existence
of a rule or a chart is insufficient. Model-judge calls and evaluation storage add costs.

Source: [recurring and continuous evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard#set-up-continuous-evaluation).

## Feedback, Replay, And Datasets

Human feedback is emitted as `gen_ai.evaluation.result`. Binary feedback uses 0/1; a
five-point rating uses 1-5. Preserve evaluator name, score, label, source (`builder` or
`end_user`), trace/span correlation, and the declared scoring semantics. Human feedback is
not the same signal as an LLM Customer Satisfaction evaluator.

Trace Replay displays recorded user interactions and span trajectories. Its Playthrough
control highlights captured spans; it is not a fresh agent execution or a counterfactual
test of modified instructions. Annotations and trace-to-dataset generation support an
inspection-to-evaluation loop, subject to capture quality and privacy review.

Sources: [end-user feedback](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/log-end-user-feedback),
[trace annotations](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-annotations),
[trace replay](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-replay),
[traces to datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/traces-to-dataset).

## Agent Insights: Version-Sensitive Preview

Current Microsoft SDK source includes on-demand trace analysis and scheduled Agent Insights
monitors through `project_client.beta.agent_insight_monitors`. The sample creates a monitor,
starts `begin_create_run()` with a lookback window, reads the resulting run and insights,
and can update an insight's review status.

Outputs include traces in the window versus traces analyzed, created/updated/reopened
insight counts, measured token usage, severity, and proposed fixes. Marking an insight
Resolved changes its review status; it does not apply the proposed fix.

**Availability caveat:** release history lists supporting models in 2.6.0, but the acquired
end-to-end samples require `azure-ai-projects>=2.7.0`, while 2.7.0 is marked **Unreleased**.
Treat this as discoverable upstream preview work, not a verified installable integration.
These monitors are also distinct from `.beta.insights` evaluation-result analysis.

The samples seed fictional telemetry under temporary external agents and use helper
modules. They still call cloud analysis, mutate monitor/agent resources, and retain ingested
telemetry under normal retention. Neither sample was executed. Project identity access
to models and protected trace content is an additional prerequisite.

Sources: [on-demand sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/agent_insights/sample_agent_insights_on_demand.py),
[scheduled sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/agent_insights/sample_agent_insights_scheduled.py),
[release history](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/CHANGELOG.md).

## Logs, Sampling, And Storage

Model resource metrics are collected automatically. Persisting/querying resource logs
requires diagnostic settings. Application Insights agent telemetry is a different pipeline.
Hosted-agent console/runtime logs are another diagnostic surface, not replacements for
structured model/tool spans.

The sampling guide states that metrics are not sampled. Trace sampling supports percentage
and rate-limited strategies; log sampling depends on the language/distro configuration.
Ingestion sampling can produce incomplete traces. Continuous-evaluation sampling is yet
another selection stage; record it separately from telemetry sampling.

Daily caps can stop ingestion and create monitoring gaps. Retention, table plan, export,
sampling, and evaluation frequency all affect cost and evidence availability. Cost estimates
from tokens do not include every external tool or storage charge.

Sources: [model log routing](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/monitor-models#logs),
[hosted-agent logs](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/monitor-hosted-agent-logs),
[sampling](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-sampling),
[retention](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure),
[billing](https://learn.microsoft.com/en-us/azure/azure-monitor/cost-usage).

### Query Schema Cautions

Application Insights examples use tables such as `customEvents` with `customDimensions`;
workspace examples use tables such as `AppEvents` with `Properties`. Verify the query
context instead of mechanically changing case. Exported platform metrics appear in
`AzureMetrics` only when the relevant export is configured and supported.

`AppGenAIContent` exposes `TraceId`, `SpanId`, `ParentSpanId`, `AgentName`, `ModelName`,
`TimeGenerated`, and dedicated content columns including `InputMessages`, `OutputMessages`,
and `ToolCallResult`. The reference marks direct Ingestion API and DCR workspace
transformation support **No**. Do not assume a workspace transformation can redact this
table after capture. A column called `TenantId` here denotes the Log Analytics workspace
ID, not necessarily the end user's Entra tenant.

Sources: [log query overview](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-query-overview),
[feedback query example](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/log-end-user-feedback#view-feedback-in-application-insights),
[AppGenAIContent schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/appgenaicontent).

## Identity And Verification

Entra-authenticated ingestion, preview, uses the project managed identity for server-side
traces. Hosted-agent code can emit with the Agent Identity, which needs its own
Monitoring Metrics Publisher assignment on the connected Application Insights resource.
The portal's project-managed-identity connection flow can assign that role to the project
identity; this does not automatically prove the hosted Agent Identity has it too.

Ingestion permission, ordinary log reading, protected-content reading, project access,
and Cost Management access are different permissions. Enforcing identity-only ingestion
also requires disabling local authentication on Application Insights through an authorized
configuration change. None of these settings or roles was changed for this research.

Source: [Entra trace ingestion](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-ingestion-entra-authentication).

Recommended verification for a later authorized integration:

1. Send one known successful and one deliberately failing nonproduction request.
2. Locate their exact trace/response IDs and confirm expected model/tool child spans.
3. Read back status, latency, available tokens, and deployment/agent identity.
4. Confirm a continuous rule produces the intended bounded evaluation and complete results.
5. Test ordinary-reader denial and authorized-reader access to protected content.
6. Verify capture minimization across SDK spans, decorators, attributes, and application logs.
7. Test missing-telemetry and failure alerts, including action delivery.
8. Recheck custom queries across the September 2026 content-routing migration.

No live monitoring, ingestion, alert delivery, RBAC refusal, or billing behavior was verified
in this documentation-only collection.