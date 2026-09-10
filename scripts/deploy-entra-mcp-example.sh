#!/usr/bin/env bash
set -euo pipefail

APP_SUBSCRIPTION_ID="${APP_SUBSCRIPTION_ID:-d88c020a-2180-43da-91a2-f6cc01f25946}"
APP_RESOURCE_GROUP="${APP_RESOURCE_GROUP:-rg-ai-dev-sea}"
CONTAINER_APPS_ENVIRONMENT="${CONTAINER_APPS_ENVIRONMENT:-capps-env-sea}"
ACR_NAME="${ACR_NAME:-acrappseaozewfizfnaft4}"
ACR_PULL_IDENTITY_NAME="${ACR_PULL_IDENTITY_NAME:-uami-container-apps}"
ENTRA_APP_NAME="${ENTRA_APP_NAME:-MCP User Data API}"
ENTRA_APP_NAME_FILTER="${ENTRA_APP_NAME//\'/\'\'}"
AZURE_CLI_APP_ID="04b07795-8ddb-461a-bbee-02f9e1bf7b46"

GATEWAY_SUBSCRIPTION_ID="${GATEWAY_SUBSCRIPTION_ID:-0d04b43f-7d15-40fd-8aa5-830f71ab0d80}"
GATEWAY_RESOURCE_GROUP="${GATEWAY_RESOURCE_GROUP:-rg-ai-gateway-sea}"
APIM_NAME="${APIM_NAME:-apim-hub-sea2uy4dibzgdn34}"
APIM_API_VERSION="${APIM_API_VERSION:-2025-09-01-preview}"

APP_NAME="${APP_NAME:-entra-user-data-api}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo local)-$(date +%Y%m%d%H%M%S)}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TENANT_ID="$(az account show --query tenantId -o tsv)"
ENTRA_APP_OBJECT_ID="$(az ad app list --filter "displayName eq '${ENTRA_APP_NAME_FILTER}'" --query '[0].id' -o tsv)"

if [[ -z "$ENTRA_APP_OBJECT_ID" ]]; then
  ENTRA_APP_OBJECT_ID="$(az ad app create --display-name "$ENTRA_APP_NAME" --sign-in-audience AzureADMyOrg --query id -o tsv)"
fi

ENTRA_APP_ID="$(az ad app show --id "$ENTRA_APP_OBJECT_ID" --query appId -o tsv)"
ENTRA_AUDIENCE="api://${ENTRA_APP_ID}"
SCOPE_ID="$(az rest --method get --url "https://graph.microsoft.com/v1.0/applications/${ENTRA_APP_OBJECT_ID}" \
  --query "api.oauth2PermissionScopes[?value=='access_as_user'].id | [0]" -o tsv)"

if [[ -z "$SCOPE_ID" ]]; then
  SCOPE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
fi

APP_API_BODY="$(jq -n \
  --arg identifier_uri "$ENTRA_AUDIENCE" \
  --arg scope_id "$SCOPE_ID" \
  '{
    identifierUris: [$identifier_uri],
    api: {
      requestedAccessTokenVersion: 2,
      oauth2PermissionScopes: [{
        id: $scope_id,
        adminConsentDescription: "Allow this client to read data belonging to the signed-in user.",
        adminConsentDisplayName: "Read signed-in user data",
        isEnabled: true,
        type: "User",
        userConsentDescription: "Allow this client to read your demo user data.",
        userConsentDisplayName: "Read your demo user data",
        value: "access_as_user"
      }]
    }
  }')"

az rest --method patch \
  --url "https://graph.microsoft.com/v1.0/applications/${ENTRA_APP_OBJECT_ID}" \
  --headers "Content-Type=application/json" \
  --body "$APP_API_BODY" >/dev/null

PREAUTHORIZED_APP_BODY="$(jq \
  --arg cli_app_id "$AZURE_CLI_APP_ID" \
  --arg scope_id "$SCOPE_ID" \
  '.api.preAuthorizedApplications = [{appId:$cli_app_id,delegatedPermissionIds:[$scope_id]}]' \
  <<<"$APP_API_BODY")"

az rest --method patch \
  --url "https://graph.microsoft.com/v1.0/applications/${ENTRA_APP_OBJECT_ID}" \
  --headers "Content-Type=application/json" \
  --body "$PREAUTHORIZED_APP_BODY" >/dev/null

if ! az ad sp show --id "$ENTRA_APP_ID" >/dev/null 2>&1; then
  az ad sp create --id "$ENTRA_APP_ID" >/dev/null
fi

ACR_LOGIN_SERVER="$(az acr show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$ACR_NAME" --query loginServer -o tsv)"
IDENTITY_ID="$(az identity show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$ACR_PULL_IDENTITY_NAME" --query id -o tsv)"

az acr build \
  --subscription "$APP_SUBSCRIPTION_ID" \
  --registry "$ACR_NAME" \
  --image "mcp-examples/entra-user-data-api:${IMAGE_TAG}" \
  "$ROOT_DIR/applications/mcp-examples/entra-user-data-api"

if az containerapp show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$APP_NAME" >/dev/null 2>&1; then
  az containerapp update \
    --subscription "$APP_SUBSCRIPTION_ID" \
    --resource-group "$APP_RESOURCE_GROUP" \
    --name "$APP_NAME" \
    --image "$ACR_LOGIN_SERVER/mcp-examples/entra-user-data-api:${IMAGE_TAG}" \
    --min-replicas 0 \
    --max-replicas 1 >/dev/null
else
  az containerapp create \
    --subscription "$APP_SUBSCRIPTION_ID" \
    --resource-group "$APP_RESOURCE_GROUP" \
    --name "$APP_NAME" \
    --environment "$CONTAINER_APPS_ENVIRONMENT" \
    --image "$ACR_LOGIN_SERVER/mcp-examples/entra-user-data-api:${IMAGE_TAG}" \
    --user-assigned "$IDENTITY_ID" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --registry-identity "$IDENTITY_ID" \
    --ingress external \
    --target-port 8002 \
    --transport auto \
    --cpu 0.5 \
    --memory 1Gi \
    --min-replicas 0 \
    --max-replicas 1 >/dev/null
fi

APP_FQDN="$(az containerapp show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)"

az apim api import \
  --subscription "$GATEWAY_SUBSCRIPTION_ID" \
  --resource-group "$GATEWAY_RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id user-data-api \
  --path user-data \
  --display-name "Entra User Data API" \
  --protocols https \
  --service-url "https://${APP_FQDN}" \
  --specification-format OpenApiJson \
  --specification-path "$ROOT_DIR/applications/mcp-examples/entra-user-data-api/openapi.json"

az apim api update \
  --subscription "$GATEWAY_SUBSCRIPTION_ID" \
  --resource-group "$GATEWAY_RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id user-data-api \
  --subscription-required false >/dev/null

TOKEN="$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)"
APIM_BASE_URL="https://management.azure.com/subscriptions/${GATEWAY_SUBSCRIPTION_ID}/resourceGroups/${GATEWAY_RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}"
MCP_POLICY_FILE="$ROOT_DIR/bicep/modules/policies/mcp-policy.xml"

put_apim_resource() {
  local url="$1"
  local body="$2"
  curl --fail --silent --show-error --request PUT "$url" \
    --header "Authorization: Bearer ${TOKEN}" \
    --header "Content-Type: application/json" \
    --header "If-Match: *" \
    --data "$body" >/dev/null
}

curl --fail --silent --show-error --request DELETE \
  "${APIM_BASE_URL}/apis/user-data-mcp?api-version=${APIM_API_VERSION}" \
  --header "Authorization: Bearer $TOKEN" \
  --header "If-Match: *" >/dev/null 2>&1 || true

put_apim_resource \
  "${APIM_BASE_URL}/apis/user-data-mcp?api-version=${APIM_API_VERSION}" \
  "{\"properties\":{\"type\":\"http\",\"path\":\"user-data-mcp\",\"displayName\":\"Entra User Data MCP Server\",\"description\":\"Transparent authenticated proxy to the private native MCP server.\",\"protocols\":[\"https\"],\"subscriptionRequired\":false,\"serviceUrl\":\"https://${APP_FQDN}\"}}"

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error \
    "${APIM_BASE_URL}/apis/user-data-mcp?api-version=${APIM_API_VERSION}" \
    --header "Authorization: Bearer ${TOKEN}" >/dev/null; then
    break
  fi
  sleep 10
done

for method in POST GET DELETE; do
  operation_id="mcp-$(tr '[:upper:]' '[:lower:]' <<<"$method")"
  put_apim_resource \
    "${APIM_BASE_URL}/apis/user-data-mcp/operations/${operation_id}?api-version=2024-05-01" \
    "{\"properties\":{\"displayName\":\"MCP ${method}\",\"method\":\"${method}\",\"urlTemplate\":\"/mcp\",\"templateParameters\":[],\"responses\":[]}}"
done

for api_id in user-data-api user-data-mcp; do
  curl --fail --silent --show-error --request PUT \
    "${APIM_BASE_URL}/products/product-fa/apis/${api_id}?api-version=2024-05-01" \
    --header "Authorization: Bearer ${TOKEN}" \
    --header "Content-Length: 0" >/dev/null
done

JWT_POLICY="<policies><inbound><validate-jwt header-name=\"Authorization\" failed-validation-httpcode=\"401\" failed-validation-error-message=\"A valid Microsoft Entra access token is required.\" require-expiration-time=\"true\" require-scheme=\"Bearer\" output-token-variable-name=\"validated-jwt\"><openid-config url=\"https://login.microsoftonline.com/${TENANT_ID}/v2.0/.well-known/openid-configuration\" /><audiences><audience>${ENTRA_APP_ID}</audience><audience>${ENTRA_AUDIENCE}</audience></audiences><required-claims><claim name=\"scp\" match=\"any\"><value>access_as_user</value></claim></required-claims></validate-jwt><set-header name=\"X-Entra-Object-Id\" exists-action=\"override\"><value>@(((Jwt)context.Variables[\"validated-jwt\"]).Claims.GetValueOrDefault(\"oid\", \"\"))</value></set-header><set-header name=\"X-Entra-Display-Name\" exists-action=\"override\"><value>@(((Jwt)context.Variables[\"validated-jwt\"]).Claims.GetValueOrDefault(\"name\", \"\"))</value></set-header><set-header name=\"X-Entra-Username\" exists-action=\"override\"><value>@(((Jwt)context.Variables[\"validated-jwt\"]).Claims.GetValueOrDefault(\"preferred_username\", \"\"))</value></set-header><rate-limit-by-key calls=\"30\" renewal-period=\"60\" counter-key=\"@(((Jwt)context.Variables[\"validated-jwt\"]).Claims.GetValueOrDefault(\"oid\", context.Request.IpAddress))\" /><base /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>"
JWT_BODY="$(jq -n --arg value "$JWT_POLICY" '{properties:{format:"rawxml",value:$value}}')"

put_apim_resource \
  "${APIM_BASE_URL}/namedValues/mcp-entra-audience?api-version=2024-05-01" \
  "$(jq -n --arg value "$ENTRA_APP_ID" '{properties:{displayName:"mcp-entra-audience",value:$value,secret:false}}')"
put_apim_resource \
  "${APIM_BASE_URL}/namedValues/mcp-allowed-origin?api-version=2024-05-01" \
  "$(jq -n --arg value "https://apic-hub-sea2uy4dibzgdn34.portal.centralindia.azure-apicenter.ms" '{properties:{displayName:"mcp-allowed-origin",value:$value,secret:false}}')"

put_apim_resource \
  "${APIM_BASE_URL}/apis/user-data-api/policies/policy?api-version=${APIM_API_VERSION}" \
  "$JWT_BODY"

MCP_POLICY_BODY="$(jq -n --rawfile value "$MCP_POLICY_FILE" '{properties:{format:"rawxml",value:$value}}')"
put_apim_resource \
  "${APIM_BASE_URL}/apis/user-data-mcp/policies/policy?api-version=${APIM_API_VERSION}" \
  "$MCP_POLICY_BODY"

APP_INSIGHTS_LOGGER_ID="${APIM_BASE_URL#https://management.azure.com}/loggers/appinsights-logger"
MCP_DIAGNOSTICS_BODY="$(jq -n --arg loggerId "$APP_INSIGHTS_LOGGER_ID" '{properties:{loggerId:$loggerId,alwaysLog:"allErrors",verbosity:"information",metrics:true,httpCorrelationProtocol:"W3C"}}')"
for api_id in user-data-mcp; do
  put_apim_resource \
    "${APIM_BASE_URL}/apis/${api_id}/diagnostics/applicationinsights?api-version=2024-05-01" \
    "$MCP_DIAGNOSTICS_BODY"
done

GATEWAY_URL="$(az apim show --subscription "$GATEWAY_SUBSCRIPTION_ID" --resource-group "$GATEWAY_RESOURCE_GROUP" --name "$APIM_NAME" --query gatewayUrl -o tsv)"
printf 'Entra application client ID: %s\n' "$ENTRA_APP_ID"
printf 'Delegated scope: %s/access_as_user\n' "$ENTRA_AUDIENCE"
printf 'Private Entra User Data MCP backend: https://%s/mcp\n' "$APP_FQDN"
printf 'Entra User Data MCP: %s/user-data-mcp/mcp\n' "$GATEWAY_URL"
