// Generic storage account module, private-endpoint only (public network access disabled).

@description('Region.')
param location string = 'southeastasia'

@description('Storage account name (must be globally unique, lowercase, <=24 chars).')
param name string

@description('Storage account SKU.')
param skuName string = 'Standard_LRS'

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Resource ID of the privatelink.blob.core.windows.net zone in the hub RG.')
param blobPrivateDnsZoneId string

@description('Create a Queue private endpoint. Required for private Azure Functions host storage.')
param enableQueuePrivateEndpoint bool = false

@description('Resource ID of the privatelink.queue.core.windows.net zone in the hub RG.')
param queuePrivateDnsZoneId string = ''

@description('Create a Table private endpoint. Required for private Azure Functions host storage.')
param enableTablePrivateEndpoint bool = false

@description('Resource ID of the privatelink.table.core.windows.net zone in the hub RG.')
param tablePrivateDnsZoneId string = ''

@description('Create a File private endpoint. Required for private Logic Apps Standard content storage.')
param enableFilePrivateEndpoint bool = false

@description('Resource ID of the privatelink.file.core.windows.net zone in the hub RG.')
param filePrivateDnsZoneId string = ''

@description('Blob containers to create in this storage account.')
param blobContainerNames array = []

@description('Allow storage account key authentication.')
param allowSharedKeyAccess bool = true

param tags object = {}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: allowSharedKeyAccess
    defaultToOAuthAuthentication: !allowSharedKeyAccess
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = [for containerName in blobContainerNames: {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}]

module blobPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${name}-blob'
  params: {
    location: location
    name: '${name}-blob-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: storage.id
    groupIds: [
      'blob'
    ]
    privateDnsZoneIds: [
      blobPrivateDnsZoneId
    ]
    tags: tags
  }
}

module queuePrivateEndpoint 'private-endpoint.bicep' = if (enableQueuePrivateEndpoint) {
  name: 'pe-${name}-queue'
  params: {
    location: location
    name: '${name}-queue-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: storage.id
    groupIds: [
      'queue'
    ]
    privateDnsZoneIds: [
      queuePrivateDnsZoneId
    ]
    tags: tags
  }
}

module tablePrivateEndpoint 'private-endpoint.bicep' = if (enableTablePrivateEndpoint) {
  name: 'pe-${name}-table'
  params: {
    location: location
    name: '${name}-table-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: storage.id
    groupIds: [
      'table'
    ]
    privateDnsZoneIds: [
      tablePrivateDnsZoneId
    ]
    tags: tags
  }
}

module filePrivateEndpoint 'private-endpoint.bicep' = if (enableFilePrivateEndpoint) {
  name: 'pe-${name}-file'
  params: {
    location: location
    name: '${name}-file-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: storage.id
    groupIds: [
      'file'
    ]
    privateDnsZoneIds: [
      filePrivateDnsZoneId
    ]
    tags: tags
  }
}

output storageId string = storage.id
output storageName string = storage.name
output primaryBlobEndpoint string = storage.properties.primaryEndpoints.blob
