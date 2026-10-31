// Hub Azure Firewall (Basic) with a firewall policy. Spoke and AI Gateway subnets
// send 0.0.0.0/0 and inter-VNet traffic here through user-defined routes.

@description('Region.')
param location string = 'southeastasia'

@description('Firewall name.')
param name string = 'afw-hub-sea'

@description('AzureFirewallSubnet resource ID.')
param firewallSubnetId string

@description('AzureFirewallManagementSubnet resource ID (required by the Basic SKU).')
param managementSubnetId string

@description('Address ranges of the connected VNets that are allowed to send traffic through the firewall.')
param internalRanges array

@description('Hub Application Gateway subnet prefix.')
param applicationGatewaySubnetPrefix string

@description('Workload spoke address space (destination of Application Gateway backend traffic).')
param spokeAddressPrefix string

@description('DNS Private Resolver inbound IP.')
param dnsResolverInboundIp string

@description('Allow outbound HTTP/HTTPS to any destination from internal ranges. Set false and extend webFqdns to allow-list only.')
param allowAllOutboundWeb bool = true

@description('FQDNs allowed over HTTP/HTTPS when allowAllOutboundWeb is false.')
param webFqdns array = [
  '*.azurecr.io'
  'mcr.microsoft.com'
  '*.data.mcr.microsoft.com'
  'login.microsoftonline.com'
  'management.azure.com'
  'graph.microsoft.com'
  '*.monitor.azure.com'
  '*.ods.opinsights.azure.com'
  '*.oms.opinsights.azure.com'
  '*.ubuntu.com'
]

@description('Log Analytics workspace resource ID for firewall logs. Leave empty to skip diagnostics.')
param logAnalyticsWorkspaceId string = ''

param tags object = {}

resource publicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${name}-pip'
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

resource managementPublicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${name}-mgmt-pip'
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

resource policy 'Microsoft.Network/firewallPolicies@2023-11-01' = {
  name: '${name}-policy'
  location: location
  tags: tags
  properties: {
    sku: {
      tier: 'Basic'
    }
    threatIntelMode: 'Alert'
    // Always SNAT so backends without a matching UDR (for example the consumption
    // Container Apps subnet) return traffic through the firewall (symmetric routing).
    snat: {
      privateRanges: [
        '255.255.255.255/32'
      ]
    }
  }
}

resource ruleGroup 'Microsoft.Network/firewallPolicies/ruleCollectionGroups@2023-11-01' = {
  parent: policy
  name: 'DefaultRuleCollectionGroup'
  properties: {
    priority: 200
    ruleCollections: [
      {
        ruleCollectionType: 'FirewallPolicyFilterRuleCollection'
        name: 'allow-internal-network'
        priority: 100
        action: {
          type: 'Allow'
        }
        rules: [
          {
            ruleType: 'NetworkRule'
            name: 'spoke-to-spoke'
            ipProtocols: [
              'TCP'
              'UDP'
              'ICMP'
            ]
            sourceAddresses: internalRanges
            destinationAddresses: internalRanges
            destinationPorts: ['*']
          }
          {
            ruleType: 'NetworkRule'
            name: 'appgw-to-spoke-https'
            ipProtocols: [
              'TCP'
            ]
            sourceAddresses: [
              applicationGatewaySubnetPrefix
            ]
            destinationAddresses: [
              spokeAddressPrefix
            ]
            destinationPorts: ['443']
          }
          {
            ruleType: 'NetworkRule'
            name: 'container-apps-platform'
            ipProtocols: [
              'UDP'
            ]
            sourceAddresses: internalRanges
            destinationAddresses: [
              'AzureCloud.${location}'
            ]
            destinationPorts: ['1194']
          }
          {
            ruleType: 'NetworkRule'
            name: 'container-apps-platform-tcp'
            ipProtocols: [
              'TCP'
            ]
            sourceAddresses: internalRanges
            destinationAddresses: [
              'AzureCloud.${location}'
            ]
            destinationPorts: ['9000']
          }
          {
            ruleType: 'NetworkRule'
            name: 'dns-to-hub-resolver'
            ipProtocols: [
              'UDP'
              'TCP'
            ]
            sourceAddresses: internalRanges
            destinationAddresses: [
              dnsResolverInboundIp
            ]
            destinationPorts: ['53']
          }
        ]
      }
      {
        ruleCollectionType: 'FirewallPolicyFilterRuleCollection'
        name: 'allow-outbound-web'
        priority: 200
        action: {
          type: 'Allow'
        }
        rules: [
          {
            ruleType: 'ApplicationRule'
            name: allowAllOutboundWeb ? 'web-any' : 'web-allow-list'
            sourceAddresses: internalRanges
            protocols: [
              {
                protocolType: 'Https'
                port: 443
              }
              {
                protocolType: 'Http'
                port: 80
              }
            ]
            targetFqdns: allowAllOutboundWeb ? ['*'] : webFqdns
          }
        ]
      }
    ]
  }
}

resource firewall 'Microsoft.Network/azureFirewalls@2023-11-01' = {
  name: name
  location: location
  tags: tags
  zones: [
    '1'
    '2'
    '3'
  ]
  dependsOn: [
    ruleGroup
  ]
  properties: {
    sku: {
      name: 'AZFW_VNet'
      tier: 'Basic'
    }
    firewallPolicy: {
      id: policy.id
    }
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          subnet: {
            id: firewallSubnetId
          }
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
    managementIpConfiguration: {
      name: 'mgmt-ipconfig'
      properties: {
        subnet: {
          id: managementSubnetId
        }
        publicIPAddress: {
          id: managementPublicIp.id
        }
      }
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'to-log-analytics'
  scope: firewall
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}

output firewallId string = firewall.id
output firewallName string = firewall.name
output privateIpAddress string = firewall.properties.ipConfigurations[0].properties.privateIPAddress
output publicIpAddress string = publicIp.properties.ipAddress
