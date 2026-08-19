// Single spoke network: combines the former rg-vm-vnet-test (vnet-1/vnet-2) and
// rg-foundry-standard-private-westus3 (agent-vnet-test) into a single VNet / single
// resource group, per the "merge spokes" requirement.
// Deployed at resource-group scope (the single spoke resource group).

@description('Region for all spoke resources.')
param location string = 'southeastasia'

@description('Name of the single spoke virtual network.')
param vnetName string = 'vnet-spoke-app-sea'

@description('Address space of the single spoke VNet.')
param vnetAddressPrefix string = '10.10.0.0/16'

@description('Deploy Azure Bastion and its public IP. Disabled by default to reduce fixed monthly cost.')
param enableBastion bool = false

param bastionSubnetPrefix string = '10.10.0.0/26'
param vmSubnetPrefix string = '10.10.1.0/24'
param containerAppsSubnetPrefix string = '10.10.2.0/23'
param functionAppSubnetPrefix string = '10.10.4.0/24'
param agentSubnetPrefix string = '10.10.5.0/24'
param privateEndpointsSubnetPrefix string = '10.10.6.0/24'
param applicationGatewaySubnetPrefix string = '10.10.7.0/24'

@description('Tags applied to all resources.')
param tags object = {}

resource vmNsg1 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-1'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource vmNsg2 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-2'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource containerAppsNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-containerapps-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource functionAppNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-functionapp-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource agentSubnetNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-agent-subnet-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource peSubnetNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-pe-subnet-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource applicationGatewayNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-appgw-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowInternetHttp'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
      {
        name: 'AllowGatewayManager'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'GatewayManager'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '65200-65535'
        }
      }
      {
        name: 'AllowAzureLoadBalancer'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'AzureLoadBalancer'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// Azure Bastion requires specific inbound/outbound rules on AzureBastionSubnet's NSG.
resource bastionNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-AzureBastionSubnet-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHttpsInbound'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowGatewayManagerInbound'
        properties: {
          priority: 130
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'GatewayManager'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowAzureLoadBalancerInbound'
        properties: {
          priority: 140
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'AzureLoadBalancer'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowBastionHostCommunicationInbound'
        properties: {
          priority: 150
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRanges: [
            '8080'
            '5701'
          ]
        }
      }
      {
        name: 'AllowSshRdpOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRanges: [
            '22'
            '3389'
          ]
        }
      }
      {
        name: 'AllowAzureCloudOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureCloud'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowBastionHostCommunicationOutbound'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRanges: [
            '8080'
            '5701'
          ]
        }
      }
      {
        name: 'AllowGetSessionInformationOutbound'
        properties: {
          priority: 130
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '80'
        }
      }
    ]
  }
}

resource natGwPip 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: 'nat-gw-pip-spoke'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2023-11-01' = {
  name: 'nat-gw-spoke'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIpAddresses: [
      {
        id: natGwPip.id
      }
    ]
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
        name: 'AzureBastionSubnet'
        properties: {
          addressPrefix: bastionSubnetPrefix
          networkSecurityGroup: {
            id: bastionNsg.id
          }
        }
      }
      {
        name: 'snet-vm'
        properties: {
          addressPrefix: vmSubnetPrefix
        }
      }
      {
        name: 'snet-containerapps'
        properties: {
          addressPrefix: containerAppsSubnetPrefix
          networkSecurityGroup: {
            id: containerAppsNsg.id
          }
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-functionapp'
        properties: {
          addressPrefix: functionAppSubnetPrefix
          networkSecurityGroup: {
            id: functionAppNsg.id
          }
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-agent'
        properties: {
          addressPrefix: agentSubnetPrefix
          networkSecurityGroup: {
            id: agentSubnetNsg.id
          }
          natGateway: {
            id: natGateway.id
          }
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
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
            id: peSubnetNsg.id
          }
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-appgw'
        properties: {
          addressPrefix: applicationGatewaySubnetPrefix
          networkSecurityGroup: {
            id: applicationGatewayNsg.id
          }
        }
      }
    ]
  }
}

resource bastionPip 'Microsoft.Network/publicIPAddresses@2023-11-01' = if (enableBastion) {
  name: 'spoke-bastion-pip'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource bastion 'Microsoft.Network/bastionHosts@2023-11-01' = if (enableBastion) {
  name: 'spoke-bastion'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'bastionIpConfig'
        properties: {
          subnet: {
            id: '${vnet.id}/subnets/AzureBastionSubnet'
          }
          publicIPAddress: {
            id: bastionPip.id
          }
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output vmSubnetId string = '${vnet.id}/subnets/snet-vm'
output containerAppsSubnetId string = '${vnet.id}/subnets/snet-containerapps'
output functionAppSubnetId string = '${vnet.id}/subnets/snet-functionapp'
output agentSubnetId string = '${vnet.id}/subnets/snet-agent'
output privateEndpointsSubnetId string = '${vnet.id}/subnets/snet-pe'
output applicationGatewaySubnetId string = '${vnet.id}/subnets/snet-appgw'
output vmNsg1Id string = vmNsg1.id
output vmNsg2Id string = vmNsg2.id
