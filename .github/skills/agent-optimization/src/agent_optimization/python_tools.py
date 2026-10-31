from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from . import _local_query as local_query


class PythonToolRunner:
    def __init__(self, executable: str, *, timeout_seconds: float = 8.0):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def validate(code: str) -> None:
        if not isinstance(code, str) or not 1 <= len(code) <= 24_000:
            raise ValueError("Python source must contain 1 to 24000 characters")
        try:
            module = ast.parse(code, filename="agent_tool.py")
        except SyntaxError as error:
            raise ValueError(f"Python syntax error on line {error.lineno}: {error.msg}") from error
        entries = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "run"]
        if len(entries) != 1 or len(entries[0].args.args) != 1 or entries[0].args.args[0].arg != "ctx":
            raise ValueError("Python tool must define one run(ctx) function")

    def run(self, code: str, database: Path, scope: dict | None = None) -> dict:
        self.validate(code)
        if not Path(self.executable).is_file():
            raise ValueError("Python isolation unavailable; supply an executable Bubblewrap path")
        worker = Path(__file__).with_name("python_worker.py")
        command = [self.executable, "--unshare-all", "--unshare-user", "--die-with-parent", "--cap-drop", "ALL",
                   "--disable-userns", "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                   "--ro-bind", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
                   "--tmpfs", "/tmp", "--chdir", "/tmp",
                   "--ro-bind", str(database.resolve()), "/case.sqlite",
                   "--ro-bind", str(worker), "/runtime/worker.py",
                   "--ro-bind", str(Path(local_query.__file__).parent), "/runtime/_local_query",
                   "/usr/bin/python3", "-I", "-S", "-B", "/runtime/worker.py"]
        payload = json.dumps({"code": code, "scope": scope or {}}).encode()
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                       env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, start_new_session=True)
            try:
                process.communicate(payload, timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise ValueError("Python tool exceeded its execution deadline") from error
            output.seek(0)
            raw = output.read(65_537)
            if process.returncode != 0:
                errors.seek(0)
                detail = errors.read(400).decode(errors="replace").strip()
                raise ValueError(f"Isolated Python tool failed ({process.returncode}): {detail}")
            if len(raw) > 24_000:
                raise ValueError("Python tool output exceeds 20 KB")
            try:
                envelope = json.loads(raw)
            except (ValueError, UnicodeError) as error:
                raise ValueError("Python tool did not return a structured result") from error
            if not envelope.get("ok"):
                raise ValueError(envelope.get("error", "Python tool failed"))
            return envelope["result"]