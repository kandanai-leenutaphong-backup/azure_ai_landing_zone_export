#!/usr/bin/env python3
"""
call_ai_gateway_agent_user.py

Example: run a basic Microsoft Agent Framework agent (`agent_framework.Agent`)
whose model calls go through the AI Gateway (APIM), authenticated as the
CURRENTLY SIGNED-IN USER via `DefaultAzureCredential` - same identity model
as call_ai_gateway_user.py, but using the Agent Framework's `Agent` +
`OpenAIChatCompletionClient` abstraction instead of raw `requests` calls.

Modeled after the Agent Framework "basic agent" pattern, e.g.:
https://github.com/edsml-kl121/TH-azure-ai-workshop-2027/blob/main/LAB_1_basic_agent/03_azure_ai_basic.py
adapted here to route through our APIM gateway (instead of Foundry directly),
so per-user/per-department cost attribution still applies.

Requires:
    pip install agent-framework agent-framework-openai azure-identity

Usage:
    python call_ai_gateway_agent_user.py [department] ["your message"]

    department  "fa" (Finance-Analytics, default) or "odi"
"""
import asyncio
import sys

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import DefaultAzureCredential

# ---- Fixed live-deployment identifiers (match bicep/scripts/test-ai-gateway-call.sh) ----
GATEWAY_URL = "https://apim-hub-sea2uy4dibzgdn34.azure-api.net"
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


def make_token_provider():
    """Returns a callable that mints a fresh Entra ID token for the signed-in
    user on each call. DefaultAzureCredential reuses your `az login` session
    when run locally, so the token carries YOUR oid + roles claims - exactly
    what the gateway needs for per-user attribution."""
    credential = DefaultAzureCredential()

    def token_provider() -> str:
        return credential.get_token(f"{ENTRA_APP_ID}/.default").token

    return token_provider


async def main() -> None:
    department = sys.argv[1] if len(sys.argv) > 1 else "fa"
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

    print("== AI Gateway Agent call (delegated user identity) ==")
    print(f"Department (product): {product_id}")
    print(f"Gateway:               {GATEWAY_URL}\n")

    print("-- Acquiring Entra ID token via DefaultAzureCredential (reuses az login)...")
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
          "your own Entra user name and oid.")


if __name__ == "__main__":
    asyncio.run(main())
