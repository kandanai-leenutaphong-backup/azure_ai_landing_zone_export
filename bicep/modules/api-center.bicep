@description('Azure region supported by API Center. API Center is a control-plane registry and can use a different region from the workloads it inventories.')
param location string = 'centralindia'

@description('Globally unique API Center service name.')
param name string

@description('API Management service name to synchronize into API Center.')
param apimName string

param tags object = {}

resource apiCenter 'Microsoft.ApiCenter/services@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  #disable-next-line BCP187
  sku: {
    name: 'Free'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource defaultWorkspace 'Microsoft.ApiCenter/services/workspaces@2024-06-01-preview' = {
  parent: apiCenter
  name: 'default'
  properties: {
    title: 'AI Gateway API Registry'
    description: 'Central inventory for REST APIs and MCP servers governed by the AI Gateway.'
  }
}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource apiCenterApimReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(apim.id, apiCenter.id, 'ApiManagementServiceReader')
  scope: apim
  properties: {
    principalId: apiCenter.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '71522526-b88f-4d52-b57f-d31fc3546d0d')
  }
}

output apiCenterId string = apiCenter.id
output apiCenterName string = apiCenter.name
output principalId string = apiCenter.identity.principalId
output workspaceId string = defaultWorkspace.id
