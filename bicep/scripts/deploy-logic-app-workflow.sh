#!/usr/bin/env bash
# Zip-deploys the usage-rollup workflow content to logic-hub-usage-sea<suffix> (Logic Apps Standard).
#
# Logic Apps Standard workflow *definitions* cannot be deployed as Bicep resources (unlike
# Consumption Logic Apps) — the Standard host/plan is deployed by
# modules/logic-app-standard.bicep, and the actual /workflows/<name>/workflow.json content
# must be pushed separately via zip deploy, exactly like Azure Functions code. Run this
# script once after `az deployment sub create` has created the Logic App Standard site.
#
# Usage:
#   ./deploy-logic-app-workflow.sh <resource-group> <logic-app-name> [subscription-id]
#
# Requires: az cli, zip.

set -euo pipefail

RESOURCE_GROUP="${1:?Usage: $0 <resource-group> <logic-app-name> [subscription-id]}"
LOGIC_APP_NAME="${2:?Usage: $0 <resource-group> <logic-app-name> [subscription-id]}"
SUBSCRIPTION_ID="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_DIR="$SCRIPT_DIR/../logic-app-workflows"
ZIP_PATH="$(mktemp -d)/logic-hub-usage-workflows.zip"

echo "Packaging workflow content from $WORKFLOWS_DIR ..."
(cd "$WORKFLOWS_DIR" && zip -r -q "$ZIP_PATH" host.json connections.json usage-rollup)

AZ_ARGS=(--resource-group "$RESOURCE_GROUP" --name "$LOGIC_APP_NAME" --src "$ZIP_PATH")
if [[ -n "$SUBSCRIPTION_ID" ]]; then
  AZ_ARGS+=(--subscription "$SUBSCRIPTION_ID")
fi

echo "Deploying $ZIP_PATH to $LOGIC_APP_NAME in $RESOURCE_GROUP ..."
az webapp deploy --type zip "${AZ_ARGS[@]}"

echo "Done. Verify the 'usage-rollup' workflow appears under $LOGIC_APP_NAME > Workflows in the portal."
