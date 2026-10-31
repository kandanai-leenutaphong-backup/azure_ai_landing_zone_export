"""Worked example 1 — an ordinary batch export, preserved and then stored.

Run it: ``python3 examples/01_generic_export.py``. Offline, no model, no cloud:
the store is an in-memory double and the artifacts go to a temporary directory
this script deletes when it is finished.

The job here is deliberately boring — a nightly export — because none of this
is AI-specific. What makes it worth protecting is that the work is expensive
and already finished by the time the risky part starts.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


from workrecovery import (  # noqa: E402
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    digest,
    encode_payload,
)

root = Path(tempfile.mkdtemp(prefix="recovery-example-"))
try:
    store = MemoryStore()
    jobs = RecoverableJobs(store=store, root=root, clock=FixedClock())

    # Forty minutes of work, finished, in memory. Nothing has written it down.
    export = {
        "generated_at": "2001-01-01T00:00:00Z",
        "rows": [{"id": i, "total": i * 3} for i in range(1000)],
    }

    # The run id is minted by the caller, before the work starts, because an
    # id nobody knows cannot be looked for after a timeout.
    outcome = jobs.commit("nightly-export-0001", export, label="nightly export")

    assert outcome.state == "saved"
    assert outcome.saved is True
    assert outcome.verified is True, "saved means read back and compared, not 'accepted'"
    assert outcome.attempts == 1
    assert outcome.capped is False
    assert outcome.warnings == ()

    # The digest is over the output bytes — not the input, not a row count.
    expected, content_type = encode_payload(export)
    assert outcome.content_sha256 == digest(expected)
    assert outcome.staged_sha256 == outcome.content_sha256
    assert content_type == "application/json"

    # The store holds exactly those bytes.
    assert store.items["nightly-export-0001"] == expected
    # Two reads, both cheap and both load-bearing: the pre-write check that the
    # id is free, and the read-back that turns "accepted" into "stored".
    assert store.saves == 1 and store.loads == 2

    # The local copy is gone, because the store demonstrably holds it. A
    # directory of artifacts is therefore a list of runs that did not land.
    assert outcome.artifact is None
    assert outcome.recoverable is False
    assert jobs.pending() == []
    assert list(root.iterdir()) == []

    # The loggable projection carries identity and outcome, never the payload.
    summary = outcome.summary()
    assert summary["state"] == "saved"
    assert "rows" not in str(summary)

    print("01_generic_export: ok")
finally:
    shutil.rmtree(root, ignore_errors=True)
