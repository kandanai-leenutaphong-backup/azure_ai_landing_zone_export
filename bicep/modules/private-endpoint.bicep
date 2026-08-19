// Generic private endpoint + private DNS zone group, deployed into the single spoke
// resource group's snet-pe subnet. The DNS zone lives in the hub resource group and is
// referenced purely by resource ID (no cross-RG "existing" symbolic reference needed).

@description('Region for the private endpoint.')
param location string = 'southeastasia'

@description('Name of the private endpoint.')
param name string

@description('Subnet resource ID (snet-pe in the single spoke VNet).')
param subnetId string

@description('Resource ID of the target PaaS resource (storage, cosmos, cognitive services, search, etc.).')
param targetResourceId string

@description('groupIds for the private link service connection, e.g. ["blob"], ["Sql"], ["account"], ["searchService"].')
param groupIds array

@description('Resource IDs of the private DNS zone(s) (hosted in the hub resource group) used for the zone group. Most resource types need one; multi-service accounts (e.g. AI Foundry) need several.')
param privateDnsZoneIds array

param tags object = {}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${name}-connection'
        properties: {
          privateLinkServiceId: targetResourceId
          groupIds: groupIds
        }
      }
    ]
  }
}

resource zoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (zoneId, i) in privateDnsZoneIds: {
      name: 'zone-${i}'
      properties: {
        privateDnsZoneId: zoneId
      }
    }]
  }
}

output privateEndpointId string = privateEndpoint.id
