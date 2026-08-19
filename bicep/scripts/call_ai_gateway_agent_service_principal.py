#!/usr/bin/env python3
"""
call_ai_gateway_agent_service_principal.py

Example: run a basic Microsoft Agent Framework agent (`agent_framework.Agent`)
whose model calls go through the AI Gateway (APIM), authenticated as a
SERVICE PRINCIPAL (app-only, client-credentials flow) via
`ClientSecretCredential` - same identity model as
call_ai_gateway_service_principal.py, but using the Agent Framework's
`Agent` + `OpenAIChatCompletionClient` abstraction instead of raw
`requests` calls.

Modeled after the Agent Framework "basic agent" pattern, e.g.:
https://github.com/edsml-kl121/TH-azure-ai-workshop-2027/blob/main/LAB_1_basic_agent/03_azure_ai_basic.py
adapted here to route through our APIM gateway (instead of Foundry directly),
so per-user/per-department cost attribution still applies. Use this when the
caller is a headless job/service (not an interactive user) - e.g. a batch
pipeline, an automation runbook, a CI job.

Requires:
    pip install agent-framework agent-framework-openai azure-identity

Setup (one-time, per service principal): see the header comment in
call_ai_gateway_service_principal.py for how to create the app
registration/service principal/secret and assign it an Entra App Role.

Usage:
    export AI_GATEWAY_SVC_CLIENT_ID="<app id>"
    export AI_GATEWAY_SVC_CLIENT_SECRET="<client secret>"
    python call_ai_gateway_agent_service_principal.py [department] ["your message"]

    department  "fa" (Finance-Analytics) or "odi" (default)
"""
import asyncio
import os
import subprocess
import sys

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import ClientSecretCredential

# ---- Fixed live-deployment identifiers (match bicep/scripts/test-ai-gateway-call.sh) ----
GATEWAY_URL = "https://apim-hub-sea2uy4dibzgdn34.azure-api.net"
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
    # Developer convenience fallback to the local az CLI's tenant - in
    # CI/production, always set AZURE_TENANT_ID explicitly instead.
    result = subprocess.run(
        ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def make_token_provider():
    """Returns a callable that mints a fresh app-only Entra ID token for the
    service principal on each call. Unlike a delegated user token, this is
    NOT subject to Azure AD's per-session role-claim caching, so a newly
    assigned App Role shows up immediately in the next token minted."""
    client_id = os.environ.get("AI_GATEWAY_SVC_CLIENT_ID")
    client_secret = os.environ.get("AI_GATEWAY_SVC_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set AI_GATEWAY_SVC_CLIENT_ID and AI_GATEWAY_SVC_CLIENT_SECRET "
            "environment variables for the service principal to use."
        )

    credential = ClientSecretCredential(
        tenant_id=get_tenant_id(),
        client_id=client_id,
        client_secret=client_secret,
    )

    def token_provider() -> str:
        return credential.get_token(f"{ENTRA_APP_ID}/.default").token

    return token_provider


async def main() -> None:
    department = sys.argv[1] if len(sys.argv) > 1 else "odi"
    message = sys.argv[2] if len(sys.argv) > 2 else "Say goodbye in exactly 3 words"

    product_id = DEPARTMENT_PRODUCTS.get(department)
    if not product_id:
        raise SystemExit(f"Unknown department '{department}' (expected 'fa' or 'odi')")

    subscription_key = SUBSCRIPTION_KEYS.get(product_id)
    if not subscription_key or subscription_key.startswith("REPLACE_WITH"):
        raise SystemExit(
            f"Set a real APIM subscription key for {product_id} in SUBSCRIPTION_KEYS "
            f"(see bicep/scripts/test-ai-gateway-call.sh for how to create/fetch one via az rest)."
        )

    print("== AI Gateway Agent call (service principal / client-credentials) ==")
    print(f"Department (product): {product_id}")
    print(f"Gateway:               {GATEWAY_URL}\n")

    print("-- Acquiring app-only Entra ID token via ClientSecretCredential...")
    token_provider = make_token_provider()

    # NOTE: azure_endpoint must be the gateway ROOT (no "/openai" suffix) -
    # the OpenAI SDK's Azure client appends "/openai/deployments/{model}/..."
    # itself, so including "/openai" here would double it up and 404.
    client = OpenAIChatCompletionClient(
        model=DEPLOYMENT_NAME,
        azure_endpoint=GATEWAY_URL,
        api_version=API_VERSION,
        credential=token_provider,
        default_headers={"Ocp-Apim-Subscription-Key": subscription_key},
    )

    agent = Agent(
        client=client,
        name="AIGatewayDemoAgent",
        description="A basic demo agent that answers questions via the AI Gateway.",
        instructions="You are a helpful, concise assistant.",
    )

    print(f"User: {message}")
    result = await agent.run(message)
    print(f"Agent: {result}")

    print("\nDone. This call will show up in App Insights/the cost workbook under "
          "'service-principal:<client-id>' as the user, and the SP's own oid.")


if __name__ == "__main__":
    asyncio.run(main())
