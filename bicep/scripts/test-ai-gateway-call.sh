#!/usr/bin/env bash
# test-ai-gateway-call.sh
#
# Reusable end-to-end test for the AI Gateway: acquires a real Entra ID user
# token (for per-user attribution) AND an APIM subscription key scoped to a
# department Product (for per-department attribution), then calls the
# gateway's OpenAI-compatible chat/completions route through APIM, and
# optionally verifies the call shows up in Application Insights custom
# metrics and the usage-audit Event Hub.
#
# Usage:
#   ./test-ai-gateway-call.sh [department] [message] [--verify]
#
#   department  "fa" (Finance-Analytics, default) or "odi"
#   message     the user chat prompt (default: a short greeting)
#   --verify    also query App Insights + Event Hub metrics after the call
#
# Requires: az CLI logged in as a user who (a) can read/manage the APIM
# instance below and (b) has been assigned the matching Entra ID App Role
# (Finance-Analytics / ODI) on the "ai-gateway-caller" app registration.
#
# NOTE on department switching: department attribution comes from the
# caller's Entra ID `roles` claim, and Azure AD can take a while (observed
# up to ~10+ min, and per Microsoft's own docs up to ~1 hour in some cases)
# to reflect a NEW app-role assignment in freshly-issued DELEGATED (user)
# tokens due to SSO/session caching. If you need to test a second
# department immediately without waiting on that cache, use a dedicated
# service-principal (client-credentials) caller instead - app-only tokens
# are not subject to this caching since there's no SSO session involved.
# Set these two env vars to use that path for a given department:
#   AI_GATEWAY_SVC_CLIENT_ID=<app id of the department's service principal>
#   AI_GATEWAY_SVC_CLIENT_SECRET=<its client secret>
# (A pre-created example exists for ODI: appId 0772edff-803f-43cb-9c5d-b4c7bd6537e8,
#  secret stored securely - ask whoever set it up, never commit it to git.)
#
# All resource names/IDs below match the live deployment in subscription
# 0d04b43f-7d15-40fd-8aa5-830f71ab0d80, resource group rg-ai-gateway-sea.
set -euo pipefail

# ---- Fixed live-deployment identifiers ------------------------------------
SUBSCRIPTION_ID="0d04b43f-7d15-40fd-8aa5-830f71ab0d80"
RESOURCE_GROUP="rg-ai-gateway-sea"
APIM_NAME="apim-hub-sea2uy4dibzgdn34"
GATEWAY_URL="https://${APIM_NAME}.azure-api.net"
API_PATH="openai"
DEPLOYMENT_NAME="gpt-4o-hub-prod"
API_VERSION="2024-08-01-preview"
APPINSIGHTS_APP="appi-apim-sea"
EVENTHUB_NAMESPACE="evhns-hub-sea-2uy4dibzgdn34"

# Entra ID app registration used for user-level attribution (App Roles).
ENTRA_APP_ID="e9de7c75-a166-4030-8c05-81694cc1fecb"

# ---- Args ------------------------------------------------------------------
DEPARTMENT="${1:-fa}"
MESSAGE="${2:-Say goodbye in exactly 3 words}"
DO_VERIFY="${3:-}"

case "$DEPARTMENT" in
  fa)  PRODUCT_ID="product-fa"  ;;
  odi) PRODUCT_ID="product-odi" ;;
  *) echo "Unknown department '$DEPARTMENT' (expected 'fa' or 'odi')" >&2; exit 1 ;;
esac

echo "== AI Gateway test call =="
echo "Department (product): $PRODUCT_ID"
echo "Gateway:               $GATEWAY_URL"
echo

# ---- 1. Acquire a real Entra ID access token --------------------------------
if [[ -n "${AI_GATEWAY_SVC_CLIENT_ID:-}" && -n "${AI_GATEWAY_SVC_CLIENT_SECRET:-}" ]]; then
  echo "-- Acquiring an app-only (client-credentials) token for service principal ${AI_GATEWAY_SVC_CLIENT_ID}..."
  TENANT_ID=$(az account show --query tenantId -o tsv)
  TOKEN_RESPONSE=$(curl -s -X POST "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token" \
    -d "grant_type=client_credentials" \
    -d "client_id=${AI_GATEWAY_SVC_CLIENT_ID}" \
    -d "client_secret=${AI_GATEWAY_SVC_CLIENT_SECRET}" \
    -d "scope=api://${ENTRA_APP_ID}/.default")
  ENTRA_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import json,sys;print(json.load(sys.stdin).get('access_token',''))")
  echo "   app-only token acquired (roles claim reflects the service principal's own App Role assignment - not cached per-user, so it's immediate)"
else
  echo "-- Acquiring Entra ID token for the signed-in user (az account get-access-token)..."
  ENTRA_TOKEN=$(az account get-access-token --resource "$ENTRA_APP_ID" --query accessToken -o tsv)
  echo "   token acquired (oid + roles claim will drive user/department attribution)"
fi
if [[ -z "$ENTRA_TOKEN" ]]; then
  echo "Failed to acquire an Entra ID token. Make sure you're logged in with 'az login'" >&2
  echo "and that your user/service-principal has been assigned an App Role on ai-gateway-caller." >&2
  exit 1
fi

# ---- 2. Get-or-create an APIM subscription key for the department product --
echo "-- Ensuring an APIM subscription key exists for product '$PRODUCT_ID'..."
SUB_NAME="sub-${PRODUCT_ID}-test"
SUB_RESOURCE="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/subscriptions/${SUB_NAME}"

EXISTING=$(az rest --method get --url "${SUB_RESOURCE}?api-version=2023-05-01-preview" 2>/dev/null || true)
if [[ -z "$EXISTING" ]]; then
  az rest --method put --url "${SUB_RESOURCE}?api-version=2023-05-01-preview" \
    --body "{\"properties\":{\"displayName\":\"${SUB_NAME}\",\"scope\":\"/products/${PRODUCT_ID}\",\"state\":\"active\"}}" \
    -o none
  # Brand-new subscription keys take a few seconds to propagate to the APIM
  # gateway runtime cache - without this wait the very first call can fail
  # with a misleading "invalid subscription key" 401 even though the key is
  # valid and active.
  echo "   new subscription created - waiting 20s for key to propagate..."
  sleep 20
fi
SUB_KEY=$(az rest --method post --url "${SUB_RESOURCE}/listSecrets?api-version=2023-05-01-preview" --query primaryKey -o tsv)
echo "   subscription key ready: ${SUB_KEY:0:8}... (product: ${PRODUCT_ID})"
echo

# ---- 3. Call the gateway -----------------------------------------------------
echo "-- Calling POST /${API_PATH}/deployments/${DEPLOYMENT_NAME}/chat/completions ..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "${GATEWAY_URL}/${API_PATH}/deployments/${DEPLOYMENT_NAME}/chat/completions?api-version=${API_VERSION}" \
  -H "Ocp-Apim-Subscription-Key: ${SUB_KEY}" \
  -H "Authorization: Bearer ${ENTRA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"${MESSAGE}\"}]}")

HTTP_STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP status: $HTTP_STATUS"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "Call failed - see response above." >&2
  exit 1
fi

# ---- 4. Optional: verify logs ------------------------------------------------
if [[ "$DO_VERIFY" == "--verify" || "${2:-}" == "--verify" ]]; then
  echo "-- Waiting ~2 minutes for telemetry ingestion..."
  sleep 120

  echo "-- Application Insights customMetrics (llm-usage, last 15 min):"
  az monitor app-insights query --app "$APPINSIGHTS_APP" --resource-group "$RESOURCE_GROUP" \
    --subscription "$SUBSCRIPTION_ID" \
    --analytics-query "customMetrics | where timestamp > ago(15m) | where name in ('Total Tokens','Prompt Tokens','Completion Tokens') | order by timestamp desc | project timestamp, name, valueSum, department=tostring(customDimensions.department), user=tostring(customDimensions.user), deployment=tostring(customDimensions.deployment)" \
    -o table 2>&1 || echo "   (query failed - check az monitor app-insights extension is installed)"

  echo
  echo "-- Event Hub (${EVENTHUB_NAMESPACE}) incoming message count (last 15 min):"
  az monitor metrics list \
    --resource "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.EventHub/namespaces/${EVENTHUB_NAMESPACE}" \
    --metric "IncomingMessages" --interval PT5M --aggregation Total -o table 2>&1 || true
fi

echo
echo "Done. Department attribution = ${PRODUCT_ID}; user attribution = Entra oid claim in the token above."
