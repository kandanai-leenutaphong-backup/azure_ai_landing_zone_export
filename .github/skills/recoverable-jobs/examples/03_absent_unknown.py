"""Worked example 3 — known-missing, refused, unreachable, and unknown.

Run it: ``python3 examples/03_absent_unknown.py``.

Four store failures, four different things to tell an operator. Collapsing
them into one "save failed" is what makes recovery guesswork:

- **refused** — the store said no. Nothing landed. Do not look for it.
- **unreachable** — never sent. Retried, bounded, then reported absent.
- **accepted but not readable back** — unknown. It may be catching up. Do not
  claim it is saved, and do not claim it is lost either.
- **the check itself failed** — unknown, with the id, so a person can look.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


from workrecovery import (  # noqa: E402
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    StoreRefused,
    StoreUnavailable,
)

root = Path(tempfile.mkdtemp(prefix="recovery-example-"))
try:
    payload = {"rows": [1, 2, 3]}

    # ------------------------------------------------------------ refused
    refused = MemoryStore(refuse="document exceeds the container's schema")
    jobs = RecoverableJobs(store=refused, root=root, clock=FixedClock())
    outcome = jobs.commit("run-refused", payload)

    assert outcome.state == "absent"
    assert isinstance(outcome.error, StoreRefused)
    assert outcome.attempts == 1, "a refusal is a decision; retrying repeats it"
    assert refused.loads == 1, "one pre-write check; a refusal is never read back"
    assert outcome.recoverable is True

    # -------------------------------------------------------- unreachable
    clock = FixedClock()
    unreachable = MemoryStore(unavailable_times=99)
    jobs = RecoverableJobs(
        store=unreachable, root=root, clock=clock, max_attempts=3, backoff_seconds=0.5
    )
    outcome = jobs.commit("run-unreachable", payload)

    assert outcome.state == "absent"
    assert isinstance(outcome.error, StoreUnavailable)
    assert outcome.attempts == 3
    # Bounded, and the schedule is data rather than a delay a test must wait
    # out: two backoffs between three attempts, doubling.
    assert clock.slept == [0.5, 1.0]
    assert outcome.recoverable is True

    # A store that recovers on the third attempt just works.
    clock = FixedClock()
    flaky = MemoryStore(unavailable_times=2)
    jobs = RecoverableJobs(store=flaky, root=root, clock=clock, max_attempts=3)
    outcome = jobs.commit("run-flaky", payload)
    assert outcome.state == "saved" and outcome.attempts == 3
    assert clock.slept == [1.0, 2.0]

    # ------------------------------- accepted, but the read-back is blind
    blind = MemoryStore(load_blind=True)
    jobs = RecoverableJobs(store=blind, root=root, clock=FixedClock())
    outcome = jobs.commit("run-blind", payload)

    assert outcome.state == "unknown", "accepted is not stored"
    assert outcome.verified is False
    assert "Do not treat this run as saved" in outcome.detail
    assert outcome.recoverable is True, "the local copy stays until it is proven redundant"

    # ------------------------------------------- the check itself failed
    mute = MemoryStore(load_error=RuntimeError("the store would not answer"))
    jobs = RecoverableJobs(store=mute, root=root, clock=FixedClock())
    outcome = jobs.commit("run-mute", payload)

    assert outcome.state == "unknown"
    assert "unknown status" in outcome.detail
    assert "run-mute" in outcome.detail, "the id is in the message; somebody has to look"
    assert isinstance(outcome.error, RuntimeError)
    assert outcome.recoverable is True

    # Every run that did not verify still has its output on disk.
    assert sorted(a.run_id for a in jobs.pending()) == [
        "run-blind",
        "run-mute",
        "run-refused",
        "run-unreachable",
    ]

    print("03_absent_unknown: ok")
finally:
    shutil.rmtree(root, ignore_errors=True)
