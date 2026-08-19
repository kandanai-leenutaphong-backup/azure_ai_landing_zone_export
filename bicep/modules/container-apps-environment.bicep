// Container Apps managed environment, VNet-integrated into snet-containerapps.

@description('Region.')
param location string = 'southeastasia'

@description('Managed environment name.')
param name string

@description('Subnet resource ID (snet-containerapps, delegated to Microsoft.App/environments).')
param infrastructureSubnetId string

@description('Name of the Log Analytics workspace in the current resource group.')
param logAnalyticsWorkspaceName string

param tags object = {}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      internal: true
    }
  }
}

output environmentId string = environment.id
output environmentName string = environment.name
output defaultDomain string = environment.properties.defaultDomain
output staticIp string = environment.properties.staticIp
