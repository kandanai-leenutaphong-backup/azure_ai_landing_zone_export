targetScope = 'resourceGroup'

@description('Existing private Foundry account containing the Standard deployment.')
param accountName string
param standardDeploymentName string = 'gpt-4.1-mini'
param globalDeploymentName string = 'gpt-4.1-mini-global'
@description('Match the existing Standard deployment capacity; verify both live quotas before deploying.')
@minValue(1)
param capacity int = 10

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource standard 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' existing = {
  parent: account
  name: standardDeploymentName
}

resource globalStandard 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: globalDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: standard.properties.model.format
      name: standard.properties.model.name
      version: standard.properties.model.version
    }
    raiPolicyName: standard.properties.raiPolicyName
    versionUpgradeOption: standard.properties.versionUpgradeOption
  }
}

output standardDeployment string = standard.name
output globalDeployment string = globalStandard.name
output modelVersion string = standard.properties.model.version!
output standardCapacity int = standard.sku.capacity!
output globalCapacity int = globalStandard.sku.capacity!
