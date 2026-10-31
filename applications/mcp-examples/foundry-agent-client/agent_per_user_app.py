# ILLUSTRATIVE ONLY - not production ready.
#
# Difference vs. agent.py:
#   agent.py                -> single shared identity (DefaultAzureCredential) for every call.
#                               OAuth consent / MCP tokens are all associated with ONE identity.
#   agent_per_user_app.py    -> a tiny web app where EACH incoming request carries the caller's
#                               own Entra ID token (e.g. from a frontend sign-in / App Service
#                               Easy Auth / API Management). We exchange that user token for a
#                               token *as that user* (On-Behalf-Of flow) before calling Foundry,
#                               so Foundry's OAuth consent / MCP tool tokens are scoped per user.
#
# Before running:
#   pip install fastapi uvicorn azure-identity azure-ai-projects>=2.1.0
#
# Run:
#   uvicorn agent_per_user_app:app --reload

from fastapi import FastAPI, Header, HTTPException
from azure.identity import OnBehalfOfCredential
from azure.ai.projects import AIProjectClient

app = FastAPI()

ENDPOINT = "https://foundry-agent-vnet-seaxlpu.services.ai.azure.com/api/projects/agent-vnet-projectxlpu"
AGENT_NAME = "eager-agent-9pp36clmdb"
AGENT_VERSION = "2"

# App registration used to perform the On-Behalf-Of exchange.
# In a real app these come from env vars / Key Vault, never hardcoded.
TENANT_ID = "<tenant-id>"
CLIENT_ID = "<web-app-client-id>"
CLIENT_SECRET = "<web-app-client-secret>"


def get_credential_for_user(user_access_token: str) -> OnBehalfOfCredential:
    """
    Exchange the caller's own bearer token (passed through from the frontend
    login) for a credential that represents THAT user, not the web app.
    This is what makes MCP OAuth consent / tokens land on the correct user
    inside Foundry, instead of all users sharing one identity.
    """
    return OnBehalfOfCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_assertion=user_access_token,
    )


@app.post("/ask")
def ask(question: str, authorization: str = Header(...)):
    """
    Example request:
        POST /ask?question=Give me my email
        Authorization: Bearer <the signed-in user's Entra ID token>

    That header is what a real frontend (or API Management / App Service
    Easy Auth) would forward after the user logs in. Nothing about the
    user's token is stored in our own database - Foundry keeps the MCP
    OAuth consent/tokens scoped to this user's identity on its side.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user_token = authorization.removeprefix("Bearer ").strip()

    # Per-request, per-user credential - NOT a shared DefaultAzureCredential.
    credential = get_credential_for_user(user_token)

    project_client = AIProjectClient(endpoint=ENDPOINT, credential=credential)
    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        input=[{"role": "user", "content": question}],
        extra_body={
            "agent_reference": {
                "name": AGENT_NAME,
                "version": AGENT_VERSION,
                "type": "agent_reference",
            }
        },
    )

    for item in response.output:
        if getattr(item, "type", None) == "oauth_consent_request":
            # First time THIS user touches this MCP tool - surface their own
            # personal consent link (not shared with other users).
            return {
                "status": "consent_required",
                "consent_link": item.consent_link,
            }

    return {"status": response.status, "output": response.output_text}
