# Current Azure AI Landing Zone

SEA baseline captured from Azure CLI on 2026-08-27. The regional agent spoke
was verified on 2026-10-14; the dual-region app/agents were updated on
2026-10-15. All four subscriptions are in Microsoft Entra
tenant `b10aac9b-2c9e-4cdf-a55e-c5042367b05e`.

## Scope map

| Role | Subscription name | Subscription ID | Resource group | Region | VNet | Address space |
|---|---|---|---|---|---|---|
| Connectivity hub | `ME-MngEnvMCAP953893-kandanail-2` | `1b00124c-ed9b-4d33-9bd6-4d14c09c9857` | `rg-hub-sea` | Southeast Asia | `vnet-hub-2` | `10.0.0.0/16` |
| Workload spoke | `ME-MngEnvMCAP953893-kandanail-1` | `d88c020a-2180-43da-91a2-f6cc01f25946` | `rg-ai-dev-sea` | Southeast Asia | `vnet-spoke-app-sea` | `10.10.0.0/16` |
| AI Gateway hub | `ME-MngEnvMCAP953893-kandanail-3` | `0d04b43f-7d15-40fd-8aa5-830f71ab0d80` | `rg-ai-gateway-sea` | Southeast Asia | `vnet-ai-gateway-sea` | `10.20.0.0/16` |
| Regional agent spoke | `ME-MngEnvMCAP953893-kandanail-5` | `6bacd437-5d04-4afd-850e-51bdc4041496` | `rg-ai-dev-wus3` | West US 3 | `vnet-spoke-agent-wus3` | `10.80.0.0/16` |

At capture time, each resource group's provisioning state was `Succeeded`.

## Connectivity hub

The hub owns shared connectivity and name resolution:

- Active-active VPN gateway: `hub-VNetGw-sea-dev`.
- Point-to-site client range: `172.16.0.0/24` in checked-in configuration.
- DNS Private Resolver: `dns-resolver-hub`, with inbound endpoint
  `10.0.2.4` in checked-in configuration.
- Central private DNS zones for Blob, Queue, Table, Cosmos DB, SQL, Search,
  Cognitive Services, Azure OpenAI, Azure AI Services, Event Hubs/Service Bus,
  Managed Redis, Key Vault, and the private Container Apps environment domain.
- The private DNS zones are linked to the hub, workload spoke, and AI Gateway
  VNets where applicable.
- Application Gateway `agw-thai-search-sea` is now in `rg-hub-sea`, with its
  existing WAF policy enabled in Prevention mode. It was **Stopped** on
  2026-10-14 and verified **Running** on 2026-10-15, with HTTP 200 on the
  app health endpoint. The agent changes did not start or stop it.
  The customer-service deployment found it stopped and started it on
  2026-10-17. HTTPS/WAF/auth acceptance passed that day; existing routes
  were preserved.

Subnets:

| Subnet | Prefix | Purpose |
|---|---|---|
| `default` | `10.0.0.0/24` | General hub network |
| `GatewaySubnet` | `10.0.1.0/27` | VPN gateway |
| `DnsResolverInboundSubnet` | `10.0.2.0/28` | DNS resolver inbound endpoint |
| `AzureFirewallSubnet` | `10.0.3.0/26` | Deployed firewall nodes; forced SNAT verified 2026-10-17 |
| `AzureFirewallManagementSubnet` | `10.0.4.0/26` | Firewall management |
| `snet-appgw` | `10.0.5.0/24` | Application Gateway WAF `agw-thai-search-sea` |

## Workload spoke

The spoke hosts application, AI, and data workloads. Key deployed resources
include:

- Internal Container Apps environment `capps-env-sea`.
- Container Apps `fe-app`, `fe-app2`, `be-app`, `be-app2`,
  `thai-surname-search`, `petstore-mcp-api`, `math-mcp-server`, and
  `entra-user-data-api`.
- `customer-service-multi-agent`, verified 2026-10-17 at
  <https://customer-service-multi-agent.azuremew-domain.org>, with 0.5 CPU,
  1 GiB and replicas 0-1. Hub WAF terminates trusted TLS and forwards through
  the existing forced-SNAT firewall path to private ACA ingress. Only the
  dedicated gateway/firewall source subnets are allowed; API authorization
  separately requires a tenant token, delegated scope and project allowlist.
  Three business agents and four specialized judges use the existing private
  West US 3 project and regional `gpt-4.1-mini` deployment. Native billing and
  return simulations and structured Log Analytics ingestion were observed.
  Gold calibration and live CI remain blocked by external prerequisites.
  The owning release/readback procedure is root `deploy/README.md`.
- Foundry accounts `foundry-app-seaozewfizfnaft4` and
  `foundry-agent-seaozewfizfnaft4`, with projects `firstProject` and
  `projectrbjp`.
- Azure AI Search `search-foundry-seaozewfizfnaft4`.
- Cosmos DB accounts `cosmos-foundry-seaozewfizfnaft4` and
  `cosmos-ragstore-seaozewfizfnaft4`.
- Function App `funcapp-spoke-sea`.
- Azure SQL server `sql-thai-search-sea-ozewfizfnaft4` with database
  `thai-search-db`, plus a Basic elastic pool `thai-search-pool-sea`
  (50 eDTU) hosting demo database `thai-search-pool-demo-db`.
- Azure Database for PostgreSQL Flexible Server
  `pg-thai-search-sea-ozewfizfnaft4` (Burstable `Standard_B1ms`, 32GB,
  Entra-only auth, private endpoint), database `thai-search-pg-db`.
- Container Registry `acrappseaozewfizfnaft4`.
- Linux VMs `myVm` and `vm-2`.
- Log Analytics workspace `workspace-spoke-app-sea`.

Most data-plane services use private endpoints in `snet-pe`. Public ingress for
the Thai surname application is through Application Gateway WAF while the
Container Apps environment remains internal.

Subnets:

| Subnet | Prefix | Purpose |
|---|---|---|
| `AzureBastionSubnet` | `10.10.0.0/26` | Optional Bastion |
| `snet-vm` | `10.10.1.0/24` | Virtual machines |
| `snet-containerapps` | `10.10.2.0/23` | Internal Container Apps environment |
| `snet-functionapp` | `10.10.4.0/24` | Function App integration |
| `snet-agent` | `10.10.5.0/24` | Dedicated Foundry agent network |
| `snet-pe` | `10.10.6.0/24` | Private endpoints |
| `snet-claimpilot-aca` | `10.10.8.0/23` | Claimpilot Container Apps workload |

Live verification on 2026-10-14 found `foundry-agent-vnet-seaxlpu` with project
`agent-vnet-projectxlpu`, agent injection into `snet-agent`, and a succeeded
`caphostproj` connected to the existing SEA Search, Blob, and Cosmos accounts.

The `thai-surname-search` app includes **Option 6: Private Foundry agents,
matched regional comparisons**, with image tag
`matched-regions-20261015-v3`.
Revision `thai-surname-search--0000012` is healthy with 100% traffic.
It uses the existing `uami-container-apps` managed
identity (`66173777-740f-49b0-a5c0-6080f29367b3`) with Foundry User scoped to the
West US 3 and SEA projects. The existing DNS entry is
`http://thai-search-sea-ozewfizfnaft4.southeastasia.cloudapp.azure.com`.
Both projects have active new-API `regional-latency-agent:1` agents using
Conversations/streaming Responses, not Classic Assistants. Their instructions,
temperature `0`, and readiness-document content match. Each has a separate
file-search vector store:

| Endpoint region | Project | Model/version | SKU | Vector store |
|---|---|---|---|---|
| West US 3 | `agent-project` | `gpt-4.1-mini` / `2025-04-14` | Standard (regional) | `vs_ybtpgTj8mRJneK0V6ej77j4X` |
| West US 3, SKU comparison | `agent-project` | `gpt-4.1-mini` / `2025-04-14` | GlobalStandard | `vs_ybtpgTj8mRJneK0V6ej77j4X` (shared) |
| SEA | `agent-vnet-projectxlpu` | `gpt-4.1-mini` / `2025-04-14` | GlobalStandard | `vs_hUcMsgTuLs02BwIJb87YwXOy` |

The UI offers only **Global Standard West US 3 vs Global Standard SEA** (default)
and **Standard SEA vs Standard West US 3**. The latter is explicitly unavailable:
on 2026-10-15 both SEA account and regional catalogs offered Standard only for
`text-embedding-3-large`, not a chat model. No different-SKU/model/region fallback
is used; reserved `seaStandardAgentName`/`seaStandardAgentVersion` stay empty.
Existing West Standard and all agents/files/stores remain retained.

`sku-global-latency-agent:1` copies West `regional-latency-agent:1`,
changing only the model reference to `gpt-4.1-mini-global`. The two West US 3
deployments match in base model/version, capacity 10, limits (10 RPM / 10,000 TPM),
content policy `Microsoft.DefaultV2`, and upgrade policy
`OnceNewDefaultVersionAvailable`. Resource-group deployment `agent-sku-comparison`
is succeeded, using `bicep/agent-sku-comparison.bicep`; no account, capability
host, network or role changes were needed.

Matched regional comparisons default to model-only (`tool_choice=none`).
The Global pair's actual agent/deployment metadata is checked before calls
(cached five minutes): same SKU, base model/version/publisher, capacity,
instructions/temperature/tools and corpus hash; regional store IDs may differ.
An optional full agent workload uses identical document bytes. Fresh pairs alternate starting
order; CSV captures workload, order, token/cache/tool counts and warm-up/pair
completeness. Medians use complete non-warm-up pairs only, separately by mode
and workload. Primary API timings cover the Responses API stream and first text
delta, excluding client/conversation setup; the original full app totals remain.
This prevents first-call identity setup from being confused with a model-serving
difference. Global inference location, load and service behavior are not fixed.

The in-app flow diagram shows browser -> hub Gateway/WAF -> SEA app, then
same-VNet SEA access or direct global peering to West. Backend boxes are logical
services outside VNet boundaries; Global inference serving location is unknown.
Only the last complete non-warm-up current-mode/workload pair supplies API,
first-text and full-app times; unmeasured hops are not assigned invented values.
The additive timeline is setup + API wait-to-first-text + remaining stream +
local processing. Coarse server timestamps overlap rather than add.
The diagram is downloadable as editable Excalidraw JSON.

USD retail checked 2026-10-15: global peering is SEA $0.09/GB + West
$0.035/GB across both endpoints, plus first-tier destination Private Link
$0.01/GB. Same-VNet SEA has only the latter on this leg. Requests + responses
count once: 1 GB each direction is approximately $0.27 West versus $0.02 SEA.
An explicit assumed-volume calculator and observed Responses HTTP-body bytes
show approximate variable costs, not Azure billing telemetry. Protocol/auth/
conversation overhead, fixed existing endpoint hours, model/tools/data/compute
and common browser/Gateway/hub paths are excluded. No generic inter-region
bandwidth or invented hidden Global inference peering charges are added.
Standard comparison estimates remain hypothetical while its SEA deployment is missing.

On 2026-10-15 at 06:50-06:51 UTC, the final image passed 54 targeted tests
inside the SEA container. A real UI warm-up pair plus two measured Global/Global
pairs succeeded, including alternating order, positive request/stream byte
counters, additive timings and medians excluding warm-up. Both Global
deployments also match `Microsoft.DefaultV2`, automatic upgrade policy,
10 RPM and 10,000 TPM. Actual generated lengths varied (one West response
used 67 output tokens, others 29); observations are not performance guarantees.
The public Gateway/WAF browser rendered the diagram and both exact mode choices,
with Standard explicitly unavailable and its call button disabled.
Public health returned HTTP 200. Identity, ingress, scaling, Gateway and DNS
were preserved, and only temporary verification conversations were deleted.
The renderer uses native `st.iframe` when available, retaining older Streamlit
compatibility. Existing agents/files/stores are unchanged.

Historical same-West comparison, no longer a UI choice: at 06:03 UTC on
2026-10-15, revision 9 passed 44 targeted tests, and the
real SEA app form called both West US 3 agents with 1,016 input tokens, 29 output
tokens, zero cached input tokens and zero file-search calls on each side:

| SKU | Responses API time | Responses API first token | Full app time |
|---|---|---|---|
| Standard | 2.09 s | 1.42 s | 3.68 s |
| GlobalStandard | 2.23 s | 1.51 s | 2.51 s |

These are individual observations, not performance guarantees. Different
one-time setup costs explain why the full app ordering differs from the primary
API ordering. The new Global Standard agent also returned the readiness code
with citations using the original shared store. All six app sections rendered,
the former mixed-SKU region mode was then available, and only temporary verification
conversations were deleted. The original agents/files/stores remain.

SEA's catalog did not offer Standard chat-model deployments. GlobalStandard
does not guarantee inference in SEA; the app explicitly flags this constraint.
The added SEA model has capacity 10; existing SEA model deployments remain.
The replaced mixed-SKU region mode previously captured total response time,
first-token time, token usage and CSV measurements.
An explicit five-connection TCP probe measures the selected endpoint's transport
baseline without calling the model. Server/app timings are not pure network
latency and exclude browser/Gateway/WAF traffic.

A historical mixed-SKU paired submission from the running SEA container on 2026-10-15
returned the readiness code with file citations from both new agents. All six
app sections rendered without errors. One fresh-pair example, captured at
05:06-05:07 UTC:

| Target endpoint | TCP median (5 connections) | Full app response | App-observed first token |
|---|---|---|---|
| West US 3 | 178.96 ms | 5.93 s | 5.23 s |
| SEA | 3.51 ms | 8.99 s | 7.89 s |

These are individual observations, not performance guarantees. The longer SEA
response despite its lower connection latency illustrates why service/model
work, GlobalStandard routing, cold setup and network time must not be conflated.
The earlier dual-region image passed 31 targeted service/UI/provisioning tests.
Public Gateway/WAF health returned HTTP 200. Temporary verification conversations
were removed; new and original agents, files and vector stores remain.

## West US 3 agent spoke

Completed and verified on 2026-10-14 after the user authorized relocation
from Sweden Central. `bicep/agent-spoke.bicep` is the separate deployment
entry point; subscription deployment `agent-standard-westus3` is `Succeeded`.

| Resource | Name | Configuration |
|---|---|---|
| Foundry account | `foundry-agent-wus3jbm3vfsrmekbg` | S0, agent VNet injection, system-assigned identity |
| Foundry project | `agent-project` | Three AAD data-service connections; succeeded `caphostproj` |
| Model deployment | `gpt-4.1-mini` | Regional Standard, version `2025-04-14`, capacity 10 |
| AI Search | `search-foundry-wus3jbm3vfsrmekbg` | Basic |
| Blob Storage | `stfoundryjbm3vfsrmekbg` | Standard LRS |
| Cosmos DB | `cosmos-foundry-wus3jbm3vfsrmekbg` | Serverless, `enterprise_memory` database |

- VNet `vnet-spoke-agent-wus3` is `10.80.0.0/16`.
- `snet-agent` is `10.80.5.0/24`, delegated to `Microsoft.App/environments`.
- `snet-pe` is `10.80.6.0/24`, containing four succeeded, approved private endpoints.
- All four services are in West US 3 with public network access disabled.
  Foundry, Blob, and Cosmos also disable local/key authentication.
- Six existing hub private DNS zones are linked to the VNet: Blob, Cosmos,
  Search, Cognitive Services, OpenAI, and AI Services.
- Reciprocal hub peerings `hub-to-vnet-spoke-agent-wus3` and
  `vnet-spoke-agent-wus3-to-hub` are `Connected`, with gateway transit and
  the hub's remote VPN gateway enabled respectively.
- Reciprocal SEA peerings `vnet-spoke-app-sea-to-wus3` and
  `vnet-spoke-agent-wus3-to-sea` are `Connected`. No AI Gateway peering was added.
- There is no additional application compute, gateway, firewall, or monitoring.

Project endpoint:
`https://foundry-agent-wus3jbm3vfsrmekbg.services.ai.azure.com/api/projects/agent-project`.
VPN-connected testing verified private DNS and TCP 443 for all six service
hostnames, Blob upload, Search vector indexing, Cosmos-backed conversation
storage, and a successful agent file-search response with a source citation.
Temporary test files, vector store, agent, and thread were deleted.

Subsequent Classic smoke-test runs retained their agents and supporting
files/vector stores at the user's request, including
`asst_oSWnjBuZtreXUb7GWomjjfv4` and `asst_kTb2Ma9FYLM71IbV5rzkzw8H`.
They remain untouched, but the app now invokes the new versioned agent instead.
Foundry resolves privately to `10.80.6.10` in West US 3 and `10.10.6.26` in SEA.

Regional provisioning, rather than quota alone, determined the location:
Sweden Central rejected Search Basic and S1; East US allowed Search but
rejected Cosmos for demand/region access; East US 2 allowed Cosmos but rejected
Search Basic and S1. West US 3 successfully provisioned the complete colocated
standard-agent setup.

The empty former resource groups `rg-ai-dev-swc`, `rg-ai-dev-eus`, and
`rg-ai-dev-eus2` were deleted after replacement verification. Their four
external hub/SEA peerings, twelve hub DNS VNet links, and private DNS A records
were removed. No application data needed migration.

## AI Gateway hub

The dedicated AI Gateway subscription separates shared AI quota, governance,
and chargeback from workload subscriptions. Key deployed resources include:

- APIM Standard V2 `apim-hub-sea2uy4dibzgdn34`.
- Shared Foundry account `aif-hub-sea2uy4dibzgdn34` and project
  `aiGatewayHubProject`.
- Azure Managed Redis `redis-hub-sea-2uy4dibzgdn34` for semantic caching.
- Event Hubs namespace `evhns-hub-sea-2uy4dibzgdn34`.
- Cosmos DB account `cosmos-hub-sea2uy4dibzgdn34` for usage and chargeback.
- Key Vault `kv-aigw-2uy4dibzgdn34`.
- Storage account `stlogicaigw2uy4dibzgdn34`.
- Logic Apps Standard supporting resources with the
  `logic-hub-usage-sea` naming prefix.
- API Center `apic-hub-sea2uy4dibzgdn34`, deployed in Central India because
  API Center is unavailable in Southeast Asia.
- Log Analytics workspace `workspace-ai-gateway-sea`.
- Application Insights `appi-apim-sea`.

Subnets:

| Subnet | Prefix | Purpose |
|---|---|---|
| `snet-apim-outbound` | `10.20.0.0/26` | APIM outbound VNet integration |
| `snet-pe` | `10.20.1.0/24` | Private endpoints |
| `snet-logicapp` | `10.20.2.0/26` | Logic Apps Standard integration |

## Peering map

All six SEA directional peerings were `Connected` in the baseline:

- Hub to workload spoke and workload spoke to hub.
- Hub to AI Gateway and AI Gateway to hub.
- Workload spoke to AI Gateway and AI Gateway to workload spoke.

The direct spoke-to-gateway peering is required because Azure VNet peering is
not transitive. It allows APIM to reach internal Container Apps APIs in the
workload spoke.

The regional agent spoke adds four verified `Connected` global peerings:
hub/West US 3 and SEA workload/West US 3, in both directions. It does not
provide transitive connectivity from the AI Gateway VNet.

## Source of truth

- Live state: refresh with `../scripts/summarize.sh` from this reference
  directory, or use the command documented in `SKILL.md`.
- Deployment intent: `bicep/main.bicep` for SEA and `bicep/agent-spoke.bicep`
  for the regional agent spoke.
- Checked-in hub and spoke IDs/RGs: `bicep/parameters/main.json`.
- Architecture rationale: `ARCHITECTURE.md` and
  `docs/ai-gateway-landing-zone.md`.
