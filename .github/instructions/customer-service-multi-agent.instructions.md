---
applyTo: '**'
description: 'Customer-service multi-agent scope, Azure targets, telemetry, evaluation and checkout limitations.'
---

# Customer-service multi-agent project

## Authority and scope

- Read [ARCHITECTURE.md](../../ARCHITECTURE.md), the repository architecture authority,
  and the [work contract](work-contract.instructions.md) before placement or deployment work.
  There is no `ARCHITECTURE_OVERVIEW.md`. Imported references to it mean `ARCHITECTURE.md` here.
- The app owns `applications/customer-service-multi-agent/`, separate from
  `applications/thai-surname-search/`. Current source, deployed versions and limitations
  belong to its README and `deploy/README.md`; reverify those before changing status.
- Build a synthetic customer-issue workflow with multi-agent orchestration. Keep scenario
  fixtures explicitly synthetic; do not import real customer records or reuse another app's state.
- Preserve existing dirty files and other applications. No unrelated restructuring, new
  tracking Markdown, commits or changes to the reserved landing-zone summary.
- Current user scope supersedes earlier UI requirements: one chat window and Logout,
  automatic Microsoft sign-in rather than a sign-in button. Keep simulation/metrics
  callable APIs but remove their dashboard controls from the primary UI. GitHub pushes
  and further CI/CD implementation are postponed.

## Supplied Azure target, not live verification

| Boundary | User-specified target |
| --- | --- |
| Application compute | SEA internal Container Apps environment `capps-env-sea` |
| Entry route | Existing hub Application Gateway WAF `agw-thai-search-sea` |
| Intended URL | `https://customer-service-multi-agent.azuremew-domain.org` |
| Model/agent service | Private West US 3 Foundry project |
| Project endpoint | `https://foundry-agent-wus3jbm3vfsrmekbg.services.ai.azure.com/api/projects/agent-project` |

App deployment, DNS and the app's gateway route are authorized by the supplied brief.
This documentation sweep performs none of them. Discover exact subscription/resource IDs,
route/DNS names, image, identity and current protected configuration before mutation.
Preserve private Foundry access, internal hosting, existing WAF routes and other workloads.
Do not substitute a public endpoint, a different region or a fresh hosting environment.

Secret retrieval, RBAC grants and unrelated infrastructure changes are not authorized.
The user separately approved one tenant-only, secretless SPA registration
`customer-service-multi-agent-web`, its HTTPS/localhost callbacks, and preauthorization
for the existing API's `access_as_user` scope. Preserve all other clients, scopes and users.
The requested conversational extension uses Microsoft Agent Framework in a native
Foundry Hosted Agent; the existing model deployment remains separate from agent compute.
Use existing identity and access where effective; report missing access
as a blocker rather than granting roles, fetching keys or disabling authentication.
Inference and judge runs need explicit execution inputs and bounds; deployment permission is
not an unbounded experiment grant. Teardown is not implied.

Parent-supplied discovery on 2026-10-17: public DNS zone `azuremew-domain.org` is owned in
subscription beginning `d88c020a`, resource group `azure_aiml_test_1`; delegation verified.
Gateway was **Stopped**, with no TLS certificate. Parent owns certificate setup and gateway
activation. These observations supersede imported historical Running claims for planning;
they are supplied evidence, not this sweep's independent live read-back.

Reuse the existing same-tenant Entra MCP User Data API registration
`b2d8ec71-c3b4-4005-a492-08b9bdab3414`, with `access_as_user` and CLI preauthorization,
as supplied by the parent. The planned app authorization uses a per-project `oid` allowlist.
Only add the approved browser client's delegated preauthorization; never change the API's
audience, token version or scopes, remove CLI access, or add RBAC grants.
Validate actual token issuer, audience,
scope and allowlist decisions through the owning app contract; configuration is not a pass.

## Required observability and evaluation

Structured operation logs must carry these exact keys:

```text
trace_id span_id agent_id agent_version session_id customer_tier operation_type
model_id input_token_count output_token_count latency_ms status error_code
```

Correlate orchestration and agent/model operations within a trace/session, with distinct spans
and actual loaded agent versions. Count tokens from provider usage, not guessed text length.
Measure latency in milliseconds. Define status/error semantics at the app boundary; absent
usage is unknown, not zero. Report instrumentation gaps explicitly.
Never log credentials, raw customer payloads, private prompts or hidden reasoning.

### Four specialized judges

The required criteria are exactly `factual_accuracy`, `task_completion`, `tone` and
`consistency`. This supersedes the earlier task-completion/goal-achievement/coherence wording.
Each judge receives an independent, focused rubric and only the context needed for its
criterion. Do not feed another judge's scores into its decision.

| Criterion | Focused context and rubric |
| --- | --- |
| `factual_accuracy` | Authorized reference facts and relevant response claims; supported correctness, contradictions and unsupported assertions. |
| `task_completion` | Requested task, expected outcome and observable result; whether the task/goal was achieved. Ignore politeness, friendliness and tone. |
| `tone` | Response and specified customer-service style; appropriateness, respect and clarity, not task success or factual correctness. |
| `consistency` | Relevant turns, commitments and agent handoffs; contradictions across the scoped interaction, not an unrelated style score. |

Require strict JSON, validated against the owning app's settled output schema, with the
criterion, score, bounded evidence references and concise justification. No Markdown fences,
extra prose, hidden reasoning or silent coercion of malformed outputs into scores.
Missing context, invalid JSON and judge failures remain explicit errors/unscorable cases,
not zeros or successful evaluations. This document does not invent the app's score scale.

Pin case inputs, expected goals, rubric revision, score scale and actual judge model/version
before comparison. Optional robustness mode uses **three prompt variants per criterion with
the same model/version**, clearly labeled as prompt variants, not independent models or
human raters. Keep each score, mean and spread (`max - min`) in the declared score units;
**spread > 3 requires human review**. Missing variants cannot silently become a complete
three-variant result; a mean does not override review.

### Calibration and batch integration

Dataset preparation is parent-owned under `datasets/**`. Require approximately **20
LLM-generated synthetic examples**, explicitly labeled generated, with a four-level taxonomy:
**interaction / complexity / persona / adversarial**. Record coverage and gaps across these
axes; approximately 20 examples do not establish exhaustive combinations or production frequency.
Pin authorized catalog/policy facts, initial state, deterministic expected state transitions
and permitted/required actions for each case. Generation must not invent business policy,
successful tool execution or observed customer outcomes.

Carry the requested **3/4/3 rubric structure** explicitly in the parent-owned dataset contract,
with flexible concept-equivalent acceptance rather than exact response wording. The supplied
shorthand does not identify its allocation/anchors; do not infer weights, criterion mappings
or a replacement scale for the four judges. Parent must settle that mapping before scored use.
Keep deterministic state/action assertions separate from semantic rubric judgments.

Freshness metadata must pin **catalog, policy and agent hashes**, provenance, generation
model/prompt revision and review date. Review at least quarterly and on relevant catalog,
policy or agent changes; identify stale cases and reverify expectations before scored reuse.
A matching hash alone is not semantic review. Generation, batch results and generated expected
answers are never human calibration labels. These approximately 20 generated cases do not
meet the separate 50-100 genuinely human-labeled-example calibration requirement.
This documentation change creates no dataset, invokes no model and claims no batch result.

Calibration must consume **50-100 real human-labeled examples**. Synthetic issue text may
be human labeled, but model-generated labels, fixture defaults and invented reviewer verdicts
are not human labels. Record provenance, rubric/label mapping, sample count and agreement
method. Freeze the comparison set; report per-criterion agreement using the appropriate
declared kappa method. **Kappa > 0.7** is required; missing, insufficient, undefined or failing
agreement leaves the affected deployment quality gate **uncalibrated**, not passed.
No calibration dataset, measured kappa or calibrated deployment acceptance is supplied here.

Optional `azure-ai-evaluation` integration may batch JSONL through custom callable evaluators
for the same four criterion contracts. A non-secret optional manifest may pin data digest,
field mappings, criterion/rubric/model/variant identities, callable references, output schema
and result location. It is a reproducibility input, not authorization or calibration evidence.
Inspect actual SDK availability/API and app implementation before documenting an executable
command; no dependency, callable, manifest or batch result is established by this guidance.
Authorized Python package changes use `uv` and an existing interpreter only.

Retain per-case verdicts, errors, sample counts, variant dispersion and calibration status.
Separate judge outputs, deterministic checks, runtime journey evidence and business outcomes.
No fabricated resolution rates, savings, satisfaction or business impact.

The required navigable metrics hierarchy is **system aggregate -> journey-type breakdown ->
per-agent component accuracy, latency, errors and tokens**. Drill-downs must retain scenario,
trace/session, time-window and denominator context so aggregates reconcile with component
observations. Define accuracy against the relevant expected outcome; do not substitute tone
or a selected anecdote. Label missing coverage and synthetic data. Agent count comes from actual
configuration, not a reference example; no fixed 14-agent design is required. Worker implementation
and navigability remain unverified by this documentation sweep.

## Imported guidance and unavailable prerequisites

Verified absent at initial inspection: `.github/tools/`, `docs/notebook/`, `libraries/`, root `deploy/`,
`testbeds/`, `template_apps/`, `agentcraft_projects/`, `architecture.json`, `.agent-harness.json`.
Bundled source packages under individual skills are not installed app dependencies.
Imported receipts, SDK pins, tenant policy observations and timings do not establish local
compatibility, deployed state or current authority.

- Use [repository tools](repository-tools.instructions.md) for available read-only discovery
  instead of missing `find.py`, `arch.py`, `docaudit.py`, `oplog.py` or notebook commands.
- Missing imported mandatory tooling is a prerequisite gap, not permission to invent results,
  install the harness, create a notebook or copy its libraries. Agent-specific exclusive-tool
  restrictions still apply; return blocked if no permitted fallback exists.
- Availability decision: absent `.github/tools/oplog.py` and `.github/tools/oracle.py`
  recipes are unavailable and must not execute. Ordinary documentation work can report
  measured host/tool durations with coverage gaps, without inventing run IDs or receipts.
  A role that exclusively requires these tools remains blocked pending role-owner correction;
  this does not authorize an alternative oracle draw or change selected model/effort settings.
- Protocol source under `.github/protocols/` is imported and is now in the authorized
  documentation scope. Entries resolve architecture references here and replace or explicitly
  disable unavailable local recipes; imported historical receipts remain non-executable evidence.
- Existing landing-zone deployment owners are [Bicep](../../bicep/README.md) and scripts under `scripts/`.
  `scripts/deploy-apps.sh` deploys other apps and can bootstrap infrastructure; it is not a
  customer-service deployment command. Parent-created `deploy/deploy.sh` now exists on disk;
  this is path discovery, not execution or deployment evidence. Inspect its help and documented
  actions before execution. Do not create, modify or substitute that parent-owned implementation.
- For authorized Python package operations use `uv` against an existing interpreter only,
  per the work contract. Never create or activate an environment, or run implicit setup.

Acceptance requires focused local checks, deployed image/revision and protected-field
read-back, a synthetic customer journey through the approved WAF route, correlated required
log fields, and all four specialized judges. Calibration-dependent quality gates remain
`uncalibrated` until qualifying human-label agreement is measured; other unobserved acceptance
remains `not_verified`. A deployed image alone does not establish calibrated judge quality.
