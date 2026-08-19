// Spoke-side half of the hub<->spoke VNet peering.
// Deployed at the single spoke resource-group scope.

@description('Name of the spoke virtual network.')
param spokeVnetName string

@description('Resource ID of the hub virtual network.')
param hubVnetId string

resource spokeVnet 'Microsoft.Network/virtualNetworks@2023-11-01' existing = {
  name: spokeVnetName
}

resource spokeToHubPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-11-01' = {
  parent: spokeVnet
  name: '${spokeVnetName}-to-hub'
  properties: {
    remoteVirtualNetwork: {
      id: hubVnetId
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: true
  }
}

output spokeToHubPeeringName string = spokeToHubPeering.name
