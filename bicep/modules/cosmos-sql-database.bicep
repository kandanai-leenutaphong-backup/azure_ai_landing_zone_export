// SQL API database + container child resources for a Cosmos DB account. Used by the
// AI Gateway usage/chargeback store — partitioned by department so each department's
// finance owner can be scoped to just their partition key if read access is delegated.

@description('Name of the parent Cosmos DB account.')
param accountName string

@description('SQL database name.')
param databaseName string = 'usage'

@description('SQL container name.')
param containerName string = 'token-usage-daily'

@description('Container partition key path.')
param partitionKeyPath string = '/department'

@description('Autoscale max throughput (RU/s) for the database. Set to 0 to use serverless (no throughput property) — only valid if the account was created without capacity mode Serverless enabled at the account level.')
param autoscaleMaxThroughput int = 0

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' existing = {
  name: accountName
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-08-15' = {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
    options: autoscaleMaxThroughput > 0 ? {
      autoscaleSettings: {
        maxThroughput: autoscaleMaxThroughput
      }
    } : {}
  }
}

resource container 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-08-15' = {
  parent: database
  name: containerName
  properties: {
    resource: {
      id: containerName
      partitionKey: {
        paths: [
          partitionKeyPath
        ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
        ]
      }
    }
  }
}

output databaseName string = database.name
output containerName string = container.name
