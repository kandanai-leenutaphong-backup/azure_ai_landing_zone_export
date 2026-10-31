"""Worked example 6 — a store size cap that does not quietly eat the tail.

Run it: ``python3 examples/06_capped_payload.py``.

Some stores have a hard per-item size limit. Capping the payload to fit is a
reasonable answer: keeping most of an expensive run beats refusing all of it.
Doing it in the wrong order is not.

The failure this example exists to prevent is real and was shipped once: the
payload was capped **first**, the local copy was written **after**, and the
message promised operators that "the full set is in the local artefact". It
was not. The dropped tail existed nowhere.

Here the artifact is written from the full output before ``fit`` is ever
called, and — because the store then holds strictly less than the artifact —
the local copy is **kept** even though the save succeeded. A verified save
only earns cleanup when the store has everything.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


from workrecovery import (  # noqa: E402
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    decode_payload,
    encode_payload,
)

root = Path(tempfile.mkdtemp(prefix="recovery-example-"))
try:
    full = {"rows": [{"id": i} for i in range(500)]}
    full_bytes, _ = encode_payload(full)

    def fit(payload: dict) -> dict:
        """Whatever the store will actually accept — here, the first 100 rows."""
        return {"rows": payload["rows"][:100]}

    store = MemoryStore()
    jobs = RecoverableJobs(store=store, root=root, clock=FixedClock())
    outcome = jobs.commit("capped-run", full, fit=fit, label="capped export")

    # The save worked, and it was verified against what was actually stored.
    assert outcome.state == "saved"
    assert outcome.verified is True
    assert outcome.capped is True

    # Two digests, deliberately: what was produced, and what was stored.
    assert outcome.staged_sha256 != outcome.content_sha256
    assert decode_payload(store.items["capped-run"], "application/json") == fit(full)

    # The artifact still exists and still holds all five hundred rows.
    assert outcome.recoverable is True
    assert outcome.artifact is not None and outcome.artifact.path is not None
    preserved = jobs.read("capped-run")
    assert preserved.payload == full
    assert len(preserved.payload["rows"]) == 500
    assert preserved.content_sha256 == outcome.staged_sha256
    assert (outcome.artifact.path).read_bytes()  # on disk, not just in memory

    # And the caller is told, in words, why the file is still there.
    assert any("capped" in warning for warning in outcome.warnings)
    assert any("only place the full output exists" in w for w in outcome.warnings)

    # A `fit` that changes nothing is not a cap, and cleanup proceeds normally.
    plain = RecoverableJobs(store=MemoryStore(), root=root, clock=FixedClock())
    unchanged = plain.commit("uncapped-run", full, fit=lambda payload: None)
    assert unchanged.state == "saved"
    assert unchanged.capped is False
    assert unchanged.artifact is None
    assert unchanged.content_sha256 == unchanged.staged_sha256 == outcome.staged_sha256
    assert len(full_bytes) > 0

    print("06_capped_payload: ok")
finally:
    shutil.rmtree(root, ignore_errors=True)
