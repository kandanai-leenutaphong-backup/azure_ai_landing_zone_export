// Generic Container App module shared by the spoke application workloads.
// Image/env/ingress are parametrized: fill in real values (or wire to ACR + secrets) before
// deploying — this file preserves the *structure* of each app, not the live secrets/image tags.

@description('Region.')
param location string = 'southeastasia'

@description('Container app name.')
param name string

@description('Resource ID of the Container Apps managed environment.')
param environmentId string

@description('Container image (e.g. <acrLoginServer>/<repo>:<tag>).')
param image string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Target port for ingress.')
param targetPort int = 80

@description('Whether ingress is external (internet-facing via the internal Container Apps environment) or internal-only (service-to-service).')
param externalIngress bool = true

@description('CPU cores per replica.')
param cpu string = '0.5'

@description('Memory per replica.')
param memory string = '1Gi'

@description('Min/max replica counts.')
param minReplicas int = 0
param maxReplicas int = 1

@description('Environment variables for the container.')
param envVars array = []

@description('User-assigned identity resource IDs to attach (e.g. for ACR pull).')
param userAssignedIdentityIds array = []

@description('Azure Container Registry login server. Leave empty for public images.')
param registryServer string = ''

param tags object = {}

var identityType = length(userAssignedIdentityIds) > 0 ? 'UserAssigned' : 'None'
var registryIdentity = length(userAssignedIdentityIds) > 0 ? userAssignedIdentityIds[0] : ''

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: identityType
    userAssignedIdentities: length(userAssignedIdentityIds) > 0 ? toObject(userAssignedIdentityIds, id => id, id => {}) : null
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      registries: empty(registryServer) ? [] : [
        {
          server: registryServer
          identity: registryIdentity
        }
      ]
      ingress: {
        external: externalIngress
        targetPort: targetPort
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: name
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: envVars
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output containerAppId string = containerApp.id
output fqdn string = containerApp.properties.configuration.ingress.fqdn
