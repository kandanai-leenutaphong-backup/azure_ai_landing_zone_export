# Customer service multi-agent deployment

One operator entry point, run from the repository root:

```bash
bash deploy/deploy.sh -e sea preflight
bash deploy/deploy.sh -e sea deploy
bash deploy/deploy.sh -e sea verify
```

`deploy` creates only `customer-service-multi-agent` in the existing internal
SEA environment, builds its image in the existing registry, provisions its
namespaced prompt agents in the existing private West US 3 Foundry project,
deploys the source-based Microsoft Agent Framework Hosted Agent,
and adds one HTTPS hostname to the existing hub Application Gateway WAF.
It starts the hub gateway if stopped. This restores the gateway's other
existing routes too and resumes its billable running capacity.

Live URL: <https://customer-service-multi-agent.azuremew-domain.org>.
External HTTPS, anonymous/forged-identity refusal and WAF prevention were
verified on 2026-10-17. Rerun `verify` after changes; health alone does not
prove Foundry connectivity or calibrated evaluation quality.

Native Hosted version `cs-customer-service-chat:1` is now active in private West US 3.
After the user restored VPN connectivity, the private endpoint resolved to `10.80.6.10`;
the deployed ZIP downloaded byte-identically with SHA256
`824f1ef58b7bcd4f86ee249e5f4efdf59ed3255f2bcceb317b91d0a885283ad3`.
No registry role grant or public-access change was needed. Two native synthetic turns
completed with matching stored response readback; console logs prove all 13 fields for
triage, policy and resolution. Minimal chat UI is now serving revision
`customer-service-multi-agent--0000004`, immutable image
`sha256:2fe74b445730dc0fcb50cb2d3de27dc9cf5fd3815d6b21358be387cb3a4a2fd7`.
Actual automatic MSAL authorization redirect and correlated denial callback passed,
including PKCE, zero return-path auth cookies and callback HTTP 200 through WAF.
Two real chat turns on revision `0000003` completed and matched displayed/stored history;
desktop/mobile and Logout checks passed in a separately labeled CLI-user test context.
Completed interactive human sign-in, consent and MFA remain unverified.
Future operator deployment still requires
the existing VPN or an authorized private runner.

## Prerequisites and targets

Non-secret targets live in [`env/sea.env`](env/sea.env). Existing Azure CLI login
must be in tenant `b10aac9b-2c9e-4cdf-a55e-c5042367b05e`, AzureCloud, active hub
subscription `1b00124c-ed9b-4d33-9bd6-4d14c09c9857`. Commands still pass explicit
subscriptions. Required local tools: Azure CLI with Container Apps/Bicep,
`dig`, `/usr/local/bin/python3`, and the app/deployment manifest dependencies
in that existing interpreter. No virtual environment is created or activated.
Use `DEPLOY_PYTHON` only to select another already provisioned interpreter.

If dependencies are absent, use `uv` against the existing interpreter:

```bash
uv pip install --python /usr/local/bin/python3 -r deploy/requirements.txt
uv pip install --python /usr/local/bin/python3 -r applications/customer-service-multi-agent/requirements.txt
```

No role assignments, provider registrations, new model deployments, shared environment
changes, or secret retrieval are performed. The separately approved `setup-browser-auth`
action creates/reconciles only the dedicated tenant-only, secretless browser registration
and adds its delegated preauthorization while preserving the existing API contract.
Existing managed identity `uami-container-apps` needs its existing ACR pull
permission and project-scoped Foundry User. An authorization denial is a
prerequisite failure, not permission to broaden access.

| Role | Existing target |
| --- | --- |
| SEA app | `d88c020a-2180-43da-91a2-f6cc01f25946` / `rg-ai-dev-sea` / `capps-env-sea` |
| Build | `acrappseaozewfizfnaft4`, managed-identity image pull |
| Hub WAF | `1b00124c-ed9b-4d33-9bd6-4d14c09c9857` / `rg-hub-sea` / `agw-thai-search-sea` |
| DNS | `azure_aiml_test_1` / `azuremew-domain.org`, new A record `customer-service-multi-agent` |
| West US 3 | `6bacd437-5d04-4afd-850e-51bdc4041496` / `rg-ai-dev-wus3` / `foundry-agent-wus3jbm3vfsrmekbg` / `agent-project` |
| Inference | Existing `gpt-4.1-mini` regional Standard deployment |

## Sequence and failure recovery

Each step is independently reachable through the same entry point:

| Action | Expected output | Failure handling |
| --- | --- | --- |
| `preflight` | Confirmed private SEA host, private West US 3 Foundry, WAF and DNS | Fix named prerequisite. No automatic grant or target switch. |
| `setup-browser-auth` | Dedicated SPA client ID and exact callbacks | Already explicitly approved for this app. Copy returned non-secret `client_id` into `BROWSER_CLIENT_ID` in `env/sea.env`; preserve API scopes, CLI preauthorization and user allowlist. |
| `vendor-msal` | Verified official MSAL Browser 4.30.0 bundle, MIT license and provenance | Requires existing npm. Refuses changed bytes; no CDN, install scripts or local dependency tree. |
| `configure-local` | Private app-local `.env`, populated from deployed non-secret settings | Requires an already-allowed Azure CLI user. Preserves differing local files; never saves tokens or grants access. |
| `provision-agents` | Matching namespaced native agent versions | Existing mismatched definitions refuse mutation. Retain agents. |
| `provision-hosted` | Native Hosted version active; downloaded six-member ZIP matches source SHA256 | Requires private data-plane connectivity. Preserves unknown outcomes and existing versions. No ACR pull grant; native source upload/remote build. |
| `verify-hosted` | Two synthetic native turns with exact stored Responses readback; anonymous 401/403 | First invocation is billable, zero POST retries. A completed matching receipt uses GET-only reconciliation with zero new inference calls. Retains accepted response IDs and unknown outcomes. |
| `verify-hosted-logs` | Native console events for all three roles and the closing `chat.workflow` row, with all 13 fields | Read only, bounded stream; retains only allowlisted structured fields, never arbitrary console payloads. |
| `build` | Focused tests pass, ACR image with `sha256` digest | Fix tests/build; never deploy an unchecked fallback image. |
| `certificate` | Local PFX path, never certificate/key bytes | Check DNS-01 visibility and ACME authorization. Reconcile before retry. |
| `start-gateway` | Existing hub WAF gateway is Running | Optional early start while building. Read actual operational state before retry. Resumes existing routes and running charges. |
| `release` | Accepted immutable image and ready revision | Inspect actual revision state. Existing shared resources stay intact. |
| `route` | Published HTTPS URL | Inspect gateway provisioning before resubmitting a pending operation. |
| `verify` | JSON containing URL, image, revision, health and anonymous refusal | Nonzero exit blocks acceptance. No auth or WAF bypass. |
| `exercise` | One actual synthetic return journey, four specialized judge results, ledger readback | Billable inference. Inspect retained run before resubmitting a failed or unknown outcome. |
| `browser-verify` | Automatic actual MSAL redirect plus two protected Hosted chat turns and desktop/mobile geometry | Existing Chrome and Playwright required. Billable inference; no TLS or caller-auth bypass. Test-only token delivery is separately labeled, never claimed as human SSO. |
| `verify-logs` | Simulation/tool/four-judge trace and three-tier metrics, plus completed chat-turn fields when available | Requires an `exercise` or earlier simulation receipt. Also checks the latest passed chat receipt. If ingestion is pending, rerun read only, not inference. |
| `observability` | App and Hosted Agent spans in `APP_INSIGHTS_NAME` | `infra/observability.bicep`: Monitoring Metrics Publisher on the component for `uami-container-apps` and the Hosted Agent instance identity; the four Azure Monitor private DNS zones linked to `AGENT_VNET` (peered to the SEA spoke holding the AMPLS endpoint); a project `AppInsights` connection. Refuses a component not tagged `project=customer-service-multi-agent`; reads back roles, links and connection to `.state/observability.json`. Run `release` afterwards so the app revision gets the secret reference. Connection string is read only by Bicep. |
| `replay --trace-id <hex32>` / `--span-id <hex16>` [`--json`] | Span tree, each agent's Cosmos record, plus the full session conversation | Read-only. Spans from App Insights (Log Analytics fallback); per-agent input/output from Cosmos `FOUNDRY_COSMOS_CONTAINER` by `trace_id` (VPN plus Cosmos data reader; otherwise a note); turn text via the app's `/api/chat/replay/{response_id}` with your delegated token. 403 means your object ID is not in `REPLAY_OPERATOR_OBJECT_IDS`; add it and `release`. "not found" right after a turn means ingestion lag (~2-5 min). |
| `workbooks` | Two shared Workbooks linked to the existing SEA Log Analytics workspace | Prevalidates all KQL panels, writes only deterministic app-owned workbook IDs, and reads exact serialized definitions back. No new monitoring resource or data retention change. |
| `generate-dataset` | Twenty LLM-generated cases and frozen manifest | Billable; refuses to overwrite the cohort. Version a changed dataset explicitly. |
| `validate-dataset` | Matching case, policy, taxonomy and freshness pins | Offline; failures block use of stale or changed fixtures. |
| `regression` | Calibrated gold comparison or explicit blocked report | Missing genuine calibration/gold fails before inference. No illustrative baseline substitution. |
| `publish --destination <external-path> --push --session-id <current-session>` | Allowlisted standalone commit and push | Refuses a dirty staging clone, wrong remote or credential-shaped source. Never changes this repository's remote. |
| `status` | Latest ready revision and gateway operational state | Read only; not full acceptance. |

`build` runs app and deployment tests and hashes reviewed application inputs; ACR receives only the app's
allowlisted Docker build context. Runtime uses the immutable manifest digest.
CPU is 0.5, memory 1 GiB, replicas 0-1. The existing environment is internal;
ingress accepts only `10.0.5.0/24` (hub gateway) and `10.0.3.0/26` (dedicated
hub firewall nodes). Existing hub policy forces SNAT, so allowing only the
gateway subnet or the firewall's frontend `.4` address rejects real probes.
Private callers traversing that trusted firewall are still subject to application
Entra authorization; this is not a claim that every private caller traverses WAF.
The NSG TLS rule must target the dedicated gateway subnet, not its public IP,
per Application Gateway infrastructure requirements. The host-specific
HTTP rule redirects to HTTPS; the existing catch-all Thai search route and its
priority remain unchanged. WAF remains enabled in Prevention mode.

Hosted source deployment uses installed Projects SDK 2.3.0, Python 3.13 remote build,
0.5 CPU / 1 GiB and Responses protocol 2.0.0. Hosting dependencies are separately pinned
under the application's `hosted/requirements.txt`. The ZIP contains only `main.py`,
`runtime.py`, `validation.py`, `requirements.txt`, canonical `scenarios.py` and `telemetry.py`.
Private/local environment files, tests and Dockerfiles are excluded. After active/source
readback, copy the returned `name` and `version` into `HOSTED_AGENT_NAME` and
`HOSTED_AGENT_VERSION` in `env/sea.env`; independent releases require the matching receipt.
The all-in-one `deploy` command passes a newly verified pin to its same-process release;
record those non-secret target fields before subsequent independent releases.
The Hosted platform supplies its runtime identity. The SEA CApp retains `uami-container-apps`
for outgoing invocation, and the existing model remains a separate deployment.

The new hostname uses a publicly trusted Let's Encrypt DNS-01 certificate.
Issuance accepts the CA terms for this hostname. Private account/key/PFX material
is kept mode 0600 in `~/.local/share/customer-service-multi-agent/tls`, never in
the repository, image, logs, or evidence. `route` renews certificates with fewer
than 21 days remaining, then uploads the new PFX directly to the gateway. Rerun
`route` at least every 30 days; automatic renewal scheduling is not installed.
The deployment certificate owner is the operator. Do not delete these files
without arranging account recovery and future renewal.

The small certificate helper implements only the required ACME DNS-01 flow
using the existing `httpx` and `cryptography` packages. Installing the declared
ACME SDK was attempted but the package host was unreachable from this operator
machine; no alternate package manager, TLS bypass, or new environment was used.
Certificate signing, nonce handling and invalid-authorization refusal have
focused checks; live CA validation is separate from those checks.

## Authentication and synthetic simulations

Existing tenant-only registration `MCP User Data API`
(`b2d8ec71-c3b4-4005-a492-08b9bdab3414`) already preauthorizes Azure CLI for
`access_as_user`. This app additionally restricts object IDs to the deploying
human on first creation; later releases preserve that allowlist.
The dedicated browser SPA `722e2f80-ccb1-4ba0-93a5-d36514a955ae` is additionally
preauthorized for the same scope. API identifier URI, v2 tokens, scope definitions
and Azure CLI preauthorization are preserved.
The managed identity authenticates outgoing Foundry calls, not incoming users.

The minimal UI automatically redirects to Microsoft sign-in using official vendored MSAL
and authorization-code PKCE. No sign-in button, token field or client secret.
Registered callbacks are the verified HTTPS
hostname's `/auth/callback` and `http://localhost:8080/auth/callback`.
Browser tokens stay in memory. Transient PKCE/redirect state survives navigation in
tab-scoped sessionStorage. MSAL 4.30.0 requires `storeAuthStateInCookie:true` to permit
MemoryStorage redirects, but a supported `NavigationClient` hook removes its generated
compatibility cookies before external navigation. These cookies are not needed on the
wire because sessionStorage retains the state, and their presence causes the hub WAF to
reject the callback. No policy exclusion or authentication bypass is introduced.
The CApp independently validates
the delegated access token and existing user allowlist. No token belongs in shell
history, URLs, files or logs. Workload managed identity remains exclusively the
outgoing CApp-to-Foundry credential, not a substitute for human authentication.
Logout clears local account/token/history and requests the tenant end-session endpoint.
A non-secret tab-only logged-out marker prevents immediate automatic re-login; Continue
with Microsoft is available only after logout or an authentication error.

`browser-verify` first loads the actual vendored SDK and checks the automatically initiated
Microsoft authorization redirect, tenant, client, callback, delegated scope, code and PKCE S256,
without entering credentials. A separate test-only browser context
then substitutes the SDK response with the current CLI user's delegated token in memory
to operate real protected APIs. This proves UI/API plumbing, **not completed human SSO,
consent or MFA**; `interactive_human_signin_verified` remains false. When Hosted targets
are configured, the same verifier operates two actual chat turns and checks
owner-bound persisted history. No POST is automatically retried.
Authorization navigation is intercepted with HTTP 204 after observing the exact request,
keeping the initiating document available for storage inspection. Tokens are absent from
local/session storage; generated MSAL cookies are gone before external navigation. The
probe requires a successful callback GET with the actual browser cookie state, then
returns a correlated synthetic `access_denied` fragment to the real SDK. Its specific
denial handling proves callback state restoration without credentials or a token exchange.
Callback/logout cleanup is also covered by the local browser harness. Microsoft's logout response is separately
intercepted with 204 to inspect the cleared UI, not claimed as a completed human logout.

Only synthetic customer fixtures are permitted. Agent calls and judge calls
consume the existing model quota and are billable. The demo has no authority to
issue real refunds, modify real orders, or ingest customer records. Judge results
are quality estimates, not customer satisfaction measurements.

## Logging and scorecards

Container stdout JSON enters the existing
`workspace-spoke-app-sea` through environment logging. Its observed retention
on 2026-10-17 is **180 days**, not the Learn example's 90-day policy. This release
does not change shared retention. Logs exclude prompts, response prose,
credentials, and customer identifiers. Session correlation uses a SHA-256
pseudonym and spans carry W3C trace correlation.

Callable scorecards aggregate system -> journey type -> per-agent components.
The simplified chat UI deliberately omits dashboard controls.
System and journey metrics use explicit attempts, completion criteria and
validated judge scores. Agent task accuracy must use evaluated component labels,
not `1 - error_rate`. Token totals and latency/error statistics include failures
with their proper denominators. Resolution/reopen business impact remains
unknown without customer feedback and follow-up observation.

[`metric-hierarchy.kql`](metric-hierarchy.kql) provides the same three tiers
over persisted lifecycle snapshots. It selects the last snapshot per run before
aggregation, so queued/completed logs do not double-count attempts. Independent
correctness labels remain a separate denominator from agent errors.
The latest readback contains both deployed chat-turn traces with all 13 required fields
and the existing 17 simulation metric rows across all three tiers. Chat advice is not
automatically judged or included in those simulation quality scorecards. Native Hosted
role telemetry is read independently through `verify-hosted-logs`, not assumed to be
present in the SEA Container App's console table.

Shared Azure Monitor Workbooks are deployed in the SEA app resource group:

- [Quality hierarchy](https://portal.azure.com/#resource/subscriptions/d88c020a-2180-43da-91a2-f6cc01f25946/resourceGroups/rg-ai-dev-sea/providers/Microsoft.Insights/workbooks/477ac8c9-7726-5e4a-9e7d-cf5ac39e049a):
  system, journey and per-agent metrics.
- [Operations](https://portal.azure.com/#resource/subscriptions/d88c020a-2180-43da-91a2-f6cc01f25946/resourceGroups/rg-ai-dev-sea/providers/Microsoft.Insights/workbooks/096caff1-5803-5f77-a4d6-d9eb4f8635cd):
  event volume, outcomes/latency, provider-reported token use, field completeness,
  safe errors and trace-correlated events.

All nine panel queries were executed against the workspace before deployment and returned
rows. Workbook definitions were read back with `canFetchContent=true` and matched exactly.
Portal rendering was not independently browser-verified. `bash deploy/deploy.sh -e sea
workbooks` safely updates these owned definitions; workbook data window is 7 days and
workspace retention is 180 days.

The app does not connect to Cosmos DB; no app code writes to the Foundry-associated
`enterprise_memory` containers. Foundry itself stores Responses there: container
`2d09d4a7-…-run-state-v1` (`FOUNDRY_COSMOS_CONTAINER`) holds the user-facing hosted turn
(`caresp_*`) and, from hosted version 3, each sub-agent call (`resp_*`, `store: true`) tagged in
`object.metadata` with `trace_id`, `span_id`, `agent_id`, `agent_step` and `session_id`. The
same `span_id` and `response_id` sit on the `chat.agent` span, so either side finds the other;
queries are in [`trace-explorer-cosmos.sql`](trace-explorer-cosmos.sql) (VPN plus Cosmos data
reader). Foundry owns that schema, so treat it as a read-only debugging view. App chat history currently
lives in local SQLite (`/tmp/customer-service.sqlite3`) and may disappear when its
Container App replica restarts or scales to zero. Foundry Hosted stored Responses are
separately read back by response ID; `chat.turn` rows record that `response_id` next to
`trace_id`. One trace spans the Container App and the Hosted triage/policy/resolution steps
(shared `trace_id` and baggage-propagated `session_id`; a Foundry gateway span sits between
`chat.turn` and `chat.workflow`, so join on `trace_id`); query it with
[`trace-explorer.kql`](trace-explorer.kql) here and `verify-hosted-logs` for hosted rows.
Spans export to Application Insights `appi-tracing-xlpu` (workspace `law-tracing-xlpu`)
through its SEA private link, Entra auth only; see `observability` below and
[`trace-explorer-appinsights.kql`](trace-explorer-appinsights.kql). Do not treat an empty Cosmos Data Explorer as evidence that Hosted inference
failed; confirm execution in Foundry sessions/Responses and sanitized telemetry here.

The frozen twenty-case cohort, four early canaries and four authored failure
safeguards live in the app's `datasets/` directory. They are not a 400-case
benchmark or observed historical incidents. No gold baseline or human
calibration has been established. See the app's `REGRESSION.md` for promotion,
seven-day drift comparisons and prerequisites.
Sampling/drift utilities require supplied observations; no automatic production
sampling or scheduled drift monitor is installed.

## Source publication and CI

**Paused by the user:** do not push additional GitHub commits or implement/execute CI/CD
for this increment. Previously published source and existing workflows remain untouched;
local/Azure deployment verification continues independently.

Standalone publication exports only the application, synthetic dataset,
deployment owner and dedicated workflow, not the original landing-zone
worktree. The authorized destination is
<https://github.com/edsml-kl121/customer-service-production-multi-agent-azure>.
The exporter rejects private keys and common credential shapes and excludes
local state, result evidence, databases, caches and symlinks.

```bash
bash deploy/deploy.sh -e sea publish --destination /absolute/external/staging-path --push --session-id <current-copilot-session-id>
```

GitHub-hosted CI runs offline checks. Live evaluation/deployment is opt-in and
requires a private-network self-hosted runner, existing Azure OIDC federation
and narrowly scoped permissions, an execution context able to use the configured
managed identity for native inference, the optional Evaluation SDK and genuine
calibrated gold. This deployment creates none of those access prerequisites.
An absent baseline blocks promotion; synthetic smoke scores cannot replace it.

Useful Log Analytics starting query:

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "customer-service-multi-agent"
| extend event = parse_json(Log_s)
| where isnotempty(event.trace_id)
| project TimeGenerated, trace_id=tostring(event.trace_id),
    span_id=tostring(event.span_id), agent_id=tostring(event.agent_id),
    journey_type=tostring(event.journey_type),
    operation_type=tostring(event.operation_type), status=tostring(event.status),
    latency_ms=todouble(event.latency_ms),
    input_tokens=tolong(event.input_token_count),
    output_tokens=tolong(event.output_token_count)
| order by TimeGenerated asc
```

## State, recovery and retirement

Gateway outage on 2026-10-18: Azure Activity Log attributes an explicit
`Microsoft.Network/applicationGateways/stop/action` to service principal
`MCAPSGovernance-AutomationApp` (application ID `a1a9c5b6-7a4f-4288-89ab-6805873f65d1`).
The stop began at `2026-10-17T17:50:29Z` and completed at `17:52:05Z`
(18 October 00:52 UTC+7), while the Container App stayed running and DNS stayed correct.
This was a governance-automation stop, not application scale-to-zero or a login failure.
Its specific policy, schedule and business reason are unknown from the activity record.
The user approved gateway restart on 2026-10-18. `start-gateway` then `verify`
restored Running state and external HTTPS 200 at `2026-10-18T09:43:41Z`,
with revision `0000004`, anonymous/forged 401 and the WAF attack probe still 403.
Preventing recurrence requires the governance owner to review its automation; this
deployment does not change or bypass that policy.

Login callback 403 diagnosis: a controlled callback GET returned 200 without cookies and
403 with the real SDK's four temporary auth-state cookies. Gateway diagnostic settings
were absent, so the individual managed rule ID is unknown; no logging/policy setting was
changed. Outbound redirect-only checks had missed this return-path failure.
The repair removes compatibility cookies before external navigation and keeps PKCE state
in the existing tab session. Browsers retaining cookies from the failed version must clear
this site's cookies once or open a fresh Incognito/InPrivate session, then start at `/`,
not reuse the old callback URL or authorization code.

Latest chat release: `customer-service-multi-agent--0000004`,
image digest `sha256:2fe74b445730dc0fcb50cb2d3de27dc9cf5fd3815d6b21358be387cb3a4a2fd7`.
Readback on 2026-10-17 confirms the dedicated SPA client, explicit
`AZURE_AUTH_MODE=managed_identity`, existing workload identity, unchanged local/deployed
allowlist configuration, ready revision, WAF refusal and HTTPS redirect.
`hosted_chat_configured:true`, pinned to active `cs-customer-service-chat:1`.
Automatic redirect uses the real MSAL SDK and PKCE, not a popup; completed human SSO
remains unverified. Current real-SDK acceptance also restores session state and handles a
synthetic denied callback through WAF with HTTP 200; zero new model calls were needed.
The supplied account is already on the deployed allowlist; no permissions changed.
On revision `0000003`, separately labeled CLI-user UI verification completed two actual Hosted
turns with exact history readback, desktop/mobile geometry and local Logout cleanup.
Chat traces `f93d55bb0c989110bc2066804a95c06a` and
`fcb9f0d0b72dfe4e838ade25d9a73c44` each contain two persisted events with all 13 fields.
Earlier synthetic SGD49 billing workflow verification remains separate. Its persisted
trace `5dcb47de0a96bbd20f847933d122c4ae` contains 16 events with all 13 required fields;
Log Analytics returned all three scorecard tiers. No real payment was executed.

Non-secret local build/readback receipts live in ignored `deploy/.state/`.
They identify the exact checked source/image/revision and are not credentials.
Copy approved receipts to the owning deployment record if durable operational
retention is needed. App result retention limits are documented in its README.

`teardown` deliberately refuses: no destructive authority was supplied.
Retirement must name the app, its namespaced agents, A record, certificate, and
`customer-service-*` gateway components. Never delete the shared gateway,
registry, identity, environment, Foundry project, resource groups, or DNS zone.
Do not run the root landing-zone teardown for this application.
