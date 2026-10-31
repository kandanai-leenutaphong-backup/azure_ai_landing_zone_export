import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot_terminal import ProviderConfig, TerminalService

HEADERS = {"host": "127.0.0.1:8080", "origin": "http://127.0.0.1:8080",
           "content-type": "application/json", "x-copilot-terminal": "1"}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.provider = ProviderConfig("https://example.test", "test-deployment")
        self.service = TerminalService(
            sys.executable, self.provider, Path(self.directory.name),
            lambda: ("unit-test-credential", time.time() + 3600), path="/usr/bin:/bin",
        )

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def test_cross_origin_and_non_json_refuse_without_launching(self):
        with patch("copilot_terminal.service.PtySession") as launcher:
            for changes in ({"origin": "https://untrusted.test"}, {"host": "untrusted.test"},
                            {"x-copilot-terminal": ""}, {"content-type": "text/plain"},
                            {"sec-fetch-site": "cross-site"}, {"origin": "null"}):
                status, _ = self.service.handle("start", HEADERS | changes, {})
                self.assertEqual(status, 403)
            launcher.assert_not_called()

    def test_interactive_argv_private_environment_and_session_ownership(self):
        with patch("copilot_terminal.service.PtySession") as launcher:
            status, started = self.service.handle("start", HEADERS, {})
            self.assertEqual(status, 201)
            argv, workspace, environment = launcher.call_args.args
            self.assertNotIn("-p", argv)
            self.assertNotIn("--allow-all-tools", argv)
            self.assertIn("--secret-env-vars=COPILOT_PROVIDER_BEARER_TOKEN", argv)
            self.assertEqual(environment["COPILOT_PROVIDER_WIRE_MODEL"], "test-deployment")
            self.assertNotIn("AZURE_CLIENT_SECRET", environment)
            self.assertNotIn("GITHUB_TOKEN", environment)
            self.assertTrue(environment["COPILOT_HOME"].startswith(self.directory.name))
            self.assertNotIn("unit-test-credential", str(started))
            self.assertTrue(workspace.is_relative_to(Path(self.directory.name)))
            for action in ("output", "input", "resize", "stop", "source"):
                status, _ = self.service.handle(action, HEADERS, started | {"key": "wrong"})
                self.assertEqual(status, 404)
            launcher.return_value.write.assert_not_called()
            status, _ = self.service.handle("input", HEADERS, started | {"data": "/help\r"})
            self.assertEqual(status, 200)
            launcher.return_value.write.assert_called_once_with("/help\r")

    def test_session_limit_and_expired_token_refuse(self):
        self.service.max_sessions = 1
        with patch("copilot_terminal.service.PtySession"):
            self.assertEqual(self.service.handle("start", HEADERS, {})[0], 201)
            self.assertEqual(self.service.handle("start", HEADERS, {})[0], 400)
        self.service.close()
        self.service.token_provider = lambda: ("test", time.time())
        self.assertEqual(self.service.handle("start", HEADERS, {})[0], 400)

    def test_endpoint_validation(self):
        for endpoint in ("http://example.test", "https://user:secret@example.test", ""):
            with self.assertRaises(ValueError):
                ProviderConfig(endpoint, "test").environment("token", Path("/tmp"), "/bin")

    def test_task_credential_is_private_and_cannot_control_a_terminal(self):
        calls = []
        self.service.task_operations["publish"] = lambda workspace, payload, headers: (
            calls.append(workspace) or {"stored": True})
        self.service.operations["prepare"] = lambda workspace, payload, headers: {"ready": True}
        self.service.workspace_initializer = lambda workspace: (workspace / "skill.txt").write_text("actual skill")
        with patch("copilot_terminal.service.PtySession") as launcher:
            status, started = self.service.handle("start", HEADERS, {})
            self.assertEqual(status, 201)
            workspace = Path(started["workspace"])
            launcher.return_value.workspace = workspace
            access = workspace.parent / "task-access.json"
            credential = json.loads(access.read_text())
            self.assertEqual(access.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(credential["task_key"], json.dumps(started))
            self.assertIn(credential["task_key"], launcher.call_args.kwargs["secrets"])
            self.assertEqual((workspace / "skill.txt").read_text(), "actual skill")
            self.assertEqual(self.service.handle("publish", HEADERS, credential)[0], 200)
            self.assertEqual(calls, [workspace])
            for action in ("input", "stop", "source", "prepare"):
                self.assertEqual(self.service.handle(action, HEADERS, credential)[0], 404)
            self.assertEqual(self.service.handle("publish", HEADERS, credential | {"task_key": "wrong"})[0], 404)
            self.assertEqual(self.service.handle("publish", HEADERS | {"origin": "https://other.test"}, credential)[0], 403)
            self.assertEqual(self.service.handle("publish", HEADERS, credential | {"session_id": "other"})[0], 404)
            self.assertEqual(self.service.handle("stop", HEADERS, started)[0], 200)
            self.assertEqual(self.service.handle("publish", HEADERS, credential)[0], 404)
            self.assertEqual(calls, [workspace])


if __name__ == "__main__":
    unittest.main()