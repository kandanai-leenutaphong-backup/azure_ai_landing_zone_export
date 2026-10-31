from dataclasses import dataclass
import os
from pathlib import Path
import uuid
from dotenv import load_dotenv

PROJECT = "https://foundry-agent-wus3jbm3vfsrmekbg.services.ai.azure.com/api/projects/agent-project"
MODEL = "gpt-4.1-mini"
CRITERIA = ("factual_accuracy", "task_completion", "tone", "consistency")
ROLES = ("triage", "policy", "resolution") + tuple("judge_" + c for c in CRITERIA)
ENV_FILE = Path(__file__).with_name(".env")


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    audience: str
    client_id: str
    database: str
    pins: dict
    allowed_object_ids: tuple[str, ...] = ()
    revision: str = "local"
    appinsights: str | None = None
    otlp_endpoint: str | None = None
    credential_mode: str = "managed_identity"
    browser_client_id: str | None = None
    hosted_agent_name: str | None = None
    hosted_agent_version: str | None = None
    replay_operator_object_ids: tuple[str, ...] = ()
    @classmethod
    def from_env(cls, *, env_file=ENV_FILE):
        if env_file is not None:
            load_dotenv(env_file, override=False, interpolate=False)
        if os.getenv("FOUNDRY_PROJECT_ENDPOINT", PROJECT).rstrip("/") != PROJECT:
            raise ValueError("Only assigned private West US 3 project is supported")
        if os.getenv("MODEL_DEPLOYMENT", MODEL) != MODEL:
            raise ValueError("Only assigned gpt-4.1-mini deployment is supported")
        tenant = str(uuid.UUID(os.environ["TENANT_ID"]))
        audience = str(uuid.UUID(os.environ["AUTH_CLIENT_ID"]))
        client = str(uuid.UUID(os.environ["AZURE_CLIENT_ID"]))
        pins = {}
        for role in ROLES:
            version = os.environ[f"AGENT_{role.upper()}_VERSION"]
            if not version.isdecimal() or int(version) < 1:
                raise ValueError("Agent version must be a positive integer")
            pins[role] = {"name": f"cs-sim-{role.replace('_', '-')}", "version": version}
        allowed = tuple(str(uuid.UUID(v.strip())) for v in os.environ["AUTH_ALLOWED_OBJECT_IDS"].split(","))
        if not allowed:
            raise ValueError("Explicit object ID allowlist required")
        credential_mode = os.getenv("AZURE_AUTH_MODE", "managed_identity")
        if credential_mode not in ("managed_identity", "azure_cli"):
            raise ValueError("AZURE_AUTH_MODE must be managed_identity or azure_cli")
        browser_client = os.getenv("BROWSER_CLIENT_ID")
        if browser_client:
            browser_client = str(uuid.UUID(browser_client))
        hosted_name = os.getenv("HOSTED_AGENT_NAME")
        hosted_version = os.getenv("HOSTED_AGENT_VERSION")
        if bool(hosted_name) != bool(hosted_version):
            raise ValueError("Hosted agent name and version must be configured together")
        if hosted_name and (hosted_name != "cs-customer-service-chat" or
                            not hosted_version.isdecimal() or int(hosted_version) < 1):
            raise ValueError("Expected the app-owned hosted chat agent and an explicit positive version")
        operators = tuple(str(uuid.UUID(v.strip())) for v in
                          os.getenv("REPLAY_OPERATOR_OBJECT_IDS", "").split(",") if v.strip())
        if not set(operators) <= set(allowed):
            raise ValueError("Replay operators must also be in AUTH_ALLOWED_OBJECT_IDS")
        return cls(tenant, audience, client, os.getenv("SQLITE_PATH", "/tmp/customer-service.sqlite3"),
                   pins, allowed, os.getenv("APP_REVISION", "local"),
                   os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"),
                   os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"), credential_mode,
                   browser_client, hosted_name, hosted_version, operators)
