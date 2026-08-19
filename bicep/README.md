# Azure AI Foundry Landing Zone — Bicep Export

This folder is a Bicep re-implementation of the live environment discovered in:

- `rg-vnet-hub-2` (hub)
- `rg-vm-vnet-test` (application spoke)
- `rg-foundry-standard-private-westus3` (Foundry standard-agent private-network spoke,
  based on the `15-private-network-standard-agent-setup` sample from
  `microsoft-foundry/foundry-samples`)

It implements the requested changes on top of a faithful export:

1. **Region standardization** — every resource defaults to `southeastasia` (the two
   global exceptions are Private DNS zones and Bing accounts, which are inherently
   `global`).
2. **Centralized private DNS** — all 9 `privatelink.*` zones now live in the hub RG
   (`rg-hub-sea`) and are linked to both the hub VNet and the single spoke VNet,
   instead of being duplicated per-spoke.
3. **Single spoke** — resources from `rg-vm-vnet-test` and `rg-foundry-standard-private-westus3` are
   combined into a single resource group (`rg-ai-dev-sea` by default) with a single
   VNet (`vnet-spoke-app-sea`), instead of two RGs / three VNets.
4. **Five container apps** — `fe-app`, `fe-app2`, `be-app`, `be-app2`, and
   `thai-surname-search`.
5. **Private-endpoint-only data plane** — Cosmos DB, Storage, AI Foundry/Cognitive
   Services accounts, AI Search, and Computer Vision all have `publicNetworkAccess:
   Disabled` and a private endpoint in `snet-pe`.

## Layout

```
bicep/
  main.bicep                    # subscription-scope orchestrator (entry point)
  parameters/main.bicepparam    # sample parameter file
  modules/
    resource-group.bicep        # cross-subscription resource group creation
    hub-network.bicep           # vnet-hub-2, VPN Gateway (x2 PIP + P2S), DNS Private Resolver
    spoke-network.bicep         # merged VNet, subnets, NSGs, NAT Gateway, optional Bastion
    vnet-peering-hub-side.bicep / vnet-peering-spoke-side.bicep
    dns-zones.bicep             # 9 centralized privatelink zones + links to both VNets
    private-endpoint.bicep      # generic PE + DNS zone group helper
    storage-account.bicep       # storage (public/private/foundry/funcapp), PE-only
    cosmos-account.bicep        # Cosmos SQL API, PE-only
    search-service.bicep        # AI Search, PE-only
    sql-database.bicep          # Entra-only Azure SQL database, PE-only
    cognitive-account.bicep     # Computer Vision + AI Foundry (AIServices) accounts, PE-only
    foundry-project.bicep       # Foundry project child resource
    bing-grounding.bicep        # Grounding with Bing (global, no PE)
    container-registry.bicep    # ACR
    virtual-machine.bicep       # generic Linux VM (SSH key, NIC+NSG, MDE.Linux extension)
    container-apps-environment.bicep
    container-apps-private-dns.bicep # private wildcard DNS for the internal environment
    container-app.bicep         # generic Container App (reused x5)
    application-gateway-waf.bicep # public WAF_v2 route to private Thai search app
    function-app.bicep          # Flex Consumption Function App + AppInsights + optional Durable Scheduler + UAMI
    log-analytics.bicep
    app-insights.bicep          # standalone workspace-based Application Insights component
    ai-gateway-network.bicep    # AI Gateway VNet (APIM outbound, PE, Logic App subnets)
    key-vault.bicep             # RBAC-authorized Key Vault, PE-only
    managed-redis.bicep         # Azure Managed Redis (RediSearch), PE-only — semantic cache
    event-hub-namespace.bicep   # Event Hub namespace + hub, PE-only — usage-event ingestion
    cognitive-deployment.bicep  # generic Foundry model deployment child resource
    logic-app-standard.bicep    # Logic Apps Standard (WS1) — required plan for Foundry connectivity
    cosmos-sql-database.bicep   # generic Cosmos SQL database + container child resource
    cosmos-sql-role-assignment.bicep # Cosmos DB data-plane RBAC (sqlRoleAssignments)
    apim.bicep                  # APIM Standard V2 + policies/products/subscriptions/backends
    policies/*.xml              # APIM policy fragments (JWT validation, semantic cache, token metering, hub-first failover)
  logic-app-workflows/          # logic-hub-usage-sea<suffix> workflow content (zip-deployed, not Bicep — see below)
    host.json, connections.json
    usage-rollup/workflow.json  # daily Log Analytics query -> Cosmos DB rollup
  scripts/
    export-vpn-client-profile.sh # generates and downloads the Azure VPN Client profile
    deploy-logic-app-workflow.sh # zip-deploys logic-app-workflows/ to logic-hub-usage-sea<suffix>
```

## AI Gateway Landing Zone

`deployAiGateway` (default `true`) deploys a third subscription
(`aiGatewaySubscriptionId`, default `0d04b43f-7d15-40fd-8aa5-830f71ab0d80`) containing
APIM Standard V2, a "hub" Foundry account (primary quota target), Azure Managed Redis
(semantic cache), an Event Hub + Cosmos DB + Logic App Standard usage pipeline, and
per-department APIM Products/Subscriptions for chargeback. Full design rationale is in
`docs/ai-gateway-landing-zone.md`. Key points to confirm before deploying:

- **APIM Standard V2 networking**: outbound-only VNet integration (`snet-apim-outbound`,
  delegated to `Microsoft.Web/serverFarms`) — the gateway hostname itself stays public.
  Upgrade to Premium/Premium v2 if full private ingress is required later.
- **Hub-first quota overflow**: `frag-backend-failover.xml` sends all traffic to
  `hub-foundry-backend` first and only fails over to `spoke-foundry-backend` (the
  existing spoke's `foundryAccountApp`, unmodified) on `429`/`503`. Both backends use
  `authentication-managed-identity` policy (not backend-resource credentials — the
  `Microsoft.ApiManagement/service/backends` schema does not support a `managedIdentity`
  credential type) to call Cognitive Services with APIM's system-assigned identity.
- **Cost attribution and usage pipeline**: department = APIM Product/Subscription
  (`aiGatewayDepartments` param, one Product+Subscription pair per entry); user = Entra
  ID JWT `oid` claim validated by `frag-validate-jwt.xml`. Both are stamped on
  `llm-emit-token-metric` (Application Insights custom metrics) and on a compact JSON
  event sent to `evhns-hub-sea-<suffix>` via `log-to-eventhub`. The `logic-hub-usage-sea<suffix>`
  Logic App Standard runs a daily workflow (`logic-app-workflows/usage-rollup/workflow.json`)
  that queries Application Insights `customMetrics` via the Log Analytics Query API and
  upserts per-department/per-user/per-model daily totals into `cosmos-hub-sea-<suffix>`
  (`usage` database, `token-usage-daily` container, partitioned by `/department`) — this
  is the queryable showback/chargeback store departments and users can report from.
- **Logic Apps Standard workflow content is NOT deployed by Bicep** — Standard's
  `Microsoft.Web/sites/workflows` child resources cannot hold inline workflow
  definitions the way Consumption Logic Apps can; the workflow JSON must be zip-deployed
  after the Bicep run. Run `scripts/deploy-logic-app-workflow.sh <rg> logic-hub-usage-sea<suffix>`
  once the Logic App site exists.
- **Redis Enterprise / Azure Managed Redis** uses
  `Microsoft.Cache/redisEnterprise@2025-04-01` (stable, non-preview), SKU `Balanced_B0`,
  RediSearch module enabled. Verified via `az provider show --namespace Microsoft.Cache`
  (API version is listed/valid) and a real `az deployment sub what-if` that included this
  resource and returned `status: Succeeded` with no Redis-related preflight errors.
- **Logic Apps Standard (WS1)**, not Consumption — Microsoft's Foundry Agent Service
  Logic Apps connector only supports Standard plans. The module uses storage
  account-key-based content share settings as a deliberate simplification.
- **Role assignments**: APIM's system-assigned identity is granted `Cognitive Services
  User` in both the AI Gateway RG (hub Foundry account) and the spoke RG (existing
  `foundryAccountApp`, cross-subscription), plus `Azure Event Hubs Data Sender` and
  `Key Vault Secrets User` in the AI Gateway RG. `logic-hub-usage-sea<suffix>`'s identity is
  granted `Log Analytics Reader`, a Cosmos DB data-plane role (`sqlRoleAssignments`,
  built-in Data Contributor), and `Key Vault Secrets User`.
- Set `deployAiGateway = false` to skip this subscription entirely and deploy only the
  existing hub/spoke topology.

### Deployment validation performed

The full template (including the AI Gateway section) was validated with a real
`az deployment sub what-if` (semantic preflight against live Azure resource providers,
not just `az bicep build` syntax checking):

```bash
az deployment sub what-if \
  --subscription "<a subscription accessible to this session>" \
  --location southeastasia \
  --template-file main.bicep \
  --parameters parameters/main.bicepparam \
  --parameters deployAiGateway=true aiGatewaySubscriptionId="<target sub>" ...
```

This run returned `status: Succeeded` after fixing two real preflight errors it caught:

1. `gpt-4o`'s `GlobalStandard` SKU only maps to a **fine-tune** usage quota in this
   tenant/region (`OpenAI.GlobalStandard.gpt-4o-finetune`), not a base chat quota —
   confirmed via `az cognitiveservices account list-models`. The hub chat deployment
   was switched to **`gpt-4.1-mini`** (version `2025-04-14`), which has a genuine
   `GlobalStandard` chat quota (`OpenAI.GlobalStandard.gpt4.1-mini`). The deployment
   *name* stays `gpt-4o-hub-prod` for continuity with the docs — re-verify your own
   subscription's model catalog before switching back to `gpt-4o`.
2. `text-embedding-3-small` (version `1`) does not expose a plain `Standard` SKU in
   this region — only `GlobalStandard`/`DataZoneStandard`. Fixed to `GlobalStandard`.

The **actual target subscription** (`0d04b43f-7d15-40fd-8aa5-830f71ab0d80`) was not
reachable from this environment's Azure CLI login (`az account set --subscription
0d04b43f...` → "Subscription not found") — the what-if above was run with
`aiGatewaySubscriptionId` pointed at an accessible substitute subscription purely to
validate the resource graph is deployable; **no billable resources were created**
(what-if only). Re-run the same command with the real
`aiGatewaySubscriptionId=0d04b43f-7d15-40fd-8aa5-830f71ab0d80` once that subscription
is accessible, and use `az deployment sub create` (drop `what-if`) to actually deploy.

## Resource mapping (old → new)

| Original | New |
|---|---|
| `rg-vnet-hub-2` (original hub) | `rg-hub-sea` (hub network + 9 centralized DNS zones) |
| `rg-vm-vnet-test` + `rg-foundry-standard-private-westus3` | `rg-ai-dev-sea` (single spoke RG) |
| `vnet-1` / `vnet-2` / `agent-vnet-test` | `vnet-spoke-app-sea` (single VNet, including dedicated `snet-appgw` and workload/private-endpoint subnets) |
| DNS zones in both original spokes | 9 hub-hosted zones, linked to the hub and single spoke VNets |
| `fe-app`, `fe-app2`, `be-app`, `be-app2`, `thai-surname-search` | deployed into the merged Container Apps environment |
| `stgaccpriv`, `publicstoragevnet`, `foundryrbjpstorage` | 4 storage accounts (added a dedicated Function App storage account), all PE-only, public access now disabled on all (including the former `publicstoragevnet`) |
| `cosmos-ragstore-vnet1-dev`, `foundryrbjpcosmosdb` | 2 Cosmos accounts, PE-only |
| `foundryrbjpsearch` | 1 AI Search Basic service, PE-only |
| `vry-cv-eus2-dev` | Computer Vision account, PE-only |
| `testapp-foundry`+`firstProject`, `foundryrbjp`+`projectrbjp` | 2 Foundry accounts + projects, PE-only, 3 DNS zones each |
| `bingsearch-dev`, `bing-grounding-rbjp` | 2 Bing grounding accounts (global) |
| `cada3823f83eacr` | 1 ACR |
| `myVm`, `vm-2` | 2 VMs in `snet-vm`, each with its own NSG + MDE.Linux extension |
| `funcapptestvnet` stack | Flex Consumption Function App + AppInsights + UAMI, VNet-integrated; dedicated Durable Task Scheduler is optional and disabled by default |

## Known assumptions / things to confirm before deploying

- **CIDR ranges are placeholders.** Live VNet address spaces/subnet prefixes could not be
  read back in this session (the deep resource-graph tool was blocked by policy). Update
  `vnetAddressPrefix`/subnet prefix parameters in `hub-network.bicep` and
  `spoke-network.bicep` to match your real ranges (or the ranges you want) before deploying,
  and make sure they don't overlap with each other or with on-prem ranges reachable via the
  VPN gateway.
- **VPN Gateway public IPs**: `VpnGw1AZ` uses two zone-redundant Standard
  public IPs across zones 1, 2, and 3. The hub subscription must have
  `Microsoft.Network/AllowBringYourOwnPublicIpAddress` registered.
- **Point-to-Site VPN**: the gateway uses OpenVPN and Microsoft Entra ID
  authentication with the Azure VPN Client application. The client address pool
  defaults to `172.16.0.0/24`; change `p2sClientAddressPool` if it overlaps any
  hub, spoke, peered, or on-premises network.
- **Container app images/env vars** for the backend samples are placeholders (`mcr.microsoft.com/...helloworld`).
  Supply real `image`/`envVars`/`targetPort` values per app via module parameters.
- **Public Thai search endpoint**: Application Gateway WAF_v2 is enabled by
  default and exposes `thai-surname-search` through an HTTP
  `cloudapp.azure.com` hostname. It uses OWASP 3.2 prevention mode and HTTPS to
  the private backend. Production HTTPS requires a custom domain and certificate.
- **Globally-unique names** (Storage, Cosmos, Search, Cognitive, ACR) are suffixed with
  `uniqueString(...)` to avoid collisions — rename if you want the original names back
  (note some, like `cada3823f83eacr`, may already be taken by the existing live resources
  if deploying alongside them rather than replacing them).
- **SSH keys**: `sshPublicKeyVm1`/`sshPublicKeyVm2` are required secure parameters — supply
  the real, existing public key material at deploy time, not in source control.
- **Function App storage account**: the original export didn't show a distinct
  `AzureWebJobsStorage` account, so a dedicated one (`stfuncapp...`) was added.
  It uses managed-identity authentication, a deployment Blob container, and private
  endpoints for Blob, Queue, and Table.
- **Function App cost profile**: the Function App uses Flex Consumption (`FC1`),
  defaults to 512 MB instances, scales to zero with no always-ready instances, and
  caps scale-out at 40 instances. The dedicated Durable Task Scheduler is disabled
  by default because its Dedicated capacity introduces fixed cost.
- **Bastion cost profile**: Azure Bastion and its public IP are optional and
  disabled by default. Set `enableBastion=true` only when Bastion-based VM
  administration is required.
- **MDE VM extension**: disabled by default. Set `enableMdeExtension=true`
  only after Defender for Servers and Microsoft Defender for Endpoint
  onboarding are configured; deploying the extension without onboarding data
  causes VM extension provisioning to fail.
- **Agent subnet range**: `snet-agent` defaults to `10.10.5.0/24`. This is a
  valid RFC1918 Class A range, `/24` is the recommended size, and Southeast
  Asia supports Class A ranges. Keep it exclusive to one Foundry resource and
  non-overlapping with all local, peered, and reserved networks.
- **Computer Vision**: disabled by default because some subscriptions cannot
  create the `ComputerVision` S0 SKU without additional quota or feature
  access. Set `enableComputerVision=true` only after confirming availability.
- **Function integration subnet**: Flex Consumption uses its own dedicated
  subnet delegated to `Microsoft.App/environments`; it is separate from both
  the Container Apps and Foundry agent subnets.
- **AI Search cost profile**: Azure AI Search defaults to the Basic SKU instead
  of Standard S1. Confirm that Basic capacity and feature limits meet the workload.
- `Microsoft.Bing/accounts@2025-05-01-preview` has no Bicep type definitions yet.
  Type validation is suppressed only for that resource until Microsoft publishes
  definitions for the preview API.
- The Container Apps environment reads the Log Analytics shared key directly with
  `listKeys()` and does not expose it through a module output.

## Validate

```bash
az bicep build --file main.bicep --outfile /tmp/main.json
az bicep build-params --file parameters/main.bicepparam
```

Both commands were run during authoring and complete with 0 errors and 0 warnings.

## Deploy

For a complete fresh deployment, including application image builds, SQL
managed-identity bootstrap, and SQL/Search data population, run this from the
repository root:

```bash
chmod +x scripts/deploy-apps.sh
./scripts/deploy-apps.sh
```

The script first bootstraps the infrastructure without repository application
revisions when ACR does not exist, builds the images with ACR Tasks, then
deploys and initializes all applications. The Bicep command below is
infrastructure-only and must be followed by `./scripts/deploy-apps.sh` to reach
the complete application state.

```bash
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

Deployment order is handled internally by module dependencies: hub network → spoke
network → hub DNS zones (needs both VNet IDs) → peering (both directions) → data
services + VMs + Container Apps + Function App (all depend on the single spoke subnets
and the hub-hosted DNS zone IDs).

Set `hubSubscriptionId` and `spokeSubscriptionId` in
`parameters/main.bicepparam` to deploy the hub and spoke into different
subscriptions in the same Microsoft Entra tenant. If omitted, both use the
subscription where the orchestration deployment is started. The deployment
identity needs sufficient permissions in both target subscriptions.

If `deployAiGateway = true` (default), after the Bicep deployment completes,
zip-deploy the usage-rollup Logic App workflow content (Standard workflow
definitions are not deployable via Bicep — see `bicep/README.md`'s "AI Gateway
Landing Zone" section):

```bash
chmod +x scripts/deploy-logic-app-workflow.sh
# <suffix> is the resolved uniqueString(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
# value — check with `az webapp list -g rg-ai-gateway-sea -o table` for the exact name.
./scripts/deploy-logic-app-workflow.sh rg-ai-gateway-sea "logic-hub-usage-sea<suffix>" "<ai-gateway-subscription-id>"
```

## Download the Point-to-Site VPN client profile

The VPN client profile is generated by Azure only after the VPN gateway
deployment reaches `Succeeded`. From this folder, run:

```bash
chmod +x scripts/export-vpn-client-profile.sh
./scripts/export-vpn-client-profile.sh \
  "<hub-subscription-id>" \
  "rg-hub-sea" \
  "hub-VNetGw-sea-dev" \
  "vpn-client-profile.zip"
```

The script downloads the generated profile ZIP. Extract it and import the
Azure VPN Client XML profile into Azure VPN Client. Users authenticate with an
account in the Microsoft Entra tenant used by the deployment. The hub VNet
advertises the static DNS Private Resolver inbound IP (`10.0.2.4` by default),
so the regenerated profile configures VPN clients to resolve linked private
DNS zones automatically.

## Remove all deployed resources

All resources created by this template are contained in the configured spoke
and hub resource groups. Delete the spoke resource group first, followed by
the hub resource group.

> **Warning:** This permanently deletes all resources and data in both
> resource groups. Replace the names and subscription IDs if you changed the
> values in `parameters/main.bicepparam`.

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

Use the same subscription ID for both commands when the hub and spoke were
deployed to one subscription. Optionally remove the subscription deployment
history after both resource groups have been deleted:

```bash
az deployment sub delete \
  --subscription "<orchestration-subscription-id>" \
  --name "main"
```
