// Private DNS for an internal Azure Container Apps environment.

@description('Generated default domain of the Container Apps environment.')
param zoneName string

@description('Static private IP of the internal Container Apps environment.')
param environmentStaticIp string

@description('Resource ID of the hub virtual network.')
param hubVnetId string

@description('Resource ID of the spoke virtual network.')
param spokeVnetId string

param tags object = {}

resource zone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: zoneName
  location: 'global'
  tags: tags
}

resource apexRecord 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
  parent: zone
  name: '@'
  properties: {
    ttl: 60
    aRecords: [
      {
        ipv4Address: environmentStaticIp
      }
    ]
  }
}

resource wildcardRecord 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
  parent: zone
  name: '*'
  properties: {
    ttl: 60
    aRecords: [
      {
        ipv4Address: environmentStaticIp
      }
    ]
  }
}

resource internalWildcardRecord 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
  parent: zone
  name: '*.internal'
  properties: {
    ttl: 60
    aRecords: [
      {
        ipv4Address: environmentStaticIp
      }
    ]
  }
}

resource hubLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zone
  name: 'link-hub-vnet'
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

output zoneId string = zone.id
