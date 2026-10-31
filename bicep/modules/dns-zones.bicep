// Centralized private DNS zones, hosted in the hub resource group and linked to both
// the hub VNet and the single spoke VNet. This replaces the zones that previously lived
// in rg-vm-vnet-test and rg-foundry-standard-private-westus3.
// Deployed at resource-group scope (the hub resource group).

@description('Resource ID of the hub virtual network (linked to every zone).')
param hubVnetId string

@description('Resource ID of the single spoke virtual network (linked to every zone).')
param spokeVnetId string

@description('Resource ID of the AI Gateway virtual network (linked to every zone). Leave empty to skip — the AI Gateway subscription is optional.')
param aiGatewayVnetId string = ''

@description('Private DNS zone names to create and link. New entries must be appended at the end — the named outputs below rely on this fixed ordering.')
param zoneNames array = [
  'privatelink.blob.${environment().suffixes.storage}'
  'privatelink.queue.${environment().suffixes.storage}'
  'privatelink.table.${environment().suffixes.storage}'
  'privatelink.documents.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.search.windows.net'
  'privatelink${environment().suffixes.sqlServerHostname}'
  'privatelink.redis.azure.net'
  'privatelink.servicebus.windows.net'
  'privatelink.vaultcore.azure.net'
  'privatelink.file.${environment().suffixes.storage}'
  'privatelink.postgres.database.azure.com'
]

param tags object = {}

var deployAiGatewayLinks = !empty(aiGatewayVnetId)

resource zones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zoneName in zoneNames: {
  name: zoneName
  location: 'global'
  tags: tags
}]

resource hubLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in zoneNames: {
  parent: zones[i]
  name: 'link-hub-vnet-hub-2'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: hubVnetId
    }
  }
}]

resource spokeLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in zoneNames: {
  parent: zones[i]
  name: 'link-spoke-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: spokeVnetId
    }
  }
}]

resource aiGatewayLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in zoneNames: if (deployAiGatewayLinks) {
  parent: zones[i]
  name: 'link-ai-gateway-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: aiGatewayVnetId
    }
  }
}]

output zoneIds array = [for i in range(0, length(zoneNames)): zones[i].id]
output zoneNamesOut array = zoneNames

// Named outputs for direct consumption by other modules (relies on the default
// zoneNames ordering above — do not reorder that array without updating these).
output blobZoneId string = zones[0].id
output queueZoneId string = zones[1].id
output tableZoneId string = zones[2].id
output documentsZoneId string = zones[3].id
output cognitiveservicesZoneId string = zones[4].id
output openaiZoneId string = zones[5].id
output servicesAiZoneId string = zones[6].id
output searchZoneId string = zones[7].id
output sqlZoneId string = zones[8].id
output redisZoneId string = zones[9].id
output serviceBusZoneId string = zones[10].id
output vaultZoneId string = zones[11].id
output fileZoneId string = zones[12].id
output postgresZoneId string = zones[13].id
