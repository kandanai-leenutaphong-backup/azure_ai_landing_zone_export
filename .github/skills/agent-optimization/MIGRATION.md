# Selected Optimization Migration

Portable skill core selected after comparison with the active custom-optimizer component.
Service/evaluation differ only in thread names; portable worker/workflow remove app imports
and use neutral result kind. Portable UI has host-neutral labels. App helper scripts and
strict feedback validation are retained improvements. Component tests overlap the neutral
suite; app-only helper tests move and adopt canonical imports.

| Old Root | Canonical Owner / Disposition |
| --- | --- |
| Skill `python/agent_optimization` | `src/agent_optimization`, `tests`, `frontend` |
| Custom optimizer `app/components/agent_optimization` | Duplicate retired; draft/install/continuation helpers and tests retained here |
| Custom optimizer `app/components/local_query` | Private `src/agent_optimization/_local_query`; public reader/refusal exports |
| Custom optimizer `app/components/copilot_terminal` | Duplicate retired; `copilot-terminal-runtime==0.2.0`, import `copilot_terminal`; npm `copilot-terminal` |
| Skill scripts/tests/metadata and `assets/implementation.zip` | Retired, not copied into another editable source pack |
| Skill notices/manifest/provenance/synthetic ledger | `LICENSE`, `provenance`, `examples/ledger` |
| Existing library research README | `RESEARCH.md`; research topic files and receipts retained |

Exact file-level moves, hashes, retirements, protected entries and counts are generated
in [MIGRATION.json](MIGRATION.json). Temporary rollback copies are not shipped. No
Investigation component roots were present. Existing `.local` records remain untouched.

## Parent Handoff

Only component roots were writable in applications. Required mechanical replacements:

- `app.components.agent_optimization` becomes `agent_optimization`.
- `app.components.agent_optimization.service` monkeypatches become `agent_optimization.service`.
- `app.components.local_query` becomes public `agent_optimization` reader/refusal exports.
- `app.components.copilot_terminal` becomes `copilot_terminal`; PTY patch target becomes
  `copilot_terminal.service.PtySession`.
- `@components/agent_optimization/frontend` becomes `@agentcraft/agent-optimization`;
  explicitly import `@agentcraft/agent-optimization/styles` for built CSS.
- `@components/copilot_terminal/frontend` becomes `copilot-terminal`, with its
  `copilot-terminal/styles` export where styles are explicitly composed.
- Raw `model_predictor(client, request_builder)` is removed. Parent backend owns the
  predictor over `llm_interface`, including its async-to-worker boundary.
- Worker result kind is `optimization_tool_result`, replacing `cybereye_tool_result`.
- Helper installer default is `/api/optimization/terminal`; pass the host's existing
  `/api/cyber/optimization/terminal` explicitly. Installed helpers cannot be retargeted.

Consumers identified for the parent: custom optimizer `frontend/src/main.tsx`,
`app/cybereye/tests/test_joint_optimization.py`, `test_optimization_evaluation.py`,
`test_optimization_service.py`, and `test_optimization_stress.py`. Parent owns those
edits, app metadata/locks/docs, catalogue and MCP. Already migrated backend imports
were not changed. App `artifacts/migration/retired` snapshots are outside this scope.
At final source scan, no old component imports remained in active custom-optimizer
frontend/backend/test sources. Other owners applied those rewrites; their host workflow
results are not inherited here. The mapping above remains the mechanical handoff.

Measured selected skill scope: 65 files / 617,089 bytes to 1 file / 1,167 bytes.
Combined with modular agents: 204 to 2 files; 2,162,950 to 2,368 logical file bytes.
Archives count as file payload bytes, not expanded members or allocated disk blocks.
Build caches and protected deployment state are excluded identically before/after.
This is not a whole-repository reduction or a RAM/disk/latency measurement.

## Acceptance

See [VALIDATION.md](VALIDATION.md) for actual commands/results. Host configurations,
data/checkpoints and `.local` state are not migration inputs. Saved implementation/skill
pins may refuse remeasurement after migration; historical read-back remains supported.
No campaign, model inference, cloud action, role grant or package publication occurred.

## Schema-2 Consolidation

The subsequent bounded optimizer increment removes schema-1 creation and the independent
execution loop in [workflow.py](src/agent_optimization/workflow.py). Historical digest
verification remains read-only; it is not a retained rule engine.

| Old Path | Supported Path |
| --- | --- |
| `rules[].code` defining `run(ctx)` | `configuration.rule_sets[].rules[]` with `query`, `parameters` and `processing.code` defining `process(rows, parameters)` |
| Optimizer iterates and executes schema-1 Python rules | `detect` -> `detect_rulesets` -> public `situation_detector.run_battery` -> host query/processing callbacks |
| Custom Optimizer `BASELINE_DETECTOR` schema-1 definition | [Host profile](../../../template_apps/custom_optimizer/app/cybereye/backend/optimization/profile.py) supplies schema-2 `guide-incident-evidence-v2` |
| Exception text in new case/run diagnostics; configured tool count | Fixed failure codes and attempted evidence-tool callbacks, documented in [CONTRACT.md](CONTRACT.md) |

The host baseline retains `SELECT COUNT(*) AS count FROM evidence`, the `count > 0`
predicate, the same observed-count fact and empty technique list. Schema-2 adds a bounded
case window and summary, and selects the host's strict response schema. This is not a
claim of identical model requests, scores, latency, native usage or billing.

Saved detectors, experiment inputs, results, records, provenance and notices are not
rewritten. Old detector reads still verify their original pins; attempts to execute or
measure them refuse with a read-only notice before callbacks or a new run record. New host
authoring instructions describe schema-2 configuration. No automatic record conversion or
campaign is performed. Earlier migration receipts and their counts remain unchanged.