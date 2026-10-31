// Native Foundry project tracing connection; Hosted Agents receive
// APPLICATIONINSIGHTS_CONNECTION_STRING from it.
param foundryAccount string
param foundryProject string
param appInsightsId string
@secure()
param connectionString string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccount
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: foundryProject
}

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: 'appi-tracing-xlpu'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: false
    credentials: { key: connectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsightsId }
  }
}
