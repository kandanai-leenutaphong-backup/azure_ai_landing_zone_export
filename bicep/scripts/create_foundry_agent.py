#!/usr/bin/env python3
"""
create_foundry_agent.py

Publish a persistent "Prompt Agent" to the AI Gateway hub's Azure AI Foundry
project (aif-hub-sea2uy4dibzgdn34 / aiGatewayHubProject) so it is visible and
manageable from the Foundry PORTAL (Agents blade) - then invoke that SAME
agent (by name/version, via the Responses API's `agent_reference`) through
the AI GATEWAY (APIM), so the call is logged with department/user cost
attribution in Application Insights / the cost workbook.

Why two DIFFERENT gateway paths are involved (read this before assuming
something is broken):

  1) Publishing (`AIProjectClient.agents.create_version`) talks DIRECTLY to
     the Foundry project control-plane. This is required - there is no way
     to "publish an agent" through APIM, Foundry's agent-management API is
     Foundry-native. This step makes the agent show up under Foundry Portal
     -> Agents, so anyone can open/edit/test it there.

  2) ACTUALLY INVOKING that exact published agent (not just replaying its
     instructions against the raw model) uses Foundry's Responses API
     (`{project}/openai/v1/responses` + `agent_reference: {name, version}`
     in the body) - a different host/path/schema than Chat Completions.
     The AI Gateway now proxies this too, via a SEPARATE APIM API
     (`ai-gateway-foundry-agents`, path `/agents`, operation `POST
     /responses`) added specifically for this - see
     bicep/modules/policies/api-agents-policy.xml and the
     `hub-foundry-agents-backend` APIM backend in bicep/modules/apim.bicep.
     Calling THIS path (via `invoke_published_agent_via_gateway` below) is
     what makes the SAME agent shown in Foundry Portal also show up with
     department/user/token attribution in the cost workbook.

  NOTE ON AN EARLIER VERSION OF THIS SCRIPT: a prior revision's
  "run_via_gateway" step did NOT call the created agent at all - it built a
  brand-new ad-hoc `agent_framework.Agent` with the same name/instructions
  and called it via `OpenAIChatCompletionClient` against the Chat
  Completions surface. That produced similar-looking output but was
  actually a different, disconnected code path from the published agent
  (same words, different resource). This version fixes that: the gateway
  call below references the PUBLISHED agent by name (and pinned version) via
  `agent_reference`, so it is verifiably the same agent object shown in
  Foundry Portal - not a lookalike.

  IMPORTANT PLATFORM LIMITATION (not fixable from Bicep/policy):
  If a human clicks "Try in playground" / "Test" inside the Foundry Portal
  UI for this agent, that traffic goes straight to the Foundry service and
  CANNOT be routed through our custom APIM gateway - Azure does not expose a
  way to force Foundry Portal's own playground through a customer-owned
  APIM instance. Those portal-native test calls ARE still metered by Azure
  (visible in the Cognitive Services account's own Azure Monitor metrics /
  Cost Management), but WITHOUT our custom department/user dimensions -
  Foundry has no concept of our Entra App Roles or APIM Products. Only
  calls made through the gateway (this script's
  `invoke_published_agent_via_gateway`, or any of the call_ai_gateway_*.py
  examples) get full department/user chargeback attribution in the cost
  workbook.

Requires:
    pip install agent-framework agent-framework-foundry azure-ai-projects \
        azure-identity openai

Usage:
    python create_foundry_agent.py [department] ["your message"]

    department  "fa" (Finance-Analytics, default) or "odi"
"""
import asyncio
import sys

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, to_prompt_agent
from azure.ai.projects.aio import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from openai import AsyncOpenAI

# ---- Fixed live-deployment identifiers (match the other bicep/scripts/*.py examples) ----
PROJECT_ENDPOINT = "https://aif-hub-sea2uy4dibzgdn34.services.ai.azure.com/api/projects/aiGatewayHubProject"
GATEWAY_URL = "https://apim-hub-sea2uy4dibzgdn34.azure-api.net"
# Separate gateway API/path (added specifically for agent invocation) - distinct from the
# `openai` path used by the other call_ai_gateway_*.py examples' Chat Completions calls.
# NOTE: unlike calling Foundry directly (base_url ends in "/openai/v1"), our APIM operation
# already forwards straight to the backend's "/openai/v1/responses" path, so the external
# gateway path is just "/agents" + "/responses" (the OpenAI SDK appends "/responses" itself).
AGENTS_API_BASE = f"{GATEWAY_URL}/agents"
DEPLOYMENT_NAME = "gpt-4o-hub-prod"

# Entra ID app registration used for user-level attribution (App Roles).
# The APIM policy validates tokens issued for this app (api://<ENTRA_APP_ID>).
ENTRA_APP_ID = "e9de7c75-a166-4030-8c05-81694cc1fecb"

DEPARTMENT_PRODUCTS = {
    "fa": "product-fa",
    "odi": "product-odi",
}

# Pre-provisioned test subscription keys, one per department Product. The SAME key works
# for both the `openai` (Chat Completions) and `agents` (Responses/agent invocation) APIs -
# both are attached to the same department Product in bicep/modules/apim.bicep.
# Never share keys across departments - the key IS part of the cost-attribution boundary
# alongside the caller's Entra oid.
SUBSCRIPTION_KEYS = {
    "product-fa": "REPLACE_WITH_YOUR_PRODUCT_FA_SUBSCRIPTION_KEY",
    "product-odi": "REPLACE_WITH_YOUR_PRODUCT_ODI_SUBSCRIPTION_KEY",
}

AGENT_NAME = "AIGatewayFoundryDemoAgent"
AGENT_DESCRIPTION = "Demo agent published to Foundry Portal; production calls go through the AI Gateway."
AGENT_INSTRUCTIONS = "You are a helpful, concise assistant."


async def publish_to_foundry_portal() -> str:
    """Publishes/updates the agent as a persistent Prompt Agent so it shows
    up in Foundry Portal -> Agents. Talks directly to the Foundry project -
    this call itself is NOT gateway-routed and will not appear in our cost
    workbook (it is a control-plane/definition call, not token usage).
    Returns the published version string, needed to pin the exact agent
    version invoked later via agent_reference."""
    async with AsyncDefaultAzureCredential() as credential:
        # FoundryChatClient here is only used to build a PromptAgentDefinition
        # (model + instructions) for publishing - it is not used to run
        # any actual chat turns in this script.
        foundry_client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=DEPLOYMENT_NAME,
            credential=credential,
        )
        agent = Agent(
            client=foundry_client,
            name=AGENT_NAME,
            description=AGENT_DESCRIPTION,
            instructions=AGENT_INSTRUCTIONS,
        )

        async with AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project_client:
            created = await project_client.agents.create_version(
                agent_name=agent.name,
                definition=to_prompt_agent(agent),
                description=agent.description,
            )
            print(f"Published '{created.name}' v{created.version} to Foundry Portal.")
            print(f"View it at: Foundry Portal -> {PROJECT_ENDPOINT.split('/api/')[0]} -> Agents -> {created.name}\n")
            return created.version


def make_token_provider():
    """Callable that mints a fresh Entra ID token for the signed-in user on
    each call, carrying THEIR oid + roles claims for gateway attribution."""
    credential = DefaultAzureCredential()

    def token_provider() -> str:
        return credential.get_token(f"{ENTRA_APP_ID}/.default").token

    return token_provider


async def invoke_published_agent_via_gateway(department: str, message: str, agent_version: str) -> None:
    """Invokes the EXACT published agent (by name + version, via
    `agent_reference`) through the AI Gateway's `/agents` API (Responses API
    surface, NOT Chat Completions) - so this really is a call to the
    Foundry-Portal-visible agent, logged with department/user token-usage
    attribution in Application Insights / the cost workbook."""
    product_id = DEPARTMENT_PRODUCTS.get(department)
    if not product_id:
        raise SystemExit(f"Unknown department '{department}' (expected 'fa' or 'odi')")

    subscription_key = SUBSCRIPTION_KEYS.get(product_id)
    if not subscription_key or subscription_key.startswith("REPLACE_WITH"):
        raise SystemExit(
            f"Set a real APIM subscription key for {product_id} in SUBSCRIPTION_KEYS "
            f"(see bicep/scripts/test-ai-gateway-call.sh for how to create/fetch one via az rest)."
        )

    print(f"== Invoking published agent '{AGENT_NAME}' v{agent_version} through the AI Gateway (cost-tracked) ==")
    print(f"Department (product): {product_id}")
    print(f"Gateway agents API:    {AGENTS_API_BASE}\n")

    token_provider = make_token_provider()

    # Point the OpenAI SDK's Responses client at the gateway's `/agents` path (instead of the
    # Foundry project directly) and swap the bearer token for our own Entra app's token, so
    # APIM's JWT validation + department/user attribution applies.
    client = AsyncOpenAI(
        base_url=AGENTS_API_BASE,
        api_key=token_provider(),
        default_headers={"Ocp-Apim-Subscription-Key": subscription_key},
    )

    print(f"User: {message}")
    response = await client.responses.create(
        input=message,
        # agent_reference tells the Responses API which published Foundry agent - and which
        # exact version - to run. This is what makes the call provably hit the SAME agent
        # object visible in Foundry Portal, not a recreated lookalike. `extra_body` is the
        # openai-python SDK's mechanism for merging extra fields into the JSON request body
        # root (NOT a nested "extra_body" wrapper in the actual HTTP payload).
        extra_body={"agent_reference": {"name": AGENT_NAME, "type": "agent_reference", "version": agent_version}},
    )
    print(f"Agent: {response.output_text}")
    print(f"Usage: {response.usage}")
    print("\nDone. This call is logged in App Insights/the cost workbook under your "
          "own Entra user name and oid, plus the department dimension above.\n"
          "Reminder: testing this SAME agent from inside the Foundry Portal UI "
          "playground will NOT appear here - see the module docstring for why.")


async def main() -> None:
    department = sys.argv[1] if len(sys.argv) > 1 else "fa"
    message = sys.argv[2] if len(sys.argv) > 2 else "Say hello in exactly 3 words"

    agent_version = await publish_to_foundry_portal()
    await invoke_published_agent_via_gateway(department, message, agent_version)


if __name__ == "__main__":
    asyncio.run(main())
