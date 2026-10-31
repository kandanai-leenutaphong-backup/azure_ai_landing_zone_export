param projectPrincipalId string
param workspaceId string
param storageName string
param cosmosName string

var workspaceGuid = '${substring(workspaceId, 0, 8)}-${substring(workspaceId, 8, 4)}-${substring(workspaceId, 12, 4)}-${substring(workspaceId, 16, 4)}-${substring(workspaceId, 20, 12)}'
var blobOwnerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b')

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageName
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' existing = {
  parent: storage
  name: 'default'
}
resource agentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' existing = {
  parent: blobService
  name: '${workspaceGuid}-azureml-agent'
}
resource agentBlobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: agentContainer
  name: guid(agentContainer.id, projectPrincipalId, blobOwnerRoleId)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: blobOwnerRoleId
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' existing = {
  name: cosmosName
}
resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = {
  parent: cosmos
  name: guid(cosmos.id, projectPrincipalId, 'enterprise_memory')
  properties: {
    principalId: projectPrincipalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: '${cosmos.id}/dbs/enterprise_memory'
  }
}
