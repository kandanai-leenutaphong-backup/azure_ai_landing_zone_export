#!/usr/bin/env bash
set -euo pipefail

APP_SUBSCRIPTION_ID="${APP_SUBSCRIPTION_ID:-d88c020a-2180-43da-91a2-f6cc01f25946}"
APP_RESOURCE_GROUP="${APP_RESOURCE_GROUP:-rg-ai-dev-sea}"
CONTAINER_APPS_ENVIRONMENT="${CONTAINER_APPS_ENVIRONMENT:-capps-env-sea}"
ACR_NAME="${ACR_NAME:-acrappseaozewfizfnaft4}"
ACR_PULL_IDENTITY_NAME="${ACR_PULL_IDENTITY_NAME:-uami-container-apps}"

GATEWAY_SUBSCRIPTION_ID="${GATEWAY_SUBSCRIPTION_ID:-0d04b43f-7d15-40fd-8aa5-830f71ab0d80}"
GATEWAY_RESOURCE_GROUP="${GATEWAY_RESOURCE_GROUP:-rg-ai-gateway-sea}"
APIM_NAME="${APIM_NAME:-apim-hub-sea2uy4dibzgdn34}"
APIM_API_VERSION="${APIM_API_VERSION:-2025-09-01-preview}"
API_CENTER_NAME="${API_CENTER_NAME:-apic-hub-sea2uy4dibzgdn34}"
API_CENTER_PORTAL_ORIGIN="${API_CENTER_PORTAL_ORIGIN:-https://${API_CENTER_NAME}.portal.centralindia.azure-apicenter.ms}"

PET_APP_NAME="${PET_APP_NAME:-petstore-mcp-api}"
MATH_APP_NAME="${MATH_APP_NAME:-math-mcp-server}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo local)-$(date +%Y%m%d%H%M%S)}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! az apic integration create apim --help >/dev/null 2>&1; then
  az extension add --name apic-extension --upgrade --allow-preview true --yes >/dev/null
fi

ACR_LOGIN_SERVER="$(az acr show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$ACR_NAME" --query loginServer -o tsv)"
IDENTITY_ID="$(az identity show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$ACR_PULL_IDENTITY_NAME" --query id -o tsv)"

az acr build \
  --subscription "$APP_SUBSCRIPTION_ID" \
  --registry "$ACR_NAME" \
  --image "mcp-examples/petstore-api:${IMAGE_TAG}" \
  "$ROOT_DIR/applications/mcp-examples/petstore-api"

az acr build \
  --subscription "$APP_SUBSCRIPTION_ID" \
  --registry "$ACR_NAME" \
  --image "mcp-examples/math-mcp-server:${IMAGE_TAG}" \
  "$ROOT_DIR/applications/mcp-examples/math-mcp-server"

deploy_container_app() {
  local name="$1"
  local image="$2"
  local port="$3"

  if az containerapp show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$name" >/dev/null 2>&1; then
    az containerapp update \
      --subscription "$APP_SUBSCRIPTION_ID" \
      --resource-group "$APP_RESOURCE_GROUP" \
      --name "$name" \
      --image "$image" \
      --min-replicas 0 \
      --max-replicas 1
  else
    az containerapp create \
      --subscription "$APP_SUBSCRIPTION_ID" \
      --resource-group "$APP_RESOURCE_GROUP" \
      --name "$name" \
      --environment "$CONTAINER_APPS_ENVIRONMENT" \
      --image "$image" \
      --user-assigned "$IDENTITY_ID" \
      --registry-server "$ACR_LOGIN_SERVER" \
      --registry-identity "$IDENTITY_ID" \
      --ingress external \
      --target-port "$port" \
      --transport auto \
      --cpu 0.5 \
      --memory 1Gi \
      --min-replicas 0 \
      --max-replicas 1
  fi
}

deploy_container_app "$PET_APP_NAME" "$ACR_LOGIN_SERVER/mcp-examples/petstore-api:${IMAGE_TAG}" 8000
deploy_container_app "$MATH_APP_NAME" "$ACR_LOGIN_SERVER/mcp-examples/math-mcp-server:${IMAGE_TAG}" 8001

PET_FQDN="$(az containerapp show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$PET_APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)"
MATH_FQDN="$(az containerapp show --subscription "$APP_SUBSCRIPTION_ID" --resource-group "$APP_RESOURCE_GROUP" --name "$MATH_APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)"

OPENAPI_FILE="$ROOT_DIR/applications/mcp-examples/petstore-api/openapi.json"
MATH_OPENAPI_FILE="$ROOT_DIR/applications/mcp-examples/math-mcp-server/openapi.json"

az apim api import \
  --subscription "$GATEWAY_SUBSCRIPTION_ID" \
  --resource-group "$GATEWAY_RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id petstore-api \
  --path pets \
  --display-name "Pet Store API" \
  --protocols https \
  --service-url "https://${PET_FQDN}" \
  --specification-format OpenApiJson \
  --specification-path "$OPENAPI_FILE"

az apim api import \
  --subscription "$GATEWAY_SUBSCRIPTION_ID" \
  --resource-group "$GATEWAY_RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id math-tools-api \
  --path math-tools \
  --display-name "Math and Text Tools API" \
  --protocols https \
  --service-url "https://${MATH_FQDN}" \
  --specification-format OpenApiJson \
  --specification-path "$MATH_OPENAPI_FILE"

for api_id in petstore-api math-tools-api; do
  az apim api update \
    --subscription "$GATEWAY_SUBSCRIPTION_ID" \
    --resource-group "$GATEWAY_RESOURCE_GROUP" \
    --service-name "$APIM_NAME" \
    --api-id "$api_id" \
    --subscription-required false >/dev/null
done

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

wait_for_apim_api() {
  local api_id="$1"
  local state

  for _ in $(seq 1 30); do
    state="$(curl --fail --silent --show-error \
      "${APIM_BASE_URL}/apis/${api_id}?api-version=${APIM_API_VERSION}" \
      --header "Authorization: Bearer ${TOKEN}" | jq -r '.properties.provisioningState // "Succeeded"')"
    if [[ "$state" == "Succeeded" ]]; then
      return
    fi
    if [[ "$state" == "Failed" ]]; then
      echo "APIM API ${api_id} provisioning failed" >&2
      exit 1
    fi
    sleep 10
  done

  echo "Timed out waiting for APIM API ${api_id}" >&2
  exit 1
}

put_apim_resource \
  "${APIM_BASE_URL}/apis/petstore-mcp?api-version=${APIM_API_VERSION}" \
  '{"properties":{"type":"mcp","path":"petstore-mcp","displayName":"Pet Store MCP Server","description":"Pet Store REST operations exposed as MCP tools.","protocols":["https"],"subscriptionRequired":false}}'
wait_for_apim_api petstore-mcp

for operation in listPets getPet createPet; do
  operation_resource_id="${APIM_BASE_URL#https://management.azure.com}/apis/petstore-api/operations/${operation}"
  put_apim_resource \
    "${APIM_BASE_URL}/apis/petstore-mcp/tools/${operation}?api-version=${APIM_API_VERSION}" \
    "{\"properties\":{\"displayName\":\"${operation}\",\"description\":\"Pet Store ${operation} operation\",\"operationId\":\"${operation_resource_id}\"}}"
done

curl --fail --silent --show-error --request DELETE \
  "${APIM_BASE_URL}/apis/math-mcp?api-version=${APIM_API_VERSION}" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "If-Match: *" >/dev/null 2>&1 || true

put_apim_resource \
  "${APIM_BASE_URL}/apis/math-mcp?api-version=${APIM_API_VERSION}" \
  '{"properties":{"type":"mcp","path":"math-mcp","displayName":"Math and Text MCP Server","description":"Math and text REST operations exposed as MCP tools.","protocols":["https"],"subscriptionRequired":false}}'
wait_for_apim_api math-mcp

for operation in calculate fibonacci isPrime textTransform; do
  operation_resource_id="${APIM_BASE_URL#https://management.azure.com}/apis/math-tools-api/operations/${operation}"
  put_apim_resource \
    "${APIM_BASE_URL}/apis/math-mcp/tools/${operation}?api-version=${APIM_API_VERSION}" \
    "{\"properties\":{\"displayName\":\"${operation}\",\"description\":\"Math and Text ${operation} operation\",\"operationId\":\"${operation_resource_id}\"}}"
done

for api_id in petstore-api petstore-mcp math-tools-api math-mcp; do
  curl --fail --silent --show-error --request PUT \
    "${APIM_BASE_URL}/products/product-fa/apis/${api_id}?api-version=2024-05-01" \
    --header "Authorization: Bearer ${TOKEN}" \
    --header "Content-Length: 0" >/dev/null
done

MCP_ENTRA_AUDIENCE="$(az rest --method get \
  --url "${APIM_BASE_URL}/namedValues/mcp-entra-audience?api-version=2024-05-01" \
  --query properties.value -o tsv 2>/dev/null || true)"
if [[ -z "$MCP_ENTRA_AUDIENCE" ]]; then
  echo "MCP Entra authentication is not configured. Run ./scripts/deploy-entra-mcp-example.sh first." >&2
  exit 1
fi

put_apim_resource \
  "${APIM_BASE_URL}/namedValues/mcp-allowed-origin?api-version=2024-05-01" \
  "$(jq -n --arg value "$API_CENTER_PORTAL_ORIGIN" '{properties:{displayName:"mcp-allowed-origin",value:$value,secret:false}}')"

MCP_POLICY_BODY="$(jq -n --rawfile value "$MCP_POLICY_FILE" '{properties:{format:"rawxml",value:$value}}')"
APP_INSIGHTS_LOGGER_ID="${APIM_BASE_URL#https://management.azure.com}/loggers/appinsights-logger"
MCP_DIAGNOSTICS_BODY="$(jq -n --arg loggerId "$APP_INSIGHTS_LOGGER_ID" '{properties:{loggerId:$loggerId,alwaysLog:"allErrors",verbosity:"information",metrics:true,httpCorrelationProtocol:"W3C"}}')"

for api_id in petstore-mcp math-mcp; do
  put_apim_resource \
    "${APIM_BASE_URL}/apis/${api_id}/policies/policy?api-version=${APIM_API_VERSION}" \
    "$MCP_POLICY_BODY"
  put_apim_resource \
    "${APIM_BASE_URL}/apis/${api_id}/diagnostics/applicationinsights?api-version=2024-05-01" \
    "$MCP_DIAGNOSTICS_BODY"
done

BACKING_API_POLICY="<policies><inbound><choose><when condition='@(context.Request.Headers.GetValueOrDefault(\"Origin\", \"\") != \"${API_CENTER_PORTAL_ORIGIN}\")'><return-response><set-status code=\"403\" reason=\"Forbidden\" /></return-response></when></choose><cors allow-credentials=\"false\" terminate-unmatched-request=\"true\"><allowed-origins><origin>${API_CENTER_PORTAL_ORIGIN}</origin></allowed-origins><allowed-methods preflight-result-max-age=\"300\"><method>GET</method><method>POST</method><method>OPTIONS</method></allowed-methods><allowed-headers><header>accept</header><header>content-type</header></allowed-headers></cors><rate-limit-by-key calls=\"30\" renewal-period=\"60\" counter-key=\"@(context.Request.IpAddress)\" /><base /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>"
BACKING_API_BODY="$(jq -n --arg value "$BACKING_API_POLICY" '{properties:{format:"rawxml",value:$value}}')"

for api_id in petstore-api math-tools-api; do
  put_apim_resource \
    "${APIM_BASE_URL}/apis/${api_id}/policies/policy?api-version=${APIM_API_VERSION}" \
    "$BACKING_API_BODY"
done

if az apic show \
  --subscription "$GATEWAY_SUBSCRIPTION_ID" \
  --resource-group "$GATEWAY_RESOURCE_GROUP" \
  --name "$API_CENTER_NAME" >/dev/null 2>&1; then
  if ! az apic integration show \
    --subscription "$GATEWAY_SUBSCRIPTION_ID" \
    --resource-group "$GATEWAY_RESOURCE_GROUP" \
    --service-name "$API_CENTER_NAME" \
    --integration-name ai-gateway-apim >/dev/null 2>&1; then
    az apic integration create apim \
      --subscription "$GATEWAY_SUBSCRIPTION_ID" \
      --resource-group "$GATEWAY_RESOURCE_GROUP" \
      --service-name "$API_CENTER_NAME" \
      --integration-name ai-gateway-apim \
      --azure-apim "$APIM_NAME"
  fi
fi

GATEWAY_URL="$(az apim show --subscription "$GATEWAY_SUBSCRIPTION_ID" --resource-group "$GATEWAY_RESOURCE_GROUP" --name "$APIM_NAME" --query gatewayUrl -o tsv)"

printf 'Pet Store backend: https://%s\n' "$PET_FQDN"
printf 'Math MCP backend: https://%s/mcp\n' "$MATH_FQDN"
printf 'Pet Store MCP: %s/petstore-mcp/mcp\n' "$GATEWAY_URL"
printf 'Math MCP: %s/math-mcp/mcp\n' "$GATEWAY_URL"
