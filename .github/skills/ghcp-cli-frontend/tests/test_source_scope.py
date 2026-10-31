import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from copilot_terminal import ProviderConfig, TerminalService

HEADERS = {"host": "localhost:8080", "origin": "http://localhost:8080",
           "content-type": "application/json", "x-copilot-terminal": "1"}


class SourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.service = TerminalService(
            sys.executable, ProviderConfig("https://example.test", "model"), Path(self.directory.name),
            lambda: ("unit-test-credential", time.time() + 3600), path="/usr/bin:/bin",
        )
        self.source = "approved/example.py"
        self.loader = Mock(return_value=(self.source, b"print(1)\n"))
        self.service.source_loader = self.loader
        self.workspace = Path(self.directory.name) / "workspace"
        self.workspace.mkdir()
        self.record = SimpleNamespace(terminal=SimpleNamespace(workspace=self.workspace))

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def test_host_scope_refusal_prevents_staging(self):
        self.loader.side_effect = PermissionError("outside host-approved source scope")
        with self.assertRaises(PermissionError):
            self.service._source(self.record, {"source": {"uid": "unapproved", "path": self.source}})
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_selected_file_is_staged_only_in_private_workspace(self):
        selection = {"uid": "a" * 32, "path": self.source}
        result = self.service._source(self.record, {"source": selection})
        target = self.workspace / result["path"]
        self.assertEqual(target.read_bytes(), b"print(1)\n")
        self.assertEqual(target.stat().st_mode & 0o777, 0o400)
        self.loader.assert_called_once_with(selection)

    def test_missing_source_loader_and_unknown_upload_are_refused(self):
        self.service.source_loader = None
        with self.assertRaises(ValueError):
            self.service._source(self.record, {"source": {"path": self.source}})
        self.loader.assert_not_called()
        with patch("copilot_terminal.service.PtySession"):
            status, started = self.service.handle("start", HEADERS, {})
            self.assertEqual(status, 201)
            self.assertEqual(self.service.handle("upload", HEADERS, started)[0], 404)

    def test_host_returned_paths_cannot_escape_workspace(self):
        for relative in ("../private.py", "/private.py", "folder/../../private.py", "folder\\private.py", "folder//file.py"):
            self.loader.return_value = (relative, b"fixture")
            with self.subTest(path=relative), self.assertRaises(ValueError):
                self.service._source(self.record, {"source": {"path": relative}})
        outside = Path(self.directory.name) / "outside"
        outside.mkdir()
        (self.workspace / "sources").symlink_to(outside, target_is_directory=True)
        self.loader.return_value = (self.source, b"fixture")
        with self.assertRaises(ValueError):
            self.service._source(self.record, {"source": {"path": self.source}})
        self.assertEqual(list(outside.iterdir()), [])

    def test_changed_local_source_copy_is_not_silently_replaced(self):
        selection = {"source": {"path": self.source}}
        self.service._source(self.record, selection)
        self.loader.return_value = (self.source, b"different source bytes")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.service._source(self.record, selection)
        self.assertEqual((self.workspace / "sources" / self.source).read_bytes(), b"print(1)\n")

    def test_credential_failures_do_not_leak_detail(self):
        with patch.object(self.service, "token_provider", side_effect=RuntimeError("unit-test-credential")):
            status, body = self.service.handle("start", HEADERS, {})
        self.assertEqual(status, 503)
        self.assertNotIn("unit-test-credential", str(body))


if __name__ == "__main__":
    unittest.main()