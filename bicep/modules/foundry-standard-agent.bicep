// Capability-host and connection wiring follows the official private standard-agent sample.
param location string
param accountName string
param projectName string
param agentSubnetId string
param privateEndpointSubnetId string
param privateDnsZoneIds string[]
param storageName string
param cosmosName string
param searchName string
param developerPrincipalId string
param tags object = {}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageName
}
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' existing = {
  name: cosmosName
}
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchName
}

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
    }
    networkInjections: [
      {
        scenario: 'agent'
        subnetArmId: agentSubnetId
        useMicrosoftManagedNetwork: false
      }
    ]
  }
}

module accountPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${accountName}'
  params: {
    location: location
    name: '${accountName}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: account.id
    groupIds: [
      'account'
    ]
    privateDnsZoneIds: privateDnsZoneIds
    tags: tags
  }
  // The official sample also completes model provisioning before creating the account PE.
  dependsOn: [
    model
  ]
}

module model 'cognitive-deployment.bicep' = {
  name: 'agent-model'
  params: {
    accountName: account.name
    deploymentName: 'gpt-4.1-mini'
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
    skuName: 'Standard'
    capacity: 10
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: '${location} standard agents'
    description: 'Private standard-agent setup with customer-owned Search, Blob and Cosmos DB.'
  }
}

resource storageConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: storageName
  properties: {
    category: 'AzureStorageAccount'
    target: storage.properties.primaryEndpoints.blob
    authType: 'AAD'
    metadata: {
      ApiType: 'Azure'
      ResourceId: storage.id
      location: location
    }
  }
}
resource cosmosConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: cosmosName
  properties: {
    category: 'CosmosDB'
    target: cosmos.properties.documentEndpoint
    authType: 'AAD'
    metadata: {
      ApiType: 'Azure'
      ResourceId: cosmos.id
      location: location
    }
  }
}
resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: searchName
  properties: {
    category: 'CognitiveSearch'
    target: 'https://${searchName}.search.windows.net'
    authType: 'AAD'
    metadata: {
      ApiType: 'Azure'
      ResourceId: search.id
      location: location
    }
  }
}

module provisioningAccess 'foundry-standard-agent-access.bicep' = {
  name: 'agent-provisioning-access'
  params: {
    projectPrincipalId: project.identity.principalId
    storageName: storageName
    cosmosName: cosmosName
    searchName: searchName
  }
}

// networkInjections automatically creates the account-level capability host.
resource capabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  parent: project
  name: 'caphostproj'
  properties: {
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
    storageConnections: [
      storageConnection.name
    ]
    threadStorageConnections: [
      cosmosConnection.name
    ]
    vectorStoreConnections: [
      searchConnection.name
    ]
  }
  dependsOn: [
    accountPrivateEndpoint
    model
    provisioningAccess
  ]
}

module runtimeAccess 'foundry-standard-agent-runtime-access.bicep' = {
  name: 'agent-runtime-access'
  params: {
    projectPrincipalId: project.identity.principalId
    #disable-next-line BCP053
    workspaceId: project.properties.internalId
    storageName: storageName
    cosmosName: cosmosName
  }
  dependsOn: [
    capabilityHost
  ]
}

resource developerFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: project
  name: guid(project.id, developerPrincipalId, '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  properties: {
    principalId: developerPrincipalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

output accountName string = account.name
output projectName string = project.name
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
