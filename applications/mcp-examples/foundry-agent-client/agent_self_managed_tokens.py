# ILLUSTRATIVE ONLY - not production ready.
#
# Difference vs. agent_per_user_app.py:
#   agent_per_user_app.py         -> Foundry runs the OAuth consent flow for the MCP tool and
#                                     stores the resulting access/refresh tokens itself, scoped
#                                     per user. You never see those tokens.
#   agent_self_managed_tokens.py  -> WE own the MCP tool's access/refresh tokens end-to-end
#                                     (acquire, cache, refresh) and hand Foundry a plain bearer
#                                     token via the tool's "headers", bypassing Foundry's
#                                     oauth_consent_request flow entirely.
#
# Trade-off: you take on the responsibility (and security burden) of storing and refreshing
# the MCP server's tokens yourself - e.g. in Key Vault / a database - instead of letting
# Foundry manage that lifecycle for you.
#
# Before running:
#   pip install fastapi uvicorn azure-identity azure-ai-projects>=2.1.0
#
# Run:
#   uvicorn agent_self_managed_tokens:app --reload

import time

from fastapi import FastAPI, Header, HTTPException
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

app = FastAPI()

ENDPOINT = "https://foundry-agent-vnet-seaxlpu.services.ai.azure.com/api/projects/agent-vnet-projectxlpu"
AGENT_NAME = "eager-agent-9pp36clmdb"
AGENT_VERSION = "2"
MCP_SERVER_LABEL = "<mcp-server-label>"  # must match the MCP tool's server_label in the agent

# Foundry's own identity for the /responses call - unrelated to the MCP tool's tokens below.
credential = DefaultAzureCredential()


class McpTokenStore:
    """
    Stand-in for wherever you actually keep these - e.g. Key Vault, a database row per user,
    or a cache in front of the MCP server's own token endpoint. This class owns the full
    access-token / refresh-token lifecycle that Foundry would otherwise manage for you.
    """

    def __init__(self):
        self._access_token = None
        self._refresh_token = "<seed-refresh-token>"  # obtained once via your own auth code flow
        self._expires_at = 0

    def get_access_token(self, user_id: str) -> str:
        if self._access_token is None or time.time() >= self._expires_at:
            self._refresh(user_id)
        return self._access_token

    def _refresh(self, user_id: str) -> None:
        # Call the MCP server's/IdP's token endpoint yourself, e.g.:
        #   resp = requests.post(token_url, data={
        #       "grant_type": "refresh_token",
        #       "refresh_token": self._refresh_token,
        #       "client_id": CLIENT_ID,
        #       "client_secret": CLIENT_SECRET,
        #   })
        #   payload = resp.json()
        #   self._access_token = payload["access_token"]
        #   self._refresh_token = payload.get("refresh_token", self._refresh_token)
        #   self._expires_at = time.time() + payload["expires_in"]
        raise NotImplementedError("Wire this up to your MCP server's real token endpoint.")


token_store = McpTokenStore()


@app.post("/ask")
def ask(question: str, x_user_id: str = Header(...)):
    """
    Example request:
        POST /ask?question=Give me my email
        X-User-Id: alice@example.com

    Unlike agent_per_user_app.py, there is no oauth_consent_request round trip here - we
    already hold (and refresh) this user's MCP access token ourselves, so we inject it
    directly into the MCP tool definition's headers.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing user id")

    mcp_access_token = token_store.get_access_token(x_user_id)

    project_client = AIProjectClient(endpoint=ENDPOINT, credential=credential)
    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        input=[{"role": "user", "content": question}],
        extra_body={
            "agent_reference": {
                "name": AGENT_NAME,
                "version": AGENT_VERSION,
                "type": "agent_reference",
            },
            # Overrides the MCP tool's auth for this call: Foundry forwards this header to
            # the MCP server as-is instead of running its own OAuth consent flow.
            "tools": [
                {
                    "type": "mcp",
                    "server_label": MCP_SERVER_LABEL,
                    "headers": {"Authorization": f"Bearer {mcp_access_token}"},
                }
            ],
        },
    )

    return {"status": response.status, "output": response.output_text}
