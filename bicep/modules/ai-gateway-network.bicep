// AI Gateway VNet: hosts APIM Standard V2 (outbound VNet integration) and the private
// endpoints for the hub Foundry account, Managed Redis, Cosmos DB, Event Hub, Key Vault,
// Storage, and the Logic Apps Standard plan. Deployed at resource-group scope (the AI
// Gateway resource group), peered to the existing hub the same way the spoke is peered.

@description('Region for all AI Gateway network resources.')
param location string = 'southeastasia'

@description('Name of the AI Gateway virtual network.')
param vnetName string = 'vnet-ai-gateway-sea'

@description('Address space of the AI Gateway VNet.')
param vnetAddressPrefix string = '10.20.0.0/16'

@description('APIM Standard V2 outbound VNet-integration subnet prefix. Must be delegated to Microsoft.Web/serverFarms, matching the regional VNet-integration model used by App Service / Standard v2 APIM.')
param apimOutboundSubnetPrefix string = '10.20.0.0/26'

@description('Private endpoints subnet prefix (Foundry, Redis, Cosmos DB, Event Hub, Key Vault, Storage).')
param privateEndpointsSubnetPrefix string = '10.20.1.0/24'

@description('Logic Apps Standard (WS1) VNet-integration subnet prefix. Must be delegated to Microsoft.Web/serverFarms and be distinct from the APIM outbound subnet.')
param logicAppSubnetPrefix string = '10.20.2.0/26'

param tags object = {}

resource apimOutboundNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-apim-outbound-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource peNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-pe-subnet-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource logicAppNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-logicapp-subnet-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: 'snet-apim-outbound'
        properties: {
          addressPrefix: apimOutboundSubnetPrefix
          networkSecurityGroup: {
            id: apimOutboundNsg.id
          }
          serviceEndpoints: [
            {
              service: 'Microsoft.EventHub'
            }
          ]
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
      {
        name: 'snet-pe'
        properties: {
          addressPrefix: privateEndpointsSubnetPrefix
          networkSecurityGroup: {
            id: peNsg.id
          }
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-logicapp'
        properties: {
          addressPrefix: logicAppSubnetPrefix
          networkSecurityGroup: {
            id: logicAppNsg.id
          }
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output apimOutboundSubnetId string = '${vnet.id}/subnets/snet-apim-outbound'
output privateEndpointsSubnetId string = '${vnet.id}/subnets/snet-pe'
output logicAppSubnetId string = '${vnet.id}/subnets/snet-logicapp'
