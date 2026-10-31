"""The failures this package raises, and the vocabulary a store speaks back.

WHY THE STORE EXCEPTIONS LIVE HERE
----------------------------------
The destination store is the caller's — a database, a queue, an object store,
an HTTP API. This package never imports one. What it does need is a way to
tell three outcomes apart, because they lead to three different actions:

- **refused** — the store said no. Nothing was written; do not look for it.
- **unavailable** — the store could not be reached. Nothing was sent.
- **timed out** — the request was sent and the answer never came. It may have
  landed. This is the one that must never be reported as "nothing was saved",
  because an operator who believes that re-runs work that already exists.

So the adapter a caller writes translates its own client's errors into these
three, and everything downstream is decidable. See GOTCHAS.md, G1.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations


class RecoveryError(Exception):
    """Base class. One ``except`` clause catches everything from this package."""


# ------------------------------------------------------------- the payload


class PayloadNotSupported(RecoveryError):
    """The payload is not one of the two shapes this package can preserve."""


class PayloadTooLarge(RecoveryError):
    """The completed output exceeds the configured ceiling.

    Raised **before** anything is written, so a bound that is too small costs
    an error rather than a half-preserved run.
    """


# ------------------------------------------------------------ the artifact


class InvalidRunId(RecoveryError):
    """The run id cannot be used as a file name safely.

    Run ids become file names, so a separator, a ``..`` segment or an absolute
    path in one is a path-traversal attempt, not a naming preference.
    """


class StagingFailed(RecoveryError):
    """The local copy could not be written, so no recovery is guaranteed.

    Under the default policy this is raised *before* the expensive store write
    is attempted, because a run with no safety net should learn that while it
    can still choose to stop. See GOTCHAS.md, G3.
    """


class ArtifactExists(RecoveryError):
    """An artifact already exists for this run id, and was left untouched.

    Two processes claiming one run id is an ownership problem. The first one's
    output is not overwritten to resolve it. See GOTCHAS.md, G5.
    """


class ArtifactMissing(RecoveryError):
    """No artifact exists at that path."""


class ArtifactCorrupt(RecoveryError):
    """The artifact does not match its recorded digest, or is not readable.

    Truncated, hand-edited or partially written. It is never repaired, never
    silently accepted, and never deleted by this package. See GOTCHAS.md, G6.
    """


class StaleArtifact(RecoveryError):
    """A discard was asked for, and the file on disk is not the one recorded.

    The file is left where it is. Deleting an unrecognised file to tidy up is
    how the only copy of something else's work disappears. See GOTCHAS.md, G7.
    """


# ---------------------------------------------------------------- the store


class StoreError(RecoveryError):
    """Base class for the three outcomes a store adapter reports."""


class StoreRefused(StoreError):
    """The store rejected the write. Nothing landed."""


class StoreUnavailable(StoreError):
    """The store could not be reached. The request was never sent."""


class StoreTimeout(StoreError):
    """The write was sent and no answer arrived. It may have landed.

    Attributes:
        operation: ``"write"`` or ``"read-back"``, so a reconciler knows which
            clock ran out.
    """

    def __init__(self, message: str = "the store did not answer", *, operation: str = "write"):
        super().__init__(message)
        self.operation = operation


class StoreOccupied(StoreError):
    """The run id already holds *different* content, which was not overwritten.

    Two owners for one run id is an ownership bug. The store's answer is the
    same as the artifact store's: refuse, and leave the first writer's bytes
    exactly as they were. The second writer keeps its local artifact and is
    told, so the output it just produced is not lost to a collision it did not
    cause. See CONTRACT.md, "The store contract", and GOTCHAS.md, G10.
    """


__all__ = [
    "ArtifactCorrupt",
    "ArtifactExists",
    "ArtifactMissing",
    "InvalidRunId",
    "PayloadNotSupported",
    "PayloadTooLarge",
    "RecoveryError",
    "StagingFailed",
    "StaleArtifact",
    "StoreError",
    "StoreOccupied",
    "StoreRefused",
    "StoreTimeout",
    "StoreUnavailable",
]
