#!/usr/bin/env bash
# Start the hub WAF Application Gateway through the repo's deploy entry point, then prove
# the app is reachable from outside. Idempotent: a Running gateway is left untouched.
set -euo pipefail

ENVIRONMENT="${1:-sea}"
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
ENV_FILE="$ROOT/deploy/env/$ENVIRONMENT.env"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 2; }
value() { grep "^$1=" "$ENV_FILE" | cut -d= -f2-; }

HUB_SUB="$(value HUB_SUBSCRIPTION_ID)"
HUB_RG="$(value HUB_RESOURCE_GROUP)"
GATEWAY="$(value GATEWAY)"
HOST="$(value PUBLIC_HOST)"

echo "Before: $(az network application-gateway show --subscription "$HUB_SUB" -g "$HUB_RG" -n "$GATEWAY" \
  --query operationalState -o tsv --only-show-errors)"

# Who stopped it last (best effort, last 7 days).
az monitor activity-log list --subscription "$HUB_SUB" -g "$HUB_RG" --offset 7d --only-show-errors \
  --query "[?contains(operationName.value,'applicationGateways/stop') && status.value=='Succeeded'] | [0].{stoppedAt:eventTimestamp,by:caller}" \
  -o tsv 2>/dev/null | sed 's/^/Last stop: /' || true

bash "$ROOT/deploy/deploy.sh" -e "$ENVIRONMENT" start-gateway

for attempt in 1 2 3 4 5 6; do
  code="$(curl -s -m 15 -o /dev/null -w '%{http_code}' "https://$HOST/healthz" || true)"
  echo "https://$HOST/healthz -> $code"
  [ "$code" = "200" ] && exit 0
  sleep 20
done
echo "Gateway reports Running but $HOST is not serving; run: bash deploy/deploy.sh -e $ENVIRONMENT verify" >&2
exit 1
