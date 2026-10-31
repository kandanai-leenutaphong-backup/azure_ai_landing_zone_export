targetScope = 'subscription'

param location string = 'westus3'
param regionCode string = 'wus3'
param resourceGroupName string = 'rg-ai-dev-${regionCode}'
param vnetName string = 'vnet-spoke-agent-${regionCode}'
param vnetAddressPrefix string = '10.80.0.0/16'
param agentSubnetPrefix string = '10.80.5.0/24'
param privateEndpointSubnetPrefix string = '10.80.6.0/24'
param developerPrincipalId string
@description('Optional managed identity principal allowed to invoke this project, such as the SEA Container App identity.')
param callerPrincipalId string = ''
param hubSubscriptionId string = '1b00124c-ed9b-4d33-9bd6-4d14c09c9857'
param hubResourceGroupName string = 'rg-hub-sea'
param hubVnetName string = 'vnet-hub-2'
param seaSubscriptionId string = 'd88c020a-2180-43da-91a2-f6cc01f25946'
param seaResourceGroupName string = 'rg-ai-dev-sea'
param seaVnetName string = 'vnet-spoke-app-sea'

var tags = {
  environment: 'dev'
  workload: 'foundry-standard-agent'
}
var hubVnetId = resourceId(hubSubscriptionId, hubResourceGroupName, 'Microsoft.Network/virtualNetworks', hubVnetName)
var seaVnetId = resourceId(seaSubscriptionId, seaResourceGroupName, 'Microsoft.Network/virtualNetworks', seaVnetName)
var dnsZoneNames = [
  'privatelink.blob.${environment().suffixes.storage}'
  'privatelink.documents.azure.com'
  'privatelink.search.windows.net'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
]
var dnsZoneIds = [for zoneName in dnsZoneNames: resourceId(hubSubscriptionId, hubResourceGroupName, 'Microsoft.Network/privateDnsZones', zoneName)]

resource spokeResourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module network 'modules/minimal-agent-network.bicep' = {
  name: '${regionCode}-agent-network'
  scope: spokeResourceGroup
  params: {
    location: location
    vnetName: vnetName
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetPrefix: agentSubnetPrefix
    privateEndpointSubnetPrefix: privateEndpointSubnetPrefix
    tags: tags
  }
}

module dnsLinks 'modules/existing-private-dns-links.bicep' = {
  name: '${regionCode}-agent-dns-links'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    zoneNames: dnsZoneNames
    vnetId: network.outputs.vnetId
    linkName: vnetName
    tags: tags
  }
}

module hubToAgentSpoke 'modules/vnet-peering-hub-side.bicep' = {
  name: 'hub-to-${regionCode}-agent'
  scope: resourceGroup(hubSubscriptionId, hubResourceGroupName)
  params: {
    hubVnetName: hubVnetName
    spokeVnetName: vnetName
    spokeVnetId: network.outputs.vnetId
  }
}

module agentSpokeToHub 'modules/vnet-peering-spoke-side.bicep' = {
  name: '${regionCode}-agent-to-hub'
  scope: spokeResourceGroup
  params: {
    spokeVnetName: vnetName
    hubVnetId: hubVnetId
  }
  dependsOn: [
    hubToAgentSpoke
  ]
}

module seaToAgentSpoke 'modules/vnet-peering-direct.bicep' = {
  name: 'sea-spoke-to-${regionCode}-agent'
  scope: resourceGroup(seaSubscriptionId, seaResourceGroupName)
  params: {
    localVnetName: seaVnetName
    remoteVnetId: network.outputs.vnetId
    peeringName: '${seaVnetName}-to-${regionCode}'
  }
}

module agentSpokeToSea 'modules/vnet-peering-direct.bicep' = {
  name: '${regionCode}-agent-to-sea-spoke'
  scope: spokeResourceGroup
  params: {
    localVnetName: vnetName
    remoteVnetId: seaVnetId
    peeringName: '${vnetName}-to-sea'
  }
  dependsOn: [
    seaToAgentSpoke
  ]
}

module workload 'modules/minimal-standard-agent.bicep' = {
  name: '${regionCode}-standard-agent'
  scope: spokeResourceGroup
  params: {
    location: location
    regionCode: regionCode
    agentSubnetId: network.outputs.agentSubnetId
    privateEndpointSubnetId: network.outputs.privateEndpointSubnetId
    dnsZoneIds: dnsZoneIds
    developerPrincipalId: developerPrincipalId
    tags: tags
  }
  dependsOn: [
    dnsLinks
    agentSpokeToHub
    agentSpokeToSea
  ]
}

module callerAccess 'modules/foundry-agent-invoker-access.bicep' = if (!empty(callerPrincipalId)) {
  name: '${regionCode}-agent-caller-access'
  scope: spokeResourceGroup
  params: {
    accountName: workload.outputs.accountName
    projectName: workload.outputs.projectName
    principalId: callerPrincipalId
  }
}

output spokeVnetId string = network.outputs.vnetId
output foundryAccountName string = workload.outputs.accountName
output foundryProjectName string = workload.outputs.projectName
output projectEndpoint string = workload.outputs.projectEndpoint
output searchName string = workload.outputs.searchName
output storageName string = workload.outputs.storageName
output cosmosName string = workload.outputs.cosmosName
