"""Suites that need a framework: races, filesystem attacks, cross-process bytes.

    pip install -r requirements-dev.txt && python3 -m pytest tests

Everything here is offline and writes only inside a per-test temporary
directory. ``tests/selftest.py`` covers the same mechanism without a framework;
these are the cases where fixtures, subprocesses and threads earn their keep.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workrecovery import (  # noqa: E402
    ArtifactExists,
    ArtifactStore,
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    StoreTimeout,
    digest,
    encode_payload,
)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "recovery"


def test_two_threads_racing_one_run_id_produce_one_winner(root: Path) -> None:
    store = ArtifactStore(root, clock=FixedClock())
    start = threading.Barrier(8)
    results: list[str] = []
    lock = threading.Lock()

    def claim(index: int) -> None:
        start.wait()
        try:
            store.stage("contested", {"claimed_by": index})
        except ArtifactExists:
            outcome = "refused"
        else:
            outcome = f"won-{index}"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [r for r in results if r.startswith("won-")]
    assert len(winners) == 1, results
    assert results.count("refused") == 7

    # The file on disk belongs to the winner and is intact.
    stored = store.read_run("contested")
    assert stored.payload == {"claimed_by": int(winners[0].split("-")[1])}
    assert list(root.glob("*.tmp")) == [], "no temporary file survives the race"
    assert len(list(root.glob("*.artifact.json"))) == 1


def test_staging_never_follows_a_symlink_planted_at_the_target(root: Path) -> None:
    root.mkdir(parents=True)
    outside = root.parent / "somebody-elses-file"
    outside.write_text("do not touch", encoding="utf-8")
    (root / "victim.artifact.json").symlink_to(outside)

    store = ArtifactStore(root, clock=FixedClock())
    with pytest.raises(ArtifactExists):
        store.stage("victim", {"rows": [1]})

    assert outside.read_text(encoding="utf-8") == "do not touch"


def test_a_run_id_cannot_escape_the_recovery_root(root: Path) -> None:
    jobs = RecoverableJobs(store=MemoryStore(), root=root, clock=FixedClock())
    outside = root.parent / "escaped.artifact.json"

    for attempt in ("../escaped", "sub/escaped", "/etc/passwd", "..", "."):
        with pytest.raises(Exception) as caught:
            jobs.commit(attempt, {"rows": [1]})
        assert "run id" in str(caught.value)

    assert not outside.exists()
    assert not root.exists() or list(root.glob("*")) == []


def test_the_directory_mode_is_owner_only_by_default(root: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores permission bits")
    previous_umask = os.umask(0o022)
    try:
        ArtifactStore(root, clock=FixedClock()).stage("run-1", {"a": 1})
        assert oct(root.stat().st_mode)[-3:] == "700"

        other = root.parent / "shared"
        ArtifactStore(other, clock=FixedClock(), dir_mode=0o750).stage("run-1", {"a": 1})
        assert oct(other.stat().st_mode)[-3:] == "750"
    finally:
        os.umask(previous_umask)


def test_canonical_bytes_are_identical_in_another_interpreter(root: Path) -> None:
    """The digest must not depend on this process's dict ordering or hashing."""
    payload = {"z": 1, "a": [{"b": 2, "a": 1}], "unicode": "café", "n": 1.5}
    here, _ = encode_payload(payload)

    program = (
        "import sys, json;"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r});"
        "from workrecovery import encode_payload, digest;"
        f"content, _ = encode_payload(json.loads({json.dumps(payload)!r}));"
        "print(digest(content))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=60,
        env=dict(os.environ, PYTHONHASHSEED="1"),
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == digest(here)


def test_a_recovered_artifact_survives_a_real_process_restart(root: Path) -> None:
    """Write in this process, read it back from a genuinely separate one."""
    jobs = RecoverableJobs(
        store=MemoryStore(timeout=StoreTimeout()), root=root, clock=FixedClock()
    )
    payload = {"rows": [{"id": i} for i in range(50)], "note": "café"}
    outcome = jobs.commit("survivor", payload, label="restart me")
    assert outcome.state == "absent"

    program = (
        "import sys;"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r});"
        "from workrecovery import RecoverableJobs, MemoryStore;"
        f"jobs = RecoverableJobs(store=MemoryStore(), root={str(root)!r});"
        "artifact = jobs.read('survivor');"
        "result = jobs.recommit(artifact);"
        "print(result.state, result.verified, len(artifact.payload['rows']))"
    )
    proc = subprocess.run([sys.executable, "-c", program], capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "saved True 50"
    # The other process cleaned up after its verified save.
    assert not (root / "survivor.artifact.json").exists()


def test_unrelated_files_in_the_directory_are_ignored_entirely(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "notes.txt").write_text("an operator's note", encoding="utf-8")
    (root / "subdir").mkdir()

    jobs = RecoverableJobs(
        store=MemoryStore(timeout=StoreTimeout()), root=root, clock=FixedClock()
    )
    jobs.commit("run-1", {"rows": [1]})

    assert [a.run_id for a in jobs.pending()] == ["run-1"]
    assert jobs.problems() == []
    assert (root / "notes.txt").exists()
    assert (root / "subdir").is_dir()


def test_created_at_comes_from_the_injected_clock(root: Path) -> None:
    clock = FixedClock(start="1999-12-31T23:59:59Z")
    jobs = RecoverableJobs(
        store=MemoryStore(timeout=StoreTimeout()), root=root, clock=clock
    )
    jobs.commit("run-1", {"a": 1})
    clock.set("2000-01-01T00:00:01Z")
    jobs.commit("run-2", {"a": 2})

    stamps = {a.run_id: a.created_at for a in jobs.pending()}
    assert stamps == {
        "run-1": "1999-12-31T23:59:59Z",
        "run-2": "2000-01-01T00:00:01Z",
    }


def test_a_custom_artifact_store_can_be_injected(root: Path) -> None:
    artifacts = ArtifactStore(root / "elsewhere", clock=FixedClock(), dir_mode=0o700)
    jobs = RecoverableJobs(
        store=MemoryStore(timeout=StoreTimeout()), artifacts=artifacts, clock=FixedClock()
    )
    jobs.commit("run-1", {"a": 1})
    assert (root / "elsewhere" / "run-1.artifact.json").exists()


@pytest.mark.parametrize(
    ("store_kwargs", "expected"),
    [
        ({}, "saved"),
        ({"refuse": "no"}, "absent"),
        ({"timeout": StoreTimeout(), "lands": False}, "absent"),
        ({"timeout": StoreTimeout(), "lands": True}, "saved"),
        ({"load_blind": True}, "unknown"),
        ({"load_error": RuntimeError("mute")}, "unknown"),
    ],
)
def test_the_outcome_matrix_is_stable(root: Path, store_kwargs: dict, expected: str) -> None:
    store = MemoryStore(**store_kwargs)
    jobs = RecoverableJobs(store=store, root=root, clock=FixedClock())
    outcome = jobs.commit("run-1", {"rows": [1]})

    assert outcome.state == expected
    assert outcome.saved is (expected == "saved")
    # The local copy survives exactly when the save was not verified.
    assert outcome.recoverable is (expected != "saved")
    assert outcome.run_id in outcome.sentence()
    assert outcome.detail
