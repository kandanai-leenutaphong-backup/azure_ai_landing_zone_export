# Current Azure AI Landing Zone

Snapshot captured from Azure CLI on 2026-08-27. All three subscriptions are in
Microsoft Entra tenant `b10aac9b-2c9e-4cdf-a55e-c5042367b05e`.

## Scope map

| Role | Subscription name | Subscription ID | Resource group | Region | VNet | Address space |
|---|---|---|---|---|---|---|
| Connectivity hub | `ME-MngEnvMCAP953893-kandanail-2` | `1b00124c-ed9b-4d33-9bd6-4d14c09c9857` | `rg-hub-sea` | Southeast Asia | `vnet-hub-2` | `10.0.0.0/16` |
| Workload spoke | `ME-MngEnvMCAP953893-kandanail-1` | `d88c020a-2180-43da-91a2-f6cc01f25946` | `rg-ai-dev-sea` | Southeast Asia | `vnet-spoke-app-sea` | `10.10.0.0/16` |
| AI Gateway hub | `ME-MngEnvMCAP953893-kandanail-3` | `0d04b43f-7d15-40fd-8aa5-830f71ab0d80` | `rg-ai-gateway-sea` | Southeast Asia | `vnet-ai-gateway-sea` | `10.20.0.0/16` |

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

Subnets:

| Subnet | Prefix | Purpose |
|---|---|---|
| `default` | `10.0.0.0/24` | General hub network |
| `GatewaySubnet` | `10.0.1.0/27` | VPN gateway |
| `DnsResolverInboundSubnet` | `10.0.2.0/28` | DNS resolver inbound endpoint |

## Workload spoke

The spoke hosts application, AI, and data workloads. Key deployed resources
include:

- Internal Container Apps environment `capps-env-sea`.
- Container Apps `fe-app`, `fe-app2`, `be-app`, `be-app2`,
  `thai-surname-search`, `petstore-mcp-api`, `math-mcp-server`, and
  `entra-user-data-api`.
- Foundry accounts `foundry-app-seaozewfizfnaft4` and
  `foundry-agent-seaozewfizfnaft4`, with projects `firstProject` and
  `projectrbjp`.
- Azure AI Search `search-foundry-seaozewfizfnaft4`.
- Cosmos DB accounts `cosmos-foundry-seaozewfizfnaft4` and
  `cosmos-ragstore-seaozewfizfnaft4`.
- Function App `funcapp-spoke-sea`.
- Azure SQL server `sql-thai-search-sea-ozewfizfnaft4` and database
  `thai-search-db`.
- Application Gateway WAF `agw-thai-search-sea`.
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
| `snet-appgw` | `10.10.7.0/24` | Application Gateway |
| `snet-claimpilot-aca` | `10.10.8.0/23` | Claimpilot Container Apps workload |

The repository documentation notes that `snet-agent` exists but is not yet
wired to Foundry through `networkInjections`.

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

All six directional peerings were `Connected` at capture time:

- Hub to workload spoke and workload spoke to hub.
- Hub to AI Gateway and AI Gateway to hub.
- Workload spoke to AI Gateway and AI Gateway to workload spoke.

The direct spoke-to-gateway peering is required because Azure VNet peering is
not transitive. It allows APIM to reach internal Container Apps APIs in the
workload spoke.

## Source of truth

- Live state: refresh with `../scripts/summarize.sh` from this reference
  directory, or use the command documented in `SKILL.md`.
- Deployment intent: `bicep/main.bicep`.
- Checked-in hub and spoke IDs/RGs: `bicep/parameters/main.json`.
- Architecture rationale: `ARCHITECTURE.md` and
  `docs/ai-gateway-landing-zone.md`.

