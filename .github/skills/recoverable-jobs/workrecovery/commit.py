"""The adoption boundary: preserve completed work, then try to store it.

THE ORDER IS THE WHOLE DESIGN
-----------------------------
1. Encode the **full** completed output and take its digest.
2. Write it to a local artifact. Nothing fallible happens before this.
3. Only now apply any store-imposed size cap, to a *copy*. The artifact keeps
   everything.
4. Save to the store.
5. Read it back and compare digests. "Accepted" is not "stored".
6. Delete the local copy only when the store demonstrably holds the identical
   bytes.

Step 3 after step 2 is deliberate and is the correction of a real defect: a
version of this that capped first, and then wrote a "full output" artifact
containing the capped output, told operators their tail was recoverable when
it had already been dropped. See GOTCHAS.md, G9.

WHAT THIS IS NOT
----------------
Not a scheduler, not a job queue, not automatic resumption of an unfinished
computation. Nothing here re-runs anything. It preserves output that is
already complete and hands it back after a restart, so a person or a script
can commit it again.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Literal

from workrecovery.artifacts import (
    DEFAULT_MAX_PAYLOAD_BYTES,
    Artifact,
    ArtifactStore,
    artifact_ceiling,
    validate_run_id,
)
from workrecovery.clock import Clock, SystemClock
from workrecovery.errors import (
    ArtifactCorrupt,
    PayloadTooLarge,
    StagingFailed,
    StaleArtifact,
    StoreError,
    StoreOccupied,
    StoreRefused,
    StoreTimeout,
    StoreUnavailable,
)
from workrecovery.payload import digest, encode_payload
from workrecovery.store import Store

logger = logging.getLogger(__name__)

CommitState = Literal["saved", "absent", "unknown", "conflict"]

StagingPolicy = Literal["require", "proceed"]

#: A ceiling on what will be staged, so one runaway job cannot fill the disk
#: the next one needs. 64 MiB is generous for structured output; raise it
#: deliberately, having thought about the disk. Defined with the artifact
#: format, because the read ceiling is derived from it. Re-exported here for
#: callers who have always imported it from this module.

#: Retries apply only to ``StoreUnavailable`` — a request that was never sent.
#: A timed-out write is never retried: it may have landed, and a second write
#: would be a duplicate or a clobber.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0


@dataclass(frozen=True)
class CommitOutcome:
    """What actually happened, in terms a caller can act on.

    Attributes:
        state: ``saved`` only when the store returned the identical bytes on
            read-back. ``absent`` when nothing was written and that is known.
            ``conflict`` when the run id already held *different* content,
            which was left exactly as it was — the local artifact is always
            kept in that case. ``unknown`` when it cannot be told — which is a
            result, not a failure to produce one.
        run_id: The id the output is stored under, and the id to look for.
        content_sha256: Digest of the bytes offered to the store.
        staged_sha256: Digest of the full completed output on disk. Differs
            from ``content_sha256`` exactly when a size cap was applied.
        artifact: The preserved local copy, or None when it was discarded
            after verification (or never written under the ``proceed``
            policy).
        capped: Whether the stored payload is smaller than the produced one.
        verified: Whether a read-back returned identical bytes.
        attempts: Store write attempts made.
        detail: One sentence for a person, safe to print. No payload in it.
        error: The store failure that ended the attempt, if any.
    """

    state: CommitState
    run_id: str
    content_sha256: str
    staged_sha256: str
    artifact: Artifact | None = None
    capped: bool = False
    verified: bool = False
    attempts: int = 0
    detail: str = ""
    error: Exception | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def saved(self) -> bool:
        return self.state == "saved"

    @property
    def recoverable(self) -> bool:
        """True when a local copy of the completed output still exists."""
        return self.artifact is not None and self.artifact.path is not None

    def sentence(self) -> str:
        """One line an operator can act on: state, run id, and where the work is."""
        where = (
            f"the completed output is on disk at {self.artifact.path}"
            if self.recoverable and self.artifact is not None
            else "no local copy of the output remains"
        )
        return f"{self.state} ({self.run_id}): {self.detail} ({where})"

    def summary(self) -> dict[str, Any]:
        """The projection safe to log: identity and outcome, never the payload."""
        return {
            "state": self.state,
            "run_id": self.run_id,
            "content_sha256": self.content_sha256,
            "staged_sha256": self.staged_sha256,
            "capped": self.capped,
            "verified": self.verified,
            "attempts": self.attempts,
            "artifact": str(self.artifact.path) if self.recoverable and self.artifact else None,
            "error": type(self.error).__name__ if self.error else None,
            "warnings": list(self.warnings),
        }


class RecoverableJobs:
    """Commit completed work so an expensive run survives a failed save.

    This is the single entry point. Everything it depends on is injected here
    and nowhere else: the store, the artifact directory, and the clock.

    Args:
        store: The authoritative destination. See :class:`.store.Store`.
        root: Directory for artifacts. Ignored when ``artifacts`` is given.
        artifacts: A pre-built :class:`.artifacts.ArtifactStore`.
        clock: Injected time. Defaults to the system clock.
        max_payload_bytes: Refuse outputs larger than this, before staging.
        max_attempts: Total store write attempts when the store is
            unreachable. 1 disables retrying.
        backoff_seconds: Base delay between those attempts; doubles each time.
        staging_policy: ``"require"`` (default) refuses to attempt the store
            write when no local copy could be made. ``"proceed"`` runs
            anyway, unprotected, and says so in the outcome's warnings.
        keep_artifact: Keep the local copy even after a verified save.

    Raises:
        ValueError: for an unusable configuration, at construction time.
    """

    def __init__(
        self,
        *,
        store: Store,
        root: str | Path | None = None,
        artifacts: ArtifactStore | None = None,
        clock: Clock | None = None,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        staging_policy: StagingPolicy = "require",
        keep_artifact: bool = False,
    ) -> None:
        if artifacts is None and root is None:
            raise ValueError("give either root= or artifacts=: there is nowhere to preserve to")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")
        if staging_policy not in ("require", "proceed"):
            raise ValueError(f"unknown staging policy {staging_policy!r}")

        self.clock = clock or SystemClock()
        self.artifacts = artifacts or ArtifactStore(
            root or ".",
            clock=self.clock,
            max_artifact_bytes=artifact_ceiling(max_payload_bytes),
        )
        self.store = store
        self.max_payload_bytes = max_payload_bytes
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.staging_policy: StagingPolicy = staging_policy
        self.keep_artifact = keep_artifact

    # ------------------------------------------------------------- commit

    def commit(
        self,
        run_id: str,
        payload: Any,
        *,
        label: str = "",
        metadata: dict[str, Any] | None = None,
        fit: Callable[[Any], Any] | None = None,
    ) -> CommitOutcome:
        """Preserve the completed output, then try to store it.

        Args:
            run_id: Stable id for this run. The caller mints it *before* the
                work starts, because an id nobody knows cannot be looked for
                after a timeout. Must be a safe file name.
            payload: The completed output: bytes, or a JSON value.
            label: Free text for a human listing the directory.
            metadata: JSON-only facts for triage. Not a second copy of the
                payload.
            fit: Optional reducer applied **after** staging, for a store with
                a size limit. It receives the payload and returns a smaller
                one; returning None means "unchanged". The artifact always
                keeps the full output.

        Returns:
            A :class:`CommitOutcome`. Store failures are outcomes, not
            exceptions.

        Raises:
            InvalidRunId, PayloadNotSupported, PayloadTooLarge: before
                anything is written.
            ArtifactExists: another owner already staged this run id.
            StagingFailed: under the default ``"require"`` policy, before the
                store is called.
        """
        validate_run_id(run_id)
        content, content_type = encode_payload(payload)
        staged_digest = digest(content)

        if len(content) > self.max_payload_bytes:
            # Before staging, so the refusal never masquerades as preservation.
            raise PayloadTooLarge(
                f"run {run_id!r} produced {len(content)} bytes, over the "
                f"{self.max_payload_bytes}-byte ceiling; nothing was written. Raise "
                "max_payload_bytes deliberately, or store the output somewhere sized "
                "for it."
            )

        warnings: list[str] = []
        artifact: Artifact | None = None
        try:
            artifact = self.artifacts.stage(
                run_id,
                payload,
                label=label,
                metadata=metadata,
                content=content,
                content_type=content_type,
            )
        except StagingFailed:
            if self.staging_policy == "require":
                # The expensive store write has not been attempted. The caller
                # still has the output in memory and can decide what to do.
                raise
            warnings.append(
                "no local copy could be written; this run is not recoverable if the "
                "save fails (staging_policy='proceed')"
            )
            logger.warning("run %s is proceeding without a recovery artifact", run_id)

        committed_content = content
        capped = False
        if fit is not None:
            reduced = fit(payload)
            if reduced is not None:
                reduced_content, reduced_type = encode_payload(reduced)
                if reduced_type != content_type:
                    raise ValueError(
                        "fit() changed the payload's content type, which would store "
                        "something the artifact cannot be compared against"
                    )
                if len(reduced_content) > len(content):
                    raise ValueError("fit() returned a larger payload than it was given")
                committed_content = reduced_content
                capped = reduced_content != content
                if capped:
                    warnings.append(
                        "the stored payload was capped to fit the store; the full "
                        "output is only in the local artifact"
                    )

        return self._save_and_verify(
            run_id=run_id,
            content=committed_content,
            content_type=content_type,
            staged_digest=staged_digest,
            artifact=artifact,
            capped=capped,
            warnings=warnings,
        )

    def recommit(self, artifact: Artifact) -> CommitOutcome:
        """Store a preserved output again, after a restart.

        The artifact is re-encoded and checked against its recorded digest
        first: committing something that no longer matches what was preserved
        would launder a corruption into the store.

        This is the recovery path. It does not re-run the work, and it does
        not resume anything: the output already exists.
        """
        content, content_type = encode_payload(artifact.payload)
        if digest(content) != artifact.content_sha256 or content_type != artifact.content_type:
            raise ArtifactCorrupt(
                f"the payload for run {artifact.run_id!r} does not match its recorded "
                "digest; it has not been committed"
            )
        return self._save_and_verify(
            run_id=artifact.run_id,
            content=content,
            content_type=content_type,
            staged_digest=artifact.content_sha256,
            artifact=artifact,
            capped=False,
            warnings=[],
        )

    # -------------------------------------------------------------- store

    def _save_and_verify(
        self,
        *,
        run_id: str,
        content: bytes,
        content_type: str,
        staged_digest: str,
        artifact: Artifact | None,
        capped: bool,
        warnings: list[str],
    ) -> CommitOutcome:
        expected = digest(content)

        def outcome(
            state: CommitState,
            *,
            detail: str,
            verified: bool = False,
            attempts: int = 0,
            error: Exception | None = None,
            keep: bool = True,
        ) -> CommitOutcome:
            result = CommitOutcome(
                state=state,
                run_id=run_id,
                content_sha256=expected,
                staged_sha256=staged_digest,
                artifact=artifact,
                capped=capped,
                verified=verified,
                attempts=attempts,
                detail=detail,
                error=error,
                warnings=tuple(warnings),
            )
            if keep:
                return result
            return self._discard(result)

        attempts = 0
        preflight = self._preflight(run_id, expected)
        if preflight is not None:
            state, detail, error = preflight
            if state == "saved":
                # Byte-identical content is already there. Committing again is
                # a no-op, which is what makes recovery safe to re-run.
                return outcome("saved", detail=detail, verified=True, keep=False)
            return outcome(state, detail=detail, error=error)

        while True:
            attempts += 1
            try:
                self.store.save(run_id, content, content_type)
                break
            except StoreOccupied as taken:
                # Somebody else's output is under this id and the store refused
                # to destroy it, which is the contract. This run's output stays
                # on disk: it is the only copy of it that exists.
                return outcome(
                    "conflict",
                    detail=(
                        f"run {run_id!r} already holds different content in the "
                        "store, which was left untouched; this run's output was "
                        "not stored"
                    ),
                    attempts=attempts,
                    error=taken,
                )
            except StoreUnavailable as unreachable:
                if attempts >= self.max_attempts:
                    return outcome(
                        "absent",
                        detail=(
                            f"the store was unreachable after {attempts} attempts, so "
                            "the write was never sent and nothing was stored"
                        ),
                        attempts=attempts,
                        error=unreachable,
                    )
                self.clock.sleep(self.backoff_seconds * (2 ** (attempts - 1)))
            except StoreRefused as refused:
                # A refusal is a decision, not a transport problem. Retrying an
                # identical rejected write only repeats the rejection.
                return outcome(
                    "absent",
                    detail=f"the store refused the write, so nothing was stored: {refused}",
                    attempts=attempts,
                    error=refused,
                )
            except StoreTimeout as slow:
                return self._reconcile(
                    run_id=run_id,
                    expected=expected,
                    staged_digest=staged_digest,
                    artifact=artifact,
                    capped=capped,
                    warnings=warnings,
                    attempts=attempts,
                    slow=slow,
                )
            except StoreError as unclassified:
                return outcome(
                    "unknown",
                    detail=(
                        f"the store failed in a way this adapter does not classify "
                        f"({type(unclassified).__name__}), so the outcome is unknown"
                    ),
                    attempts=attempts,
                    error=unclassified,
                )

        # The store accepted it. That is a claim, and it is checked.
        return self._verify(
            run_id=run_id,
            expected=expected,
            staged_digest=staged_digest,
            artifact=artifact,
            capped=capped,
            warnings=warnings,
            attempts=attempts,
            after="the store accepted the write",
            absent_state="unknown",
        )

    def _preflight(
        self, run_id: str, expected: str
    ) -> tuple[CommitState, str, Exception | None] | None:
        """Look before writing. Returns None when the write should proceed.

        This is a **narrowing**, not a lock. Between this read and the write
        another writer can still claim the id, so the guarantee that a foreign
        document is never destroyed belongs to the adapter's atomic conditional
        write — see :mod:`workrecovery.store`. What this buys is the common
        case: a collision that already exists is reported without an attempt,
        and an identical re-commit costs no write at all.

        A store that will not answer is not treated as empty: the write goes
        ahead and the read-back decides, which is the pre-existing behaviour.
        """
        try:
            existing = self.store.load(run_id)
        except Exception:  # noqa: BLE001 - an unanswered read is not an answer
            return None
        if existing is None:
            return None
        if digest(existing) == expected:
            return (
                "saved",
                f"run {run_id!r} already holds these exact bytes; nothing was rewritten",
                None,
            )
        return (
            "conflict",
            (
                f"run {run_id!r} already holds different content ({len(existing)} "
                f"bytes, digest {digest(existing)[:12]}… != {expected[:12]}…); it "
                "was not overwritten and this run's output was not stored"
            ),
            StoreOccupied(f"run {run_id!r} is already taken by different content"),
        )

    def _reconcile(
        self,
        *,
        run_id: str,
        expected: str,
        staged_digest: str,
        artifact: Artifact | None,
        capped: bool,
        warnings: list[str],
        attempts: int,
        slow: StoreTimeout,
    ) -> CommitOutcome:
        """A timed-out write may have landed. Look before declaring it lost."""
        return self._verify(
            run_id=run_id,
            expected=expected,
            staged_digest=staged_digest,
            artifact=artifact,
            capped=capped,
            warnings=warnings,
            attempts=attempts,
            after=f"the {slow.operation} timed out",
            absent_state="absent",
            error=slow,
        )

    def _verify(
        self,
        *,
        run_id: str,
        expected: str,
        staged_digest: str,
        artifact: Artifact | None,
        capped: bool,
        warnings: list[str],
        attempts: int,
        after: str,
        absent_state: CommitState,
        error: Exception | None = None,
    ) -> CommitOutcome:
        def outcome(
            state: CommitState, *, detail: str, verified: bool = False,
            failure: Exception | None = error,
        ) -> CommitOutcome:
            return CommitOutcome(
                state=state,
                run_id=run_id,
                content_sha256=expected,
                staged_sha256=staged_digest,
                artifact=artifact,
                capped=capped,
                verified=verified,
                attempts=attempts,
                detail=detail,
                error=failure,
                warnings=tuple(warnings),
            )

        try:
            stored = self.store.load(run_id)
        except Exception as blind:  # noqa: BLE001 - any read failure is "unknown"
            return outcome(
                "unknown",
                detail=(
                    f"{after}, and the check for it also failed "
                    f"({type(blind).__name__}), so run {run_id!r} is of unknown status — "
                    "look for it before running this work again"
                ),
                failure=blind,
            )

        if stored is None:
            detail = (
                f"{after} and run {run_id!r} is not in the store, so nothing was written"
                if absent_state == "absent"
                else (
                    f"{after}, but reading it back returned nothing. Do not treat this "
                    "run as saved: the store may be catching up, or it may have "
                    "discarded the write"
                )
            )
            return outcome(absent_state, detail=detail)

        if digest(stored) != expected:
            # Something is under that id. That is not the same as "our output
            # landed", and reporting it as success reports another run's write.
            return outcome(
                "unknown",
                detail=(
                    f"{after}, and run {run_id!r} exists in the store but holds "
                    f"different content ({len(stored)} bytes, digest "
                    f"{digest(stored)[:12]}… != {expected[:12]}…) — do not treat this "
                    "run as saved"
                ),
            )

        result = outcome(
            "saved",
            detail=f"{after}; the stored bytes were read back and are identical",
            verified=True,
        )
        return self._discard(result)

    # ------------------------------------------------------------ cleanup

    def _discard(self, result: CommitOutcome) -> CommitOutcome:
        """Remove the local copy — only when the store provably holds it all.

        Two conditions, both required. The read-back matched, and nothing was
        capped: when the stored payload is a reduced copy, the artifact is the
        only place the full output exists and deleting it would destroy the
        thing this package was built to protect.
        """
        artifact = result.artifact
        if artifact is None or self.keep_artifact or not result.verified:
            return result
        if result.capped or result.content_sha256 != result.staged_sha256:
            return replace(
                result,
                warnings=result.warnings
                + (
                    "the local artifact was kept: the store holds a capped copy, so it "
                    "is the only place the full output exists",
                ),
            )
        try:
            self.artifacts.discard(artifact)
        except StaleArtifact as stale:
            return replace(result, warnings=result.warnings + (str(stale),))
        return replace(result, artifact=None)

    # ---------------------------------------------------------- recovery

    def pending(self) -> list[Artifact]:
        """Completed outputs still on disk — the runs that did not land."""
        return self.artifacts.list()

    def problems(self) -> list[tuple[Path, str]]:
        """Files in the recovery directory that do not read back, with reasons."""
        return self.artifacts.problems()

    def read(self, run_id: str | Path) -> Artifact:
        """One preserved output **by run id**, digest verified.

        Dispatch is by type, never by the shape of the string: a run id may
        legitimately contain a dot, and guessing that ``"nightly.0001"`` is a
        file name turned a valid id into a CWD-relative path lookup that could
        not find work that was plainly on disk. A :class:`~pathlib.Path` is
        forwarded to :meth:`read_path`; a ``str`` is always a run id.
        """
        if isinstance(run_id, Path):
            return self.read_path(run_id)
        return self.artifacts.read_run(run_id)

    def read_path(self, path: str | Path) -> Artifact:
        """One preserved output by path, refusing anything outside the root.

        Raises:
            InvalidRunId: the path is not inside the recovery root. A recovery
                API that will also delete what it reads has no business
                reading somewhere it does not own.
        """
        return self.artifacts.read_inside_root(path)

    def discard(self, artifact: Artifact) -> None:
        """Remove one preserved output, after proving it is still that one."""
        self.artifacts.discard(artifact)


__all__ = [
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "CommitOutcome",
    "CommitState",
    "RecoverableJobs",
    "StagingPolicy",
]
