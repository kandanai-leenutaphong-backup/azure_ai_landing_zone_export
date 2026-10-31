from __future__ import annotations

import codecs
import errno
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path


class Redactor:
    def __init__(self, secrets: tuple[str, ...]):
        self.secrets = tuple(secret for secret in secrets if secret)
        self.pending = ""

    def feed(self, text: str, final: bool = False) -> str:
        text = self.pending + text
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        keep = 0
        for secret in self.secrets:
            for length in range(1, min(len(secret), len(text) + 1)):
                if text.endswith(secret[:length]):
                    keep = max(keep, length)
        self.pending = text[-keep:] if keep else ""
        visible = text[:-keep] if keep else text
        if final and self.pending:
            visible += "[redacted]"
            self.pending = ""
        return visible


class PtySession:
    def __init__(
        self, argv: list[str], workspace: Path, environment: dict[str, str], *,
        columns: int = 100, rows: int = 30, secrets: tuple[str, ...] = (),
        lifetime_seconds: float = 3600, buffer_limit: int = 1_000_000,
    ):
        self._dimensions(columns, rows)
        self.workspace = workspace
        self._buffer = ""
        self._offset = 0
        self._limit = buffer_limit
        self._condition = threading.Condition()
        self._io_lock = threading.Lock()
        self._stopped = threading.Event()
        self._done = False
        self._exit_code: int | None = None
        self._deadline = time.monotonic() + lifetime_seconds
        self._redactor = Redactor(secrets)
        self._master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
            self.process = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name("child.py")), *argv],
                cwd=workspace, env=environment, stdin=slave, stdout=slave, stderr=slave,
                close_fds=True, start_new_session=True,
            )
        except BaseException:
            os.close(self._master)
            raise
        finally:
            os.close(slave)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    @staticmethod
    def _dimensions(columns: int, rows: int) -> None:
        if type(columns) is not int or type(rows) is not int or not (20 <= columns <= 400 and 5 <= rows <= 200):
            raise ValueError("Terminal size must be 20..400 columns and 5..200 rows")

    def _append(self, text: str) -> None:
        if not text:
            return
        with self._condition:
            self._offset += len(text)
            self._buffer = (self._buffer + text)[-self._limit:]
            self._condition.notify_all()

    def _signal_group(self, signum: int) -> None:
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            pass

    def _pump(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while not self._stopped.is_set():
                if time.monotonic() >= self._deadline:
                    self._append("\r\nSession time limit reached.\r\n")
                    break
                ready, _, _ = select.select([self._master], [], [], 0.2)
                if ready:
                    try:
                        data = os.read(self._master, 16384)
                    except OSError as error:
                        if error.errno == errno.EIO:
                            break
                        raise
                    if not data:
                        break
                    self._append(self._redactor.feed(decoder.decode(data)))
                elif self.process.poll() is not None:
                    break
        finally:
            self._append(self._redactor.feed(decoder.decode(b"", final=True), final=True))
            self._signal_group(signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._signal_group(signal.SIGKILL)
                self.process.wait(timeout=2)
            self._signal_group(signal.SIGKILL)
            with self._io_lock:
                os.close(self._master)
            with self._condition:
                self._exit_code = self.process.returncode
                self._done = True
                self._condition.notify_all()

    def output(self, cursor: int = 0, wait: float = 0) -> dict:
        if type(cursor) is not int or cursor < 0:
            raise ValueError("Invalid terminal cursor")
        with self._condition:
            if cursor > self._offset:
                raise ValueError("Terminal cursor is ahead of output")
            if cursor == self._offset and not self._done and wait:
                self._condition.wait(timeout=min(wait, 20))
            start = self._offset - len(self._buffer)
            return {
                "output": self._buffer[max(0, cursor - start):],
                "cursor": self._offset, "reset": cursor < start,
                "running": not self._done, "exit_code": self._exit_code,
            }

    def write(self, data: str) -> None:
        if not isinstance(data, str) or len(data.encode("utf-8")) > 65536:
            raise ValueError("Terminal input exceeds 64 KiB")
        with self._io_lock:
            if self.process.poll() is not None or self._stopped.is_set():
                raise ValueError("Terminal session has exited")
            encoded = data.encode("utf-8")
            while encoded:
                written = os.write(self._master, encoded)
                encoded = encoded[written:]

    def resize(self, columns: int, rows: int) -> None:
        self._dimensions(columns, rows)
        with self._io_lock:
            if self.process.poll() is not None or self._stopped.is_set():
                return
            fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))

    def close(self) -> None:
        self._stopped.set()
        self._signal_group(signal.SIGTERM)
        self._reader.join(timeout=5)