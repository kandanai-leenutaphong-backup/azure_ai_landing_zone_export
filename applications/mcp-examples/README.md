# MCP examples

This folder contains three governed MCP examples and an Agent Framework client:

- `petstore-api`: a FastAPI REST service imported into Azure API Management and exported as an MCP server.
- `math-mcp-server`: a native streamable-HTTP MCP server with a REST facade. APIM exports the REST operations as a governed MCP server while the native `/mcp/` endpoint remains available inside the private network.
- `entra-user-data-api`: an Entra-protected API exported as MCP tools. APIM validates the delegated user token and injects immutable user claims so each identity receives only its own deterministic demo profile and orders.
- `agent-client`: a Python Agent Framework client that gives one Foundry-backed agent access to all three deployed MCP servers.

All three workloads deploy to the existing internal Container Apps environment in `rg-ai-dev-sea`. API Management reaches them through direct gateway-to-spoke peering and the Container Apps private DNS zone.

Run `./scripts/deploy-mcp-examples.sh` from the repository root to build both images, deploy the Container Apps, import/register the APIs in APIM, and synchronize them into API Center.

The two MCP front doors are intentionally keyless demo endpoints so the API Center browser test console can connect. They allow only the API Center portal origin in browser CORS and are limited to 30 calls per minute per client IP. Their backing REST APIs reject requests without the same portal origin. Production MCP servers should use OAuth 2.1 protected-resource metadata instead.

Run `./scripts/deploy-entra-mcp-example.sh` to create the delegated Entra scope, deploy the user-data Container App, and register its REST and MCP APIs in APIM. Then run the Agent Framework client:

```bash
cd applications/mcp-examples/agent-client
cp .env.example .env
python -m pip install -r requirements.txt
python call_mcp_agent.py
```

`AzureCliCredential` authenticates to Foundry, while the client obtains the current user's delegated MCP token from Azure CLI. To demonstrate user isolation, sign in to Azure CLI as another tenant user and run again. You can also pass a delegated token through the `MCP_ENTRA_ACCESS_TOKEN` environment variable. Do not place access tokens in `.env`, source control, or command-line arguments.
