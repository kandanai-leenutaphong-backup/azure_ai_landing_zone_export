@description('Region.')
param location string = 'southeastasia'

@description('Globally unique Azure SQL logical server name.')
param serverName string

@description('Azure SQL database name.')
param databaseName string = 'thai-search-db'

@description('Microsoft Entra administrator login name.')
param entraAdminLogin string

@description('Microsoft Entra administrator object ID.')
param entraAdminObjectId string

@description('Microsoft Entra tenant ID.')
param entraTenantId string

@description('Private endpoint subnet resource ID.')
param privateEndpointSubnetId string

@description('Private DNS zone resource ID for privatelink.database.windows.net.')
param sqlPrivateDnsZoneId string

@description('Deploy a Basic elastic pool on this server to showcase shared-eDTU pooling, with a second small database inside it.')
param deployElasticPool bool = true

@description('Elastic pool name. Basic tier, 50 eDTU is the lowest available Basic-pool capacity.')
param elasticPoolName string = 'thai-search-pool-sea'

@description('Elastic pool eDTU capacity. 50 is the minimum for the Basic pool tier.')
param elasticPoolCapacity int = 50

@description('Name of the second, pool-hosted database used to demonstrate elastic DTU sharing.')
param poolDatabaseName string = 'thai-search-pool-demo-db'

param tags object = {}

resource server 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: entraAdminLogin
      sid: entraAdminObjectId
      tenantId: entraTenantId
      azureADOnlyAuthentication: true
    }
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    restrictOutboundNetworkAccess: 'Disabled'
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: server
  name: databaseName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    collation: 'Thai_100_CI_AS'
    maxSizeBytes: 2147483648
    requestedBackupStorageRedundancy: 'Local'
  }
}

module privateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${serverName}'
  params: {
    location: location
    name: '${serverName}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: server.id
    groupIds: [
      'sqlServer'
    ]
    privateDnsZoneIds: [
      sqlPrivateDnsZoneId
    ]
    tags: tags
  }
}

// Basic elastic pool: demonstrates eDTU pooling across multiple small databases that
// share one fixed capacity rather than each paying for a dedicated Basic tier. 50 eDTU
// is the lowest Basic-pool capacity Azure offers (the Standard/Premium pool floors cost
// more), making this the cheapest way to showcase the capability.
resource elasticPool 'Microsoft.Sql/servers/elasticPools@2023-08-01-preview' = if (deployElasticPool) {
  parent: server
  name: elasticPoolName
  location: location
  tags: tags
  sku: {
    name: 'BasicPool'
    tier: 'Basic'
    capacity: elasticPoolCapacity
  }
  properties: {
    perDatabaseSettings: {
      minCapacity: 0
      maxCapacity: 5
    }
  }
}

// Second database sharing the pool's eDTUs with the primary database above, instead of
// provisioning its own dedicated tier. Used to seed showcase/mock data demonstrating the
// pool and to exercise the app's upload-to-SQL path without touching the primary dataset.
resource poolDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = if (deployElasticPool) {
  parent: server
  name: poolDatabaseName
  location: location
  tags: tags
  sku: {
    name: 'ElasticPool'
    tier: 'Basic'
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    elasticPoolId: elasticPool.id
    requestedBackupStorageRedundancy: 'Local'
  }
}

output serverId string = server.id
output serverName string = server.name
output serverFqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output elasticPoolName string = deployElasticPool ? elasticPool.name : ''
output poolDatabaseName string = deployElasticPool ? poolDatabase.name : ''
