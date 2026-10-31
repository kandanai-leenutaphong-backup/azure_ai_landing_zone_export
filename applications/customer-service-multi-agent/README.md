# Customer Service Multi-Agent Lab

Synthetic-only callable FastAPI service and no-build static UI. Three native service agents,
four specialized native prompt judges. No real customers, payments, retrieval corpus, or cloud
resources created by serving runtime.

Conversational UI and protected chat API are implemented. `hosted/` composes three
Microsoft Agent Framework agents through `Workflow.as_agent()` for triage, policy and
resolution. Native Hosted version `cs-customer-service-chat:1` is active in private West US 3;
downloaded source matches the accepted archive. The existing model deployment remains
separate from hosted compute. Two real synthetic turns completed and their stored native Responses matched.
Minimal UI is deployed at <https://customer-service-multi-agent.azuremew-domain.org>
on revision `customer-service-multi-agent--0000004`. Two chat turns on the preceding
revision completed and matched owner-bound history. The current revision fixes the
WAF-blocked login callback: automatic authorization and correlated SDK denial handling passed;
completed interactive human sign-in/MFA remains unverified. GitHub pushes and further
CI/CD implementation are postponed.
Missing Hosted configuration returns explicit 503, never a prompt-agent or local fallback.
The existing synthetic simulation and metric capabilities remain callable through the API,
not displayed in the simplified chat UI.

Offline CI/gold-promotion/drift owner: [`REGRESSION.md`](REGRESSION.md).
No cloud execution; source `regression.py`, safeguards `test_regression.py`.

## Ownership and placement

All implementation belongs to this app. `ARCHITECTURE.md` supplies repository context;
`docs/ARCHITECTURE_OVERVIEW.md` does not exist. Existing Python application stack and explicit
assignment justify FastAPI plus framework-free HTML/CSS/JS instead of React/build tooling.
No imported template or nonexistent shared library used. Parent owns deployment, hub WAF/TLS,
DNS, networking, existing identity and resources. Nothing under `deploy/`.

| Capability | Owner / callable surface | Dependencies / callers | Verification |
|---|---|---|---|
| Immutable cases | `scenarios.py`, `GET /api/scenarios` | UI, simulation; no external data | fixture tests |
| Simulation + action readback | `simulation.py`, `SimulationService.submit`, Store | API and evaluation CLI; native agents, SQLite | service/API tests |
| Native agent lifecycle | `native.py`, `provision_agents.py` | installed Azure Projects/OpenAI SDKs; assigned private project only | SDK reference/provision tests; deployed synthetic workflow readback |
| Strict specialized judging | `evaluation.py`, `SpecializedJudges.evaluate` | runtime and SDK callable share owner; schema in `simulation_schema.py` | rubric/consensus/calibration tests |
| Tiered measurement | `simulation.aggregate`, `GET /api/metrics` | UI; caller-owned runs only | weighted totals/filter tests |
| Identity boundary | `auth.py`, `EntraAuth` | pinned tenant JWKS; explicit users and scope | valid and matching negative JWTs |
| Safe telemetry | `telemetry.py` | OTel SDK; stdout JSON primary, optional exporter | schema/privacy/parent-span tests |
| Browser surface | `static/` | one chat and Logout; automatic tenant redirect; memory tokens, transient tab PKCE state; no build/CDN | `browser_check.py`, screenshots |
| Conversational support | `chat.py`, `POST /api/chat/messages`, `GET /api/chat/conversations/{id}` | UI; shared simulation busy lock; owner-isolated SQLite; explicit native Hosted pin | chat service/API tests |
| Framework hosted runtime | `hosted/{main,runtime,validation}.py` | three AF roles; canonical `scenarios.py` and `telemetry.py`; no transaction tools | AF/native host tests; active source ZIP, two-turn Responses and native role telemetry readback |

Dependency direction: `app.py` composes configuration, auth, telemetry, native and simulation.
Simulation consumes specialized evaluation, which consumes shared strict schema only, never
composition root. CLI adapters consume same service and judge owner. Configuration enters at
composition edge. SQLite owns deterministic authoritative tools because this demo requires
local state transitions/readback, not real financial or carrier services.

## Local configuration

From the repository root, use your existing Azure CLI login:

```sh
bash deploy/deploy.sh -e sea configure-local
cd applications/customer-service-multi-agent
/usr/local/bin/python3 -m uvicorn app:create_app --factory --host 127.0.0.1 --port 8080 --workers 1 --no-access-log
```

Open <http://localhost:8080>. `configure-local` reads this app's deployed
non-secret settings and exact version pins, verifies your CLI user is already
allowed, then creates a mode-0600 `.env` beside `.env-template`. It does not
grant access, fetch secrets, save tokens or overwrite custom local changes.

`Settings.from_env` automatically loads that exact app-local file, independent
of the working directory. Existing process variables win; dotenv interpolation
is disabled. No `source` or manual `export` is required. `.env` and its variants
are gitignored and excluded from publication and container builds; only
`.env-template` is committed.

Local `.env` explicitly selects `AZURE_AUTH_MODE=azure_cli`, so outgoing Foundry
calls use your existing login in the configured tenant. Incoming API calls still
require delegated authorization; the browser automatically redirects to Microsoft sign-in,
not a pasted API token.
Without that explicit local mode, deployed runtime continues to use its managed
identity, with no automatic credential fallback.

## Configuration reference

Existing interpreter `/usr/local/bin/python3`. Existing packages verified through installed
metadata and actual import paths, not skill pins. `requirements.txt` pins runtime direct
dependencies. No environment creation/activation. If packages need installation:

```sh
uv pip install --python /usr/local/bin/python3 -r requirements.txt
```

Required environment:

| Name | Value / rule |
|---|---|
| `TENANT_ID` | Existing Entra tenant UUID |
| `AUTH_CLIENT_ID` | `b2d8ec71-c3b4-4005-a492-08b9bdab3414`, exact v2 access-token audience |
| `BROWSER_CLIENT_ID` | `722e2f80-ccb1-4ba0-93a5-d36514a955ae`, tenant-only secretless SPA |
| `AUTH_ALLOWED_OBJECT_IDS` | Nonempty comma-separated explicit user object UUIDs |
| `AZURE_CLIENT_ID` | `fd13bac4-3953-420e-bd15-7ff20765fe80`, existing UAMI |
| `AZURE_AUTH_MODE` | `azure_cli` in local `.env`; defaults to `managed_identity` when unset |
| `AGENT_TRIAGE_VERSION` | Exact provisioning output |
| `AGENT_POLICY_VERSION` | Exact provisioning output |
| `AGENT_RESOLUTION_VERSION` | Exact provisioning output |
| `AGENT_JUDGE_FACTUAL_ACCURACY_VERSION` | Exact provisioning output |
| `AGENT_JUDGE_TASK_COMPLETION_VERSION` | Exact provisioning output |
| `AGENT_JUDGE_TONE_VERSION` | Exact provisioning output |
| `AGENT_JUDGE_CONSISTENCY_VERSION` | Exact provisioning output |

Optional:

- `HOSTED_AGENT_NAME` / `HOSTED_AGENT_VERSION`: supplied together after native source
  deployment verifies active status and downloaded source bytes. Name must be
  `cs-customer-service-chat`; version must be explicit. Missing pins disable only chat.
- `FOUNDRY_PROJECT_ENDPOINT`: defaults to and only accepts
  `https://foundry-agent-wus3jbm3vfsrmekbg.services.ai.azure.com/api/projects/agent-project`.
- `MODEL_DEPLOYMENT`: defaults to and only accepts `gpt-4.1-mini`.
- `SQLITE_PATH`: `/tmp/customer-service.sqlite3` default.
- `APP_REVISION`: parent artifact SHA/revision, returned by health.
- `APPLICATIONINSIGHTS_CONNECTION_STRING`: set from a Bicep-referenced Container App secret; never
  fetched by the operator. Export uses the managed identity (Monitoring Metrics Publisher).
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`: optional trusted nonsecret collector endpoint, when
  Application Insights connection is absent. Deployment owner must provide trusted destination.

Auth configuration missing/invalid means startup fails. No default audience, principal-header
trust, environment bypass, app-registration writes or RBAC changes.

## Native provisioning and launch

### Conversational Hosted Agent

Run `bash deploy/deploy.sh -e sea provision-hosted` from the repository root while connected
to the existing private network. Native `create_version_from_code` uploads exactly six
source members, uses Python 3.13 remote build, 0.5 CPU / 1 GiB, and Responses protocol
2.0.0. It requires no registry role grant or local Docker. The model remains the existing
regional `gpt-4.1-mini`, separate from Hosted Agent compute. Hosting dependency pins live
only in `hosted/requirements.txt`, not the SEA web container.

After successful active/source readback, record the returned name/version in
`deploy/env/sea.env`, release, then refresh the local `.env` fields without discarding
custom settings. The single `deploy` sequence passes a newly verified pin into that same
release; record it in environment targets before later independent releases.

Chat accepts 1-2000 characters, eight turns maximum. The server owns native response IDs;
clients receive only app UUIDs. Shared exclusion prevents chat and simulation inference
from overlapping. Pending turns persist before invocation; restart marks interrupted work
failed instead of replaying it. Unknown outcomes are not retried. Hosted processing permits
three paced model calls per turn, read-only synthetic policy and no financial execution.
Conversation history is replica-local and can disappear on scale-to-zero.

### Existing synthetic workflow

Run from this directory on private network with existing Azure CLI login:

```sh
/usr/local/bin/python3 provision_agents.py --apply
```

Creates only missing app-owned names `cs-sim-triage`, `cs-sim-policy`, `cs-sim-resolution`,
`cs-sim-judge-factual-accuracy`, `cs-sim-judge-task-completion`, `cs-sim-judge-tone`,
`cs-sim-judge-consistency`. All definitions are native `PromptAgentDefinition`, temperature 0,
model `gpt-4.1-mini`, no remote tools. Preflights all names, rejects unrelated ownership,
definition/hash changes or ambiguous versions, never updates/deletes existing agents.
Readback verifies exact created definitions. Repeating returns existing versions without writes.
No-argument invocation verifies read-only and fails when agents are missing.
Unknown create outcome: reconcile by rerunning read-only, not blindly recreating. Concurrent
provisioners are unsupported; one operator owns these names.

Copy printed `AGENT_*_VERSION` values into parent app configuration. Runtime verifies pinned
definitions and deployment's regional `Standard` SKU/model before first invocation.
Uses actual reference shape from sibling's read-only example:
`responses.create(extra_body={"agent_reference":{"type":"agent_reference","name":...,"version":...}})`.
No direct-model judge fallback. Native client imports only at runtime.

```sh
/usr/local/bin/python3 -m uvicorn app:create_app --factory --host 0.0.0.0 --port 8080 --workers 1 --no-access-log --log-level critical
```

Container context is this directory. `Dockerfile` copies pinned official uv image binary and
installs into existing `/usr/local/bin/python3` using `uv pip`, never creates a virtualenv.
Nonroot UID/GID 10001, port 8080, strict context allowlist. Parent target: one replica,
0.5 CPU / 1 GiB, private SEA Container App behind hub WAF, HTTPS-only public route
`https://customer-service-multi-agent.azuremew-domain.org`. Resource sizing not load-tested.
Parent must attach existing UAMI and supply private DNS/network access.

## Authentication and browser

Every `/api/*` handler validates RS256 signature from pinned tenant JWKS, `exp`, `iat`, `nbf`,
`tid`, v2 `iss`, exact `aud`, `oid`, delegated `access_as_user`, and explicit object allowlist.
JWKS failure refuses access. ID tokens, app-only tokens, forged principal headers, wrong tenant,
wrong audience, expired/future tokens and unlisted users fail. All results/metrics isolate
owners by SHA256 of tenant + user object ID. Cross-owner reads return 404.

Initial visits automatically redirect to Microsoft using the tenant-only, secretless
`customer-service-multi-agent-web` SPA and authorization-code PKCE. Official MIT-licensed
MSAL Browser 4.30.0 is vendored under `static/vendor/` with integrity/provenance, never
loaded from a CDN. `/auth/config` exposes only public identifiers; it grants no access.
MSAL handles the redirect before selecting an account, then acquires delegated API tokens
silently. Tokens stay in memory, never cookies or local/session storage. Transient
PKCE/redirect state survives navigation in tab-scoped sessionStorage. Pinned MSAL 4.30.0
requires `storeAuthStateInCookie` to permit MemoryStorage redirects, but its generated
auth-state cookies trigger the hub WAF on callback. A supported `NavigationClient` hook
removes those compatibility cookies before navigating externally; sessionStorage retains
the required state. No authentication cookies are sent on return. Actual SDK callback
handling is exercised with a correlated synthetic `access_denied` response, without
credentials, codes or token exchange. Transient state is cleared after handling.
No localStorage.
Logout clears the account, token, polling and displayed data, then requests the tenant's
end-session endpoint with the exact registered callback. A non-secret tab-scoped
`service-chat:logged-out=1` marker prevents automatic immediate re-login. Only that
logged-out/recovery state exposes a deliberate Continue with Microsoft action.
Normal authenticated UI contains only the chat, composer/Send and Logout.
Browser refuses non-HTTPS except localhost. CSP forbids inline/eval scripts and embedding;
only the Microsoft login origin is allowed for external authentication connections/frames.
Callbacks are the exact HTTPS hostname and `http://localhost:8080/auth/callback`.

Existing Azure CLI is preauthorized for API's `access_as_user`; operator can obtain a delegated
token for `api://b2d8ec71-c3b4-4005-a492-08b9bdab3414` using trusted local tooling. Never put token
in shell arguments, artifacts, logs, screenshots, source, or chat. The deployment-only
`setup-browser-auth` action owns the explicitly approved SPA/preauthorization;
serving runtime never changes Entra registrations or grants roles.

For installed `azure-identity==1.19.0`, SDK acquisition scope must be
`api://b2d8ec71-c3b4-4005-a492-08b9bdab3414/.default`, not `/access_as_user`.
`AzureCliCredential.get_token("api://b2d8ec71-c3b4-4005-a492-08b9bdab3414/.default")`
converts that scope to the API resource. Equivalent CLI acquisition uses
`az account get-access-token --resource api://b2d8ec71-c3b4-4005-a492-08b9bdab3414`
through trusted local token-handling tooling, never captured in logs/artifacts.
Returned access token must still contain delegated `scp: access_as_user`; acquisition scope
and API's required permission claim are different concepts. Installed conversion inspected
offline; no token request made by worker.

## HTTP contract

JSON only. Bearer auth on all API endpoints. UI `/`, static assets and `/healthz` are public.
All responses `no-store`; no CORS allowance.

| Method | Path | Contract |
|---|---|---|
| GET | `/healthz` | 200 `{status,revision,storage,native_connectivity}`. Liveness/artifact identity only, not cloud readiness |
| GET | `/auth/config` | Public tenant/client/scope/callback identifiers; 503 if browser registration missing |
| GET | `/auth/callback` | Public same-origin blank MSAL callback; no credentials returned by this handler |
| GET | `/api/scenarios` | 200 `{simulation:true,scenarios:[...]}`. Four immutable fixture objects, criteria/policy included intentionally |
| POST | `/api/simulations` | Body exactly `{"scenario_id":"damaged-return"}`. 202 result + `Location` readback URL |
| GET | `/api/simulations/{id}` | 200 owned result; 404 missing or other owner |
| GET | `/api/metrics` | 200 `{system,journeys,selected_journey,agents,demo_targets,...}` |
| GET | `/api/metrics?journey_type=return` | Agent tier filtered to journey; system tier stays overall; journey table retains all groups |
| POST | `/api/chat/messages` | `{message,conversation_id:null|UUID}`; 202 `{conversation_id,turn_id,status:"queued"}` + `Location`; 503 without Hosted pin |
| GET | `/api/chat/conversations/{id}` | Owned status/messages/error readback; cross-owner/missing 404 |
| GET | `/api/chat/replay/{response_id}` | Stored Foundry turn text; 403 unless caller is in `REPLAY_OPERATOR_OBJECT_IDS`; 422 bad ID; 404 missing |

Fixture IDs: `damaged-return`, `duplicate-charge`, `missing-shipment`, `out-of-policy`.
Journey types: `return`, `billing`, `shipping`, `exception`. The simulation API accepts only
fixture IDs. Chat accepts validated synthetic support questions, never real customer records
or transaction authority. Invalid JSON/extra fields: 422, unknown scenario: 404, auth failure: 401,
one run already active: 429 with `Retry-After: 30`. Client polls GET until completed/failed.
No POST auto-retry or idempotency key: a new POST creates a distinct synthetic case.
Unknown submission outcome: query known returned ID; do not assume no action happened.

Run fields include ID, scenario/journey, queued/running/completed/failed status, agent pins,
trace/session correlation, authoritative `ledger`, component results, judge, goal index,
agent samples, evaluation scope, safe error code. Completion means evaluated synthetic workflow,
not resolved customer issue. Judge failure yields failed status/null goal, never success;
recorded action remains readable. Startup marks queued/running saved runs failed with
`worker_interrupted`. No automatic replay.

## Tool integrity and storage

Policy request must exactly match immutable authoritative action. Single ledger row per run;
repeated operation reads existing receipt. Return authorization is not refund. Duplicate charge
records exactly one simulated SGD 49 refund, never external payment. Missing shipment opens
investigation only. Late return escalates regardless of premium tier.
Resolution's action/receipt/completion fields must match actual tool readback before any success.
Free-form explanation is model output, evaluated for factual accuracy; ledger, not prose,
is authoritative.

SQLite survives process restarts **only while the same file survives**. Replica-local `/tmp`
is non-durable across replacement/redeploy, not shared across replicas, no backups or promised
retention. One worker/replica only. Parent may later provide an authorized persistent mount;
no Blob grants/resources requested or fabricated Foundry metadata persistence used. Stored native
responses are synthetic, but not a reconstruction database for this service.

## Evaluation and three-tier metrics

[Microsoft Learn observability](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability)
distinguishes evaluation, monitoring and tracing.
[Agent evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators)
distinguishes system task completion from process/tool correctness.
This app implements **custom domain rubrics**, not Microsoft built-in evaluator scores:

- Four specialized versioned native judges: factual accuracy, task completion, tone,
  consistency. Each receives full synthetic transcript, immutable ground truth and actual
  final ledger state. Strict integer 0..10 `score`, nonempty `reasoning`,
  optional `missing_requirements`. Task judge additionally returns exactly three strict booleans
  for scenario-specific criteria, explicitly ignores politeness.
- Goal index = criterion1 × 3 + criterion2 × 4 + criterion3 × 3, 0..10.
- Holistic journey coherence = specialized consistency judge's score, **custom 0..10 scale**,
  not Microsoft `CoherenceEvaluator`'s built-in scale.
- Ordinary run invokes each of four judges once: seven total model calls.
- Explicit consensus invokes three prompt variants per criterion: fifteen total calls including
  three service agents. Same available regional model, not independent model consensus.
  Average numeric scores, max-minus-min spread; spread > 3 requires human review.
  Binary criteria conservatively require all three variants to pass each criterion.
- Zero model retries, one active simulation, >=7 seconds between native request attempts.
  Shared deployment also serves others, so 429 can still occur. No automatic model fallback.
- Scores provisional. `calibration_not_established`, `release_ready:false` by default.

Three callable metric tiers, retained in `/api/metrics` and Log Analytics rather than
dashboard controls in the simplified chat UI:

1. System: all-attempt task completion, average scored goal achievement, journey coherence,
   attempts/errors/pending/scored/unscored. Business impact, resolution and reopen remain null.
2. Journey: same measures grouped by immutable journey type; selectable in UI.
3. Agent: specialized task accuracy **only explicit correctness labels**, correct/evaluated/
   total/unevaluated counts, error count/rate, mean/p95 latency, latency samples, input/output
   token totals plus known-token sample counts. Journey selector filters agent samples.
   Triage correctness = exact category; policy = exact requested authoritative action;
   resolution = receipt/action/completion contract only, not prose quality. Judge accuracy
   unavailable without independent ground truth, never derived as `1 - error_rate`.

Task completion denominator includes all attempts (failed and pending included). A completed task
requires all three criteria true. Goals/coherence mean over scored runs only, unscored count
explicit. Aggregation uses raw samples, not mean of group means. p95 uses nearest rank, including
failed native attempts with measured latency; quota pacing included. Null tokens never become zero.
Demo targets 90% completion, 8.5 goal, 9 coherence are illustrative, not production SLOs.

Scope claims: components and single-run handoffs tested; no cross-session memory evaluation.
Knowledge is supplied immutable policy, no retrieval/rank metrics. Tool correctness/readback
measured locally. Prompts version-pinned, no optimizer experiment. Synthetic scores cannot
establish business resolution/reopen or production quality.

### Calibration, consensus and SDK batch entry

Offline calibration consumes **user-supplied human labels**, 50..100 examples. Each JSONL line:

```json
{"human_scores":{"factual_accuracy":8,"task_completion":9,"tone":8,"consistency":9},"judge_scores":{"factual_accuracy":8,"task_completion":8,"tone":8,"consistency":9}}
```

```sh
/usr/local/bin/python3 evaluate_cli.py calibrate --data /path/to/human-labels.jsonl
```

Computes unweighted Cohen kappa on exact integer categories for each criterion. Requires >0.7
for every criterion and 50..100 supplied examples. Insufficient samples or undefined kappa
retain `calibration_not_established`; constant-label agreement cannot fabricate kappa.
Even measured agreement does not grant release readiness or representativeness.

Explicit billable synthetic smoke/consensus, using configured managed identity:

```sh
/usr/local/bin/python3 evaluate_cli.py simulate --scenario-id duplicate-charge --allow-model-calls
/usr/local/bin/python3 evaluate_cli.py simulate --scenario-id out-of-policy --consensus --allow-model-calls
```

Optional SDK batch adapter:
[SDK reference](https://learn.microsoft.com/en-us/python/api/azure-ai-evaluation/azure.ai.evaluation?view=azure-python).
`azure-ai-evaluation` is **not installed locally**. Public release 1.18.9 metadata and source
signature checked; live SDK execution remains unverified. Runtime image does not install it.
If parent authorizes package installation into an existing interpreter:

```sh
uv pip install --python /usr/local/bin/python3 -r requirements-evaluation.txt
/usr/local/bin/python3 evaluate_cli.py batch --data /path/to/synthetic-cases.jsonl --output ./evaluation-output/results.json --allow-model-calls
```

Batch JSONL file defaults to one smoke case; explicit `--max-cases 20` allows up to 20.
Each row requires known `scenario_id`, optional synthetic `customer_request` of 1..2000 characters.
Offline taxonomy/freshness/expected-state/rubric metadata is ignored, never authoritative.
Parent owns `datasets/**`, not required by serving image. Callable interface:
`SimulationEvaluator(service, consensus=False, result_sink=None)(scenario_id="damaged-return", customer_request="Synthetic wording", **ignored_metadata)`.
Request language may vary; category/action/policy/criteria and judge ground truth always derive
from immutable fixture, never dataset expected-state fields. API accepts no request override.
Adapter passes a **file path**, not unsupported in-memory data, to
`azure.ai.evaluation.evaluate`, with custom callable `SimulationEvaluator`, same native judge
owner and serialized runs. `fail_on_evaluator_errors=True`. Optional `--consensus`. Output must
remain inside app boundary. No Foundry evaluation project publishing configured.
Runtime CLI auth config is identical to service config. No native red-team campaign run or
authorized by this command. SDK red-team support absent locally; do not claim integration.
Offline opt-in adversarial boundary regression:

```sh
/usr/local/bin/python3 -m unittest test_app.EvaluationTests.test_adversarial_boundary_no_arbitrary_actions -v
```

Checks injected prompt field is rejected and hostile/unauthorized actions cannot alter immutable
out-of-policy ledger. Not a model red-team score or proof of general prompt-injection resistance.

## Structured telemetry and monitoring

Every app event JSON includes `trace_id`, `span_id`, `agent_id`, `agent_version`, SHA256
`session_id`, `run_id`, `journey_type`, `customer_tier`, `operation_type`, `model_id`,
`input_token_count`, `output_token_count`, `latency_ms`, `status`, `error_code`,
`correctness`, `decision_code`. Unknown tokens/HTTP journey/run are null, tier unknown.
Known journey values derive only from fixtures. No URLs, prompts, model text/reasoning,
customer PII, bearer tokens, object IDs or raw exceptions logged.

W3C `traceparent` extracted at HTTP edge. Child simulation, native calls, validated decisions,
tool execute/readback share trace. Responses include `traceparent`; run readback includes
trace/session IDs. Decision metadata limited to contract name and correctness, never content.
Explicit parent/child spans, no auto-instrumentation that might capture request bodies/headers.
Azure SDK request logging not enabled. Third-party diagnostic loggers suppressed; app emits
safe error codes instead of raw credential/export/provider diagnostics.
Serving command disables uvicorn access/error chatter.

`simulation.snapshot` events emit at acceptance and completion/failure, including `metrics`
with schema version, immutable scenario ID, completion/error/scored flags, goal/coherence,
four numeric judge scores and allowlisted per-agent numeric/correctness samples. No transcript,
judge reasoning, ledger receipt/amount, user identity or explanations included. Failed runs
retain error/attempt denominator even when unscored. Accepted runs without terminal events
remain incomplete/unknown, never success. After process restart on surviving file, interrupted
run emits failed snapshot. Deduplicate by run ID; never count every lifecycle event as an attempt.
UI does not query historical logs and must not be described as a persistent scorecard.

Stdout JSON into existing Container Apps Log Analytics is primary, existing workspace
**180-day** retention supplied by parent, not created/changed here. If configured, OTel spans
also export to existing Application Insights, otherwise optional trusted OTLP collector.
No resource creation or connection-secret fetch. Null token counts are honest unknowns.
Two shared Azure Monitor Workbooks now query this workspace: **Customer service multi-agent -
Quality** (system/journey/agent) and **Customer service multi-agent - Operations**
(volume, outcomes, tokens, schema completeness, errors, trace fields). Deployment links and
query/readback evidence are in `deploy/README.md`. They show structured operational events,
not transcript bodies or semantic scores for chat replies.

Conversation rows are currently stored in owner-bound local SQLite at
`/tmp/customer-service.sqlite3`. This is replica-local, not durable across scale-to-zero or
restart. Foundry Responses are stored by the Hosted service and can be read back by response
ID. Message bodies are never logged. The app does not write to Cosmos; Foundry stores each
hosted turn and, from hosted version 3, each sub-agent response (tagged with `trace_id`/`span_id`)
in its own Cosmos `run-state-v1` container (see `deploy/trace-explorer-cosmos.sql`).

### Cross-agent trace contract

One chat turn is one W3C trace across both services:

```
chat.turn      customer-service-capp-sea   (SEA Container App)  response_id
└─ (Foundry gateway span, platform-owned, not logged)
   └─ chat.workflow customer-service-hosted-wus3 (Hosted, West US 3)
      ├─ chat.agent  step 1 triage       response_id ─┐
      ├─ chat.agent  step 2 policy       response_id ─┼─ Cosmos run-state-v1 (hosted v3+),
      └─ chat.agent  step 3 resolution   response_id ─┘  object.metadata.{trace_id,span_id,agent_id}
```

- Each sub-agent call is a stored Foundry Response (`store: true`) whose `metadata` carries
  `trace_id`, `span_id`, `agent_id`, `agent_step`, `agent_version` and `session_id`; the
  `chat.agent` span records that call's `response_id`. Per-agent input/output is therefore
  readable in Cosmos by trace or span ID (verified 2026-10-19, trace `58c6c0c7…`).
- The app sends `traceparent` plus W3C baggage `cs.session_id` (SHA256 session hash) on the
  Responses call. Hosted middleware extracts both, so every hosted row shares the app's
  `trace_id` and `session_id`.
- Every row also carries `parent_span_id`, `service_name` and `agent_step`. Hosted
  `parent_span_id` links rebuild the hosted tree. `chat.workflow.parent_span_id` is the
  Foundry gateway's span, not `chat.turn.span_id` (observed 2026-10-18: trace `cbbe26ce…`,
  app span `a6ced59b…`, workflow parent `76bd0167…`; the app has no HTTP auto-instrumentation),
  so join the app row to the hosted tree on `trace_id`. The `chat.turn`
  row carries the Foundry `response_id`, the key for reading the stored response back.
- Spans carry the same fields plus `gen_ai.*` attributes (`agent.name`, `request.model`,
  `conversation.id`, `response.id`, `usage.*_tokens`).
- App rows land in the SEA Log Analytics table. Hosted rows land in the Foundry session log
  stream (`deploy.sh -e sea verify-hosted-logs`); join on `trace_id`.
  [`deploy/trace-explorer.kql`](../../deploy/trace-explorer.kql) lists one trace or session.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` enables span export in either service with Entra
  (managed identity) auth only. Both are configured for `appi-tracing-xlpu`
  (`deploy.sh -e sea observability`): the app reads it from a Container App secret set by Bicep;
  the Hosted Agent receives it from the project's native App Insights connection. Query one
  trace with [`deploy/trace-explorer-appinsights.kql`](../../deploy/trace-explorer-appinsights.kql)
  (`operation_Id` = `trace_id`). Foundry's own `responsesapi` spans (`invoke_agent`, `chat`)
  arrive under separate trace IDs and are not joined.
- Replay one conversation from any trace or span ID:
  `bash deploy/deploy.sh -e sea replay --trace-id <32 hex>` or `--span-id <16 hex>` (`--json`
  for machine output). [`deploy/replay.py`](../../deploy/replay.py) prints the span tree, finds
  the session's `chat.turn` spans by `session_id`, and reads each turn's text through
  `GET /api/chat/replay/{response_id}`. Foundry binds stored Hosted responses to the app identity
  (CLI reads return 403 `session_not_accessible`) and drops request `metadata` and
  `previous_response_id`, so the route is an operator capability: 403 unless the caller's object
  ID is in `REPLAY_OPERATOR_OBJECT_IDS` (subset of `AUTH_ALLOWED_OBJECT_IDS`). Text is printed,
  never written to disk.

KQL, using existing Container Apps console table (adjust table name only to actual workspace):

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "customer-service-multi-agent"
| extend e = parse_json(Log_s)
| where isnotempty(e.trace_id)
| project TimeGenerated, trace_id=tostring(e.trace_id), run_id=tostring(e.run_id),
    session_id=tostring(e.session_id), journey_type=tostring(e.journey_type),
    agent_id=tostring(e.agent_id), agent_version=tostring(e.agent_version),
    operation=tostring(e.operation_type), status=tostring(e.status),
    error_code=tostring(e.error_code), latency_ms=todouble(e.latency_ms)
| order by TimeGenerated desc
```

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "customer-service-multi-agent"
| extend e = parse_json(Log_s)
| where tostring(e.operation_type) startswith "judge_" or tostring(e.operation_type) in ("triage","policy","resolution")
| summarize attempts=count(), errors=countif(tostring(e.status) == "failed"),
    p95_latency_ms=percentile(todouble(e.latency_ms),95),
    input_tokens=sum(tolong(e.input_token_count)), input_known=countif(isnotnull(e.input_token_count)),
    output_tokens=sum(tolong(e.output_token_count)), output_known=countif(isnotnull(e.output_token_count))
  by bin(TimeGenerated, 5m), journey_type=tostring(e.journey_type), agent=tostring(e.agent_id)
```

KQL percentile is monitor approximation, API p95 nearest-rank. All-null token sums must be
interpreted with known sample counts, not as known zero. Filter first query by exact `run_id`
or `trace_id` for drilldown. KQL not executed against cloud by worker.

Recover overall/journey completion metrics after ephemeral state loss:

```kusto
let latest =
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == "customer-service-multi-agent"
    | extend e = parse_json(Log_s)
    | where tostring(e.operation_type) == "simulation.snapshot"
    | extend run_id=tostring(e.run_id)
    | summarize arg_max(TimeGenerated, *) by run_id;
latest
| summarize attempts=count(),
    task_completed=countif(tobool(e.metrics.task_completed)),
    errors=countif(tobool(e.metrics.error)),
    pending=countif(tostring(e.status) in ("queued","running")),
    scored=countif(tobool(e.metrics.scored)),
    average_goal_achievement=avg(todouble(e.metrics.goal_index)),
    journey_coherence=avg(todouble(e.metrics.coherence))
  by journey_type=tostring(e.journey_type)
| extend task_completion_rate=todouble(task_completed)/attempts
```

Remove final `by journey_type=...` for overall raw-event aggregate. For per-agent recovery,
apply `mv-expand s=e.metrics.agent_samples` to deduplicated latest rows, then aggregate
`s.agent`, `s.correct`, `s.error`, `s.latency_ms` and nullable token fields with evaluated/known
sample counts. Do not equate error-free with correct. Historical recoverability depends on
actual platform ingestion; worker cannot prove that with local tests or create a query grant.

## Verification

From app directory:

```sh
/usr/local/bin/python3 -m unittest test_app -q
/usr/local/bin/python3 browser_check.py
node --check static/app.js
```

Existing pytest also discovers service and deployment checks. Local `browser_check.py`
uses real FastAPI, signed test JWTs, mocked MSAL and injected fake native responses;
production exposes no injection route or flag. It checks two-turn history, bounded polling,
unknown-outcome duplicate prevention, authorization/errors, transient-state cleanup and logout.
Existing Chrome is used without browser/package downloads. Desktop 1440px and mobile 390px
have no horizontal overflow, controls are at least 44px high, and no JavaScript errors occurred.
The harness prints its retained synthetic screenshot directory.

Deployed acceptance belongs to `bash deploy/deploy.sh -e sea browser-verify`. It first
observes actual vendored MSAL automatically requesting authorization-code PKCE, then
separately substitutes the existing CLI user's delegated token in memory to operate two
real Hosted turns. Both completed with exact UI/history matches. This is not completed
human sign-in, consent or MFA. Logout request and local cleanup passed; the verifier
intercepts Microsoft's end-session response rather than claiming a human session ended.
The deployment runbook owns accepted image identity and private evidence locations.
Callback regression checks now send the actual pre-redirect cookie state through the
gateway and exercise real SDK callback state restoration, not just the outbound redirect.
External WAF/auth refusal and Log Analytics ingestion passed independently. Resource
sizing is not load-tested; calibrated quality and automatic production sampling remain
unestablished. Existing Starlette/httpx deprecation warning remains.
