#!/usr/bin/env python3
"""
call_ai_gateway_user.py

Example: call the AI Gateway (APIM) as the currently signed-in user,
using azure-identity's DefaultAzureCredential for the Entra ID token
(per-user attribution via the JWT `oid`/`roles` claims) plus an APIM
subscription key (per-department attribution via the Product scope).

DefaultAzureCredential will pick up your identity in this order (first
one that works wins): environment vars, managed identity, Azure CLI
login (`az login`), Azure PowerShell, VS Code / Visual Studio sign-in,
interactive browser (if enabled). In practice, for a developer running
this locally after `az login`, it uses your existing CLI session -
no extra code needed to get a real per-user token.

Requires:
    pip install azure-identity requests

Usage:
    python call_ai_gateway_user.py [department] ["your message"]

    department  "fa" (Finance-Analytics, default) or "odi"
"""
import sys
import requests
from azure.identity import DefaultAzureCredential

# ---- Fixed live-deployment identifiers (match bicep/scripts/test-ai-gateway-call.sh) ----
SUBSCRIPTION_ID = "0d04b43f-7d15-40fd-8aa5-830f71ab0d80"
RESOURCE_GROUP = "rg-ai-gateway-sea"
APIM_NAME = "apim-hub-sea2uy4dibzgdn34"
GATEWAY_URL = f"https://{APIM_NAME}.azure-api.net"
API_PATH = "openai"
DEPLOYMENT_NAME = "gpt-4o-hub-prod"
API_VERSION = "2024-08-01-preview"

# Entra ID app registration used for user-level attribution (App Roles).
# The APIM policy validates tokens issued for this app (api://<ENTRA_APP_ID>).
ENTRA_APP_ID = "e9de7c75-a166-4030-8c05-81694cc1fecb"

DEPARTMENT_PRODUCTS = {
    "fa": "product-fa",
    "odi": "product-odi",
}

# Pre-provisioned test subscription keys, one per department Product.
# In a real rollout each department/team would get its own key (never
# share keys across departments - the key IS the cost-attribution boundary
# alongside the user's Entra oid).
SUBSCRIPTION_KEYS = {
    "product-fa": "REPLACE_WITH_YOUR_PRODUCT_FA_SUBSCRIPTION_KEY",
    "product-odi": "REPLACE_WITH_YOUR_PRODUCT_ODI_SUBSCRIPTION_KEY",
}


def get_user_token() -> str:
    """Acquire a delegated (signed-in user) Entra ID access token.

    DefaultAzureCredential transparently reuses your `az login` session
    when run locally, so the token carries YOUR oid + roles claims -
    exactly what the gateway needs for per-user attribution.
    """
    credential = DefaultAzureCredential()
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

    print(f"== AI Gateway call (delegated user identity) ==")
    print(f"Department (product): {product_id}")
    print(f"Gateway:               {GATEWAY_URL}\n")

    print("-- Acquiring Entra ID token via DefaultAzureCredential (reuses az login)...")
    access_token = get_user_token()
    print("   token acquired (oid + roles claim will drive user/department attribution)\n")

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
          "your own Entra user name and oid.")


if __name__ == "__main__":
    dept = sys.argv[1] if len(sys.argv) > 1 else "fa"
    msg = sys.argv[2] if len(sys.argv) > 2 else "Say goodbye in exactly 3 words"
    call_gateway(dept, msg)
