from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .options import LaunchOptions
from .runtime import PtySession


@dataclass(frozen=True)
class ProviderConfig:
    endpoint: str
    deployment: str
    model_id: str = "gpt-5.4"
    provider_type: str = "openai"
    wire_api: str = "responses"
    max_prompt_tokens: int | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.provider_type not in {"openai", "azure", "anthropic"}:
            raise ValueError("provider_type must be openai, azure, or anthropic")
        if self.wire_api not in {"responses", "completions"}:
            raise ValueError("wire_api must be responses or completions")
        for value in (self.deployment, self.model_id):
            if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(character) < 32 for character in value):
                raise ValueError("model alias and deployment must be explicit printable identifiers")
        for value in (self.max_prompt_tokens, self.max_output_tokens):
            if value is not None and (type(value) is not int or not 1 <= value <= 2_000_000):
                raise ValueError("provider token limits must be integers in 1..2000000")

    def environment(self, token: str, home: Path, path: str) -> dict[str, str]:
        endpoint = urlsplit(self.endpoint)
        if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username is not None
                or endpoint.password is not None or endpoint.query or endpoint.fragment):
            raise ValueError("A configured HTTPS model endpoint is required")
        if self.provider_type == "azure" and endpoint.path not in {"", "/"}:
            raise ValueError("Azure provider endpoint must be a host URL; the CLI builds its path")
        if not isinstance(token, str) or not token or any(ord(character) < 32 for character in token):
            raise ValueError("Model deployment and server-side access token are required")
        environment = {
            "PATH": path, "HOME": str(home), "SHELL": "/bin/bash",
            "LANG": "C.UTF-8", "TERM": "xterm-256color", "COLORTERM": "truecolor",
            "COPILOT_HOME": str(home / ".copilot"),
            "XDG_CONFIG_HOME": str(home / "config"), "XDG_CACHE_HOME": str(home / "cache"),
            "COPILOT_PROVIDER_BASE_URL": self.endpoint,
            "COPILOT_PROVIDER_TYPE": self.provider_type, "COPILOT_PROVIDER_WIRE_API": self.wire_api,
            "COPILOT_PROVIDER_BEARER_TOKEN": token,
            "COPILOT_PROVIDER_MODEL_ID": self.model_id,
            "COPILOT_PROVIDER_WIRE_MODEL": self.deployment,
        }
        if self.max_prompt_tokens is not None:
            environment["COPILOT_PROVIDER_MAX_PROMPT_TOKENS"] = str(self.max_prompt_tokens)
        if self.max_output_tokens is not None:
            environment["COPILOT_PROVIDER_MAX_OUTPUT_TOKENS"] = str(self.max_output_tokens)
        return environment


@dataclass
class SessionRecord:
    key: str
    terminal: PtySession
    last_seen: float
    task_key: str


class TerminalService:
    def __init__(
        self, cli: str, provider: ProviderConfig, workspace_root: Path,
        token_provider: Callable[[], tuple[str, float]], *, path: str,
        source_loader: Callable[[dict], tuple[str, bytes]] | None = None,
        extra_dirs: tuple[Path, ...] = (),
        max_sessions: int = 4, idle_seconds: float = 300,
        launch: LaunchOptions | None = None,
        plugin_dirs: tuple[Path, ...] = (),
    ):
        self.launch = launch or LaunchOptions()
        self.cli = cli
        self.provider = provider
        self.workspace_root = workspace_root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.workspace_root.stat().st_uid != os.getuid():
            raise PermissionError("Terminal workspace must belong to the host user")
        self.workspace_root.chmod(0o700)
        self.token_provider = token_provider
        self.path = path
        self.source_loader = source_loader
        self.workspace_initializer: Callable[[Path], None] | None = None
        self.allowed_executables: Callable[[Path], tuple[Path, ...]] | None = None
        self.operations: dict[str, Callable[[Path, dict, Mapping[str, str]], dict]] = {}
        self.task_operations: dict[str, Callable[[Path, dict, Mapping[str, str]], dict]] = {}
        # Read access plus `.github/skills` loading. Resolved once, so a caller
        # cannot widen the CLI's reach after the service is built.
        self.extra_dirs = tuple(directory.resolve(strict=True) for directory in extra_dirs)
        self.plugin_dirs = tuple(directory.resolve(strict=True) for directory in plugin_dirs)
        for directory in self.plugin_dirs:
            manifest = directory / "plugin.json"
            if not directory.is_dir() or not manifest.resolve().is_relative_to(directory):
                raise ValueError("Plugin must be a contained, host-approved package")
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or metadata.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
                raise ValueError("Plugin must declare the Agent Plugins 1.0.0 schema")
        self.max_sessions = max_sessions
        self.idle_seconds = idle_seconds
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        self._reaper = threading.Thread(target=self._reap, daemon=True)
        self._reaper.start()

    @staticmethod
    def authorized(headers: Mapping[str, str]) -> bool:
        try:
            host = urlsplit("http://" + headers.get("host", ""))
            if host.hostname not in {"127.0.0.1", "localhost", "::1"} or host.username or host.password:
                return False
            if headers.get("x-copilot-terminal") != "1":
                return False
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return False
            if headers.get("sec-fetch-site") == "cross-site":
                return False
            origin = urlsplit(headers.get("origin", ""))
            return origin.scheme == "http" and origin.netloc == host.netloc
        except ValueError:
            return False

    def _lookup(self, payload: dict, *, allow_task: bool = False) -> SessionRecord:
        session_id, key = payload.get("session_id"), payload.get("key")
        task_key = payload.get("task_key")
        if not isinstance(session_id, str):
            raise PermissionError("Unknown terminal session")
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                raise PermissionError("Unknown terminal session")
            controls_session = isinstance(key, str) and hmac.compare_digest(record.key, key)
            performs_task = (allow_task and isinstance(task_key, str)
                             and hmac.compare_digest(record.task_key, task_key))
            if not controls_session and not performs_task:
                raise PermissionError("Unknown terminal session")
            record.last_seen = time.monotonic()
            return record

    def _start(self, payload: dict) -> dict:
        if set(payload) - {"columns", "rows"}:
            raise ValueError("Session startup accepts terminal dimensions only; launch policy belongs to the host")
        columns, rows = payload.get("columns", 100), payload.get("rows", 30)
        PtySession._dimensions(columns, rows)
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise ValueError("Terminal session limit reached; close an existing terminal")
            token, expires_at = self.token_provider()
            remaining = min(3600, expires_at - time.time() - 30)
            if remaining < 60:
                raise ValueError("Model access token is expiring; reconnect after signing in")
            session_id = str(uuid.uuid4())
            home = self.workspace_root / session_id / "home"
            workspace = self.workspace_root / session_id / "workspace"
            home.mkdir(mode=0o700, parents=True)
            workspace.mkdir(mode=0o700)
            task_key = secrets.token_urlsafe(32)
            if self.task_operations:
                access = workspace.parent / "task-access.json"
                with access.open("x", encoding="utf-8") as output:
                    access.chmod(0o600)
                    json.dump({"session_id": session_id, "task_key": task_key}, output)
            if self.workspace_initializer is not None:
                self.workspace_initializer(workspace)
            tool_arguments = []
            for executable in self.allowed_executables(workspace) if self.allowed_executables else ():
                resolved = executable.resolve(strict=True)
                if (not resolved.is_relative_to(workspace) or not resolved.is_file()
                        or not os.access(resolved, os.X_OK)
                        or re.fullmatch(r"[A-Za-z0-9_./-]+", str(resolved)) is None):
                    raise ValueError("Allowed helpers must be literal executable paths inside the session workspace")
                relative = resolved.relative_to(workspace).as_posix()
                for command in (str(resolved), relative, f"./{relative}"):
                    tool_arguments.append(f"--allow-tool=shell({command})")
            # The CLI asks whether to trust its working folder. This one was
            # just created here, 0700 and empty, so the question has one honest
            # answer and asking it every session would only train a reflex.
            config = home / ".copilot"
            config.mkdir(mode=0o700)
            (config / "config.json").write_text(
                json.dumps({"trustedFolders": [str(workspace),
                                               *(str(d) for d in self.extra_dirs)]}),
                encoding="utf-8")
            terminal = PtySession(
                [self.cli, "--no-auto-update", "--no-remote", "--no-remote-export", "--disable-builtin-mcps",
                 "--no-custom-instructions", "--no-bash-env", "--log-level=none",
                 "--secret-env-vars=COPILOT_PROVIDER_BEARER_TOKEN", "--session-id", session_id,
                 *self.launch.arguments(),
                 *tool_arguments,
                 *[argument for directory in self.plugin_dirs for argument in ("--plugin-dir", str(directory))],
                 *[argument for directory in self.extra_dirs for argument in ("--add-dir", str(directory))]],
                workspace, self.provider.environment(token, home, self.path),
                columns=columns, rows=rows, secrets=(token, task_key), lifetime_seconds=remaining,
            )
            key = secrets.token_urlsafe(32)
            self._sessions[session_id] = SessionRecord(key, terminal, time.monotonic(), task_key)
            return {"session_id": session_id, "key": key, "workspace": str(workspace),
                    "model": self.provider.deployment, "expires_in": int(remaining), "launch": self.launch.summary()}

    def _source(self, record: SessionRecord, payload: dict) -> dict:
        source = payload.get("source")
        if self.source_loader is None or not isinstance(source, dict):
            raise ValueError("Source attachment is unavailable")
        path, content = self.source_loader(source)
        relative = PurePosixPath(path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in path.split("/")) or "\\" in path:
            raise ValueError("Invalid source path")
        workspace = record.terminal.workspace
        target = workspace / "sources" / path
        if not target.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("Source path leaves the terminal workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as output:
                output.write(content)
            target.chmod(0o400)
        elif target.read_bytes() != content:
            raise ValueError("The local source copy was changed; start a new session to attach it again")
        return {"path": target.relative_to(workspace).as_posix(), "bytes": len(content)}

    def handle(self, action: str, headers: Mapping[str, str], payload: object) -> tuple[int, dict]:
        if not self.authorized(headers):
            return 403, {"error": "forbidden", "detail": "Terminal access requires the local same-origin application"}
        if not isinstance(payload, dict):
            return 400, {"error": "bad_request", "detail": "Expected a JSON object"}
        try:
            if action == "info":
                if not self.cli or not Path(self.cli).is_file():
                    return 200, {"available": False, "model": self.provider.deployment, "detail": "Copilot CLI is not installed"}
                version = subprocess.run([self.cli, "--version"], capture_output=True, text=True, timeout=10, check=True)
                return 200, {"available": True, "model": self.provider.deployment,
                             "version": version.stdout.splitlines()[0], "interactive": True,
                             "launch": self.launch.summary()}
            if action == "start":
                return 201, self._start(payload)
            record = self._lookup(payload, allow_task=action in self.task_operations)
            if action == "output":
                return 200, record.terminal.output(payload.get("cursor", 0), wait=15)
            if action == "input":
                record.terminal.write(payload.get("data"))
            elif action == "resize":
                record.terminal.resize(payload.get("columns"), payload.get("rows"))
            elif action == "stop":
                with self._lock:
                    self._sessions.pop(payload["session_id"], None)
                record.terminal.close()
            elif action == "source":
                return 200, self._source(record, payload)
            elif action in self.operations or action in self.task_operations:
                operation = self.operations.get(action) or self.task_operations[action]
                return 200, operation(record.terminal.workspace, payload, headers)
            else:
                return 404, {"error": "not_found", "detail": "Unknown terminal operation"}
            return 200, {"ok": True}
        except PermissionError:
            return 404, {"error": "not_found", "detail": "Unknown terminal session"}
        except ValueError as error:
            return 400, {"error": "bad_request", "detail": str(error)}
        except Exception as error:
            return 503, {"error": "terminal_unavailable", "detail": f"Terminal operation failed ({type(error).__name__})"}

    def _reap(self) -> None:
        while not self._shutdown.wait(30):
            with self._lock:
                expired = [session_id for session_id, record in self._sessions.items()
                           if time.monotonic() - record.last_seen > self.idle_seconds]
                terminals = [self._sessions.pop(session_id).terminal for session_id in expired]
            for terminal in terminals:
                terminal.close()

    def close(self) -> None:
        self._shutdown.set()
        with self._lock:
            records = list(self._sessions.values())
            self._sessions.clear()
        for record in records:
            record.terminal.close()