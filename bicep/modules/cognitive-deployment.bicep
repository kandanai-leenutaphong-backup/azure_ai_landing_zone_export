// Model deployment child resource for a Cognitive Services (AIServices/Foundry) account.
// Deployment name (label) can differ from the underlying base model name, matching the
// {model}-{team}-{env} labeling convention used for department chargeback attribution.

@description('Name of the parent Cognitive Services / AI Foundry account.')
param accountName string

@description('Deployment name (label), e.g. gpt-4o-odi-prod. Used as the {deployment} path segment callers hit through APIM.')
param deploymentName string

@description('Underlying base model name, e.g. gpt-4o. Can differ from deploymentName.')
param modelName string

@description('Model publisher/format, e.g. OpenAI.')
param modelFormat string = 'OpenAI'

@description('Model version.')
param modelVersion string

@description('Deployment SKU name, e.g. GlobalStandard.')
param skuName string = 'GlobalStandard'

@description('Deployment capacity in thousands of tokens per minute (TPM), matching the department quota allocated to this deployment.')
param capacity int

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: deploymentName
  sku: {
    name: skuName
    capacity: capacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
  }
}

output deploymentId string = deployment.id
output deploymentName string = deployment.name
