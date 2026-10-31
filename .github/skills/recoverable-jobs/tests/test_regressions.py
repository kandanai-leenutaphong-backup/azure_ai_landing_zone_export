"""Regressions for defects found by review, each reproduced before it was fixed.

    pip install -r requirements-dev.txt && python3 -m pytest tests

Every check here failed against the code as reviewed. Nothing sleeps, nothing
reaches a network, and every temporary directory is pytest's own.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workrecovery import (  # noqa: E402
    Artifact,
    ArtifactCorrupt,
    ArtifactStore,
    InvalidRunId,
    MemoryStore,
    PayloadNotSupported,
    PayloadTooLarge,
    RecoverableJobs,
    StagingFailed,
    StaleArtifact,
    StoreOccupied,
)
from workrecovery.payload import digest, encode_payload  # noqa: E402



def jobs_for(tmp_path: Path, store: MemoryStore, **kwargs: Any) -> RecoverableJobs:
    return RecoverableJobs(store=store, root=tmp_path / "recovery", **kwargs)


# ------------------------------------- F3 one bad file must not hide the rest


def test_a_deeply_nested_file_is_corrupt_not_a_recursion_error(tmp_path: Path) -> None:
    store = MemoryStore()
    jobs = jobs_for(tmp_path, store, keep_artifact=True)
    jobs.commit("good-0001", {"rows": 2})

    evil = jobs.artifacts.root / "evil.artifact.json"
    evil.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")

    listed = [artifact.run_id for artifact in jobs.pending()]
    assert listed == ["good-0001"]

    problems = dict((path.name, reason) for path, reason in jobs.problems())
    assert "evil.artifact.json" in problems
    assert evil.exists(), "a suspect file is reported, never deleted"

    with pytest.raises(ArtifactCorrupt):
        jobs.read_path(evil)


def test_an_oversized_file_is_refused_before_it_is_read(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    artifacts = ArtifactStore(root, max_artifact_bytes=4096)
    artifacts.stage("good-0001", {"rows": 1})

    fat = root / "fat.artifact.json"
    fat.write_bytes(b"{" + b"x" * 8192 + b"}")

    assert [a.run_id for a in artifacts.list()] == ["good-0001"]
    reasons = [reason for _, reason in artifacts.problems()]
    assert any("larger than" in reason for reason in reasons)
    with pytest.raises(ArtifactCorrupt) as caught:
        artifacts.read(fat)
    assert "larger than" in str(caught.value)
    assert fat.exists()


def test_a_symlinked_artifact_is_refused_rather_than_followed(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    artifacts = ArtifactStore(root)
    real = artifacts.stage("good-0001", {"rows": 1})
    link = root / "linked.artifact.json"
    link.symlink_to(real.path)

    with pytest.raises(ArtifactCorrupt) as caught:
        artifacts.read(link)
    assert "symlink" in str(caught.value)
    assert [a.run_id for a in artifacts.list()] == ["good-0001"]
    assert link.is_symlink(), "the suspect entry is left in place"


def test_a_directory_in_the_root_is_a_problem_not_a_crash(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    artifacts = ArtifactStore(root)
    artifacts.stage("good-0001", {"rows": 1})
    (root / "folder.artifact.json").mkdir()

    assert [a.run_id for a in artifacts.list()] == ["good-0001"]
    assert len(artifacts.problems()) == 1


def test_recover_list_reports_a_bad_file_without_a_traceback(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    ArtifactStore(root).stage("good-0001", {"rows": 1})
    (root / "evil.artifact.json").write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")

    done = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "workrecovery.cli", "list", str(root)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 1
    assert "Traceback" not in done.stderr
    assert "PROBLEM" in done.stderr
    assert "good-0001" in done.stdout


# ------------------------------------------------- F4 no foreign clobber


def test_a_foreign_document_is_never_overwritten(tmp_path: Path) -> None:
    foreign = b'{"someone":"elses work"}'
    store = MemoryStore(items={"shared-0001": foreign})
    jobs = jobs_for(tmp_path, store)

    outcome = jobs.commit("shared-0001", {"mine": True})

    assert outcome.state == "conflict"
    assert outcome.saved is False
    assert outcome.verified is False
    assert outcome.recoverable is True, "the local copy is the caller's only copy"
    assert store.items["shared-0001"] == foreign
    assert isinstance(outcome.error, StoreOccupied)


def test_two_writers_one_run_id_one_wins_and_the_other_keeps_its_output(
    tmp_path: Path,
) -> None:
    store = MemoryStore()
    first = jobs_for(tmp_path / "a", store)
    second = jobs_for(tmp_path / "b", store)

    won = first.commit("shared-0001", {"writer": "first"})
    lost = second.commit("shared-0001", {"writer": "second"})

    assert won.state == "saved" and won.verified is True
    assert lost.state == "conflict"
    assert store.items["shared-0001"] == encode_payload({"writer": "first"})[0]
    assert lost.artifact is not None and lost.artifact.path is not None
    assert lost.artifact.path.exists()
    # And the losing side can still be recovered and inspected later.
    assert second.read("shared-0001").payload == {"writer": "second"}


def test_recommitting_identical_content_is_idempotent(tmp_path: Path) -> None:
    store = MemoryStore()
    jobs = jobs_for(tmp_path, store, keep_artifact=True)
    first = jobs.commit("nightly-0001", {"rows": 3})
    assert first.state == "saved"
    saves_after_first = store.saves

    again = jobs.recommit(jobs.read("nightly-0001"))
    assert again.state == "saved"
    assert again.verified is True
    assert store.saves == saves_after_first, "identical content needs no second write"


def test_the_shipped_memory_store_refuses_a_conflicting_write() -> None:
    store = MemoryStore(items={"run-1": b"original"})
    store.save("run-1", b"original", "application/octet-stream")  # idempotent
    assert store.items["run-1"] == b"original"
    with pytest.raises(StoreOccupied):
        store.save("run-1", b"different", "application/octet-stream")
    assert store.items["run-1"] == b"original"


def test_a_capped_commit_still_keeps_the_full_artifact(tmp_path: Path) -> None:
    store = MemoryStore()
    jobs = jobs_for(tmp_path, store)
    outcome = jobs.commit(
        "capped-0001",
        {"rows": list(range(50))},
        fit=lambda payload: {"rows": payload["rows"][:5]},
    )
    assert outcome.state == "saved"
    assert outcome.capped is True
    assert outcome.recoverable is True
    assert jobs.read("capped-0001").payload == {"rows": list(range(50))}


# ------------------------------------------ F5 a run id is not a path


def test_a_run_id_containing_a_dot_is_read_as_a_run_id(tmp_path: Path) -> None:
    store = MemoryStore(load_blind=True)
    jobs = jobs_for(tmp_path, store)
    jobs.commit("nightly.0001", {"rows": 1})

    recovered = jobs.read("nightly.0001")
    assert recovered.run_id == "nightly.0001"
    assert recovered.payload == {"rows": 1}


def test_a_path_outside_the_root_is_refused(tmp_path: Path) -> None:
    outside_root = tmp_path / "elsewhere"
    ArtifactStore(outside_root).stage("stranger-0001", {"rows": 1})
    outside = outside_root / "stranger-0001.artifact.json"

    jobs = jobs_for(tmp_path, MemoryStore())
    jobs.commit("mine-0001", {"rows": 1})

    with pytest.raises(InvalidRunId):
        jobs.read_path(outside)
    with pytest.raises(InvalidRunId):
        jobs.read(outside)
    assert outside.exists()


def test_a_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    outside_root = tmp_path / "elsewhere"
    ArtifactStore(outside_root).stage("stranger-0001", {"rows": 1})

    jobs = jobs_for(tmp_path, MemoryStore())
    jobs.commit("mine-0001", {"rows": 1})
    escape = jobs.artifacts.root / "escape.artifact.json"
    escape.symlink_to(outside_root / "stranger-0001.artifact.json")

    with pytest.raises(ArtifactCorrupt):
        jobs.read_path(escape)


def test_a_traversal_run_id_is_still_refused(tmp_path: Path) -> None:
    jobs = jobs_for(tmp_path, MemoryStore())
    for bad in ("../escape", "/etc/passwd", "a/b"):
        with pytest.raises(InvalidRunId):
            jobs.read(bad)


# ------------------------------------- F10 the payload cannot drift


def test_a_mutated_payload_object_cannot_poison_the_record(tmp_path: Path) -> None:
    payload = {"rows": [1, 2, 3]}
    artifacts = ArtifactStore(tmp_path / "recovery")
    artifact = artifacts.stage("nightly-0001", payload)

    payload["rows"].append(4)

    assert artifact.payload is not payload
    assert artifact.payload == {"rows": [1, 2, 3]}
    assert digest(encode_payload(artifact.payload)[0]) == artifact.content_sha256
    assert artifacts.read_run("nightly-0001").payload == {"rows": [1, 2, 3]}


def test_a_mutated_payload_object_cannot_poison_a_recommit(tmp_path: Path) -> None:
    store = MemoryStore()
    jobs = jobs_for(tmp_path, store, keep_artifact=True)
    payload = {"rows": [1, 2, 3]}
    outcome = jobs.commit("nightly-0001", payload)
    payload["rows"].append(4)

    assert outcome.artifact is not None
    again = jobs.recommit(outcome.artifact)
    assert again.state == "saved"
    assert store.items["nightly-0001"] == encode_payload({"rows": [1, 2, 3]})[0]


def test_the_memory_store_snapshots_the_bytes_it_is_given() -> None:
    store = MemoryStore()
    buffer = bytearray(b"payload")
    store.save("run-1", buffer, "application/octet-stream")
    buffer.extend(b"-tampered")
    assert store.items["run-1"] == b"payload"
    assert store.load("run-1") == b"payload"


def test_a_fabricated_artifact_cannot_delete_a_file_outside_the_root(
    tmp_path: Path,
) -> None:
    outside_root = tmp_path / "elsewhere"
    victim = ArtifactStore(outside_root).stage("stranger-0001", {"rows": 1})
    artifacts = ArtifactStore(tmp_path / "recovery")

    forged = Artifact(
        run_id=victim.run_id,
        created_at=victim.created_at,
        label=victim.label,
        content_type=victim.content_type,
        content_sha256=victim.content_sha256,
        content_bytes=victim.content_bytes,
        payload=victim.payload,
        path=victim.path,
    )
    with pytest.raises(StaleArtifact):
        artifacts.discard(forged)
    assert victim.path is not None and victim.path.exists()


def test_discarding_a_real_artifact_still_works(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "recovery")
    artifact = artifacts.stage("nightly-0001", {"rows": 1})
    artifacts.discard(artifact)
    assert artifact.path is not None and not artifact.path.exists()
    artifacts.discard(artifact)  # idempotent


def test_stage_still_refuses_a_second_owner(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "recovery")
    artifacts.stage("nightly-0001", {"rows": 1})
    with pytest.raises(Exception) as caught:
        artifacts.stage("nightly-0001", {"rows": 2})
    assert "already exists" in str(caught.value)
    assert json.loads((artifacts.root / "nightly-0001.artifact.json").read_text())[
        "content"
    ] == {"rows": 1}


def test_artifact_files_stay_owner_only(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "recovery")
    artifact = artifacts.stage("nightly-0001", {"rows": 1})
    assert artifact.path is not None
    assert oct(os.stat(artifact.path).st_mode & 0o777) == "0o600"


# ------------------------------------------------- the check/open symlink race


def test_a_symlink_swapped_in_after_the_check_is_still_not_followed(
    tmp_path: Path,
) -> None:
    """The window between `lstat` and `open`, exercised rather than argued.

    The reader used to `lstat` the name, decide it was a regular file, and
    then `open` the same name again. Another writer that replaces the file
    with a symlink in between gets its target read — the exact case the check
    was written for. Deleting the symlink after the fact would not close it
    either: the unlink removes the link, never the file already read.

    Here the swap is performed *at the moment* the old code had its window,
    by a store that does the replacement inside the pre-open stat.
    """
    root = tmp_path / "recovery"
    artifacts = ArtifactStore(root)
    honest = artifacts.stage("nightly-0001", {"rows": 1})
    assert honest.path is not None

    victim_dir = tmp_path / "elsewhere"
    victim_dir.mkdir()
    victim = victim_dir / "victim.artifact.json"
    victim.write_text(json.dumps({"not": "yours"}), encoding="utf-8")

    class SwappingStore(ArtifactStore):
        swapped = False

        def _lstat_or_refuse(self, target: Path) -> os.stat_result:
            stat_result = super()._lstat_or_refuse(target)
            if not SwappingStore.swapped:
                SwappingStore.swapped = True
                target.unlink()
                target.symlink_to(victim)
            return stat_result

    racing = SwappingStore(root)
    # Force the no-O_NOFOLLOW fallback, which is the path a platform without
    # the flag takes: it cannot prevent the swap, so it must detect it.
    import workrecovery.artifacts as artifacts_module

    original_flag = artifacts_module._NOFOLLOW
    artifacts_module._NOFOLLOW = 0
    try:
        with pytest.raises(ArtifactCorrupt) as caught:
            racing.read(honest.path)
    finally:
        artifacts_module._NOFOLLOW = original_flag
    assert SwappingStore.swapped is True
    assert "replaced between the check and the open" in str(caught.value)
    assert victim.read_text(encoding="utf-8") == json.dumps({"not": "yours"})
    assert honest.path.is_symlink(), "the planted link is reported, never unlinked"


def test_o_nofollow_refuses_the_symlink_at_the_syscall(tmp_path: Path) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("no O_NOFOLLOW on this platform; the fallback test covers it")
    root = tmp_path / "recovery"
    artifacts = ArtifactStore(root)
    artifacts.stage("nightly-0001", {"rows": 1})
    victim = tmp_path / "victim.artifact.json"
    victim.write_bytes(b"x" * 16)

    planted = artifacts.root / "planted.artifact.json"
    planted.symlink_to(victim)
    with pytest.raises(ArtifactCorrupt) as caught:
        artifacts.read(planted)
    assert "symlink" in str(caught.value)
    # There is only one lookup of the name, so there is no interval to swap in.
    assert victim.exists() and planted.is_symlink()
    assert [a.run_id for a in artifacts.list()] == ["nightly-0001"]


def test_a_fifo_does_not_park_the_reader(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs on this platform")
    artifacts = ArtifactStore(tmp_path / "recovery")
    artifacts.stage("nightly-0001", {"rows": 1})
    fifo = artifacts.root / "pipe.artifact.json"
    os.mkfifo(fifo)
    with pytest.raises(ArtifactCorrupt) as caught:
        artifacts.read(fifo)
    assert "not a regular file" in str(caught.value)
    assert [a.run_id for a in artifacts.list()] == ["nightly-0001"]


# --------------------------------------------------- envelope field validation


def _plant(root: Path, name: str, **overrides: Any) -> Path:
    content, content_type = encode_payload({"x": 1})
    document: dict[str, Any] = {
        "schema": "recoverable-job/artifact",
        "version": 1,
        "run_id": name,
        "created_at": "2026-01-01T00:00:00Z",
        "label": "",
        "content_type": content_type,
        "content_sha256": digest(content),
        "content_bytes": len(content),
        "metadata": {},
        "content": {"x": 1},
    }
    document.update(overrides)
    path = root / f"{name}.artifact.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"metadata": 5}, "not a JSON object"),
        ({"metadata": ["a"]}, "not a JSON object"),
        ({"metadata": "text"}, "not a JSON object"),
        ({"metadata": {"n": "x" * 40_000}}, "metadata"),
        ({"run_id": 123}, "run_id"),
        ({"run_id": "../../../etc/passwd"}, "run_id"),
        ({"run_id": "another-run"}, "should be called"),
        ({"created_at": 17}, "created_at"),
        ({"created_at": ""}, "created_at"),
        ({"created_at": "x" * 500}, "created_at"),
        ({"label": 5}, "label"),
        ({"label": "x" * 5_000}, "label"),
        ({"version": True}, "version"),
        ({"content_bytes": True}, "content_bytes"),
        ({"content_bytes": "7"}, "content_bytes"),
        ({"content_sha256": 7}, "sha256"),
        ({"content_sha256": "AB" * 32}, "sha256"),
        ({"content_base64": "AA=="}, "both content"),
        ({"surprise": "hello"}, "does not define"),
    ],
)
def test_a_malformed_envelope_field_is_a_named_refusal(
    tmp_path: Path, overrides: dict[str, Any], fragment: str
) -> None:
    """`dict(document.get("metadata") or {})` raised TypeError out of read().

    Not a RecoveryError, so it escaped `read`, `_scan`, `list` and
    `problems` — one planted file hid every pending run from the operator.
    """
    artifacts = ArtifactStore(tmp_path / "recovery")
    artifacts.stage("nightly-0001", {"rows": 1})
    planted = _plant(artifacts.root, "planted", **overrides)
    with pytest.raises(ArtifactCorrupt) as caught:
        artifacts.read(planted)
    assert fragment in str(caught.value)
    assert planted.exists(), "a refused envelope is reported, never deleted"
    assert [a.run_id for a in artifacts.list()] == ["nightly-0001"]
    assert len(artifacts.problems()) == 1


def test_a_recommit_cannot_be_pointed_at_a_foreign_key(tmp_path: Path) -> None:
    """`recommit` writes to `artifact.run_id`, which comes out of the file."""
    store = MemoryStore()
    runner = jobs_for(tmp_path, store, keep_artifact=True)
    runner.commit("nightly-0001", {"rows": 1})
    _plant(runner.artifacts.root, "planted", run_id="../../someone-elses-key")
    with pytest.raises(ArtifactCorrupt):
        runner.artifacts.read(runner.artifacts.root / "planted.artifact.json")
    assert list(store.items) == ["nightly-0001"]


# ------------------------------------------ staging within the read's own bound


def test_stage_refuses_an_envelope_its_own_reader_would_reject(tmp_path: Path) -> None:
    """A staged file that read() refuses is work preserved nowhere."""
    artifacts = ArtifactStore(tmp_path / "recovery", max_artifact_bytes=20_000)
    with pytest.raises(StagingFailed) as caught:
        artifacts.stage("nightly-0001", ["y" * 30_000])
    assert "artifact ceiling" in str(caught.value)
    assert list(artifacts.root.iterdir()) == []


def test_pretty_printing_is_dropped_before_the_work_is(tmp_path: Path) -> None:
    """indent=2 measured 4.9x canonical size, past the ceiling's 2x allowance."""
    artifacts = ArtifactStore(tmp_path / "recovery", max_artifact_bytes=20_000)
    artifact = artifacts.stage("nightly-0001", [[1, 2, 3]] * 2_000)
    assert artifact.path is not None
    assert artifact.path.stat().st_size <= artifacts.max_artifact_bytes
    assert artifacts.read(artifact.path).payload == [[1, 2, 3]] * 2_000
    # Small artifacts stay readable by a human, which is why indent exists.
    readable = artifacts.stage("nightly-0002", {"rows": 1})
    assert readable.path is not None
    assert b"\n  " in readable.path.read_bytes()


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"label": 5}, PayloadNotSupported),
        ({"metadata": [("a", 1)]}, PayloadNotSupported),
        ({"metadata": {1: "a"}}, PayloadNotSupported),
        ({"label": "x" * 5_000}, PayloadTooLarge),
        ({"metadata": {"n": "x" * 40_000}}, PayloadTooLarge),
    ],
)
def test_metadata_and_label_are_bounded_at_the_write(
    tmp_path: Path, kwargs: dict[str, Any], expected: type[Exception]
) -> None:
    artifacts = ArtifactStore(tmp_path / "recovery")
    with pytest.raises(expected):
        artifacts.stage("nightly-0001", {"rows": 1}, **kwargs)
    # Refused before the root is even created: nothing on disk to clean up.
    assert not artifacts.root.exists()


def test_metadata_is_a_snapshot_like_the_payload(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "recovery")
    live = {"source": {"rows": 1}}
    artifact = artifacts.stage("nightly-0001", {"rows": 1}, metadata=live)
    live["source"]["rows"] = 999
    assert artifact.metadata == {"source": {"rows": 1}}
    assert artifacts.read_run("nightly-0001").metadata == {"source": {"rows": 1}}
