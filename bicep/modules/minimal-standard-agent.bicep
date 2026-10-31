// Adapted from microsoft-foundry/foundry-samples' 15-private-network-standard-agent-setup.
// Keep the capability-host flow used by the existing SEA spoke, without ACR or monitoring.
param location string
param regionCode string
param agentSubnetId string
param privateEndpointSubnetId string
param dnsZoneIds string[]
param developerPrincipalId string
param tags object = {}

var suffix = uniqueString(resourceGroup().id)
var accountName = 'foundry-agent-${regionCode}${suffix}'
var storageName = 'stfoundry${suffix}'
var searchName = 'search-foundry-${regionCode}${suffix}'
var cosmosName = 'cosmos-foundry-${regionCode}${suffix}'

module storage 'storage-account.bicep' = {
  name: 'agent-storage'
  params: {
    location: location
    name: storageName
    privateEndpointSubnetId: privateEndpointSubnetId
    blobPrivateDnsZoneId: dnsZoneIds[0]
    allowSharedKeyAccess: false
    tags: tags
  }
}

module cosmos 'cosmos-account.bicep' = {
  name: 'agent-cosmos'
  params: {
    location: location
    name: cosmosName
    privateEndpointSubnetId: privateEndpointSubnetId
    documentsPrivateDnsZoneId: dnsZoneIds[1]
    enableServerless: true
    disableLocalAuth: true
    enableAutomaticFailover: true
    tags: tags
  }
}

module search 'search-service.bicep' = {
  name: 'agent-search'
  params: {
    location: location
    name: searchName
    privateEndpointSubnetId: privateEndpointSubnetId
    searchPrivateDnsZoneId: dnsZoneIds[2]
    tags: tags
  }
}

module foundry 'foundry-standard-agent.bicep' = {
  name: 'agent-foundry'
  params: {
    location: location
    accountName: accountName
    projectName: 'agent-project'
    agentSubnetId: agentSubnetId
    privateEndpointSubnetId: privateEndpointSubnetId
    privateDnsZoneIds: [
      dnsZoneIds[3]
      dnsZoneIds[4]
      dnsZoneIds[5]
    ]
    storageName: storage.outputs.storageName
    cosmosName: cosmos.outputs.cosmosName
    searchName: search.outputs.searchName
    developerPrincipalId: developerPrincipalId
    tags: tags
  }
}

output accountName string = foundry.outputs.accountName
output projectName string = foundry.outputs.projectName
output projectEndpoint string = foundry.outputs.projectEndpoint
output storageName string = storage.outputs.storageName
output cosmosName string = cosmos.outputs.cosmosName
output searchName string = search.outputs.searchName
