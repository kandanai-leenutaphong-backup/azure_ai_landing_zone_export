// Connects the SEA Container App and the West US 3 Hosted Agent to the existing private
// Application Insights component. Entra-only export: each workload needs Monitoring Metrics
// Publisher on the component. The connection string is read here, never by the operator.
targetScope = 'resourceGroup'

param appInsightsName string
param appPrincipalId string
param hostedPrincipalId string
param agentVnetId string
param foundrySubscriptionId string
param foundryResourceGroup string
param foundryAccount string
param foundryProject string

var metricsPublisher = '3913510d-42f4-4e42-8a64-420c390055eb'
// Zones already serving AMPLS `ampls-tracing-xlpu` for vnet-spoke-app-sea.
var monitorZones = [
  'privatelink.monitor.azure.com'
  'privatelink.oms.opinsights.azure.com'
  'privatelink.ods.opinsights.azure.com'
  'privatelink.agentsvc.azure-automation.net'
]

resource appi 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource publishers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principal in [appPrincipalId, hostedPrincipalId]: {
  scope: appi
  name: guid(appi.id, principal, metricsPublisher)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', metricsPublisher)
    principalId: principal
    principalType: 'ServicePrincipal'
    description: 'customer-service-multi-agent: Entra trace export'
  }
}]

resource zones 'Microsoft.Network/privateDnsZones@2020-06-01' existing = [for zone in monitorZones: {
  name: zone
}]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zone, i) in monitorZones: {
  parent: zones[i]
  name: 'link-vnet-spoke-agent-wus3'
  location: 'global'
  tags: { project: 'customer-service-multi-agent', capability: 'observability-tracing' }
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: agentVnetId }
  }
}]

module foundryConnection 'observability-foundry.bicep' = {
  name: 'customer-service-appinsights-connection'
  scope: resourceGroup(foundrySubscriptionId, foundryResourceGroup)
  params: {
    foundryAccount: foundryAccount
    foundryProject: foundryProject
    appInsightsId: appi.id
    connectionString: appi.properties.ConnectionString
  }
  dependsOn: [links]
}
