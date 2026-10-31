# Application Deployment And Retirement

General process: discover -> preserve -> bound -> validate -> deploy privately -> configure
approved access -> expose -> verify -> record. Retirement is a separately authorized operation,
not an automatic final step. Use the consuming project's existing deployment owner and scripts.
This guide defines no new library, cloud target, credential, grant or deployment permission.

## Ownership And Scope

| Concern | Owner | Required Decision |
| --- | --- | --- |
| Target, resources, lifecycle and receipts | Host `deploy/`, following this skill | Exact tenant/subscription/cloud, resource IDs, mutation set and read-back |
| Container Apps hosting and image pulls | [deploy-container-apps](../../deploy-container-apps/SKILL.md) | Existing versus new environment, registry, identity, SKU and rollout sequence |
| Human auth, workload identity and grants | [azure-access-management](../../../../libraries/entra-auth/docs/skills/azure-access-management.md) | Allowed callers, token/session contract, resource-scoped roles and separate authority |
| Agent piloting | [signed-dev-access](../../../../libraries/signed-dev-access/docs/skills/signed-dev-access.md) | Existing authorized agent identity, no human credential reuse or bypass |
| Local/browser behavior | [frontend-implementation](../../frontend-implementation/SKILL.md) | Real routes, controls, assets, responsive geometry and observable results |

An app deployed "by itself" usually means one application plus its necessary hosting resources.
Enumerate those resources before creation. A registry, managed environment and pull identity may
be necessary; a database, model endpoint, second demo service or logging workspace is not implied.
Static demo assets inside the same image do not require a second backend.

Keep these operations distinct: importing source, creating an empty group, provisioning services,
changing authentication, granting access, publishing an image, and deleting old resources.
Existing CLI access establishes credentials, not authority for all of them. A plan names any
billable resources, lifetime, exposure and identity changes; unresolved authority blocks that step.

## 1. Discover And Preserve

- Start from the named app manifest, build script and deployment record. Follow only dependencies
  needed to reproduce its actual build and runtime; do not copy an entire adjacent platform.
- Verify the active CLI tenant, subscription and cloud. Query resource names/IDs and image/revision
  directly with non-secret projections; a remembered RG name or an old image tag is only a lead.
- Inspect app-specific deployment files, nested build inputs, symlinks, generated output, local
  configuration and secret candidates before transfer. Catch both `.env.*` and files ending in
  `.env`; ignored files can still be copied or uploaded to a build service.
- Retain the original source until the new copy is verified unless removal was separately
  requested. Transfer source, lockfiles, assets, tests and non-secret deployment facts; exclude
  credentials, local agent configuration, installed dependencies and regenerable build caches.
- Preserve dataset/provenance artifacts even when a broad ignore rule would hide their directory.
  Check that retained inputs and target configuration are actually trackable by Git.
- Update path-dependent commands and metadata. Compare untouched source/assets by digest; record
  deliberate adaptations and verify generated copies using their existing synchronization check.

A source backup is not a backup of databases, registry images, auth secrets, platform configuration
or user data. Say exactly what was preserved before deleting the old environment.

## 2. Establish A Local Release Artifact

Use the locked dependency install and real production build, including nested/static demo staging
and post-build processing. Do not substitute a development server for a production-output check.
Confirm the server's dependency manifest and every Docker `COPY` input exists in the new context.

Check installed tool versions and `--help` before trusting inherited commands. A documented preview
flag may no longer exist. Reuse an already declared preview server with loopback binding when
appropriate; do not edit a dependency's installed source or expose confidential preview content.

Inspect `.dockerignore` separately from `.gitignore`. Exclude local environments, credential files,
unneeded source/configuration and old receipts, while keeping generated site and demo output.
Do not assume Git exclusion prevents upload, or that a Git-ignore parser proves Docker semantics.
Validate using the actual build-context implementation and container build.

Operate a representative workflow locally and keep the matching negative checks for access or
integrity. Existing build/test warnings are not new failures; record relevant limits without an
unrequested cleanup pass. A local pass is prerequisite evidence, not proof of a cloud deployment.

## 3. Bound And Validate The Cloud Change

Store non-secret target data in `deploy/env/`; parse a strict schema rather than executing sourced
configuration. Refuse duplicate/unknown fields, ambiguous IDs, shell syntax and credential values.
Keep one documented operator entry point, such as `deploy/deploy.sh`, with plan/apply/verify and
an appropriately scoped teardown or explicit refusal. Extend existing owners, not another wrapper
stack. The skill does not need a copy of the host's Python runner or Bicep template.

Before provisioning:

1. Compare active account with target; use explicit subscription selection on supported commands.
2. Check names, location/SKU availability, provider registration, actual ownership and locks.
3. Inspect reported permissions without treating them as proof against policy/deny/conditional rules.
4. Name required app-registration changes and exact resource-scoped grants. Do not broaden operator
   permissions or registration audience to make a deployment succeed.
5. Compile IaC locally, then run provider validation or what-if for that exact target. Neither
   compiler success nor preview guarantees apply-time policy, quota, image pull or application health.
6. Confirm the mutation set. Preserve pre-existing unrelated resources, tags, settings and callbacks.

Matching owned creation is a no-op. A repeated release may intentionally publish a new unique image
and revision; describe it as a release, not a mutation-free idempotent check. Callback addition should
preserve other callbacks and become a no-op when already present. Do not rotate secrets on every run.

## 4. Resolve Authentication Before Exposure

Workload managed identity authenticates outbound resource access, not the human reading the app.
Choose supported native sign-in and explicit application authorization with the access owner.
Reuse the approved contract; do not silently broaden tenants, audiences, callers or sessions.

Credential metadata cannot recover a deleted client-secret value. If the old platform held the only
copy, stop for an approved credential/Key Vault reference or evaluate a supported identity-based
alternative. Do not fetch secrets into shell variables, command arguments, repository files or logs.
Changing from code/hybrid flow to ID-token-only implicit flow is a material auth change, not simply
"secretless deployment." Obtain explicit approval before changing that contract; a comment or
runbook caveat is not approval. Microsoft discourages implicit flow where safer alternatives work.

For a retained registration, append only the approved new callback and read it back. Preserve its
other callbacks, audience, token settings and API permissions. Registration changes, consent and
grants are separate authority decisions from creating the Container App.

Native platform enforcement is the default for a private frontend. An approved custom signed path
may instead require a default-deny application gate on every content/asset/API route. `AllowAnonymous`
only forwards the request to that gate; it is not authentication. Prove the platform strips forged
principal headers and that no public origin bypasses it. Never disable auth to validate deployment.

Reuse an existing authorized agent key only through its signing client; keep private bytes and
session/signature values out of receipts and logs. Creating a new key or enabling another caller
needs explicit authority. The observed replay cache is process-local. A replica limit of one
applies per revision and does not share replay state across restarts or overlapping revisions.
Choose and verify the supported replay model.

## 5. Deploy Privately, Then Release

1. Provision only the approved hosting resources. Record IDs and owner tags; prefer an existing
   suitable environment when allowed. Separate application count from required infrastructure count.
2. Build a uniquely tagged artifact through the existing image-build mechanism. Keep local source
   out of a public registry and keep image-pull identity grants narrow. Read back the actual role,
   principal and registry scope; successful identity creation does not establish pull access.
3. Deploy the real image with external ingress closed or private. A placeholder image is not a
   safe substitute for protecting confidential content during first rollout.
4. Configure the approved tenant-pinned auth and callback. Read back the actual configuration,
   HTTPS setting, image, ready revision, identity/pull reference, scale and registry access controls.
5. Open the intended ingress only after private readiness and auth configuration checks pass.
   Immediately exercise the real edge. Predetermine how failed verification closes exposure without
   exposing content or destroying a previously working revision; record rollback uncertainty.

Avoid rewriting unrelated defaults through convenience CLI handlers. For a one-field adjustment,
use the existing owner's narrow declarative update or precise API request, then compare protected
before/after fields. Do not relax policy, access controls or registry authentication on failure.

## 6. Verify The Deployed Result

| Evidence | What It Establishes | What It Does Not Establish |
| --- | --- | --- |
| ARM resource and revision read-back | Exact target, deployed image/configuration and ready state | Working content, data-plane access or user authorization |
| Health endpoint | Process reachable through the intended route | Protected routes, dependencies or usable UI |
| Authenticated content digest/read-back | Actual response matches the intended artifact or stored result | Exhaustive source/image equivalence or all workflows |
| Anonymous, forged, expired, tampered and replay refusals | The tested negative paths fail closed at the deployed boundary | Untested replicas, restart windows, other tenants or cookie lifecycles |
| Native sign-in redirect with tenant/audience/callback/state/nonce | Correct redirect and entry into the identity flow | Completed sign-in, consent, callback/session success, logout or revocation |
| Browser interaction, geometry and screenshots | Tested controls, routes, assets and responsive behavior | Every user/device or untested persistence |

Test anonymously fetched documents, assets and unknown routes, not only the home page. Pair the
expected positive caller with the matching unauthorized caller. A redirect followed to login HTML
can look like HTTP 200; distinguish it from successful API/content access. Do not save tokens in a
response dump to prove the result. Read back persisted results when the app changes state.

Operate the deployed app, not merely its local preview: open navigation, follow a representative
content route, load assets/documents and return. Use the existing browser harness at affected
desktop/mobile widths. Preserve any known inherited layout defects rather than calling them fixed.
Finish with independent verify through the host entry point, then give the actual HTTPS URL and
required sign-in context. Explicitly label any unperformed human sign-in/consent acceptance.

## 7. Retire An Old Group Separately

An empty-group creation tool must keep refusing non-empty teardown. When the operator explicitly
authorizes an entire non-empty group, use a narrowly owned retirement action with this sequence:

1. Confirm exact full group ID, tenant/subscription, current owner and scope, including service data.
   Inventory actual resources, child resources, relevant external dependencies and inherited locks.
2. Preserve only the requested source/configuration/backups. Disclose data/image loss and retained
   backups; do not invent a backup guarantee or silently purge provider retention.
3. Freeze a deterministic inventory with a digest and dated receipt. Re-read ownership, contents and
   locks immediately before deletion. Changed scope requires review, not a freshly blessed checksum.
   Digests detect drift; they neither grant authority nor eliminate the final concurrent-write race.
4. Submit the exact group deletion through the host entry point. Native group deletion removes
   contained workloads; no generic scale-to-zero sequence works for every service. Use a separately
   authorized service-specific stop/drain only when its data or availability contract requires it.
5. Use a bounded native waiter, such as `az group wait --deleted`, with explicit target selection.
   A backgrounded terminal or accepted deletion request is pending, not complete and not a reason
   to repeat deletion. Wait for its final result; on timeout inspect before any retry.
6. Independently verify group absence and remaining resource inventory. Check provider-managed
   infrastructure cleanup without directly deleting outside scope. Escalate leftovers instead of
   guessing that their names authorize removal.
7. Keep tenant-level registrations, other-scope role assignments and private operator keys separate.
   Resource absence is not revocation of those identities or secure erasure of provider backups.
8. Preserve historical receipts, update current-state docs, and disable retired deployment targets
   so an old command cannot recreate the removed host. A future redeployment is a new action.

## Failure Lessons

| Observed Pattern | Generalizable Response |
| --- | --- |
| CLI reports failure and no ARM deployment record exists | Inspect sanitized original error and rerun non-mutating validation. CLI parsing and provider preflight can both fail before a deployment record exists. |
| Bicep compiles but provider rejects a field | Verify exact API semantics. In the observed Container Apps API, literal logging destination `none` failed; omitting logging configuration passed. Do not assume the same omission/default across services or API versions. |
| Bicep resource name shadows a function | Use an unambiguous name or qualify the built-in, such as `az.environment()`. Compile again before apply. |
| Registry property produces a type warning | Select a supported API schema that declares it; validate with the provider and read back the field. Do not suppress the warning and assume security configuration applied. |
| Build context loses an app route or includes a local env file | Compare source exclusions with exact generated `COPY` inputs, inspect the actual context and rebuild. Git-ignore checks alone are insufficient. |
| Old preview command fails on a now-unsupported flag | Inspect installed CLI help and reuse a declared supported preview mechanism; bind locally. |
| A successful deployment leaves the document unreadable | Test the real response/route and auth callback, not only readiness. A login page or placeholder is not the expected content. |
| RG deletion appears stuck while resources disappear | Keep the native waiter and inspect bounded state on timeout/failure. Do not relaunch deletion or report completion before independent absence. |
| Log output truncates or a wrapper reduces every failure to `command_failed` | Retain a bounded, sanitized provider code/message and immutable failure receipt. Use exact-target read-only diagnostics; never enable token/payload logging as the workaround. |

## Durable Handoff

Keep live facts with the host, not in this reusable skill. The host runbook links non-secret
environment configuration, source/build commands, artifact version, release URL, resources,
identity/authorization decisions, creation/release/retirement sequence and failure recovery.
Update the consuming project's root README only where the operation changes its current state.

Each receipt should name the operation and UTC observation time, target, intended scope, sanitized
commands, artifact tag/digest, actual image/revision, relevant config and before/after inventory,
verification observations, failed/pending steps, remaining resources and explicit limitations.
Use new receipt names; never overwrite failed attempts with a later success. Checkpoint long-running
operations so interruption does not leave only an empty file. A receipt is evidence, not authority.

Report `planned`, `submitted/pending`, `failed/unknown`, or `verified` according to observation.
Zero exit, local tests, an empty RG, a sign-in page and terminal backgrounding each prove different
things. Do not turn any of them into an unqualified application-success claim.

## Evidence Boundary

These lessons derive from the dated host records linked in the parent [skill](../SKILL.md).
Those records describe one observed run and its limitations, not a reference deployment to copy.
No cloud operation is needed to apply this documentation update.

Official references; recheck platform support before applying a configuration:

- [Container Apps authentication](https://learn.microsoft.com/en-us/azure/container-apps/authentication)
- [Microsoft Entra provider and ID-token-only caveat](https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra)
- [App Service identity-backed client assertions](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad#use-a-managed-identity-instead-of-a-secret): service-specific guidance, not proof the same configuration is supported by Container Apps.