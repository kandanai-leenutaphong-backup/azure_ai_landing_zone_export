"""Worked example 4 — a fresh process finds the work and commits it again.

Run it: ``python3 examples/04_restart_and_recommit.py``.

This is the recovery half, and it is deliberately unglamorous: the output is
already complete, so nothing is re-run and nothing is resumed. A new process
opens the directory, reads what is there, and offers it to the store again.

It also shows the two things that must *not* happen while recovering: an
unrelated run's artifact is not touched, and a second process claiming the same
run id is refused rather than allowed to overwrite the first one's only copy.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


from workrecovery import (  # noqa: E402
    ArtifactExists,
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    StoreTimeout,
)

root = Path(tempfile.mkdtemp(prefix="recovery-example-"))
try:
    payload = {"rows": [{"id": 1}, {"id": 2}], "note": "expensive"}

    # ---------------------------------------------------- the failed run
    down = MemoryStore(timeout=StoreTimeout(operation="write"))
    first = RecoverableJobs(store=down, root=root, clock=FixedClock())
    lost = first.commit("run-a", payload, label="the run that did not land")
    assert lost.state == "absent"

    # A second, unrelated run also fails. It must survive the first one's
    # recovery untouched.
    other = first.commit("run-b", {"rows": ["unrelated"]}, label="somebody else's run")
    assert other.state == "absent"

    # Two owners, one run id: refused, and the existing file is preserved.
    before = (root / "run-a.artifact.json").read_bytes()
    try:
        first.commit("run-a", {"rows": ["a different answer"]})
    except ArtifactExists as clash:
        assert "left untouched" in str(clash)
    else:  # pragma: no cover
        raise AssertionError("a second owner of one run id must be refused")
    assert (root / "run-a.artifact.json").read_bytes() == before

    # ------------------------------------------------- a new process, later
    # Nothing is carried over: new store handle, new objects, same directory.
    up = MemoryStore()
    after_restart = RecoverableJobs(store=up, root=root, clock=FixedClock())

    waiting = after_restart.pending()
    assert sorted(a.run_id for a in waiting) == ["run-a", "run-b"]
    assert after_restart.problems() == []

    # The output came back exactly as it was produced, digest verified on read.
    recovered = after_restart.read("run-a")
    assert recovered.payload == payload
    assert recovered.label == "the run that did not land"
    assert recovered.content_sha256 == lost.staged_sha256

    outcome = after_restart.recommit(recovered)

    assert outcome.state == "saved"
    assert outcome.verified is True
    assert up.items["run-a"] is not None
    # Committed, verified, so the local copy is now redundant and removed.
    assert not (root / "run-a.artifact.json").exists()

    # The unrelated run was left completely alone.
    assert (root / "run-b.artifact.json").exists()
    assert [a.run_id for a in after_restart.pending()] == ["run-b"]
    assert after_restart.read("run-b").payload == {"rows": ["unrelated"]}

    print("04_restart_and_recommit: ok")
finally:
    shutil.rmtree(root, ignore_errors=True)
