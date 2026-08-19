@description('Region.')
param location string = 'southeastasia'

@description('Application Gateway name.')
param name string

@description('Dedicated Application Gateway subnet resource ID.')
param subnetId string

@description('Private Container App backend FQDN.')
param backendFqdn string

@description('Globally unique DNS label for the public IP.')
param publicDnsLabel string

param tags object = {}

var frontendIpName = 'publicFrontend'
var frontendPortName = 'httpPort'
var backendPoolName = 'thaiSurnameBackend'
var backendSettingsName = 'httpsBackendSettings'
var listenerName = 'publicHttpListener'
var probeName = 'thaiHealthProbe'
var routingRuleName = 'thaiSurnameRule'
var rewriteRuleSetName = 'streamlitOriginRewrite'
var publicOrigin = 'http://${publicDnsLabel}.${location}.cloudapp.azure.com'

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
    dnsSettings: {
      domainNameLabel: publicDnsLabel
    }
  }
}

resource wafPolicy 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2023-11-01' = {
  name: '${name}-waf-policy'
  location: location
  tags: tags
  properties: {
    policySettings: {
      state: 'Enabled'
      mode: 'Prevention'
      requestBodyCheck: true
      maxRequestBodySizeInKb: 128
      fileUploadLimitInMb: 100
    }
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'OWASP'
          ruleSetVersion: '3.2'
        }
      ]
    }
  }
}

resource gateway 'Microsoft.Network/applicationGateways@2023-11-01' = {
  name: name
  location: location
  tags: tags
  zones: [
    '1'
    '2'
    '3'
  ]
  properties: {
    sku: {
      name: 'WAF_v2'
      tier: 'WAF_v2'
    }
    autoscaleConfiguration: {
      minCapacity: 0
      maxCapacity: 2
    }
    firewallPolicy: {
      id: wafPolicy.id
    }
    gatewayIPConfigurations: [
      {
        name: 'gatewayIpConfiguration'
        properties: {
          subnet: {
            id: subnetId
          }
        }
      }
    ]
    frontendIPConfigurations: [
      {
        name: frontendIpName
        properties: {
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
    frontendPorts: [
      {
        name: frontendPortName
        properties: {
          port: 80
        }
      }
    ]
    backendAddressPools: [
      {
        name: backendPoolName
        properties: {
          backendAddresses: [
            {
              fqdn: backendFqdn
            }
          ]
        }
      }
    ]
    probes: [
      {
        name: probeName
        properties: {
          protocol: 'Https'
          host: backendFqdn
          path: '/_stcore/health'
          interval: 30
          timeout: 30
          unhealthyThreshold: 3
          match: {
            statusCodes: [
              '200-399'
            ]
          }
        }
      }
    ]
    backendHttpSettingsCollection: [
      {
        name: backendSettingsName
        properties: {
          port: 443
          protocol: 'Https'
          cookieBasedAffinity: 'Disabled'
          requestTimeout: 60
          pickHostNameFromBackendAddress: true
          probe: {
            id: resourceId('Microsoft.Network/applicationGateways/probes', name, probeName)
          }
        }
      }
    ]
    httpListeners: [
      {
        name: listenerName
        properties: {
          frontendIPConfiguration: {
            id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', name, frontendIpName)
          }
          frontendPort: {
            id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', name, frontendPortName)
          }
          protocol: 'Http'
        }
      }
    ]
    rewriteRuleSets: [
      {
        name: rewriteRuleSetName
        properties: {
          rewriteRules: [
            {
              name: 'rewritePublicOriginForStreamlit'
              ruleSequence: 100
              conditions: [
                {
                  variable: 'http_req_Origin'
                  pattern: '^${publicOrigin}$'
                  ignoreCase: true
                  negate: false
                }
              ]
              actionSet: {
                requestHeaderConfigurations: [
                  {
                    headerName: 'Origin'
                    headerValue: 'https://${backendFqdn}:443'
                  }
                ]
              }
            }
          ]
        }
      }
    ]
    requestRoutingRules: [
      {
        name: routingRuleName
        properties: {
          ruleType: 'Basic'
          priority: 100
          httpListener: {
            id: resourceId('Microsoft.Network/applicationGateways/httpListeners', name, listenerName)
          }
          backendAddressPool: {
            id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', name, backendPoolName)
          }
          backendHttpSettings: {
            id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', name, backendSettingsName)
          }
          rewriteRuleSet: {
            id: resourceId('Microsoft.Network/applicationGateways/rewriteRuleSets', name, rewriteRuleSetName)
          }
        }
      }
    ]
    enableHttp2: true
  }
}

output gatewayId string = gateway.id
output publicIpAddress string = publicIp.properties.ipAddress
output publicFqdn string = publicIp.properties.dnsSettings.fqdn
output publicUrl string = 'http://${publicIp.properties.dnsSettings.fqdn}'
