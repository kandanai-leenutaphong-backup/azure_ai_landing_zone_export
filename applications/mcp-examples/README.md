# MCP examples

This folder contains two examples adapted from `LAB_4_MCP_APIM`:

- `petstore-api`: a FastAPI REST service imported into Azure API Management and exported as an MCP server.
- `math-mcp-server`: a native streamable-HTTP MCP server with a REST facade. APIM exports the REST operations as a governed MCP server while the native `/mcp/` endpoint remains available inside the private network.

Both workloads deploy to the existing internal Container Apps environment in `rg-ai-dev-sea`. API Management reaches them through direct gateway-to-spoke peering and the Container Apps private DNS zone.

Run `./scripts/deploy-mcp-examples.sh` from the repository root to build both images, deploy the Container Apps, import/register the APIs in APIM, and synchronize them into API Center.

The two MCP front doors are intentionally keyless demo endpoints so the API Center browser test console can connect. They allow only the API Center portal origin in browser CORS and are limited to 30 calls per minute per client IP. Their backing REST APIs reject requests without the same portal origin. Production MCP servers should use OAuth 2.1 protected-resource metadata instead.
