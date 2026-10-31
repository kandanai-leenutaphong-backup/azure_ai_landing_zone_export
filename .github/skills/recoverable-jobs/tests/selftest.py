#!/usr/bin/env python3
"""selftest.py — proves this box works here, with no test framework installed.

    python3 tests/selftest.py

Standard library only, no network, no sleeping. Every artifact is written under
a fresh temporary directory that this file removes when it is done.

Exit code 0 means every check passed. Any failure prints the traceback and
exits 1.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workrecovery import (  # noqa: E402
    ENVELOPE_SCHEMA,
    ENVELOPE_VERSION,
    Artifact,
    ArtifactCorrupt,
    ArtifactExists,
    ArtifactMissing,
    ArtifactStore,
    FixedClock,
    InvalidRunId,
    MemoryStore,
    PayloadNotSupported,
    PayloadTooLarge,
    RecoverableJobs,
    RecoveryError,
    StagingFailed,
    StaleArtifact,
    StoreOccupied,
    StoreRefused,
    StoreTimeout,
    StoreUnavailable,
    decode_payload,
    digest,
    encode_payload,
    validate_run_id,
)

CHECKS: list = []
TEMP_ROOTS: list[Path] = []


def check(fn):
    CHECKS.append(fn)
    return fn


def workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="workrecovery-selftest-"))
    TEMP_ROOTS.append(root)
    return root


def jobs(store: Any = None, **options: Any) -> RecoverableJobs:
    return RecoverableJobs(
        store=store if store is not None else MemoryStore(),
        root=workspace(),
        clock=FixedClock(),
        **options,
    )


def refuses(exc_type, fn, *, contains: str = "") -> BaseException:
    try:
        fn()
    except exc_type as raised:
        if contains:
            assert contains in str(raised), f"{contains!r} not in {raised!s}"
        return raised
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")


# ---------------------------------------------------------------- payload


@check
def a_payload_is_bytes_or_json_and_nothing_else() -> None:
    content, kind = encode_payload({"b": 1, "a": [1, 2, None, True, "é"]})
    assert kind == "application/json"
    # Canonical: sorted keys, no whitespace, no ASCII escaping. Two equal
    # values must produce one digest, or a correct read-back reads as a
    # mismatch.
    assert content == '{"a":[1,2,null,true,"é"],"b":1}'.encode("utf-8")
    assert encode_payload({"a": [1, 2, None, True, "é"], "b": 1})[0] == content

    raw, kind = encode_payload(b"\x00\x01binary")
    assert (raw, kind) == (b"\x00\x01binary", "application/octet-stream")
    assert encode_payload(bytearray(b"abc"))[0] == b"abc"

    refuses(PayloadNotSupported, lambda: encode_payload({1: "x"}), contains="keys must be")
    refuses(PayloadNotSupported, lambda: encode_payload((1, 2)), contains="tuple")
    refuses(PayloadNotSupported, lambda: encode_payload({"a": {1, 2}}), contains="set")
    refuses(PayloadNotSupported, lambda: encode_payload({"a": float("nan")}), contains="NaN")
    refuses(PayloadNotSupported, lambda: encode_payload(object()), contains="not a JSON value")

    deep: Any = "leaf"
    for _ in range(70):
        deep = [deep]
    refuses(PayloadNotSupported, lambda: encode_payload(deep), contains="nested more than")


@check
def payloads_round_trip_exactly() -> None:
    for value in ({"rows": [1, 2, 3]}, [], {}, "", 0, False, None, b"", b"\xff\xfe"):
        content, kind = encode_payload(value)
        assert decode_payload(content, kind) == value, value
    refuses(PayloadNotSupported, lambda: decode_payload(b"{", "application/json"))
    refuses(PayloadNotSupported, lambda: decode_payload(b"x", "text/plain"), contains="unknown")


@check
def the_digest_identifies_the_output_not_its_source() -> None:
    first, _ = encode_payload({"rows": [1, 2, 3]})
    second, _ = encode_payload({"rows": [1, 2, 4]})
    # Same source, same item count, different output: different digest. An
    # item count would call these equal, which is the bug it exists to avoid.
    assert digest(first) != digest(second)
    assert digest(first) == digest(encode_payload({"rows": [1, 2, 3]})[0])
    assert len(digest(b"")) == 64


# --------------------------------------------------------------- run ids


@check
def run_ids_that_are_not_safe_file_names_are_refused() -> None:
    assert validate_run_id("run-1.0_A") == "run-1.0_A"
    for bad in (
        "../escape",
        "nested/run",
        "nested\\run",
        ".hidden",
        "",
        "with space",
        "..",
        ".",
        "x" * 129,
        "run\x00id",
        "/absolute",
    ):
        refuses(InvalidRunId, lambda b=bad: validate_run_id(b))
    refuses(InvalidRunId, lambda: validate_run_id(7))  # type: ignore[arg-type]

    store = ArtifactStore(workspace())
    refuses(InvalidRunId, lambda: store.path_for("../outside"))
    assert store.path_for("run-1").parent == store.root


# ------------------------------------------------------------- artifacts


@check
def an_artifact_is_written_atomically_and_never_clobbers() -> None:
    root = workspace()
    store = ArtifactStore(root, clock=FixedClock())
    artifact = store.stage("run-1", {"rows": [1]}, label="first")

    assert artifact.path == root / "run-1.artifact.json"
    assert artifact.path.exists()
    # No temporary files left behind, and the directory is owner-only.
    assert [p.name for p in root.iterdir()] == ["run-1.artifact.json"]
    assert stat.S_IMODE(root.stat().st_mode) == 0o700

    document = json.loads(artifact.path.read_text(encoding="utf-8"))
    assert document["schema"] == ENVELOPE_SCHEMA
    assert document["version"] == ENVELOPE_VERSION
    assert document["run_id"] == "run-1"
    assert document["content"] == {"rows": [1]}
    assert document["content_sha256"] == artifact.content_sha256

    before = artifact.path.read_bytes()
    clash = refuses(
        ArtifactExists,
        lambda: store.stage("run-1", {"rows": ["different"]}),
        contains="already exists",
    )
    assert isinstance(clash, RecoveryError)
    assert artifact.path.read_bytes() == before, "the first owner's copy must survive"


@check
def bytes_payloads_survive_the_envelope() -> None:
    store = ArtifactStore(workspace(), clock=FixedClock())
    blob = bytes(range(256))
    staged = store.stage("blob-run", blob)
    assert staged.content_type == "application/octet-stream"
    read_back = store.read_run("blob-run")
    assert read_back.payload == blob
    assert read_back.content_sha256 == digest(blob)
    assert "content_base64" in json.loads((staged.path or Path()).read_text())


@check
def a_truncated_or_edited_artifact_is_refused_and_kept() -> None:
    root = workspace()
    store = ArtifactStore(root, clock=FixedClock())
    artifact = store.stage("run-1", {"rows": [1, 2, 3]})
    path = artifact.path or Path()
    text = path.read_text(encoding="utf-8")

    truncated = root / "truncated.artifact.json"
    truncated.write_text(text[: len(text) // 2], encoding="utf-8")
    refuses(ArtifactCorrupt, lambda: store.read(truncated), contains="truncated")
    assert truncated.exists(), "a corrupt artifact is never deleted by this package"

    edited = root / "edited.artifact.json"
    edited.write_text(text.replace("[1,2,3]", "[1,2,4]").replace("1,\n      2", "1,\n      9"))
    # Either the JSON body or the digest changes; both must be caught.
    refuses(ArtifactCorrupt, lambda: store.read(edited))

    for name, body in (
        ("wrong-schema", {"schema": "something/else", "version": 1}),
        ("wrong-version", {"schema": ENVELOPE_SCHEMA, "version": 99}),
        ("missing-fields", {"schema": ENVELOPE_SCHEMA, "version": ENVELOPE_VERSION}),
        ("not-an-object", ["nope"]),
    ):
        target = root / f"{name}.artifact.json"
        target.write_text(json.dumps(body), encoding="utf-8")
        refuses(ArtifactCorrupt, lambda t=target: store.read(t))

    refuses(ArtifactMissing, lambda: store.read(root / "absent.artifact.json"))

    # A listing survives the bad files, reports them, and deletes nothing.
    assert [a.run_id for a in store.list()] == ["run-1"]
    assert len(store.problems()) == 6
    assert len(list(root.glob("*.artifact.json"))) == 7


@check
def discarding_requires_proof_that_the_file_is_still_the_same_one() -> None:
    root = workspace()
    store = ArtifactStore(root, clock=FixedClock())
    artifact = store.stage("run-1", {"rows": [1]})
    path = artifact.path or Path()

    # Replaced by another run's output: refused, and left in place.
    path.unlink()
    other = store.stage("run-1", {"rows": ["somebody else"]})
    refuses(StaleArtifact, lambda: store.discard(artifact), contains="left in place")
    assert path.exists()
    assert store.read(path).payload == {"rows": ["somebody else"]}

    # Corrupt: also refused, also left in place.
    path.write_text("{ truncated", encoding="utf-8")
    refuses(StaleArtifact, lambda: store.discard(other), contains="not deleted")
    assert path.exists()

    # The genuine article is removed, and removing it twice is not an error.
    path.unlink()
    real = store.stage("run-2", {"rows": [2]})
    store.discard(real)
    assert not (real.path or Path()).exists()
    store.discard(real)


@check
def an_unwritable_recovery_root_fails_before_anything_else() -> None:
    if os.geteuid() == 0:
        # Root ignores the mode bits, so this check cannot mean anything here.
        return
    root = workspace()
    locked = root / "locked"
    locked.mkdir(mode=0o500)
    try:
        store = ArtifactStore(locked / "inner", clock=FixedClock())
        refuses(StagingFailed, lambda: store.stage("run-1", {"a": 1}), contains="not usable")
    finally:
        locked.chmod(0o700)

    # A symlinked root is refused rather than followed: it can point anywhere.
    target = root / "elsewhere"
    target.mkdir()
    link = root / "link"
    link.symlink_to(target, target_is_directory=True)
    linked = ArtifactStore(link, clock=FixedClock())
    refuses(StagingFailed, lambda: linked.stage("run-1", {"a": 1}), contains="symlink")

    # A file where the root should be is a refusal, not a crash.
    occupied = root / "afile"
    occupied.write_text("x", encoding="utf-8")
    refuses(StagingFailed, lambda: ArtifactStore(occupied).stage("run-1", {"a": 1}))


# ----------------------------------------------------------- commit flow


@check
def a_verified_save_removes_the_local_copy_and_nothing_else_does() -> None:
    store = MemoryStore()
    runner = jobs(store)
    outcome = runner.commit("run-1", {"rows": [1, 2]}, label="export")

    assert outcome.state == "saved" and outcome.verified is True
    assert outcome.artifact is None and outcome.recoverable is False
    assert runner.pending() == []
    # Two reads: the pre-write check that the id is free, and the read-back.
    assert store.saves == 1 and store.loads == 2
    assert outcome.summary()["state"] == "saved"
    assert "rows" not in str(outcome.summary())

    # keep_artifact overrides the cleanup, for an operator who wants the trail.
    kept = RecoverableJobs(
        store=MemoryStore(), root=workspace(), clock=FixedClock(), keep_artifact=True
    )
    result = kept.commit("run-1", {"rows": [1]})
    assert result.state == "saved"
    assert result.recoverable is True
    assert len(kept.pending()) == 1


@check
def the_artifact_exists_before_the_store_is_ever_called() -> None:
    """The ordering claim, asserted from inside the store's own save()."""
    seen: list[bool] = []
    root = workspace()

    class Watching(MemoryStore):
        def save(self, run_id: str, content: bytes, content_type: str) -> None:
            seen.append((root / f"{run_id}.artifact.json").exists())
            super().save(run_id, content, content_type)

    runner = RecoverableJobs(store=Watching(), root=root, clock=FixedClock())
    runner.commit("run-1", {"rows": [1]})
    assert seen == [True], "the local copy must exist before the risky call starts"


@check
def a_payload_over_the_ceiling_is_refused_before_anything_is_written() -> None:
    root = workspace()
    runner = RecoverableJobs(
        store=MemoryStore(), root=root, clock=FixedClock(), max_payload_bytes=64
    )
    refuses(
        PayloadTooLarge,
        lambda: runner.commit("run-1", {"rows": list(range(1000))}),
        contains="nothing was written",
    )
    assert not root.exists() or list(root.glob("*.artifact.json")) == []
    assert runner.commit("run-1", {"a": 1}).state == "saved"

    for bad in (
        {"max_attempts": 0},
        {"max_payload_bytes": 0},
        {"backoff_seconds": -1},
        {"staging_policy": "whatever"},
    ):
        refuses(
            ValueError,
            lambda b=bad: RecoverableJobs(store=MemoryStore(), root=workspace(), **b),
        )
    refuses(ValueError, lambda: RecoverableJobs(store=MemoryStore()), contains="nowhere")


@check
def staging_failure_refuses_the_expensive_write_by_default() -> None:
    if os.geteuid() == 0:
        return
    root = workspace()
    locked = root / "locked"
    locked.mkdir(mode=0o500)
    try:
        store = MemoryStore()
        runner = RecoverableJobs(store=store, root=locked / "inner", clock=FixedClock())
        refuses(StagingFailed, lambda: runner.commit("run-1", {"rows": [1]}))
        assert store.saves == 0, "no safety net means the store is not attempted"

        # The documented weaker policy: proceed, unprotected, and say so.
        risky = RecoverableJobs(
            store=store,
            root=locked / "inner",
            clock=FixedClock(),
            staging_policy="proceed",
        )
        outcome = risky.commit("run-1", {"rows": [1]})
        assert outcome.state == "saved"
        assert outcome.artifact is None and outcome.recoverable is False
        assert any("not recoverable" in w for w in outcome.warnings)
        assert store.saves == 1
    finally:
        locked.chmod(0o700)


@check
def the_three_store_outcomes_stay_distinguishable() -> None:
    payload = {"rows": [1]}

    landed = MemoryStore(timeout=StoreTimeout(operation="write"), lands=True)
    outcome = jobs(landed).commit("run-1", payload)
    assert outcome.state == "saved" and outcome.verified is True

    lost = MemoryStore(timeout=StoreTimeout(operation="write"))
    runner = jobs(lost)
    outcome = runner.commit("run-1", payload)
    assert outcome.state == "absent" and outcome.recoverable is True
    assert isinstance(outcome.error, StoreTimeout)

    refused = MemoryStore(refuse="schema violation")
    outcome = jobs(refused).commit("run-1", payload)
    # One load, the pre-write check; a refusal is never read back.
    assert outcome.state == "absent" and refused.loads == 1
    assert isinstance(outcome.error, StoreRefused)

    blind = MemoryStore(load_blind=True)
    outcome = jobs(blind).commit("run-1", payload)
    assert outcome.state == "unknown" and outcome.verified is False

    mute = MemoryStore(load_error=RuntimeError("no answer"))
    outcome = jobs(mute).commit("run-1", payload)
    assert outcome.state == "unknown" and "run-1" in outcome.detail

    # Content under our id that is not ours is never reported as saved, and is
    # never written over: the collision is its own outcome.
    foreign, _ = encode_payload({"rows": ["not ours"]})
    occupied = MemoryStore(items={"run-1": foreign}, timeout=StoreTimeout())
    outcome = jobs(occupied).commit("run-1", payload)
    assert outcome.state == "conflict" and "different content" in outcome.detail
    assert outcome.recoverable is True, "the losing writer keeps its own output"
    assert occupied.items["run-1"] == foreign, "the foreign document was not overwritten"
    assert occupied.saves == 0, "a known collision is not attempted"

    # Same item count, different content: still not a match.
    same_shape, _ = encode_payload({"rows": [2]})
    lookalike = MemoryStore(items={"run-1": same_shape}, timeout=StoreTimeout())
    outcome = jobs(lookalike).commit("run-1", payload)
    assert outcome.state == "conflict"

    # A store that answers late still refuses to clobber, and the engine
    # reports the collision the adapter raised rather than a false success.
    racing = MemoryStore(load_blind=True)
    racing.items["run-1"] = foreign
    outcome = jobs(racing).commit("run-1", payload)
    assert outcome.state == "conflict"
    assert isinstance(outcome.error, StoreOccupied)
    assert racing.items["run-1"] == foreign


@check
def retries_are_bounded_and_never_applied_to_a_timeout() -> None:
    clock = FixedClock()
    store = MemoryStore(unavailable_times=99)
    runner = RecoverableJobs(
        store=store, root=workspace(), clock=clock, max_attempts=4, backoff_seconds=0.25
    )
    outcome = runner.commit("run-1", {"a": 1})
    assert outcome.state == "absent" and outcome.attempts == 4
    assert isinstance(outcome.error, StoreUnavailable)
    assert clock.slept == [0.25, 0.5, 1.0], "bounded exponential backoff, no sleeping in tests"
    assert store.loads == 1, "one pre-write check, and no read-back for an unsent write"

    # A timed-out write is never retried: it may have landed.
    timed_out = MemoryStore(timeout=StoreTimeout())
    runner = RecoverableJobs(
        store=timed_out, root=workspace(), clock=FixedClock(), max_attempts=5
    )
    outcome = runner.commit("run-1", {"a": 1})
    assert timed_out.saves == 1 and outcome.attempts == 1

    # max_attempts=1 disables retrying entirely.
    once = MemoryStore(unavailable_times=1)
    runner = RecoverableJobs(
        store=once, root=workspace(), clock=FixedClock(), max_attempts=1
    )
    assert runner.commit("run-1", {"a": 1}).attempts == 1


@check
def a_cap_is_applied_after_staging_and_keeps_the_full_output() -> None:
    full = {"rows": list(range(100))}
    store = MemoryStore()
    runner = jobs(store)
    outcome = runner.commit("run-1", full, fit=lambda p: {"rows": p["rows"][:10]})

    assert outcome.state == "saved" and outcome.capped is True
    assert outcome.staged_sha256 != outcome.content_sha256
    assert decode_payload(store.items["run-1"], "application/json") == {"rows": list(range(10))}
    # The artifact is kept *because* it is capped: it holds the only full copy.
    assert outcome.recoverable is True
    assert runner.read("run-1").payload == full
    assert any("only place the full output exists" in w for w in outcome.warnings)

    # fit() returning None means unchanged, and cleanup proceeds.
    plain = jobs()
    unchanged = plain.commit("run-1", full, fit=lambda p: None)
    assert unchanged.capped is False and unchanged.artifact is None

    # A fit() that grows the payload, or changes its type, is a programming
    # error and is refused rather than stored.
    refuses(ValueError, lambda: jobs().commit("run-1", full, fit=lambda p: {"rows": [0] * 500}))
    refuses(ValueError, lambda: jobs().commit("run-2", full, fit=lambda p: b"bytes"))


@check
def an_interrupted_save_leaves_the_output_on_disk() -> None:
    root = workspace()

    class Killed(MemoryStore):
        def save(self, run_id: str, content: bytes, content_type: str) -> None:
            raise KeyboardInterrupt("operator pressed ctrl-c during the slow write")

    runner = RecoverableJobs(store=Killed(), root=root, clock=FixedClock())
    refuses(KeyboardInterrupt, lambda: runner.commit("run-1", {"rows": [1, 2, 3]}))

    # The interruption is not swallowed, and the work is still there.
    assert (root / "run-1.artifact.json").exists()
    assert runner.read("run-1").payload == {"rows": [1, 2, 3]}


# -------------------------------------------------------------- recovery


@check
def a_fresh_process_reads_and_recommits_preserved_output() -> None:
    root = workspace()
    payload = {"rows": [{"id": 1}], "note": "expensive"}

    first = RecoverableJobs(
        store=MemoryStore(timeout=StoreTimeout()), root=root, clock=FixedClock()
    )
    assert first.commit("run-a", payload, label="batch").state == "absent"
    assert first.commit("run-b", {"rows": ["other"]}).state == "absent"

    # Nothing is carried across: new objects, same directory.
    store = MemoryStore()
    later = RecoverableJobs(store=store, root=root, clock=FixedClock())
    assert sorted(a.run_id for a in later.pending()) == ["run-a", "run-b"]

    artifact = later.read("run-a")
    assert artifact.payload == payload and artifact.label == "batch"
    # A path is read through read_path (or by passing a Path), and only from
    # inside the root: read() is by run id, whatever the id looks like.
    assert artifact.path is not None
    assert later.read_path(str(artifact.path)).payload == payload
    assert later.read(artifact.path).payload == payload
    refuses(InvalidRunId, lambda: later.read_path("/etc/hostname"))
    assert artifact.summary()["run_id"] == "run-a"
    assert "rows" not in str(artifact.summary()) and "rows" not in repr(artifact)

    outcome = later.recommit(artifact)
    assert outcome.state == "saved" and outcome.verified is True
    assert decode_payload(store.items["run-a"], "application/json") == payload
    assert not (root / "run-a.artifact.json").exists()
    # The unrelated run was untouched throughout.
    assert [a.run_id for a in later.pending()] == ["run-b"]


@check
def recommitting_something_that_no_longer_matches_is_refused() -> None:
    runner = jobs()
    tampered = Artifact(
        run_id="run-1",
        created_at="2001-01-01T00:00:00Z",
        label="",
        content_type="application/json",
        content_sha256="0" * 64,
        content_bytes=2,
        payload={"rows": ["changed after staging"]},
        path=None,
    )
    refuses(ArtifactCorrupt, lambda: runner.recommit(tampered), contains="has not been committed")

    # A recommit that times out is reconciled the same way a commit is.
    root = workspace()
    seed = RecoverableJobs(
        store=MemoryStore(timeout=StoreTimeout()), root=root, clock=FixedClock()
    )
    seed.commit("run-2", {"rows": [1]})
    artifact = seed.read("run-2")

    lands = MemoryStore(timeout=StoreTimeout(operation="read-back"), lands=True)
    outcome = RecoverableJobs(store=lands, root=root, clock=FixedClock()).recommit(artifact)
    assert outcome.state == "saved" and outcome.verified is True
    assert not (root / "run-2.artifact.json").exists()


# ------------------------------------------------------------ regressions


@check
def one_unreadable_file_never_hides_the_readable_ones() -> None:
    runner = jobs(keep_artifact=True)
    runner.commit("good-0001", {"rows": [1]})
    root = runner.artifacts.root

    # Deep enough that json.loads raises RecursionError, which is not a
    # RecoveryError and used to escape list() and problems() entirely.
    (root / "deep.artifact.json").write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    (root / "truncated.artifact.json").write_text('{"schema": "recov', encoding="utf-8")
    (root / "folder.artifact.json").mkdir()
    (root / "linked.artifact.json").symlink_to(root / "good-0001.artifact.json")

    assert [a.run_id for a in runner.pending()] == ["good-0001"]
    problems = {path.name for path, _ in runner.problems()}
    assert problems == {
        "deep.artifact.json",
        "truncated.artifact.json",
        "folder.artifact.json",
        "linked.artifact.json",
    }
    for name in problems:
        assert (root / name).exists(), "a suspect file is reported, never removed"

    # And the size ceiling refuses before a byte is read.
    small = ArtifactStore(workspace(), max_artifact_bytes=2048)
    small.stage("good-0001", {"rows": [1]})
    fat = small.root / "fat.artifact.json"
    fat.write_bytes(b"{" + b"x" * 4096 + b"}")
    assert [a.run_id for a in small.list()] == ["good-0001"]
    refuses(ArtifactCorrupt, lambda: small.read(fat), contains="larger than")


@check
def every_envelope_field_is_checked_before_it_is_used() -> None:
    # An envelope is a file other processes can write. Its run_id becomes the
    # store key a recommit writes to and the identity a discard matches on, so
    # "it parsed as JSON" is not the same as "it is an artifact".
    store = ArtifactStore(workspace())
    store.stage("good-0001", {"rows": [1]})
    content, content_type = encode_payload({"x": 1})
    template = {
        "schema": ENVELOPE_SCHEMA,
        "version": ENVELOPE_VERSION,
        "created_at": "2026-01-01T00:00:00Z",
        "label": "",
        "content_type": content_type,
        "content_sha256": digest(content),
        "content_bytes": len(content),
        "metadata": {},
        "content": {"x": 1},
    }

    def plant(name: str, **overrides: Any) -> Path:
        document = dict(template, run_id=name)
        document.update(overrides)
        path = store.root / f"{name}.artifact.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    refusals = {
        # dict(5) raised TypeError and dict(["a"]) raised ValueError — neither
        # is a RecoveryError, so one planted file took list() down with it.
        "metadata-int": (dict(metadata=5), "not a JSON object"),
        "metadata-list": (dict(metadata=["a"]), "not a JSON object"),
        "metadata-huge": (dict(metadata={"n": "x" * 40_000}), "metadata"),
        "run-id-int": (dict(run_id=123), "run_id"),
        "run-id-traversal": (dict(run_id="../../../etc/passwd"), "run_id"),
        "run-id-mismatch": (dict(run_id="somebody-else"), "should be called"),
        "created-at-int": (dict(created_at=17), "created_at"),
        "label-int": (dict(label=5), "label"),
        # True == 1, so a bare equality test accepted "version": true.
        "version-true": (dict(version=True), "version"),
        "bytes-true": (dict(content_bytes=True), "content_bytes"),
        "digest-shouted": (dict(content_sha256=digest(content).upper()), "sha256"),
        "two-bodies": (dict(content_base64="AA=="), "both content"),
        "undefined-field": (dict(surprise="hello"), "does not define"),
    }
    for name, (overrides, fragment) in refusals.items():
        path = plant(name, **overrides)
        refuses(ArtifactCorrupt, lambda p=path: store.read(p), contains=fragment)
        assert path.exists(), "a refused envelope is reported, never deleted"

    assert [a.run_id for a in store.list()] == ["good-0001"], "one bad file hides nothing"
    assert len(store.problems()) == len(refusals)


@check
def nothing_is_staged_that_this_reader_would_refuse() -> None:
    # A file on disk that read() rejects is the worst outcome available: the
    # work is preserved nowhere and looks preserved.
    store = ArtifactStore(workspace(), max_artifact_bytes=20_000)

    refuses(PayloadNotSupported, lambda: store.stage("r-1", {"k": 1}, label=5))
    refuses(PayloadNotSupported, lambda: store.stage("r-2", {"k": 1}, metadata=[("a", 1)]))
    refuses(
        PayloadTooLarge,
        lambda: store.stage("r-3", {"k": 1}, label="x" * 5_000),
        contains="label",
    )
    refuses(
        PayloadTooLarge,
        lambda: store.stage("r-4", {"k": 1}, metadata={"n": "x" * 40_000}),
        contains="metadata",
    )
    refuses(
        StagingFailed,
        lambda: store.stage("r-5", ["y" * 30_000]),
        contains="artifact ceiling",
    )
    assert list(store.root.iterdir()) == [], "a refusal leaves nothing behind, not even a temp file"

    # indent=2 measured 4.9x the canonical size for many small values, which
    # is past the ceiling's 2x allowance. Readability is dropped before the
    # work is.
    artifact = store.stage("r-6", [[1, 2, 3]] * 2_000)
    assert artifact.path is not None
    assert artifact.path.stat().st_size <= store.max_artifact_bytes
    assert store.read(artifact.path).content_sha256 == artifact.content_sha256

    # And metadata is a snapshot, like the payload: mutating it afterwards
    # cannot change what was recorded.
    live = {"source": {"rows": 1}}
    recorded = store.stage("r-7", {"k": 1}, metadata=live)
    live["source"]["rows"] = 999
    assert recorded.metadata == {"source": {"rows": 1}}
    assert store.read_run("r-7").metadata == {"source": {"rows": 1}}


@check
def a_symlink_is_refused_by_the_open_itself() -> None:
    # lstat-then-open is two lookups of one name. The promise "symlinks are
    # never followed" can only be kept by the syscall that opens the file.
    store = ArtifactStore(workspace())
    victim_store = ArtifactStore(workspace())
    victim = victim_store.stage("victim-0001", {"secret": "elsewhere"})
    assert victim.path is not None

    planted = store.root / "planted.artifact.json"
    planted.symlink_to(victim.path)
    refuses(ArtifactCorrupt, lambda: store.read(planted), contains="symlink")
    assert victim.path.exists(), "the victim is never touched, and never unlinked"

    if hasattr(os, "mkfifo"):
        # Opening a FIFO for reading blocks until somebody writes. O_NONBLOCK
        # means this returns instead of parking the whole listing forever.
        fifo = store.root / "fifo.artifact.json"
        os.mkfifo(fifo)
        refuses(ArtifactCorrupt, lambda: store.read(fifo), contains="not a regular file")

    assert store.list() == []


@check
def a_foreign_document_in_the_store_is_never_overwritten() -> None:
    foreign = b'{"someone":"elses work"}'
    store = MemoryStore(items={"run-1": foreign})
    outcome = jobs(store).commit("run-1", {"mine": True})
    assert outcome.state == "conflict"
    assert outcome.saved is False and outcome.verified is False
    assert outcome.recoverable is True, "the losing writer keeps its own output"
    assert store.items["run-1"] == foreign

    # The shipped double implements the contract rather than approximating it.
    refuses(StoreOccupied, lambda: store.save("run-1", b"different", "application/json"))
    store.save("run-1", foreign, "application/json")  # identical is idempotent
    assert store.items["run-1"] == foreign

    # Two writers, one id: one wins, the other keeps its output and is told.
    shared = MemoryStore()
    first = jobs(shared)
    second = jobs(shared)
    won = first.commit("run-2", {"writer": "first"})
    lost = second.commit("run-2", {"writer": "second"})
    assert won.state == "saved" and lost.state == "conflict"
    assert shared.items["run-2"] == encode_payload({"writer": "first"})[0]
    assert second.read("run-2").payload == {"writer": "second"}


@check
def a_run_id_is_a_run_id_and_a_path_is_a_path() -> None:
    runner = jobs(MemoryStore(load_blind=True))
    runner.commit("nightly.0001", {"rows": [1]})
    # A dot is legal in a run id and must not turn it into a file lookup.
    assert runner.read("nightly.0001").payload == {"rows": [1]}

    stranger = ArtifactStore(workspace())
    victim = stranger.stage("stranger-0001", {"rows": [1]})
    assert victim.path is not None
    refuses(InvalidRunId, lambda: runner.read_path(victim.path), contains="not inside")

    escape = runner.artifacts.root / "escape.artifact.json"
    escape.symlink_to(victim.path)
    refuses(ArtifactCorrupt, lambda: runner.read_path(escape), contains="symlink")
    assert victim.path.exists()


@check
def a_record_can_never_disagree_with_its_own_digest() -> None:
    payload = {"rows": [1, 2, 3]}
    store = ArtifactStore(workspace())
    artifact = store.stage("run-1", payload)
    payload["rows"].append(4)

    assert artifact.payload is not payload
    assert artifact.payload == {"rows": [1, 2, 3]}
    assert digest(encode_payload(artifact.payload)[0]) == artifact.content_sha256
    assert store.read_run("run-1").payload == {"rows": [1, 2, 3]}

    # A hand-built Artifact pointing outside the root cannot delete anything.
    stranger = ArtifactStore(workspace())
    victim = stranger.stage("run-1", {"rows": [9]})
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
    refuses(StaleArtifact, lambda: store.discard(forged), contains="not inside")
    assert victim.path is not None and victim.path.exists()


def main() -> int:
    failures = 0
    try:
        for fn in CHECKS:
            try:
                fn()
            except BaseException:
                failures += 1
                print(f"FAIL  {fn.__name__}")
                traceback.print_exc()
            else:
                print(f"ok    {fn.__name__}")
    finally:
        for root in TEMP_ROOTS:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
