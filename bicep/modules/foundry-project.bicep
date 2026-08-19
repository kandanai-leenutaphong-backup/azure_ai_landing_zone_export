// AI Foundry project, a child resource of a Cognitive Services (AIServices) account.

@description('Name of the parent Cognitive Services / AI Foundry account.')
param accountName string

@description('Name of the project.')
param projectName string

@description('Region (must match parent account).')
param location string = 'southeastasia'

param tags object = {}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
  }
}

output projectId string = project.id
output projectName string = project.name
