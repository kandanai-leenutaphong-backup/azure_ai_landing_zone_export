param accountName string
param projectName string
param principalId string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}

resource invoker 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, principalId, '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    // Project-scoped Foundry User supports the app's Conversations/Responses calls.
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}
