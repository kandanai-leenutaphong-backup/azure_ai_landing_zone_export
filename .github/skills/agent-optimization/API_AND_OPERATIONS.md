# Foundry API, SDK, And Operating Constraints

> Research only: upstream capabilities and historical evidence, not implemented library support.

Research assembled 2026-09-15. Source acquisition timestamps are preserved in UTC; they
must not be confused with a page's publication date or a package release date. No package
was installed and no Azure API was called for this collection.

## API Map

| Capability | Documented Surface | Important Boundary |
| --- | --- | --- |
| Project resources | `azure.ai.projects.AIProjectClient` | Entra-authenticated Foundry project endpoint |
| Evaluation definition/run/results | `project_client.get_openai_client().evals` | OpenAI-compatible Evals with Azure-specific evaluator/data-source variants |
| Registered datasets | `project_client.datasets` | Versioned references differ from inline data and local files |
| Generated datasets/rubrics | `beta.datasets`, `beta.evaluators` | Preview job contracts and poller behavior vary by SDK version |
| Continuous evaluation | `evaluation_rules` | Response-completed rules are not fixed-time schedules |
| Scheduled evaluation | `beta.schedules` in the cited Python workflow | Verify language/version support and the task's exact data source |
| Evaluation-result analysis | `beta.insights` | Comparison/clustering is distinct from agent-monitor insights |
| Native agent optimization | `beta.agents.begin_create_optimization_job` | Long-running preview job; selected result still needs review/application |
| Red teaming | `beta.red_teams` | Preview, scoped target/tool/region support and safety prerequisites |
| Agent Insights monitors | `beta.agent_insight_monitors` in current samples | Samples require unreleased 2.7.0; not a verified installable feature here |

The SDK README names `v1` as its data-plane API family. Current cloud target-evaluation
examples show run creation under:

```text
https://<account>.services.ai.azure.com/api/projects/<project>/openai/v1/evals/<eval-id>/runs
```

This is a project endpoint, not a hub connection string or a generic model endpoint.
Use the corresponding SDK/reference for full request, paging, status, and preview contracts;
do not construct undocumented optimizer or monitor REST routes from their Python names.

Sources: [SDK README](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/README.md),
[client reference](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.aiprojectclient),
[cloud setup](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation),
[target-evaluation REST examples](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-targets),
[official REST reference short-link](https://aka.ms/azsdk/azure-ai-projects-v2/api-reference-v1).
The short-link is retained but not fetched because its host's robots policy refused access.

## Version Evidence

These are observations from the acquired documentation/source, not a tested dependency set.

| Evidence | What It Says | Consequence |
| --- | --- | --- |
| Cloud evaluation introduction | Install `azure-ai-projects>=2.2.0` | Tutorial minimum, not a frozen environment |
| Main SDK README | Check 2.3.0 or later; still says Python 3.9+ | README prerequisites lag later release notes |
| Release 2.4.0, July 24, 2026 | Optimizer and generation methods become `begin_create_*` long-running operations | Older creation/polling snippets need review |
| Release 2.5.0, August 20, 2026 | Python minimum becomes 3.10; `openai>=3.0.0`/`httpx2`; optimizer models renamed | Do not assume older interpreter, transport, or beta model compatibility |
| Release 2.6.0, September 4, 2026 | Supporting Agent Insights models and other features added | Latest dated release in the acquired changelog, not a registry/install verification |
| 2.7.0 heading | Unreleased; new Agent Insights samples | Source presence is not release availability |

Stable distribution does not imply every operation is GA. The README says preview features
on stable methods use `allow_preview=True`; preview `.beta` subclients have their own
exposure and can change. The current native optimizer sample advertises `>=2.4.0` while
using types renamed in 2.5. Pin an actual compatible version and verify it before adoption.

Sources: [release history](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/CHANGELOG.md),
[SDK README](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/README.md),
[optimization example](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/agents/optimization/sample_optimization_job_basic.py),
[Agent Insights example](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/agent_insights/sample_agent_insights_on_demand.py).

## Current Versus Classic

| Current Foundry | Classic/Compatibility Material |
| --- | --- |
| New cloud guide uses Projects 2.x plus the OpenAI Evals client | Local guide uses `azure-ai-evaluation`, `azure.ai.evaluation`, evaluator objects, and `evaluate()` |
| Current dataset schema favors `messages` or separate query/response | Classic guides include a `conversation` wrapper and their own agent-message mappings |
| Agent versions, Responses, and current project endpoints | Older project, agent, or Azure OpenAI evaluation examples have different entry points |
| Explicit turn/conversation evaluation levels | Do not assume every older conversation evaluator matches the current whole-conversation semantics |

Classic does not mean that the Python evaluation library has ceased to exist. It means the
cited portal/workflow documentation is explicitly scoped to classic. Do not mix its
schemas, imports, environment names, or result formats into a current cloud run without
checking the owning API.

"Local evaluation" describes orchestration location. Deterministic metrics can run locally,
but judge-based and hosted-safety evaluators can still call models/services and incur charges.
It is not an assurance of offline operation or data remaining on the workstation.

Sources: [classic local evaluation](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/evaluate-sdk),
[classic agent evaluation](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/agent-evaluate-sdk),
[Evaluation SDK reference](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-evaluation-readme),
[Evaluation SDK source README](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/evaluation/azure-ai-evaluation/README.md),
[classic Azure OpenAI Evals](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/evaluations).

## Language And Example Coverage

Current cloud evaluation guides contain Python, .NET, JavaScript/TypeScript, and selected
cURL examples. Their capabilities and method signatures are not identical. The result
guide demonstrates automatic full iteration in Python/JavaScript and explicit protocol
paging in .NET. The monitoring guide distinguishes supported continuous rules from
scheduled workflows in JavaScript/TypeScript.

The official sample index covers inline/registered/CSV datasets, agent/model targets,
captured responses, traces, synthetic data, multi-turn simulation, custom/rubric evaluators,
human feedback, multimodal model graders, and comparison/cluster insights. Multimodal
grader examples do not establish image/audio support for every built-in evaluator or
red-teaming scenario.

Sources: [SDK overview](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview),
[sample index](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/evaluations/README.md),
[result retrieval](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-results),
[recurring evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard).

### Reproduced Documentation Defect

The acquired dashboard guide's second Python code block contains a `//` comment for
scheduled evaluation. Parsing that block with Python `ast.parse` raises `SyntaxError` at
block line 19. The separately acquired maintained continuous-evaluation sample passes
syntax parsing. Neither was imported or executed; syntax acceptance is not API compatibility
or a successful cloud run.

Use official code examples as version-bound starting points and inspect their setup,
helper modules, resource creation, model calls, and cleanup. Do not execute a documentation
sample merely to verify a link or copy its broad grants into a production integration.

Sources: [affected dashboard guide](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard#create-a-recurring-evaluation),
[maintained continuous-rule sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_continuous_evaluation_rule.py).

## Identity And Data Boundaries

| Actor Or Resource | Required Distinction |
| --- | --- |
| Human/automation creating evaluations | Project access and a valid Entra credential; default credential selection is not proof of the intended principal |
| Project managed identity | Separate service-side model/evaluation/trace access, including continuous-evaluation permissions |
| Hosted Agent Identity | Can emit code-level telemetry independently of project-identity server traces |
| Application Insights/Log Analytics reader | Read permission is separate from project membership and ingestion permission |
| Protected trace-content reader | Additional protected-table privilege, including review of equivalent custom DataActions |
| Storage identity | BYO storage access is independent of model and telemetry roles |
| Application end user | Application-owned authorization and record ownership are not supplied by an evaluation score |

The current docs rename Azure AI User/Owner/Account Owner/Project Manager to Foundry
User/Owner/Account Owner/Project Manager. They explicitly say role IDs and core permissions
are unchanged by that rename. Both names can still appear in examples and portals.

Some official BYO-storage examples use key authentication. Official origin does not override
this repository's managed-identity/secret-handling policy. Choose the supported identity
path, exact scopes, and required read-back under a separately authorized deployment plan.

Sources: [Foundry RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry),
[evaluation prerequisites and storage](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network),
[Entra trace ingestion](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-ingestion-entra-authentication),
[trace data handling](https://learn.microsoft.com/en-us/azure/foundry/observability/concepts/trace-data).

## Quotas, Regions, Networking, And Costs

The centralized evaluation guide states a **2 MB maximum row** and **100,000 rows per batch
evaluation**. Creation throttles exist at tenant, subscription, and project scopes; the
guide describes `retry-after` and backoff, not one universal creation-RPM value. Judge-model
capacity and tool/service quotas remain additional bottlenecks.

Regional tables differ by playground, batch evaluation, safety evaluator, data generation,
virtual network, red teaming, and optimizer. Groundedness Pro is listed in East US 2 and
Sweden Central; Protected Material in East US 2. Do not use generic Foundry availability
as evidence for a particular evaluator.

The red-teaming overview and central region matrix disagree, as recorded in
[EVALUATIONS.md](EVALUATIONS.md). Agent Optimizer and Prompt Optimizer also have different
availability rules, recorded in [OPTIMIZATION.md](OPTIMIZATION.md). Treat unresolved
availability as a preflight question, not a permission to create a different region's
resources without approval.

Evaluation network isolation uses network injection/subnet delegation. The guide links
an evaluation-only infrastructure template for scenarios that do not require all agent
services. BYO storage can be configured with or without a virtual network. Connected
Application Insights is an additional destination for evaluation data, so a private
evaluation network alone is not a complete data-flow description.

Cost planning must include target-model calls, judge/reflection calls, external tools,
training where applicable, and telemetry/storage. Optimizer cost estimates, RFT cost-pause
behavior, and Azure Monitor ingestion caps are different mechanisms with different gaps.
No price or tenant-specific cost estimate was calculated here.

Sources: [limits, regions, networks, storage](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network),
[Foundry cost planning](https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs),
[optimizer cost semantics](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-costs),
[monitor cost semantics](https://learn.microsoft.com/en-us/azure/azure-monitor/cost-usage).

## Remaining Verification

- Exact released dependency set and SDK/API compatibility in a clean environment.
- Actual tenant/region/model access and all required positive/negative permission checks.
- Real evaluation, optimization, red-team, or insight outcomes and complete persisted results.
- Telemetry ingestion, protected-content denial, sampling, retention, and alert delivery.
- Actual billing, latency, quota behavior, and model-judge accuracy on representative data.
- Preview access and eventual release support for Agent Insights 2.7 examples.

These require implementation or live access beyond this documentation-only request.
The collection makes no library registration, migration, cloud grant, or deployment change.