# Offline regression, promotion and drift

Owner: `regression.py`. Offline gates use standard library only and immutable scenario/settings
contracts. Explicit `run` optionally orchestrates existing native/SDK owners; no second model
runner. No deployment, dataset generation, real transcript ingestion or permission changes.
Parent owns CI workflow, model execution, `datasets/**`, artifact publication and standalone repo.
No new runtime dependency or Docker allowlist entry. Serving/native agent definitions unchanged.

## Gates

Fixed maximum **drops**, inclusive at boundary:

| Measure | Maximum gold minus candidate |
|---|---:|
| Overall task completion | 0.02 absolute probability, **2 percentage points**, not 2% relative |
| Average goal index | 0.3 points on 0..10 scale |
| Average journey coherence | 0.5 points on 0..10 scale |
| Every journey's task completion | 0.05 absolute probability |

Raw case counts determine means/rates. All four journey categories required in every stage.
Failed native calls remain attempts/errors, never disappear from denominator, and block gate.
Unknown/nonfinite scores, inconsistent 3/4/3 goal/completion labels, missing/extra/duplicate cases,
missing categories, case/hash/provenance mismatch, missing calibration or calibration sample
mismatch block comparison. Scores from a failed call must be null.

Code revisions, business-agent versions/prompt definitions and target serving `model_version`
may differ. Each result binds its **own** bundle's complete provenance. Report records all allowed
target changes. Dataset/case identity, four judge pins/rubrics, independent judge-model identity,
calibration and evaluation config remain frozen. Default comparability policy keeps target
model ID `gpt-4.1-mini`, SKU `Standard` and assigned project fixed; other IDs/SKUs are explicitly
blocked, not silently compared. A shared model deployment upgrade that also changes judges
cannot masquerade as target-only change: its judge-model provenance must change and gate blocks.
Threshold changes require reviewed code changes; CLI cannot weaken them.

## Frozen evidence contract

One JSON bundle per gold/candidate:

- `schema_version`: integer 1.
- `synthetic`: true.
- `frozen`: true for gold. Candidate may be false.
- `dataset_id`: explicit identifier; `dataset_sha256`: actual source dataset artifact byte hash.
  Both must match. Parent calculates actual artifact hash; comparator does not fetch dataset.
- `provenance` contains **exactly**:
  - `source_revision`: nonempty source revision; may differ between gold/candidate.
  - `project_endpoint`: assigned private West US 3 project.
  - `model_id`: `gpt-4.1-mini`; `model_version`: actual observed **business target** serving
    version, not unknown; may differ between gold/candidate.
  - `model_sku`: `Standard`.
  - `config_sha256`: canonical evaluation configuration hash. Include fixture/policy/rubric
    version, 3/4/3 weights, consensus setting, sampling settings and execution limits.
  - `agent_pins`: all seven role keys. Each value exactly `{name,version,definition_sha256}`.
    Names follow `cs-sim-<role with hyphens>`, versions positive decimal strings, definition
    hashes from `canonical_hash(actual_agent.definition.as_dict())`, consistently.
    Do not mix this compact canonical form with provisioning metadata's differently spaced
    JSON hash; neither changes the actual native definition.
    Business triage/policy/resolution versions and definition hashes may change. Four judge
    entries must remain equal across bundles.
  - `judge_model`: exactly `{project_endpoint,model_id,model_version,model_sku}`, actual
    independently observed **judge** model identity. Same assigned project, model ID and SKU;
    judge version must remain frozen even when business target serving version changes.
- `calibration`: actual `evaluation.calibrate` report, additionally:
  - `labels_sha256`: actual human-label artifact hash.
  - `judge_pins_sha256`: canonical hash of four judge entries from provenance's `agent_pins`.
  - `judge_model_sha256`: canonical hash of provenance's `judge_model`.
  - Requires status `established_on_supplied_labels`, sample count 50..100,
    `insufficient_sample:false`, every criterion's finite kappa **>0.7**.
  - Gold/candidate must use same entire calibration report, label artifact and sample count;
    calibration must bind current judge pins **and judge-model identity**. No actual human
    calibration supplied or claimed by worker.
- `stages`: `canary`, `full`, `historical`, each:
  - `manifest`: nonempty list of `{case_id,case_sha256,scenario_id,journey_type}`.
  - `manifest_sha256`: `canonical_hash(manifest)`. Ordering is part of stage hash.
  - `results`: exactly one raw case result for every manifest ID, no duplicates/extras.
  - Canary cases must be unchanged members of full manifest.
  - Each historical manifest item additionally requires `origin:"authored_safeguard"`,
    unless actual observed-bug provenance is supplied as
    `origin:"observed_bug", evidence_ref:<reference>, evidence_sha256:<artifact hash>`.
    Supplied bug evidence is retained, not independently verified or invented here.

Case hash should bind the full immutable dataset row, including taxonomy and review metadata.
`canonical_hash` uses sorted compact JSON, UTF-8, finite numbers only.
`provenance_hash` now hashes the complete provenance **including source_revision**. Gold and
candidate result hashes intentionally differ when target provenance differs. Existing earlier
hashes that omitted source revision must be regenerated from original evidence, not relabelled.
Parent must preserve
the original dataset/raw result artifacts whose hashes are declared. Hash equality detects
substitution, not truthfulness of user-supplied source claims.

Raw case result:

```text
case_id, case_sha256, scenario_id, journey_type
provenance_sha256 = provenance_hash(THIS result's own gold OR candidate bundle.provenance)
raw_result_sha256 = canonical_hash(actual SimulationService readback)
run_id
status = completed | failed
criteria = [strict bool, strict bool, strict bool] | null for failed
task_completed = all(criteria) | false for failed
goal_index = sum(3/4/3 weights for true criteria) | null for failed
coherence = actual specialized consistency score | null for failed
```

Produce this record with `regression.case_result(case_manifest_entry, actual_run, provenance)`.
Adapter verifies actual native pins, immutable fixture/action, simulated final state,
binary criteria and score consistency. It hashes existing raw readback, never runs a model.
Original complete readbacks remain parent-owned evidence, not replaced by aggregates.

Existing SDK adapter can capture raw terminal evidence without a second runner:

```python
captured = []
evaluator = SimulationEvaluator(service, consensus=False, result_sink=captured.append)
# Call with known scenario_id and optional bounded synthetic customer_request.
# result_sink receives a deep copy of terminal service readback BEFORE failed-call error.
# Failure still raises; parent records it and stops the stage, never converts it to success.
```

`SimulationEvaluator` remains owner of native execution, with same specialized-judge owner.
`customer_request` only varies language. Authoritative category, policy, action and criteria
remain immutable. Dataset metadata, including supplied expected state, cannot modify policy.
Sidecar calibration is a promotion prerequisite; it does not retroactively make runtime UI
claim calibrated or production-ready.

Limits: 5 MiB per evidence file, 1..1000 cases per stage, explicit synthetic-only flag.
No baseline or historical failure artifact auto-generated. Tests use clearly authored
algorithm fixtures, not real human labels or production bug observations.

## Parent CI order

From application directory, after parent supplies actual evidence files:

```sh
/usr/local/bin/python3 -m pytest -q test_app.py test_regression.py
/usr/local/bin/python3 regression.py compare --gold /path/to/frozen-gold.json --candidate /path/to/candidate-canary.json --through canary
```

Only after canary returns exit 0 may parent invoke existing native/SDK adapter for full cohort.
Canary report says `next_stage:"full"` and never claims historical/full success.

```sh
/usr/local/bin/python3 regression.py compare --gold /path/to/frozen-gold.json --candidate /path/to/candidate-full.json --through full
```

Only after that exits 0 may parent run historical probes and compare through all stages:

```sh
/usr/local/bin/python3 regression.py compare --gold /path/to/frozen-gold.json --candidate /path/to/candidate-complete.json --through historical
```

Comparator validates stages in order, stops at first failed stage and does not inspect later
stage cases. It only analyzes already-created artifacts; parent workflow must enforce ordering
of **billable probe execution**. Missing later stage artifacts cannot pass later-stage gate.
Exit 1 means blocked. Reports show exact thresholds, denominators, drops and blocking reasons.
Also reports `gold_provenance_sha256`, `candidate_provenance_sha256`,
`frozen_evaluation_sha256`, `comparability_policy` and `allowed_target_changes` (old/new
source revision, target version and changed business-agent pins).

## Bounded actual candidate entrypoint

From repository root, parent may invoke:

```sh
/usr/local/bin/python3 applications/customer-service-multi-agent/regression.py run --gold applications/customer-service-multi-agent/datasets/gold.json --dataset applications/customer-service-multi-agent/datasets/synthetic-customer-issues.jsonl --output deploy/.state/regression-report.json --allow-model-calls
```

Standalone parent layout may use `python app/regression.py` with equivalent app paths.
Worker has **not** executed this billable command. `--allow-model-calls` must be explicit.

Before any evaluation SDK import or model call, command:

1. Requires existing calibrated, frozen gold and all three complete gold stage cohorts.
   Calls existing comparator against gold itself. No missing-gold/uncalibrated fallback.
2. Verifies exact dataset **file byte SHA256**, strict JSONL, 1..20 unique cases, exact full
   cohort and every canary/historical case's source-row hash/binding.
3. Requires embedded gold `evaluation_config`:
   `{"profile":"customer-service-native-v1","consensus":false}`.
   Its canonical hash must equal gold provenance `config_sha256`. Profile declares existing
   3/4/3 service owner, max output 400, >=7-second pacing, zero model retries.
   Consensus may be true only when identically frozen in gold/config hash.
4. Enforces planned inference bound: sum of all three stage sizes × 7 ordinary or × 15
   consensus. Default `--max-model-calls 200`; explicit larger bound allowed up to 1000.
   Typical 4-canary + 20-full + 4-historical ordinary plan = 196 maximum calls.
5. Requires explicit `AGENT_TRIAGE_VERSION`, `AGENT_POLICY_VERSION`,
   `AGENT_RESOLUTION_VERSION`, `AZURE_CLIENT_ID`, and `GITHUB_SHA` or `APP_REVISION`.
   Four judge versions come from calibrated gold; any supplied judge environment version
   must match it. No API bearer token/allowlist is used or bypassed by this native CLI.

Dataset rows require `case_id`, `customer_request` and `scenario_id` **or** `fixture_id`.
If both binding fields exist they must agree. Optional `synthetic` must be true when present.
Other dataset metadata is hashed but never forwarded as policy/ground truth.
Gold `case_sha256` must equal `canonical_hash(complete_original_dataset_row)`, not a normalized
request-only projection. Historical probes must be present in this same frozen input file.

Then requires installed optional `azure-ai-evaluation` and supported actual `evaluate` signature.
SDK absent returns **`azure_ai_evaluation_not_installed`**, exit 1, no native imports/calls.
Existing `requirements-evaluation.txt` declares optional pin. Worker installed nothing.

Native metadata preflight uses existing `NativeAgents.project` (`AIProjectClient`) to read exact
configured agent versions/definitions and actual deployment `model_name`, `model_version`, SKU.
No hardcoded observed model version or metric. Verifies definitions against current native
owner, builds candidate provenance from those readbacks, then checks frozen judge/model/config
and calibration before any `responses.create`. Actual target changes are recorded by comparator.

**Credential prerequisite:** current `NativeAgents` uses `ManagedIdentityCredential` for existing
UAMI, not `AzureCliCredential`/GitHub OIDC. Execution needs an already-authorized, MI-accessible
context and private Foundry connectivity. A GitHub runner's CLI login alone does not supply that.
No identity/RBAC/FIC setup or credential fallback added. Unavailable metadata/auth returns
`native_metadata_or_execution_prerequisite_failed`, never a passing synthetic result.
Serving Docker image excludes regression/SDK tooling, so it is not automatically a CLI runner.

For each stage, SDK gets a temporary **JSONL file path**, custom callable delegates only to
existing `SimulationEvaluator`, and its `result_sink` captures actual terminal readback.
Existing `case_result` validates/hashes those actual payloads. After canary pass, full may run;
after full pass, historical may run. SDK/model failure sets stage-stop flag, refuses duplicate/
subsequent case invocations and never begins next stage. No model-call retry/replay.
Native owner still paces shared quota; other users can cause 429, recorded as failed.

Output preflight writes `not_started` before optional work, preventing stale success reuse.
Report replaces only explicitly selected `deploy/.state/**` (relative repository-root working
directory) or app `evaluation-artifacts/**`. Gold/dataset inputs cannot be overwritten.
Report includes blocked reasons, actual stage capture/error counts, candidate bundle, comparison
and **synthetic raw terminal payloads** keyed by stage/case. Raw texts stay in explicit state
artifact, never stdout; stdout emits safe summary only. Keep state artifact out of public source
publication unless separately reviewed. Successful comparison still does not grant promotion.

**Current blockers:** no calibrated gold supplied to worker; optional evaluation SDK absent.
Live SDK orchestration, metadata permissions, private connectivity and MI runner context remain
unverified. Offline fail-closed tests prove early refusal only, not successful cloud execution.

`demo_build_allowed:true` means this offline promotion gate does not prohibit a labelled demo
image build. It is not a passing regression test or deployment authorization. Calibration absent
blocks regression/promotion. Ordinary demo can still be built with honest uncalibrated labels.
Comparator always reports `production_promotion_allowed:false`; human approval is separate.

## Explicit new-gold promotion, never overwrite

After all three stages pass and actual bound calibration exists, parent supplies approval JSON:

```text
approved: true
approver: nonsecret human approval identifier
candidate_sha256: canonical_hash(exact candidate bundle)
comparison_sha256: canonical_hash(compare(gold, candidate, through="historical"))
```

```sh
/usr/local/bin/python3 regression.py promote --gold /path/to/frozen-gold.json --candidate /path/to/candidate-complete.json --approval /path/to/human-approval.json --output ./evaluation-artifacts/gold-vNEXT.json
```

Recomputes all gates. Requires explicit matching approval. Writes exclusive **new** file,
never updates old gold or an existing output. Output constrained to app `evaluation-artifacts/`,
not parent-owned datasets. New artifact includes previous-gold, approval and comparison hashes.
This promotes a local gold artifact only, not application traffic/deployment.
Generated artifact directory ignored by default; parent explicitly versions/publishes approved
gold in authorized artifact store. No automatic baseline replacement or synthetic human approval.

## Offline synthetic drift

Deterministic sample selection, no transcript access:

```sh
/usr/local/bin/python3 regression.py sample --run-id synthetic-run-123 --synthetic
```

Rule: `int(SHA256(run_id),16) % 10000 < 100`. Fixed 1% hash-bucket probability,
not exactly 1% of every finite cohort. Selection stable across restart.
Non-synthetic input rejected. Caller does not provide any transcript/customer fields.

Daily snapshot JSONL, one row per date/journey:

```json
{"date":"2026-10-17","synthetic":true,"journey_type":"return","attempts":10,"task_completed":9,"errors":0,"scored":10,"goal_sum":90,"coherence_sum":90}
```

```sh
/usr/local/bin/python3 regression.py drift --snapshots /path/to/synthetic-daily.jsonl --as-of 2026-10-17
```

Compares inclusive current seven days (`as_of-6 .. as_of`) with preceding seven
(`as_of-13 .. as_of-7`). Sums raw counts/scores; never averages daily means. Completion weighted
by attempts. Goal/coherence weighted by attempts **only with complete score coverage**;
otherwise null plus explicit unscored count, not fabricated zeros. Missing journey history or
unknown score coverage yields `insufficient_data`. Threshold drift alerts are offline diagnostics,
not calibrated business impact or production promotion. Dates outside windows excluded only
after row validation. Duplicate day/journey, unknown categories, nonfinite values, inconsistent
counts, real/non-synthetic flags and extra transcript fields refused.
CLI exits 0 only for `no_threshold_drift`; `drift_detected` and `insufficient_data` exit 1.

## Verification / known limits

Focused tests cover absolute-vs-relative boundary, inclusive decimal thresholds, per-journey
limits, missing category/case/hash/pin/config, failed calls, NaN/unknown/calibration mismatches,
canary short-circuit, authored-vs-observed historical provenance, bound human approval,
exclusive no-overwrite CLI promotion, strict JSON, rolling weighting and deterministic sampling.

`azure-ai-evaluation` absent locally. Optional SDK adapter's pinned public API inspected earlier,
not imported/execution-tested. No package install attempted, no cloud/model batches run.
No real frozen gold, representative human calibration or observed historical bugs supplied.
Source-based health assessment: `/healthz` has no auth/source gate and returns 200;
default factory selects `NativeAgents`, not a fake. Offline tests separately verify these facts.
Parent-observed native seven-agent provisioning/image health is not proof of completed inference.

Latest gate including bounded-run preflight: `/usr/local/bin/python3 -m pytest -q test_app.py test_regression.py`
returned **52 passed, 63 subtests passed in 1.75s**, one existing Starlette/httpx deprecation
warning. Five new offline tests prove missing/uncalibrated gold, mismatched cohorts, profile,
budget, explicit pins and optional SDK never cause fallback/model calls. Positive business
prompt/version/target-model comparisons pass; mixed provenance and changed judges remain blocked.
No server or model campaign left running.
