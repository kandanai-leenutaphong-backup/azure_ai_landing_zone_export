"""Optional, fixed-binding MCP host. Importing this module performs no I/O.

``create_server`` accepts host-owned ``Binding`` values and exact tool-name grants
per binding ID. Every tool requires that ID, never an endpoint, credential,
principal, grant or recovery path. One supplied execution context bounds the
server's calls. Ownership transfers to Framework for the server lifespan only.
``python -m agentcraft.mcp`` exposes only the bundled offline composition tools.

Failure contract: host/recovery exceptions retain ``error: FailureInfo``.
Capability adapters add sibling ``failure`` or ordered ``failures`` metadata to
their native bodies. This edge stamps each mapping with the fixed binding's
capability label, declared tool name and supplied context's run_id, never a
request's artifact ID or an ambient context that may already have unwound.
Unknown bindings/tools use ``framework``/``unknown_tool``. Native ``isError``
is authoritative; native payloads and non-body content blocks are retained.
JSON TextContent representing the body is refreshed with structuredContent.

SDK input-schema validation happens before this handler. Its protocol errors
are not domain FailureInfo responses; the built-in validator is not replaced.
External HTTP authentication and its empty denial bodies are not involved.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Callable, Collection, Mapping
from contextlib import asynccontextmanager
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

import anyio
from appcompose import CompositionError, CredentialShaped, DocumentInvalid, UnsupportedVersion
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from agentcraft import Binding, CallerContext, ExecutionContext, FailureInfo, Framework, FrameworkError


def _composition(settings: Any) -> tuple[list[types.Tool], dict[str, Callable[..., Any]]]:
    from appcompose.mcp import TOOLS, Settings, demo, validate

    if not isinstance(settings, Settings):
        raise FrameworkError("binding_type_mismatch", capability_id="composition")

    def validate_document(document: str, format: str = "json") -> dict[str, Any]:
        return validate(document, format, settings)

    return TOOLS, {
        "composition_status": lambda: {"configured": True, **settings.model_dump(),
                                        "arbitrary_execution": False, "network": False},
        "composition_validate": validate_document,
        "composition_demo": demo,
    }


def _recovery(application: Any) -> tuple[list[types.Tool], dict[str, Callable[..., Any]]]:
    from workrecovery import (
        ArtifactCorrupt, ArtifactExists, ArtifactMissing, InvalidRunId,
        PayloadNotSupported, PayloadTooLarge, RecoveryError, StagingFailed,
        StaleArtifact, StoreError, StoreOccupied, StoreRefused, StoreTimeout,
        StoreUnavailable,
    )
    from workrecovery.mcp import TOOLS, RecoveryTools

    if not isinstance(application, RecoveryTools):
        raise FrameworkError("binding_type_mismatch", capability_id="recovery")
    if not application.settings.recovery_root or not Path(application.settings.recovery_root).is_absolute():
        raise FrameworkError("explicit_recovery_root_required", category="denied")

    failures = (
        (PayloadNotSupported, "unsupported", "none", "never", "payload_json",
         "Use a supported JSON payload; retain the original output."),
        (PayloadTooLarge, "invalid", "none", "safe_after_correction", "payload_json",
         "Review the payload ceiling before staging; retain the full output."),
        (InvalidRunId, "invalid", "none", "safe_after_correction", "run_id",
         "Use a valid artifact run ID within the configured root."),
        (ArtifactExists, "denied", "none", "safe_after_correction", "run_id",
         "Read the existing artifact; choose an unused ID for different output."),
        (ArtifactMissing, "failed", "none", "safe_after_correction", "run_id",
         "Check the artifact ID and retained local output; no artifact was found."),
        (ArtifactCorrupt, "failed", "none", "never", None,
         "Preserve the artifact and inspect its integrity; do not overwrite it."),
        (StaleArtifact, "denied", "none", "read_back_first", None,
         "Read the current artifact and reconcile ownership; preserve its bytes."),
        (StagingFailed, "failed", "unknown", "read_back_first", None,
         "Inspect the local artifact before staging again; preservation is unconfirmed."),
        (StoreRefused, "denied", "none", "safe_after_correction", None,
         "Correct the destination store refusal; retain the local artifact."),
        (StoreUnavailable, "unavailable", "none", "unspecified", None,
         "Check store availability; this request was not sent."),
        (StoreTimeout, "interrupted", "unknown", "read_back_first", None,
         "Read back the destination before another write; retain the local artifact."),
        (StoreOccupied, "denied", "none", "never", "run_id",
         "Reconcile destination ownership; do not overwrite existing output."),
        (StoreError, "failed", "unknown", "read_back_first", None,
         "Read back the destination and retain the local artifact."),
        (RecoveryError, "failed", "unknown", "read_back_first", None,
         "Inspect retained output before attempting recovery again."),
    )

    def invoke(operation, **arguments):
        try:
            return operation(**arguments)
        except json.JSONDecodeError:
            return {"error": FailureInfo(
                "invalid_payload_json", category="invalid", field="payload_json",
                retry="safe_after_correction", action="Supply valid JSON before staging.",
            ).to_dict()}
        except RecoveryError as error:
            for kind, category, effect, retry, field, action in failures:
                if isinstance(error, kind):
                    return {"error": FailureInfo(
                        kind.__name__, category=category, effect=effect, retry=retry,
                        field=field, action=action,
                    ).to_dict()}

    return TOOLS, {
        "recovery_status": application.status,
        "recovery_list": partial(invoke, application.listing),
        "recovery_stage": partial(invoke, application.stage),
        "recovery_read": partial(invoke, application.read),
    }


def _document_field(field: str) -> str:
    if isinstance(field, str) and len(field) <= 160 and re.fullmatch(
        r"(?:schemaVersion|kind|name|members|ownership)"
        r"(?:\[[0-9]{1,4}\])?"
        r"(?:\.(?:id|capability|requires|settings)(?:\[[0-9]{1,4}\])?)*", field,
    ):
        return field
    return "document"


def _correlate_result(payload, *, capability_id: str, operation: str, run_id: str) -> types.CallToolResult:
    native = payload if isinstance(payload, types.CallToolResult) else None
    original = native.structuredContent if native else payload
    if native and original is None:
        for block in native.content:
            if isinstance(block, types.TextContent):
                try:
                    candidate = json.loads(block.text)
                except (ValueError, TypeError):
                    continue
                if isinstance(candidate, dict):
                    original = candidate
                    break
    body = dict(original or {})
    failed = native.isError if native else "error" in body

    def correlated(failure):
        return {**failure, "capability_id": capability_id, "operation": operation, "run_id": run_id}

    if failed:
        if isinstance(body.get("failures"), list) and body["failures"]:
            body["failures"] = [correlated(failure) for failure in body["failures"]]
        elif isinstance(body.get("failure"), dict):
            body["failure"] = correlated(body["failure"])
        elif isinstance(body.get("error"), dict) and {"effect", "retry"} <= body["error"].keys():
            body["error"] = correlated(body["error"])
        else:
            body["failure"] = correlated(FailureInfo(
                "operation_failed", effect="unknown",
                retry="read_back_first" if operation == "recovery_stage" else "unspecified",
                action="Inspect operation state before another attempt; effects are unconfirmed.",
            ).to_dict())
    elif native:
        return native

    text = json.dumps(body, allow_nan=False)
    if native:
        content = []
        replaced = False
        for block in native.content:
            if isinstance(block, types.TextContent):
                try:
                    matches = json.loads(block.text) == original
                except (ValueError, TypeError):
                    matches = False
                if matches:
                    content.append(block.model_copy(update={"text": text}))
                    replaced = True
                    continue
            content.append(block)
        if not replaced:
            content.append(types.TextContent(type="text", text=text))
        return native.model_copy(update={"content": content, "structuredContent": body})
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], structuredContent=body, isError=failed,
    )


def create_server(
    *,
    bindings: Mapping[str, Binding],
    grants: Mapping[str, Collection[str]],
    principal: str,
    context: ExecutionContext,
) -> Server:
    """Compose allowlisted public owners without opening or probing their targets.

    Capability ``composition`` takes ``appcompose.mcp.Settings``; ``data`` takes
    ``azdata.DataConnector``; ``model`` takes ``llm_interface.Connection``.
    ``inventory`` borrows ``resource_explorer.InventoryService`` and its probes.
    ``recovery`` takes ``workrecovery.mcp.RecoveryTools`` with an explicit absolute
    recovery root and separate native stage/inspect/payload-read grants.
    Grants are exact MCP tool names, defaulting to none.
    Configuration is copied before activation;
    the context principal must match the trusted host principal. No caller-supplied
    configuration document is resolved into executable code.
    """
    if not isinstance(context, ExecutionContext) or principal != context.caller.principal:
        raise FrameworkError("principal_mismatch", category="denied")
    configured = dict(bindings)
    if set(grants) - set(configured):
        raise FrameworkError("unknown_grant_binding", category="denied")
    schemas: dict[str, types.Tool] = {}
    handlers: dict[tuple[str, str], Callable[..., Any]] = {}
    declared_tools: set[str] = set()
    for binding_id, binding in configured.items():
        if not isinstance(binding, Binding):
            raise FrameworkError("binding_type_mismatch")
        if binding.capability == "composition":
            tools, operations = _composition(binding.value)
        elif binding.capability == "data":
            from azdata.mcp_adapter import bind_tools

            tools, operations = bind_tools(binding.value)
        elif binding.capability == "model":
            from llm_interface.mcp_adapter import bind_tools

            tools, operations = bind_tools(binding.value)
        elif binding.capability == "inventory":
            from resource_explorer.mcp_adapter import bind_tools

            tools, operations = bind_tools(binding.value)
        elif binding.capability == "recovery":
            tools, operations = _recovery(binding.value)
        else:
            raise FrameworkError("unsupported_capability")
        declared_tools.update(operations)
        allowed = grants.get(binding_id, ())
        if isinstance(allowed, str) or set(allowed) - set(operations):
            raise FrameworkError("invalid_tool_grant", category="denied")
        for tool in tools:
            if tool.name not in allowed:
                continue
            handlers[tool.name, binding_id] = operations[tool.name]
            if tool.name not in schemas:
                schema = tool.model_copy(deep=True)
                schema.inputSchema["properties"]["binding"] = {"type": "string", "enum": []}
                schema.inputSchema["required"] = ["binding", *schema.inputSchema.get("required", [])]
                schemas[tool.name] = schema
            schemas[tool.name].inputSchema["properties"]["binding"]["enum"].append(binding_id)
    framework = Framework(configured)

    @asynccontextmanager
    async def lifespan(server: Server):
        try:
            await framework.__aenter__()
            yield framework
        finally:
            with anyio.CancelScope(shield=True):
                await framework.aclose()

    server = Server("agentcraft", version="0.1.0", lifespan=lifespan)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [tool.model_copy(deep=True) for tool in schemas.values()]

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        binding_id = arguments.get("binding")
        binding = configured.get(binding_id) if isinstance(binding_id, str) else None
        capability_id = binding.capability if binding else "framework"
        operation = name if name in declared_tools else "unknown_tool"
        dispatched = False
        try:
            handler = handlers.get((name, binding_id)) if binding else None
            if handler is None:
                raise FrameworkError("tool_not_granted", category="denied")
            request = {key: value for key, value in arguments.items() if key != "binding"}
            with context.activate():
                context.budget.reserve("tool_calls")
                with anyio.fail_after(context.remaining()):
                    dispatched = True
                    if inspect.iscoroutinefunction(handler):
                        payload = await handler(**request)
                    else:
                        payload = await anyio.to_thread.run_sync(partial(handler, **request), abandon_on_cancel=False)
                    await anyio.lowlevel.checkpoint_if_cancelled()
            return _correlate_result(
                payload, capability_id=capability_id, operation=operation, run_id=context.run_id,
            )
        except FrameworkError as error:
            failure = error.failure
            refused = failure.category in {"config", "invalid", "denied", "unsupported"}
            effect = failure.effect if dispatched else "none"
            if dispatched and not refused and effect == "none":
                effect = "unknown"
            retry = "never" if failure.category == "unsupported" else (
                "safe_after_correction" if refused or not dispatched else (
                    "read_back_first" if operation == "recovery_stage" and effect != "none" else "unspecified"
                )
            )
            payload = {"error": replace(
                failure, effect=effect, retry=retry,
            ).to_dict()}
        except DocumentInvalid as error:
            unsupported = isinstance(error, UnsupportedVersion)
            code = "unsupported_version" if unsupported else (
                "credential_shaped" if isinstance(error, CredentialShaped) else "invalid_document"
            )
            payload = {"error": FailureInfo(
                code, category="unsupported" if unsupported else "invalid",
                field=_document_field(error.field), retry="never" if unsupported else "safe_after_correction",
                action="Use a supported document version." if unsupported else "Correct the named document field.",
            ).to_dict()}
        except CompositionError:
            payload = {"error": FailureInfo(
                "composition_failed", effect="unknown", retry="unspecified",
                action="Inspect composition lifecycle state before another attempt.",
            ).to_dict()}
        except PermissionError:
            payload = {"error": FailureInfo(
                "permission_denied", category="denied", retry="safe_after_correction",
                action="Ask the host to review the operation grant and configured bounds.",
            ).to_dict()}
        except TimeoutError:
            payload = {"error": FailureInfo(
                "deadline_exceeded", category="interrupted", effect="unknown" if dispatched else "none",
                retry="read_back_first" if operation == "recovery_stage" and dispatched else "unspecified",
                action="Inspect operation state before another attempt; timeout does not prove no effects.",
            ).to_dict()}
        except Exception:
            payload = {"error": FailureInfo(
                "operation_failed", effect="unknown" if dispatched else "none",
                retry="read_back_first" if operation == "recovery_stage" and dispatched else "unspecified",
                action="Inspect operation state and the public contract before another attempt.",
            ).to_dict()}
        await anyio.lowlevel.checkpoint_if_cancelled()
        return _correlate_result(
            payload, capability_id=capability_id, operation=operation, run_id=context.run_id,
        )

    return server


async def _stdio() -> None:
    from appcompose.mcp import TOOLS, Settings

    principal = "offline-composition"
    server = create_server(
        bindings={"composition": Binding("composition", Settings())},
        grants={"composition": tuple(tool.name for tool in TOOLS)},
        principal=principal,
        context=ExecutionContext.create(CallerContext(principal),
                                        limits={"tool_calls": 1000}, timeout_seconds=3600),
    )
    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


def main() -> int:
    """Run the offline composition-only stdio host; no configuration factory."""
    asyncio.run(_stdio())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())