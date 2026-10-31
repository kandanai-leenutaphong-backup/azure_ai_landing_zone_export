# Agent Optimization

Canonical `agent_optimization` runtime and `@agentcraft/agent-optimization` replay UI.
Immutable generations, frozen cohorts, bounded evidence tools, owner-checked results,
and completed-run manifest recovery. No model SDK or second agent loop lives here.

## Install And Use

Python 3.12+, distribution `agent-optimization==0.1.0a1`. Install with its declared
`situation-detector`, `copilot-terminal-runtime>=0.2.0,<0.3`, and `recoverable-jobs`
dependencies. Optional `[execution]` selects `llm-interface`; the host supplies the
predictor using that public API. [Workspace setup](../../../libraries/README.md#installation) owns source
enrollment; published metadata contains no unresolved local paths. Releases are not claimed published.

```bash
python examples/offline.py
python -m pytest tests -q -p no:cacheprovider
node --test tests/test_continue_campaign.mjs
npm run typecheck
npm run build
npm run test:replay
```

[Offline example](examples/offline.py) creates only a temporary synthetic experiment,
reads its completed result, and proves another caller is denied. It calls no model.
For retained process details read the [runtime guide](src/agent_optimization/README.md)
and [process contract](src/agent_optimization/PROCESS.md).

## Public Surface

| Outcome | Public API | Bounds And Authority |
| --- | --- | --- |
| Generations and cohorts | `OptimizationProfile`, `OptimizationService` | Host dataset, root, identity and authorization; immutable configuration receipts |
| Evidence | `SQLiteReader`, `PythonToolRunner`, `QueryDenied`, `QueryTimeout` | Trusted construction-time table policy; requests only narrow; labels never readable |
| Measurement and replay | `GradeEvaluator`, `score`, `audit_results`, `measure_run` | Host predictor; evaluator-only expected labels; failures remain in denominator |
| Completed output recovery | `run_recovery`, `RunSaveError` | Public `workrecovery` staging/commit/read-back; no automatic re-evaluation |
| Native authoring | `OptimizationTerminal`, `HELPER` | Public `copilot_terminal`; host launch policy and private workspace |
| UI | `OptimizationWorkspace`, `RunReplay`, `OptimizationApiProvider`, `createOptimizationApi` | npm root export; `./types` and `./styles`; host HTTP/auth adapter |

```tsx
import { OptimizationApiProvider, OptimizationWorkspace, createOptimizationApi } from "@agentcraft/agent-optimization";
import "@agentcraft/agent-optimization/styles";
```

UI uses `copilot-terminal` and `@agentcraft/source-code` public exports, never app
aliases. Existing UI is retained, not redesigned. Host styling and authenticated
API integration still require the consuming application's browser acceptance.
The [typed synthetic replay fixture](examples/replay/main.tsx) uses public exports only.
Its Playwright check covers stage switching, source rendering, close and desktop/mobile
geometry. The source-code package exports built ESM and declarations, not a TSX source alias.

## State And Limits

Host configurations, datasets, checkpoints and `.local` records are not migration
inputs. Existing records remain readable; implementation/skill digest mismatches can
refuse new measurement. Do not rewrite historical pins to manufacture compatibility.
No campaign, inference, cloud action, role grant or package publication is implied.

Read [CONTRACT.md](CONTRACT.md) for lifecycle, failures, recovery and F1-F8 gaps;
[MIGRATION.md](MIGRATION.md) for imports and retirement; [PROVENANCE.md](PROVENANCE.md)
for notices. [RESEARCH.md](RESEARCH.md), [EVALUATIONS.md](EVALUATIONS.md),
[OPTIMIZATION.md](OPTIMIZATION.md), [OBSERVABILITY.md](OBSERVABILITY.md), and
[API_AND_OPERATIONS.md](API_AND_OPERATIONS.md) are research, not implemented SDK support.