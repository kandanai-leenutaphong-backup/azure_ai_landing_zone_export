// Event Hub namespace + a single event hub, used as the durable usage-event ingestion
// path for the AI Gateway chargeback pipeline. Reachable both privately (private endpoint,
// for VNet-resident clients like the usage-rollup Logic App) and publicly (required — see
// apimOutboundSubnetId below). Data-plane writes are still gated by Azure RBAC via the
// callers' managed identities (disableLocalAuth left false only for break-glass; the
// logger/consumers in this template all use identityClientId: 'SystemAssigned', never keys).

@description('Region.')
param location string = 'southeastasia'

@description('Event Hub namespace name (globally unique).')
param namespaceName string

@description('Event hub (topic) name.')
param eventHubName string = 'llm-usage-events'

@description('Namespace SKU.')
param skuName string = 'Standard'

@description('Namespace throughput units.')
param capacity int = 1

@description('Message retention in days for the event hub.')
param messageRetentionInDays int = 3

@description('Partition count for the event hub.')
param partitionCount int = 2

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('APIM outbound-VNet-integration subnet resource ID. Kept for reference/tagging only — APIM Standard v2\'s logger-validation control-plane call is issued from Microsoft-managed infrastructure outside the customer VNet, so a VNet/service-endpoint rule on this namespace cannot allow-list it; the namespace is left at publicNetworkAccess=Enabled (no IP/VNet restriction) as the accepted trade-off, with RBAC-only data-plane access as the compensating control.')
param apimOutboundSubnetId string

@description('Resource ID of the privatelink.servicebus.windows.net zone in the hub RG.')
param serviceBusPrivateDnsZoneId string

param tags object = {}

resource namespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuName
    capacity: capacity
  }
  properties: {
    disableLocalAuth: false
    publicNetworkAccess: 'Enabled'
  }
}

resource namespaceNetworkRuleSet 'Microsoft.EventHub/namespaces/networkRuleSets@2024-01-01' = {
  parent: namespace
  name: 'default'
  properties: {
    defaultAction: 'Allow'
    publicNetworkAccess: 'Enabled'
    virtualNetworkRules: [
      {
        subnet: {
          id: apimOutboundSubnetId
        }
        ignoreMissingVnetServiceEndpoint: false
      }
    ]
    ipRules: []
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: namespace
  name: eventHubName
  properties: {
    messageRetentionInDays: messageRetentionInDays
    partitionCount: partitionCount
  }
}

module namespacePrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${namespaceName}'
  params: {
    location: location
    name: '${namespaceName}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: namespace.id
    groupIds: [
      'namespace'
    ]
    privateDnsZoneIds: [
      serviceBusPrivateDnsZoneId
    ]
    tags: tags
  }
}

output namespaceId string = namespace.id
output namespaceName string = namespace.name
output eventHubName string = eventHub.name
