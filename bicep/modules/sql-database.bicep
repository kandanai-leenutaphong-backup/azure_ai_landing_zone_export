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

param tags object = {}

resource server 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  tags: tags
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

output serverId string = server.id
output serverName string = server.name
output serverFqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
