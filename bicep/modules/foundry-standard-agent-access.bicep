param projectPrincipalId string
param storageName string
param cosmosName string
param searchName string

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageName
}
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' existing = {
  name: cosmosName
}
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchName
}

var storageRoleIds = [
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  '17d1049b-9a84-46fb-8f53-869881c3d3ab'
]
var cosmosOperatorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '230815da-be43-4aae-9cb4-875f7bd000aa')
var searchRoleIds = [
  '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
]

resource storageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in storageRoleIds: {
  scope: storage
  name: guid(storage.id, projectPrincipalId, roleId)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
  }
}]
resource cosmosOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: cosmos
  name: guid(cosmos.id, projectPrincipalId, cosmosOperatorRoleId)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cosmosOperatorRoleId
  }
}
resource searchRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in searchRoleIds: {
  scope: search
  name: guid(search.id, projectPrincipalId, roleId)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
  }
}]
