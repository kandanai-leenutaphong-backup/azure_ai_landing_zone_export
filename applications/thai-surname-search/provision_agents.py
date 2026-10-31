from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FileSearchTool, PromptAgentDefinition
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from foundry_agent import AGENT_TARGETS, GLOBAL_MODEL_DEPLOYMENT, AgentSettings, validate_sku_comparison


DOCUMENT = b"The West US 3 landing zone readiness code is WESTUS3-SPOKE-READY."
INSTRUCTIONS = (
    "Use file_search to read the supplied document and answer questions about "
    "the landing zone with its exact readiness code. Cite the source document. "
    "For other questions, be helpful and concise."
)
MODEL = "gpt-4.1-mini"


def provision(settings: AgentSettings, source_settings: AgentSettings | None = None) -> dict:
    corpus_hash = hashlib.sha256(DOCUMENT).hexdigest()
    if settings.region == "westus3" and settings.model_sku == "GlobalStandard" and source_settings is None:
        raise ValueError("The West US 3 GlobalStandard agent requires its matching Standard source agent.")
    if source_settings is not None:
        validate_sku_comparison(source_settings, settings)
    with DefaultAzureCredential() as credential, AIProjectClient(
        endpoint=settings.project_endpoint, credential=credential,
        connection_timeout=10, read_timeout=60, retry_total=0,
    ) as project:
        shared_definition = None
        if source_settings is not None:
            source = project.agents.get_version(
                agent_name=source_settings.agent_name, agent_version=source_settings.agent_version
            )
            if (
                not isinstance(source.definition, PromptAgentDefinition)
                or source.definition.model != MODEL
                or source.definition.instructions != INSTRUCTIONS
                or source.definition.temperature != 0
                or len(source.definition.tools or []) != 1
                or source.definition.tools[0].type != "file_search"
                or not source.metadata
                or source.metadata.get("corpus_sha256") != corpus_hash
            ):
                raise RuntimeError("Source agent differs from the comparison definition; not cloning it.")
            shared_definition = copy.deepcopy(source.definition)
            shared_definition.model = GLOBAL_MODEL_DEPLOYMENT
        expected_model = GLOBAL_MODEL_DEPLOYMENT if shared_definition is not None else MODEL
        try:
            existing = project.agents.get_version(
                agent_name=settings.agent_name, agent_version=settings.agent_version
            )
        except ResourceNotFoundError:
            existing = None
            try:
                project.agents.get(agent_name=settings.agent_name)
            except ResourceNotFoundError:
                pass
            else:
                raise RuntimeError("Agent name already exists without the requested version; not modifying it.")
        if existing is not None:
            definition = existing.definition
            if (
                not isinstance(definition, PromptAgentDefinition)
                or definition.model != expected_model
                or definition.instructions != INSTRUCTIONS
                or definition.temperature != 0
                or len(definition.tools or []) != 1
                or definition.tools[0].type != "file_search"
                or not existing.metadata
                or existing.metadata.get("corpus_sha256") != corpus_hash
                or (
                    shared_definition is not None
                    and definition.as_dict() != shared_definition.as_dict()
                )
            ):
                raise RuntimeError("Existing agent differs from the comparison definition; not modifying it.")
            return existing.as_dict()

        if shared_definition is None:
            with project.get_openai_client(timeout=60, max_retries=0) as client:
                uploaded = client.files.create(
                    file=("agent-spoke-readiness.txt", io.BytesIO(DOCUMENT)), purpose="assistants"
                )
                store = client.vector_stores.create(
                    name=f"{settings.agent_name}-knowledge", file_ids=[uploaded.id],
                    metadata={"corpus_sha256": corpus_hash},
                )
                print(f"Retained file {uploaded.id} and vector store {store.id}", flush=True)
                deadline = time.monotonic() + 300
                while store.status == "in_progress":
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Vector store {store.id} indexing timed out; resources retained.")
                    time.sleep(1)
                    store = client.vector_stores.retrieve(store.id)
                if store.status != "completed" or store.file_counts.completed != 1 or store.file_counts.failed:
                    raise RuntimeError(f"Vector store indexing failed: {store.model_dump_json()}")
                shared_definition = PromptAgentDefinition(
                    model=MODEL,
                    instructions=INSTRUCTIONS,
                    temperature=0,
                    tools=[FileSearchTool(vector_store_ids=[store.id])],
                )
        agent = project.agents.create_version(
            agent_name=settings.agent_name,
            definition=shared_definition,
            metadata={
                "corpus_sha256": corpus_hash,
                "comparison_region": settings.region,
                "model_sku": settings.model_sku,
                "model_version": "2025-04-14",
            },
        )
        if agent.version != settings.agent_version:
            raise RuntimeError(
                f"Created version {agent.version}, not configured version {settings.agent_version}; "
                "update configuration explicitly before invoking it."
            )
        return agent.as_dict()


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Create and retain matched new Foundry prompt agents.")
    parser.add_argument(
        "--region", "--target", dest="target",
        choices=("westus3", "sea", "westus3_global"), required=True,
    )
    arguments = parser.parse_args()
    source_settings = AgentSettings.from_env("westus3") if arguments.target == "westus3_global" else None
    print(json.dumps(provision(AgentSettings.from_env(arguments.target), source_settings), indent=2))
