# Release Task Card

Optional compact template. Put these fields in the existing task/runbook/recorder; reference
known decisions rather than copying them. Do not create a competing ledger or fill unknowns
with guessed values. This is task-specific authority, not an experiment constitution.

| Field | Fill Or Reference |
| --- | --- |
| Objective | Task ID, requested outcome, app/source owner, release or verification scope. |
| Scope and authority | Current decision/version and permitted operations; tenant, subscription, cloud, region, full target resource IDs; one writer; limits and protected boundaries. Separate provisioning, grants, models/data writes, exposure, restore and cleanup authority. |
| Inputs and prerequisites | Actual source/build/deploy entrypoints, target config, existing interpreter executable/version, dependency versions/import origins, build/browser/CLI tools, credential context without values, owner checks, artifact/evidence paths and pins. |
| Acceptance | Required local gates/production build; accepted source/archive/image/revision; protected field comparisons/normalization; external API/security/browser/persistence cases; authorized verification writes, cost bounds, retention and explicit exclusions. |
| Procedure | Existing `deploy/deploy.sh` actions from actual help/runbook; ordered checks, package/build, protected rollout, readiness, external acceptance and final readback. Commands are project-specific, never invented from this template. |
| Recovery | Failure classification, bounded diagnostic/retry conditions, unknown-side-effect inspection, approved traffic/protection recovery, restore status and separate cleanup decision. Snapshot coverage and rollback verification are distinct. |
| Evidence and versions | Existing recorder/location; command/attempt IDs, UTC, monotonic spans and parent links; source/archive/config/image digests, current/tested/deployed/runtime-loaded identities; sanitized field readbacks, exact inventory IDs/deltas, failures and evidence readback. |
| Result and next decision | Outcome, URL/revision/image, observed checks and their scope, gaps/unknown cost or telemetry, retained writes/resources, settled or pending work, smallest remaining decision. |

## Compact Completion

```text
Outcome: <verified / partial / blocked / pending; scoped objective>
Release: <URL; accepted revision; immutable image digest>
Evidence: <existing receipt references; source/archive/configuration identities>
Checks: <observed local and external checks; caller/data/scenario coverage>
Gaps: <not verified; denials; unresolved failures; current-version drift; unknown costs>
Settlement: <owned processes/provider operations; resource deltas; retained verification writes>
Next decision: <none, or exact missing authority/acceptance decision>
```

Record current, tested, deployed and runtime-loaded versions separately. Preserve earlier
passes with their original identity when current bytes change. Never combine nested command
durations into a fabricated total or relabel a retry pass as a diagnosed cause. Human interactive
sign-in, signed-agent access and domain effectiveness remain separate claims.