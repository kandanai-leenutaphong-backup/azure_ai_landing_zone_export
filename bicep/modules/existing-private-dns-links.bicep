param zoneNames string[]
param vnetId string
param linkName string
param tags object = {}

resource zones 'Microsoft.Network/privateDnsZones@2020-06-01' existing = [for zoneName in zoneNames: {
  name: zoneName
}]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in zoneNames: {
  parent: zones[i]
  name: linkName
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}]
