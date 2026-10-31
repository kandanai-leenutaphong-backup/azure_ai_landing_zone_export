"""Composition root. Test injection is Python-only, never an environment bypass."""
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import uuid
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import BaseModel, ConfigDict, Field
from auth import EntraAuth
from chat import ChatService, ChatUnavailable
from settings import Settings
from simulation import Store, SimulationService
from telemetry import Telemetry, configure

ROOT = Path(__file__).parent


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario_id: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=36)


def create_app(settings=None, *, agents=None, auth=None, chat_client=None):
    settings = settings or Settings.from_env()
    auth = auth or EntraAuth(settings.tenant_id, settings.audience, settings.allowed_object_ids)
    provider = configure(settings)
    telemetry = Telemetry(provider)
    if agents is None:
        from native import NativeAgents
        agents = NativeAgents(settings)
    service = SimulationService(Store(settings.database), agents, telemetry, settings.pins)
    chat = ChatService(settings, service.busy, telemetry=telemetry, hosted_client=chat_client)

    @asynccontextmanager
    async def lifespan(app):
        yield
        chat.close()
        service.close()
        provider.shutdown()

    app = FastAPI(title="Synthetic Service Lab", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.service = service
    app.state.chat = chat

    @app.middleware("http")
    async def boundary(request, call_next):
        context = TraceContextTextMapPropagator().extract(dict(request.headers))
        session = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        with telemetry.event("http.request", session, context=context) as event:
            try:
                response = await call_next(request)
            except Exception:
                event.update(status="failed", error_code="internal_error")
                response = JSONResponse({"detail": "Internal service error"}, 500)
            if response.status_code >= 400:
                event.update(status="rejected", error_code=f"http_{response.status_code}")
            from opentelemetry import trace
            ctx = trace.get_current_span().get_span_context()
            response.headers["traceparent"] = f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01"
            response.headers.update({
                "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' https://login.microsoftonline.com; frame-src https://login.microsoftonline.com; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
                "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Strict-Transport-Security": "max-age=31536000",
            })
            return response

    def owner(authorization):
        return auth(authorization)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "revision": settings.revision, "storage": "ephemeral-sqlite",
                "native_connectivity": "not-probed"}

    @app.get("/auth/config")
    def browser_configuration():
        if not settings.browser_client_id:
            raise HTTPException(503, "Microsoft sign-in is not configured")
        return {
            "tenant_id": settings.tenant_id, "client_id": settings.browser_client_id,
            "scope": f"api://{settings.audience}/access_as_user", "redirect_path": "/auth/callback",
        }

    @app.get("/auth/callback")
    def browser_callback():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/api/scenarios")
    def scenarios(authorization: str | None = Header(default=None)):
        owner(authorization)
        from scenarios import SCENARIOS
        return {"simulation": True, "scenarios": [s.public() for s in SCENARIOS.values()]}

    @app.post("/api/simulations", status_code=202)
    def submit(body: SimulationRequest, authorization: str | None = Header(default=None),
               traceparent: str | None = Header(default=None)):
        user = owner(authorization)
        from scenarios import SCENARIOS
        if body.scenario_id not in SCENARIOS:
            raise HTTPException(404, "Unknown synthetic scenario")
        from opentelemetry import context
        try:
            row = service.submit(user, body.scenario_id, context.get_current())
            return JSONResponse(row, 202, headers={"Location": f"/api/simulations/{row['id']}"})
        except BlockingIOError:
            raise HTTPException(429, "One simulation is running. Poll its result first.", headers={"Retry-After": "30"}) from None

    @app.get("/api/simulations/{run_id}")
    def read(run_id: str, authorization: str | None = Header(default=None)):
        user = owner(authorization)
        row = service.store.get(user, run_id)
        if row is None:
            raise HTTPException(404, "Simulation not found")
        return row

    @app.get("/api/metrics")
    def metrics(journey_type: str | None = None, authorization: str | None = Header(default=None)):
        user = owner(authorization)
        from scenarios import SCENARIOS
        if journey_type is not None and journey_type not in {s.category for s in SCENARIOS.values()}:
            raise HTTPException(422, "Unknown journey type")
        return service.metrics(user, journey_type)

    @app.post("/api/chat/messages", status_code=202)
    def chat_message(body: ChatRequest, authorization: str | None = Header(default=None)):
        user = owner(authorization)
        try:
            row = chat.submit(user, body.message, body.conversation_id)
            return JSONResponse(row, 202, headers={
                "Location": f"/api/chat/conversations/{row['conversation_id']}",
            })
        except ChatUnavailable:
            raise HTTPException(503, "Hosted chat is not configured") from None
        except KeyError:
            raise HTTPException(404, "Conversation not found") from None
        except BlockingIOError:
            raise HTTPException(429, "An agent operation is running. Poll its result first.",
                                headers={"Retry-After": "30"}) from None
        except ValueError:
            raise HTTPException(422, "Invalid message, conversation or conversation state") from None

    @app.get("/api/chat/conversations/{conversation_id}")
    def chat_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
        row = chat.get(owner(authorization), conversation_id)
        if row is None:
            raise HTTPException(404, "Conversation not found")
        return row

    @app.get("/api/chat/replay/{response_id}")
    def chat_replay(response_id: str, authorization: str | None = Header(default=None)):
        user = owner(authorization)
        # Foundry binds stored responses to the app identity and drops request metadata,
        # so replay is an explicit operator capability, not a per-owner read.
        operators = {hashlib.sha256(f"{settings.tenant_id}:{oid}".encode()).hexdigest()
                     for oid in settings.replay_operator_object_ids}
        if user not in operators:
            raise HTTPException(403, "Replay requires a configured operator")
        try:
            return chat.replay(response_id)
        except ValueError:
            raise HTTPException(422, "Invalid response id") from None
        except KeyError:
            raise HTTPException(404, "Response not found") from None
        except ChatUnavailable:
            raise HTTPException(503, "Replay is unavailable") from None

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app
