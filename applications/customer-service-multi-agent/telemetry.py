"""Allowlisted telemetry only. No exception messages, prompts, tokens or model text."""
from contextlib import contextmanager
import json
import logging
import sys
import time
from opentelemetry import trace
from opentelemetry import baggage
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_APP = "customer-service-capp-sea"
SERVICE_HOSTED = "customer-service-hosted-wus3"
# W3C baggage key carrying the app's hashed session ID to every downstream agent.
SESSION_BAGGAGE = "cs.session_id"
SPAN_FIELDS = ("service_name", "operation_type", "status", "error_code", "agent_id", "agent_version",
               "agent_step", "session_id", "customer_tier", "journey_type", "model_id",
               "input_token_count", "output_token_count", "latency_ms", "response_id")
GEN_AI = {"agent_id": "gen_ai.agent.name", "agent_version": "gen_ai.agent.version",
          "model_id": "gen_ai.request.model", "session_id": "gen_ai.conversation.id",
          "response_id": "gen_ai.response.id", "input_token_count": "gen_ai.usage.input_tokens",
          "output_token_count": "gen_ai.usage.output_tokens"}

LOGGER = logging.getLogger("customer-service.safe")
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler(sys.stdout))


def configure(settings):
    # Suppress third-party diagnostic text; app emits safe codes/metrics instead.
    for namespace in ("azure", "openai", "httpx", "httpcore", "opentelemetry"):
        logger = logging.getLogger(namespace)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL)
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_APP}))
    if settings.appinsights:
        provider.add_span_processor(BatchSpanProcessor(
            azure_monitor_exporter(settings.appinsights, getattr(settings, "client_id", None))))
    elif settings.otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
    return provider


def azure_monitor_exporter(connection_string, client_id=None):
    """Entra-only ingestion through the workload's managed identity; no instrumentation-key auth."""
    from azure.identity import ManagedIdentityCredential
    from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
    credential = ManagedIdentityCredential(client_id=client_id) if client_id else ManagedIdentityCredential()
    return AzureMonitorTraceExporter(connection_string=connection_string, credential=credential)


def baggage_session():
    value = baggage.get_baggage(SESSION_BAGGAGE)
    if isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value):
        return value
    return None


class Telemetry:
    def __init__(self, provider, service=SERVICE_APP):
        self.tracer = provider.get_tracer("customer-service-simulation", "1")
        self.service = service

    @contextmanager
    def event(self, operation, session, tier="unknown", agent=None, context=None,
              journey_type=None, run_id=None, step=None):
        start = time.perf_counter()
        values = {"input_token_count": None, "output_token_count": None,
                  "status": "ok", "error_code": None, "correctness": None, "decision_code": None,
                  "metrics": None}
        with self.tracer.start_as_current_span(operation, context=context,
                                               record_exception=False, set_status_on_exception=False) as span:
            try:
                yield values
            except Exception:
                values.update(status="failed", error_code="operation_failed")
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise
            finally:
                ctx = span.get_span_context()
                parent = getattr(span, "parent", None)
                row = {
                    "trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}",
                    "parent_span_id": f"{parent.span_id:016x}" if parent else None,
                    "service_name": self.service, "agent_step": step,
                    "agent_id": agent["name"] if agent else "service",
                    "agent_version": agent["version"] if agent else "1",
                    "session_id": session, "customer_tier": tier, "operation_type": operation,
                    "journey_type": journey_type, "run_id": run_id,
                    "model_id": "gpt-4.1-mini" if agent else None,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    **values,
                }
                for key in SPAN_FIELDS:
                    if row.get(key) is not None:
                        span.set_attribute(key, row[key])
                        if key in GEN_AI:
                            span.set_attribute(GEN_AI[key], row[key])
                LOGGER.info(json.dumps(row, separators=(",", ":")))
