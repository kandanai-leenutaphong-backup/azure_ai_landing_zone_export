// Grounding with Bing account. Global resource, no private endpoint (Bing grounding is
// consumed by the Foundry agent over the Foundry account's outbound connection, not
// reached directly via VNet).

@description('Name of the Bing grounding account.')
param name string

@description('SKU name.')
param skuName string = 'G1'

param tags object = {}

#disable-next-line BCP081
resource bingAccount 'Microsoft.Bing/accounts@2025-05-01-preview' = {
  name: name
  location: 'global'
  tags: tags
  kind: 'Bing.Grounding'
  sku: {
    name: skuName
  }
}

output bingAccountId string = bingAccount.id
output bingAccountName string = bingAccount.name
