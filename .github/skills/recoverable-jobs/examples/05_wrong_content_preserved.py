"""Worked example 5 — wrong content, corrupt files, and foreign artifacts.

Run it: ``python3 examples/05_wrong_content_preserved.py``.

Three ways a naive implementation destroys the thing it was protecting:

1. Treating "something exists under that id" as "our run landed". It is
   somebody else's document, and reporting success loses this run's output.
2. Accepting a truncated artifact, or deleting it because it "looks broken".
3. Tidying up a directory by removing files it did not recognise.

All three are refusals here, and in every one of them the bytes stay on disk.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


from workrecovery import (  # noqa: E402
    ArtifactCorrupt,
    FixedClock,
    MemoryStore,
    RecoverableJobs,
    StaleArtifact,
    StoreTimeout,
    encode_payload,
)

root = Path(tempfile.mkdtemp(prefix="recovery-example-"))
try:
    payload = {"rows": [1, 2, 3], "note": "ours"}
    foreign, _ = encode_payload({"rows": ["not ours at all"]})

    # ------------------------ 1. another document is already under that id
    occupied = MemoryStore(
        items={"run-collision": foreign},
        timeout=StoreTimeout(operation="write"),
        lands=False,
    )
    jobs = RecoverableJobs(store=occupied, root=root, clock=FixedClock())
    outcome = jobs.commit("run-collision", payload)

    assert outcome.state == "conflict", "a foreign document is not this run landing"
    assert outcome.saved is False
    assert outcome.verified is False
    assert "different content" in outcome.detail
    assert outcome.recoverable is True
    # The foreign document was not overwritten, and ours was not lost.
    assert occupied.items["run-collision"] == foreign
    assert jobs.read("run-collision").payload == payload

    # ------------------------------------------ 2. a truncated artifact
    truncated = root / "run-truncated.artifact.json"
    good = jobs.read("run-collision")
    text = (good.path or Path()).read_text(encoding="utf-8")
    truncated.write_text(text[: len(text) // 2], encoding="utf-8")

    try:
        jobs.read_path(truncated)
    except ArtifactCorrupt as broken:
        assert "truncated" in str(broken)
    else:  # pragma: no cover
        raise AssertionError("a truncated artifact must not read back as valid")

    # It is reported, not raised past a listing, and above all not deleted.
    assert [a.run_id for a in jobs.pending()] == ["run-collision"]
    assert [p.name for p, _ in jobs.problems()] == ["run-truncated.artifact.json"]
    assert truncated.exists()

    # An artifact whose *content* was edited fails the digest check too, even
    # though the file is still valid JSON. The id inside is renamed to match
    # the new file name, because a file whose name and run id disagree is
    # refused for that reason first — a recommit stores under the id in the
    # file, so the two are never allowed to drift.
    tampered = root / "run-tampered.artifact.json"
    tampered.write_text(
        text.replace('"ours"', '"edited"').replace(
            '"run_id": "run-collision"', '"run_id": "run-tampered"'
        ),
        encoding="utf-8",
    )
    try:
        jobs.read(tampered)
    except ArtifactCorrupt as broken:
        assert "does not match its recorded digest" in str(broken)
        assert "has not been deleted" in str(broken)
    else:  # pragma: no cover
        raise AssertionError("an edited artifact must fail its digest check")
    assert tampered.exists()

    # ------------------------------------- 3. discarding somebody else's file
    ours = jobs.read("run-collision")

    # While we were away, that path came to hold a different run's output: the
    # first file was cleaned up, and a later run claimed the same id and also
    # failed to store, leaving its own artifact behind.
    (root / "run-collision.artifact.json").unlink()
    later = RecoverableJobs(
        store=MemoryStore(refuse="still refusing"), root=root, clock=FixedClock()
    )
    replaced = later.commit("run-collision", {"rows": ["a later, different run"]})
    assert replaced.state == "absent" and replaced.recoverable is True

    # Our stale record still points at that path. Deleting it would destroy the
    # later run's only copy, so the discard refuses and the file survives.
    try:
        jobs.discard(ours)
    except StaleArtifact as stale:
        assert "left in place" in str(stale)
    else:  # pragma: no cover
        raise AssertionError("discarding a file that is no longer ours must refuse")

    assert (root / "run-collision.artifact.json").exists()
    assert later.read("run-collision").payload == {"rows": ["a later, different run"]}

    # Discarding something that is simply gone is not an error: recovery has to
    # be safe to run twice.
    (root / "run-collision.artifact.json").unlink()
    jobs.discard(ours)

    print("05_wrong_content_preserved: ok")
finally:
    shutil.rmtree(root, ignore_errors=True)
