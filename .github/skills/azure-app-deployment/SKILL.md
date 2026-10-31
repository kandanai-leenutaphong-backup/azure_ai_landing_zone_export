---
name: azure-app-deployment
description: "Use when deploying, redeploying, releasing, migrating or verifying an Azure application: prerequisite-first checks, exact source/image identity, protected rollout, external API/security/browser/persistence acceptance and settled evidence. Composes existing deployment owners; grants no provisioning, access, model, data-write or teardown authority."
---

# Azure Application Deployment

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). Release only the separate new app into
`capps-env-sea`, through the existing WAF and intended DNS name. Parent owns root
`deploy/deploy.sh`, TLS and gateway activation; inspect actual actions before use.
Initial discovery found the gateway stopped and no certificate, per parent evidence.
Only the separately approved secretless browser registration/preauthorization is in scope;
see the customer-service context. Do not grant RBAC, fetch secrets or reuse public-hosting defaults.
Verify the synthetic journey, required correlated logs and system/journey/agent drill-downs;
local checks and imported receipts do not establish live acceptance.
Four-judge quality gates require the central calibration evidence. Optional JSONL batch
integration or a deployed evaluator callable does not substitute for real human labels and
measured kappa > 0.7; preserve `uncalibrated` until those requirements are met.

Release the exact checked application through its existing deployment owner, verify the
protected result, and return bounded evidence. Use for initial deployment, redeployment,
migration and release verification. Guidance only: installation, discovery and loading start
no process, register no MCP server, and grant no execution or publication permission.

## Owners And Boundaries

- This skill owns end-to-end release sequencing and evidence, not an infrastructure engine.
- [Azure CLI infrastructure management](../azure-cli-infra-management/SKILL.md) owns target,
  resource lifecycle and ownership checks; its [application lifecycle playbook](../azure-cli-infra-management/references/application-lifecycle.md)
  covers migration and separately authorized retirement.
- [Container Apps deployment](../deploy-container-apps/SKILL.md) owns ACA/ACR mechanics.
  Its examples are not approved target configuration: do not inherit replica counts, public
  health exemptions, role grants, policy exemptions or ingress changes without authority.
- Imported `libraries/entra-auth` and `libraries/signed-dev-access` guidance is absent here.
  The project context owns reuse of existing Entra registration and per-project `oid`
  authorization; no signed-caller library is required or supplied.
- [Frontend implementation](../frontend-implementation/SKILL.md) owns browser interaction
  and responsive checks. The application's service owns acceptance and persistence semantics.

Reuse the approved scope and decisions already supplied. Escalate only missing material
authority or changed acceptance, targets or protected boundaries; do not request the same
permission at every step. A release request is not authority to provision services, grant
roles, change registrations/policy, fetch credentials, invoke models, ingest data or tear down.
Command availability is not execution permission. Keep one writer per source path/resource.

## Quick Path

Use existing runbook/task records for the fields in the optional [task card](./references/template.md).
No new form, ledger or mandatory artifact is needed when those facts already exist.

1. Resolve actual app, build and deployment entrypoints. Establish task authority, target,
   prerequisites, accepted artifact identities, protected fields and permitted verification.
2. Run focused local checks and the real production build with the verified toolchain.
3. Archive an allowlisted, secret-free source manifest with digests; verify build inputs.
4. Build and read back immutable image identity through the existing deployment entrypoint.
5. Roll out with protection and availability preserved; require the accepted image/revision ready.
6. Verify actual external API, security, browser and persistence behavior within authority.
7. Read back final state and inventory deltas; settle owned processes and return results/gaps.

Use the consuming project's `deploy/deploy.sh`, documented sequence and non-secret target
configuration. Inspect its actual help and action semantics; this skill supplies no turnkey
command names or target values. Keep repeatable missing steps with that owner, only within
authorized code scope. Do not create a generic deployment runner or another wrapper stack.

## Prerequisites Before Expensive Work

- Resolve real source roots, manifests, lockfiles, Dockerfiles, nested build inputs, test
  commands, evidence recorder and deployment configuration. Old paths/runbooks are leads,
  not proof. Confirm working directory and path-dependent packaging behavior.
- Record current interpreter executable/version, dependency versions AND actual import origins.
  Check source versus installed-package resolution and namespace-package paths; a package
  version installed elsewhere does not prove what this interpreter imports. Verify Node,
  package manager, compiler, Azure CLI/extensions and browser tooling needed by the task.
- Use existing approved interpreter/dependencies. Missing or mismatched prerequisites stop the
  affected step with an exact remedy; no silent installation, environment creation/activation,
  dependency-source editing, credential retrieval or implicit package-manager download.
- Bind explicit tenant, subscription, cloud, region and full resource IDs to current approved
  configuration. Read actual account, target ownership, locks, relevant policy and permissions
  through authorized non-secret projections. A login or reported role is not effective authority.
  Do not switch a shared CLI context under another writer; follow the target owner's procedure.
- Confirm artifact/evidence locations are writable, confined and suitable for retention, and
  required source/configuration/authority pins resolve before a build or cloud mutation.
  Inspect current changes; retain user/concurrent edits and never guess source from Git HEAD.
- Identify billable build/test actions, bounds, recovery and who owns pending work. A named
  `verify` action may write versions/profiles, invoke models or retain fixtures. Declare those
  writes, costs, retention and cleanup authority separately from read-only status checks.

Task-specific authority must be versioned separately from historical experiment pins and
provenance. A manual release neither inherits nor rewrites an old experiment's scope. Require
current task/source/target references; no skip-pin option or hardcoded dated allowlist. Digests
prove integrity, not permission. Runner implementations must refuse traversal, foreign evidence
roots and symlink escapes for receipts, archives and receipt-referenced inputs; test refusals.
No constitution or candidate pin is required for standalone deployment unless its actual owner
requires one. Unknown facts remain unknown, not invented gate values.

## Artifact And Protected Rollout

1. Run the smallest checks covering the change, including matching negative tests for touched
   auth, ownership or integrity, then the production build including nested/static staging.
   A development preview is not production-build evidence. Record warnings and failures.
2. Freeze the exact checked source/configuration and relevant lockfiles. Archive only reviewed
   allowlisted inputs and required build output; exclude credentials, private histories,
   receipts, environments, installed dependencies and unrelated state. Verify archive members,
   source-to-member mapping and digests. Inspect actual build context and Docker `COPY` paths;
   `.gitignore` alone does not control upload. Keep source changes distinguishable from outputs.
3. Use the existing authorized image builder. Record build attempt, source/archive digests,
   dependency/base-image identities and immutable image digest. A unique tag is useful, but
   tag text alone is not immutable identity. Read back the image actually submitted.
4. Apply only the approved mutation. Preserve auth, identity, registry references, secrets,
   scale, callbacks, traffic and other protected fields unless explicitly in scope. Private-first
   rollout is one strategy, not mandatory downtime: retain the protected serving revision for
   zero-downtime services and use their established staged/canary/slot procedure. Never expose
   a placeholder or new image before its required protection is effective.
5. Read back protected fields semantically against accepted prestate and intended changes.
   Document normalization per provider/API/field; never strip arbitrary differences. Concrete
   ACA example: an added `value: ""` alongside the same nonempty `secretRef` is equivalent for
   that environment entry. A changed reference or nonempty value still fails. This exception
   does not apply to other fields/providers. Keep sanitized actual observations for diagnosis.
6. Require ready state for the accepted revision AND immutable image, with intended traffic.
   For ACA, latest/ready mismatch blocks release acceptance; a successful update or an older
   healthy revision is insufficient. Use bounded provider waiters or fresh state-based checks,
   not a blind fixed sleep or retry-all loop. Preserve protected service while readiness settles.

A runner/source repair after packaging requires affected local checks, new archive/image and
fresh acceptance for changed bytes. Do not attribute an old image's pass to edited source.

## Security And External Acceptance

Human tenant-scoped sign-in stays fail closed. Use the project's supplied registration reuse
and authorization contract, not an imported signed-access implementation. Workload identity controls outbound access and
does not authenticate users. An authorized signed-agent caller is separate from the human and
uses its own credential; enable it only when needed and authorized. Both paths reach the same
explicit authorization rule. Do not fetch private key/token/secret bytes into evidence or logs.

Preserve signed method, raw path/query, body bytes and signature headers through every proxy.
Verify this on the real external route. Replay defense must cover actual replicas, overlapping
revisions and restarts; use a shared durable replay store when that topology requires it.
One replica per revision does not prove distributed replay safety. No auth bypass, broad grant,
public-health exemption or policy relaxation is an acceptance shortcut.

| Check | Required Observation And Limit |
| --- | --- |
| Revision/configuration | Accepted image, ready revision, actual protected fields, intended traffic and HTTPS; HTTP 200 alone is insufficient. |
| API and ownership | Real permitted operation succeeds; anonymous/foreign owner and relevant forged, expired, tampered or replayed requests refuse. Retain distinct response semantics. |
| Persistence/concurrency | Read back authorized writes through the owning contract; verify stale-write/CAS/conflict refusals where applicable. Test relevant shared session/replay state without unapproved writes. |
| Human sign-in | Complete approved interactive sign-in/callback/session journey when in scope; redirect or signed-agent acceptance does not prove human sign-in/consent. Otherwise mark not verified. |
| Browser | Operate actual deployed controls/routes/assets at affected desktop/mobile sizes; inspect results, focus, overflow and errors. Screenshots support observations, not merely DOM presence. |
| Data operations | Report list, count, read and schema access separately. A schema `provider_denied` can coexist with successful count/read; no implied grant to repair it. |
| Domain coverage | Name actual fixtures/scenarios and mutations. Smoke is not full-data acceptance or real-incident effectiveness; source text is not loaded behavior or measured improvement. |

Read back final acceptance outputs, not just command exits. A signed browser walk covers that
caller path only. Distinguish current source, locally tested, deployed and runtime-loaded versions.
For agent/skill behavior, a file edit does not reconfigure an existing session: fresh invocation
and loaded definition identity are needed for that claim. Later drift invalidates only affected
current claims; retain earlier passes with their exact versions and do not reverse concurrent edits.

## Failure And Recovery

| Class | Response |
| --- | --- |
| Prerequisite/path/version mismatch | Resolve actual owner, interpreter/import origin or configuration. Rerun affected local gate; do not silently install or weaken pins. |
| Authority or provider denial | Preserve scoped error and successful operation coverage. Diagnose policy/access separately; stop blocked mutation, request only missing material authority. No broader grants. |
| Readiness/handover | Read accepted image/revision/traffic again within bounded wait policy. Keep protection; do not probe/reopen a mismatched revision as accepted. |
| Application regression | Preserve sanitized diagnostics and failed receipt. Repair within scope, rebuild affected artifact and rerun relevant checks before release. |
| Unknown postmutation outcome | Inspect actual state, inventory and operation status before resubmitting. Timeout is neither proof of absence nor permission for destructive recovery. |

Retry only after diagnosis supports a bounded relevant retry within existing authority. An
unchanged retry passing does not explain the original failure; preserve unknown cause and
missing intermediate observations. Keep failed/cancelled receipts immutable. Use only the
approved exposure/traffic recovery; a snapshot is not verified rollback. Restore, purge, fixture
cleanup, old-image removal and retirement require their own authority. Preserve retained state
and resource inventory IDs/deltas, never a remembered fixed expected count.

## Evidence And Settled Return

Reuse the existing recorder and permitted evidence location. Capture sanitized, allowlisted
outputs rather than raw CLI/environment/credential dumps. Retain command and attempt IDs,
exit/result, UTC observations and measured monotonic duration. Attribute parent/child spans
and nested phases without double-counting; unmeasured tool overhead/cost remains unknown.
Do not fabricate a whole-task total from partial or overlapping intervals.

Record task authority version, source/archive/image/configuration and relevant loaded-version
digests, actual field readbacks, inventory deltas, check scope, failed attempts, retention and
gaps. Read evidence back; a digest without retained retrievable bytes is not an archive.
Keep private host records with their owner, not in this portable skill or its package.

Return compactly: outcome; URL and accepted revision/image; checks and exact scope; gaps;
resource/process/worker settlement; smallest next decision. Join owned work and identify pending
provider operations; do not stop unrelated sessions. Update owning runbook/current-state docs
only where facts changed. A deployment pass is neither domain effectiveness nor optimization
improvement. Installation and documentation validation prove neither live behavior nor access.