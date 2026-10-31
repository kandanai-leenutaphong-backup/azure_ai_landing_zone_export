"""The local copy that exists before the store is asked for anything.

WHY THIS EXISTS
---------------
Expensive work is finished, in memory, and the only thing standing between it
and permanence is a store call that can take minutes and can be killed. A
process that dies there loses everything it produced, and the cost of that is
the whole run, not the call.

Writing the completed output to a local file first costs milliseconds and
covers a store failure, a container eviction and a ``SIGKILL`` with one
mechanism instead of three.

WHY IT IS WRITTEN BEFORE THE SAVE AND NOT IN A ``finally``
----------------------------------------------------------
A ``finally`` runs when the frame unwinds. It does not run when the process is
killed — and the save is exactly where a process gets killed. So the order is:
build the output, write it here, then attempt the save.

WHY NO-CLOBBER, NOT OVERWRITE
-----------------------------
``os.replace`` is atomic and silently destroys whatever was there. Two workers
that believe they own the same run id would then take turns overwriting each
other's only copy. Creating the final name with ``O_EXCL`` — through a hard
link from a temporary file in the same directory — is atomic *and* refuses,
which turns an ownership bug into an error instead of data loss.

WHAT THIS IS NOT
----------------
Not a cache, not a queue, not a second store, not a scheduler. Nothing here
resumes an unfinished computation. It preserves output that is already
complete, and hands it back after a restart.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import base64
import errno
import json
import os
import re
import stat as stat_module
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from workrecovery.clock import Clock, SystemClock
from workrecovery.errors import (
    ArtifactCorrupt,
    ArtifactExists,
    ArtifactMissing,
    InvalidRunId,
    PayloadNotSupported,
    PayloadTooLarge,
    RecoveryError,
    StagingFailed,
    StaleArtifact,
)
from workrecovery.payload import (
    BYTES_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    decode_payload,
    digest,
    encode_payload,
)

#: The envelope's identity. A reader checks both before trusting a file, so a
#: future format change is a refusal rather than a misreading.
ENVELOPE_SCHEMA = "recoverable-job/artifact"
ENVELOPE_VERSION = 1

_SUFFIX = ".artifact.json"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

#: Every field this format defines. A document carrying anything else is not
#: a version-1 envelope written by this code, and is refused rather than
#: partially understood: silently ignoring an unknown key is how a reader
#: accepts a document whose meaning it does not share.
_ENVELOPE_FIELDS = frozenset(
    {
        "schema",
        "version",
        "run_id",
        "created_at",
        "label",
        "content_type",
        "content_sha256",
        "content_bytes",
        "metadata",
        "content",
        "content_base64",
    }
)

#: A ceiling on what :meth:`ArtifactStore.read` will load into memory. The
#: recovery directory is a place other processes can write, so a reader that
#: calls ``read_bytes()`` on whatever it finds can be made to exhaust memory by
#: anyone who can create a file there — and that takes the whole listing with
#: it. Derived from the payload ceiling rather than guessed: base64 inflates
#: bytes by 4/3, JSON escaping can double a pathological string, and the
#: envelope's own fields are bounded by the metadata and label caps below.
DEFAULT_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
_ENVELOPE_OVERHEAD_BYTES = 64 * 1024

#: Metadata is triage, not a second copy of the payload, so it is bounded —
#: and bounded at *staging*, because the envelope's own size is what the read
#: ceiling has to cover. It is comfortably inside
#: ``_ENVELOPE_OVERHEAD_BYTES``.
DEFAULT_MAX_METADATA_BYTES = 32 * 1024

#: A label is one line for a human reading a directory listing.
MAX_LABEL_CHARS = 512
#: ``created_at`` is a timestamp, so a planted 10 MB "timestamp" is not one.
_MAX_CREATED_AT_CHARS = 64

# Open flags, resolved once. `O_NOFOLLOW` and `O_NONBLOCK` are POSIX and are
# what makes the no-follow promise true at the syscall rather than in a check
# a moment earlier; `O_BINARY` matters only on Windows, where the first two do
# not exist and the fallback in `_read_checked` applies.
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_BINARY = getattr(os, "O_BINARY", 0)


def artifact_ceiling(max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES) -> int:
    """The largest artifact file a payload ceiling can legitimately produce."""
    return max_payload_bytes * 2 + _ENVELOPE_OVERHEAD_BYTES


DEFAULT_MAX_ARTIFACT_BYTES = artifact_ceiling()


def validate_run_id(run_id: str) -> str:
    """Return ``run_id`` when it is safe to use as a file name, else refuse.

    Run ids become file names. A separator, a ``..`` segment, a NUL or a
    leading dot is a path-traversal attempt or a hidden file, not a naming
    preference. See GOTCHAS.md, G4.
    """
    if not isinstance(run_id, str):
        raise InvalidRunId(f"run id must be a string, got {type(run_id).__name__}")
    if not _RUN_ID.match(run_id):
        raise InvalidRunId(
            f"run id {run_id!r} is not usable as a file name: use 1-128 characters "
            "from [A-Za-z0-9._-], starting with a letter or digit"
        )
    if run_id in {".", ".."} or ".." in run_id:
        raise InvalidRunId(f"run id {run_id!r} contains a path segment")
    return run_id


@dataclass(frozen=True)
class Artifact:
    """One completed output, preserved on disk, with its identity.

    Attributes:
        run_id: The caller's stable id for this run. Also the file name stem
            and the key the store is asked for during reconciliation.
        created_at: When it was staged, from the injected clock.
        label: Free text for a human listing a directory. Never load-bearing.
        content_type: ``application/json`` or ``application/octet-stream``.
        content_sha256: Digest of the **output** bytes. The identity.
        content_bytes: Length of those bytes.
        metadata: Caller-supplied JSON, for triage. Never the payload again.
        payload: The completed output itself. A **snapshot**, decoded from the
            bytes the digest covers, never the caller's live object: a record
            that can disagree with its own digest is not a record.
        path: Where it is. None for an artifact that was never written.
    """

    run_id: str
    created_at: str
    label: str
    content_type: str
    content_sha256: str
    content_bytes: int
    metadata: dict[str, Any] = field(default_factory=dict)
    payload: Any = None
    path: Path | None = None

    def summary(self) -> dict[str, Any]:
        """The projection safe to log or print: identity, never the payload."""
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "label": self.label,
            "content_type": self.content_type,
            "content_sha256": self.content_sha256,
            "content_bytes": self.content_bytes,
            "path": str(self.path) if self.path else None,
        }

    def __repr__(self) -> str:
        return (
            f"Artifact(run_id={self.run_id!r}, content_sha256={self.content_sha256[:12]}…, "
            f"content_bytes={self.content_bytes}, path={str(self.path)!r})"
        )


class ArtifactStore:
    """A directory of preserved outputs, one file per run id.

    Args:
        root: Directory to hold artifacts. Created with owner-only permissions
            if absent, because completed output is as sensitive as the data it
            was derived from.
        clock: Injected time source; only used for ``created_at``.
        dir_mode: Permission bits for a directory this object creates.
        max_artifact_bytes: Refuse to read a file larger than this, and refuse
            to *write* an envelope larger than this, so nothing this object
            stages is something its own reader rejects. Defaults to
            :data:`DEFAULT_MAX_ARTIFACT_BYTES`.
        max_metadata_bytes: Ceiling on the encoded ``metadata`` object, applied
            on both write and read. Defaults to
            :data:`DEFAULT_MAX_METADATA_BYTES`.

    Raises:
        StagingFailed: when ``root`` cannot be created, or exists as something
            other than a directory.
        ValueError: for a non-positive ``max_artifact_bytes`` or
            ``max_metadata_bytes``.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        clock: Clock | None = None,
        dir_mode: int = 0o700,
        max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
        max_metadata_bytes: int = DEFAULT_MAX_METADATA_BYTES,
    ) -> None:
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")
        if max_metadata_bytes < 1:
            raise ValueError("max_metadata_bytes must be positive")
        self.clock = clock or SystemClock()
        self.dir_mode = dir_mode
        self.max_artifact_bytes = max_artifact_bytes
        self.max_metadata_bytes = max_metadata_bytes
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _ensure_root(self) -> Path:
        root = self._root
        try:
            if root.is_symlink():
                # A symlinked recovery root can point anywhere, including
                # somewhere world-readable. Refuse rather than follow it.
                raise StagingFailed(f"recovery root {root} is a symlink; refusing to follow it")
            root.mkdir(parents=True, exist_ok=True, mode=self.dir_mode)
        except StagingFailed:
            raise
        except OSError as refused:
            raise StagingFailed(
                f"recovery root {root} is not usable: {type(refused).__name__}: "
                f"{refused.strerror}"
            ) from refused
        if not root.is_dir():
            raise StagingFailed(f"recovery root {root} exists and is not a directory")
        return root

    def path_for(self, run_id: str) -> Path:
        """Where this run's artifact lives. Validated, and inside the root."""
        validate_run_id(run_id)
        target = self._root / f"{run_id}{_SUFFIX}"
        # Belt and braces: even with a validated id, assert containment.
        if target.parent != self._root:
            raise InvalidRunId(f"run id {run_id!r} escapes the recovery root")
        return target

    # ------------------------------------------------------------- writing

    def stage(
        self,
        run_id: str,
        payload: Any,
        *,
        label: str = "",
        metadata: dict[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> Artifact:
        """Write the **full** completed output, atomically, refusing to clobber.

        ``content``/``content_type`` may be passed when the caller has already
        encoded the payload — the digest then covers exactly the bytes that
        will be offered to the store.

        Raises:
            InvalidRunId: for a run id that is not a safe file name.
            PayloadNotSupported: for a ``label`` that is not a string, or
                ``metadata`` that is not a JSON object.
            PayloadTooLarge: for a label or metadata over its ceiling.
            ArtifactExists: when this run id already has an artifact. The
                existing file is left exactly as it was.
            StagingFailed: for any filesystem refusal — read-only mount, full
                disk, permissions — and for an envelope that would exceed
                ``max_artifact_bytes``, which is refused **before** anything
                is written. Nothing is left half-written.
        """
        if content is None or content_type is None:
            content, content_type = encode_payload(payload)

        target = self.path_for(run_id)
        label = self._checked_label(label)
        metadata_snapshot = self._checked_metadata(metadata)
        root = self._ensure_root()

        artifact = Artifact(
            run_id=run_id,
            created_at=self.clock.now(),
            label=label,
            content_type=content_type,
            content_sha256=digest(content),
            content_bytes=len(content),
            metadata=metadata_snapshot,
            # Decoded from the bytes the digest covers, not the caller's
            # object: a caller that mutates its payload afterwards must not be
            # able to make this record disagree with its own digest, or make a
            # later recommit store something else. See GOTCHAS.md, G11.
            payload=decode_payload(content, content_type),
            path=target,
        )
        document = self._envelope(artifact, content)

        try:
            handle, temporary = tempfile.mkstemp(dir=str(root), prefix=".staging-", suffix=".tmp")
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(document)
                    stream.flush()
                    # The bytes, then the directory entry. Without both fsyncs
                    # a crash can leave a name with no content behind it.
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, target)
                except FileExistsError as clash:
                    raise ArtifactExists(
                        f"an artifact for run {run_id!r} already exists at {target}; "
                        "it was left untouched — two owners for one run id is an "
                        "ownership bug, not a write to resolve"
                    ) from clash
                self._fsync_dir(root)
            finally:
                Path(temporary).unlink(missing_ok=True)
        except (ArtifactExists, StagingFailed):
            raise
        except OSError as refused:
            raise StagingFailed(
                f"no local copy of run {run_id!r} could be written to {root}: "
                f"{type(refused).__name__}: {refused.strerror}"
            ) from refused

        return artifact

    def _checked_label(self, label: str) -> str:
        if not isinstance(label, str):
            raise PayloadNotSupported(
                f"label must be a string, got {type(label).__name__}; it is one line "
                "for a human, not a place to put structured data"
            )
        if len(label) > MAX_LABEL_CHARS:
            raise PayloadTooLarge(
                f"label is {len(label)} characters, over the {MAX_LABEL_CHARS}-character "
                "ceiling; nothing was written"
            )
        return label

    def _checked_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        """A validated, bounded, defensive copy of the caller's metadata.

        ``dict(metadata or {})`` accepted a list of pairs, kept a live nested
        object the caller could mutate afterwards, and let a value that JSON
        cannot represent reach ``json.dumps`` — where it becomes a
        ``TypeError`` out of ``stage``, not a named refusal.
        """
        if metadata is None:
            return {}
        if not isinstance(metadata, dict):
            raise PayloadNotSupported(
                f"metadata must be a JSON object, got {type(metadata).__name__}"
            )
        encoded, _ = encode_payload(metadata)
        if len(encoded) > self.max_metadata_bytes:
            raise PayloadTooLarge(
                f"metadata encodes to {len(encoded)} bytes, over the "
                f"{self.max_metadata_bytes}-byte ceiling; metadata is for triage, not a "
                "second copy of the payload. Nothing was written."
            )
        # Round-tripped rather than shallow-copied: a nested dict the caller
        # keeps mutating must not change this record after the fact.
        snapshot = decode_payload(encoded, JSON_CONTENT_TYPE)
        assert isinstance(snapshot, dict)
        return snapshot

    @staticmethod
    def _fsync_dir(directory: Path) -> None:
        try:
            fd = os.open(str(directory), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            # Some filesystems refuse to fsync a directory. The file's own
            # fsync already happened; this is best effort, and saying so is
            # more honest than pretending durability is absolute.
            pass
        finally:
            os.close(fd)

    def _envelope(self, artifact: Artifact, content: bytes) -> bytes:
        document: dict[str, Any] = {
            "schema": ENVELOPE_SCHEMA,
            "version": ENVELOPE_VERSION,
            "run_id": artifact.run_id,
            "created_at": artifact.created_at,
            "label": artifact.label,
            "content_type": artifact.content_type,
            "content_sha256": artifact.content_sha256,
            "content_bytes": artifact.content_bytes,
            "metadata": artifact.metadata,
        }
        if artifact.content_type == BYTES_CONTENT_TYPE:
            document["content_base64"] = base64.b64encode(content).decode("ascii")
        else:
            # Stored decoded so a person can read and grep it. Canonical
            # encoding is deterministic, so re-encoding on read reproduces
            # these exact bytes — which is what the digest check relies on.
            document["content"] = decode_payload(content, artifact.content_type)
        return self._serialise(document, artifact.run_id)

    def _serialise(self, document: dict[str, Any], run_id: str) -> bytes:
        """Envelope bytes that this object's own :meth:`read` will accept.

        ``indent=2`` is for the person who has to look at the file, and it is
        not free: pretty-printing a payload of many small values measured
        4.9× its canonical size, which is more than the read ceiling's 2×
        allowance. A staged file the reader then refuses is the worst outcome
        available — the work is on disk and unreachable — so the exact byte
        length is measured here, the readable form is dropped in favour of the
        compact one when it does not fit, and staging refuses outright rather
        than writing a file it knows is unreadable.
        """
        try:
            raw = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
            if len(raw) > self.max_artifact_bytes:
                raw = json.dumps(
                    document, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
        except (ValueError, TypeError, RecursionError) as broken:
            raise StagingFailed(
                f"the envelope for run {run_id!r} could not be serialised: "
                f"{type(broken).__name__}; nothing was written"
            ) from broken
        if len(raw) > self.max_artifact_bytes:
            raise StagingFailed(
                f"the envelope for run {run_id!r} would be {len(raw)} bytes, over this "
                f"store's {self.max_artifact_bytes}-byte artifact ceiling; nothing was "
                "written, because a file this store's own read() refuses is work "
                "preserved nowhere. Raise max_artifact_bytes deliberately."
            )
        return raw

    # ------------------------------------------------------------- reading

    def read(self, path: str | os.PathLike[str]) -> Artifact:
        """Load one artifact and verify it against its own digest.

        The file is opened without following a symlink and every decision is
        made from the descriptor: a symlink, a directory, a device node, a FIFO
        or anything over ``max_artifact_bytes`` is refused without its content
        being read. The recovery directory is somewhere other processes can
        write, so "whatever is at this path" is untrusted input, and a reader
        that trusts it can be made to hang, exhaust memory, or take the whole
        listing down with one planted file. See GOTCHAS.md, G12.

        Every field is then checked before it is used, because ``run_id`` is
        the key a later ``recommit`` writes to the store and the identity
        ``discard`` matches on. The file name must agree with the id inside.

        Raises:
            ArtifactMissing: no such file.
            ArtifactCorrupt: unreadable, not a regular file, oversized, wrong
                schema or version, missing field, a field of the wrong type or
                over its own bound, an undefined field, unparseable at any
                depth, or content whose digest does not match the recorded one
                — which is what a truncated write looks like. The file is never
                deleted.
        """
        target = Path(path)
        raw = self._read_checked(target)

        try:
            document = json.loads(raw.decode("utf-8"))
        except RecursionError as deep:
            # 200 000 nested arrays is a valid JSON document and an invalid
            # artifact. Left as a RecursionError it escapes read(), _scan(),
            # list() and problems(), and one planted file hides every pending
            # run from the operator.
            raise ArtifactCorrupt(
                f"artifact at {target} is nested too deeply to parse; it has not "
                "been deleted"
            ) from deep
        except (ValueError, MemoryError) as broken:
            # ValueError covers UnicodeDecodeError and json.JSONDecodeError,
            # and every integer-too-large refusal json raises for a huge
            # numeric literal.
            raise ArtifactCorrupt(
                f"artifact at {target} is not valid JSON — most likely a truncated write"
            ) from broken
        if not isinstance(document, dict):
            raise ArtifactCorrupt(f"artifact at {target} is not an object")

        unknown = sorted(set(document) - _ENVELOPE_FIELDS)
        if unknown:
            raise ArtifactCorrupt(
                f"artifact at {target} carries fields this format does not define: "
                f"{unknown}. Version {ENVELOPE_VERSION} is closed; a reader that "
                "ignores unknown fields accepts a document whose meaning it does not "
                "share. The file has not been deleted."
            )

        if document.get("schema") != ENVELOPE_SCHEMA:
            raise ArtifactCorrupt(
                f"artifact at {target} has schema {document.get('schema')!r}, "
                f"expected {ENVELOPE_SCHEMA!r}"
            )
        version = document.get("version")
        # `True == 1`, so a bare equality test accepts `"version": true`.
        if isinstance(version, bool) or version != ENVELOPE_VERSION:
            raise ArtifactCorrupt(
                f"artifact at {target} is version {version!r}; "
                f"this reader understands version {ENVELOPE_VERSION}"
            )

        missing = [
            key
            for key in ("run_id", "created_at", "content_type", "content_sha256", "content_bytes")
            if key not in document
        ]
        if missing:
            raise ArtifactCorrupt(f"artifact at {target} is missing {missing}")

        run_id = self._checked_run_id(document["run_id"], target)
        created_at = self._checked_created_at(document["created_at"], target)
        label = self._checked_read_label(document.get("label", ""), target)
        metadata = self._checked_read_metadata(document.get("metadata"), target)
        recorded_digest = document["content_sha256"]
        if not isinstance(recorded_digest, str) or not _SHA256_HEX.match(recorded_digest):
            raise ArtifactCorrupt(
                f"artifact at {target} has content_sha256 {recorded_digest!r}, which is "
                "not a lowercase sha256 hex digest"
            )
        recorded_bytes = document["content_bytes"]
        if isinstance(recorded_bytes, bool) or not isinstance(recorded_bytes, int):
            raise ArtifactCorrupt(
                f"artifact at {target} has content_bytes {recorded_bytes!r}, which is "
                "not an integer"
            )

        content_type = document["content_type"]
        if content_type == BYTES_CONTENT_TYPE:
            if "content" in document:
                raise ArtifactCorrupt(
                    f"artifact at {target} carries both content and content_base64"
                )
            encoded = document.get("content_base64")
            if not isinstance(encoded, str):
                raise ArtifactCorrupt(f"artifact at {target} carries no content_base64")
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as broken:
                raise ArtifactCorrupt(f"artifact at {target} has invalid base64") from broken
            payload: Any = content
        elif content_type == JSON_CONTENT_TYPE:
            if "content_base64" in document:
                raise ArtifactCorrupt(
                    f"artifact at {target} carries both content and content_base64"
                )
            if "content" not in document:
                raise ArtifactCorrupt(f"artifact at {target} carries no content")
            payload = document["content"]
            try:
                content, _ = encode_payload(payload)
            except RecursionError as deep:
                raise ArtifactCorrupt(
                    f"artifact at {target} carries content too deeply nested to "
                    "re-encode; it has not been deleted"
                ) from deep
            except (RecoveryError, ValueError) as broken:
                raise ArtifactCorrupt(
                    f"artifact at {target} carries content this reader cannot "
                    f"re-encode: {type(broken).__name__}"
                ) from broken
        else:
            raise ArtifactCorrupt(f"artifact at {target} has unknown content type {content_type!r}")

        actual = digest(content)
        if actual != recorded_digest or len(content) != recorded_bytes:
            raise ArtifactCorrupt(
                f"artifact at {target} does not match its recorded digest "
                f"({actual[:12]}… != {str(recorded_digest)[:12]}…) — it was "
                "truncated or edited; it has not been deleted"
            )

        return Artifact(
            run_id=run_id,
            created_at=created_at,
            label=label,
            content_type=content_type,
            content_sha256=recorded_digest,
            content_bytes=recorded_bytes,
            metadata=metadata,
            payload=payload,
            path=target,
        )

    # The four field checks below exist because every value read out of this
    # file is untrusted, and three of them are load-bearing rather than
    # cosmetic: `run_id` becomes the key `recommit` writes to the store and
    # the identity `discard` matches on, and `metadata` used to reach
    # `dict(...)` unchecked — where a planted list or integer raised
    # TypeError/ValueError straight out of `read`, past `_scan`, and hid every
    # good artifact in the directory behind one bad file.

    @staticmethod
    def _checked_run_id(value: Any, target: Path) -> str:
        try:
            run_id = validate_run_id(value)
        except InvalidRunId as bad:
            raise ArtifactCorrupt(
                f"artifact at {target} carries an unusable run_id: {bad}. It has not "
                "been deleted."
            ) from bad
        expected = f"{run_id}{_SUFFIX}"
        if target.name != expected:
            raise ArtifactCorrupt(
                f"artifact at {target} names run {run_id!r}, so it should be called "
                f"{expected}. A recommit stores under the id inside the file, so a "
                "file whose name and id disagree is refused rather than trusted."
            )
        return run_id

    @staticmethod
    def _checked_created_at(value: Any, target: Path) -> str:
        if not isinstance(value, str) or not value or len(value) > _MAX_CREATED_AT_CHARS:
            raise ArtifactCorrupt(
                f"artifact at {target} has a created_at that is not a short timestamp "
                "string"
            )
        return value

    @staticmethod
    def _checked_read_label(value: Any, target: Path) -> str:
        if not isinstance(value, str) or len(value) > MAX_LABEL_CHARS:
            raise ArtifactCorrupt(
                f"artifact at {target} has a label that is not a string of at most "
                f"{MAX_LABEL_CHARS} characters"
            )
        return value

    def _checked_read_metadata(self, value: Any, target: Path) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ArtifactCorrupt(
                f"artifact at {target} has metadata of type "
                f"{type(value).__name__}, which is not a JSON object"
            )
        try:
            encoded, _ = encode_payload(value)
        except (RecoveryError, ValueError, RecursionError) as broken:
            raise ArtifactCorrupt(
                f"artifact at {target} has metadata this reader cannot re-encode: "
                f"{type(broken).__name__}"
            ) from broken
        if len(encoded) > self.max_metadata_bytes:
            raise ArtifactCorrupt(
                f"artifact at {target} has {len(encoded)} bytes of metadata, over the "
                f"{self.max_metadata_bytes}-byte ceiling; it has not been deleted"
            )
        return value

    def _read_checked(self, target: Path) -> bytes:
        """Open once, then check the descriptor — not the name, twice.

        The previous order was ``lstat`` then ``open``: two separate lookups of
        the same name, with an interval another writer can use to replace a
        regular file with a symlink. The check passed, the open followed the
        link, and the "symlinks are never followed" promise was false for
        exactly the case it was written for. Unlinking the symlink afterwards
        would not have helped — it removes the link, never the file already
        read.

        So the open itself refuses: ``O_NOFOLLOW`` fails on a final-component
        symlink, ``O_NONBLOCK`` stops a planted FIFO from parking the reader
        forever, and every type and size decision is made from ``fstat`` on the
        descriptor that is actually going to be read. Where ``O_NOFOLLOW`` does
        not exist the fallback is an ``lstat`` before and an identity
        comparison after, which detects the swap instead of preventing it.

        The **root's own path** is outside this: a parent directory swapped
        between calls is not defended here, because that needs ``openat`` on a
        held directory descriptor. See CONTRACT.md, "Root path trust boundary".
        """
        before: os.stat_result | None = None
        if not _NOFOLLOW:
            before = self._lstat_or_refuse(target)

        try:
            fd = os.open(target, os.O_RDONLY | _NOFOLLOW | _NONBLOCK | _CLOEXEC | _BINARY)
        except FileNotFoundError as missing:
            raise ArtifactMissing(f"no artifact at {target}") from missing
        except OSError as refused:
            if refused.errno in (errno.ELOOP, errno.EMLINK):
                raise ArtifactCorrupt(
                    f"{target} is a symlink; an artifact is a regular file and this "
                    "one was not followed"
                ) from refused
            raise ArtifactCorrupt(
                f"artifact at {target} could not be opened: {type(refused).__name__}"
            ) from refused

        try:
            try:
                stat = os.fstat(fd)
            except OSError as refused:
                raise ArtifactCorrupt(
                    f"artifact at {target} could not be inspected: {type(refused).__name__}"
                ) from refused

            if not stat_module.S_ISREG(stat.st_mode):
                raise ArtifactCorrupt(
                    f"{target} is not a regular file, so it is not an artifact; "
                    "it was left in place"
                )
            if before is not None and (before.st_dev, before.st_ino) != (
                stat.st_dev,
                stat.st_ino,
            ):
                raise ArtifactCorrupt(
                    f"{target} was replaced between the check and the open; the file "
                    "that was opened is not the one that was inspected, so it was not "
                    "read"
                )
            if stat.st_size > self.max_artifact_bytes:
                raise ArtifactCorrupt(
                    f"{target} is {stat.st_size} bytes, larger than the "
                    f"{self.max_artifact_bytes}-byte read ceiling; it was not read and "
                    "not deleted"
                )

            try:
                # One byte more than the ceiling, so a file that grew between
                # the fstat and the read is refused rather than swallowed.
                raw = self._read_all(fd, self.max_artifact_bytes + 1)
            except (OSError, MemoryError) as refused:
                raise ArtifactCorrupt(
                    f"artifact at {target} could not be read: {type(refused).__name__}"
                ) from refused
        finally:
            os.close(fd)

        if len(raw) > self.max_artifact_bytes:
            raise ArtifactCorrupt(
                f"{target} is larger than the {self.max_artifact_bytes}-byte read "
                "ceiling; it was not read and not deleted"
            )
        return raw

    def _lstat_or_refuse(self, target: Path) -> os.stat_result:
        """Only used where ``O_NOFOLLOW`` is unavailable."""
        try:
            stat = os.lstat(target)
        except FileNotFoundError as missing:
            raise ArtifactMissing(f"no artifact at {target}") from missing
        except OSError as refused:
            raise ArtifactCorrupt(
                f"artifact at {target} could not be inspected: {type(refused).__name__}"
            ) from refused
        if stat_module.S_ISLNK(stat.st_mode):
            raise ArtifactCorrupt(
                f"{target} is a symlink; an artifact is a regular file and this "
                "one was not followed"
            )
        return stat

    @staticmethod
    def _read_all(fd: int, limit: int) -> bytes:
        chunks: list[bytes] = []
        remaining = limit
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1 << 20))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read_run(self, run_id: str) -> Artifact:
        """The artifact for one run id."""
        return self.read(self.path_for(run_id))

    def read_inside_root(self, path: str | os.PathLike[str]) -> Artifact:
        """Read a path, refusing anything that is not inside this root.

        A recovery API that takes "a run id or a path" can otherwise be handed
        an absolute path to somewhere else entirely, and read — and, with
        :meth:`discard`, delete — a file this store never wrote.

        Raises:
            InvalidRunId: the path resolves outside the root, or the root does
                not exist.
            ArtifactCorrupt, ArtifactMissing: as :meth:`read`.
        """
        self._require_inside_root(Path(path))
        return self.read(path)

    def _require_inside_root(self, target: Path) -> Path:
        """Refuse a path that is not directly inside the root.

        The parent is resolved (so ``..`` and a symlinked directory cannot walk
        out) while the final component is not, because resolving it would
        follow a symlinked *artifact* to its target and quietly accept it.
        :meth:`read` refuses that symlink separately.
        """
        try:
            root = self._root.resolve(strict=False)
            parent = target.parent.resolve(strict=False)
        except OSError as refused:
            raise InvalidRunId(
                f"{target} could not be resolved: {type(refused).__name__}"
            ) from refused
        if parent != root:
            raise InvalidRunId(
                f"{target} is not inside the recovery root {self._root}; this API "
                "reads and deletes only what it owns"
            )
        return target

    def list(self) -> list[Artifact]:
        """Every readable artifact in the root, oldest name first.

        A corrupt file is *not* raised past this call and *not* deleted: use
        :meth:`problems` to see it. One bad file must not hide the good ones,
        and a listing routine is the last place that should decide to delete.
        """
        return [artifact for artifact, _ in self._scan() if artifact is not None]

    def problems(self) -> list[tuple[Path, str]]:
        """Files in the root that do not read back, with the reason."""
        return [(path, reason) for artifact, (path, reason) in self._scan() if artifact is None]

    def _scan(self) -> Iterator[tuple[Artifact | None, tuple[Path, str]]]:
        if not self._root.is_dir():
            return
        try:
            candidates = sorted(self._root.glob(f"*{_SUFFIX}"))
        except OSError as refused:
            # The directory itself became unreadable. That is worth reporting,
            # not swallowing, and it is not one file's problem.
            raise StagingFailed(
                f"recovery root {self._root} could not be listed: "
                f"{type(refused).__name__}"
            ) from refused
        for path in candidates:
            try:
                yield self.read(path), (path, "")
            except ArtifactMissing:
                # Removed between the listing and the read — a race with a
                # concurrent recovery, not a problem to report.
                continue
            except RecoveryError as broken:
                yield None, (path, str(broken))
            except OSError as refused:
                yield None, (path, f"{type(refused).__name__}: {refused.strerror}")

    # ------------------------------------------------------------ removing

    def discard(self, artifact: Artifact) -> None:
        """Delete this artifact, and only after proving it is still this one.

        The file is re-read and its digest compared with the record in hand.
        Anything else — a different digest, a different run id, an unreadable
        file — is a :class:`StaleArtifact` and the file stays. Tidying up is
        never worth deleting somebody else's only copy. See GOTCHAS.md, G7.

        Removing an artifact that is already gone is not an error: recovery
        must be idempotent.
        """
        if artifact.path is None:
            return
        # An Artifact is an ordinary dataclass, so one can be constructed by
        # hand with any path in it. Deleting is confined to this root, which is
        # the only part of the proof that does not depend on in-process code
        # being trustworthy. See GOTCHAS.md, G13.
        try:
            self._require_inside_root(artifact.path)
        except InvalidRunId as outside:
            raise StaleArtifact(str(outside)) from outside
        try:
            on_disk = self.read(artifact.path)
        except ArtifactMissing:
            return
        except ArtifactCorrupt as broken:
            raise StaleArtifact(
                f"{artifact.path} did not read back cleanly, so it was not deleted: {broken}"
            ) from broken
        if (
            on_disk.run_id != artifact.run_id
            or on_disk.content_sha256 != artifact.content_sha256
        ):
            raise StaleArtifact(
                f"{artifact.path} now holds run {on_disk.run_id!r} with digest "
                f"{on_disk.content_sha256[:12]}…, not run {artifact.run_id!r} with "
                f"{artifact.content_sha256[:12]}… — it was left in place"
            )
        try:
            artifact.path.unlink()
        except FileNotFoundError:
            return
        except OSError as refused:
            raise StaleArtifact(
                f"{artifact.path} could not be removed: {type(refused).__name__}"
            ) from refused


__all__ = [
    "DEFAULT_MAX_ARTIFACT_BYTES",
    "DEFAULT_MAX_METADATA_BYTES",
    "ENVELOPE_SCHEMA",
    "ENVELOPE_VERSION",
    "MAX_LABEL_CHARS",
    "Artifact",
    "ArtifactStore",
    "artifact_ceiling",
    "validate_run_id",
]
