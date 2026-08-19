// Cosmos DB data-plane RBAC role assignment (Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments).
// This is separate from generic ARM control-plane RBAC (Microsoft.Authorization/roleAssignments) —
// Cosmos DB SQL API data access requires its own built-in role definitions and assignment resource type.

@description('Name of the Cosmos DB account.')
param accountName string

@description('Principal (object) ID of the identity to grant data-plane access to.')
param principalId string

@description('Cosmos DB built-in data role definition ID. Defaults to the built-in "Cosmos DB Built-in Data Contributor" role (00000000-0000-0000-0000-000000000002).')
param roleDefinitionId string = '00000000-0000-0000-0000-000000000002'

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' existing = {
  name: accountName
}

resource roleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = {
  parent: account
  name: guid(account.id, principalId, roleDefinitionId)
  properties: {
    principalId: principalId
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${roleDefinitionId}'
    scope: account.id
  }
}
