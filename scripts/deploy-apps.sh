#!/usr/bin/env bash

set -euo pipefail

spoke_subscription_id="${SPOKE_SUBSCRIPTION_ID:-d88c020a-2180-43da-91a2-f6cc01f25946}"
spoke_resource_group="${SPOKE_RESOURCE_GROUP:-rg-ai-dev-sea}"
orchestration_subscription_id="${ORCHESTRATION_SUBSCRIPTION_ID:-$spoke_subscription_id}"
location="${LOCATION:-southeastasia}"
image_tag="${1:-$(date -u +%Y%m%d%H%M%S)}"
ssh_public_key_file="${SSH_PUBLIC_KEY_FILE:-$HOME/.ssh/id_rsa.pub}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$ssh_public_key_file" ]]; then
  echo "SSH public key not found: $ssh_public_key_file" >&2
  exit 1
fi

ssh_key="$(cat "$ssh_public_key_file")"

acr_name="$(
  az acr list \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --query '[0].name' \
    --output tsv \
    --only-show-errors 2>/dev/null || true
)"

if [[ -z "$acr_name" ]]; then
  echo "No Azure Container Registry found. Bootstrapping landing zone infrastructure..."
  az deployment sub create \
    --subscription "$orchestration_subscription_id" \
    --name main \
    --location "$location" \
    --template-file "$repo_root/bicep/main.bicep" \
    --parameters "$repo_root/bicep/parameters/main.bicepparam" \
    --parameters location="$location" \
                 spokeSubscriptionId="$spoke_subscription_id" \
                 spokeResourceGroupName="$spoke_resource_group" \
                 deployRepositoryApps=false \
                 deployThaiSurnameApp=false \
                 sshPublicKeyVm1="$ssh_key" \
                 sshPublicKeyVm2="$ssh_key" \
    --only-show-errors

  acr_name="$(
    az acr list \
      --subscription "$spoke_subscription_id" \
      --resource-group "$spoke_resource_group" \
      --query '[0].name' \
      --output tsv \
      --only-show-errors
  )"
fi

if [[ -z "$acr_name" ]]; then
  echo "Azure Container Registry bootstrap failed in $spoke_resource_group." >&2
  exit 1
fi

az acr build \
  --subscription "$spoke_subscription_id" \
  --registry "$acr_name" \
  --image "ping-url:$image_tag" \
  "$repo_root/applications/ping-url" \
  --only-show-errors

az acr build \
  --subscription "$spoke_subscription_id" \
  --registry "$acr_name" \
  --image "azure-ocr-service:$image_tag" \
  "$repo_root/applications/azure-ocr-service" \
  --only-show-errors

az acr build \
  --subscription "$spoke_subscription_id" \
  --registry "$acr_name" \
  --image "thai-surname-search:$image_tag" \
  "$repo_root/applications/thai-surname-search" \
  --only-show-errors

az deployment sub create \
  --subscription "$orchestration_subscription_id" \
  --name main \
  --location "$location" \
  --template-file "$repo_root/bicep/main.bicep" \
  --parameters "$repo_root/bicep/parameters/main.bicepparam" \
  --parameters location="$location" \
               spokeSubscriptionId="$spoke_subscription_id" \
               spokeResourceGroupName="$spoke_resource_group" \
               appImageTag="$image_tag" \
               deployRepositoryApps=true \
               deployThaiSurnameApp=false \
               sshPublicKeyVm1="$ssh_key" \
               sshPublicKeyVm2="$ssh_key" \
  --only-show-errors

for obsolete_app in fe-app-ai fe-app-ai-2; do
  if az containerapp show \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --name "$obsolete_app" \
    --only-show-errors \
    --output none 2>/dev/null; then
    az containerapp delete \
      --subscription "$spoke_subscription_id" \
      --resource-group "$spoke_resource_group" \
      --name "$obsolete_app" \
      --yes \
      --only-show-errors
  fi
done

sql_server="$(
  az sql server list \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --query "[?starts_with(name, 'sql-thai-search-sea-')].fullyQualifiedDomainName | [0]" \
    --output tsv \
    --only-show-errors
)"

if [[ -z "$sql_server" ]]; then
  echo "Thai surname Azure SQL server was not found." >&2
  exit 1
fi

bootstrap_venv="$(mktemp -d)/venv"
python3 -m venv "$bootstrap_venv"
"$bootstrap_venv/bin/pip" install --quiet azure-identity certifi python-tds 'pyOpenSSL>=24.2,<26' 'psycopg[binary]>=3.1,<4'
identity_client_id="$(
  az identity show \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --name "uami-container-apps" \
    --query clientId \
    --output tsv \
    --only-show-errors
)"
identity_principal_id="$(
  az identity show \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --name "uami-container-apps" \
    --query principalId \
    --output tsv \
    --only-show-errors
)"
"$bootstrap_venv/bin/python" "$repo_root/scripts/bootstrap-thai-sql.py" \
  --server "$sql_server" \
  --database "thai-search-db" \
  --identity-name "uami-container-apps" \
  --identity-client-id "$identity_client_id"

pool_database="$(
  az sql db list \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --server "$(echo "$sql_server" | cut -d. -f1)" \
    --query "[?elasticPoolName != null].name | [0]" \
    --output tsv \
    --only-show-errors 2>/dev/null || true
)"
if [[ -n "$pool_database" ]]; then
  "$bootstrap_venv/bin/python" "$repo_root/scripts/bootstrap-thai-sql.py" \
    --server "$sql_server" \
    --database "$pool_database" \
    --identity-name "uami-container-apps" \
    --identity-client-id "$identity_client_id"
fi

postgres_server="$(
  az postgres flexible-server list \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --query "[?starts_with(name, 'pg-thai-search-sea-')].fullyQualifiedDomainName | [0]" \
    --output tsv \
    --only-show-errors 2>/dev/null || true
)"
if [[ -n "$postgres_server" ]]; then
  postgres_server_name="$(echo "$postgres_server" | cut -d. -f1)"
  postgres_database="$(
    az postgres flexible-server db list \
      --subscription "$spoke_subscription_id" \
      --resource-group "$spoke_resource_group" \
      --server-name "$postgres_server_name" \
      --query "[?name=='thai-search-pg-db'].name | [0]" \
      --output tsv \
      --only-show-errors
  )"
  admin_login="$(
    az postgres flexible-server microsoft-entra-admin list \
      --subscription "$spoke_subscription_id" \
      --resource-group "$spoke_resource_group" \
      --server-name "$postgres_server_name" \
      --query "[0].principalName" \
      --output tsv \
      --only-show-errors
  )"
  # Allowlist the pg_trgm extension used by the PostgreSQL fuzzy search tab.
  az postgres flexible-server parameter set \
    --subscription "$spoke_subscription_id" \
    --resource-group "$spoke_resource_group" \
    --server-name "$postgres_server_name" \
    --name azure.extensions \
    --value PG_TRGM \
    --only-show-errors
  "$bootstrap_venv/bin/python" "$repo_root/scripts/bootstrap-thai-postgres.py" \
    --server "$postgres_server" \
    --database "${postgres_database:-thai-search-pg-db}" \
    --admin-login "$admin_login" \
    --identity-name "uami-container-apps" \
    --identity-principal-id "$identity_principal_id"
fi

az deployment sub create \
  --subscription "$orchestration_subscription_id" \
  --name main \
  --location "$location" \
  --template-file "$repo_root/bicep/main.bicep" \
  --parameters "$repo_root/bicep/parameters/main.bicepparam" \
  --parameters location="$location" \
               spokeSubscriptionId="$spoke_subscription_id" \
               spokeResourceGroupName="$spoke_resource_group" \
               appImageTag="$image_tag" \
               deployRepositoryApps=true \
               deployThaiSurnameApp=true \
               sshPublicKeyVm1="$ssh_key" \
               sshPublicKeyVm2="$ssh_key" \
  --only-show-errors

public_url="$(
  az deployment sub show \
    --subscription "$orchestration_subscription_id" \
    --name main \
    --query properties.outputs.thaiSearchPublicUrl.value \
    --output tsv \
    --only-show-errors
)"

if [[ -n "$public_url" ]]; then
  echo "Thai surname public WAF endpoint: $public_url"
fi
