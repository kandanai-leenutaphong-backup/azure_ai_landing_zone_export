from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from azure.ai.contentunderstanding.aio import ContentUnderstandingClient
from azure.core.exceptions import ServiceRequestError, ServiceResponseError
from azure.core.pipeline.policies import AsyncHTTPPolicy


API_VERSION = "2025-11-01"
ANALYZER = "prebuilt-layout"
MAX_INPUT_BYTES = 10_000_000


class Refusal(ValueError):
    pass


class ExtractionFailed(RuntimeError):
    pass


def validate_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.services\.ai\.azure\.com", parsed.netloc)
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise Refusal("Use an explicit public Azure Foundry resource HTTPS endpoint without credentials, paths or queries")
    return endpoint.rstrip("/")


def source_bytes(source: Path, expected_sha256: str) -> bytes:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise Refusal("An explicit lowercase source SHA-256 is required")
    if source.is_symlink() or not source.is_file():
        raise Refusal("Input must be an existing regular local PDF, not a symlink or URL")
    with source.open("rb") as stream:
        payload = stream.read(MAX_INPUT_BYTES + 1)
    if not payload.startswith(b"%PDF-") or len(payload) > MAX_INPUT_BYTES:
        raise Refusal("Input must have PDF magic bytes and fit the documented byte limit")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise Refusal("Source bytes differ from the explicitly authorized SHA-256")
    return payload


def validate_result(result: dict[str, Any]) -> tuple[str, int]:
    if result.get("analyzerId") != ANALYZER or result.get("apiVersion") != API_VERSION:
        raise Refusal("Native result does not match the requested analyzer and API version")
    contents = result.get("contents")
    if not isinstance(contents, list) or not contents:
        raise Refusal("Native result contains no document content")
    pieces = []
    pages = 0
    for content in contents:
        if not isinstance(content, dict) or content.get("kind") != "document":
            raise Refusal("Native result contains an unexpected non-document content block")
        text = content.get("markdown")
        page_list = content.get("pages")
        if not isinstance(text, str) or not text.strip() or not isinstance(page_list, list) or not page_list:
            raise Refusal("Native result contains empty Markdown or no observed pages")
        if not all(isinstance(page, dict) and type(page.get("pageNumber")) is int and page["pageNumber"] > 0 for page in page_list):
            raise Refusal("Native result contains invalid page identifiers")
        pieces.append(text)
        pages += len(page_list)
    return "\n\n".join(pieces), pages


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


async def extract(
    *,
    endpoint: str,
    credential: Any,
    source: Path,
    expected_sha256: str,
    output: Path,
    allow_analysis: bool = False,
    processing_location: str = "geography",
    timeout_seconds: float = 900,
    transport: Any = None,
) -> dict[str, Any]:
    if not allow_analysis:
        raise Refusal("Paid document analysis requires an explicit host authorization decision")
    endpoint = validate_endpoint(endpoint)
    if processing_location not in {"geography", "dataZone", "global"}:
        raise Refusal("Processing location must be an explicit supported data-boundary choice")
    if not 0 < timeout_seconds <= 900:
        raise Refusal("Timeout must be greater than zero and at most 900 seconds")
    payload = source_bytes(source, expected_sha256)
    if output.exists() or output.is_symlink():
        raise Refusal("Output already exists; preserve prior evidence and select a new directory")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "method": "azure-content-understanding-native-sdk",
        "execution": "native-sdk",
        "status": "submitting",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input": {"file": source.name, "sha256": expected_sha256, "bytes": len(payload)},
        "provider": {"endpoint": endpoint, "api_version": API_VERSION, "analyzer_id": ANALYZER, "processing_location": processing_location},
        "versions": {"python": platform.python_version(), **{package: version(package) for package in ("azure-ai-contentunderstanding", "azure-core", "azure-identity", "aiohttp")}},
        "operation_id": None,
        "outputs": {},
        "cost_usd": None,
        "error": None,
    }
    write_json(output / "request.json", receipt)
    captured: dict[str, Any] = {}
    accepted = False

    async def retain_response(response: Any) -> None:
        nonlocal accepted
        accepted = accepted or response.http_response.status_code == 202
        location = response.http_response.headers.get("Operation-Location")
        if location:
            parsed = urlsplit(location)
            operation = parsed.path.rsplit("/", 1)[-1]
            if (
                parsed.scheme != "https"
                or parsed.netloc != urlsplit(endpoint).netloc
                or not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", operation)
                or parsed.path != f"/contentunderstanding/analyzerResults/{operation}"
                or parse_qs(parsed.query) != {"api-version": [API_VERSION]}
                or parsed.fragment
            ):
                raise Refusal("Native polling URL escaped the explicitly authorized endpoint")
            if receipt["operation_id"] is None:
                receipt["operation_id"] = operation
                write_json(output / "operation.json", {"operation_id": operation, "endpoint": endpoint, "api_version": API_VERSION})
            elif receipt["operation_id"] != operation:
                raise Refusal("Native response changed the submitted operation ID")
        await response.http_response.read()
        try:
            native = response.http_response.json()
        except (ValueError, AttributeError):
            return
        if isinstance(native, dict) and "status" in native:
            captured.clear()
            captured.update(native)

    class CapturePolicy(AsyncHTTPPolicy):
        async def send(self, request: Any) -> Any:
            response = await self.next.send(request)
            await retain_response(response)
            return response

    options: dict[str, Any] = {
        "api_version": API_VERSION,
        "retry_total": 0,
        "connection_timeout": 15,
        "read_timeout": 90,
        "polling_interval": 3,
        "per_call_policies": [CapturePolicy()],
    }
    if transport is not None:
        options["transport"] = transport
    try:
        async with asyncio.timeout(timeout_seconds):
            async with ContentUnderstandingClient(endpoint, credential, **options) as client:
                poller = await client.begin_analyze_binary(
                    ANALYZER,
                    binary_input=payload,
                    content_type="application/pdf",
                    processing_location=processing_location,
                )
                if receipt["operation_id"] != poller.operation_id:
                    raise Refusal("SDK operation ID does not match the retained native response")
                result = await poller.result()
                native_result = result.as_dict()
                if not captured or str(captured.get("status", "")).lower() != "succeeded":
                    raise Refusal("No complete native service envelope was captured")
                write_json(output / "native.json", captured)
                receipt["outputs"]["native"] = "native.json"
                write_json(output / "sdk-result.json", native_result)
                receipt["outputs"]["sdk_result"] = "sdk-result.json"
                markdown, pages = validate_result(native_result)
                with (output / "content.md").open("x", encoding="utf-8", newline="") as stream:
                    stream.write(markdown)
                receipt["outputs"]["markdown"] = "content.md"
                receipt["input"]["pages"] = pages
                receipt["usage"] = captured.get("usage")
                receipt["warnings"] = native_result.get("warnings", [])
                receipt["status"] = "succeeded"
    except Exception as error:
        if captured and "native" not in receipt["outputs"]:
            write_json(output / "native.json", captured)
            receipt["outputs"]["native"] = "native.json"
        uncertain = isinstance(error, (TimeoutError, ServiceRequestError, ServiceResponseError))
        uncertain = uncertain or (accepted and str(captured.get("status", "")).lower() not in {"succeeded", "failed", "canceled"})
        receipt["status"] = "incomplete" if uncertain and receipt["operation_id"] else "unconfirmed" if uncertain else "failed"
        receipt["error"] = {
            "type": type(error).__name__,
            "message": "Analysis did not produce verified complete output. Preserve this directory and check the operation before retrying; remote cancellation and zero charges are not implied.",
        }
        receipt["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "receipt.json", receipt)
        raise ExtractionFailed("Analysis incomplete; inspect the receipt and recorded operation before retrying") from None
    receipt["elapsed_seconds"] = time.monotonic() - started
    write_json(output / "receipt.json", receipt)
    for name in receipt["outputs"].values():
        if not (output / name).is_file() or (output / name).stat().st_size == 0:
            raise ExtractionFailed("Result read-back failed")
    if json.loads((output / "native.json").read_text(encoding="utf-8")) != captured:
        raise ExtractionFailed("Native result read-back differs")
    return receipt


def identifier(value: str) -> str:
    try:
        valid = str(UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError("Identity identifiers must be canonical UUIDs")
    return value


async def run(options: argparse.Namespace) -> None:
    from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential

    if options.identity == "cli" and not options.tenant_id:
        raise Refusal("Azure CLI identity requires an explicit tenant ID")
    if options.identity == "managed" and options.tenant_id:
        raise Refusal("A workload managed identity does not use the CLI tenant option")
    if options.identity == "cli" and options.client_id:
        raise Refusal("A managed identity client ID cannot configure Azure CLI identity")
    credential = AzureCliCredential(tenant_id=options.tenant_id) if options.identity == "cli" else ManagedIdentityCredential(client_id=options.client_id)
    async with credential:
        await extract(
            endpoint=options.endpoint, credential=credential, source=options.input,
            expected_sha256=options.input_sha256, output=options.output,
            allow_analysis=options.allow_analysis, processing_location=options.processing_location,
            timeout_seconds=options.timeout_seconds,
        )
    print(f"Verified extraction: {options.output / 'receipt.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Native CU layout recipe; explicit paid-analysis authorization required")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--identity", choices=("cli", "managed"), default="cli")
    parser.add_argument("--tenant-id", type=identifier)
    parser.add_argument("--client-id", type=identifier)
    parser.add_argument("--processing-location", choices=("geography", "dataZone", "global"), required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--allow-analysis", action="store_true")
    try:
        asyncio.run(run(parser.parse_args()))
    except (Refusal, ExtractionFailed, OSError) as error:
        print(f"{type(error).__name__}: extraction refused or incomplete; check input/target authorization and any retained receipt")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())