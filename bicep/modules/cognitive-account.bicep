// Generic Cognitive Services account module. Used both for the standalone Computer
// Vision account (kind: ComputerVision) and the AI Foundry accounts (kind: AIServices).
// Private-endpoint only.

@description('Region.')
param location string = 'southeastasia'

@description('Account name (also used as the custom subdomain).')
param name string

@description('Cognitive Services kind, e.g. ComputerVision or AIServices.')
param kind string = 'AIServices'

@description('SKU name.')
param skuName string = 'S0'

@description('Whether this account should allow project creation (AI Foundry accounts).')
param allowProjectManagement bool = false

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Resource IDs of the private DNS zones this account needs (cognitiveservices, plus openai + services.ai for AIServices kind).')
param privateDnsZoneIds array

param tags object = {}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: kind
  sku: {
    name: skuName
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: false
    allowProjectManagement: allowProjectManagement
    networkAcls: {
      defaultAction: 'Deny'
    }
  }
}

module accountPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${name}'
  params: {
    location: location
    name: '${name}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: account.id
    groupIds: [
      'account'
    ]
    privateDnsZoneIds: privateDnsZoneIds
    tags: tags
  }
}

output accountId string = account.id
output accountName string = account.name
output principalId string = account.identity.principalId
