// Subscription-scope orchestrator for the Azure AI Foundry landing zone export.
//
// Topology:
//   - Hub RG (rg-hub-sea by default): VNet, VPN Gateway, DNS Private Resolver,
//     and now ALL private DNS zones (centralized).
//   - Single Spoke RG (default: rg-ai-dev-sea): single VNet that replaces both
//     rg-vm-vnet-test and rg-foundry-standard-private-westus3. Hosts the VMs,
//     Bastion, Container Apps (fe-app, fe-app2, be-app, be-app2, thai-surname-search),
//     Function App, ACR, and all data services (Storage, Cosmos, AI Search,
//     Computer Vision, AI Foundry accounts/projects, Bing grounding) — all behind
//     private endpoints, DNS resolved via the hub-hosted zones.
//
// All resources default to South East Asia.

targetScope = 'subscription'

@description('Default region for every resource in this deployment.')
param location string = 'southeastasia'

@description('Subscription ID where the hub resource group and resources are deployed.')
param hubSubscriptionId string = subscription().subscriptionId

@description('Subscription ID where the spoke resource group and resources are deployed.')
param spokeSubscriptionId string = subscription().subscriptionId

@description('Name of the hub resource group.')
param hubResourceGroupName string = 'rg-hub-sea'

@description('Name of the single AI workload spoke resource group.')
param spokeResourceGroupName string = 'rg-ai-dev-sea'

@description('Deploy the AI Gateway Landing Zone subscription (APIM, hub Foundry, Managed Redis semantic cache, usage/chargeback pipeline). See docs/ai-gateway-landing-zone.md.')
param deployAiGateway bool = true

@description('Subscription ID where the AI Gateway resource group and resources are deployed.')
param aiGatewaySubscriptionId string = '0d04b43f-7d15-40fd-8aa5-830f71ab0d80'

@description('Name of the AI Gateway resource group.')
param aiGatewayResourceGroupName string = 'rg-ai-gateway-sea'

@description('Azure region for API Center. API Center is not currently available in Southeast Asia.')
param apiCenterLocation string = 'centralindia'

@description('Publisher email required by the AI Gateway APIM instance.')
param apimPublisherEmail string = 'ai-gateway-admin@contoso.com'

@description('Expected audience (application ID URI or client ID) for AI Gateway caller access tokens, validated by validate-jwt.')
param entraAudience string = 'e9de7c75-a166-4030-8c05-81694cc1fecb'

@description('Name of the Foundry project on the hub Foundry account used to publish/invoke agents from the Foundry Portal (currently auto-provisioned on first Portal use, not yet itself Bicep-managed).')
param hubFoundryProjectName string = 'aiGatewayHubProject'

@description('Create the Foundry project App Insights reader role assignments. Disable when equivalent assignments already exist under different resource IDs.')
param deployFoundryAppInsightsRoleAssignments bool = true

@description('Departments onboarded to the AI Gateway. Each becomes an APIM Product + Subscription — the chargeback boundary for per-department AI spend.')
param aiGatewayDepartments array = [
  {
    name: 'odi'
    displayName: 'ODI'
  }
  {
    name: 'fa'
    displayName: 'Finance & Analytics'
  }
]

@description('Deploy Azure Bastion in the spoke. Disabled by default to reduce fixed monthly cost.')
param enableBastion bool = false

@description('Name of the hub VPN gateway.')
param vpnGatewayName string = 'hub-VNetGw-sea-dev'

@description('Address pool assigned to Point-to-Site VPN clients. Must not overlap any connected network.')
param p2sClientAddressPool string = '172.16.0.0/24'

@description('Static private IP of the hub DNS Private Resolver inbound endpoint, advertised to VPN clients.')
param dnsResolverInboundIp string = '10.0.2.4'

@description('Install the Microsoft Defender for Endpoint VM extension. Enable only after Defender for Servers/MDE onboarding is configured.')
param enableMdeExtension bool = false

@description('Deploy the optional Computer Vision S0 account. Requires subscription quota/feature access for the ComputerVision kind.')
param enableComputerVision bool = false

@description('Container image tag deployed to the repository-owned front-end applications.')
param appImageTag string = 'latest'

@description('Deploy repository-owned Container Apps. The deployment script disables these during a fresh infrastructure bootstrap before images exist.')
param deployRepositoryApps bool = true

@description('Deploy the Thai surname search Container App. The deployment script bootstraps SQL before enabling it.')
param deployThaiSurnameApp bool = true
@description('Optional private Foundry project endpoint called by the Thai search app agent module.')
param regionalAgentProjectEndpoint string = ''
@description('New versioned West US 3 Foundry agent name, not a Classic asst_ ID.')
param regionalAgentName string = ''
param regionalAgentVersion string = ''
param regionalAgentModelSku string = ''
@description('Existing private SEA project for the regional latency comparison.')
param seaAgentProjectEndpoint string = ''
param seaAgentName string = ''
param seaAgentVersion string = ''
param seaAgentModelSku string = ''
@description('Matched Global Standard agent in the same West US 3 project as regionalAgentName.')
param globalAgentName string = ''
param globalAgentVersion string = ''
@description('Reserved SEA Standard chat agent. Leave unset while this model SKU is unavailable in SEA.')
param seaStandardAgentName string = ''
param seaStandardAgentVersion string = ''
@description('Optional Thai search app image override without changing the other repository applications.')
param thaiSurnameAppImageTag string = appImageTag

@description('Expose thai-surname-search publicly through Application Gateway WAF_v2.')
param enableThaiPublicGateway bool = true

@description('Deploy the hub Azure Firewall and force spoke/AI Gateway egress and inter-VNet traffic through it with user-defined routes.')
param enableAzureFirewall bool = true

@description('Expected private IP of the hub Azure Firewall (first usable address of AzureFirewallSubnet). Used as the UDR next hop; verify it matches the firewallPrivateIpAddress output after the first deployment.')
param firewallPrivateIp string = '10.0.3.4'

@description('Allow outbound HTTP/HTTPS to any destination through the firewall. Set false to allow-list only the FQDNs in azure-firewall.bicep.')
param firewallAllowAllOutboundWeb bool = true

@description('Route the Container Apps subnets through the firewall. Requires a workload-profiles Container Apps environment (capps-env-sea is one).')
param enableContainerAppsFirewallRoute bool = true

@description('Microsoft Entra administrator login for Azure SQL.')
param sqlEntraAdminLogin string

@description('Microsoft Entra administrator object ID for Azure SQL.')
param sqlEntraAdminObjectId string

@description('SSH public key material for the two VMs (paste the existing key(s) before deploying).')
@secure()
param sshPublicKeyVm1 string

@secure()
param sshPublicKeyVm2 string

@description('Globally-unique base names for resources that require tenant-wide uniqueness. Adjust if these collide.')
param uniqueSuffix string = uniqueString(spokeSubscriptionId, spokeResourceGroupName)

@description('Globally-unique base names for AI Gateway resources. Adjust if these collide.')
param aiGatewayUniqueSuffix string = uniqueString(aiGatewaySubscriptionId, aiGatewayResourceGroupName)

param tags object = {
  environment: 'exported'
  source: 'rg-vnet-hub-2 + rg-vm-vnet-test + rg-foundry-standard-private-westus3'
}

var functionAppBaseName = 'funcapp-spoke-sea'
var functionDeploymentContainerName = 'function-deployment'

// ---------------------------------------------------------------------------
// Resource groups
// ---------------------------------------------------------------------------

module hubRg 'modules/resource-group.bicep' = {
  name: 'deploy-hub-resource-group'
  scope: subscription(hubSubscriptionId)
  params: {
    name: hubResourceGroupName
    location: location
    tags: tags
  }
}

module spokeRg 'modules/resource-group.bicep' = {
  name: 'deploy-spoke-resource-group'
  scope: subscription(spokeSubscriptionId)
  params: {
    name: spokeResourceGroupName
    location: location
    tags: tags
  }
}

module aiGatewayRg 'modules/resource-group.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-resource-group'
  scope: subscription(aiGatewaySubscriptionId)
  params: {
    name: aiGatewayResourceGroupName
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Networking
// ---------------------------------------------------------------------------

var hubAddressPrefix = '10.0.0.0/16'
var spokeAddressPrefix = '10.10.0.0/16'
var aiGatewayAddressPrefix = '10.20.0.0/16'
var hubApplicationGatewaySubnetPrefix = '10.0.5.0/24'

module hubAppGwRouteTable 'modules/route-table.bicep' = if (enableAzureFirewall) {
  name: 'deploy-hub-appgw-route-table'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  dependsOn: [
    hubRg
  ]
  params: {
    location: location
    name: 'rt-hub-appgw'
    routes: [
      {
        name: 'spoke-via-firewall'
        addressPrefix: spokeAddressPrefix
        nextHopType: 'VirtualAppliance'
        nextHopIpAddress: firewallPrivateIp
      }
    ]
    tags: tags
  }
}

module spokeRouteTable 'modules/route-table.bicep' = if (enableAzureFirewall) {
  name: 'deploy-spoke-route-table'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    spokeRg
  ]
  params: {
    location: location
    name: 'rt-spoke-via-firewall'
    routes: [
      {
        name: 'default-via-firewall'
        addressPrefix: '0.0.0.0/0'
        nextHopType: 'VirtualAppliance'
        nextHopIpAddress: firewallPrivateIp
      }
      {
        name: 'ai-gateway-via-firewall'
        addressPrefix: aiGatewayAddressPrefix
        nextHopType: 'VirtualAppliance'
        nextHopIpAddress: firewallPrivateIp
      }
    ]
    tags: tags
  }
}

module aiGatewayRouteTable 'modules/route-table.bicep' = if (enableAzureFirewall && deployAiGateway) {
  name: 'deploy-ai-gateway-route-table'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  dependsOn: [
    aiGatewayRg
  ]
  params: {
    location: location
    name: 'rt-ai-gateway-via-firewall'
    routes: [
      {
        name: 'default-via-firewall'
        addressPrefix: '0.0.0.0/0'
        nextHopType: 'VirtualAppliance'
        nextHopIpAddress: firewallPrivateIp
      }
      {
        name: 'spoke-via-firewall'
        addressPrefix: spokeAddressPrefix
        nextHopType: 'VirtualAppliance'
        nextHopIpAddress: firewallPrivateIp
      }
    ]
    tags: tags
  }
}

module hubNetwork 'modules/hub-network.bicep' = {
  name: 'deploy-hub-network'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  dependsOn: [
    hubRg
  ]
  params: {
    vnetAddressPrefix: hubAddressPrefix
    applicationGatewaySubnetPrefix: hubApplicationGatewaySubnetPrefix
    applicationGatewayRouteTableId: enableAzureFirewall ? hubAppGwRouteTable!.outputs.id : ''
    location: location
    vpnGatewayName: vpnGatewayName
    p2sClientAddressPool: p2sClientAddressPool
    dnsResolverInboundIp: dnsResolverInboundIp
    entraTenantId: tenant().tenantId
    tags: tags
  }
}

module spokeNetwork 'modules/spoke-network.bicep' = {
  name: 'deploy-spoke-network'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    spokeRg
    hubFirewall
  ]
  params: {
    location: location
    enableBastion: enableBastion
    firewallRouteTableId: enableAzureFirewall ? spokeRouteTable!.outputs.id : ''
    containerAppsRouteTableId: enableAzureFirewall && enableContainerAppsFirewallRoute ? spokeRouteTable!.outputs.id : ''
    tags: tags
  }
}

module aiGatewayNetwork 'modules/ai-gateway-network.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-network'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  dependsOn: [
    aiGatewayRg
    hubFirewall
  ]
  params: {
    location: location
    firewallRouteTableId: enableAzureFirewall ? aiGatewayRouteTable!.outputs.id : ''
    tags: tags
  }
}

module hubFirewall 'modules/azure-firewall.bicep' = if (enableAzureFirewall) {
  name: 'deploy-hub-firewall'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    location: location
    firewallSubnetId: hubNetwork.outputs.firewallSubnetId
    managementSubnetId: hubNetwork.outputs.firewallManagementSubnetId
    internalRanges: [
      hubAddressPrefix
      spokeAddressPrefix
      aiGatewayAddressPrefix
    ]
    applicationGatewaySubnetPrefix: hubApplicationGatewaySubnetPrefix
    spokeAddressPrefix: spokeAddressPrefix
    dnsResolverInboundIp: dnsResolverInboundIp
    allowAllOutboundWeb: firewallAllowAllOutboundWeb
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    tags: tags
  }
}

module dnsZones 'modules/dns-zones.bicep' = {
  name: 'deploy-hub-dns-zones'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    hubVnetId: hubNetwork.outputs.vnetId
    spokeVnetId: spokeNetwork.outputs.vnetId
    aiGatewayVnetId: deployAiGateway ? aiGatewayNetwork!.outputs.vnetId : ''
    tags: tags
  }
}

module hubPeering 'modules/vnet-peering-hub-side.bicep' = {
  name: 'deploy-hub-peering'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    hubVnetName: hubNetwork.outputs.vnetName
    spokeVnetName: spokeNetwork.outputs.vnetName
    spokeVnetId: spokeNetwork.outputs.vnetId
  }
}

module spokePeering 'modules/vnet-peering-spoke-side.bicep' = {
  name: 'deploy-spoke-peering'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    spokeVnetName: spokeNetwork.outputs.vnetName
    hubVnetId: hubNetwork.outputs.vnetId
  }
}

module aiGatewayHubPeering 'modules/vnet-peering-hub-side.bicep' = if (deployAiGateway) {
  name: 'deploy-hub-ai-gateway-peering'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    hubVnetName: hubNetwork.outputs.vnetName
    spokeVnetName: aiGatewayNetwork!.outputs.vnetName
    spokeVnetId: aiGatewayNetwork!.outputs.vnetId
  }
}

module aiGatewaySpokePeering 'modules/vnet-peering-spoke-side.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-hub-peering'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    spokeVnetName: aiGatewayNetwork!.outputs.vnetName
    hubVnetId: hubNetwork.outputs.vnetId
  }
}

// VNet peering is not transitive. APIM needs direct connectivity to the application
// spoke to reach internal Container Apps backends used by REST and MCP APIs.
module aiGatewayToAppSpokePeering 'modules/vnet-peering-direct.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-to-app-spoke-peering'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    localVnetName: aiGatewayNetwork!.outputs.vnetName
    remoteVnetId: spokeNetwork.outputs.vnetId
    peeringName: 'vnet-ai-gateway-sea-to-app-spoke'
  }
}

module appSpokeToAiGatewayPeering 'modules/vnet-peering-direct.bicep' = if (deployAiGateway) {
  name: 'deploy-app-spoke-to-ai-gateway-peering'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    localVnetName: spokeNetwork.outputs.vnetName
    remoteVnetId: aiGatewayNetwork!.outputs.vnetId
    peeringName: 'vnet-spoke-app-sea-to-ai-gateway'
  }
}

// ---------------------------------------------------------------------------
// Observability
// ---------------------------------------------------------------------------

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'deploy-log-analytics'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    spokeRg
  ]
  params: {
    location: location
    name: 'workspace-spoke-app-sea'
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Data services (Storage, Cosmos, Search, Cognitive/Foundry) — all private-endpoint only
// ---------------------------------------------------------------------------

module storagePublic 'modules/storage-account.bicep' = {
  name: 'deploy-storage-public'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'stpublicapp${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    blobPrivateDnsZoneId: dnsZones.outputs.blobZoneId
    tags: tags
  }
}

module storagePrivate 'modules/storage-account.bicep' = {
  name: 'deploy-storage-private'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'stappsea${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    blobPrivateDnsZoneId: dnsZones.outputs.blobZoneId
    blobContainerNames: [
      'test'
    ]
    tags: tags
  }
}

module storageFoundry 'modules/storage-account.bicep' = {
  name: 'deploy-storage-foundry'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'stfoundry${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    blobPrivateDnsZoneId: dnsZones.outputs.blobZoneId
    tags: tags
  }
}

module storageFunctionApp 'modules/storage-account.bicep' = {
  name: 'deploy-storage-funcapp'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'stfuncapp${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    blobPrivateDnsZoneId: dnsZones.outputs.blobZoneId
    enableQueuePrivateEndpoint: true
    queuePrivateDnsZoneId: dnsZones.outputs.queueZoneId
    enableTablePrivateEndpoint: true
    tablePrivateDnsZoneId: dnsZones.outputs.tableZoneId
    blobContainerNames: [
      functionDeploymentContainerName
    ]
    allowSharedKeyAccess: false
    tags: tags
  }
}

module cosmosRagStore 'modules/cosmos-account.bicep' = {
  name: 'deploy-cosmos-ragstore'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'cosmos-ragstore-sea${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    documentsPrivateDnsZoneId: dnsZones.outputs.documentsZoneId
    tags: tags
  }
}

module cosmosFoundry 'modules/cosmos-account.bicep' = {
  name: 'deploy-cosmos-foundry'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'cosmos-foundry-sea${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    documentsPrivateDnsZoneId: dnsZones.outputs.documentsZoneId
    tags: tags
  }
}

module aiSearch 'modules/search-service.bicep' = {
  name: 'deploy-ai-search'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'search-foundry-sea${uniqueSuffix}'
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    searchPrivateDnsZoneId: dnsZones.outputs.searchZoneId
    tags: tags
  }
}

module computerVision 'modules/cognitive-account.bicep' = if (enableComputerVision) {
  name: 'deploy-computer-vision'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'cv-app-sea${uniqueSuffix}'
    kind: 'ComputerVision'
    allowProjectManagement: false
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    privateDnsZoneIds: [
      dnsZones.outputs.cognitiveservicesZoneId
    ]
    tags: tags
  }
}

module foundryAccountApp 'modules/cognitive-account.bicep' = {
  name: 'deploy-foundry-account-app'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'foundry-app-sea${uniqueSuffix}'
    kind: 'AIServices'
    allowProjectManagement: true
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    privateDnsZoneIds: [
      dnsZones.outputs.cognitiveservicesZoneId
      dnsZones.outputs.openaiZoneId
      dnsZones.outputs.servicesAiZoneId
    ]
    tags: tags
  }
}

module foundryProjectApp 'modules/foundry-project.bicep' = {
  name: 'deploy-foundry-project-app'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    accountName: foundryAccountApp.outputs.accountName
    projectName: 'firstProject'
    tags: tags
  }
}

module foundryAccountAgent 'modules/cognitive-account.bicep' = {
  name: 'deploy-foundry-account-agent'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'foundry-agent-sea${uniqueSuffix}'
    kind: 'AIServices'
    allowProjectManagement: true
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    privateDnsZoneIds: [
      dnsZones.outputs.cognitiveservicesZoneId
      dnsZones.outputs.openaiZoneId
      dnsZones.outputs.servicesAiZoneId
    ]
    tags: tags
  }
}

module foundryProjectAgent 'modules/foundry-project.bicep' = {
  name: 'deploy-foundry-project-agent'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    accountName: foundryAccountAgent.outputs.accountName
    projectName: 'projectrbjp'
    tags: tags
  }
}

module bingApp 'modules/bing-grounding.bicep' = {
  name: 'deploy-bing-app'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    spokeRg
  ]
  params: {
    name: 'bingsearch-app-sea'
    tags: tags
  }
}

module bingAgent 'modules/bing-grounding.bicep' = {
  name: 'deploy-bing-agent'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    spokeRg
  ]
  params: {
    name: 'bing-grounding-agent-sea'
    tags: tags
  }
}

module acr 'modules/container-registry.bicep' = {
  name: 'deploy-acr'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    spokeRg
  ]
  params: {
    location: location
    name: 'acrappsea${uniqueSuffix}'
    tags: tags
  }
}

module thaiSearchSql 'modules/sql-database.bicep' = {
  name: 'deploy-thai-search-sql'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    serverName: 'sql-thai-search-sea-${uniqueSuffix}'
    databaseName: 'thai-search-db'
    entraAdminLogin: sqlEntraAdminLogin
    entraAdminObjectId: sqlEntraAdminObjectId
    entraTenantId: tenant().tenantId
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    sqlPrivateDnsZoneId: dnsZones.outputs.sqlZoneId
    deployElasticPool: deployThaiSearchElasticPool
    elasticPoolName: 'thai-search-pool-sea'
    elasticPoolCapacity: 50
    poolDatabaseName: 'thai-search-pool-demo-db'
    tags: tags
  }
}

@description('Deploy the Basic (50 eDTU) elastic pool and its pool-hosted showcase database alongside thai-search-db.')
param deployThaiSearchElasticPool bool = true

@description('Deploy the Thai surname search PostgreSQL Flexible Server (cheapest Burstable B1ms SKU, Entra-only auth, Private Link).')
param deployThaiSearchPostgres bool = true

module thaiSearchPostgres 'modules/postgres-flexible-server.bicep' = if (deployThaiSearchPostgres) {
  name: 'deploy-thai-search-postgres'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    serverName: 'pg-thai-search-sea-${uniqueSuffix}'
    databaseName: 'thai-search-pg-db'
    entraAdminLogin: sqlEntraAdminLogin
    entraAdminObjectId: sqlEntraAdminObjectId
    entraTenantId: tenant().tenantId
    privateEndpointSubnetId: spokeNetwork.outputs.privateEndpointsSubnetId
    postgresPrivateDnsZoneId: dnsZones.outputs.postgresZoneId
    tags: tags
  }
}

module containerAppsIdentity 'modules/user-assigned-identity.bicep' = {
  name: 'deploy-container-apps-identity'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'uami-container-apps'
    tags: tags
  }
}

module containerAppsAcrPull 'modules/resource-group-role-assignment.bicep' = {
  name: 'assign-container-apps-acr-pull'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    principalId: containerAppsIdentity.outputs.principalId
    roleDefinitionId: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  }
}

module containerAppsCognitiveUser 'modules/resource-group-role-assignment.bicep' = {
  name: 'assign-container-apps-cognitive-user'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    principalId: containerAppsIdentity.outputs.principalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  }
}

module containerAppsStorageReader 'modules/resource-group-role-assignment.bicep' = {
  name: 'assign-container-apps-storage-reader'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    principalId: containerAppsIdentity.outputs.principalId
    roleDefinitionId: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  }
}

module containerAppsSearchServiceContributor 'modules/resource-group-role-assignment.bicep' = {
  name: 'assign-container-apps-search-service-contributor'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    principalId: containerAppsIdentity.outputs.principalId
    roleDefinitionId: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  }
}

module containerAppsSearchDataContributor 'modules/resource-group-role-assignment.bicep' = {
  name: 'assign-container-apps-search-data-contributor'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    principalId: containerAppsIdentity.outputs.principalId
    roleDefinitionId: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  }
}

// ---------------------------------------------------------------------------
// Compute: VMs + optional Bastion (controlled by enableBastion in spoke networking)
// ---------------------------------------------------------------------------

module vm1 'modules/virtual-machine.bicep' = {
  name: 'deploy-vm-1'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    vmName: 'myVm'
    sshKeyName: 'vm-1-key'
    sshPublicKey: sshPublicKeyVm1
    nicName: 'myvm-nic'
    subnetId: spokeNetwork.outputs.vmSubnetId
    nsgId: spokeNetwork.outputs.vmNsg1Id
    enableMdeExtension: enableMdeExtension
    tags: tags
  }
}

module vm2 'modules/virtual-machine.bicep' = {
  name: 'deploy-vm-2'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    vmName: 'vm-2'
    sshKeyName: 'vm-2-key'
    sshPublicKey: sshPublicKeyVm2
    nicName: 'vm-2-nic'
    subnetId: spokeNetwork.outputs.vmSubnetId
    nsgId: spokeNetwork.outputs.vmNsg2Id
    enableMdeExtension: enableMdeExtension
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Container Apps: environment + fe-app, fe-app2, be-app, be-app2, thai-surname-search
// ---------------------------------------------------------------------------

module containerAppsEnvironment 'modules/container-apps-environment.bicep' = {
  name: 'deploy-container-apps-env'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'capps-env-sea'
    infrastructureSubnetId: spokeNetwork.outputs.containerAppsSubnetId
    logAnalyticsWorkspaceName: logAnalytics.outputs.workspaceName
    tags: tags
  }
}

module containerAppsPrivateDns 'modules/container-apps-private-dns.bicep' = {
  name: 'deploy-container-apps-private-dns'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    zoneName: containerAppsEnvironment.outputs.defaultDomain
    environmentStaticIp: containerAppsEnvironment.outputs.staticIp
    hubVnetId: hubNetwork.outputs.vnetId
    spokeVnetId: spokeNetwork.outputs.vnetId
    aiGatewayVnetId: deployAiGateway ? aiGatewayNetwork!.outputs.vnetId : ''
    tags: tags
  }
}

module feApp 'modules/container-app.bicep' = if (deployRepositoryApps) {
  name: 'deploy-fe-app'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    containerAppsAcrPull
    containerAppsStorageReader
  ]
  params: {
    location: location
    name: 'fe-app'
    environmentId: containerAppsEnvironment.outputs.environmentId
    image: '${acr.outputs.acrLoginServer}/ping-url:${appImageTag}'
    targetPort: 8501
    externalIngress: true
    userAssignedIdentityIds: [
      containerAppsIdentity.outputs.identityId
    ]
    registryServer: acr.outputs.acrLoginServer
    envVars: [
      {
        name: 'AZURE_CLIENT_ID'
        value: containerAppsIdentity.outputs.clientId
      }
      {
        name: 'BASE_URL'
        value: 'https://${beApp.outputs.fqdn}'
      }
      {
        name: 'PUBLIC_BACKEND_URL'
        value: 'https://${beApp2.outputs.fqdn}'
      }
      {
        name: 'STORAGE_ACCOUNT_URL'
        value: storagePrivate.outputs.primaryBlobEndpoint
      }
      {
        name: 'STORAGE_CONTAINER'
        value: 'test'
      }
      {
        name: 'PRIV_STORAGE_ACCOUNT_URL'
        value: storagePrivate.outputs.primaryBlobEndpoint
      }
      {
        name: 'PRIV_STORAGE_CONTAINER'
        value: 'test'
      }
    ]
    tags: tags
  }
}

module beApp 'modules/container-app.bicep' = {
  name: 'deploy-be-app'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'be-app'
    environmentId: containerAppsEnvironment.outputs.environmentId
    externalIngress: false
    tags: tags
  }
}

module beApp2 'modules/container-app.bicep' = {
  name: 'deploy-be-app2'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    name: 'be-app2'
    environmentId: containerAppsEnvironment.outputs.environmentId
    externalIngress: false
    tags: tags
  }
}

module feApp2 'modules/container-app.bicep' = if (deployRepositoryApps) {
  name: 'deploy-fe-app2'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    containerAppsAcrPull
    containerAppsCognitiveUser
  ]
  params: {
    location: location
    name: 'fe-app2'
    environmentId: containerAppsEnvironment.outputs.environmentId
    image: '${acr.outputs.acrLoginServer}/azure-ocr-service:${appImageTag}'
    targetPort: 8501
    externalIngress: true
    userAssignedIdentityIds: [
      containerAppsIdentity.outputs.identityId
    ]
    registryServer: acr.outputs.acrLoginServer
    envVars: [
      {
        name: 'AZURE_CLIENT_ID'
        value: containerAppsIdentity.outputs.clientId
      }
      {
        name: 'AZURE_CV_ENDPOINT'
        value: 'https://${foundryAccountApp.outputs.accountName}.cognitiveservices.azure.com/'
      }
    ]
    tags: tags
  }
}

module thaiSurnameSearch 'modules/container-app.bicep' = if (deployRepositoryApps && deployThaiSurnameApp) {
  name: 'deploy-thai-surname-search'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  dependsOn: [
    containerAppsSearchServiceContributor
    containerAppsSearchDataContributor
  ]
  params: {
    location: location
    name: 'thai-surname-search'
    environmentId: containerAppsEnvironment.outputs.environmentId
    image: '${acr.outputs.acrLoginServer}/thai-surname-search:${thaiSurnameAppImageTag}'
    targetPort: 8501
    externalIngress: true
    cpu: '1.0'
    memory: '2Gi'
    userAssignedIdentityIds: [
      containerAppsIdentity.outputs.identityId
    ]
    registryServer: acr.outputs.acrLoginServer
    envVars: [
      {
        name: 'AZURE_CLIENT_ID'
        value: containerAppsIdentity.outputs.clientId
      }
      {
        name: 'AZURE_SQL_SERVER'
        value: thaiSearchSql.outputs.serverFqdn
      }
      {
        name: 'AZURE_SQL_DATABASE'
        value: thaiSearchSql.outputs.databaseName
      }
      {
        name: 'AZURE_SQL_POOL_DATABASE'
        value: thaiSearchSql.outputs.poolDatabaseName
      }
      {
        name: 'AZURE_POSTGRES_SERVER'
        value: deployThaiSearchPostgres ? thaiSearchPostgres!.outputs.serverFqdn : ''
      }
      {
        name: 'AZURE_POSTGRES_DATABASE'
        value: deployThaiSearchPostgres ? thaiSearchPostgres!.outputs.databaseName : ''
      }
      {
        name: 'AZURE_POSTGRES_USER'
        value: 'uami-container-apps'
      }
      {
        name: 'AZURE_SEARCH_ENDPOINT'
        value: 'https://${aiSearch.outputs.searchName}.search.windows.net'
      }
      {
        name: 'AZURE_SEARCH_INDEX'
        value: 'thai-people'
      }
      {
        name: 'FIREWALL_PUBLIC_IP'
        value: enableAzureFirewall ? hubFirewall!.outputs.publicIpAddress : ''
      }
      {
        name: 'AZURE_AGENT_PROJECT_ENDPOINT'
        value: regionalAgentProjectEndpoint
      }
      {
        name: 'AZURE_AGENT_NAME'
        value: regionalAgentName
      }
      {
        name: 'AZURE_AGENT_VERSION'
        value: regionalAgentVersion
      }
      {
        name: 'AZURE_AGENT_MODEL_SKU'
        value: regionalAgentModelSku
      }
      {
        name: 'AZURE_SEA_AGENT_PROJECT_ENDPOINT'
        value: seaAgentProjectEndpoint
      }
      {
        name: 'AZURE_SEA_AGENT_NAME'
        value: seaAgentName
      }
      {
        name: 'AZURE_SEA_AGENT_VERSION'
        value: seaAgentVersion
      }
      {
        name: 'AZURE_SEA_AGENT_MODEL_SKU'
        value: seaAgentModelSku
      }
      {
        name: 'AZURE_GLOBAL_AGENT_PROJECT_ENDPOINT'
        value: regionalAgentProjectEndpoint
      }
      {
        name: 'AZURE_GLOBAL_AGENT_NAME'
        value: globalAgentName
      }
      {
        name: 'AZURE_GLOBAL_AGENT_VERSION'
        value: globalAgentVersion
      }
      {
        name: 'AZURE_SEA_STANDARD_AGENT_PROJECT_ENDPOINT'
        value: seaAgentProjectEndpoint
      }
      {
        name: 'AZURE_SEA_STANDARD_AGENT_NAME'
        value: seaStandardAgentName
      }
      {
        name: 'AZURE_SEA_STANDARD_AGENT_VERSION'
        value: seaStandardAgentVersion
      }
      {
        name: 'AZURE_SEA_STANDARD_AGENT_MODEL_SKU'
        value: 'Standard'
      }
      {
        name: 'AZURE_GLOBAL_AGENT_MODEL_SKU'
        value: 'GlobalStandard'
      }
    ]
    tags: tags
  }
}

module thaiPublicGateway 'modules/application-gateway-waf.bicep' = if (deployRepositoryApps && deployThaiSurnameApp && enableThaiPublicGateway) {
  name: 'deploy-thai-public-waf'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  dependsOn: [
    containerAppsPrivateDns
    hubFirewall
  ]
  params: {
    location: location
    name: 'agw-thai-search-sea'
    subnetId: hubNetwork.outputs.applicationGatewaySubnetId
    backendFqdn: thaiSurnameSearch!.outputs.fqdn
    publicDnsLabel: 'thai-search-sea-${uniqueSuffix}'
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Function App stack
// ---------------------------------------------------------------------------

module functionApp 'modules/function-app.bicep' = {
  name: 'deploy-function-app'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    location: location
    baseName: functionAppBaseName
    integrationSubnetId: spokeNetwork.outputs.functionAppSubnetId
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    functionStorageAccountName: storageFunctionApp.outputs.storageName
    deploymentStorageContainerName: functionDeploymentContainerName
    maximumInstanceCount: 40
    instanceMemoryMB: 512
    deployDurableTaskScheduler: false
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// AI Gateway Landing Zone (APIM, hub Foundry, Managed Redis, usage/chargeback
// pipeline). See docs/ai-gateway-landing-zone.md for the full design.
// ---------------------------------------------------------------------------

module aiGatewayKeyVault 'modules/key-vault.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-key-vault'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    name: 'kv-aigw-${aiGatewayUniqueSuffix}'
    privateEndpointSubnetId: aiGatewayNetwork!.outputs.privateEndpointsSubnetId
    vaultPrivateDnsZoneId: dnsZones.outputs.vaultZoneId
    tags: tags
  }
}

module aiGatewayRedis 'modules/managed-redis.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-redis'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    name: 'redis-hub-sea-${aiGatewayUniqueSuffix}'
    privateEndpointSubnetId: aiGatewayNetwork!.outputs.privateEndpointsSubnetId
    redisPrivateDnsZoneId: dnsZones.outputs.redisZoneId
    tags: tags
  }
}

module aiGatewayEventHub 'modules/event-hub-namespace.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-event-hub'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    namespaceName: 'evhns-hub-sea-${aiGatewayUniqueSuffix}'
    privateEndpointSubnetId: aiGatewayNetwork!.outputs.privateEndpointsSubnetId
    apimOutboundSubnetId: aiGatewayNetwork!.outputs.apimOutboundSubnetId
    serviceBusPrivateDnsZoneId: dnsZones.outputs.serviceBusZoneId
    tags: tags
  }
}

module aiGatewayCosmos 'modules/cosmos-account.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-cosmos'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    name: 'cosmos-hub-sea${aiGatewayUniqueSuffix}'
    privateEndpointSubnetId: aiGatewayNetwork!.outputs.privateEndpointsSubnetId
    documentsPrivateDnsZoneId: dnsZones.outputs.documentsZoneId
    enableServerless: true
    tags: tags
  }
}

module aiGatewayCosmosUsageDb 'modules/cosmos-sql-database.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-cosmos-usage-db'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    accountName: aiGatewayCosmos!.outputs.cosmosName
    databaseName: 'usage'
    containerName: 'token-usage-daily'
    partitionKeyPath: '/department'
  }
}

module aiGatewayLogAnalytics 'modules/log-analytics.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-log-analytics'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  dependsOn: [
    aiGatewayRg
  ]
  params: {
    location: location
    name: 'workspace-ai-gateway-sea'
    tags: tags
  }
}

module aiGatewayAppInsights 'modules/app-insights.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-app-insights'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    name: 'appi-apim-sea'
    logAnalyticsWorkspaceId: aiGatewayLogAnalytics!.outputs.workspaceId
    tags: tags
  }
}

module aiGatewayCostWorkbook 'modules/cost-workbook.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-cost-workbook'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    appInsightsId: aiGatewayAppInsights!.outputs.id
    tags: tags
  }
}

module aiGatewayStorage 'modules/storage-account.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-storage'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    name: 'stlogicaigw${aiGatewayUniqueSuffix}'
    privateEndpointSubnetId: aiGatewayNetwork!.outputs.privateEndpointsSubnetId
    blobPrivateDnsZoneId: dnsZones.outputs.blobZoneId
    enableFilePrivateEndpoint: true
    filePrivateDnsZoneId: dnsZones.outputs.fileZoneId
    allowSharedKeyAccess: true
    tags: tags
  }
}

module aiGatewayLogicApp 'modules/logic-app-standard.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-logic-app'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    // Microsoft.Web/sites names are globally unique across all of Azure (they get a
    // public *.azurewebsites.net hostname) — a fixed name collided with an existing
    // customer's app on first deploy ("Website with given name ... already exists"),
    // so the unique suffix (same pattern as the other aiGateway resources) is required.
    name: 'logic-hub-usage-sea${aiGatewayUniqueSuffix}'
    integrationSubnetId: aiGatewayNetwork!.outputs.logicAppSubnetId
    logAnalyticsWorkspaceId: aiGatewayLogAnalytics!.outputs.workspaceId
    storageAccountName: aiGatewayStorage!.outputs.storageName
    usageLogAnalyticsWorkspaceCustomerId: aiGatewayLogAnalytics!.outputs.workspaceCustomerId
    usageAppInsightsAppId: aiGatewayAppInsights!.outputs.appId
    usageCosmosAccountEndpoint: 'https://${aiGatewayCosmos!.outputs.cosmosName}.documents.azure.com:443/'
    usageCosmosDatabaseName: aiGatewayCosmosUsageDb!.outputs.databaseName
    usageCosmosContainerName: aiGatewayCosmosUsageDb!.outputs.containerName
    tags: tags
  }
}

module foundryAccountHub 'modules/cognitive-account.bicep' = if (deployAiGateway) {
  name: 'deploy-foundry-account-hub'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    name: 'aif-hub-sea${aiGatewayUniqueSuffix}'
    kind: 'AIServices'
    allowProjectManagement: true
    privateEndpointSubnetId: aiGatewayNetwork!.outputs.privateEndpointsSubnetId
    privateDnsZoneIds: [
      dnsZones.outputs.cognitiveservicesZoneId
      dnsZones.outputs.openaiZoneId
      dnsZones.outputs.servicesAiZoneId
    ]
    tags: tags
  }
}

module foundryProjectHub 'modules/foundry-project.bicep' = if (deployAiGateway) {
  name: 'deploy-foundry-project-hub'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    accountName: foundryAccountHub!.outputs.accountName
    projectName: 'aiGatewayHubProject'
    tags: tags
  }
}

// Connects the hub Foundry account + project to the AI Gateway's existing App Insights, so
// Foundry Portal's own Traces/Monitor tabs (and the "Create or connect an App Insights
// resource" prompt shown when opening an agent's Monitor settings) work out of the box —
// distinct from, and in addition to, the APIM->App Insights logging that only sees
// gateway-routed calls (see modules/foundry-appinsights-connection.bicep for the full
// rationale).
module foundryHubAppInsightsConnection 'modules/foundry-appinsights-connection.bicep' = if (deployAiGateway) {
  name: 'deploy-foundry-hub-appinsights-connection'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  dependsOn: [
    foundryProjectHub
  ]
  params: {
    accountName: foundryAccountHub!.outputs.accountName
    projectName: 'aiGatewayHubProject'
    appInsightsName: aiGatewayAppInsights!.outputs.name
    appInsightsId: aiGatewayAppInsights!.outputs.id
    appInsightsConnectionString: aiGatewayAppInsights!.outputs.connectionString
    deployReaderRoleAssignments: deployFoundryAppInsightsRoleAssignments
  }
}

module foundryHubDeploymentChat 'modules/cognitive-deployment.bicep' = if (deployAiGateway) {
  name: 'deploy-foundry-hub-deployment-chat'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    accountName: foundryAccountHub!.outputs.accountName
    deploymentName: 'gpt-4o-hub-prod'
    // gpt-4o's GlobalStandard SKU in this subscription/region maps only to fine-tune
    // usage quotas (verified via `az cognitiveservices account list-models`), not base
    // chat; gpt-4.1-mini has a confirmed, actively-used GlobalStandard chat SKU
    // (`OpenAI.GlobalStandard.gpt4.1-mini`) so it's used here as the primary hub chat
    // model. Swap modelName/modelVersion below if your subscription's catalog differs.
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
    skuName: 'GlobalStandard'
    capacity: 50
  }
}

module foundryHubDeploymentEmbeddings 'modules/cognitive-deployment.bicep' = if (deployAiGateway) {
  name: 'deploy-foundry-hub-deployment-embeddings'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  // Cognitive Services rejects concurrent model-deployment operations on the same
  // account ("Another operation is being performed on the parent resource") — confirmed
  // via a real deployment failure when this ran in parallel with the chat deployment.
  // Force serialization with an explicit dependsOn.
  dependsOn: [
    foundryHubDeploymentChat
  ]
  params: {
    accountName: foundryAccountHub!.outputs.accountName
    deploymentName: 'text-embedding-3-small'
    modelName: 'text-embedding-3-small'
    modelVersion: '1'
    // text-embedding-3-small v1 only exposes GlobalStandard/DataZoneStandard in this region
    // (verified via `az cognitiveservices account list-models`), not a plain "Standard" SKU.
    skuName: 'GlobalStandard'
    capacity: 30
  }
}

module aiGatewayApim 'modules/apim.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-apim'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: location
    apimName: 'apim-hub-sea${aiGatewayUniqueSuffix}'
    publisherEmail: apimPublisherEmail
    outboundSubnetId: aiGatewayNetwork!.outputs.apimOutboundSubnetId
    departments: aiGatewayDepartments
    hubFoundryBackendUrl: 'https://${foundryAccountHub!.outputs.accountName}.cognitiveservices.azure.com/openai'
    hubFoundryAccountId: foundryAccountHub!.outputs.accountId
    spokeFoundryBackendUrl: 'https://${foundryAccountApp.outputs.accountName}.cognitiveservices.azure.com/openai'
    spokeFoundryAccountId: foundryAccountApp.outputs.accountId
    embeddingsBackendUrl: 'https://${foundryAccountHub!.outputs.accountName}.cognitiveservices.azure.com/openai/deployments/${foundryHubDeploymentEmbeddings!.outputs.deploymentName}/embeddings'
    // The Foundry project (currently `aiGatewayHubProject`, auto-provisioned the first time
    // the hub Foundry account is opened in the Foundry Portal — not itself Bicep-managed
    // yet) exposes a separate Responses API surface used to invoke a specific PUBLISHED
    // agent by name/version (see modules/policies/api-agents-policy.xml). Update
    // hubFoundryProjectName if the project is ever renamed/recreated.
    hubFoundryProjectAgentsUrl: 'https://${foundryAccountHub!.outputs.accountName}.services.ai.azure.com/api/projects/${hubFoundryProjectName}/openai/v1'
    redisClusterName: aiGatewayRedis!.outputs.redisClusterName
    redisHostName: aiGatewayRedis!.outputs.redisHostName
    entraTenantId: tenant().tenantId
    entraAudience: entraAudience
    spokeAppProjectPrincipalId: foundryProjectApp.outputs.principalId
    spokeAgentProjectPrincipalId: foundryProjectAgent.outputs.principalId
    appInsightsId: aiGatewayAppInsights!.outputs.id
    appInsightsConnectionString: aiGatewayAppInsights!.outputs.connectionString
    eventHubNamespaceHostName: '${aiGatewayEventHub!.outputs.namespaceName}.servicebus.windows.net'
    eventHubNamespaceId: aiGatewayEventHub!.outputs.namespaceId
    eventHubName: aiGatewayEventHub!.outputs.eventHubName
    tags: tags
  }
}

module foundryAppHubGatewayConnection 'modules/foundry-apim-model-connection.bicep' = if (deployAiGateway) {
  name: 'connect-foundry-app-to-hub-ai-gateway'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    accountName: foundryAccountApp.outputs.accountName
    connectionName: 'hub-ai-gateway'
    gatewayBaseUrl: '${aiGatewayApim!.outputs.gatewayUrl}/openai'
    deploymentName: foundryHubDeploymentChat!.outputs.deploymentName
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
  }
}

module foundryAgentHubGatewayConnection 'modules/foundry-apim-model-connection.bicep' = if (deployAiGateway) {
  name: 'connect-foundry-agent-to-hub-ai-gateway'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    accountName: foundryAccountAgent.outputs.accountName
    connectionName: 'hub-ai-gateway'
    gatewayBaseUrl: '${aiGatewayApim!.outputs.gatewayUrl}/openai'
    deploymentName: foundryHubDeploymentChat!.outputs.deploymentName
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
  }
}

module aiGatewayApiCenter 'modules/api-center.bicep' = if (deployAiGateway) {
  name: 'deploy-ai-gateway-api-center'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    location: apiCenterLocation
    name: 'apic-hub-sea${aiGatewayUniqueSuffix}'
    apimName: aiGatewayApim!.outputs.apimName
    tags: tags
  }
}

// The APIM system-assigned identity is the priority-1 (hub) backend credential —
// granted Cognitive Services User on the hub Foundry account in this same resource group.
module aiGatewayApimHubCognitiveUser 'modules/resource-group-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-apim-hub-cognitive-user'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    principalId: aiGatewayApim!.outputs.apimPrincipalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  }
}

// Priority-2 overflow backend: the same APIM identity is also granted Cognitive Services
// User on the existing spoke Foundry account (foundryAccountApp), cross-subscription, so
// the hub-first failover policy can fail over there once the hub's quota is exhausted —
// no other changes are required in the spoke.
module aiGatewayApimSpokeCognitiveUser 'modules/resource-group-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-apim-spoke-cognitive-user'
  scope: resourceGroup(spokeSubscriptionId, spokeResourceGroupName)
  params: {
    principalId: aiGatewayApim!.outputs.apimPrincipalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  }
}

// APIM's identity also needs "Foundry Agent Consumer" (data action
// Microsoft.CognitiveServices/accounts/AIServices/endpoints/interact/action) to invoke a
// SPECIFIC published Foundry agent by name/version via the Responses API
// (modules/policies/api-agents-policy.xml / hub-foundry-agents-backend) — this is a
// distinct permission from "Cognitive Services User" above, which only covers raw model
// deployment calls, not named-agent invocation.
module aiGatewayApimFoundryAgentConsumer 'modules/resource-group-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-apim-foundry-agent-consumer'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    principalId: aiGatewayApim!.outputs.apimPrincipalId
    roleDefinitionId: 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6'
  }
}

// APIM's identity is granted Azure Event Hubs Data Sender inside modules/apim.bicep itself
// (not as a separate module here), so the RBAC assignment completes with the loggers/
// fragments in the same nested deployment before the logger validates it, instead of only
// after this module's outputs resolve (which caused "unauthorized operation" on first deploy).

// logic-hub-usage-sea's identity needs Log Analytics Reader (to query customMetrics via the
// Log Analytics Query API) and Cosmos DB data-plane write access (to upsert daily rollups).
module aiGatewayLogicAppLogAnalyticsReader 'modules/resource-group-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-logicapp-log-analytics-reader'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    principalId: aiGatewayLogicApp!.outputs.principalId
    roleDefinitionId: '73c42c96-874c-492b-b04d-ab87d138a893'
  }
}

module aiGatewayLogicAppCosmosContributor 'modules/cosmos-sql-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-logicapp-cosmos-contributor'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    accountName: aiGatewayCosmos!.outputs.cosmosName
    principalId: aiGatewayLogicApp!.outputs.principalId
  }
}

// APIM (Redis connection string source) and the Logic App (future Key Vault-backed
// secrets) both get Key Vault Secrets User on kv-aigw-<suffix>.
module aiGatewayApimKeyVaultSecretsUser 'modules/resource-group-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-apim-kv-secrets-user'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    principalId: aiGatewayApim!.outputs.apimPrincipalId
    roleDefinitionId: '4633458b-17de-408a-b874-0445c86b69e6'
  }
}

module aiGatewayLogicAppKeyVaultSecretsUser 'modules/resource-group-role-assignment.bicep' = if (deployAiGateway) {
  name: 'assign-ai-gateway-logicapp-kv-secrets-user'
  scope: resourceGroup(aiGatewaySubscriptionId, aiGatewayResourceGroupName)
  params: {
    principalId: aiGatewayLogicApp!.outputs.principalId
    roleDefinitionId: '4633458b-17de-408a-b874-0445c86b69e6'
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output hubSubscription string = hubSubscriptionId
output spokeSubscription string = spokeSubscriptionId
output hubResourceGroup string = hubResourceGroupName
output spokeResourceGroup string = spokeResourceGroupName
output hubVnetId string = hubNetwork.outputs.vnetId
output spokeVnetId string = spokeNetwork.outputs.vnetId
output vpnGatewayName string = hubNetwork.outputs.vpnGatewayName
output firewallPrivateIpAddress string = enableAzureFirewall ? hubFirewall!.outputs.privateIpAddress : ''
output thaiSearchPublicUrl string = deployRepositoryApps && deployThaiSurnameApp && enableThaiPublicGateway ? thaiPublicGateway!.outputs.publicUrl : ''
output aiGatewaySubscription string = aiGatewaySubscriptionId
output aiGatewayResourceGroup string = aiGatewayResourceGroupName
output aiGatewayVnetId string = deployAiGateway ? aiGatewayNetwork!.outputs.vnetId : ''
output aiGatewayApimGatewayUrl string = deployAiGateway ? aiGatewayApim!.outputs.gatewayUrl : ''
output aiGatewayApiCenterName string = deployAiGateway ? aiGatewayApiCenter!.outputs.apiCenterName : ''
output aiGatewayHubFoundryAccountName string = deployAiGateway ? foundryAccountHub!.outputs.accountName : ''
output spokeFoundryAppGatewayModel string = deployAiGateway ? foundryAppHubGatewayConnection!.outputs.modelReference : ''
output spokeFoundryAgentGatewayModel string = deployAiGateway ? foundryAgentHubGatewayConnection!.outputs.modelReference : ''
output thaiSearchSqlServerFqdn string = thaiSearchSql.outputs.serverFqdn
output thaiSearchSqlElasticPoolName string = thaiSearchSql.outputs.elasticPoolName
output thaiSearchSqlPoolDatabaseName string = thaiSearchSql.outputs.poolDatabaseName
output thaiSearchPostgresServerFqdn string = deployThaiSearchPostgres ? thaiSearchPostgres!.outputs.serverFqdn : ''
output thaiSearchPostgresDatabaseName string = deployThaiSearchPostgres ? thaiSearchPostgres!.outputs.databaseName : ''
