#!/usr/bin/env python3
"""
call_ai_gateway_service_principal.py

Example: call the AI Gateway (APIM) as a service principal (app-only,
client-credentials flow) using azure-identity's ClientSecretCredential.

Use this when the caller is a headless job/service (not an interactive
user) - e.g. a batch pipeline, an automation runbook, a CI job. The
token's `oid` claim is the SERVICE PRINCIPAL's own identity (not a
human user), so cost/usage will attribute to that service principal.
Combine with the App Role assignment on the service principal (instead
of on a user) to get clean department attribution for automated callers.

Requires:
    pip install azure-identity requests

Setup (one-time, per service principal):
    1. Create an app registration + service principal (see
       bicep/scripts/test-ai-gateway-call.sh header comments for the
       equivalent az/Graph calls), OR reuse an existing one like
       "ai-gateway-caller-odi-svc".
    2. Create a client secret for it.
    3. Assign it the relevant Entra App Role (Finance-Analytics / ODI)
       on the "ai-gateway-caller" app registration's service principal,
       via Microsoft Graph:
         POST /v1.0/servicePrincipals/{resourceSpObjectId}/appRoleAssignedTo
         { "principalId": "<your-sp-object-id>",
           "resourceId": "<ai-gateway-caller-sp-object-id>",
           "appRoleId": "<role-guid>" }
    4. Set the env vars below (or hardcode for a quick local test - never
       commit real secrets to git).

Usage:
    export AI_GATEWAY_SVC_CLIENT_ID="<app id>"
    export AI_GATEWAY_SVC_CLIENT_SECRET="<client secret>"
    python call_ai_gateway_service_principal.py [department] ["your message"]

    department  "fa" (Finance-Analytics) or "odi" (default)
"""
import os
import sys
import requests
from azure.identity import ClientSecretCredential

# ---- Fixed live-deployment identifiers (match bicep/scripts/test-ai-gateway-call.sh) ----
TENANT_ID_FALLBACK = None  # if not set via env, we resolve it via `az account show` below
SUBSCRIPTION_ID = "0d04b43f-7d15-40fd-8aa5-830f71ab0d80"
RESOURCE_GROUP = "rg-ai-gateway-sea"
APIM_NAME = "apim-hub-sea2uy4dibzgdn34"
GATEWAY_URL = f"https://{APIM_NAME}.azure-api.net"
API_PATH = "openai"
DEPLOYMENT_NAME = "gpt-4o-hub-prod"
API_VERSION = "2024-08-01-preview"

# Entra ID app registration used for user/service-level attribution (App Roles).
ENTRA_APP_ID = "e9de7c75-a166-4030-8c05-81694cc1fecb"

DEPARTMENT_PRODUCTS = {
    "fa": "product-fa",
    "odi": "product-odi",
}

SUBSCRIPTION_KEYS = {
    "product-fa": "REPLACE_WITH_YOUR_PRODUCT_FA_SUBSCRIPTION_KEY",
    "product-odi": "REPLACE_WITH_YOUR_PRODUCT_ODI_SUBSCRIPTION_KEY",
}


def get_tenant_id() -> str:
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    if tenant_id:
        return tenant_id
    # Fall back to whatever tenant the local az CLI is logged into, purely
    # as a developer convenience - in CI/production, always set
    # AZURE_TENANT_ID explicitly instead of relying on this.
    import subprocess
    result = subprocess.run(
        ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def get_service_principal_token() -> str:
    """Acquire an app-only (client-credentials) Entra ID access token.

    Unlike a delegated user token, this is NOT subject to Azure AD's
    per-session role-claim caching, so a newly assigned App Role shows
    up immediately in the next token you mint.
    """
    client_id = os.environ.get("AI_GATEWAY_SVC_CLIENT_ID")
    client_secret = os.environ.get("AI_GATEWAY_SVC_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set AI_GATEWAY_SVC_CLIENT_ID and AI_GATEWAY_SVC_CLIENT_SECRET "
            "environment variables for the service principal to use."
        )

    tenant_id = get_tenant_id()
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    token = credential.get_token(f"{ENTRA_APP_ID}/.default")
    return token.token


def call_gateway(department: str, message: str) -> None:
    product_id = DEPARTMENT_PRODUCTS.get(department)
    if not product_id:
        raise SystemExit(f"Unknown department '{department}' (expected 'fa' or 'odi')")

    subscription_key = SUBSCRIPTION_KEYS.get(product_id)
    if not subscription_key or subscription_key.startswith("REPLACE_WITH"):
        raise SystemExit(
            f"Set a real APIM subscription key for {product_id} in SUBSCRIPTION_KEYS "
            f"(see bicep/scripts/test-ai-gateway-call.sh for how to create/fetch one via az rest)."
        )

    print("== AI Gateway call (service principal / client-credentials) ==")
    print(f"Department (product): {product_id}")
    print(f"Gateway:               {GATEWAY_URL}\n")

    print("-- Acquiring app-only Entra ID token via ClientSecretCredential...")
    access_token = get_service_principal_token()
    print("   token acquired (oid = service principal's own object id; "
          "roles claim reflects the SP's own App Role assignment, no caching delay)\n")

    url = f"{GATEWAY_URL}/{API_PATH}/deployments/{DEPLOYMENT_NAME}/chat/completions"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {"messages": [{"role": "user", "content": message}]}

    print(f"-- Calling POST {url}?api-version={API_VERSION} ...")
    response = requests.post(url, headers=headers, json=body, params={"api-version": API_VERSION}, timeout=60)

    print(f"HTTP status: {response.status_code}")
    try:
        print(response.json())
    except ValueError:
        print(response.text)

    response.raise_for_status()
    print("\nDone. This call will show up in App Insights/the cost workbook under "
          "'service-principal:<client-id>' as the user, and the SP's own oid.")


if __name__ == "__main__":
    dept = sys.argv[1] if len(sys.argv) > 1 else "odi"
    msg = sys.argv[2] if len(sys.argv) > 2 else "Say goodbye in exactly 3 words"
    call_gateway(dept, msg)
