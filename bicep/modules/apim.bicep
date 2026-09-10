// APIM Standard V2 — the AI Gateway control plane: department Products/Subscriptions,
// hub-first backend pool (hub Foundry primary, spoke Foundry secondary/example fallback),
// semantic caching via Managed Redis, and per-department/per-user token metering.
//
// Networking: Standard V2 keeps its public gateway hostname (no inbound Private Endpoint
// support on this SKU) and uses outbound VNet integration to reach private backends —
// this is the accepted trade-off documented in docs/ai-gateway-landing-zone.md. Confirm
// the exact `virtualNetworkConfiguration` outbound-integration schema against the ARM
// reference for the API version in use before deploying; this is a newer capability for
// v2 SKUs and the property surface has been evolving.

@description('Region.')
param location string = 'southeastasia'

@description('APIM service name (globally unique).')
param apimName string = 'apim-hub-sea'

@description('Publisher email required by APIM.')
param publisherEmail string

@description('Publisher/organization name required by APIM.')
param publisherName string = 'AI Gateway Platform Team'

@description('Number of Standard V2 scale units.')
param capacity int = 1

@description('Outbound VNet-integration subnet resource ID (snet-apim-outbound, delegated to Microsoft.Web/serverFarms).')
param outboundSubnetId string

@description('Departments onboarded to the gateway. Each becomes an APIM Product + Subscription, the chargeback boundary described in docs/ai-gateway-landing-zone.md.')
param departments array = [
  {
    name: 'odi'
    displayName: 'ODI'
  }
  {
    name: 'fa'
    displayName: 'FA'
  }
]

@description('Hub Foundry (AI Gateway subscription) OpenAI-compatible base URL, e.g. https://aif-hub-sea.cognitiveservices.azure.com/openai. Priority-1 backend — all quota is consumed here first.')
param hubFoundryBackendUrl string

@description('Resource ID of the hub Foundry (AIServices) account, used to scope the managed-identity backend credential.')
param hubFoundryAccountId string

@description('Existing spoke Foundry OpenAI-compatible base URL (worked overflow example only, no spoke changes required), e.g. https://foundry-app-sea<suffix>.cognitiveservices.azure.com/openai.')
param spokeFoundryBackendUrl string

@description('Resource ID of the spoke Foundry (AIServices) account, used to scope the managed-identity backend credential.')
param spokeFoundryAccountId string

@description('Embeddings deployment URL on the hub Foundry account used to vectorize prompts for the semantic cache, e.g. https://aif-hub-sea.cognitiveservices.azure.com/openai/deployments/text-embedding-3-small/embeddings.')
param embeddingsBackendUrl string

@description('Hub Foundry PROJECT OpenAI v1 base URL used to invoke a specific published agent by name/version (the Responses API surface, not the account-level Chat Completions surface), e.g. https://aif-hub-sea.services.ai.azure.com/api/projects/aiGatewayHubProject/openai/v1. Agents only ever live in the hub project — there is no spoke equivalent/failover for this path.')
param hubFoundryProjectAgentsUrl string = ''

@description('Managed Redis cluster name (from the redis module output), used to derive the database access key.')
param redisClusterName string

@description('Managed Redis hostname (from the redis module output).')
param redisHostName string

@description('Microsoft Entra tenant ID used by validate-jwt.')
param entraTenantId string = tenant().tenantId

@description('Expected audience (application ID URI or client ID) for caller access tokens.')
param entraAudience string

@description('System-assigned principal ID of the application spoke Foundry project allowed to use the model gateway.')
param spokeAppProjectPrincipalId string

@description('System-assigned principal ID of the agent spoke Foundry project allowed to use the model gateway.')
param spokeAgentProjectPrincipalId string

@description('Application Insights instrumentation resource ID, for the APIM diagnostic logger.')
param appInsightsId string

@description('Application Insights connection string.')
@secure()
param appInsightsConnectionString string

@description('Event Hub namespace fully-qualified hostname (e.g. evhns-hub-sea-<suffix>.servicebus.windows.net), for the usage-event logger.')
param eventHubNamespaceHostName string

@description('Resource ID of the Event Hub namespace, used to grant APIM\'s managed identity Azure Event Hubs Data Sender before the logger/fragment are validated.')
param eventHubNamespaceId string

@description('Event hub (topic) name receiving usage events.')
param eventHubName string = 'llm-usage-events'

param tags object = {}

resource redisCluster 'Microsoft.Cache/redisEnterprise@2024-09-01-preview' existing = {
  name: redisClusterName
}

resource redisDb 'Microsoft.Cache/redisEnterprise/databases@2024-09-01-preview' existing = {
  parent: redisCluster
  name: 'default'
}

var redisAccessKey = redisDb.listKeys().primaryKey
var redisConnectionString = '${redisHostName}:10000,password=${redisAccessKey},ssl=True,abortConnect=False'

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: 'StandardV2'
    capacity: capacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
    publicNetworkAccess: 'Enabled'
    // Standard v2's "outbound-only" VNet integration (subnetResourceId set, but gateway
    // hostname stays public) requires virtualNetworkType: 'External' — ARM rejects
    // 'None' (the schema default) whenever virtualNetworkConfiguration is also set
    // ("'virtualNetworkType' cannot be 'none' when 'virtualNetworkConfiguration' is not
    // null", confirmed via a real deployment failure).
    virtualNetworkType: 'External'
    virtualNetworkConfiguration: {
      subnetResourceId: outboundSubnetId
    }
  }
}

resource loggerAppInsights 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights-logger'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsightsId
    credentials: {
      connectionString: appInsightsConnectionString
    }
  }
}

resource redisCache 'Microsoft.ApiManagement/service/caches@2024-05-01' = {
  parent: apim
  name: 'semantic-cache-redis'
  properties: {
    connectionString: redisConnectionString
    useFromLocation: 'default'
    description: 'redis-hub-sea Managed Redis (RediSearch) — semantic cache'
  }
}

resource namedValueTenantId 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'entra-tenant-id'
  properties: {
    displayName: 'entra-tenant-id'
    value: entraTenantId
    secret: false
  }
}

// Event Hub logger for the usage-audit trail (uses APIM's system-assigned identity — the
// identity must be granted "Azure Event Hubs Data Sender" on the namespace; see main.bicep).
resource eventHubNamespaceRef 'Microsoft.EventHub/namespaces@2024-01-01' existing = {
  name: last(split(eventHubNamespaceId, '/'))
}

// Granted here (not as a separate top-level module in main.bicep) so it completes, with
// RBAC propagation, before the logger/fragment below are validated in the same deployment —
// a cross-module dependsOn on this module's *output* would only run after this whole module
// (including the logger validation) already finished, which caused
// "Attempted to perform an unauthorized operation" on first deploy.
resource apimEventHubSenderRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHubNamespaceRef.id, apim.id, 'EventHubsDataSender')
  scope: eventHubNamespaceRef
  properties: {
    principalId: apim.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2b629674-e913-4c01-ae53-ef4638d8f975')
    principalType: 'ServicePrincipal'
  }
}

resource loggerEventHub 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'eventhub-usage-logger'
  properties: {
    loggerType: 'azureEventHub'
    description: 'Usage-event audit trail — drained by the logic-hub-usage-sea rollup workflow'
    credentials: {
      endpointAddress: eventHubNamespaceHostName
      name: eventHubName
      identityClientId: 'SystemAssigned'
    }
  }
  dependsOn: [
    apimEventHubSenderRoleAssignment
  ]
}

resource namedValueAudience 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'entra-audience'
  properties: {
    displayName: 'entra-audience'
    value: entraAudience
    secret: false
  }
}

resource namedValueSpokeAppProjectPrincipalId 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'spoke-app-project-principal-id'
  properties: {
    displayName: 'spoke-app-project-principal-id'
    value: spokeAppProjectPrincipalId
    secret: false
  }
}

resource namedValueSpokeAgentProjectPrincipalId 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'spoke-agent-project-principal-id'
  properties: {
    displayName: 'spoke-agent-project-principal-id'
    value: spokeAgentProjectPrincipalId
    secret: false
  }
}

resource hubFoundryBackend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'hub-foundry-backend'
  properties: {
    url: hubFoundryBackendUrl
    protocol: 'http'
    resourceId: '${environment().resourceManager}${skip(hubFoundryAccountId, 1)}'
    circuitBreaker: {
      rules: [
        {
          failureCondition: {
            count: 3
            interval: 'PT1M'
            statusCodeRanges: [
              {
                min: 429
                max: 429
              }
              {
                min: 500
                max: 599
              }
            ]
          }
          name: 'hub-foundry-breaker'
          tripDuration: 'PT1M'
        }
      ]
    }
  }
}

resource spokeFoundryBackend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'spoke-foundry-backend'
  properties: {
    url: spokeFoundryBackendUrl
    protocol: 'http'
    resourceId: '${environment().resourceManager}${skip(spokeFoundryAccountId, 1)}'
  }
}

resource embeddingsBackend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'foundry-embeddings'
  properties: {
    url: embeddingsBackendUrl
    protocol: 'http'
  }
}

// Separate backend for invoking a specific PUBLISHED Foundry agent (Prompt Agent created
// in the Foundry Portal / via AIProjectClient.agents.create_version). This targets the
// project-scoped Responses API (`{project}/openai/v1/responses` + `agent_reference` in the
// body) — a completely different host+path shape than hub-foundry-backend's account-scoped
// Chat Completions surface, so it needs its own backend/operation/policy rather than
// reusing the existing hub/spoke failover pair. No spoke equivalent: agents are defined
// against the hub project only, so there is nothing to fail over to here.
resource hubFoundryAgentsBackend 'Microsoft.ApiManagement/service/backends@2024-05-01' = if (!empty(hubFoundryProjectAgentsUrl)) {
  parent: apim
  name: 'hub-foundry-agents-backend'
  properties: {
    url: hubFoundryProjectAgentsUrl
    protocol: 'http'
    resourceId: '${environment().resourceManager}${skip(hubFoundryAccountId, 1)}'
  }
}

resource fragValidateJwt 'Microsoft.ApiManagement/service/policyFragments@2024-05-01' = {
  parent: apim
  name: 'frag-validate-jwt'
  properties: {
    format: 'xml'
    value: loadTextContent('policies/frag-validate-jwt.xml')
    description: 'Validates caller Entra ID tokens and resolves the per-user cost dimension.'
  }
  dependsOn: [
    namedValueTenantId
    namedValueAudience
    namedValueSpokeAppProjectPrincipalId
    namedValueSpokeAgentProjectPrincipalId
  ]
}

resource fragSemanticCacheLookup 'Microsoft.ApiManagement/service/policyFragments@2024-05-01' = {
  parent: apim
  name: 'frag-semantic-cache-lookup'
  properties: {
    format: 'xml'
    value: loadTextContent('policies/frag-semantic-cache-lookup.xml')
    description: 'Semantic cache lookup backed by Managed Redis.'
  }
  dependsOn: [
    redisCache
    embeddingsBackend
  ]
}

resource fragSemanticCacheStore 'Microsoft.ApiManagement/service/policyFragments@2024-05-01' = {
  parent: apim
  name: 'frag-semantic-cache-store'
  properties: {
    format: 'xml'
    value: loadTextContent('policies/frag-semantic-cache-store.xml')
    description: 'Stores successful responses in the semantic cache.'
  }
}

// frag-backend-failover.xml and frag-llm-token-metric.xml are no longer deployed as
// policyFragment resources: APIM rejects `forward-request`/`retry` and
// `llm-emit-token-metric`/`log-to-eventhub` inside a <fragment> ("allowed sections don't
// overlap" / "Policy is not allowed in this section") since fragments must be
// section-agnostic, but those policies are restricted to specific sections
// (backend-only, outbound-only). Both are now inlined directly in api-policy.xml's
// <backend>/<outbound> sections instead. The .xml files are kept only as
// documentation/reference for the pattern.

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  properties: {
    displayName: 'AI Gateway — OpenAI-compatible'
    path: 'openai'
    protocols: [
      'https'
    ]
    // Project managed identities authenticate with Entra tokens and do not carry APIM
    // subscription keys. JWT validation remains mandatory in the API policy.
    subscriptionRequired: false
    serviceUrl: hubFoundryBackendUrl
  }
  name: 'ai-gateway-openai'
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/api-policy.xml')
  }
  dependsOn: [
    fragValidateJwt
    fragSemanticCacheLookup
    fragSemanticCacheStore
    loggerEventHub
    hubFoundryBackend
    spokeFoundryBackend
  ]
}

// Wires the ai-gateway-openai API to the Application Insights logger so request
// traces AND custom metrics (llm-emit-token-metric's "llm-usage" namespace) actually
// flow into App Insights. Without this diagnostics resource, App Insights integration
// is inert even though the logger itself exists — llm-emit-token-metric's own
// prerequisites explicitly require "Enable Application Insights logging for your LLM
// APIs" and "Enable custom metrics with dimensions in Application Insights", both of
// which are configured here (metrics: true, verbosity: information).
resource apiDiagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = {
  parent: api
  name: 'applicationinsights'
  properties: {
    loggerId: loggerAppInsights.id
    alwaysLog: 'allErrors'
    verbosity: 'information'
    metrics: true
    logClientIp: true
    httpCorrelationProtocol: 'W3C'
    frontend: {
      request: {
        headers: []
        body: {
          bytes: 0
        }
      }
      response: {
        headers: []
        body: {
          bytes: 0
        }
      }
    }
    backend: {
      request: {
        headers: []
        body: {
          bytes: 0
        }
      }
      response: {
        headers: []
        body: {
          bytes: 0
        }
      }
    }
  }
}

resource chatCompletionsOperation 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'chat-completions'
  properties: {
    displayName: 'Chat completions'
    method: 'POST'
    urlTemplate: '/deployments/{deployment-id}/chat/completions'
    templateParameters: [
      {
        name: 'deployment-id'
        type: 'string'
        required: true
      }
    ]
  }
}

// Separate API surface for invoking a specific PUBLISHED Foundry agent by name/version
// (Responses API + agent_reference), distinct from the account-scoped Chat Completions
// API above. See modules/policies/api-agents-policy.xml for why this needs its own
// backend/policy. Only created when hubFoundryProjectAgentsUrl is supplied.
resource agentsApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = if (!empty(hubFoundryProjectAgentsUrl)) {
  parent: apim
  properties: {
    displayName: 'AI Gateway — Foundry Agents'
    path: 'agents'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    serviceUrl: hubFoundryProjectAgentsUrl
  }
  name: 'ai-gateway-foundry-agents'
}

resource agentsApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = if (!empty(hubFoundryProjectAgentsUrl)) {
  parent: agentsApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/api-agents-policy.xml')
  }
}

resource agentsResponsesOperation 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = if (!empty(hubFoundryProjectAgentsUrl)) {
  parent: agentsApi
  name: 'agent-responses'
  properties: {
    displayName: 'Invoke a published Foundry agent (Responses API)'
    method: 'POST'
    urlTemplate: '/responses'
  }
}

// Same reasoning as `apiDiagnostics` above: without an explicit diagnostics binding, this
// API's requests/customMetrics (llm-emit-token-metric, "llm-usage" namespace) never reach
// Application Insights even though the logger resource exists. Discovered live: the first
// deployment of the agents API omitted this, so agent-invocation calls succeeded (HTTP 200)
// but produced zero rows in App Insights until this binding was added.
resource agentsApiDiagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = if (!empty(hubFoundryProjectAgentsUrl)) {
  parent: agentsApi
  name: 'applicationinsights'
  properties: {
    loggerId: loggerAppInsights.id
    alwaysLog: 'allErrors'
    verbosity: 'information'
    metrics: true
    logClientIp: true
    httpCorrelationProtocol: 'W3C'
    frontend: {
      request: {
        headers: []
        body: {
          bytes: 0
        }
      }
      response: {
        headers: []
        body: {
          bytes: 0
        }
      }
    }
    backend: {
      request: {
        headers: []
        body: {
          bytes: 0
        }
      }
      response: {
        headers: []
        body: {
          bytes: 0
        }
      }
    }
  }
}

resource departmentProducts 'Microsoft.ApiManagement/service/products@2024-05-01' = [for dept in departments: {
  parent: apim
  name: 'product-${dept.name}'
  properties: {
    displayName: dept.displayName
    description: 'Department chargeback boundary for ${dept.displayName} — every call under this product/subscription is attributed to this department.'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}]

resource departmentProductPolicies 'Microsoft.ApiManagement/service/products/policies@2024-05-01' = [for (dept, i) in departments: {
  parent: departmentProducts[i]
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('policies/default-product-policy.xml')
  }
}]

resource departmentProductApis 'Microsoft.ApiManagement/service/products/apis@2024-05-01' = [for (dept, i) in departments: {
  parent: departmentProducts[i]
  name: api.name
}]

// Same department Product/Subscription boundary also covers the Foundry Agents API, so
// the exact same subscription key used for chat/completions works for agent invocation too
// — one key, one product, one department, regardless of which API surface is called.
resource departmentProductAgentsApis 'Microsoft.ApiManagement/service/products/apis@2024-05-01' = [for (dept, i) in departments: if (!empty(hubFoundryProjectAgentsUrl)) {
  parent: departmentProducts[i]
  name: 'ai-gateway-foundry-agents'
  dependsOn: [
    agentsApi
  ]
}]

resource departmentSubscriptions 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = [for (dept, i) in departments: {
  parent: apim
  name: 'subscription-${dept.name}'
  properties: {
    displayName: '${dept.displayName} department subscription'
    scope: '/products/${departmentProducts[i].name}'
    state: 'active'
  }
}]

output apimId string = apim.id
output apimName string = apim.name
output apimPrincipalId string = apim.identity.principalId
output gatewayUrl string = apim.properties.gatewayUrl
