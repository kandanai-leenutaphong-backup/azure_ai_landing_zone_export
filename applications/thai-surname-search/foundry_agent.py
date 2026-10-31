from __future__ import annotations

import os
import re
import socket
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from openai import OpenAI
from openai.types.responses import Response
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ModelDeployment, PromptAgentDefinition
from azure.core.credentials import TokenCredential


REGION_LABELS = {"westus3": "West US 3", "sea": "Southeast Asia"}
AGENT_TARGETS = {
    "westus3": ("AZURE_AGENT", "westus3"),
    "sea": ("AZURE_SEA_AGENT", "sea"),
    "westus3_global": ("AZURE_GLOBAL_AGENT", "westus3"),
    "sea_standard": ("AZURE_SEA_STANDARD_AGENT", "sea"),
}
GLOBAL_MODEL_DEPLOYMENT = "gpt-4.1-mini-global"
COMPARISON_TARGETS = {
    "global": ("westus3_global", "sea"),
    "standard": ("sea_standard", "westus3"),
}
COMPARISON_LABELS = {
    "global": "Global Standard: West US 3 vs SEA",
    "standard": "Standard: SEA vs West US 3",
}
COMPARISON_SKUS = {"global": "GlobalStandard", "standard": "Standard"}
SEA_STANDARD_UNAVAILABLE = (
    "Standard SEA vs Standard West US 3 is unavailable: on 2026-10-15, "
    "both the SEA regional and account catalogs offered Standard only for "
    "text-embedding-3-large, not a chat model. gpt-4.1-mini cannot be deployed "
    "as Standard there. No Global Standard or different-region fallback is used."
)


@dataclass(frozen=True)
class AgentSettings:
    project_endpoint: str
    agent_name: str
    agent_version: str
    region: str
    model_sku: str

    @property
    def label(self) -> str:
        return REGION_LABELS[self.region]

    @classmethod
    def from_env(cls, region: str = "westus3") -> AgentSettings:
        if region not in AGENT_TARGETS:
            raise ValueError(f"Unsupported agent target: {region}")
        prefix, region = AGENT_TARGETS[region]
        endpoint = os.getenv(f"{prefix}_PROJECT_ENDPOINT", "").strip().rstrip("/")
        name = os.getenv(f"{prefix}_NAME", "").strip()
        version = os.getenv(f"{prefix}_VERSION", "").strip()
        sku = os.getenv(f"{prefix}_MODEL_SKU", "").strip()
        if not endpoint or not name or not version or not sku:
            raise ValueError(
                f"Configure {prefix}_PROJECT_ENDPOINT, {prefix}_NAME, "
                f"{prefix}_VERSION and {prefix}_MODEL_SKU for {REGION_LABELS[region]}."
            )
        if name.startswith("asst_") or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", name):
            raise ValueError(f"{prefix}_NAME must be a new Foundry agent name, not a Classic asst_ ID.")
        if not version.isdecimal() or int(version) < 1:
            raise ValueError(f"{prefix}_VERSION must be a positive agent version number.")
        if sku not in {"Standard", "GlobalStandard"}:
            raise ValueError(f"{prefix}_MODEL_SKU must be Standard or GlobalStandard.")
        url = urlsplit(endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith(".services.ai.azure.com")
            or url.username
            or url.password
            or url.port not in (None, 443)
            or not url.path.startswith("/api/projects/")
            or not url.path.removeprefix("/api/projects/")
            or url.query
            or url.fragment
        ):
            raise ValueError(f"{prefix}_PROJECT_ENDPOINT must be a Foundry HTTPS project endpoint.")
        return cls(endpoint, name, version, region, sku)


@dataclass(frozen=True)
class AgentTimings:
    response_ms: float
    first_token_ms: float | None
    service_run_ms: float | None


@dataclass(frozen=True)
class AgentReply:
    text: str
    file_ids: tuple[str, ...]
    response_id: str
    timings: AgentTimings
    model: str
    input_tokens: int | None
    output_tokens: int | None
    file_search_calls: int = 0
    cached_input_tokens: int | None = None
    request_payload_bytes: int | None = None
    response_payload_bytes: int | None = None


def verify_regional_agents(
    first: AgentSettings, second: AgentSettings, sku: str, credential: TokenCredential,
) -> dict:
    if (
        {first.region, second.region} != {"sea", "westus3"}
        or first.project_endpoint == second.project_endpoint
        or first.model_sku != sku
        or second.model_sku != sku
    ):
        raise ValueError("Regional comparison requires SEA and West US 3 endpoints with the same model SKU.")
    signatures = []
    for settings in (first, second):
        with AIProjectClient(
            endpoint=settings.project_endpoint, credential=credential,
            connection_timeout=10, read_timeout=20, retry_total=0,
        ) as project:
            agent = project.agents.get_version(
                agent_name=settings.agent_name, agent_version=settings.agent_version,
            )
            definition = agent.definition
            if not isinstance(definition, PromptAgentDefinition):
                raise ValueError("Regional comparison requires new Foundry prompt agents.")
            deployment = project.deployments.get(name=definition.model)
            if not isinstance(deployment, ModelDeployment) or deployment.sku.name != sku:
                raise ValueError(f"{settings.label} actual deployment is not {sku}; comparison blocked.")
            if deployment.sku.capacity is None or deployment.sku.capacity <= 0:
                raise ValueError("Deployment capacity is unknown; matched comparison blocked.")
            normalized = definition.as_dict()
            normalized.pop("model")
            tools = normalized.get("tools", [])
            if len(tools) != 1 or tools[0].get("type") != "file_search" or not tools[0].get("vector_store_ids"):
                raise ValueError("Matched agents must have the same file-search workload configuration.")
            tools[0].pop("vector_store_ids")
            corpus_hash = (agent.metadata or {}).get("corpus_sha256", "")
            if not re.fullmatch(r"[0-9a-f]{64}", corpus_hash):
                raise ValueError("The agent knowledge corpus hash is missing; comparison blocked.")
            signatures.append((
                normalized, deployment.model_name, deployment.model_version,
                deployment.model_publisher, deployment.sku.capacity, corpus_hash,
            ))
    if signatures[0] != signatures[1]:
        raise ValueError(
            "Agent definitions, base model/version, capacity or knowledge corpus differ; comparison blocked."
        )
    return {
        "model": signatures[0][1], "version": signatures[0][2], "sku": sku,
        "capacity": signatures[0][4],
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def validate_sku_comparison(standard: AgentSettings, global_standard: AgentSettings) -> None:
    if (
        standard.project_endpoint != global_standard.project_endpoint
        or standard.region != global_standard.region
        or standard.model_sku != "Standard"
        or global_standard.model_sku != "GlobalStandard"
        or standard.agent_name == global_standard.agent_name
    ):
        raise ValueError(
            "SKU comparison requires distinct Standard and GlobalStandard agents "
            "in the same Foundry project and endpoint region."
        )


@dataclass(frozen=True)
class AgentConnectionProbe:
    hostname: str
    resolved_ip: str
    measured_at: str
    dns_ms: float
    tcp_samples_ms: tuple[float, ...]

    @property
    def median_tcp_ms(self) -> float:
        return statistics.median(self.tcp_samples_ms)


def measure_agent_connection(settings: AgentSettings) -> AgentConnectionProbe:
    hostname = urlsplit(settings.project_endpoint).hostname
    if not hostname:
        raise ValueError("The Foundry endpoint must have a hostname.")
    started_at = time.perf_counter()
    addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    dns_ms = (time.perf_counter() - started_at) * 1000
    if not addresses:
        raise OSError(f"No addresses resolved for {hostname}.")
    family, socktype, protocol, _, address = addresses[0]
    samples = []
    for _ in range(5):
        with socket.socket(family, socktype, protocol) as connection:
            connection.settimeout(3)
            started_at = time.perf_counter()
            connection.connect(address)
            samples.append((time.perf_counter() - started_at) * 1000)
    return AgentConnectionProbe(
        hostname,
        address[0],
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        dns_ms,
        tuple(samples),
    )


def invoke_agent(
    client: OpenAI,
    settings: AgentSettings,
    conversation_id: str,
    prompt: str,
    timeout_seconds: float = 90,
    *,
    tool_choice: Literal["auto", "none"] = "auto",
) -> AgentReply:
    prompt = prompt.strip()
    if not prompt or len(prompt) > 4000:
        raise ValueError("Enter a message between 1 and 4000 characters.")
    if timeout_seconds <= 0:
        raise ValueError("The agent timeout must be positive.")
    if tool_choice not in {"auto", "none"}:
        raise ValueError("Agent tool choice must be auto or none.")

    started_at = time.perf_counter()
    first_token_ms = None
    response: Response | None = None
    with client.responses.create(
        conversation=conversation_id,
        input=prompt,
        stream=True,
        max_output_tokens=1000,
        tool_choice=tool_choice,
        timeout=timeout_seconds,
        extra_body={
            "agent_reference": {
                "type": "agent_reference",
                "name": settings.agent_name,
                "version": settings.agent_version,
            }
        },
    ) as stream:
        request_payload_bytes = len(stream.response.request.content)
        for event in stream:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            if elapsed_ms > timeout_seconds * 1000:
                raise TimeoutError(
                    "Agent response exceeded the time limit; stream closed. "
                    "Server-side processing may continue."
                )
            if event.type == "response.output_text.delta" and event.delta and first_token_ms is None:
                first_token_ms = elapsed_ms
            if event.type in {"response.completed", "response.failed", "response.incomplete"}:
                response = event.response
            if event.type == "error":
                raise RuntimeError(f"Agent response stream failed: {event.message}")
        response_payload_bytes = stream.response.num_bytes_downloaded
    finished_at = time.perf_counter()
    if response is None:
        raise RuntimeError("Agent stream ended without a terminal response.")
    if response.status != "completed":
        detail = response.error.message if response.error else str(response.incomplete_details)
        raise RuntimeError(f"Agent response {response.id} ended with status {response.status}: {detail}")
    if any(item.type in {"function_call", "custom_tool_call", "mcp_approval_request"} for item in response.output):
        raise RuntimeError("This agent requested client-side tools that this module does not execute.")
    if not response.output_text.strip():
        raise RuntimeError(f"Agent response {response.id} completed without a text response.")
    file_search_calls = sum(item.type == "file_search_call" for item in response.output)
    if tool_choice == "none" and file_search_calls:
        raise RuntimeError("Foundry executed file search during a model-only benchmark; result excluded.")
    file_ids: list[str] = []
    for item in response.output:
        if item.type != "message":
            continue
        for content in item.content:
            if content.type == "output_text":
                for annotation in content.annotations:
                    if annotation.type == "file_citation":
                        file_ids.append(annotation.file_id)
    service_run_ms = None
    if response.completed_at is not None and response.completed_at >= response.created_at:
        service_run_ms = (response.completed_at - response.created_at) * 1000
    return AgentReply(
        response.output_text,
        tuple(dict.fromkeys(file_ids)),
        response.id,
        AgentTimings(
            response_ms=(finished_at - started_at) * 1000,
            first_token_ms=first_token_ms,
            service_run_ms=service_run_ms,
        ),
        response.model,
        response.usage.input_tokens if response.usage else None,
        response.usage.output_tokens if response.usage else None,
        file_search_calls,
        response.usage.input_tokens_details.cached_tokens if response.usage else None,
        request_payload_bytes,
        response_payload_bytes,
    )
