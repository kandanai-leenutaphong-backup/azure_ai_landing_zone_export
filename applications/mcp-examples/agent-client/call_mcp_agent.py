import argparse
import asyncio
import json
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

DEFAULT_GATEWAY = "https://apim-hub-sea2uy4dibzgdn34.azure-api.net"
DEFAULT_ALLOWED_ORIGIN = "https://apic-hub-sea2uy4dibzgdn34.portal.centralindia.azure-apicenter.ms"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the deployed MCP servers through an Agent Framework agent.")
    parser.add_argument(
        "--prompt",
        default=(
            "Use the tools to calculate 18 * 7, list the pets, then retrieve my Entra profile "
            "and my orders. Clearly identify which data came from my authenticated identity."
        ),
    )
    return parser.parse_args()


async def get_azure_cli_scope_token(scope: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "az",
        "account",
        "get-access-token",
        "--scope",
        scope,
        "--output",
        "json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode().strip() or "Azure CLI token acquisition failed"
        raise RuntimeError(message)
    return str(json.loads(stdout)["accessToken"])


async def main() -> None:
    args = parse_args()
    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    entra_scope = os.environ["MCP_ENTRA_SCOPE"]
    gateway = os.getenv("MCP_GATEWAY_URL", DEFAULT_GATEWAY).rstrip("/")
    allowed_origin = os.getenv("MCP_ALLOWED_ORIGIN", DEFAULT_ALLOWED_ORIGIN)

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=project_endpoint, credential=credential) as project_client,
    ):
        access_token = os.getenv("MCP_ENTRA_ACCESS_TOKEN")
        if not access_token:
            access_token = await get_azure_cli_scope_token(entra_scope)

        authenticated_headers = lambda _context: {
            "Authorization": f"Bearer {access_token}",
            "Origin": allowed_origin,
        }
        tools = [
            MCPStreamableHTTPTool(
                name="Pet Store MCP",
                tool_name_prefix="pet",
                url=f"{gateway}/petstore-mcp/mcp",
                header_provider=authenticated_headers,
            ),
            MCPStreamableHTTPTool(
                name="Math MCP",
                tool_name_prefix="math",
                url=f"{gateway}/math-mcp/mcp",
                header_provider=authenticated_headers,
            ),
            MCPStreamableHTTPTool(
                name="Entra User Data MCP",
                tool_name_prefix="user",
                url=f"{gateway}/user-data-mcp/mcp",
                header_provider=authenticated_headers,
            ),
        ]
        client = FoundryChatClient(project_client=project_client, model=model)
        async with Agent(
            client=client,
            name="GovernedMcpAgent",
            instructions=(
                "Use the governed MCP tools when relevant. User profile and order data must only come "
                "from the Entra User Data MCP tool. Never infer another user's data or identity."
            ),
            tools=tools,
        ) as agent:
            result = await agent.run(args.prompt)
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
