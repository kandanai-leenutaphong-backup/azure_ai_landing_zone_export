#!/usr/bin/env bash
set -euo pipefail

HUB_SUBSCRIPTION_ID="1b00124c-ed9b-4d33-9bd6-4d14c09c9857"
SPOKE_SUBSCRIPTION_ID="d88c020a-2180-43da-91a2-f6cc01f25946"
AI_GATEWAY_SUBSCRIPTION_ID="0d04b43f-7d15-40fd-8aa5-830f71ab0d80"

if ! command -v az >/dev/null 2>&1; then
  printf 'Azure CLI is required. Install az, sign in, and run this script again.\n' >&2
  exit 1
fi

if ! az account show --only-show-errors >/dev/null 2>&1; then
  printf 'Azure CLI is not authenticated. Run az login and try again.\n' >&2
  exit 1
fi

print_scope() {
  local role="$1"
  local subscription_id="$2"
  local resource_group="$3"

  local subscription_name
  subscription_name="$(az account show \
    --subscription "$subscription_id" \
    --query name \
    --output tsv \
    --only-show-errors)"

  printf '\n## %s\n\n' "$role"
  printf -- '- Subscription: `%s`\n' "$subscription_name"
  printf -- '- Subscription ID: `%s`\n' "$subscription_id"
  printf -- '- Resource group: `%s`\n' "$resource_group"

  az group show \
    --subscription "$subscription_id" \
    --name "$resource_group" \
    --query '{location:location,provisioningState:properties.provisioningState}' \
    --output table \
    --only-show-errors

  printf '\n### Virtual network\n\n'
  az network vnet list \
    --subscription "$subscription_id" \
    --resource-group "$resource_group" \
    --query '[].{name:name,addressSpace:join(`, `, addressSpace.addressPrefixes)}' \
    --output table \
    --only-show-errors

  printf '\n### Subnets\n\n'
  az network vnet list \
    --subscription "$subscription_id" \
    --resource-group "$resource_group" \
    --query '[].subnets[].{name:name,prefix:addressPrefix}' \
    --output table \
    --only-show-errors

  printf '\n### Peerings\n\n'
  az network vnet list \
    --subscription "$subscription_id" \
    --resource-group "$resource_group" \
    --query '[].virtualNetworkPeerings[].{name:name,state:peeringState,remoteVnet:remoteVirtualNetwork.id}' \
    --output table \
    --only-show-errors

  printf '\n### Top-level resources\n\n'
  az resource list \
    --subscription "$subscription_id" \
    --resource-group "$resource_group" \
    --query "[?!contains(name, '/') && type!='Microsoft.Network/networkInterfaces' && type!='Microsoft.Compute/disks' && type!='Microsoft.EventGrid/systemTopics'].{name:name,type:type,location:location}" \
    --output table \
    --only-show-errors
}

printf '# Live Azure AI Landing Zone Summary\n\n'
printf 'Generated: `%s`\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

print_scope "Connectivity hub" "$HUB_SUBSCRIPTION_ID" "rg-hub-sea"
print_scope "Workload spoke" "$SPOKE_SUBSCRIPTION_ID" "rg-ai-dev-sea"
print_scope "AI Gateway hub" "$AI_GATEWAY_SUBSCRIPTION_ID" "rg-ai-gateway-sea"

