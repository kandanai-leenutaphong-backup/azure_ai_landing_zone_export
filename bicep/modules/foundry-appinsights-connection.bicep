// Connects the AI Foundry hub account + project to the existing AI Gateway Application
// Insights instance, so agent runs created/tested in Foundry Portal (Playground, Traces,
// Monitor tabs) get full OpenTelemetry tracing/monitoring — independent of and in addition
// to the AI Gateway's own APIM->App Insights logging (which only sees calls that go
// through the gateway). Portal-native "Try in playground" calls can never be routed
// through our custom APIM instance (Azure does not expose that), so this connection is the
// only way to get Foundry-side traces for those calls; it does NOT carry our
// department/user cost-attribution dimensions (Foundry has no concept of our Entra App
// Roles or APIM Products) - only gateway-routed calls get that.
//
// Mirrors the official pattern: one connection at the ACCOUNT level (isSharedToAll, used as
// the account-wide default) plus one at the PROJECT level (Foundry Portal's "Monitor
// settings" dialog reads/writes the project-level connection). Only one Application
// Insights can be connected per project at a time.

@description('Name of the parent Cognitive Services / AI Foundry account (hub).')
param accountName string

@description('Name of the Foundry project to connect (e.g. aiGatewayHubProject).')
param projectName string

@description('Name of the existing Application Insights component to connect (must be in this same resource group).')
param appInsightsName string

@description('Resource ID of the existing Application Insights component to connect.')
param appInsightsId string

@description('Connection string of the Application Insights component (used as the connection credential).')
@secure()
param appInsightsConnectionString string

@description('Create App Insights reader role assignments for the Foundry project identity.')
param deployReaderRoleAssignments bool = true

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: projectName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource accountConnection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  parent: account
  name: '${accountName}-appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
    }
  }
}

resource projectConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: last(split(appInsightsId, '/'))
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
    }
  }
}

// Log Analytics Reader + Privileged Monitoring Data Reader (the latter is required to read
// GenAI trace content, per Foundry's own connection sample) on the App Insights resource,
// so the project's managed identity (used by Foundry Portal's Traces/Monitor tabs) can
// actually read back the agent traces it just sent.
var appInsightsReaderRoleGuids = [
  '73c42c96-874c-492b-b04d-ab87d138a893' // Log Analytics Reader
  'dbc9c667-e97f-4491-aee6-90b9cf960190' // Privileged Monitoring Data Reader
]

resource appInsightsReaderRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleGuid in appInsightsReaderRoleGuids: if (deployReaderRoleAssignments) {
  name: guid(project.id, roleGuid, appInsightsId)
  scope: appInsights
  properties: {
    principalId: project.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleGuid)
    principalType: 'ServicePrincipal'
  }
}]
