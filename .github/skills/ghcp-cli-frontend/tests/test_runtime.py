import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from copilot_terminal.runtime import PtySession, Redactor


class RuntimeTests(unittest.TestCase):
    def test_redaction_across_reads(self):
        for split in range(1, len("unit-test-credential")):
            redactor = Redactor(("unit-test-credential",))
            result = redactor.feed("prefix unit-test-credential"[:7 + split])
            result += redactor.feed("unit-test-credential"[split:] + " suffix", final=True)
            self.assertEqual(result, "prefix [redacted] suffix")

    def test_partial_secret_at_exit_is_not_leaked(self):
        redactor = Redactor(("unit-test-credential",))
        self.assertEqual(redactor.feed("safe unit-test-cred", final=True), "safe [redacted]")

    def wait_for(self, session, text):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = session.output()
            if text in result["output"]:
                return result
            session.output(result["cursor"], wait=0.1)
        self.fail(f"Missing {text!r}: {session.output()}")

    def test_interactive_tty_input_resize_and_cleanup(self):
        script = (
            "import os,sys; "
            "print('TTY',os.isatty(0),flush=True); "
            "command=input(); print('REPLY',command,os.get_terminal_size(0),flush=True); "
            "input()"
        )
        with tempfile.TemporaryDirectory() as directory:
            session = PtySession([sys.executable, "-u", "-c", script], Path(directory), dict(os.environ))
            try:
                self.wait_for(session, "TTY True")
                session.resize(87, 24)
                session.write("interactive-input\r")
                result = self.wait_for(session, "columns=87, lines=24")
                self.assertIn("REPLY interactive-input", result["output"])
                self.assertEqual(session.output(result["cursor"])["output"], "")
                session.write("\x03")
                self.wait_for(session, "KeyboardInterrupt")
            finally:
                session.close()
            self.assertIsNotNone(session.process.poll())
            self.assertFalse(session.output()["running"])

    def test_invalid_size_refuses_before_spawn(self):
        with self.assertRaises(ValueError):
            PtySession(["does-not-exist"], Path("."), {}, columns=0)

    def test_bounded_output_marks_replay_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            session = PtySession(
                [sys.executable, "-u", "-c", "print('x'*10000);print('END')"],
                Path(directory), dict(os.environ), buffer_limit=1024,
            )
            try:
                result = self.wait_for(session, "END")
                self.assertTrue(result["reset"])
                self.assertLessEqual(len(result["output"]), 1024)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()