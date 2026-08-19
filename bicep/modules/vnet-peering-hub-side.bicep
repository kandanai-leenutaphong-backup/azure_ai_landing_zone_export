// Bidirectional VNet peering between the hub and the single spoke VNet.
// Deploy this module twice is not needed; it creates both peering directions
// by taking both VNet names/resource groups as parameters (cross-RG scope via modules).

@description('Name of the hub virtual network.')
param hubVnetName string

@description('Name of the spoke virtual network.')
param spokeVnetName string

@description('Resource ID of the spoke virtual network.')
param spokeVnetId string

resource hubVnet 'Microsoft.Network/virtualNetworks@2023-11-01' existing = {
  name: hubVnetName
}

resource hubToSpokePeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-11-01' = {
  parent: hubVnet
  name: 'hub-to-${spokeVnetName}'
  properties: {
    remoteVirtualNetwork: {
      id: spokeVnetId
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
  }
}

output hubToSpokePeeringName string = hubToSpokePeering.name
