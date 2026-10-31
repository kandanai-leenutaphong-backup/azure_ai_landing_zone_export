# Selected Optimization Validation

All runtime tests use neutral/synthetic cases and injected collaborators; no live campaign.
Commands run from repository root unless `npm --prefix` selects this package.

| Check | Observed Result |
| --- | --- |
| Final wheel-installed Python suite, Python 3.12.3, `PYTHONPATH` unset | 133 passed outside the checkout |
| Private reader before policy change | 34 passed |
| Public reader with trusted table policy | 50 passed: includes escaped URI paths and non-finite/typed-bound refusal |
| `tests/test_persistence.py` | 8 passed: measured-run read-back/recommit without repeated prediction, conflict, identity and symlink refusal |
| Draft/install helper tests | 45 passed |
| `node --test libraries/agent-optimization/tests/test_continue_campaign.mjs` | 3 passed; no stages executed |
| `python3 libraries/agent-optimization/examples/offline.py` | Synthetic completed read-back, label isolation and owner refusal passed |
| `npm --prefix libraries/agent-optimization run typecheck` | Passed with canonical npm dependency artifacts |
| `npm --prefix libraries/agent-optimization run build` | Vite 7.3.6 ESM/CSS plus TypeScript declarations passed |
| Thin skill frontmatter/link check | Passed |
| Outside-checkout Python 3.12.3 profile | Six local capability wheels installed; eight imports resolve in site-packages under `-I`, no `foundryagent` or app import |
| First installed optimizer artifact | 124 tests and the wheel-installed public example passed with `PYTHONPATH` unset |
| `npm run test:replay` | Passed at 1440x900 and 390x844: stage reads, source viewer, close, measured dialog geometry; screenshots viewed |
| Typed replay example | Public API and CSS exports passed strict TypeScript check |
| Retired source/state integrity | 124 retired paths absent with hash-identical rollback copies; three protected modular deployment-state artifacts unchanged |
| Retained documentation | 67 non-historical local links resolved before final evidence additions |

Native npm dependencies used canonical local `copilot-terminal@0.2.0` and
`@agentcraft/source-code@0.1.0` tarballs. Lucide 0.460.x satisfies source-code's peer;
terminal retains its separately declared Lucide dependency. No forced peer resolution.

Initial app-context test collection failed on `app.components`; canonical relocation
resolved it. Relocated verifier/helper imports and CSS declarations were corrected
after focused failures. Recovery tests exposed the native store-error translation and
Artifact-based `recommit` contract; corrected and rerun.
Replay fixture initially lacked automatic JSX for the source-code dependency; Vite host
configuration was corrected and both viewport checks passed. Public CSS subpath typing
was then corrected and the typed example rerun successfully. An interrupted browser
run was not counted as a pass.

Still unverified: full host workflow after parent rewrites, real sandbox operation
(`bwrap` not found on this machine), live CLI/provider session, model/data/identity,
shared framework descriptors/events/failures and registry availability/publication.
These are gaps, not completion claims. Further observed artifact checks are appended here.

Artifact proof root: `/tmp/agentcraft-selected-artifacts.BiwIbM`.
Final current-source wheel/sdist/npm artifacts: `/tmp/agentcraft-selected-final.hSpHoR/artifacts`.
Final wheels installed with `--no-deps --reinstall`; no dependency fetching during
the 133-test run. The installed public example passed again. All artifact notices,
typing markers, npm export paths and normal dependency requirements were verified.
Exact artifact SHA256 values are recorded in [MIGRATION.json](MIGRATION.json).
Replay screenshots: `/tmp/agent-optimization-replay-cu1sFN/replay-1440.png` and
`replay-390.png`. These are temporary verification outputs, not shipped user records.