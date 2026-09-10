# MCP examples

This folder contains three governed MCP examples and an Agent Framework client:

- `petstore-api`: a FastAPI REST service imported into Azure API Management and exported as an MCP server.
- `math-mcp-server`: a native streamable-HTTP MCP server with a REST facade. APIM exports the REST operations as a governed MCP server while the native `/mcp/` endpoint remains available inside the private network.
- `entra-user-data-api`: a native streamable-HTTP MCP server at `/mcp` with a REST facade. APIM transparently proxies the MCP transport, validates the delegated user token, and injects immutable user claims so each identity receives only its own deterministic demo profile and orders.
- `agent-client`: a Python Agent Framework client that gives one Foundry-backed agent access to all three deployed MCP servers.
- `agent-client-tester`: a lightweight MCP smoke-test client (no Foundry/model required) that connects to any streamable-HTTP MCP endpoint, lists its tools, and can optionally invoke one. Useful for validating a new endpoint, such as an `outlook-mcp` server exposed through API Management, before wiring it into `agent-client`.

All three workloads deploy to the existing internal Container Apps environment in `rg-ai-dev-sea`. API Management reaches them through direct gateway-to-spoke peering and the Container Apps private DNS zone.

Run `./scripts/deploy-mcp-examples.sh` from the repository root to build both images, deploy the Container Apps, import/register the APIs in APIM, and synchronize them into API Center.

All three MCP front doors require a delegated Entra token for the `access_as_user` scope. They allow the API Center portal origin in browser CORS, rate-limit by the caller's Entra object ID, and emit identity-scoped `MCP Tool Calls` metrics to Application Insights. Their backing REST APIs remain inaccessible directly.

Run `./scripts/deploy-entra-mcp-example.sh` first to create the shared delegated Entra scope and deploy the user-data MCP server. Then run `./scripts/deploy-mcp-examples.sh` to deploy the pet and math servers with the same authentication and telemetry policy. Finally, run the Agent Framework client:

```bash
cd applications/mcp-examples/agent-client
cp .env.example .env
python -m pip install -r requirements.txt
python call_mcp_agent.py
```

`AzureCliCredential` authenticates to Foundry, while the client obtains the current user's delegated MCP token from Azure CLI. To demonstrate user isolation, sign in to Azure CLI as another tenant user and run again. You can also pass a delegated token through the `MCP_ENTRA_ACCESS_TOKEN` environment variable. Do not place access tokens in `.env`, source control, or command-line arguments.
