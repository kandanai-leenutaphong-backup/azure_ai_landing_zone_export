# MCP examples

This folder contains two examples adapted from `LAB_4_MCP_APIM`:

- `petstore-api`: a FastAPI REST service imported into Azure API Management and exported as an MCP server.
- `math-mcp-server`: a native streamable-HTTP MCP server with a REST facade. APIM exports the REST operations as a governed MCP server while the native `/mcp/` endpoint remains available inside the private network.

Both workloads deploy to the existing internal Container Apps environment in `rg-ai-dev-sea`. API Management reaches them through direct gateway-to-spoke peering and the Container Apps private DNS zone.

Run `./scripts/deploy-mcp-examples.sh` from the repository root to build both images, deploy the Container Apps, import/register the APIs in APIM, and synchronize them into API Center.
