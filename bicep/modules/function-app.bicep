// Cost-optimized Function App stack: UAMI, Flex Consumption plan, Application
// Insights, optional Durable Task Scheduler, and VNet-integrated Function App.

@description('Region.')
param location string = 'southeastasia'

@description('Base name used to derive resource names.')
param baseName string = 'funcapptestvnet'

@description('Subnet resource ID (snet-functionapp, delegated to Microsoft.App/environments for Flex Consumption).')
param integrationSubnetId string

@description('Log Analytics workspace resource ID (for Application Insights workspace-based mode).')
param logAnalyticsWorkspaceId string

@description('Storage account name backing the Function App (must already exist / be deployed, private-endpoint only).')
param functionStorageAccountName string

@description('Blob container used as the Flex Consumption deployment package source.')
param deploymentStorageContainerName string

@description('Maximum Flex Consumption scale-out instance count.')
@minValue(40)
@maxValue(1000)
param maximumInstanceCount int = 40

@description('Memory allocated to each Flex Consumption instance.')
@allowed([
  512
  2048
  4096
])
param instanceMemoryMB int = 512

@description('Deploy the dedicated Durable Task Scheduler. Disabled by default to avoid fixed cost.')
param deployDurableTaskScheduler bool = false

param tags object = {}

var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${baseName}-uami'
  location: location
  tags: tags
}

resource appInsights 'microsoft.insights/components@2020-02-02' = {
  name: baseName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
  }
}

resource durableTaskScheduler 'Microsoft.DurableTask/schedulers@2024-10-01-preview' = if (deployDurableTaskScheduler) {
  name: 'durableTaskScheduler-${baseName}'
  location: location
  tags: tags
  properties: {
    ipAllowlist: [
      '0.0.0.0/0'
    ]
    sku: {
      name: 'Dedicated'
      capacity: 1
    }
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'ASP-${baseName}'
  location: location
  tags: tags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource functionStorage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: functionStorageAccountName
}

resource storageBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionStorage.id, uami.id, storageBlobDataContributorRoleId)
  scope: functionStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageQueueDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionStorage.id, uami.id, storageQueueDataContributorRoleId)
  scope: functionStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageTableDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionStorage.id, uami.id, storageTableDataContributorRoleId)
  scope: functionStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource site 'Microsoft.Web/sites@2024-04-01' = {
  name: baseName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: integrationSubnetId
    vnetRouteAllEnabled: true
    siteConfig: {
      minTlsVersion: '1.2'
      alwaysOn: false
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${functionStorage.properties.primaryEndpoints.blob}${deploymentStorageContainerName}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: uami.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: instanceMemoryMB
      }
      runtime: {
        name: 'dotnet-isolated'
        version: '8.0'
      }
    }
  }
  dependsOn: [
    storageBlobDataContributor
    storageQueueDataContributor
    storageTableDataContributor
  ]
}

resource appSettings 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: site
  name: 'appsettings'
  properties: {
    AzureWebJobsStorage__accountName: functionStorage.name
    AzureWebJobsStorage__credential: 'managedidentity'
    AzureWebJobsStorage__clientId: uami.properties.clientId
    AzureWebJobsStorage__blobServiceUri: functionStorage.properties.primaryEndpoints.blob
    AzureWebJobsStorage__queueServiceUri: functionStorage.properties.primaryEndpoints.queue
    AzureWebJobsStorage__tableServiceUri: functionStorage.properties.primaryEndpoints.table
    APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
  }
}

output siteId string = site.id
output siteName string = site.name
output uamiPrincipalId string = uami.properties.principalId
