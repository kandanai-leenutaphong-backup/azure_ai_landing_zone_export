@description('Location for the workbook.')
param location string

@description('Display name shown in the Azure Portal Workbooks gallery.')
param displayName string = 'AI Gateway - Cost, Token & MCP Usage Dashboard'

@description('Resource ID of the Application Insights instance backing the AI Gateway (source of llm-usage custom metrics).')
param appInsightsId string

@description('Tags to apply to the workbook resource.')
param tags object = {}

// Deterministic GUID so re-deployments update the same workbook instead of creating duplicates.
var workbookGuid = guid(resourceGroup().id, 'ai-gateway-cost-workbook')

// Match the backing Log Analytics workspace retention so the workbook shows all available data.
var telemetryHistoryDurationMs = 15552000000

var workbookContent = {
  version: 'Notebook/1.0'
  items: [
    {
      type: 1
      content: {
        json: '## AI Gateway - Cost, Token & MCP Usage Dashboard\nPer-department and per-user chargeback plus MCP tool activity, sourced from APIM custom metrics. The dashboard covers the full 180-day telemetry retention period. Department comes from the caller\'s Entra ID App Role; user comes from the Entra `oid` claim.'
      }
      name: 'text - title'
    }
    {
      type: 9
      content: {
        version: 'KqlParameterItem/1.0'
        parameters: [
          {
            id: 'department-param'
            version: 'KqlParameterItem/1.0'
            name: 'Department'
            type: 2
            isRequired: false
            multiSelect: true
            quote: '\''
            delimiter: ','
            query: 'customMetrics\n| where name in (\'Total Tokens\', \'MCP Tool Calls\')\n| extend department = tostring(customDimensions.department)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| distinct department\n| order by department asc\n| project value = department, label = department, selected = true'
            typeSettings: {
              additionalResultOptions: [
                'selectall'
              ]
              showDefault: true
            }
            timeContext: {
              durationMs: telemetryHistoryDurationMs
            }
            queryType: 0
            resourceType: 'microsoft.insights/components'
          }
          {
            id: 'user-param'
            version: 'KqlParameterItem/1.0'
            name: 'User'
            type: 2
            isRequired: false
            multiSelect: true
            quote: '\''
            delimiter: ','
            query: 'customMetrics\n| where name in (\'Total Tokens\', \'MCP Tool Calls\')\n| extend user = tostring(customDimensions.user), userName = tostring(customDimensions.userName)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| distinct Display\n| order by Display asc\n| project value = Display, label = Display, selected = true'
            typeSettings: {
              additionalResultOptions: [
                'selectall'
              ]
              showDefault: true
            }
            timeContext: {
              durationMs: telemetryHistoryDurationMs
            }
            queryType: 0
            resourceType: 'microsoft.insights/components'
          }
        ]
        style: 'pills'
        queryType: 0
        resourceType: 'microsoft.insights/components'
      }
      name: 'parameters - filters'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        // "Prompt Tokens"/"Completion Tokens"/"Prompt Cached Tokens" are llm-emit-token-metric's
        // OWN normalized metric names — it emits these same three names regardless of whether the
        // call went through Chat Completions (prompt_tokens/completion_tokens) or the Responses API
        // used by agent invocation (input_tokens/output_tokens/cached_tokens), so InputTokens/
        // OutputTokens/CachedTokens below are populated consistently for both the "gpt-4o-hub-prod"
        // and "foundry-agent" deployment rows. CachedTokens is a SUBSET of InputTokens (cached
        // prompt tokens are billed at a discount, not on top of InputTokens), not additional —
        // InputTokens + OutputTokens = TotalTokens as usual.
        query: 'let departmentFilter = dynamic([{Department}]);\nlet userFilter = dynamic([{User}]);\ncustomMetrics\n| where name in (\'Total Tokens\',\'Prompt Tokens\',\'Completion Tokens\',\'Prompt Cached Tokens\')\n| extend department = tostring(customDimensions.department), user = tostring(customDimensions.user), userName = tostring(customDimensions.userName), deployment = tostring(customDimensions.deployment)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| where array_length(departmentFilter) == 0 or department in (departmentFilter)\n| where array_length(userFilter) == 0 or Display in (userFilter)\n| summarize TotalTokens = sumif(valueSum, name == \'Total Tokens\'), InputTokens = sumif(valueSum, name == \'Prompt Tokens\'), OutputTokens = sumif(valueSum, name == \'Completion Tokens\'), CachedTokens = sumif(valueSum, name == \'Prompt Cached Tokens\'), Calls = dcountif(itemId, name == \'Total Tokens\') by department, deployment\n| extend EstimatedCostUSD = round((InputTokens/1000.0 * 0.005) + (OutputTokens/1000.0 * 0.015), 4)\n| project department, deployment, TotalTokens, InputTokens, OutputTokens, CachedTokens, Calls, EstimatedCostUSD\n| order by TotalTokens desc'
        size: 0
        title: 'Token usage & estimated cost by Department'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
      }
      name: 'query - by department'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        // Same normalized-metric-name reasoning as the "by Department" query above applies here.
        query: 'let departmentFilter = dynamic([{Department}]);\nlet userFilter = dynamic([{User}]);\ncustomMetrics\n| where name in (\'Total Tokens\',\'Prompt Tokens\',\'Completion Tokens\',\'Prompt Cached Tokens\')\n| extend department = tostring(customDimensions.department), user = tostring(customDimensions.user), userName = tostring(customDimensions.userName)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| where array_length(departmentFilter) == 0 or department in (departmentFilter)\n| where array_length(userFilter) == 0 or Display in (userFilter)\n| summarize TotalTokens = sumif(valueSum, name == \'Total Tokens\'), InputTokens = sumif(valueSum, name == \'Prompt Tokens\'), OutputTokens = sumif(valueSum, name == \'Completion Tokens\'), CachedTokens = sumif(valueSum, name == \'Prompt Cached Tokens\'), Calls = dcountif(itemId, name == \'Total Tokens\'), UserName = anyif(userName, isnotempty(userName)) by department, user\n| extend EstimatedCostUSD = round((InputTokens/1000.0 * 0.005) + (OutputTokens/1000.0 * 0.015), 4)\n| project department, user, UserName, TotalTokens, InputTokens, OutputTokens, CachedTokens, Calls, EstimatedCostUSD\n| order by TotalTokens desc'
        size: 0
        title: 'Token usage & estimated cost by User'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
      }
      name: 'query - by user'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        // Sourced from the "Tokens By Model" metric (namespace llm-usage-model), emitted
        // separately by api-policy.xml/api-agents-policy.xml alongside (not instead of) the
        // llm-usage metrics above — see the MODEL ATTRIBUTION comment in those policy files
        // for why a second metric was needed (llm-emit-token-metric can't read the response
        // to know which model actually served the request). "agent" is populated only for
        // calls through the /agents (Foundry agent invocation) API; for plain Chat
        // Completions calls it is blank, so the deployment name is shown instead.
        query: 'let departmentFilter = dynamic([{Department}]);\nlet userFilter = dynamic([{User}]);\ncustomMetrics\n| where name == \'Tokens By Model\'\n| extend department = tostring(customDimensions.department), user = tostring(customDimensions.user), userName = tostring(customDimensions.userName), model = tostring(customDimensions.model), agent = tostring(customDimensions.agent), deployment = tostring(customDimensions.deployment)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| where array_length(departmentFilter) == 0 or department in (departmentFilter)\n| where array_length(userFilter) == 0 or Display in (userFilter)\n| extend AgentOrDeployment = iif(isnotempty(agent), agent, deployment)\n| summarize TotalTokens = sum(valueSum), Calls = count() by department, Model = model, Agent = AgentOrDeployment\n| order by TotalTokens desc'
        size: 0
        title: 'Token usage by Model (and Agent)'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
      }
      name: 'query - by model'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'let departmentFilter = dynamic([{Department}]);\nlet userFilter = dynamic([{User}]);\ncustomMetrics\n| where name == \'Total Tokens\'\n| extend department = tostring(customDimensions.department), user = tostring(customDimensions.user), userName = tostring(customDimensions.userName)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| where array_length(departmentFilter) == 0 or department in (departmentFilter)\n| where array_length(userFilter) == 0 or Display in (userFilter)\n| summarize Tokens = sum(valueSum) by bin(timestamp, 1h), department\n| render timechart'
        size: 0
        title: 'Token usage over time by Department'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'timechart'
      }
      name: 'query - timechart'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'requests\n| where name has \'chat/completions\'\n| summarize Requests = count(), AvgDurationMs = avg(duration), Failures = countif(resultCode != \'200\') by bin(timestamp, 1h)\n| render columnchart'
        size: 0
        title: 'Gateway request volume & failures'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'timechart'
      }
      name: 'query - requests'
    }
    {
      type: 1
      content: {
        json: '### MCP tool activity\nIdentity-scoped tool calls across the governed Pet Store, Math, and Entra User Data MCP servers.'
      }
      name: 'text - mcp activity'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'let departmentFilter = dynamic([{Department}]);\nlet userFilter = dynamic([{User}]);\ncustomMetrics\n| where name == \'MCP Tool Calls\'\n| extend department = tostring(customDimensions.department), user = tostring(customDimensions.user), userName = tostring(customDimensions.userName), server = tostring(customDimensions.server), tool = tostring(customDimensions.tool)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\',\'MCP\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| where array_length(departmentFilter) == 0 or department in (departmentFilter)\n| where array_length(userFilter) == 0 or Display in (userFilter)\n| summarize ToolCalls = sum(valueSum), Servers = dcount(server), Tools = dcount(tool), LastCall = max(timestamp) by department, user, UserName = userName\n| project department, user, UserName, ToolCalls, Servers, Tools, LastCall\n| order by ToolCalls desc'
        size: 0
        title: 'MCP tool calls by User'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
      }
      name: 'query - mcp by user'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: 'let departmentFilter = dynamic([{Department}]);\nlet userFilter = dynamic([{User}]);\ncustomMetrics\n| where name == \'MCP Tool Calls\'\n| extend department = tostring(customDimensions.department), user = tostring(customDimensions.user), userName = tostring(customDimensions.userName), server = tostring(customDimensions.server), tool = tostring(customDimensions.tool)\n| extend department = case(department in (\'Finance-Analytics\',\'ODI\',\'MCP\'), department, department has \'odi\', \'ODI\', department has \'fa\', \'Finance-Analytics\', department)\n| extend Display = iif(isnotempty(userName), strcat(userName, \'  (\', user, \')\'), user)\n| where array_length(departmentFilter) == 0 or department in (departmentFilter)\n| where array_length(userFilter) == 0 or Display in (userFilter)\n| summarize ToolCalls = sum(valueSum), UniqueUsers = dcount(user), LastCall = max(timestamp) by department, server, tool\n| project department, server, tool, ToolCalls, UniqueUsers, LastCall\n| order by ToolCalls desc'
        size: 0
        title: 'MCP usage by Server and Tool'
        timeContext: {
          durationMs: telemetryHistoryDurationMs
        }
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
      }
      name: 'query - mcp by tool'
    }
  ]
  fallbackResourceIds: [
    appInsightsId
  ]
  '$schema': 'https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json'
}

resource costWorkbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: workbookGuid
  location: location
  kind: 'shared'
  tags: tags
  properties: {
    displayName: displayName
    serializedData: string(workbookContent)
    category: 'workbook'
    sourceId: appInsightsId
  }
}

output id string = costWorkbook.id
output name string = costWorkbook.name
