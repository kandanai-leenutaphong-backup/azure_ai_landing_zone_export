param location string = 'southeastasia'
param appName string = 'customer-service-multi-agent'
param environmentName string
param registryName string
param identityName string
param image string
param tenantId string
param authClientId string
param browserClientId string
param hostedAgentName string = ''
param hostedAgentVersion string = ''
param allowedObjectIds string
param managedIdentityClientId string
param projectEndpoint string
param modelDeployment string
param agentVersions object
param hubFirewallSourcePrefix string
@description('Existing Application Insights in this resource group; empty disables trace export.')
param appInsightsName string = ''
@description('Comma-separated Entra object IDs allowed to replay any stored conversation; empty disables replay.')
param replayOperatorObjectIds string = ''

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: environmentName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: identityName
}

resource appi 'Microsoft.Insights/components@2020-02-02' existing = if (!empty(appInsightsName)) {
  name: empty(appInsightsName) ? 'none' : appInsightsName
}

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  tags: {
    project: 'customer-service-multi-agent'
    managedBy: 'deploy/deploy.sh'
    dataClassification: 'synthetic-only'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'http'
        ipSecurityRestrictions: [
          {
            name: 'hub-waf-only'
            description: 'Only the existing hub Application Gateway subnet may reach the private ingress.'
            ipAddressRange: '10.0.5.0/24'
            action: 'Allow'
          }
          {
            name: 'hub-firewall-snat'
            description: 'Existing hub policy forces SNAT for gateway-to-spoke traffic.'
            ipAddressRange: hubFirewallSourcePrefix
            action: 'Allow'
          }
        ]
      }
      registries: [
        {
          server: '${registryName}.azurecr.io'
          identity: identity.id
        }
      ]
      secrets: empty(appInsightsName) ? [] : [
        { name: 'appinsights-connection', value: appi!.properties.ConnectionString }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            { name: 'TENANT_ID', value: tenantId }
            { name: 'AUTH_CLIENT_ID', value: authClientId }
            { name: 'BROWSER_CLIENT_ID', value: browserClientId }
            { name: 'HOSTED_AGENT_NAME', value: hostedAgentName }
            { name: 'HOSTED_AGENT_VERSION', value: hostedAgentVersion }
            { name: 'AUTH_ALLOWED_OBJECT_IDS', value: allowedObjectIds }
            { name: 'REPLAY_OPERATOR_OBJECT_IDS', value: replayOperatorObjectIds }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'AZURE_AUTH_MODE', value: 'managed_identity' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: projectEndpoint }
            { name: 'MODEL_DEPLOYMENT', value: modelDeployment }
            { name: 'APP_REVISION', value: last(split(image, '@')) }
            { name: 'AGENT_TRIAGE_VERSION', value: agentVersions.triage }
            { name: 'AGENT_POLICY_VERSION', value: agentVersions.policy }
            { name: 'AGENT_RESOLUTION_VERSION', value: agentVersions.resolution }
            { name: 'AGENT_JUDGE_FACTUAL_ACCURACY_VERSION', value: agentVersions.judge_factual_accuracy }
            { name: 'AGENT_JUDGE_TASK_COMPLETION_VERSION', value: agentVersions.judge_task_completion }
            { name: 'AGENT_JUDGE_TONE_VERSION', value: agentVersions.judge_tone }
            { name: 'AGENT_JUDGE_CONSISTENCY_VERSION', value: agentVersions.judge_consistency }
          ], empty(appInsightsName) ? [] : [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
          ])
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8080, scheme: 'HTTP' }
              initialDelaySeconds: 15
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/healthz', port: 8080, scheme: 'HTTP' }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '5' } }
          }
        ]
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output appId string = app.id
