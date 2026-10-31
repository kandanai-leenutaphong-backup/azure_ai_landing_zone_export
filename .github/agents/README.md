# Workspace agent roster

## Project integration

Read [customer-service-multi-agent](../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../ARCHITECTURE.md). Coding-agent roles below are not the app's
runtime agent inventory. No 14-agent count is prescribed. Acceptance includes synthetic
journeys, required structured logs, four specialized judges and navigable system aggregate ->
journey-type -> per-agent accuracy/latency/errors/tokens.

The new app targets internal SEA Container Apps, existing hub WAF and private West US 3
Foundry. Parent owns deployment entrypoint, TLS and gateway activation. DNS and existing
Entra registration reuse are supplied project facts, not this roster's live read-back.

Imported role procedures retain unresolved prerequisites: `.github/tools/` is absent,
including `oracle.py` and the mandatory AgentCraft `oplog.py` clock tool. Do not claim these
commands or receipts exist. An exclusive-tool role remains blocked when its tool is missing.
`docs/notebook/`, root `libraries/` and harness manifests are also absent. General source
discovery uses [repository tools](../instructions/repository-tools.instructions.md).
Missing skill-index/auth-library documentation pointers now resolve to available guidance.
Imported tenant policy/timing observations are labeled unavailable history, not local evidence.
The [central judge contract](../instructions/customer-service-multi-agent.instructions.md#four-specialized-judges)
names `factual_accuracy`, `task_completion`, `tone`, `consistency`, independent focused context,
strict JSON and task scoring that ignores politeness. Optional three same-model prompt variants
report mean/spread; spread > 3 requires human review. Calibration requires 50-100 real
human-labeled examples with kappa > 0.7; until then quality gates remain `uncalibrated`.
Optional `azure-ai-evaluation` custom-callable JSONL batches preserve that contract.
Role behavior, dispatch,
models and tool declarations were not changed by this documentation-only adaptation.

`general-overseer` runs a portfolio of independent outcomes. Each `general-orchestrator` owns one verifiable
increment end-to-end and returns evidence before taking another assignment. Specialists own
bounded work inside that increment and approve nothing.

Every specialist is optional: delegate when it removes real risk or real unknowns, implement
directly otherwise. Contract for all:
[`work-contract.instructions.md`](../instructions/work-contract.instructions.md).

## Available agents

Conciseness is mandatory for all agents, including support agent `note_scribe`.
Each definition carries `Conciseness (Required)`: fewer words, never less required information.
This is a behavioral requirement, not code-enforced language-model compliance.

Every maintained agent must use `uv` for authorized Python dependency/package management, with no
alternative package manager. Configuring, creating, recreating or activating Python environments,
including virtual environments, is forbidden; use existing interpreters/environments only. Missing
`uv` blocks package operations. The
[work contract](../instructions/work-contract.instructions.md#python-dependency-and-package-management)
owns command guidance and precedence over conflicting setup examples; agent permissions remain unchanged.
Overseer and orchestrator specs prefer reusable capabilities and suitable official/open-source libraries;
custom functionality requires a concrete uncovered requirement and minimal integration glue.

| Agent | Role | Employ when | Mutation boundary |
| --- | --- | --- | --- |
| [`general-overseer`](general-overseer.agent.md) | Designs parallel outcome teams, maximizes useful simultaneous execution and owns integration | The objective splits into independently verifiable increments | Dispatches only general-orchestrator; dependency-ready teams with disjoint ownership and required joins |
| [`agentcraft-overseer`](agentcraft-overseer.agent.md) | Owns mission alignment, strategic priorities, authorization/criteria changes, evidence review and direct record publication | Whole-application AgentCraft development | Direct children exactly agentcraft-orchestrator, agentcraft-oracle (advisory only); owns records and lessons |
| [`agentcraft-orchestrator`](agentcraft-orchestrator.agent.md) | Executes assigned AgentCraft stages/iterations and pilots candidates/specialists | Constitution-pinned exploration, implementation and measured iteration | Assigned paths/resources; never dispatches any overseer, no controller recursion or record/lesson publication |
| [`agentcraft-oracle`](agentcraft-oracle.agent.md) | Mock oracle; three bounded cryptic candidates, two randomly selected lines | Optional planning/critique consultation by AgentCraft overseer or orchestrator | One local selector invocation; no research, other file access, network or delegation; advice grants no authority |
| [`note_scribe`](note_scribe.agent.md) | Independent evidence-linked lesson writer | Separately authorized use; no AgentCraft overseer route | Assigned `agentcraft_projects/<project-id>/notebook/lessons.md` only |
| [`general-orchestrator`](general-orchestrator.agent.md) | Owns one verifiable increment end-to-end | One behavior change or bounded uncertainty | Its own assigned paths, contracts, deployments, resources |
| [`architecture-cartographer`](architecture-cartographer.agent.md) | Maps ownership, placement, dependency direction, and final-app readiness | Placement is genuinely contested or topology changed | Read-only except `ARCHITECTURE_STATUS.md` under the docs root |
| [`solution-architect`](solution-architect.agent.md) | Produces a minimum implementation-ready design | The route to value is unclear enough that coding would thrash | Read-only |
| [`data-explorer`](data-explorer.agent.md) | Proves feasibility of unfamiliar authorized sources | Inventory, parsing, rights, or extraction feasibility is unknown | Read-only; never executes source bytes |
| [`developer`](developer.agent.md) | Implements backend, infrastructure, and general code slices | The slice, constraints, and safety signal are known | Assigned writable paths only |
| [`frontend-developer`](frontend-developer.agent.md) | Implements frontend slices with browser evidence | Work belongs to one named frontend surface | Assigned frontend paths only |
| [`documentation_curator`](documentation_curator.agent.md) | Reconciles README, CONTRACT, runbook, and architecture prose with verified source | Documentation reconciliation is worth handing off | Documentation paths only |
| [`experience-evaluator`](experience-evaluator.agent.md) | Measures pre-change impact or a deployed journey | User impact or runtime evidence needs assessment | Read-only browser work |
| [`ui-experience-auditor`](ui-experience-auditor.agent.md) | Cold first-time UI walk returning one record per gap | A runnable surface needs independent usability scrutiny | Read-only browser work |

`general-overseer` and `agentcraft-overseer` are user-invocable; the rest are private to orchestration unless their frontmatter says
otherwise. Modules add agents beyond this table — `hyperframes-motion` adds
`hyperframes-motion-smith`.

## Imported AgentCraft v1.63 Delivery

Portable practices from an imported timed deployment. Its original receipts are unavailable
here; this is not a local deployment record or proven causal speedup:

- Overseer assigns one end-to-end owner per coupled outcome with compact scope, authority, prerequisites,
  evidence pins, acceptance/refusals and return condition; independent outcomes may run in parallel.
- Orchestrator reuses verified facts, checks cheap prerequisites first and completes in-scope repairs.
  Mutable state and source drift require rechecks; extra handoffs and reassurance checks do not.
- User deadlines include the full process, including handoff, archival and notes. Check remaining time,
  reserve closure, report risk and retain failures; never weaken safety or relabel late closure as success.
- Overseer directly preserves selected bytes, linked primary receipts and concise lessons.
  Do not rebuild unrelated history. Evidence, recovery and authorization obligations remain intact.
- Report verified usable results promptly with pending closure explicit. Source versions, applied behavior
  and measured improvement remain separate; no hot-reload or general speedup claim follows from these rules.

## Coordination

AgentCraft overseer v1.64 and orchestrator v1.3 require recorded task starts and periodic
[clock checks](agentcraft-overseer.agent.md#task-clock-and-deadlines-required) through
`oplog.py` (absent here). Explicit user limits in that imported procedure accrue one recorded penalty per started overdue
minute until verified completion. Scheduling and penalties are procedural, not host-enforced.

- Follow [assignment sizing](general-overseer.agent.md#assignment-size-and-cadence) and the [return contract](general-orchestrator.agent.md#return-evidence). Evidence from each return determines the next assignment; no automatic follow-on work.
- General dependency direction is `general-overseer -> general-orchestrator -> specialists`. General orchestrators never spawn
  orchestrators; specialists never report sideways.
- General teams maximize useful concurrency toward end-to-end verified completion, not agent count.
  Shared specialists return to their assigning orchestrator, general or AgentCraft; bare role words
  describe responsibilities, not alternate dispatch names.
- AgentCraft direction is `agentcraft-overseer -> agentcraft-orchestrator -> candidates/specialists`.
  Overseer direct children are exactly `agentcraft-orchestrator`, `agentcraft-oracle`. Direct
  specialists/candidates are prohibited; no direct-test-subject exception.
  The [process skill](../skills/agentcraft-process/SKILL.md) owns the loop, paths and constitution validation.
- Both AgentCraft callers may consult the oracle once per consultation, optionally, never recursively.
  This advisory-only option preserves the process's execution authority.
  Callers interpret, test or reject advice. Imported low-effort requests conflict with the
  oracle file's `Claude Opus 5.5` / `medium` frontmatter. Runtime availability and the intended
  resolution are unknown; do not silently choose a replacement model. Tool restrictions are not a sandbox.
- Only overseer directly publishes authoritative records and maintains lessons. Workers save
  primary evidence; orchestrators hand it to overseer, returning checkpoint requests when receipts are needed.
  No recursive orchestration, isolated evaluation exception, support-role dispatch by
  orchestrators, or waiting for undispatched peers.
  Candidates never own evaluators or authoritative records. Notebook lessons link the archive, not a second ledger.
- One writer per path, contract, deployment target, and cloud resource at a time.
- Subagent calls are synchronous to the parent. Peer chats, worktree sessions, and cloud-agent
  tasks are the asynchronous planes; join them before any claim depends on their result.

| Plane | Use |
| --- | --- |
| Synchronous subagent | Bounded research, review, feasibility, or design this turn needs |
| Same-session peer chat | Independent tracks needing the current dirty tree, with disjoint writable paths |
| Worktree session | Mutating tracks that may overlap or need independent rollback |
| Cloud-agent task | Clean, bounded branch or PR work from committed Git state |

Session-management tools are host-provided; never guess their identifiers into frontmatter.

## Retired Evaluation Workflow

Both orchestrators must never dispatch ANY overseer, including isolated evaluation. No exception or indirect
dispatch through CLI, SDK, clone, alias or nested team. Pass this prohibition to every descendant.
The former isolated evaluation workflow is unsupported; no replacement route is authorized.
Historical records remain factual, not routing authority. Source edits do not reconfigure loaded sessions.
Static source checks do not prove runtime refusal. See the [process contract](../skills/agentcraft-process/SKILL.md#isolated-overseer-evaluation).
