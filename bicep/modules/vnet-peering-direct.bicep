@description('Name of the local virtual network.')
param localVnetName string

@description('Resource ID of the remote virtual network.')
param remoteVnetId string

@description('Name of the peering resource.')
param peeringName string

resource localVnet 'Microsoft.Network/virtualNetworks@2023-11-01' existing = {
  name: localVnetName
}

resource peering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-11-01' = {
  parent: localVnet
  name: peeringName
  properties: {
    remoteVirtualNetwork: {
      id: remoteVnetId
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

output peeringName string = peering.name
