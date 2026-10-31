# Before running the sample:
#    pip install azure-ai-projects>=2.1.0

import base64
import json

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

endpoint = "https://foundry-agent-vnet-seaxlpu.services.ai.azure.com/api/projects/agent-vnet-projectxlpu"

credential = DefaultAzureCredential()


def decode_jwt_claims(jwt: str) -> dict:
    """Decode a JWT payload WITHOUT verifying its signature - for local debugging only."""
    payload_b64 = jwt.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


# This is the same token DefaultAzureCredential hands to AIProjectClient under the hood
# (the "shared identity" - notice it's tied to whoever is logged into az/vscode/managed identity,
# not to any individual end user of the app).
debug_token = credential.get_token("https://ai.azure.com/.default")
print("=== Token used by agent.py (shared identity) ===")
print(f"Raw access token: {debug_token.token}")
print(f"Expires on (epoch): {debug_token.expires_on}")
print(f"Decoded claims: {json.dumps(decode_jwt_claims(debug_token.token), indent=2)}")
print("=" * 50)

project_client = AIProjectClient(
    endpoint=endpoint,
    credential=credential,
)

my_agent = "private-network-agent-test"
my_version = "2"

openai_client = project_client.get_openai_client()

# Reference the agent to get a response
response = openai_client.responses.create(
    input=[{"role": "user", "content": "Give me my email"}],
    extra_body={"agent_reference": {"name": my_agent, "version": my_version, "type": "agent_reference"}},
)

print(f"Response status: {response.status}")

# Some MCP tools require one-time OAuth consent before they can run;
# in that case output_text is empty and an oauth_consent_request item is returned instead.
consent_requests = [item for item in response.output if getattr(item, "type", None) == "oauth_consent_request"]
if consent_requests:
    for item in consent_requests:
        print(f"OAuth consent required for '{item.server_label}'. Visit this link to authorize, then re-run:")
        print(item.consent_link)
else:
    approval_requests = [item for item in response.output if getattr(item, "type", None) == "mcp_approval_request"]
    if approval_requests:
        # The agent wants to call an MCP tool and needs explicit approval first.
        # Send the approvals back, chained to this response, to get the final answer.
        approval_input = [
            {
                "type": "mcp_approval_response",
                "approval_request_id": item.id,
                "approve": True,
            }
            for item in approval_requests
        ]
        response = openai_client.responses.create(
            input=approval_input,
            previous_response_id=response.id,
            extra_body={"agent_reference": {"name": my_agent, "version": my_version, "type": "agent_reference"}},
        )
        print(f"Response status: {response.status}")
        print(f"Response output: {response.output_text}")
        print(f"Raw output items: {response.output}")
    else:
        print(f"Response output: {response.output_text}")
        print(f"Raw output items: {response.output}")