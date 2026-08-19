// Azure Container Registry.

@description('Region.')
param location string = 'southeastasia'

@description('ACR name (globally unique, alphanumeric only).')
param name string

@description('SKU name.')
param skuName string = 'Standard'

param tags object = {}

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    adminUserEnabled: false
  }
}

output acrId string = acr.id
output acrLoginServer string = acr.properties.loginServer
