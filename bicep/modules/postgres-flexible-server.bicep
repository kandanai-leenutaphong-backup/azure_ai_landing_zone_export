@description('Region.')
param location string = 'southeastasia'

@description('Globally unique PostgreSQL Flexible Server name.')
param serverName string

@description('PostgreSQL database name.')
param databaseName string = 'thai-search-pg-db'

@description('PostgreSQL major version.')
param postgresVersion string = '16'

@description('Compute SKU. Standard_B1ms (Burstable, 1 vCore / 2 GiB) is the cheapest generally-available Flexible Server SKU.')
param skuName string = 'Standard_B1ms'

@description('Storage size in GiB. 32 GiB is the smallest size Flexible Server offers.')
param storageSizeGB int = 32

@description('Microsoft Entra administrator principal name (UPN).')
param entraAdminLogin string

@description('Microsoft Entra administrator object ID.')
param entraAdminObjectId string

@description('Microsoft Entra tenant ID.')
param entraTenantId string

@description('Private endpoint subnet resource ID.')
param privateEndpointSubnetId string

@description('Private DNS zone resource ID for privatelink.postgres.database.azure.com.')
param postgresPrivateDnsZoneId string

param tags object = {}

// Entra-only admin: no password is ever created, generated, or stored for this server.
resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Burstable'
  }
  properties: {
    version: postgresVersion
    storage: {
      storageSizeGB: storageSizeGB
      autoGrow: 'Disabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    // Private Link access only; no delegated-subnet VNet injection and no public endpoint.
    network: {
      publicNetworkAccess: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: entraTenantId
    }
    availabilityZone: ''
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource entraAdmin 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2024-08-01' = {
  parent: server
  name: entraAdminObjectId
  properties: {
    principalType: 'User'
    principalName: entraAdminLogin
    tenantId: entraTenantId
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    entraAdmin
  ]
}

module privateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${serverName}'
  params: {
    location: location
    name: '${serverName}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: server.id
    groupIds: [
      'postgresqlServer'
    ]
    privateDnsZoneIds: [
      postgresPrivateDnsZoneId
    ]
    tags: tags
  }
}

output serverId string = server.id
output serverName string = server.name
output serverFqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
