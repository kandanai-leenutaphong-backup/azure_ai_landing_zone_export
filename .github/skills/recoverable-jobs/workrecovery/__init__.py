"""workrecovery — completed expensive work survives a failed save.

The job finished. The save is the risky part: it can be slow, it can fail, and
the process can be killed in the middle of it. This package writes the finished
output to a local file *first*, then stores it, then verifies the store really
holds the identical bytes, and only then removes the local copy.

    from workrecovery import RecoverableJobs

    jobs = RecoverableJobs(store=my_store, root="/var/lib/recovery")
    outcome = jobs.commit(run_id, results)
    if not outcome.saved:
        print(outcome.sentence())      # names the file the work is still in

Nothing here is AI-specific, and nothing here talks to a cloud service: the
store is yours and is injected.

Public surface
--------------
- :class:`RecoverableJobs` — the entry point: ``commit``, ``recommit``,
  ``pending``, ``problems``, ``read``, ``read_path``, ``discard``.
- :class:`CommitOutcome`, :data:`CommitState`, :data:`StagingPolicy` — what
  happened, in four distinguishable states.
- :class:`Store`, :class:`MemoryStore` — the destination protocol, and an
  in-memory one that reproduces its failures.
- :class:`ArtifactStore`, :class:`Artifact`, :func:`validate_run_id`,
  :data:`ENVELOPE_SCHEMA`, :data:`ENVELOPE_VERSION` — the durable local copy.
- :class:`Clock`, :class:`SystemClock`, :class:`FixedClock` — injected time.
- :func:`encode_payload`, :func:`decode_payload`, :func:`digest`,
  :data:`JSON_CONTENT_TYPE`, :data:`BYTES_CONTENT_TYPE` — what a payload is.
- :class:`RecoveryError` and its subclasses — every failure that escapes.
- :data:`DEFAULT_MAX_PAYLOAD_BYTES`, :data:`DEFAULT_MAX_ATTEMPTS`,
  :data:`DEFAULT_BACKOFF_SECONDS`, :data:`DEFAULT_MAX_METADATA_BYTES`,
  :data:`MAX_LABEL_CHARS` — the bounds.
"""

from workrecovery.artifacts import (
    DEFAULT_MAX_ARTIFACT_BYTES,
    DEFAULT_MAX_METADATA_BYTES,
    ENVELOPE_SCHEMA,
    ENVELOPE_VERSION,
    MAX_LABEL_CHARS,
    Artifact,
    ArtifactStore,
    artifact_ceiling,
    validate_run_id,
)
from workrecovery.clock import Clock, FixedClock, SystemClock
from workrecovery.commit import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_PAYLOAD_BYTES,
    CommitOutcome,
    CommitState,
    RecoverableJobs,
    StagingPolicy,
)
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
    StoreError,
    StoreOccupied,
    StoreRefused,
    StoreTimeout,
    StoreUnavailable,
)
from workrecovery.payload import (
    BYTES_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    decode_payload,
    digest,
    encode_payload,
)
from workrecovery.store import MemoryStore, Store

__version__ = "1.0.0"

__all__ = [
    "Artifact",
    "ArtifactCorrupt",
    "ArtifactExists",
    "ArtifactMissing",
    "ArtifactStore",
    "BYTES_CONTENT_TYPE",
    "Clock",
    "CommitOutcome",
    "CommitState",
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_MAX_ARTIFACT_BYTES",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_METADATA_BYTES",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "ENVELOPE_SCHEMA",
    "ENVELOPE_VERSION",
    "FixedClock",
    "MAX_LABEL_CHARS",
    "InvalidRunId",
    "JSON_CONTENT_TYPE",
    "MemoryStore",
    "PayloadNotSupported",
    "PayloadTooLarge",
    "RecoverableJobs",
    "RecoveryError",
    "StagingFailed",
    "StagingPolicy",
    "StaleArtifact",
    "Store",
    "StoreError",
    "StoreOccupied",
    "StoreRefused",
    "StoreTimeout",
    "StoreUnavailable",
    "SystemClock",
    "__version__",
    "artifact_ceiling",
    "decode_payload",
    "digest",
    "encode_payload",
    "validate_run_id",
]
