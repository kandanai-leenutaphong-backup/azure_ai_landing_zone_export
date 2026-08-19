// Log Analytics workspace.

@description('Region.')
param location string = 'southeastasia'

@description('Workspace name.')
param name string

param retentionInDays int = 30
param skuName string = 'PerGB2018'
param tags object = {}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: skuName
    }
    retentionInDays: retentionInDays
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output workspaceCustomerId string = workspace.properties.customerId
