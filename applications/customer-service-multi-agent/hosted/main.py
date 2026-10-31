"""Native Foundry Responses host. Configuration enters only here."""
import logging
import os

from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import context
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if __package__:
    from .runtime import build_agent
else:
    from runtime import build_agent
from telemetry import SERVICE_HOSTED, Telemetry, azure_monitor_exporter

PROJECT = "https://foundry-agent-wus3jbm3vfsrmekbg.services.ai.azure.com/api/projects/agent-project"


class SafeResponsesHost(ResponsesHostServer):
    @staticmethod
    def _emit_failure(response_event_stream, tracker, ex):
        # Installed host otherwise sends str(ex) in public response.failed.
        yield from ResponsesHostServer._emit_failure(
            response_event_stream, tracker, RuntimeError("hosted_turn_failed"))


class ZeroRetryProject(AIProjectClient):
    def get_openai_client(self, **kwargs):
        return super().get_openai_client(max_retries=0, timeout=35, **kwargs)


class TraceContext:
    """Propagate CApp trace without logging HTTP headers or payloads."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = {k.decode("latin1"): v.decode("latin1") for k, v in scope.get("headers", [])}
        token = context.attach(extract(headers))
        try:
            await self.app(scope, receive, send)
        finally:
            context.detach(token)


def make_host(agent):
    server = SafeResponsesHost(agent, configure_observability=None, access_log=None)
    server.add_middleware(TraceContext)
    return server


def safe_logging():
    """Host constructor installs diagnostic handlers; disable them after construction."""
    root = logging.getLogger()
    root.handlers = [logging.NullHandler()]
    root.setLevel(logging.CRITICAL + 1)
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(logger, logging.Logger) or name == "customer-service.safe":
            continue
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.disabled = True
        logger.setLevel(logging.CRITICAL + 1)


def main():
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
    safe_logging()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    if endpoint.rstrip("/") != PROJECT:
        raise ValueError("assigned_private_project_required")
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")
    if model != "gpt-4.1-mini":
        raise ValueError("assigned_regional_model_required")
    credential = DefaultAzureCredential()
    project = ZeroRetryProject(endpoint=endpoint, credential=credential, retry_total=0)
    client = FoundryChatClient(project_client=project, model=model)
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_HOSTED}))
    connection = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection:
        # Foundry injects this when the project has an App Insights connection.
        provider.add_span_processor(BatchSpanProcessor(azure_monitor_exporter(connection)))
    host = make_host(build_agent(client, Telemetry(provider, service=SERVICE_HOSTED)))
    safe_logging()
    host.run(port=8088)


if __name__ == "__main__":
    main()
