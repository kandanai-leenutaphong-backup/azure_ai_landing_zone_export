---
name: protocol-foundry-agent-lifecycle
description: "Assess a native Foundry Hosted Agent lifecycle only when its actual owners and prerequisites exist. Imported template/library recipes are disabled and historical in this checkout; customer-service app deployment uses its own parent-owned runner."
metadata:
  protocol: protocol-foundry-agent-lifecycle
---

# Foundry Agent Lifecycle

## Project integration and current executable boundary

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). This project's web app runs in the existing
internal SEA Container Apps environment and calls the private West US 3 Foundry project.
It is not a request to deploy a new Hosted Agent template, optimizer or model.
Use the parent's actual root `deploy/deploy.sh` and documented supported actions for authorized
app deployment. Read help and prerequisites first; no command names are inferred here.

The imported `libraries/foundry-ops`, `template_apps/foundry_hosted_agent`, referenced
testbeds/specs/receipts and their run-spec tooling are absent. Their command recipes below
are **disabled: unavailable, no execution**. Do not install/copy them or substitute a new
runner to make this protocol appear runnable. A separately requested native Hosted Agent
lifecycle remains blocked until a real owner, implementation and scoped authority are supplied.

Applicable acceptance remains executable through the actual app owner:
1. Run its existing focused checks and build, preserving dirty work and dependency policy.
2. Read back accepted image/revision, protected configuration and approved route after an
   authorized deployment; local fixtures do not prove live identity or private reachability.
3. Exercise synthetic journeys, required correlated log fields and navigable
   system -> journey-type -> per-agent accuracy/latency/errors/tokens.
4. Validate independent focused `factual_accuracy`, `task_completion`, `tone`, `consistency`
   strict-JSON outputs. Task completion ignores politeness. Optional three prompt variants
   use the same model, retain mean/spread and require human review for spread > 3.
5. Keep quality gates `uncalibrated` until 50-100 real human-labeled examples establish
   kappa > 0.7. Optional `azure-ai-evaluation` custom-callable JSONL integration or manifest
   is not a calibration result and authorizes no additional inference or data upload.

No secret retrieval, RBAC grants, registration changes, unbounded inference or teardown.
Optional process execution uses host-supported attached background sessions only. Detach
only for an explicit requirement to survive session exit; never construct `nohup`/`setsid`
shell detachment or redirect logs as an implicit lifecycle step.

## Unavailable imported historical procedure

The original text is retained below as a quoted reference. Every source-workspace path,
API pin, receipt, run status, command, gate and field contract inside this block is historical,
unverified here and non-executable. It does not declare the customer-service app's current
implementation or alter the four-judge contract.

```markdown
One agent package (configuration, prompts, tool modules) becomes one container image, hosted as a
native Foundry Hosted Agent version, called, verified, evaluated and optimized natively, then
redeployed with the selected candidate and re-verified. The operator writes only the package, the
caller files and one run spec (or the older env/run-manifest pair); every step is a stage of
[`foundry_ops.pipeline`](../../../libraries/foundry-ops/README.md#pipeline) reached through
[deploy.sh](../../../template_apps/foundry_hosted_agent/deploy/deploy.sh). No per-project
orchestration script: the E2E project's `records/live/optimize_v2.sh` and `promote_v2.sh` are
superseded by `deploy.sh run` over one spec and are kept only because retained evidence references them.

Live reference run: [E2E project](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/)
and [spec](../../../specs/20260924_FOUNDRY_AGENT_PACKAGE_E2E.md). Baseline series
`pkg-e2e-baseline-v1` ran steps 1-9 live on 2026-09-24
([receipts](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/)).
Steps 10-14 are offline-tested; their first live run is in progress into
`records/live/pkg-e2e-optimized-v1/`.

## When To Use

- A new or changed agent must run as a Foundry Hosted Agent with stored, verifiable tool records.
- A hosted agent needs native evaluation, native instruction optimization and promotion of a
  selected candidate with a retained restore target.

Not for: a separate web front end ([deploy-container-apps](../../skills/deploy-container-apps/SKILL.md)),
local frozen-cohort optimization ([agent-optimization](../../skills/agent-optimization/SKILL.md)),
provisioning projects, registries, model deployments or role grants.

## Owners

| Owner | Holds |
| --- | --- |
| [foundry-native-agents](../../skills/foundry-native-agents/SKILL.md) | knowledge: native features, pins, traps, teardown order |
| [foundry_ops](../../../libraries/foundry-ops/README.md) | lifecycle glue: ledger, manifests, build, deploy, invoke, verify, evals, evaluators, datasets, optimize, traces, teardown; `pipeline`: run spec, ordered stages, resume, authorization |
| [template](../../../template_apps/foundry_hosted_agent/README.md) | runtime (Responses host, MAF loop, tool recorder, candidate loader), image layout and the only entry point `deploy.sh` -> `deploy/cli.py`, [runbook](../../../template_apps/foundry_hosted_agent/deploy/README.md) |
| agent package | the agent: configuration, prompts, tools, declared error codes |
| caller project | caller files, env/run manifests, records |

## Operator-Authored Inputs

**Agent package** (one folder, repository-relative, named by run-manifest `package_dir`):

- `configuration.yaml`: canonical `agentconfig`, exactly one default agent; `model` equals the env
  `MODEL_DEPLOYMENT`; `tools` list `module:function`; no `include:`.
- `prompts/**/*.{md,txt}`: instructions referenced by the configuration.
- `<module>.py`: tool functions defined in that module. Failures raise an exception whose class
  attribute `error_code` matches `[A-Za-z][A-Za-z0-9_.-]{0,63}`; that code becomes the tool record's
  `error_code`. Keep tools side-effect-free or idempotent.
- Nothing else: dotfiles, symlinks, binaries, secret-shaped content or foreign tools refuse before
  any cloud call. Example: [agent/](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/agent/).

**Caller files** (inside the repository, each sha256-pinned under run-manifest `inputs.<kind>`;
formats in the [runbook](../../../template_apps/foundry_hosted_agent/deploy/README.md#caller-file-formats)):

| Kind | Flag | Content |
| --- | --- | --- |
| `journeys` | `--journeys` | 1-20 journeys: input, `stream`, ordered `expected_tools` with `ok`/`error` + `error_code`; include one deliberate tool failure |
| `criteria`, `items` | `--criteria`, `--items` | eval testing criteria; item rows |
| `evaluator` | `--evaluator` | code evaluator spec (`code_file` + sha256, `canary` cases positive/wrong/invalid) |
| `optimization`, `train`, `validation` | `--optimization`, `--train`, `--validation` | registered evaluator name/version, optimizer model, `max_candidates`; row files |
| `selection_rule` | `--rule` | frozen rule (`strictly_above_baseline`, `earliest_observation`, fallback `baseline`) |
| `candidate_record` or `optimization_config` | `--instructions-from-candidate` or `--optimization-config` | promotion overlay (second series only) |

A project may generate these files from frozen artefacts with its own generator
([build_inputs.py](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/inputs/build_inputs.py),
`--check` rewrites nothing); the generator derives inputs, it does not orchestrate.

**Env + run manifest** per series in the caller's env directory: `<env>.env` (targets only: tenant,
subscription, project, registry, model; no secret) and `<env>.run.json` with `series`, `agent`,
`package_dir`, `env_sha256`, `inputs`, `actions` allowlist, `previous_version`/`previous_image`.
Review, then pin `SHA=$(sha256sum <env-dir>/<env>.run.json | cut -d' ' -f1)`. Omit `teardown` from
`actions` so retention is structural.

## Prerequisites (outside deploy.sh, each separately authorized)

Existing Foundry project with system identity, model deployment, ACR; project identity `AcrPull` on
the registry ([G1 intent](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/prereqs/g1-acrpull-intent.json));
a supported optimizer model deployment
([G6 intent](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/prereqs/g6-optimizer-deployment-intent.json));
`az login --tenant <t>` and `az account set --subscription <s>`.

## Sequence From One Run Spec (preferred)

Author `<project>/run-spec.json` from
[run-spec.example.json](../../../libraries/foundry-ops/examples/hosted_agent_e2e/run-spec.example.json):
targets, `agent.package_dir`, `models` (runtime, judge, optimizer), pinned `inputs`, `evaluator`,
`optimization`, `selection_rule`, `bounds`, `records`, `authorization.cloud_write` (omit `teardown`),
`data: inline|dataset`. Review, pin `SHA=$(sha256sum $S | cut -d' ' -f1)`. From the repository root,
`X="bash template_apps/foundry_hosted_agent/deploy/deploy.sh"`, `W=--authorize-cloud-write`:

| # | Command | Stages |
| --- | --- | --- |
| 1 | `$X test` | offline suite |
| 2 | `$X run --spec $S --spec-sha256 $SHA --until preflight` | preflight (read) |
| 3 | `$X run --spec $S --spec-sha256 $SHA $W --until verify` | build, deploy, invoke (journeys, streamed and not), verify |
| 4 | `$X run … $W --until select [--demonstration]` | register-evaluator, evaluate, optimize (rerun while `pending`), select |
| 5 | `$X run … $W` | promote (overlay version, same series), reverify, reevaluate |

Each stage completion is `pipeline-NN-<stage>.json`, reused on rerun; `--from S` needs every earlier
stage retained. Unauthorized write stage, undeclared input or resume gap refuses before any Azure call.
A `baseline` decision stops at promote with `baseline_retained` (pass; later stages not applicable).
Walkthrough, evidence per step and cost: [pipeline example](../../../libraries/foundry-ops/examples/hosted_agent_e2e/README.md).
Not yet live through `run`; the per-action path below is what ran live.

## Sequence Per Action (env + run manifest)

From `template_apps/foundry_hosted_agent`, with `P=../../agentcraft_projects/<project>`,
`X="bash deploy/deploy.sh"`, `W=--authorize-cloud-write`,
`M="-e <env> --manifest-sha256 $SHA --env-dir $P/deploy-env --records $P/records/live"`.

| # | Command | Gate | Evidence (`<records>/<series>/`) |
| --- | --- | --- | --- |
| 1 | `$X test` | none | `result.tests`, `failures: 0` |
| 2 | `$X preflight $M` | read | package model/tools, `AcrPull`, no gaps |
| 3 | `$X build $M $W` | billable ACR build | `host/repo@sha256:…`, `package_sha256`, tag `src-…-pkg-…` |
| 4 | `$X deploy $M $W` | new version | `deploy-*-active.json`: version active, exact image, identity metadata |
| 5 | `$X invoke $M $W --journeys $P/inputs/journeys.json` (ad hoc: `--input TEXT [--stream]`) | inference, stored responses, sessions | one `invoke-*-result.json` per journey; streamed ones keep ordered events |
| 6 | `$X verify $M --journeys $P/inputs/journeys.json` | read + anonymous POST | exact version, 401/403, raw-GET equality, tool records match `expected_tools` |
| 7 | `$X register-evaluator $M $W --evaluator $P/inputs/evaluator.json` | evaluator version, canary eval | read-back definition, canary scores exact |
| 8 | `$X evaluate $M $W --criteria $P/inputs/criteria.json --items $P/dataset/validation.jsonl` | eval + run, judge inference | `eval-*-summary.json` per criterion |
| 9 | `$X optimize $M $W --optimization $P/inputs/optimization.json --train $P/dataset/train.jsonl --validation $P/dataset/validation.jsonl` | one billable job | `optimize-*-identity.json` (job id), then candidates + config sha256 |
| 10 | `$X select $M --rule $P/inputs/selection-rule.json [--demonstration]` | none (ledger) | `decision` `selected`/`demonstration`/`baseline`, record path |
| 11 | new series env `M2`; `$X deploy $M2 $W --instructions-from-candidate <records>/<baseline-series>/select-….json` (or `--optimization-config F`) | new version, same image | `optimization_config_sha256`, `promotion`, candidate id; baseline version retained |
| 12 | `$X invoke $M2 $W --journeys …`, `$X verify $M2 --journeys …` | inference + read | steps 5-6 against the new version, overlay env read back |
| 13 | `$X evaluate $M2 $W --criteria … --items …` | eval + run | side-by-side with step 8; no reselection |
| 14 | `$X inspect $M` / `$X logs $M [--session-id ID]` | read | versions, sessions, redacted excerpts |

Second series manifest: new `series`, `previous_version` = baseline version, `previous_image`,
`inputs.candidate_record` = sha256 of the select record. A candidate carried as new prompt bytes
instead is a changed package: new series from step 3. `baseline` decision: steps 11-13 are
`not-applicable`, the baseline version stays live.

Every action prints `{"status", "action", "receipt", "code", "seconds"}`; exit `0` complete, `2`
refused or blocked. Missing `$W` on a write, `$W` on a read, or an option on the wrong action
refuses before any Azure call.

## Resume And Recovery

- Each write records intent, then result. Rerunning the same command reuses the result; it never
  replays a settled write.
- Intent without result = outcome unknown → `unresolved_intent`. Reconcile read-only (`preflight`,
  `verify`, `inspect`, `az acr task show-run`). Never delete an intent to retry.
- `evaluate` and `optimize` return `settled: false` at their bound; rerun the identical command to
  resume polling from the retained id. One optimization job per series; never resubmit.
- The source workspace used detached shell polling. That recipe is disabled and not
  reproduced here. Use only an authorized host-supported process lifecycle; retain the
  operation identity and reconcile state before a supported resume.
- Never re-invoke to recover lost output; read the stored response.
- New bytes bound to an existing series refuse (`record_exists`, `series_deployed`,
  `series_optimized`): start a new series.

## Retention And Teardown

Default: retain everything (versions, image, evaluator, evals, job, optimizer deployment); the
baseline version is the restore target. Teardown is a separate authority: add `teardown` to a
reviewed manifest, run `$X teardown $M --plan`, then `$X teardown $M $W`. Order enforced:
stored responses → sessions → versions → agent read-back. Evaluators, evals, datasets,
optimization jobs, model deployments and ACR tags follow the
[skill's teardown order](../../skills/foundry-native-agents/SKILL.md#lifecycle), separately authorized.

## Failure Playbook (live lessons)

| Symptom | Cause | Action |
| --- | --- | --- |
| `preflight_gaps` naming `AcrPull` | project identity cannot pull | owner grants registry-scoped `AcrPull`; deploy.sh grants nothing |
| `verify` `stored_response_drift` while outputs match | SDK `model_dump` adds null-only fields (`async_`, `caller`, `namespace`, `phase`) raw GET omits | compare ignoring null-only fields (fixed in `foundry_ops.pipeline.stages.verify`, formerly template `deploy/lifecycle.py`); first [blocked](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/20260924T073740278955Z-verify.json), rerun [complete](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/20260924T073954810889Z-verify.json) |
| `tool_call_accuracy` errored on every row | container-hosted tools leave `sample.tool_definitions` empty | use `builtin.tool_call_success`; keep accuracy out of gates ([summary](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/eval-src-d51b5dad684649d0f0202d79-pkg-95667431e925f468-v1-df3c66519eb40d8d-summary.json)) |
| baseline exact 0/N | package instructions omit the answer contract (by design here) | confirm with local recompute before blaming the pipeline ([recompute](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/baseline-validation-local-recompute.json)) |
| `optimize` `settled: false` | job still running at the bound | rerun the identical command ([first](../../../agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-baseline-v1/20260924T074953481482Z-optimize.json)) |
| `canary_failed` | evaluator reads the wrong field | score `item["sample.output_text"]`; fix the evaluator spec, new name or version |
| `unresolved_intent`, `*_unknown` | prior write outcome unknown | reconcile read-only |
| `anonymous_accepted` | endpoint answered without credentials | stop; auth incident |

Full code table: [runbook failure playbook](../../../template_apps/foundry_hosted_agent/deploy/README.md#failure-playbook).

## Acceptance

`lifecycle PASS — <agent> v<baseline> → v<promoted>, image <digest>, journeys N/N, eval <criterion>
<passed>/<total> both versions, decision <selected|demonstration|baseline>`. A `baseline` decision
is a pass with steps 11-13 `not-applicable`; nothing is called optimized.

## Scope And Permissions

This procedure grants nothing. Each cloud-write gate needs explicit, attributed authorization
recorded before the action; teardown, role grants and model deployments are separate authorities.
No secret enters the package, caller files, env files or records.
```
