// Standalone addon: adds the privatelink.postgres.database.azure.com private DNS zone
// and its hub/spoke/AI-Gateway VNet links, without touching the other 13 zones already
// managed by modules/dns-zones.bicep. Deploy at resource-group scope in the hub RG.
//
// The resource/zone/link names here match modules/dns-zones.bicep's convention exactly,
// so a future full `main.bicep` redeploy is a no-op against what this addon creates.

@description('Resource ID of the hub virtual network.')
param hubVnetId string

@description('Resource ID of the single spoke virtual network.')
param spokeVnetId string

@description('Resource ID of the AI Gateway virtual network. Leave empty to skip linking.')
param aiGatewayVnetId string = ''

param tags object = {}

var zoneName = 'privatelink.postgres.database.azure.com'
var deployAiGatewayLink = !empty(aiGatewayVnetId)

resource zone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: zoneName
  location: 'global'
  tags: tags
}

resource hubLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zone
  name: 'link-hub-vnet-hub-2'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: hubVnetId
    }
  }
}

resource spokeLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zone
  name: 'link-spoke-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: spokeVnetId
    }
  }
}

resource aiGatewayLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (deployAiGatewayLink) {
  parent: zone
  name: 'link-ai-gateway-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: aiGatewayVnetId
    }
  }
}

output zoneId string = zone.id
