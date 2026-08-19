#!/usr/bin/env bash

set -euo pipefail

subscription_id="${1:-1b00124c-ed9b-4d33-9bd6-4d14c09c9857}"
resource_group="${2:-rg-hub-sea}"
gateway_name="${3:-hub-VNetGw-sea-dev}"
output_file="${4:-vpn-client-profile.zip}"

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI is required. Install it and run 'az login' before retrying." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download the generated VPN profile." >&2
  exit 1
fi

provisioning_state="$(
  az network vnet-gateway show \
    --subscription "$subscription_id" \
    --resource-group "$resource_group" \
    --name "$gateway_name" \
    --query provisioningState \
    --output tsv \
    --only-show-errors
)"

if [[ "$provisioning_state" != "Succeeded" ]]; then
  echo "VPN gateway provisioning state is '$provisioning_state'; expected 'Succeeded'." >&2
  exit 1
fi

profile_url="$(
  az network vnet-gateway vpn-client generate \
    --subscription "$subscription_id" \
    --resource-group "$resource_group" \
    --name "$gateway_name" \
    --output tsv \
    --only-show-errors
)"

if [[ "$profile_url" != https://* ]]; then
  echo "Azure did not return a valid VPN client profile URL." >&2
  exit 1
fi

curl --fail --location --output "$output_file" "$profile_url"
echo "VPN client profile downloaded to: $output_file"
