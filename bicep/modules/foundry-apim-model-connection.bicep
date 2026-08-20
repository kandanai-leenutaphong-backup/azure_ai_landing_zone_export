// Registers hub-hosted model deployments exposed through APIM as admin-connected
// models in a spoke Foundry project. Model capacity remains centralized in the hub.

@description('Name of the spoke Foundry account.')
param accountName string

@description('Name shown for this gateway connection in Foundry.')
param connectionName string = 'hub-ai-gateway'

@description('APIM API base URL, without a deployment-specific suffix.')
param gatewayBaseUrl string

@description('Hub deployment name exposed through APIM.')
param deploymentName string

@description('Underlying model name.')
param modelName string

@description('Underlying model version.')
param modelVersion string

@description('Azure OpenAI inference API version appended by Foundry.')
param inferenceApiVersion string = '2024-10-21'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

var connectionMetadata = {
  deploymentInPath: 'true'
  inferenceAPIVersion: inferenceApiVersion
  models: string([
    {
      name: deploymentName
      properties: {
        model: {
          name: modelName
          version: modelVersion
          format: 'OpenAI'
        }
      }
    }
  ])
}

// Foundry model connections are resource-scoped. This appears under
// Manage > Resource details > Admin-connected models and is available to every
// project in the resource.
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  parent: account
  name: connectionName
  properties: {
    category: 'ApiManagement'
    target: gatewayBaseUrl
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    audience: 'https://cognitiveservices.azure.com'
    isSharedToAll: true
    credentials: {}
    metadata: connectionMetadata
  }
}

output connectionId string = connection.id
output connectionName string = connection.name
output modelReference string = '${connection.name}/${deploymentName}'
