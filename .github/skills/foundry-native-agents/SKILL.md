---
name: foundry-native-agents
description: "Use when selecting native Microsoft Foundry agent and evaluation capabilities. Includes explicitly unavailable imported historical testbed guidance, not verified SDK pins or local deployment receipts. Follow the project's private endpoint, hosting and authorization boundaries; discovery grants no inference, RBAC or teardown authority."
---

# Foundry native agents in this project

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). App compute belongs in SEA internal
`capps-env-sea`; use the supplied private West US 3 Foundry project. A Hosted Agent template
is not the app hosting requirement, and no model, agent version or SDK pin is established
by this imported skill. Inspect actual app dependencies and service metadata before selection.

Use native features when they meet a concrete requirement; justify only uncovered custom glue.
Use the central four-judge contract: `factual_accuracy`, `task_completion`, `tone`, `consistency`.
Keep each rubric/context focused and independent, with strict JSON; task scoring ignores politeness.
Optional three prompt variants use the same model, retain mean/spread and require human review
when spread > 3. Optional `azure-ai-evaluation` custom-callable JSONL batches are not evidence
of calibration. Require 50-100 genuine human-labeled examples and kappa > 0.7 before a
calibrated quality gate; otherwise retain `uncalibrated`. Preserve trace
and span correlation and system -> journey-type -> per-agent accuracy/latency/errors/tokens.
Report unsupported evaluator dimensions or missing telemetry, never invented service fields.
Agent count must follow real configuration, not historical examples.

Use [release guidance](../azure-app-deployment/SKILL.md) and
[Container Apps guidance](../deploy-container-apps/SKILL.md) with the parent's actual
`deploy/deploy.sh`. No secret retrieval, dataset credentials, RBAC grants, registration
changes, optimizer campaign or teardown is authorized by loading this entry.

## Imported historical reference, unavailable here

The text below is preserved from another workspace. All receipt paths, testbeds, templates,
`libraries/`, lifecycle protocol, pins, dates, measurements and support claims inside the
quoted block are **unavailable imported history**, not instructions to run here or verified
compatibility. Original relative paths retain their source-workspace meaning and are
deliberately quoted rather than presented as resolving checkout links.
Reverify any selected API against the installed SDK and authorized target.

```markdown
# Foundry Native Agents

Build agentic apps on native Microsoft Foundry capability first. Every claim below links a
testbed receipt, record or operator document; `unverified` marks the rest. Guidance only:
loading this skill authorizes no cloud call.

Proving testbeds, accepted together in
[F09](../../../agentcraft_projects/foundry-official-integration-20260922/records/v2/20260922T200128628556Z-f09-migration-accepted/record.json)
on 2026-09-22:

- H — [hosted agents](../../../testbeds/foundry-hosted-agents/deploy/README.md): versions, tools, invoke, 401, cancel.
- E — [evaluation](../../../testbeds/foundry-agent-evaluation/deploy/README.md): dataset, Evals, judge, result shape.
- O — [optimization](../../../testbeds/foundry-agent%20optimization/deploy/README.md): custom evaluator, native optimizer, candidate hosting.
- T — [teardown report](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T101500000000Z-teardown-report.json)
  and its [record](../../../agentcraft_projects/foundry-official-integration-20260922/records/v2/20260923T101229757113Z-teardown-experiment-resources-executed-v1/record.json), 2026-09-23.
- P — [agent package E2E](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/):
  package → build → version → journeys → verify → evaluator → eval → optimization job, live 2026-09-24
  through the template; redeploy series in progress.

Repeatable procedure: [protocol-foundry-agent-lifecycle](../../protocols/protocol-foundry-agent-lifecycle/SKILL.md)
over the [template](../../../template_apps/foundry_hosted_agent/README.md) entry point
[deploy.sh](../../../template_apps/foundry_hosted_agent/deploy/README.md).

## Capability Map

| Need | Native Foundry feature | Package pin | Proven by |
| --- | --- | --- | --- |
| Run agent code as a managed, versioned service | Hosted Agent: `HostedAgentDefinition` + `project.agents.create_version` (ACR image) | `azure-ai-projects==2.6.1` | [H final deploy](../../../testbeds/foundry-hosted-agents/deploy/records/migration-h-v1/20260922T183120213195Z-deploy.json) |
| Serve Responses protocol in the container | `ResponsesAgentServerHost`, deferred `TextResponse(text=async_callable)`, port 8088 | `azure-ai-agentserver-responses==2.1.0`, `azure-ai-agentserver-core==2.1.0` | [H new-tool verify](../../../testbeds/foundry-hosted-agents/deploy/records/migration-h-v1/20260922T184312034351Z-verify.json) |
| Model and tool loop | Microsoft Agent Framework through `llm_interface.connect` | `agent-framework-core==1.18.0`, `agent-framework-foundry==1.13.0`, `agent-framework-openai==1.14.3` | [H install receipt](../../../testbeds/foundry-hosted-agents/deploy/records/20260922T054628468461Z-install.json) |
| Invoke, stored readback, cancel | `project.get_openai_client(...)`: `responses.create/retrieve/cancel` | `openai==3.13.0` | [H cancellation](../../../testbeds/foundry-hosted-agents/deploy/records/migration-h-v1/20260922T185121107291Z-invoke.json) |
| Inspect versions, sessions, logs | `agents.get/get_version/list_sessions/get_session/get_session_log_stream` | `azure-ai-projects==2.6.1` | [H final inventory](../../../testbeds/foundry-hosted-agents/deploy/records/20260922T060747173873Z-inspect.json) |
| Evaluation dataset with byte readback | `datasets.pending_upload` → Blob upload → `datasets.create_or_update` → `get_credentials` | `azure-ai-projects==2.6.1`, `azure-storage-blob==12.26.0` | [E final verify](../../../testbeds/foundry-agent-evaluation/deploy/records/migration-e-final-h-v3/20260922T194842941922Z-verify.json) |
| Judge-scored evaluation run | `evals.create`, `evals.runs.create/retrieve`, `runs.output_items.list`; `builtin.coherence` v12 | `openai==3.13.0` | [E final verify](../../../testbeds/foundry-agent-evaluation/deploy/records/migration-e-final-h-v3/20260922T194842941922Z-verify.json) |
| Judge model identity | `deployments.list/get` typed `model_name`/`model_version` | `azure-ai-projects==2.6.1` | [E selection](../../../testbeds/foundry-agent-evaluation/deploy/records/selection.json) |
| Task-specific scoring | Custom code evaluator: `project.beta.evaluators.create_version`, `grade(sample, item)` | `azure-ai-projects==2.6.1` | [O mapped canary readback](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v1/20260922T181008444895Z-mapped-canary-readback.json) |
| Instruction optimization | `project.beta.agents.begin_create_optimization_job` / `get_optimization_job` | `azure-ai-projects==2.6.1` | [O v3 independent metrics](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v3/candidate-validation-metrics.json) |
| Apply candidate config in hosted runtime | `azure.ai.agentserver.optimization.load_config` | `azure-ai-agentserver-optimization==1.0.0b1` | [O v3 native metrics](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v3/migration-o-v3-recomputed-metrics.json) |
| Identity | Caller `AzureCliCredential`; container `DefaultAzureCredential` on platform identity; Foundry gateway enforces Entra | `azure-identity==1.26.0b2`, `azure-core==1.39.0` | [H baseline verify](../../../testbeds/foundry-hosted-agents/deploy/records/20260922T060202403083Z-verify.json) |
| Image build | Server-side `az acr build --no-wait`, run ID observed | Azure CLI, version `unknown` here | [H build overlap](../../../testbeds/foundry-hosted-agents/deploy/records/migration-h-overlap-v1/20260922T194519593953Z-build-overlap.json) |

Pins come from the hash-locked profiles:
[H host lock](../../../testbeds/foundry-hosted-agents/deploy/host-requirements.lock),
[H runtime lock](../../../testbeds/foundry-hosted-agents/deploy/runtime-requirements.lock),
[O host lock](../../../testbeds/foundry-agent%20optimization/deploy/host-requirements.lock)
(adds the loader), [O dependency manifest](../../../testbeds/foundry-agent%20optimization/deploy/dependency-manifest.json).
`httpx==0.28.1`; uv 0.9.30. Other versions are untested here, not forbidden.

## Decision Rule: Native First

Use the native feature when it covers the requirement. Write custom code only for a named,
concrete requirement the native surface does not meet, keep it minimal, and record why.

| Situation | Choice | Reason |
| --- | --- | --- |
| Score an optimizer's candidates | Register a custom code evaluator natively | Native optimizer consumes only registered evaluators |
| Report accuracy/macro-F1 of candidates | Independent hosted validation, local frozen scorer | Native composite `avg_score` is not that metric (O) |
| Frozen cohorts, immutable generations, lineage | Local [agent-optimization](../agent-optimization/SKILL.md) library | Native candidate IDs carry no generation/parent lineage (O) |
| Dataset upload with per-stage recovery | Native `pending_upload`/Blob/`create_or_update` stages, not `upload_file` | Provenance capture and recovery per stage (E) |
| Config acquisition | Public `load_config` at runtime; one bounded GET retained | Loader 1.0.0b1 strips whitespace, allows fallback, has no timeout (O) |
| Model loop | MAF via `llm_interface`; no second runner | One owner of the tool loop (H) |
| Hosting fallback | None; no ACA fallback for a Hosted Agent | Out of scope in H; use [deploy-container-apps](../deploy-container-apps/SKILL.md) only for a separate web app |

Counter-example: raw candidate-list REST was removed in O once
`get_optimization_job().result.candidates` matched it; custom authenticated HTTP sites went 6 → 1
([acceptance gaps](../../../deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/README.md)).

## Lifecycle

`write` = cloud mutation or billable inference; each needs explicit, scoped authorization
recorded before the action. Never replay a settled write; reconcile unknown outcomes read-only.

| # | Stage | Native operations | Cloud write |
| --- | --- | --- | --- |
| 1 | Preflight | Offline tests; read account, project, model, registry, role, evaluator | no |
| 2 | Build | Allowlisted archive → `az acr build`; image smoke of real SDK readiness | **write** (billable) |
| 2a | Registry pull | Exact registry-scoped `AcrPull` for project identity, only when absent | **write** (RBAC) |
| 3 | Deploy version | `agents.create_version`; wait ≤300 s for active exact image/metadata | **write** |
| 4 | Verify | `get_version` readback; one authenticated invoke; stored-response readback; anonymous 401 | **write** (invoke = inference, stored response, session) |
| 5 | Evaluate | Dataset reserve/upload/register; `evals.create`; `runs.create`; reconcile reads | **write** + judge inference |
| 6 | Optimize | Evaluator register + 1/0/0 canaries; optimizer model deployment if absent; one job | **write** (billable) |
| 7 | Promote / restore | New version loading the returned config; baseline version retained as restore target | **write** |
| 8 | Teardown | Frozen inventory manifest, then delete in order below, then readback | **write** (destructive, separate authority) |

Promotion needs its own authority and labels: a regressing candidate may be hosted only as a
labelled demonstration, never as best configuration
([O demonstration result](../../../testbeds/foundry-agent%20optimization/deploy/evidence/demonstration-result.json)).
Teardown order: stored responses → hosted sessions → agent versions (T finding; T itself ran
sessions first and had to repeat them). Remaining order as executed in T: optimization jobs,
eval runs, evals, agent versions, agent, evaluator versions, dataset versions, model deployment,
ACR manifests ([T ledger](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T092540658731Z-ledger.jsonl)).
`unverified`: whether any other order among those later kinds fails.

## Traps

| # | Trap | Rule | Evidence |
| --- | --- | --- | --- |
| 1 | Responses retrieve/delete through `get_openai_client(agent_name=...)` re-creates deleted hosted sessions with the same IDs | Delete responses before sessions, sessions before versions | [T `findings`](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T101500000000Z-teardown-report.json) |
| 2 | `openai` 3.13 maps that endpoint's 404 to `APIConnectionError` | Read back deletion with raw `httpx` GET `{base_url}responses/{id}` → 404 | [T `deleted_notes`](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T101500000000Z-teardown-report.json), [manifest code](../../../deploy/remediation-evidence/20260923-cleanup/teardown_manifest.py) |
| 3 | `evals.runs.delete` is eventually consistent; `evals.delete` returns `deleted=false` (async) | Repeat bounded readback passes; 404 is the proof | [T `deleted_notes`](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T101500000000Z-teardown-report.json) |
| 4 | Agent delete (`force=False`) 409 while sessions exist; deleting the last version removes the agent | Delete versions; read agent 404 | [T `deleted_notes`](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T101500000000Z-teardown-report.json) |
| 5 | Session list returns deleted and re-created records with the same ID | Judge by state, not ID presence | [T `findings`](../../../deploy/remediation-evidence/20260923-cleanup/teardown/20260923T101500000000Z-teardown-report.json) |
| 6 | Dataset registration rejects versions >50 chars; `pending_upload` accepted 71 | Short version (`sha256-<32 hex>`); full hash stays the content pin | [E version evidence](../../../testbeds/foundry-agent-evaluation/deploy/records/version-recovery-evidence.json) |
| 7 | Eval `sample.output[].content` holds a JSON-encoded list of `output_text` blocks | Decode, extract text, cross-check `datasource_item["sample.output_text"]`; judge `results[].sample` is not target output | [E README "Result shape"](../../../testbeds/foundry-agent-evaluation/deploy/README.md), [E verify](../../../testbeds/foundry-agent-evaluation/deploy/records/20260922T075653771799Z-verify.json) |
| 8 | Hosted inference failed `CERTIFICATE_VERIFY_FAILED` (version 1) | Pass `ssl.create_default_context()` through public `connect(..., transport=...)`; keep `CERT_REQUIRED` + hostname check; no bypass | [H logs](../../../testbeds/foundry-hosted-agents/deploy/records/20260922T055753697020Z-logs.json), [spec](../../../specs/20260922_FOUNDRY_HOSTED_AGENTS_EXPERIMENT.md) |
| 9 | Native optimizer candidate IDs (`_0001`, list order, `max_candidates`) are not generations or lineage | Store service IDs and observation order; generation/parent stay null | [O README "Generation Semantics"](../../../testbeds/foundry-agent%20optimization/deploy/README.md), [spec](../../../specs/20260922_FOUNDRY_AGENT_OPTIMIZATION.md) |
| 10 | Native composite `avg_score` is not an independent metric (not macro-F1) | Measure candidates with an independent scorer under separate names | [O native](../../../testbeds/foundry-agent%20optimization/deploy/evidence/native-mapping-v2-recomputed-metrics.json) vs [independent](../../../testbeds/foundry-agent%20optimization/deploy/evidence/candidate-validation-metrics.json) |
| 11 | Access control proven only by success is unproven | Anonymous invoke must return 401/403; 404, login page or 200 fail | [H verify `anonymous_status: 401`](../../../testbeds/foundry-hosted-agents/deploy/records/20260922T060202403083Z-verify.json) |
| 12 | Native optimizer supplies output in `item["sample.output_text"]`, not `item["response"]`; first job scored 0 | Canary positive/wrong/invalid = 1/0/0 on the native field before any job | [O mapped canary](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v1/20260922T180900595917Z-mapped-canary.json), [O README](../../../testbeds/foundry-agent%20optimization/deploy/README.md) |
| 13 | SDK advertises `evaluation_level="turn"`; service returns HTTP 400 | Omit it | [O README](../../../testbeds/foundry-agent%20optimization/deploy/README.md) |
| 14 | Optimizer `Operation-Location` returns an internal path that 404s publicly | Poll with `get_optimization_job(job_id)`; never resubmit | [O README](../../../testbeds/foundry-agent%20optimization/deploy/README.md) |
| 15 | `max_candidates` caps generated candidates (baseline excluded) and promises none; baseline-only jobs occur | Accept actual returned count; baseline-only refuses collection | [O README](../../../testbeds/foundry-agent%20optimization/deploy/README.md) |
| 16 | Snake-case `dataset_items` is not wire JSON (`items` is); registration omits metric `threshold` | Build rows with typed SDK constructors; check 1/0/0 independently of pass threshold | [O README](../../../testbeds/foundry-agent%20optimization/deploy/README.md) |
| 17 | Foundry-managed dataset storage lives in a provider subscription; SAS exists only in process memory | Capture non-secret metadata before validation; require account/host/container containment; never retain SAS | [E README "Managed Storage Rule"](../../../testbeds/foundry-agent-evaluation/deploy/README.md) |
| 18 | `az acr build --no-wait` serialized stdout as `null` on this host | Accept exactly one `Queued a build with ID:` diagnostic; ambiguity refuses resubmission | [H README](../../../testbeds/foundry-hosted-agents/deploy/README.md) |
| 19 | `deployments` raw `as_dict()` wire keys differ from typed properties | Use typed `model_name`/`model_version` | [E README "Public APIs"](../../../testbeds/foundry-agent-evaluation/deploy/README.md) |
| 20 | Host SDK disables in-flight crash recovery; synchronous tool side effects are not undone on cancel | Claim completed-response retrieval only; keep tools side-effect-free | [H README](../../../testbeds/foundry-hosted-agents/deploy/README.md) |
| 21 | `builtin.tool_call_accuracy` errors every row ("Tool definitions input is required") for tools inside the hosted container: `sample.tool_definitions` is empty | Use `builtin.tool_call_success` (`response: {{sample.output_items}}`, 12/15 passed); keep accuracy out of gates | [P eval summary](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/eval-src-d51b5dad684649d0f0202d79-pkg-95667431e925f468-v1-df3c66519eb40d8d-summary.json) (15/15 errored) |
| 22 | SDK `model_dump` of a response adds null-only fields (`async_`, `caller`, `namespace`, `phase`) the raw GET omits | Compare stored responses with null-only fields dropped | [P verify blocked](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/20260924T073740278955Z-verify.json), [rerun complete](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/20260924T073954810889Z-verify.json) |
| 23 | Eval `sample.output[]` assistant messages carry `function_call`/`tool_call` blocks beside text | Target-text extraction skips those blocks (encoded offline in `foundry_ops.evaluation.target_text`) | [P eval summary](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/eval-src-d51b5dad684649d0f0202d79-pkg-95667431e925f468-v1-df3c66519eb40d8d-summary.json), [local recompute](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/baseline-validation-local-recompute.json) |
| 24 | Native `function_call` items carry no timing, status or error code | Runtime writes response metadata `tool_call.<n>` (`started_at`, `ended_at`, `duration_ms`, `status`, `error_code`), joined by `call_id` | [P invoke result](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/invoke-src-d51b5dad684649d0f0202d79-pkg-95667431e925f468-v1-n-7ca9bccd536c9c31-result.json), [template contract](../../../template_apps/foundry_hosted_agent/README.md#tool-call-observability) |
| 25 | Project system identity holds no `AcrPull` on a registry it was never granted (read-only probe: absent) | Prerequisite, not a deploy.sh step: `preflight` reports the gap; owner grants registry-scoped `AcrPull` before `deploy` | [P G1 intent](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/prereqs/g1-acrpull-intent.json), [P prereqs](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/prereqs/20260924T065314900608Z-prereqs.json) |

`unverified`: live downstream client closure after cancel (H, C09); provider cleanup logs;
reservation deletion (no public cancel/delete API, T `blocked`); agent identity principal state
after teardown (T `blocked`); cost, reservation lifetime and target token usage (`unknown`).

## Lifecycle Glue Owner

[`libraries/foundry-ops`](../../../libraries/foundry-ops/README.md) (import `foundry_ops`) is the
shared lifecycle glue owner. Reuse it for receipts, pinned manifests, build, deploy, readback,
probes and ordered teardown; do not re-implement those steps per app. Its API is owned there.
Start new apps from [`template_apps/foundry_hosted_agent`](../../../template_apps/foundry_hosted_agent/README.md)
and run them with [protocol-foundry-agent-lifecycle](../../protocols/protocol-foundry-agent-lifecycle/SKILL.md).

## Related Skills

- Model loop and native provider integration:
  [llm-interface connectors](../../../libraries/llm-interface/docs/skills/azure-llm-connectors.md),
  [contract](../../../libraries/llm-interface/CONTRACT.md).
- Hosted bundle composition: [modular-agents](../../../libraries/modular-agents/README.md).
- Custom frozen-cohort optimization: [agent-optimization](../agent-optimization/SKILL.md).
- Release sequencing and deployed acceptance: [azure-app-deployment](../azure-app-deployment/SKILL.md).
- Separate web front ends on ACA: [deploy-container-apps](../deploy-container-apps/SKILL.md).
- Human and workload identity: [azure-access-management](../../../libraries/entra-auth/docs/skills/azure-access-management.md).
- Resource inventory and teardown authority: [azure-cli-infra-management](../azure-cli-infra-management/SKILL.md).
```
