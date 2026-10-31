import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from azure.core.credentials import AccessToken
from azure.core.exceptions import ResponseNotReadError
from azure.core.pipeline.transport import AsyncHttpResponse, AsyncHttpTransport
from azure.core.utils import CaseInsensitiveDict


SPEC = importlib.util.spec_from_file_location("skill_extract", Path(__file__).resolve().parents[1] / "scripts" / "extract.py")
recipe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe)

HOST = "https://synthetic-resource.services.ai.azure.com"
OPERATION = "ba7c903d-568f-47ea-a205-39d39ef0c8c6"
PAYLOAD = b"%PDF-1.7\nsynthetic offline fixture, not an actual document"


class Credential:
    def __init__(self):
        self.calls = 0

    async def get_token(self, *scopes, **kwargs):
        self.calls += 1
        return AccessToken("offline-not-a-secret", 4102444800)


class Response(AsyncHttpResponse):
    def __init__(self, request, status, body, headers):
        super().__init__(request, None)
        self.status_code = status
        self.headers = CaseInsensitiveDict({"Content-Type": "application/json", **headers})
        self.content_type = "application/json"
        self.reason = "offline fixture"
        self._body = json.dumps(body).encode()
        self.was_read = False

    def body(self):
        return self._body

    async def load_body(self):
        return None

    def json(self):
        if not self.was_read:
            raise ResponseNotReadError()
        return json.loads(self._body)

    async def read(self):
        self.was_read = True
        return self._body

    async def iter_bytes(self):
        yield self._body

    async def iter_raw(self):
        yield self._body


class Transport(AsyncHttpTransport):
    def __init__(self, replies):
        self.replies = replies
        self.requests = []
        self.closed = False

    async def open(self):
        return None

    async def close(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def send(self, request, **kwargs):
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("unexpected native SDK request")
        status, body, headers = self.replies.pop(0)
        return Response(request, status, body, headers)

    async def sleep(self, duration):
        return None


def native_result():
    return {
        "id": OPERATION, "status": "Succeeded",
        "result": {"analyzerId": "prebuilt-layout", "apiVersion": "2025-11-01", "stringEncoding": "codePoint", "contents": [{"kind": "document", "markdown": "# Synthetic\n597 MW", "pages": [{"pageNumber": 1}], "tables": []}]},
        "usage": {"documentPagesStandard": 1},
    }


class RecipeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "fixture.pdf"
        self.source.write_bytes(PAYLOAD)
        self.digest = hashlib.sha256(PAYLOAD).hexdigest()
        self.credential = Credential()

    def tearDown(self):
        self.temporary.cleanup()

    async def invoke(self, transport, **overrides):
        options = dict(endpoint=HOST, credential=self.credential, source=self.source, expected_sha256=self.digest, output=self.root / "result", allow_analysis=True, processing_location="geography", transport=transport)
        options.update(overrides)
        return await recipe.extract(**options)

    async def test_native_sdk_binary_poll_and_complete_artifact(self):
        native = native_result()
        transport = Transport([(202, {}, {"Operation-Location": f"{HOST}/contentunderstanding/analyzerResults/{OPERATION}?api-version=2025-11-01"}), (200, native, {})])
        receipt = await self.invoke(transport)
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(receipt["input"]["pages"], 1)
        self.assertEqual(receipt["operation_id"], OPERATION)
        self.assertEqual(json.loads((self.root / "result" / "native.json").read_text()), native)
        self.assertEqual((self.root / "result" / "content.md").read_text(), "# Synthetic\n597 MW")
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0].method, "POST")
        self.assertIn("prebuilt-layout:analyzeBinary", transport.requests[0].url)
        self.assertIn("api-version=2025-11-01", transport.requests[0].url)
        self.assertIn("processingLocation=geography", transport.requests[0].url)
        self.assertEqual(transport.requests[0].content, PAYLOAD)
        self.assertTrue(transport.closed)

    async def test_permission_refusal_precedes_credentials_and_output(self):
        transport = Transport([])
        with self.assertRaises(recipe.Refusal):
            await self.invoke(transport, allow_analysis=False)
        self.assertEqual(self.credential.calls, 0)
        self.assertEqual(transport.requests, [])
        self.assertFalse((self.root / "result").exists())

    async def test_hash_refusal_before_submit(self):
        transport = Transport([])
        with self.assertRaises(recipe.Refusal):
            await self.invoke(transport, expected_sha256="0" * 64)
        self.assertEqual(transport.requests, [])

    async def test_byte_limit_refuses_before_submit(self):
        transport = Transport([])
        with patch.object(recipe, "MAX_INPUT_BYTES", len(PAYLOAD) - 1):
            with self.assertRaises(recipe.Refusal):
                await self.invoke(transport)
        self.assertEqual(transport.requests, [])
        self.assertEqual(self.credential.calls, 0)

    async def test_overwrite_refusal(self):
        folder = self.root / "result"
        folder.mkdir()
        (folder / "precious.txt").write_text("preserve")
        with self.assertRaises(recipe.Refusal):
            await self.invoke(Transport([]))
        self.assertEqual((folder / "precious.txt").read_text(), "preserve")

    async def test_target_refusals_before_credentials(self):
        for endpoint in ("http://synthetic-resource.services.ai.azure.com", "https://other.invalid", HOST + "?key=secret", HOST + "/contentunderstanding", "https://name:secret@synthetic-resource.services.ai.azure.com", HOST + ":443"):
            with self.subTest(endpoint=endpoint), self.assertRaises(recipe.Refusal):
                await self.invoke(Transport([]), endpoint=endpoint)
        self.assertEqual(self.credential.calls, 0)

    async def test_invalid_pdf_and_symlink_refused(self):
        self.source.write_bytes(b"not a pdf")
        with self.assertRaises(recipe.Refusal):
            await self.invoke(Transport([]), expected_sha256=hashlib.sha256(b"not a pdf").hexdigest())
        symlink = self.root / "link.pdf"
        symlink.symlink_to(self.source)
        with self.assertRaises(recipe.Refusal):
            await self.invoke(Transport([]), source=symlink)

    async def test_empty_success_preserves_native_and_fails(self):
        native = native_result()
        native["result"]["contents"][0]["markdown"] = ""
        transport = Transport([(202, {}, {"Operation-Location": f"{HOST}/contentunderstanding/analyzerResults/{OPERATION}?api-version=2025-11-01"}), (200, native, {})])
        with self.assertRaises(recipe.ExtractionFailed):
            await self.invoke(transport)
        receipt = json.loads((self.root / "result" / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["outputs"]["native"], "native.json")
        self.assertFalse((self.root / "result" / "content.md").exists())

    async def test_http_failure_redacts_provider_message(self):
        transport = Transport([(403, {"error": {"code": "Forbidden", "message": "private document or credential detail"}}, {})])
        with self.assertRaises(recipe.ExtractionFailed):
            await self.invoke(transport)
        text = (self.root / "result" / "receipt.json").read_text()
        self.assertNotIn("private document or credential detail", text)
        self.assertEqual(len(transport.requests), 1)

    async def test_operation_location_escape_is_refused_before_poll(self):
        transport = Transport([(202, {}, {"Operation-Location": f"https://unrelated.services.ai.azure.com/contentunderstanding/analyzerResults/{OPERATION}?api-version=2025-11-01"})])
        with self.assertRaises(recipe.ExtractionFailed):
            await self.invoke(transport)
        self.assertEqual(len(transport.requests), 1)
        self.assertTrue(transport.closed)

    async def test_timeout_preserves_operation_and_closes_transport(self):
        class StalledPoll(Transport):
            async def send(self, request, **kwargs):
                if self.requests:
                    await asyncio.Event().wait()
                return await super().send(request, **kwargs)

        transport = StalledPoll([(202, {}, {"Operation-Location": f"{HOST}/contentunderstanding/analyzerResults/{OPERATION}?api-version=2025-11-01"})])
        with self.assertRaises(recipe.ExtractionFailed):
            await self.invoke(transport, timeout_seconds=0.05)
        receipt = json.loads((self.root / "result" / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "incomplete")
        self.assertEqual(receipt["operation_id"], OPERATION)
        self.assertFalse((self.root / "result" / "content.md").exists())
        self.assertTrue(transport.closed)

    async def test_failed_native_result_is_retained(self):
        native = {"id": OPERATION, "status": "Failed", "error": {"code": "InvalidDocument", "message": "synthetic failure"}}
        transport = Transport([(202, {}, {"Operation-Location": f"{HOST}/contentunderstanding/analyzerResults/{OPERATION}?api-version=2025-11-01"}), (200, native, {})])
        with self.assertRaises(recipe.ExtractionFailed):
            await self.invoke(transport)
        self.assertEqual(json.loads((self.root / "result" / "native.json").read_text()), native)
        self.assertEqual(json.loads((self.root / "result" / "receipt.json").read_text())["status"], "failed")

    def test_analyzer_and_empty_page_refusals(self):
        for field, value in (("apiVersion", "future"), ("analyzerId", "prebuilt-documentSearch")):
            native = native_result()["result"]
            native[field] = value
            with self.subTest(field=field), self.assertRaises(recipe.Refusal):
                recipe.validate_result(native)
        native = native_result()["result"]
        native["contents"][0]["pages"] = []
        with self.assertRaises(recipe.Refusal):
            recipe.validate_result(native)

    async def test_timeout_requires_valid_bound(self):
        for timeout in (0, -1, 901, float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(recipe.Refusal):
                await self.invoke(Transport([]), timeout_seconds=timeout)


if __name__ == "__main__":
    unittest.main()