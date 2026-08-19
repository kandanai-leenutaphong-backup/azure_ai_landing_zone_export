// Azure AI Search service, private-endpoint only.

@description('Region.')
param location string = 'southeastasia'

@description('Search service name (globally unique, lowercase).')
param name string

@description('Search SKU.')
param skuName string = 'basic'

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Resource ID of the privatelink.search.windows.net zone in the hub RG.')
param searchPrivateDnsZoneId string

param tags object = {}

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'disabled'
    networkRuleSet: {
      ipRules: []
    }
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
    disableLocalAuth: false
  }
}

module searchPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${name}'
  params: {
    location: location
    name: '${name}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: search.id
    groupIds: [
      'searchService'
    ]
    privateDnsZoneIds: [
      searchPrivateDnsZoneId
    ]
    tags: tags
  }
}

output searchId string = search.id
output searchName string = search.name
