// Workspace-based Application Insights component, following the same pattern already
// used inline in function-app.bicep. Extracted as a standalone module so the AI Gateway
// resources (APIM, Logic App Standard) can share one component or each get their own.

@description('Region.')
param location string = 'southeastasia'

@description('Application Insights component name.')
param name string

@description('Log Analytics workspace resource ID (workspace-based mode).')
param logAnalyticsWorkspaceId string

param tags object = {}

resource appInsights 'microsoft.insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
  }
}

output id string = appInsights.id
output name string = appInsights.name
output appId string = appInsights.properties.AppId
output instrumentationKey string = appInsights.properties.InstrumentationKey
output connectionString string = appInsights.properties.ConnectionString
