// Azure Managed Redis (Redis Enterprise architecture) with the RediSearch module
// enabled, used as the APIM semantic-cache backing store. Private-endpoint only.

@description('Region. Azure Managed Redis is only available in a subset of regions — confirm availability before deploying.')
param location string = 'southeastasia'

@description('Cluster name (globally unique, lowercase).')
param name string

@description('Azure Managed Redis SKU name. Balanced_B0 is the smallest Balanced-tier SKU; confirm current SKU names/capacity increments against the latest Azure Managed Redis pricing/availability before deploying.')
param skuName string = 'Balanced_B0'

@description('snet-pe subnet resource ID for the private endpoint.')
param privateEndpointSubnetId string

@description('Resource ID of the privatelink.redis.azure.net zone in the hub RG.')
param redisPrivateDnsZoneId string

param tags object = {}

resource redisCluster 'Microsoft.Cache/redisEnterprise@2025-04-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    minimumTlsVersion: '1.2'
  }
}

resource redisDatabase 'Microsoft.Cache/redisEnterprise/databases@2025-04-01' = {
  parent: redisCluster
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    // RediSearch (and other Enterprise modules) require EnterpriseCluster; OSSCluster is
    // rejected by the API with "'RediSearch' module is not supported with OSS clustering
    // policy" (confirmed via a real deployment failure).
    clusteringPolicy: 'EnterpriseCluster'
    evictionPolicy: 'NoEviction'
    port: 10000
    modules: [
      {
        name: 'RediSearch'
      }
    ]
  }
}

module redisPrivateEndpoint 'private-endpoint.bicep' = {
  name: 'pe-${name}'
  params: {
    location: location
    name: '${name}-pe'
    subnetId: privateEndpointSubnetId
    targetResourceId: redisCluster.id
    groupIds: [
      'redisEnterprise'
    ]
    privateDnsZoneIds: [
      redisPrivateDnsZoneId
    ]
    tags: tags
  }
}

output redisClusterId string = redisCluster.id
output redisClusterName string = redisCluster.name
output redisHostName string = redisCluster.properties.hostName
output redisDatabaseId string = redisDatabase.id
