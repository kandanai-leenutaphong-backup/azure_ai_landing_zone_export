# Repeatable Question-Led Optimization

Optimize the investigation process: **question -> available data -> retrieval -> evidence
view -> interpretation -> decision -> measured feedback**. A new classifier revision is
one possible change, not the organizing principle.

This is the reusable method for this component. [README.md](README.md) owns API signatures,
runtime bounds and protocol sizes. The installed
[creative skill](skills/creative-agent-optimization/SKILL.md) owns the experimentation method;
[process.py](process.py) carries the coding-agent procedure and validation;
[service.py](service.py) enforces publication and measurement. Host-specific datasets, prompts,
labels and deployment commands remain outside this component.

## 1. Fix the Experiment Contract

Before a baseline, declare the task, the decision being scored, the unit of evaluation, its
time horizon, available evidence and authorization. Record which questions the data cannot
answer. Separate observations, hypotheses, retrieved reference material and ground truth.

Freeze the cases/splits, label meanings, model, scorer, resource bounds and comparison policy.
Use development cases for discovery and tuning; keep evaluation access behind the evaluator.
If evaluation is repeatedly used for selection, it is adaptive feedback, not an untouched test.
Changing a fixed contract requires a new experiment, not revised history.

The supplied evaluator measures classification macro-F1, per-class errors and latency. Its
labels are host-supplied; it is not a general evaluator for every possible agent behavior.
A diagnosis, explanation, recommended action or acquired view is not independently validated
unless the host provides ground truth and an appropriate acceptance check.

## 2. Design Questions Before Tools

### Discover Existing Capabilities

Start with `./opt capabilities`, then `./opt describe` and `./opt tools`. The component does
not search the host filesystem or guess what cloud stores exist. Its host injects
`capability_catalogue(caller, experiment)` from the same source and tool registries that
populate the product catalogue. Sources and tools may be visible without being callable.

| Discovery fact | Evidence required |
| --- | --- |
| Registered | A source/tool declaration with a stable ID, purpose and contract |
| Configured | Required non-secret coordinates and an installed host adapter |
| Reachable | A recent authorized read, not merely configuration or a tree node |
| Authorized here | An explicit campaign operation and its scope; not a broader UI permission |
| Used | The candidate's pins and actual retained tool/knowledge result |
| Helpful | Relevant outputs and a controlled comparison; not presence or invocation count |

The discovery contract carries version 1, `sources`, `tools`, `limitations` and a digest;
it is owner-checked and capped at 128 KiB. An unconfigured host returns an explicit missing
catalogue limitation. Hosts whitelist metadata: no credentials, raw label rows or arbitrary
file contents. Runtime requests still pass the original authorization/query boundaries.

CLI preparation writes the snapshot to its private `CAPABILITIES.json`, includes the
discovery instruction in `TASK.md`, and preserves the snapshot in the immutable process
receipt. `./opt describe` includes discovery; `./opt capabilities` refreshes it. The HTTP
adapter exposes owner-checked `GET /api/cyber/optimization/experiments/{id}/capabilities`.
Refreshing discovery never changes frozen inputs or enables newly discovered sources.

Record the applicable source IDs and tool operations in each question plan. Reuse exposed
tools where suitable; treat inaccessible tools as reference contracts only. Missing joins
or adapters are explicit deferrals, not evidence that a source is useless. Adding a new
source to execution requires an authorized host adapter and a new experiment when it changes
the frozen data contract. Knowledge remains advisory and is tested separately from telemetry.

Start with competing explanations and a discriminating question. Ask which observation
would change the decision, then find the source and smallest useful representation of it.

| Question family | Required evidence | Useful returned view | What it does not establish |
| --- | --- | --- | --- |
| What exists in scope? | Inventory with identifiers/types | Inventory or coverage table | That an item was active or faulty |
| What happened, and when? | Timestamped observations | Ordered timeline or bounded time bins | Causality from ordering alone |
| What changed? | Comparable values before/after an event | Change table with baseline and delta | Why the change occurred |
| What is connected? | Real relationship keys/edges | Bounded neighborhood or adjacency table | An edge invented from co-occurrence |
| Is evidence independent? | Provenance and repeated observations | Deduplication/concentration report | Independence inferred merely from row count |
| How reliable is the interpretation? | Relevant historical support/calibration | Support, uncertainty and comparison profile | A current fact derived from past labels |

An evidence **view** is a representation consumed by an investigator: a table, timeline,
relationship projection, distribution or comparison. It does not require a new UI widget.
Return structure and provenance; a frontend renderer is a separate consumer of that contract.

Create a separate tool when a question or result contract is independently useful. Revise an
existing tool when the same question needs better retrieval or computation. Reuse its exact
version when neither changes. A composite view is appropriate when a real decision needs
several sources aligned, not as a reason to hide every question in one universal tool.

For each tool specify the question, source/fields, case/window scope, parameters, returned
shape, ordering/units, empty/truncated/error semantics and the decision it supports. Missing
data is an explicit limitation, not an empty successful answer. Follow-up keys must come
from real returned identifiers. Keep source permissions separate from what a prompt requests.

Explore additions, combinations, specialized revisions and removals. Inspect actual probe
outputs, then measure contribution with controlled ablations. Tool counts, family labels,
renamed functions and distinct source hashes do not prove useful diversity.

## Creative Exploration

Creative exploration is an opt-in contract over `joint-10`, selected with `creative: true`
when the host creates the experiment. It is a new experiment, not a migration of a prior
single-tool campaign. The API advertises `creative_supported`; the corresponding checkbox
defaults on only for a supported `joint-10` selection. Existing experiments keep their
original pins and gates. The component owns the skill, process and records; host-specific
questions and sources remain host inputs.

The search has two phases: **diverge before converging**. Early generations compare different
evidence questions, views and interpretation strategies. Later generations combine useful
views, investigate counterexamples, remove redundant tools and consolidate. Do not consume
the whole budget tuning coefficients or rewording a single classifier. Neither novelty for
its own sake nor an increasing tool count is the objective.

| Experiment kind | Change to test | Useful control |
| --- | --- | --- |
| `new-evidence` | Retrieve an observation the parent never received | Parent interpretation with one new view |
| `new-representation` | Re-express available observations as a sequence, distribution or comparison | Same evidence and decision contract |
| `new-strategy` | Change interpretation, competing hypotheses, reliability weighting or conflict resolution | Same tool and detector pins |
| `combination` | Combine complementary question-specific tools | Individual views or an earlier bundle |
| `ablation` | Remove selected parent tools | Exact parent prompt, detector, knowledge setting and remaining tool pins |
| `refinement` | Repair or improve a tested approach | Named parent and explicit mechanism retained |

Every creative successor has both `investigation_plan` and `design_audit.experiment`:

```json
{
   "approach_id": "reliability_first",
   "kind": "new-strategy",
   "mechanism": "Interpret support and duplication before combining the available evidence views.",
   "alternatives": [
      "Interpret event ordering before considering evidence reliability.",
      "Compare independent hypotheses using the same evidence bundle."
   ],
   "disconfirmation": "The new policy still lets repeated low-support observations dominate contrasting development cases."
}
```

This is an audit template, not a measured candidate. `approach_id` is a stable lowercase
identifier; `mechanism` and `disconfirmation` are 20-700 characters; `alternatives` holds
2-4 distinct 20-400 character descriptions. A reused approach ID means a retained mechanism.
Descriptions explain intent, not measured results. Preserve the rejected alternatives so
the next generation can consider a different mechanism rather than rediscovering the same one.

`creative-experimentation-v1` freezes eight workers and the following completion floors:
five approach IDs, four tool families, five AST-distinct tool sources, four source-based
tool sets, four measured multi-tool successors, and four experiment kinds including
`combination` and `ablation`. The first successor must select at least two tools. Only
completed successors count. These floors keep this particular ten-generation campaign from
collapsing into one line of refinement; they are not a universal optimum or proof of
semantic diversity. Inspect actual question contracts and contrasting probe outputs.

The ablation validator checks a strict subset of parent tool pins and unchanged prompt,
detector version and knowledge setting. A detector ablation or simultaneous prompt edit is
another experiment kind, not a controlled tool-removal claim. `feedback.exploration_coverage`
reports achieved counts and kinds; `finish` refuses unmet floors. Existing joint detector,
tool and prompt coverage, probe and complete-cohort gates still apply.

`OptimizationTerminal.initialize` installs the exact component-owned skill under the private
workspace at `<workspace>/.github/skills/creative-agent-optimization/`. `prepare` includes it and the
creative contract in the actual task. A process receipt retains the full skill text and
SHA-256 alongside the full submitted task; the experiment pins `skill_digest`. A changed
skill refuses resumed measurements or a mismatched task receipt. `TASK.md` is updated to
the task actually submitted, not left with older host-only instructions.

The installed skill describes strategy diversity, not extra runtime abilities. Distinct
investigator strategies currently mean evidence-selection and prompt policies within one
model response, not unimplemented multi-agent debate or adaptive tool selection.

## 3. Record the Investigation Plan

New question-led proposals include `design_audit.investigation_plan`. It is required in
creative mode and optional for older contracts; the current CLI procedure asks
for it. When present it is validated before probing/publication and preserved in the exact
proposal receipt and immutable candidate. It never appears retroactively in an old version.

The following is a **plan template**, not an executable candidate or a measured result:

```json
{
  "version": "question-evidence-tools-v1",
  "questions": [
    {
      "id": "duration",
      "question": "Which work items have unusually long durations?",
      "decision": "Distinguish routine processing from delays worth investigating.",
      "data": "Authorized case evidence: item_type, duration, timestamp.",
      "view": "Duration distribution with observation counts and missingness.",
      "tool": "duration_distribution",
      "status": "tool",
      "limits": "Case window only; duration alone does not establish a cause."
    },
    {
      "id": "dependencies",
      "question": "Which external dependency blocked the work?",
      "decision": "Identify a dependency owner for follow-up.",
      "data": "Dependency identifiers are absent from the authorized source.",
      "view": "Dependency evidence unavailable.",
      "tool": null,
      "status": "unavailable",
      "limits": "Do not invent relationships from item types."
    }
  ],
  "code_changes": ["Add a bounded duration-distribution query and computation."],
  "agent_changes": ["Select the duration view and distinguish delay evidence from causal claims."],
  "held_fixed": ["Parent detector, model, case windows and scoring rubric."],
  "acceptance_checks": ["Contrasting development cases return different measured duration distributions."]
}
```

Each `status: "tool"` entry names either a reused tool's exact `id` or a new tool's `name`
from the proposal. Every selected tool must be referenced. Multiple questions may share a
tool; validation does not force one tool per question or an arbitrary minimum count. Resolve
new names through the candidate's pinned `tool_ids` and the corresponding tool records.
`unavailable` and `deferred` entries require `tool: null` and explicit limits.

Bounds: 1-12 questions; unique lowercase question IDs; 1-600 characters per question text
field; 0-8 code/agent change statements; 1-8 held-fixed/acceptance statements, each 1-400
characters; total plan at most 16,000 serialized bytes. Unknown fields/versions and dangling
tool references are refused. These checks prove traceability and shape, not factual truth
of a declared source, a useful question, or correctness of its returned answer.

## 4. Separate the Change Levels

| Level | Tunable change | Exact record | Controlled comparison |
| --- | --- | --- | --- |
| Detector code/configuration | Ruleset membership, query, parameters, processing | Versioned detector configuration, rule revision/digest | Same tools/prompt, revised detector |
| Tool code/contract | Retrieval, aggregation, normalization, result shape | Tool source, source digest, lineage, `supersedes`, rationale | Same question and prompt, revised implementation |
| Agent configuration | Selected tools/views, prompt, interpretation/uncertainty policy | Exact tool pins and `system_prompt` in the candidate | Same code, changed selection or prompt |
| Process implementation | Procedure, host adapters, response contracts or scoring machinery | Process task receipt and implementation identity; host release evidence | New experiment when the fixed execution contract changes |

`code_changes` and `agent_changes` explain intent. `held_fixed` names comparison controls;
`acceptance_checks` names falsifiable observations. Source/configuration pins are the evidence
of what ran. A simultaneous code and prompt change is a joint comparison, not causal
attribution to either. Follow useful combined changes with an ablation when attribution matters.

Do not confuse task instructions for the **coding agent** with the **investigator prompt**.
The former governs how tools/candidates are designed and measured; the latter governs how a
candidate interprets its evidence. Both are recorded, at different locations.

## 5. Execute One Generation

1. Read the completed parent's development feedback, confusion directions and recorded
   operator guidance. Identify a testable gap; branch from a measured parent when justified.
2. Build the question plan and exact proposed detector/tools/prompt. Retrieve only authorized
   evidence. Explain additions, revisions, reused tools, removals and unavailable views.
3. Test individual tools on contrasting development cases. Inspect scope, row duplication,
   ordering, empty inputs, truncation, unavailable sources and authorization negatives as
   applicable. Compare values, not just execution success.
4. Probe the **combined exact proposal** on 2-4 distinct development cases covering at least
   two grades. Varying detector summaries and zero execution/response-contract errors admit
   publication. Wrong predictions remain valid probe observations and are not hidden.
5. Publish by the passed receipt. Changing the plan, code, tools, detector or prompt requires
   another probe. Save immutable versions before cohort measurement.
6. Measure every development case, then every evaluation case with the frozen version.
   Completion is read from terminal run records, not an accepted HTTP request or CLI prose.
7. Read metrics, failures and authentic replays; compare against the parent. Retain regressions
   and failed attempts. Choose the next hypothesis and finish only at the declared gate.

CLI operations are exposed only in the host-created private workspace:

| Operation | Input/readback |
| --- | --- |
| `./opt describe`, `./opt feedback` | Actual limits, schema, development cases, measured parent runs and guidance |
| `./opt tools`, `./opt detector` | Existing exact sources/contracts and detector history |
| `./opt query` | Development `case_id` plus bounded `sql` or candidate `code`; inspect returned evidence |
| `./opt probe` | Full `proposal` plus exact `case_ids`; returns receipt `id`, status and observed probe results |
| `./opt publish` | `{"probe_id":"<returned receipt id>"}`; returns the immutable candidate |
| `./opt tune`, `./opt evaluate` | `{"version":<saved version>}`; full training before evaluation |
| `./opt wait` | Bounded wait/readback for the active stage |
| `./opt finish` | Refuses incomplete stage/version/lever coverage |

This is an operation reference, not commands with invented IDs to paste into a shell. Use
identifiers returned by the ledger. Arguments are one quoted JSON object; for a shell single
quoted argument encode embedded apostrophes as `\u0027`. No shell permission expansion,
credential reading or arbitrary evaluation-case access is part of the method.

## 6. Preserve the Evidence Chain

| Artifact inside an owner-partitioned experiment | Reproduces/explains |
| --- | --- |
| `cases.json`, dataset/profile/scorer pins | Which cases and evidence contract were evaluated |
| `versions/<version>.json` | Parent, prompt, selected tool IDs, detector pin, audits and plan |
| `tools/<id>.json` and `.py` | Exact tool source/contract, lineage and change rationale |
| `detectors/<version>.json` | Ruleset composition, queries, processing and configuration identity |
| `probes/<id>.json` | Exact proposal including the plan, actual probe inputs/outputs and result |
| `process/<id>.json` | Exact coding-agent task, task digest, session, implementation digest, and installed skill text/hash for new sessions |
| `runs/<id>/run.json` and `cases.jsonl` | Run status, metrics and every retained case outcome |
| `runs/<id>/best.json` and `worst.json` | Actual requests, evidence, responses/errors and grading for selected examples |
| `interventions/<id>.json`, `terminal.log` | Operator direction and redacted CLI trace, never substitute measurements |

The ledger and underlying source/labels stay outside the candidate workspace. A historical
record is not rewritten when an implementation improves. A host restart or rate-limit error
remains recorded; a replacement/retry is identified separately.

Repeatability means another authorized host can run the same procedure and inspect what
changed. It does **not** guarantee identical model output. The implementation digest covers
component Python sources, not a complete package/environment snapshot; hosts must separately
retain their adapter revision, dependency locks, dataset holdings and external service/index
versions. External knowledge contents are not automatically snapshotted. Preserved example
responses are real recordings, not deterministic replay of a fresh model call.

## 7. Reuse in Another Domain

| Host supplies | Responsibility |
| --- | --- |
| `OptimizationProfile` | Labels, objective, baseline, request builder, runtime policy, tool families and joint baseline detector |
| Dataset adapter | Authorized cases, bounded queries/tool execution, profile identity, detector query/processing callbacks |
| `authorize` / `identify` | Explicit operation authorization and owner-partitioned readback |
| `predict` / knowledge adapter | Model access and advisory retrieval; secrets never enter generated tools |
| `TerminalTasks` and `OptimizationTerminal` wiring | Domain vocabulary, CLI provider, private workspace, helper operations and endpoint |
| UI API provider, if used | Existing request/auth transport and configured API prefix |

The dataset implements `describe`, `cases`, `query`, `profiles`, `run_tool` and
`profile_digest`; staged full protocols also use `full_cases`. Joint detection additionally
uses `detector_query(case_id, rule, window)` and
`detector_process(case_id, rule, result, window)`. Supply `stress_cases` only when using that
protocol. Validate callbacks and a small neutral fixture before spending model calls.

The current evaluator runs the detector, **all selected tools**, optional knowledge retrieval,
then one model response. Its tool interface is `run(ctx)` with case/window scope, not a
parameterized, model-selected tool loop. No tool-output-to-next-tool
argument binding is implemented. Adaptive questioning/tool choice requires an execution
adapter and transcript/argument/authorization tests; it is not enabled by this document.

The current generated-Python runner is a bounded read-only SQLite context. Other stores,
graph projections and richer views must enter through a host-owned authorized adapter, not
new network/credential access granted to candidate Python. The method generalizes beyond
classification; the supplied evaluator needs extension for other outcome contracts.

### Verification

After installing the declared shared packages, resolve `SKILL_ROOT` to the portable skill:

```bash
python3 -m pytest "$SKILL_ROOT/python/agent_optimization/tests" -q -p no:cacheprovider
```

These are **offline fixture checks**, not a learned-performance demonstration. They verify
neutral labels/authorization, no application import, question/selected-tool traceability,
missing-data declarations, separate change records, immutable plan pins and a two-tool
candidate executing both tools during its probe. The domain-neutral plan example lives in
[tests/test_process.py](../../tests/test_process.py). Original application-side tests are not part of
this distribution. Real CLI campaigns and recovery use the consuming host's explicitly authorized
deployment entry point; the portable library does not provision it.

### Evidence-Tool Design Lessons

General lessons, phrased independently of any inspected codebase and carrying no copied source,
dependency or license grant:

| Lesson | Why it matters |
| --- | --- |
| Split inventory, direct relationship and aggregate-structure lookups into separate tools | One "show me everything" tool hides which question was actually answered, and its output cannot be interpreted per question |
| Bound every traversal and retrieval explicitly | Unbounded neighbourhood or full-text expansion produces output the model cannot read and latency the campaign cannot compare |
| Return one entity view per tool result, and use several results for several entities | Multi-entity rows flattened into one table destroy the per-entity comparison the investigator needs |
| Let the declared return contract, not the tool description, define what a tool proves | Descriptions overstate; an identity/alias listing is not a state reading, and the missing fact needs its own query |

When the host dataset cannot support one of these views — no entity topology, no numeric
measurements, anonymized identifiers — mark it unavailable. Do not reconstruct it from category
names and present the reconstruction as evidence.

### Coverage and Open Limits

| Surface | Documentation/verification status |
| --- | --- |
| General question-led method and tool-contract decisions | Defined here; executed procedure carried by `JOINT_TASK` |
| Optional plan validation and publication | Implemented; fixture-tested; old proposals remain accepted |
| Creative skill and campaign gates | Installed/pinned skill; required alternatives, plan and measured exploration coverage; controlled-ablation negatives tested |
| Code-level/agent-level traceability | Separate intent records plus existing exact source/configuration pins |
| Multi-tool candidates | Supported and fixture-tested; useful diversity still requires measured outputs/ablations |
| Public APIs, settings, credentials and host data | Component README and host-owned adapters/runbook; no new setting or credential |
| Model-selected follow-up questions/tools, arbitrary new result evaluators | Not implemented by this change |
| Existing in-flight campaign | No hot reload or record migration; new creative campaigns use a separate ledger when concurrent |