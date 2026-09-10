// Logic Apps Standard (WS1 plan) — the only Logic Apps plan Foundry Agent Service
// officially supports connecting to (both for the Foundry Logic Apps connector and for
// exposing a workflow as an agent-callable tool). Hosts the scheduled usage-ingestion
// workflow for the AI Gateway chargeback pipeline.
//
// Uses key-based access to the backing storage account for the Azure Files content
// share (WEBSITE_CONTENTAZUREFILECONNECTIONSTRING). This is a deliberate simplification —
// Logic Apps Standard's content-share mount is most reliably configured with a storage
// account key today; revisit user-assigned-identity-based content storage before
// production if a fully keyless posture is required.

@description('Region.')
param location string = 'southeastasia'

@description('Logic App (Standard) site name.')
param name string = 'logic-hub-usage-sea'

@description('VNet-integration subnet resource ID (snet-logicapp, delegated to Microsoft.Web/serverFarms).')
param integrationSubnetId string

@description('Log Analytics workspace resource ID (Application Insights workspace-based mode).')
param logAnalyticsWorkspaceId string

@description('Name of the storage account backing the Logic App content share. Must already exist and allow shared key access.')
param storageAccountName string

@description('Log Analytics workspace GUID (properties.customerId, not the ARM resource ID) queried by the usage-rollup workflow via the Log Analytics Query API.')
param usageLogAnalyticsWorkspaceCustomerId string = ''

@description('Application Insights App ID (properties.AppId) that owns the llm-usage custom metrics queried by the usage-rollup workflow.')
param usageAppInsightsAppId string = ''

@description('Cosmos DB account document endpoint (e.g. https://cosmos-hub-sea<suffix>.documents.azure.com:443/) the usage-rollup workflow upserts daily rollups into via AAD/managed-identity auth.')
param usageCosmosAccountEndpoint string = ''

@description('Cosmos DB SQL database name for the usage-rollup workflow.')
param usageCosmosDatabaseName string = 'usage'

@description('Cosmos DB SQL container name for the usage-rollup workflow.')
param usageCosmosContainerName string = 'token-usage-daily'

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

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'ASP-${name}'
  location: location
  tags: tags
  sku: {
    name: 'WS1'
    tier: 'WorkflowStandard'
  }
  kind: 'elastic'
  properties: {
    maximumElasticWorkerCount: 5
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource site 'Microsoft.Web/sites@2024-04-01' = {
  name: name
  location: location
  tags: tags
  kind: 'functionapp,workflowapp'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: integrationSubnetId
    vnetRouteAllEnabled: true
    siteConfig: {
      minTlsVersion: '1.2'
      alwaysOn: true
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        }
        {
          name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        }
        {
          name: 'WEBSITE_CONTENTSHARE'
          value: toLower(name)
        }
        {
          name: 'WEBSITE_CONTENTOVERVNET'
          value: '1'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'node'
        }
        {
          name: 'WEBSITE_NODE_DEFAULT_VERSION'
          value: '~18'
        }
        {
          name: 'APP_KIND'
          value: 'workflowApp'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'USAGE_LOG_ANALYTICS_WORKSPACE_ID'
          value: usageLogAnalyticsWorkspaceCustomerId
        }
        {
          name: 'USAGE_APPINSIGHTS_APP_ID'
          value: usageAppInsightsAppId
        }
        {
          name: 'USAGE_COSMOS_ACCOUNT_ENDPOINT'
          value: usageCosmosAccountEndpoint
        }
        {
          name: 'USAGE_COSMOS_DATABASE_NAME'
          value: usageCosmosDatabaseName
        }
        {
          name: 'USAGE_COSMOS_CONTAINER_NAME'
          value: usageCosmosContainerName
        }
      ]
    }
  }
}

output siteId string = site.id
output siteName string = site.name
output principalId string = site.identity.principalId
