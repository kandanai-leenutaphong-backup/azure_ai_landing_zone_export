import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from copilot_terminal import ProviderConfig, TerminalService
from copilot_terminal import LaunchOptions

HEADERS = {"host": "127.0.0.1:8080", "origin": "http://127.0.0.1:8080",
           "content-type": "application/json", "x-copilot-terminal": "1"}


class OptionsTests(unittest.TestCase):
    def test_modes_do_not_grant_permissions(self):
        for mode in ("interactive", "plan", "autopilot"):
            options = LaunchOptions(mode=mode, max_autopilot_continues=2, session_name="Review local changes",
                                    reasoning_effort="high", screen_reader=True, mouse=False)
            arguments = options.arguments()
            self.assertEqual(arguments[:2], ["--mode", mode])
            self.assertIn("--screen-reader", arguments)
            self.assertIn("--no-mouse", arguments)
            self.assertEqual("--max-autopilot-continues" in arguments, mode == "autopilot")
            self.assertFalse(any(value in {"--allow-all", "--allow-all-tools", "--allow-all-paths", "--allow-all-urls", "--no-ask-user", "--yolo"} for value in arguments))

    def test_invalid_options_refuse_before_launch(self):
        for options in ({"mode": "--allow-all"}, {"max_autopilot_continues": True},
                        {"max_autopilot_continues": 21}, {"reasoning_effort": "unbounded"},
                        {"session_name": "--yolo"}, {"session_name": "name\ncommand"}, {"mouse": "true"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                LaunchOptions(**options)

    def test_documented_provider_variants_and_token_limits(self):
        for provider_type in ("openai", "azure", "anthropic"):
            provider = ProviderConfig("https://provider.example.test", "deployment", provider_type=provider_type,
                                      wire_api="completions", max_prompt_tokens=16000, max_output_tokens=1024)
            environment = provider.environment("fixture-credential", Path("/tmp/private-home"), "/bin")
            self.assertEqual(environment["COPILOT_PROVIDER_TYPE"], provider_type)
            self.assertEqual(environment["COPILOT_PROVIDER_MAX_OUTPUT_TOKENS"], "1024")
            self.assertNotIn("GITHUB_TOKEN", environment)
        for options in ({"provider_type": "unknown"}, {"wire_api": "unknown"},
                        {"max_output_tokens": 0}, {"max_prompt_tokens": True}, {"model_id": ""}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ProviderConfig("https://provider.example.test", "deployment", **options)
        with self.assertRaises(ValueError):
            ProviderConfig("https://provider.example.test/v1", "deployment", provider_type="azure").environment("fixture", Path("/tmp"), "/bin")

    def test_browser_cannot_change_host_policy_and_remote_export_stays_off(self):
        with tempfile.TemporaryDirectory() as directory:
            service = TerminalService(sys.executable, ProviderConfig("https://provider.example.test", "deployment"),
                                      Path(directory), lambda: ("fixture-credential", time.time() + 600),
                                      path="/bin", launch=LaunchOptions(mode="plan", reasoning_effort="low"))
            try:
                with patch("copilot_terminal.service.PtySession") as launcher:
                    for payload in ({"mode": "autopilot"}, {"cli": "/bin/sh"}, {"args": ["--allow-all"]}):
                        self.assertEqual(service.handle("start", HEADERS, payload)[0], 400)
                    launcher.assert_not_called()
                    status, started = service.handle("start", HEADERS, {})
                    self.assertEqual(status, 201)
                    arguments = launcher.call_args.args[0]
                    self.assertIn("--no-remote-export", arguments)
                    self.assertIn("--secret-env-vars=COPILOT_PROVIDER_BEARER_TOKEN", arguments)
                    self.assertEqual(started["launch"]["mode"], "plan")
                    self.assertNotIn("fixture-credential", str(started))
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)