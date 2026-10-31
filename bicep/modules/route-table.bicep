// User-defined route table. Routes are passed in so the same module serves the
// hub, workload spoke, and AI Gateway subscriptions.

@description('Region.')
param location string = 'southeastasia'

@description('Route table name.')
param name string

@description('Routes: array of { name, addressPrefix, nextHopType, nextHopIpAddress? }.')
param routes array

@description('Disable BGP route propagation (keeps VPN-learned routes off the subnet when true).')
param disableBgpRoutePropagation bool = false

param tags object = {}

resource routeTable 'Microsoft.Network/routeTables@2023-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    disableBgpRoutePropagation: disableBgpRoutePropagation
    routes: [for route in routes: {
      name: route.name
      properties: {
        addressPrefix: route.addressPrefix
        nextHopType: route.nextHopType
        nextHopIpAddress: contains(route, 'nextHopIpAddress') ? route.nextHopIpAddress : null
      }
    }]
  }
}

output id string = routeTable.id
output name string = routeTable.name
