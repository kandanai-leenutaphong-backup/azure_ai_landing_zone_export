// Hub network: replica of existing rg-vnet-hub-2 (VNet, VPN Gateway, DNS Private Resolver).
// Deployed at resource-group scope (the hub resource group).

@description('Region for all hub resources.')
param location string = 'southeastasia'

@description('Name of the hub virtual network.')
param vnetName string = 'vnet-hub-2'

@description('Address space of the hub VNet.')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('Default subnet prefix (workload subnet in the hub).')
param defaultSubnetPrefix string = '10.0.0.0/24'

@description('GatewaySubnet prefix (must be named GatewaySubnet, min /27).')
param gatewaySubnetPrefix string = '10.0.1.0/27'

@description('DNS Resolver inbound endpoint subnet prefix (min /28, delegated to Microsoft.Network/dnsResolvers).')
param dnsResolverInboundSubnetPrefix string = '10.0.2.0/28'

@description('Static private IP assigned to the DNS Resolver inbound endpoint and advertised as the hub VNet DNS server.')
param dnsResolverInboundIp string = '10.0.2.4'

@description('VPN Gateway SKU.')
param vpnGatewaySku string = 'VpnGw1AZ'

@description('Name prefix used for the VPN gateway resources.')
param vpnGatewayName string = 'hub-VNetGw-sea-dev'

@description('Address pool assigned to Point-to-Site VPN clients. Must not overlap any connected network.')
param p2sClientAddressPool string = '172.16.0.0/24'

@description('Microsoft Entra tenant ID used to authenticate Point-to-Site VPN clients.')
param entraTenantId string = tenant().tenantId

@description('Application ID used by the Azure VPN Client for Microsoft Entra authentication.')
param azureVpnClientApplicationId string = '41b23e61-6c1e-4545-b367-cd054e0ed4b4'

@description('Name of the DNS Private Resolver.')
param dnsResolverName string = 'dns-resolver-hub'

@description('Tags applied to all resources.')
param tags object = {}

var entraLoginEndpoint = environment().authentication.loginEndpoint

resource defaultNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-default-nsg-sea'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource dnsResolverInboundNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${vnetName}-DnsResolverInboundSubnet-nsg-sea'
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
    dhcpOptions: {
      dnsServers: [
        dnsResolverInboundIp
      ]
    }
    subnets: [
      {
        name: 'default'
        properties: {
          addressPrefix: defaultSubnetPrefix
          networkSecurityGroup: {
            id: defaultNsg.id
          }
        }
      }
      {
        name: 'GatewaySubnet'
        properties: {
          addressPrefix: gatewaySubnetPrefix
        }
      }
      {
        name: 'DnsResolverInboundSubnet'
        properties: {
          addressPrefix: dnsResolverInboundSubnetPrefix
          networkSecurityGroup: {
            id: dnsResolverInboundNsg.id
          }
          delegations: [
            {
              name: 'Microsoft.Network.dnsResolvers'
              properties: {
                serviceName: 'Microsoft.Network/dnsResolvers'
              }
            }
          ]
        }
      }
    ]
  }
}

resource gwPip1 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: 'VNetHubGWpip1'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  zones: [
    '1'
    '2'
    '3'
  ]
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource gwPip2 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: 'VNetHubGWpip2'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  zones: [
    '1'
    '2'
    '3'
  ]
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource p2sPip 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${vpnGatewayName}-p2s-pip'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  zones: [
    '1'
    '2'
    '3'
  ]
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource vpnGateway 'Microsoft.Network/virtualNetworkGateways@2023-11-01' = {
  name: vpnGatewayName
  location: location
  tags: tags
  properties: {
    gatewayType: 'Vpn'
    vpnType: 'RouteBased'
    activeActive: true
    sku: {
      name: vpnGatewaySku
      tier: vpnGatewaySku
    }
    ipConfigurations: [
      {
        name: 'default'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: '${vnet.id}/subnets/GatewaySubnet'
          }
          publicIPAddress: {
            id: gwPip1.id
          }
        }
      }
      {
        name: 'activeActive'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: '${vnet.id}/subnets/GatewaySubnet'
          }
          publicIPAddress: {
            id: gwPip2.id
          }
        }
      }
      {
        name: 'p2s'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: '${vnet.id}/subnets/GatewaySubnet'
          }
          publicIPAddress: {
            id: p2sPip.id
          }
        }
      }
    ]
    vpnClientConfiguration: {
      vpnClientAddressPool: {
        addressPrefixes: [
          p2sClientAddressPool
        ]
      }
      vpnClientProtocols: [
        'OpenVPN'
      ]
      vpnAuthenticationTypes: [
        'AAD'
      ]
      aadTenant: '${entraLoginEndpoint}${entraTenantId}/'
      aadAudience: azureVpnClientApplicationId
      aadIssuer: 'https://sts.windows.net/${entraTenantId}/'
    }
  }
}

resource dnsResolver 'Microsoft.Network/dnsResolvers@2022-07-01' = {
  name: dnsResolverName
  location: location
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource dnsResolverInboundEndpoint 'Microsoft.Network/dnsResolvers/inboundEndpoints@2022-07-01' = {
  parent: dnsResolver
  name: 'inbound-endpoint'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        privateIpAllocationMethod: 'Static'
        privateIpAddress: dnsResolverInboundIp
        subnet: {
          id: '${vnet.id}/subnets/DnsResolverInboundSubnet'
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output vpnGatewayName string = vpnGateway.name
