---
name: azure-cli-infra-management
description: "Use when Azure infrastructure must be inspected, created, verified or retired through Azure CLI: explicit tenant/subscription selection, resource groups, scoped app deployment, protected rollout, non-secret target configuration, ownership, inventory-confirmed teardown and read-back evidence. Plans and reads by default; resource mutation needs explicit scoped authorization. Not RBAC grants, secret retrieval or automatic data-plane writes."
---

# Azure CLI Infrastructure Management

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). The supplied grant covers app deployment
and its DNS/WAF route. The separately approved secretless browser registration and native
Hosted Agent extension are scoped in the customer-service context. RBAC, secret retrieval,
teardown and unrelated infrastructure remain excluded. Parent owns TLS, gateway activation and root `deploy/`.
Use non-secret resource read-back with exact subscription IDs; supplied DNS ownership and
stopped-gateway observations are not this skill's independent live verification.

Use the existing Azure CLI identity to perform one authorized infrastructure change,
then read back the exact resource state. A logged-in account is a credential context,
not permission to create services, expand scope, change access or spend money.

## Scope

This skill owns the operator procedure, not a second infrastructure implementation.
The consuming repository owns its target configuration and deployment entry point.

- Resource lifecycle and control-plane inspection belong here.
- Application rollout uses this skill's target, ownership and evidence procedure; Container Apps
  hosting details belong to [deploy-container-apps](../deploy-container-apps/SKILL.md).
- Role assignments and data-plane grants are separate authorization decisions.
  Imported `libraries/entra-auth` is absent here; this project's grant excludes RBAC changes.
- Application data CRUD belongs to its owning contract. Imported
  `libraries/azure-data-connectors` is absent, not an available required dependency.
- Azure resources are not automatically billable merely because they exist, but an empty
  resource group does not provision or price its future contents. Check each service/SKU.

## Start With A Bounded Change

Name the requested outcome, tenant, subscription, cloud, region, resource names, owner,
mutation set and verification before changing anything. When the user requests a group
for future tests, creation of the group does not authorize service provisioning or tests.

Use the host's single `deploy/deploy.sh` entry point. Keep scripts, infrastructure,
non-secret environment targets, operator sequence and dated evidence together in `deploy/`.
Do not leave required steps only in a terminal transcript or inside this skill's examples.

Default action is plan/inspect. Creation, updates and teardown require separate deliberate
actions tied to the target under review. Unknown targets and unrecognized options fail closed.

## Preflight

1. Check required tools and the current CLI account without printing tokens:
   `az account show --query '{subscriptionId:id,tenantId:tenantId,state:state,cloud:environmentName}'`.
2. Require active tenant, subscription and cloud to equal the committed target. Do not silently
   switch the shared CLI account while another agent might be using it. If mismatched, stop
   with the exact `az account set --subscription ...` or tenant login step for the operator.
3. Use an explicit subscription argument on commands that support it, even after account
   verification. `az account list-locations` uses the active account and may not accept that
   argument; verify supported syntax with the installed command's help.
4. Check location, name collisions, ownership and reported permissions. A permission listing
   is evidence, not a complete effective-access proof: deny assignments, conditions, Azure
   Policy, resource locks, quota and service availability can still reject a mutation.
5. Refuse unknown/secret-shaped configuration fields and literal credentials. Targets and
   identifiers may be committed; tokens, keys, connection strings and secret values may not.
6. Confirm only the requested mutation set. Provider registration, role grants, enabling
   public access, changing policy and creating paid services are not implicit prerequisites.

For a resource group, location describes the group's metadata home; it does not guarantee
that a future Search, Cosmos or other service supports that region, tier or capacity.

## Application Lifecycle

Use [the application lifecycle playbook](references/application-lifecycle.md) when moving an
existing app, deploying it into a new group, releasing another version, or retiring its old host.
It generalizes observed deployment failures and successful read-back, not a new deployment engine.

1. Discover the actual source, deployed image, owner and target; treat old runbooks as leads.
2. Preserve portable source and non-secret deployment facts; prove the local production build.
3. Authorize the exact hosting, exposure and identity changes. A new RG is not an app deployment.
4. Validate tooling, configuration, IaC and provider preflight before provisioning.
5. Build a versioned artifact, deploy privately, configure the approved auth contract, read it back.
6. Expose only the ready protected app; verify real content, negative access paths and browser flow.
7. Record the URL, image/revision, inventory, observations and limitations in the host runbook.
8. Retire old resources only under separate exact-scope authorization; verify absence independently.

Do not generalize a workaround into a default. In particular, ID-token-only implicit sign-in is
not equivalent to a confidential-client flow; changing it requires an explicit auth decision.
One replica per revision is not a distributed replay defense. Read the playbook's failure table
before carrying either assumption into another deployment.

## Apply And Read Back

- Check whether the named resource already exists. Matching owned state is a no-op.
- Do not silently adopt, retag, overwrite or delete an existing resource owned elsewhere.
- Keep one writer per target. A preflight GET followed by PUT is not an atomic reservation.
- Submit only the frozen mutation through the documented deployment entry point.
- Read the resource again with an independent command. Verify ID, location, lifecycle state
  and required ownership tags, and enumerate the actual resource-group contents.
- Record command identity, UTC observation time, exact resource ID and relevant observed
  fields in the host's deployment record. Store no tokens, request credentials or data payloads.
- A successful CLI exit or `Succeeded` property alone proves neither data-plane reachability,
  caller authorization, correct application behavior nor data persistence.
- A timed-out mutation may have applied. Inspect before retrying; never report it as absent
  or issue a destructive recovery merely because the command did not return cleanly.

Idempotent creation must not imply idempotent updates to unrelated fields. A repeat run
should verify an already owned resource and avoid rewriting it without a requested change.

## Live CRUD Environments

Use a dedicated, clearly tagged resource group, isolated from production. Commit non-secret
targets in `deploy/env/`; the authoritative resource record belongs to the deploy runbook.
The test suite should refer to that record, not guess a subscription from its environment.

- Start with supported adapters and their real supported operations. A standard `create`
  method can correctly return `unsupported`; do not fake an insert-if-absent guarantee.
- Provision service instances, grant data-plane access and load samples only after their
  names, SKUs, region, cost limits, lifetime and identity plan have been authorized.
- Use synthetic, deterministic fixtures with per-run IDs and owned partitions/indexes.
  Never copy customer datasets, application state or developer credential files into tests.
- Exercise positive behavior plus conflict, permission, partition, partial-result and
  unsupported-guarantee cases. Denials must not be implemented by disabling real auth.
- Drive data operations through the actual library, and read back what persisted. Azure CLI
  is for infrastructure setup, not a substitute implementation of the library being tested.
- Keep live tests opt-in and outside default offline discovery. A future live suite should
  declare its exact grants, target and fixture cleanup, and emit payload-free result evidence.
- E2E coverage requires a live service. An empty group establishes ownership and a target,
  not a working connector or a test pass.

## Teardown

Teardown is separately authorized. Verify exact resource ID and owner before deleting.
List current contents and locks; stop on unfamiliar or unexpected resources.

A runner created only for an empty resource group should refuse non-empty groups. Do not
turn it into recursive workload deletion later without a reviewed ownership manifest.
After deletion, read back absence. Preserve uncertainty when the provider cannot answer.
Deleting a group does not revoke subscription/tenant-wide roles granted elsewhere.

For an explicitly authorized non-empty group retirement, freeze the exact resource inventory,
recheck it and ownership/locks immediately before deletion, then use a bounded native waiter.
An inventory digest detects drift; it is not permission or a lock against concurrent writes.
Keep the empty-group-only runner's refusal intact. The playbook separates scoped retirement,
provider-managed cleanup, tenant-level identities and retained/soft-deleted data.

## Where The Record Lives

The host's deployment runbook is the live target authority. This skill carries the reusable
procedure and bounded adoption notes, not copied subscription/tenant values that drift.
Link a dated application record when using this procedure in a repository; distinguish
created infrastructure from proposed services and unexecuted live tests.

### Applied In This Checkout

The imported source described 2026-09-14 connector-test and 2026-09-16 group/application
changes under root `deploy/README.md`. Neither those summaries nor their three original
receipts were present at initial inspection. They are unavailable imported history, not
local deployment evidence. Parent is creating a new root `deploy/` for this app; do not
attribute imported history to that new runbook.

Use the host's authorized `verify` command before relying on any target. Service/SKU/access
plans, data tests, sign-in and teardown keep separate authority. For another repository,
use its own deployment owner; do not copy these historical targets, identity choices or
configuration. Missing evidence must remain explicit, never replaced with invented receipts.

## Validation

Verify frontmatter and native catalogue registration after adding the skill. For any host
deployment runner, use isolated fake CLI responses to test target mismatch, collisions,
denied permissions, idempotence and non-empty teardown refusal before an authorized cloud
mutation. Offline evidence does not prove live access. This skill registers no MCP server
and creates no login, credential, resource or grant merely by being loaded.

For an application runner, also test inventory drift, callback preservation, private-first
ingress, unsafe target/URL refusal, missing-credential refusal and failed-verification closure.
Then verify the actual release through its public boundary; a mocked deployment is not a live pass.