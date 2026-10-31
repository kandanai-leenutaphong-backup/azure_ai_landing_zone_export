"""Worked example 2 — the write timed out. Did it land? Look before answering.

Run it: ``python3 examples/02_commit_then_timeout.py``.

A store write that times out client-side **may already have succeeded**. Those
are two different worlds and the caller has to be told which one it is in:

- it landed  → the run is done; re-running it would duplicate real work;
- it did not → the run is not done; the output is still on disk, locally.

The difference is one cheap read of the id the caller minted. Reporting
"nothing was saved" without that read is how twenty minutes of finished work
gets done twice — or worse, how a completed run is silently lost.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


from workrecovery import (  # noqa: E402
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    StoreTimeout,
    encode_payload,
)

root = Path(tempfile.mkdtemp(prefix="recovery-example-"))
try:
    payload = {"rows": [1, 2, 3], "summary": "done"}
    expected, _ = encode_payload(payload)

    # ---------------------------------------------------- it landed anyway
    # The item is recorded and *then* the call raises: exactly what happens
    # when a client-side read timeout fires after the store committed.
    landed = MemoryStore(timeout=StoreTimeout(operation="read-back"), lands=True)
    jobs = RecoverableJobs(store=landed, root=root, clock=FixedClock())

    outcome = jobs.commit("run-that-timed-out", payload)

    assert outcome.state == "saved"
    assert outcome.verified is True
    assert "read-back timed out" in outcome.detail
    assert landed.loads == 2, "one pre-write check and one read-back, not a poll loop"
    # It really is in the store, byte for byte.
    assert landed.items["run-that-timed-out"] == expected
    # And the local copy is gone, because the store provably holds it.
    assert outcome.artifact is None
    assert jobs.pending() == []

    # ------------------------------------------------------ it did not land
    lost = MemoryStore(timeout=StoreTimeout(operation="write"), lands=False)
    jobs = RecoverableJobs(store=lost, root=root, clock=FixedClock())

    outcome = jobs.commit("run-that-was-lost", payload)

    assert outcome.state == "absent"
    assert outcome.saved is False
    assert outcome.verified is False
    assert "nothing was written" in outcome.detail
    assert isinstance(outcome.error, StoreTimeout)

    # The work is not lost with it: the artifact is still there, and the
    # outcome names the file rather than making somebody guess.
    assert outcome.recoverable is True
    assert outcome.artifact is not None and outcome.artifact.path is not None
    assert outcome.artifact.path.exists()
    assert str(outcome.artifact.path) in outcome.sentence()

    preserved = jobs.pending()
    assert [a.run_id for a in preserved] == ["run-that-was-lost"]
    assert preserved[0].payload == payload

    print("02_commit_then_timeout: ok")
finally:
    shutil.rmtree(root, ignore_errors=True)
