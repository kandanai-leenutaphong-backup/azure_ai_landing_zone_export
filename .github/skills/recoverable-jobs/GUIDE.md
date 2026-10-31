---
name: recoverable-jobs
description: >
  Use when a job's completed output must not be lost between finishing the work
  and getting it stored. Use for expensive batch runs, model pipelines, report
  builds and exports where the save is slow or unreliable; for a store write
  that timed out and may or may not have landed; for telling "nothing was
  saved" apart from "unknown status"; for verifying a write by reading it back
  before deleting the local copy; for recovering finished output after a crash
  or restart and committing it again; for size caps that must not silently drop
  the tail; and for artifacts that must never be clobbered, never be deleted
  without proof, and never contain payload in a log line. Do not use for
  scheduling, retrying jobs, resuming an unfinished computation, or as a cache
  or queue.
---

# recoverable-jobs

Preserve completed work before the risky save, verify the store really has it,
and hand it back after a restart. Import name `workrecovery`. Standard library
only.

## Decide

Use this box when **all** of these are true:

- the work is expensive enough that redoing it is a real cost;
- the output is *complete* before it is stored;
- the store call can be slow, refuse, be unreachable, or time out ambiguously.

Do not use it for: scheduling or retrying jobs; resuming a partially finished
computation; caching; queueing; or as a second store. It runs nothing and
resumes nothing — it preserves output that already exists.

If your process holds an entire finished result in memory and the next line is
a network write, that is the shape this is for.

## MCP Integration

The [installed adapter](README.md#mcp-adapter) and SDK test belong to this library.
Staging, metadata inspection and payload reads require separate operator grants,
all off by default. Tools take run IDs, not filesystem authority. Staging reports
`preserved` and `saved: false`; it is not a destination-store commit. The adapter
reads only digest-verified JSON payloads and cannot delete artifacts.

The [framework host](../harness-guide/framework/README.md#composition-contract) supports explicit
bindings and exact grants; generated discovery does not activate it.
For real work, configure an absolute durable operator-owned `recovery_root`.
Never remove pending output before verified commit or explicit export.

## Standalone Python Install

Copy the folder, then install it into the environment that will import it:

```bash
python3 -m pip install ./.github/skills/recoverable-jobs
```

A plain, non-editable install. It puts the `workrecovery` package in
`site-packages`, so `import workrecovery` then works from any working
directory with no `PYTHONPATH` and no `sys.path` edit. Copying the folder
alone is **not** enough: the importable package sits one level down inside it.

No runtime dependencies, so the install needs the network only to fetch
`setuptools` for the build when it is not cached. CLI implementations are installed;
`tests/` and `examples/` stay in the library source.

Confirm it, from a directory that is not the copied folder:

```bash
python3 -c "import workrecovery; print(workrecovery.__file__)"   # …/site-packages/workrecovery/__init__.py
```

Then write the store adapter — two methods, and the failure
translation is the important half:

```python
from workrecovery import (
    StoreOccupied, StoreRefused, StoreTimeout, StoreUnavailable,
)

class MyStore:
    def save(self, run_id: str, content: bytes, content_type: str) -> None:
        # Create-if-absent, never overwrite. The conditional header is what
        # makes that atomic; a read-then-write has a window.
        try:
            self.client.put(run_id, content, content_type, if_none_match="*")
        except MyAlreadyExists:
            if self.client.get(run_id) == content:
                return                    # identical: committing again is a no-op
            raise StoreOccupied(f"run {run_id!r} already holds different content")
        except MyTimeout as slow:
            raise StoreTimeout("write timed out", operation="write") from slow
        except MyConnectionError as down:
            raise StoreUnavailable(str(down)) from down
        except MyValidationError as no:
            raise StoreRefused(str(no)) from no

    def load(self, run_id: str) -> bytes | None:
        try:
            return self.client.get(run_id)
        except MyNotFound:
            return None          # absent is an answer, not an error
```

Point `root` at a volume that outlives the process. A container's ephemeral
filesystem is not one.

## Use

```python
from workrecovery import RecoverableJobs

jobs = RecoverableJobs(store=MyStore(), root="/var/lib/recovery")

run_id = mint_id()                     # minted BEFORE the work starts
results = do_the_expensive_work()      # finished, in memory, unprotected

outcome = jobs.commit(run_id, results, label="nightly export")

if outcome.saved:
    ...                                 # read back and verified; local copy gone
elif outcome.state == "absent":
    ...                                 # nothing was written; safe to re-run
elif outcome.state == "conflict":
    log.error(outcome.sentence())       # somebody else owns that id; yours is on disk
else:
    log.error(outcome.sentence())       # unknown: look before re-running
```

The payload is bytes, or plain JSON — `dict` with string keys, `list`, `str`,
`int`, `float`, `bool`, `None`. Anything else is refused by name.

For a store with a hard item-size limit, cap it **through** `fit`, never
before the call:

```python
outcome = jobs.commit(run_id, results, fit=lambda p: {"rows": p["rows"][:1000]})
assert outcome.capped                 # the artifact still holds every row
```

After a crash or restart, in a fresh process pointed at the same directory:

```python
for artifact in jobs.pending():        # the runs that did not land
    outcome = jobs.recommit(artifact)  # no work is re-run; the output exists
    print(outcome.sentence())

for path, reason in jobs.problems():   # unreadable files, reported not deleted
    print(path, reason)
```

Rules worth holding on to:

- `saved` means a read-back returned identical bytes. Nothing else does.
- On `unknown`, do not re-run blindly — the write may have landed.
- On `conflict`, do not retry under the same id: another run owns it, its bytes
  were left alone, and yours is still in the recovery directory.
- `save` is create-if-absent-or-identical, never an overwrite. Implement it
  with an atomic conditional write — `If-None-Match: *`, or a unique constraint
  — and raise `StoreOccupied` on a collision. Without one you inherit a race
  the engine's pre-write check narrows but cannot close.
- Read by run id with `read(...)`; read a file with `read_path(...)`, which
  refuses anything outside the recovery root.
- The local copy is deleted only when the store has everything.
- Never delete the recovery directory before `pending()` is empty.

## Verify

In the copied folder, offline:

```bash
python3 tests/selftest.py                        # framework-free; one line per check
for f in examples/*.py; do python3 "$f"; done    # six worked examples, all asserting
pip install -r requirements-dev.txt && python3 -m pytest tests
```

Core self-tests target the library source. Examples use the installed public
package without path injection; install the library before running them.

`tests/selftest.py` exits non-zero on any failure and writes only under a
temporary directory it removes. The pytest suite adds a thread race for a
single run id, a symlink planted at the artifact path, path-traversal
attempts, and a second interpreter reading an artifact this one wrote.

Against your own store, the honest check is a deliberate failure: make the
store time out, and confirm the outcome is a named state — `absent`,
`unknown`, `conflict` or `saved` — and never a guess. A store that fails the
write reports `absent`; one that fails *after* the write, or on the read-back,
reports `unknown`, and `unknown` is the state most adapters get wrong. While
the run is unsaved the artifact is on disk; `recommit` it from a fresh process
and confirm the file disappears once the read-back verifies. It stays only when
the stored copy is not the whole output — a `capped` save keeps the full
original for recovery, on purpose.

Operator tooling, read-only except for an explicit export. Set `RUN_ID` from the existing
pending list; `OUTPUT_FILE` must name a new, approved export destination:

```bash
workrecovery list   /var/lib/recovery
workrecovery show   /var/lib/recovery --run-id "$RUN_ID"
workrecovery verify /var/lib/recovery
workrecovery export /var/lib/recovery --run-id "$RUN_ID" --out "$OUTPUT_FILE"
```

## Remove

The box owns files, so order matters:

1. `workrecovery list <root>` — commit or export anything still
   pending. Those are completed runs that never landed.
2. `grep -rn workrecovery <your-repo>` and remove the call sites.
3. `python3 -m pip uninstall recoverable-jobs`.
4. Delete the folder.
5. Delete the recovery directory — after step 1, never before.

No third-party dependencies to uninstall, no schema to migrate, no cloud
resource to revoke. Artifacts already written stay readable without this code:
they are plain JSON, and CONTRACT.md specifies the envelope.

## Read next

- [README.md](README.md) — rationale, adoption boundary, limits.
- [CONTRACT.md](CONTRACT.md) — the spec and the full outcome state table.
- [GOTCHAS.md](GOTCHAS.md) — G1–G16: the failures this box exists to prevent.
