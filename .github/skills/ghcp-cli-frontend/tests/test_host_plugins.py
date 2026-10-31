import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot_terminal import ProviderConfig, TerminalService

HEADERS = {"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765",
           "content-type": "application/json", "x-copilot-terminal": "1"}


class HostPlugins(unittest.TestCase):
    def test_native_plugin_and_helper_are_host_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "plugin"
            plugin.mkdir()
            (plugin / "plugin.json").write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "fixture",
            }))
            service = TerminalService(sys.executable, ProviderConfig("https://example.test", "model"),
                                      root / "sessions", lambda: ("fixture-value", time.time() + 600),
                                      path="/bin", plugin_dirs=(plugin,))
            def initialize(workspace):
                helper = workspace / "opt"
                helper.write_text("#!/bin/sh\nexit 0\n")
                helper.chmod(0o700)
            service.workspace_initializer = initialize
            service.allowed_executables = lambda workspace: (workspace / "opt",)
            try:
                with patch("copilot_terminal.service.PtySession") as launcher:
                    self.assertEqual(service.handle("start", HEADERS, {"plugin_dirs": ["/untrusted"]})[0], 400)
                    launcher.assert_not_called()
                    self.assertEqual(service.handle("start", HEADERS, {})[0], 201)
                    argv = launcher.call_args.args[0]
                    self.assertEqual(argv[argv.index("--plugin-dir") + 1], str(plugin))
                    self.assertIn("--allow-tool=shell(./opt)", argv)
                    self.assertNotIn("--allow-all-tools", argv)
                    self.assertIn("--no-remote-export", argv)
            finally:
                service.close()

    def test_outside_symlink_and_pattern_helpers_refuse_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.write_text("#!/bin/sh\nexit 0\n")
            outside.chmod(0o700)
            service = TerminalService(sys.executable, ProviderConfig("https://example.test", "model"),
                                      root / "sessions", lambda: ("fixture-value", time.time() + 600), path="/bin")
            try:
                for kind in ("outside", "symlink", "glob"):
                    def initialize(workspace):
                        if kind == "symlink":
                            (workspace / "helper").symlink_to(outside)
                        elif kind == "glob":
                            (workspace / "helper*").write_text("fixture")
                            (workspace / "helper*").chmod(0o700)
                    service.workspace_initializer = initialize
                    service.allowed_executables = lambda workspace: (outside if kind == "outside" else workspace / ("helper*" if kind == "glob" else "helper"),)
                    with self.subTest(kind=kind), patch("copilot_terminal.service.PtySession") as launcher:
                        self.assertEqual(service.handle("start", HEADERS, {})[0], 400)
                        launcher.assert_not_called()
            finally:
                service.close()