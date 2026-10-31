// Generic Cosmos DB (SQL API) account module, private-endpoint only.

@description('Region.')
param location string = 'southeastasia'

@description('Cosmos DB account name (globally unique, lowercase).')
param name string

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Resource ID of the privatelink.documents.azure.com zone in the hub RG.')
param documentsPrivateDnsZoneId string

@description('Enable Serverless capacity mode (no throughput auto-provisioning; billed per-request). Recommended for low, spiky workloads like a usage/chargeback rollup store.')
param enableServerless bool = false

@description('Disable account-key authentication and use Microsoft Entra data-plane roles.')
param disableLocalAuth bool = false

@description('Enable automatic failover.')
param enableAutomaticFailover bool = false

param tags object = {}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: disableLocalAuth
    enableAutomaticFailover: enableAutomaticFailover
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: enableServerless ? [
      {
        name: 'EnableServerless'
      }
    ] : []
    publicNetworkAccess: 'Disabled'
    isVirtualNetworkFilterEnabled: false
    networkAclBypass: 'None'
  }
}

module cosmosPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${name}'
  params: {
    location: location
    name: '${name}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: cosmos.id
    groupIds: [
      'Sql'
    ]
    privateDnsZoneIds: [
      documentsPrivateDnsZoneId
    ]
    tags: tags
  }
}

output cosmosId string = cosmos.id
output cosmosName string = cosmos.name
