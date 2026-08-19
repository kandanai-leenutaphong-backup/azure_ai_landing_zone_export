// Generic Key Vault module, RBAC-authorized, private-endpoint only.

@description('Region.')
param location string = 'southeastasia'

@description('Key Vault name (globally unique, 3-24 chars).')
param name string

@description('Microsoft Entra tenant ID.')
param tenantId string = tenant().tenantId

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Resource ID of the privatelink.vaultcore.azure.net zone in the hub RG.')
param vaultPrivateDnsZoneId string

param tags object = {}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

module vaultPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${name}'
  params: {
    location: location
    name: '${name}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: vault.id
    groupIds: [
      'vault'
    ]
    privateDnsZoneIds: [
      vaultPrivateDnsZoneId
    ]
    tags: tags
  }
}

output vaultId string = vault.id
output vaultName string = vault.name
output vaultUri string = vault.properties.vaultUri
