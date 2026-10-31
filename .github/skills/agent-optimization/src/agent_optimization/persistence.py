from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from workrecovery import CommitOutcome, RecoverableJobs, StoreError, StoreOccupied, StoreRefused, validate_run_id


def _write(path: Path, content: bytes, *, immutable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if immutable:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, value, *, immutable: bool = False) -> None:
    _write(path, json.dumps(value, indent=2).encode("utf-8"), immutable=immutable)


class RunSaveError(OSError):
    def __init__(self, outcome: CommitOutcome) -> None:
        self.outcome = outcome
        super().__init__(outcome.sentence())


class _RunManifestStore:
    def __init__(self, directory: Path, run_id: str) -> None:
        self.path = directory / "run.json"
        self.run_id = run_id

    def load(self, run_id: str) -> bytes | None:
        if run_id != self.run_id:
            raise StoreRefused("Run identity does not match the bound manifest")
        if self.path.is_symlink():
            raise StoreRefused("Run manifest must not be a symbolic link")
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def save(self, run_id: str, content: bytes, content_type: str) -> None:
        if run_id != self.run_id:
            raise StoreRefused("Run identity does not match the bound manifest")
        try:
            _write(self.path, content, immutable=True)
        except FileExistsError:
            if self.load(run_id) != content:
                raise StoreOccupied("Run manifest already holds different content") from None
        except OSError as error:
            raise StoreError("Run manifest write could not be confirmed") from error


def run_recovery(directory: Path, run_id: str) -> RecoverableJobs:
    """Bind completed-manifest recovery to one trusted, owner-authorized run directory."""
    validate_run_id(run_id)
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Run directory must not be a symbolic link")
    return RecoverableJobs(
        store=_RunManifestStore(directory, run_id),
        root=directory / ".recovery",
        max_attempts=1,
    )