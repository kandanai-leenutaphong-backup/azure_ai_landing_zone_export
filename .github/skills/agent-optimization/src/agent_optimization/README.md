# Agent Optimization

Portable import: `agent_optimization`. The integration sections below describe the host
responsibilities a consuming project implements, not files this package requires. Current
setup and shared dependencies are in [the library entry](../../README.md).

Reusable, host-composed optimization process for a detector feeding an investigator.

Start with [PROCESS.md](PROCESS.md): the general-use question-to-evidence-to-tool method,
separate code/agent change records, repeatable generation sequence, host integration,
verification and explicit limits. This README owns the implementation contracts and bounds.
The [creative-agent-optimization skill](skills/creative-agent-optimization/SKILL.md) is installed
into native CLI workspaces and included in the recorded joint task, not merely linked in docs.

The component owns immutable generation/configuration history, tools, sandbox execution,
development probes, staged measurement, native CLI process contract, result/replay storage,
and optimization UI. Hosts inject authorization, dataset/case selection, scoring task,
model and knowledge adapters, HTTP prefix and storage locations. No component reads host
configuration or imports the application, and no credential enters a candidate workspace.

A generation pins all three levers: detector ruleset configuration, evidence tool set and
logic, and investigator prompt. The detector emits window-bounded patterns and summaries;
the investigator consumes those observations for diagnosis/triage and proposed actions.
Actions are proposals, never executed by this component.

Replicable generation sequence, exactly `PROCESS_CONTRACT["sequence"]`:

1. Read the chosen parent's completed development result and named failures.
2. Record a falsifiable hypothesis and which levers change or remain fixed.
3. Preview the actual proposed detector, tools and prompt on contrasting development cases.
4. Publish the immutable configuration by the probe receipt that evidences it.
5. Measure the full development cohort.
6. Measure the same frozen evaluation cohort.
7. Read the result back and choose the next parent from saved results.

Every failed attempt and regression is retained.

Tool design starts from questions, available data and useful evidence views, not a required
number of classifier revisions. Optional `design_audit.investigation_plan` records each
question's data, view, selected tool, decision and limits plus `code_changes`, `agent_changes`,
`held_fixed` and `acceptance_checks`. The service validates and preserves it under
`question-evidence-tools-v1`; existing proposals and records are unchanged. See
[the plan contract](PROCESS.md#3-record-the-investigation-plan) for exact fields and bounds.

Publication must refuse missing or stale probe evidence. Runs record detector, tool, prompt,
dataset, knowledge, model and scorer identities. No filtering away detector misses and no
fabricated measurements, chat turns, detector improvements or source coverage.

## Public surface

Python, through the installed `agent_optimization` package:

| Export | Purpose |
| --- | --- |
| `OptimizationService(dataset, root, model, predict, *, authorize, profile, identify=…, knowledge_search=None, detector_reference=None, knowledge_reference=None, capability_catalogue=None)` | the ledger: experiments, immutable versions, tools, detectors, staged measurement, replay artefacts and host-supplied capability discovery |
| `OptimizationTerminal(service, *, cli, endpoint, model, workspace_root, token_provider, path, api_origin, tasks, api_path)` | the native CLI process: bounded `./opt` helper, task operations, terminal trace capture |
| `OptimizationProfile`, `TerminalTasks` | the two injection points that carry every domain fact |
| `GradeEvaluator(dataset, predict, profile, *, knowledge_search=None)`, `score(cases, elapsed_ms, grades)`, `audit_results(cases, grades)` | measurement with a host predictor bound to `llm_interface` |
| `measure_run(...)` | full-cohort run persistence, exemplars and development failures |
| `PythonToolRunner`, `HELPER` | sandbox execution and the workspace helper source |
| `detect`, `detector_version`, `verify_detector`, `knowledge_arguments` | detector rules and advisory knowledge arguments |
| `PROCESS_CONTRACT`, `PROCESS_VERSION`, `normalize_rulesets` | the joint generation contract and schema-2 ruleset validation |
| `PROTOCOLS`, `compare_evaluation`, `digest`, `now`, `write_json` | process limits and the persistence primitives |

React, through `@agentcraft/agent-optimization` and its `styles` export:
`OptimizationWorkspace`, `createOptimizationApi(requestJson, base?)`, `OptimizationApiProvider`,
`useOptimizationApi`, `formatMs`, `formatScore`, `MISSING`, and the workspace/snapshot types.
The client is injected through context; no module-level mutable base exists.

`authorize(caller) -> owner` decides who may optimize and names the storage directory.
`identify(caller)` returns the value persisted as a record's owner and re-checked on every
read; it defaults to the caller itself, so a host with a richer identity type passes its own
accessor. The component knows no principal, issuer or tenant.

`OptimizationProfile` carries labels, scorer version, tool runtime, tool families, objective,
baseline proposal, request builder, runtime budgets, baseline detector, workflow contract,
knowledge tool and behaviour classes, and the two evaluation-policy statements.
`TerminalTasks` carries the task text, skill identity, per-protocol objectives and contracts.

`capability_catalogue(caller, experiment)` supplies bounded, non-secret metadata from the
host's actual source/tool registries. `service.capabilities` authorizes the owner, returns
the declaration and its digest, and grants no new operations. `./opt capabilities` and
`./opt describe` expose it; CLI preparation preserves `CAPABILITIES.json` and the same
snapshot in its process receipt. [Discovery procedure](PROCESS.md#discover-existing-capabilities).

## Structural dataset protocol

The service delegates dataset access to its host. It calls `dataset.describe()`, `dataset.cases()`,
`dataset.full_cases()`, `dataset.stress_cases(final=…)`, `dataset.query(case_id, sql)`,
`dataset.profiles()`, `dataset.run_tool(case_id, tool, scope=None)` and reads
`dataset.profile_digest`. Any host object answering that shape works.
Joint hosts also implement `detector_query(case_id, rule, window)` and
`detector_process(case_id, rule, result, window)`; the generated-Python runner's SQLite mount
is separate from this service-level callback contract.

## Protocols

`PROTOCOLS` in `service.py` fixes the shape of a campaign; a host chooses one by name.

| Protocol | Versions (min/max) | Max tools | Case workers | Min tool families | Joint |
| --- | --- | --- | --- | --- | --- |
| `smoke` | 3 / 5 | 3 | 1 | 1 | no |
| `stress-10` | 11 / 11 | 5 | 4 | 6 | no |
| `full-10` | 11 / 11 | 5 | 32 | 6 | no |
| `joint-10` | 11 / 11 | 5 | 16 | 1 | yes |
| `joint-12` | 13 / 13 | 5 | 16 | 1 | yes |
| `joint-smoke` | 3 / 3 | 5 | 1 | 1 | yes |

`joint-10` is the frontend default (`OptimizationWorkspace`, `createOptimizationApi`). Its 16
workers apply without the creative overlay; `full-10` keeps its 32 and is
unchanged. Worker count, model, scoring and cohorts stay fixed for the life of a campaign, so
misses stay in the denominator.

`create(caller, name, "joint-10", creative=True)` (also `joint-12`) opts into `creative-experimentation-v1`:
eight fixed workers, mandatory question plans and approach/alternatives/disconfirmation
records, first successor with at least two tools, and measured exploration completion gates.
The API accepts `creative: true` only with `joint-10` or `joint-12`; other protocols refuse it. The UI
offers the option only when `snapshot.creative_supported` is true. Gate values and rationale
live in [Creative Exploration](PROCESS.md#creative-exploration), with `CREATIVE_CONTRACT` in
`process.py` as the executable authority.

`joint-12` means a measured generation-zero baseline plus twelve CLI-authored successors,
not twelve total versions. Both stages use the host's full frozen cohorts. The
[operational lessons](LESSONS.md) distinguish reproducible improvements from provider,
selection and measurement artifacts. The consuming host owns launch and local-result locations;
no source-project deployment runbook is required by this package.

## Joint generations (schema 2)

A joint experiment carries `process_contract = PROCESS_CONTRACT`
(`version: "joint-query-battery-v1"`), which names the seven-step sequence, the three levers
(`detector_rulesets`, `tools`, `investigator_prompt`), the 2-to-4 probe-case bound, and
`action_policy: "recommendations-only"`. `process.py` holds `JOINT_TASK`, the CLI instruction
text. It is domain-neutral: it names `./opt`, development and evaluation cohorts, and the
contract shapes, and no use case, label, dataset or product. Every domain fact reaches the CLI
from the host's `TerminalTasks` and `OptimizationProfile`.

### Detector configuration

A schema-2 detector is a `situation_detector` configuration validated by `normalize_rulesets`:
at most 8 rule sets and 16 declared rules, 1 to 6 **enabled** query tests, and
`max_window_seconds` at most 366 days. Each rule's `query` is one bounded read-only
`SELECT`/`WITH` of at most 12,000 characters taking named parameters from `rule.parameters`
plus `window_start`/`window_end`; `processing` declares only `code` and `max_rows` (1–200), and
`code` must parse to exactly one `def process(rows, parameters)`. Detection requires an explicit
`{start, end}` window — an absent window is refused, never defaulted. `process` must return
exactly `{matched: bool, facts: [1–8 strings ≤500 chars], technique_ids: [≤16 items ≤20 chars],
summary: <JSON object ≤4000 serialized chars>}`.

`version_rulesets` stamps `schema_version: 2`, a per-rule `digest` and `revision` that increments
only on changed content, a `configuration_digest` and a payload `digest`. `verify_rulesets` —
reached through `verify_detector` for schema 2 — recomputes both before any run, so an edited
pinned ruleset fails rather than silently measuring something else. Schema-1 detector records
remain byte-for-byte readable and verifiable, but creation and execution of their older
`rules`/`code` form refuse. All supported execution uses the canonical `situation_detector`
battery; start a new schema-2 experiment instead of rewriting historical pins.

### Publication gates

`probe` refuses unless all of these hold, and each refusal names its cause:

- the experiment is a joint experiment and is idle (not `completed`, `cancelled`, `running` or
  `baseline_running`);
- fewer than **60** probe receipts already exist for the campaign;
- `design_audit.parent_training_run_id` equals the **latest** development run id of a parent
  whose status is `completed` — an earlier successful run does not admit a candidate;
- `design_audit.hypothesis` is 20–800 characters and `design_audit.levers` covers exactly the
  three levers, each with a 15–500 character change-or-retain justification;
- 2 to 4 distinct development case ids spanning at least two expected grades; evaluation cases
  are never exposed;
- the proposal carries the actual proposed `system_prompt` and the exact tool set, and its
  `situation_detector` resolves to a schema-2 detector.

The probe then runs the exact proposed detector, tools and prompt on those cases. It **passes**
only when the detector summaries differ across probes and no case raised an execution or
response-contract error; an incorrect prediction is retained and does not fail the probe.

`publish` accepts `{"probe_id": "<32 hex>"}` and expands the saved proposal from disk, so the
published candidate is byte-identical to the probed one. Any other proposal is re-audited and
its `proposal_digest` must equal the receipt's, computed over the proposal with `probe_id`
removed: a changed field needs a new probe. `finish` additionally requires every successor to
carry a probe receipt and at least **3** distinct configurations per lever for `joint-10` (2 for
`joint-smoke`). `lever_coverage` counts distinct detector configurations ignoring the
configuration's `version` string, distinct sorted tool `source_digest` sets, and distinct prompt
texts — renaming a version does not buy coverage, but a metadata-only edit does count, so the
number measures distinct configurations and not semantic novelty.

### Receipts on disk

| Path | Written | Holds |
| --- | --- | --- |
| `<experiment>/probes/<id>.json` | every probe, passed or failed | the full `proposal`, every case `result`, metrics, both detector digests, `detector_summary_varies`, `status` |
| `<experiment>/process/<id>.json` | when a CLI session loads the contract | the exact task `prompt`, its `prompt_digest`, the component `implementation_digest`, the `session_id` and the `process_contract` |
| `<experiment>/interventions/<id>.json` | operator guidance | the note, never an edit to code, labels or scores |

All three are written with `write_json(..., immutable=True)`. The value `probe` **returns** omits
`results` and `proposal` and adds a compact per-case list plus the detector summaries; the full
record stays on disk.

New task receipts also preserve `skill: {name, content, digest}`. Creative experiments pin
the skill digest in `exploration_contract`; mismatch is refused before measurement or task
recording. `feedback.exploration_coverage` counts completed successors only, using AST source
digests for tool sets so renamed copies do not create new bundles. The UI displays the
question/data/view/decision mapping, alternatives, disconfirmation and separate code/agent
changes without inventing a plan for legacy versions.

The UI surfaces this rather than asserting it: a joint version card renders the hypothesis, each
lever with its changed/retained decision, and a receipt disclosure carrying the receipt id, the
exact proposal digest, probe macro-F1 and whether varying detector observations were verified.

### What the host adds

The component builds no model request. A host profile module owns it. One working example
sends schema-2 evidence under a strict `json_schema` response format, requiring
`grade`, `rationale`, `diagnosis`, `proposed_actions` and `citations`, with the citation items
constrained to an enum of exactly the `doc_id`/`path` values the knowledge retrieval returned
(and `maxItems: 0` when it returned none). Historical schema-1 replay requests and grade-only
requests keep their previous `json_object` format unchanged; that does not enable schema-1
detector execution. New diagnostic codes and attempted-tool count semantics are defined in
the [contract](../../CONTRACT.md#results-and-state).

## Host placement

| Path | Holds |
| --- | --- |
| `<host>/…/agent_optimization/` (this package) | the whole process: service, evaluation, workflow rules, runs, sandbox, worker, CLI and frontend |
| `<host>/optimization/profile.py` | every domain fact: labels, prompts, task text, budgets, baseline, request builder |
| `<host>/optimization/{service,cli,evaluation,workflow,runs,python_tools}.py` | thin adapters binding the component to the host dataset and to the host's principal type |
| `<host>/optimization/dataset.py` | the dataset and SQLite contexts; application-owned |
| `<host>/frontend/features/optimization/index.ts` | composition: supplies `requestJson` to the component client |

An agent catalogue accessor belongs in the application adapter: its output shape is the host's
agent catalogue, not an optimization concern.

Two wire literals are fixed by this package and by artefacts already recorded against it: the
`optimization_tool_result` envelope kind emitted by the sandbox worker, and the
`agent-optimization.columns` browser preference key.

Acceptance: existing optimizer tests, no application imports from components, sandbox and
authorization negatives, actual CLI publication with all levers evidenced, baseline plus
ten successors on the full fixed cohorts, joint detector-to-investigator traces, and the
integrated desktop/mobile UI. [Joint tests](../../tests/test_joint.py) cover schema-2 ruleset validation, the
windowed battery run and the digest verification; the host owns the matching tests for its
composed probe, audit and publication gates. Case-grade labels do not validate
diagnosis/action correctness.