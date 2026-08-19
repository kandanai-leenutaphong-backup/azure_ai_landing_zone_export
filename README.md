# Azure AI Landing Zone — Setup Guide

This repository contains a Bicep export of an Azure AI Foundry landing zone
(hub + spoke network, private DNS, data services, container apps, VMs, and a
Flex Consumption Function App). All infrastructure lives under [`bicep/`](bicep/README.md),
which also documents the architecture and resource mapping in detail.

## Prerequisites

- One or two Azure subscriptions with **Owner** or **Contributor + User Access
  Administrator** rights. The deployment is subscription-scoped and creates
  resource groups in the configured hub and spoke subscriptions.
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) v2.60+
  with the Bicep tooling installed:
  ```bash
  az bicep install
  az bicep upgrade
  ```
- Two existing SSH public keys (for the two VMs deployed into the spoke
  VNet) — you will supply these at deploy time, not in source control.
- Sufficient regional quota in `southeastasia` (or your chosen region) for
  VMs, VPN Gateway, Container Apps, Cosmos DB, AI Search, and AI Foundry
  (Cognitive Services) accounts.
- The hub subscription must have the Network public IP feature used by the
  active-active VPN Gateway registered:
  ```bash
  az feature register \
    --subscription "<hub-subscription-id>" \
    --namespace Microsoft.Network \
    --name AllowBringYourOwnPublicIpAddress

  az feature show \
    --subscription "<hub-subscription-id>" \
    --namespace Microsoft.Network \
    --name AllowBringYourOwnPublicIpAddress \
    --query properties.state -o tsv
  ```
  Wait until the state is `Registered`, then run
  `az provider register --subscription "<hub-subscription-id>" --namespace Microsoft.Network`.

## 1. Log in and select a subscription

```bash
az login
az account set --subscription "<subscription-id-or-name>"
```

## 2. Review and customize parameters

Copy or edit [`bicep/parameters/main.bicepparam`](bicep/parameters/main.bicepparam)
before running the deployment.

### Parameters to review

| Parameter | Required change? | What to set |
|---|---|---|
| `sshPublicKeyVm1` | **Yes** | Public SSH key for `myVm`. Replace the placeholder or pass it securely on the deployment command. |
| `sshPublicKeyVm2` | **Yes** | Public SSH key for `vm-2`. Replace the placeholder or pass it securely on the deployment command. |
| `hubSubscriptionId` | For cross-subscription deployment | Uncomment and set the hub subscription ID. If omitted, it uses the orchestration subscription. |
| `spokeSubscriptionId` | For cross-subscription deployment | Uncomment and set the spoke subscription ID. If omitted, it uses the orchestration subscription. |
| `location` | Review | Azure region for the deployment, currently `southeastasia`. Confirm service availability and quota there. |
| `hubResourceGroupName` | Optional | Hub resource group name, currently `rg-hub-sea`. |
| `spokeResourceGroupName` | Optional | The single spoke resource group name, currently `rg-ai-dev-sea`. |
| `enableBastion` | Optional | Set to `true` only if Azure Bastion is required. It is `false` by default to avoid its fixed cost. |
| `enableMdeExtension` | Optional | Keep `false` unless Defender for Servers and Microsoft Defender for Endpoint onboarding are configured. |
| `enableComputerVision` | Optional | Keep `false` unless the subscription has quota/feature access for a Computer Vision S0 account. |
| `enableThaiPublicGateway` | Optional | Keep `true` to publish Thai search through Application Gateway WAF_v2; set `false` to keep it VPN/private-only and avoid the gateway cost. |
| `dnsResolverInboundIp` | Review | Static DNS Private Resolver inbound IP advertised to VPN clients, currently `10.0.2.4`. It must belong to `dnsResolverInboundSubnetPrefix`. |
| `tags` | Recommended | Replace the sample environment and source tags with your organization tags. |
| `uniqueSuffix` | Only for name conflicts | Normally generated automatically. Override it in the parameter file only if a globally unique resource name collides. |

For a same-subscription deployment, leave both subscription ID parameters
commented out. For different subscriptions, uncomment both lines:

```bicep
param hubSubscriptionId = '<hub-subscription-id>'
param spokeSubscriptionId = '<spoke-subscription-id>'
```

### Network values to review

The network values are currently defined in the module files rather than the
main parameter file. Confirm that every range is non-overlapping with the
other VNet and with connected on-premises networks.

| File | Parameters to review |
|---|---|
| `bicep/modules/hub-network.bicep` | `vnetAddressPrefix`, `defaultSubnetPrefix`, `gatewaySubnetPrefix`, `dnsResolverInboundSubnetPrefix`, `dnsResolverInboundIp`, `vpnGatewaySku`, `vpnGatewayName`, `dnsResolverName` |
| `bicep/modules/spoke-network.bicep` | `vnetAddressPrefix`, `bastionSubnetPrefix`, `vmSubnetPrefix`, `containerAppsSubnetPrefix`, `functionAppSubnetPrefix`, `agentSubnetPrefix`, `privateEndpointsSubnetPrefix`, `applicationGatewaySubnetPrefix` |

The Flex Consumption Function App uses a dedicated subnet delegated to
`Microsoft.App/environments`. It cannot share the Container Apps or Foundry
agent subnets.

The default agent subnet, `10.10.5.0/24`, meets the Foundry Agent Service
requirements: it is an RFC1918 private range, `/24` is the recommended size,
and Southeast Asia supports private Class A (`10.x.x.x`) ranges. The subnet is
delegated to `Microsoft.App/environments`. It must remain dedicated to one
Foundry resource and must not overlap the hub, other spoke subnets, peered
networks, or the reserved ranges documented in the
[Foundry Agent Service VNet limitations](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations).

Before a production deployment, also replace the sample Container App images
and configure their ports and environment variables in the Container App
module calls in `bicep/main.bicep`.

See `bicep/README.md` → **Known assumptions / things to confirm before
deploying** for the full list of items to review first.

## 3. Validate the templates

```bash
cd bicep
az bicep build --file main.bicep --outfile /tmp/main.json
az bicep build-params --file parameters/main.bicepparam
```

Both commands should complete with 0 errors and 0 warnings.

## 4. Deploy the complete landing zone

If `hubSubscriptionId` and `spokeSubscriptionId` are uncommented and set in
`parameters/main.bicepparam`, do not repeat them on the deployment command.
The Azure CLI subscription only determines where the subscription-scope
deployment record runs. Select that orchestration subscription first:

```bash
az account set --subscription "<orchestration-subscription-id>"
az account show --query "{name:name, id:id}" -o table
```

Run the repository deployment script from the repository root. This is the
recommended command for both a fresh environment and later application updates:

```bash
chmod +x scripts/deploy-apps.sh

SPOKE_SUBSCRIPTION_ID="<spoke-subscription-id>" \
ORCHESTRATION_SUBSCRIPTION_ID="<orchestration-subscription-id>" \
SSH_PUBLIC_KEY_FILE="$HOME/.ssh/id_rsa.pub" \
./scripts/deploy-apps.sh
```

The script performs the complete deployment:

1. Bootstraps the Bicep infrastructure without repository application
   revisions when the ACR does not exist yet.
2. Builds all three application images with ACR Tasks. A local Docker daemon
   is not required.
3. Deploys `fe-app`, `fe-app2`, and the remaining backend Container Apps.
4. Creates the private Azure SQL server/database and configures the Container
   Apps managed identity as a contained database user.
5. Deploys `thai-surname-search`, loads 10,000 rows into SQL, and creates and
   populates the `thai-people` Azure AI Search index.
6. Deploys Application Gateway WAF_v2 and publishes the Thai search app through
   an Azure `cloudapp.azure.com` hostname.
7. Removes the obsolete `fe-app-ai` and duplicate `fe-app-ai-2` resources.

The orchestration subscription can be either target subscription. The signed-in
identity must have permission to create resource groups and resources in both
subscriptions, and both subscriptions must belong to the same Microsoft Entra
tenant.

Deployment order (hub network → spoke network → hub DNS zones → VNet
peering → data services/VMs/Container Apps/Function App) is handled
automatically via module dependencies.

### Bicep-only deployment

The raw `az deployment sub create` command provisions the infrastructure and
resource definitions, but it does not build the repository application images
or bootstrap the Thai SQL/Search data. Use it only for infrastructure-only
work:

```bash
cd bicep
ssh_key="$(cat "$HOME/.ssh/id_rsa.pub")"

az deployment sub create \
  --subscription "<orchestration-subscription-id>" \
  --location southeastasia \
  --template-file main.bicep \
  --parameters parameters/main.bicepparam \
  --parameters deployRepositoryApps=false \
               deployThaiSurnameApp=false \
               sshPublicKeyVm1="$ssh_key" \
               sshPublicKeyVm2="$ssh_key"
```

After an infrastructure-only deployment, return to the repository root and run
`./scripts/deploy-apps.sh` to reach the complete application and data state.

## 5. Verify

```bash
az group list --query "[?name=='rg-hub-sea' || name=='rg-ai-dev-sea']" -o table
az deployment sub show --name main -o table
```

Confirm the container apps, VMs, and data services came up healthy, and that
private endpoints resolve correctly through the hub-hosted private DNS
zones.

## Repository applications

Application source deployed by the complete deployment command is stored under:

- `applications/ping-url`, deployed to `fe-app`
- `applications/azure-ocr-service`, deployed to `fe-app2`
- `applications/thai-surname-search`, deployed to `thai-surname-search`

The deployment script uses a unique UTC image tag by default so source-only
changes always create a new Container Apps revision. Override
`SPOKE_SUBSCRIPTION_ID`, `SPOKE_RESOURCE_GROUP`,
`ORCHESTRATION_SUBSCRIPTION_ID`, or `SSH_PUBLIC_KEY_FILE` when needed.

## Public Thai surname endpoint

`thai-surname-search` remains private inside the internal Container Apps
environment. Application Gateway WAF_v2 exposes it to the internet using a
public hostname similar to:

```text
http://thai-search-sea-<unique-suffix>.southeastasia.cloudapp.azure.com
```

The public listener currently accepts HTTP on port 80, applies OWASP 3.2 rules
in prevention mode, and forwards requests over HTTPS to the private Container
App hostname. A gateway rewrite rule maps the public browser origin to the
private backend origin so Streamlit WebSockets work without disabling
Streamlit CORS or XSRF protection. The deployment script prints the exact
public URL when it finishes.

For production HTTPS, configure a custom domain and certificate in Key Vault,
add an HTTPS listener on port 443, and redirect port 80 to 443. A public TLS
certificate cannot be generated safely by this template without ownership of
the intended DNS name.

## 6. Remove all deployed resources

The deployment places all resources in the configured hub and spoke resource
groups. Deleting those resource groups removes the complete landing zone.
Delete the spoke first, then the hub, to remove dependent workload and
network resources in a predictable order.

> **Warning:** These commands permanently delete all resources and data in
> both resource groups. Use the resource group names and subscription IDs from
> your parameter file if you changed the defaults.

```bash
az group delete \
  --subscription "<spoke-subscription-id>" \
  --name "rg-ai-dev-sea" \
  --yes

az group delete \
  --subscription "<hub-subscription-id>" \
  --name "rg-hub-sea" \
  --yes
```

For a same-subscription deployment, use the same subscription ID in both
commands. After the resource groups are deleted, optionally remove the
subscription deployment history record:

```bash
az deployment sub delete \
  --subscription "<orchestration-subscription-id>" \
  --name "main"
```

## Estimated monthly cost

Costs are broken out **per subscription** because the hub, the spoke, and the
AI Gateway landing zone can each be billed to a different Azure
subscription (`hubSubscriptionId`, `spokeSubscriptionId`, and
`aiGatewaySubscriptionId`). All figures use pay-as-you-go public USD retail
rates as of August 2026, 730 hours per month, before taxes, contract
discounts, outbound bandwidth, and usage-based AI charges. Confirm final
pricing with the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/).

### Hub subscription (`rg-hub-sea`) — deployed

| Resource | Estimated monthly cost |
|---|---:|
| VPN Gateway `VpnGw1AZ` | $153 |
| DNS Private Resolver inbound endpoint | $180 |
| 9 private DNS zones | $5 plus queries |
| **Hub subtotal** | **≈ $338 plus queries** |

### Spoke subscription (`rg-ai-dev-sea`) — deployed

| Resource | Estimated monthly cost |
|---|---:|
| NAT Gateway | $33 plus processed data |
| 12 private endpoints | $88 plus processed data |
| 5 Standard public IP addresses | $18 |
| Two `Standard_B2s` Linux VMs | $77 |
| Two Premium SSD OS disks | $11 |
| Azure AI Search Basic | $74 |
| Azure Container Registry Standard | $20 |
| Azure SQL Database Basic | $5 |
| Application Gateway WAF_v2 | $342 fixed cost plus capacity units |
| Container Apps | Scale to zero when idle; usage-based when requests activate a replica |
| Storage, monitoring, and light transactions | $5-$25 |
| Flex Consumption Function App | Usually $0 at light usage within the free grant |
| Azure Bastion | $0 by default; approximately $143 when enabled, including its public IP |
| **Spoke subtotal** | **≈ $673-$693 plus capacity units and usage-based charges** |

AI Foundry accounts and projects, Computer Vision, Cosmos DB accounts, and
Grounding with Bing have little or no idle resource charge in this template.
Model tokens, search operations, vision calls, Bing calls, provisioned Cosmos
DB throughput, logs, and network egress are billed separately.

**Hub + spoke total: ≈ $1,010-$1,040/month fixed**, or approximately
**$1,150-$1,450/month plus AI model consumption** with moderate application
activity.

### AI Gateway subscription (`rg-ai-gateway-sea`) — deployed

Deployed by `bicep/main.bicep` behind the `deployAiGateway` parameter
(default `true`; see [`docs/ai-gateway-landing-zone.md`](docs/ai-gateway-landing-zone.md)
for the full design). Re-confirm once the Bicep parameters (APIM capacity
units, Redis SKU, Event Hub throughput units) are tuned for your workload.

| Resource | Estimated monthly cost |
|---|---:|
| APIM Standard V2 (`apim-hub-sea<suffix>`, 1 unit, ~$0.96-$1.01/hour) | $700-$734 |
| Azure Managed Redis, smallest SKU (`redis-hub-sea-<suffix>`, semantic cache) | $40-$90 |
| Event Hub Standard namespace, 1 throughput unit (`evhns-hub-sea-<suffix>`) | $22 plus ingress events |
| Logic Apps **Standard**, WS1 plan (`logic-hub-usage-sea<suffix>`, usage ingestion) | $140-$143 |
| Key Vault (`kv-aigw-<suffix>`) | ~$1 |
| Storage account (`stlogicaigw<suffix>`, Logic App content share) | $3-$5 |
| Application Insights + Log Analytics (`appi-apim-sea`, `workspace-ai-gateway-sea`) | $10-$20 |
| ~5 private endpoints (Foundry, Redis, Event Hub, Key Vault, Storage) | $37 plus processed data |
| Foundry hub account (`aif-hub-sea<suffix>`) idle cost | $0; model deployment capacity/token usage billed separately |
| **AI Gateway subtotal** | **≈ $953-$1,050/month fixed, plus Foundry model token consumption (the dominant cost driver in production)** |

APIM Standard V2 is billed per deployed unit regardless of traffic (no
scale-to-zero), which is why it dominates this subscription's fixed cost;
additional units cost roughly the same again each and would only be needed
for higher throughput or multi-region gateway deployments. **Logic Apps must
be Standard (WS1), not Consumption**, in `logic-hub-usage-sea<suffix>` — Foundry
Agent Service's Logic Apps connector, and the pattern for exposing a
workflow as an agent-callable tool, are only supported on Logic Apps
Standard (see [`docs/ai-gateway-landing-zone.md`](docs/ai-gateway-landing-zone.md#logic-apps-plan-requirement-for-foundry-connectivity)).
This is a flat WS1 plan charge, not usage-based like Consumption, so it does
not scale down when idle.

**All three subscriptions combined: ≈ $1,960-$2,090/month fixed,
plus AI model token consumption across all Foundry accounts.**

## More details

For architecture, resource mapping (old → new), and a full list of
assumptions to confirm before deploying, see [`bicep/README.md`](bicep/README.md).
