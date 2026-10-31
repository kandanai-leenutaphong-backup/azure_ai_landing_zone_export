# recoverable-jobs

Canonical owner of `workrecovery`. Python 3.10+, no runtime dependencies.
From the repository root:

```bash
python -m pip install ./.github/skills/recoverable-jobs
```

Executable recovery example using only temporary synthetic output:

```python
from tempfile import TemporaryDirectory
from workrecovery import MemoryStore, RecoverableJobs, StoreTimeout

with TemporaryDirectory() as root:
  jobs = RecoverableJobs(store=MemoryStore(timeout=StoreTimeout()), root=root)
  outcome = jobs.commit("example-run", {"rows": [1, 2, 3]})
  assert outcome.state == "absent" and not outcome.saved
  restarted = RecoverableJobs(store=MemoryStore(), root=root)
  artifact = restarted.read("example-run")
  assert artifact.payload == {"rows": [1, 2, 3]}
  assert restarted.recommit(artifact).saved
  assert not restarted.pending()
```

[Guide](GUIDE.md), [contract](CONTRACT.md), [failure knowledge](GOTCHAS.md),
[exact source migration manifest](MIGRATION.json). User recovery roots are not
package content and are never moved or removed by installation.

Completed expensive work survives a failed save. Write the finished output
locally first, store it, verify the store really holds the identical bytes, and
only then remove the local copy — with `saved`, `absent` and `unknown` kept
apart so nobody re-runs an hour of work that is already there.

Standard library only. No cloud SDK, no model, no scheduler, no database.

## Why this exists

A run of expensive work — a model batch, a report build, a nightly export —
finishes, holds its entire result in memory, and then calls the store. That
call is the dangerous part: it can take minutes, it can fail, and the process
can be killed in the middle of it. When that happens the work is gone, and the
cost is the whole run rather than the call.

The original of this pattern was written after a job spent **23 minutes** of
real work producing a finished dataset and lost every row because the save
failed. Writing the bytes down first costs milliseconds and covers a store
failure, a container eviction and a `SIGKILL` with one mechanism instead of
three.

Two further things make it more than a `try/except`:

- A write that **times out** may already have succeeded. "The save failed" and
  "nothing was saved" are different claims, and reporting the second when you
  observed the first sends someone to redo work that exists.
- Cleaning up the local copy after a successful save is only safe if the store
  demonstrably holds the same bytes. Otherwise cleanup is data loss with good
  intentions.

Symptom-first list of the rest: [GOTCHAS.md](GOTCHAS.md).

## Adoption boundary

**One import, one object: `RecoverableJobs(store=..., root=...)`.**

```python
from workrecovery import RecoverableJobs

jobs = RecoverableJobs(store=my_store, root="/var/lib/recovery")

results = do_the_expensive_work()          # finished, in memory, unprotected
outcome = jobs.commit(run_id, results)     # preserved, stored, verified

if not outcome.saved:
    log.error(outcome.sentence())          # names the file the work is still in
```

Everything the mechanism depends on is injected in that constructor and
nowhere else: the destination `store`, the artifact directory, and the `clock`.
There is no global state, no import-time configuration and no ambient
filesystem path.

The same object is the recovery half after a restart — `pending()`, `read()`,
`read_path()`, `recommit()`, `problems()`, `discard()` — so adopting this is one
call site, not a set of collaborating pieces.

The only thing you must write is the store adapter: two methods, `save` and
`load`, translating your client's failures into `StoreRefused`,
`StoreUnavailable`, `StoreTimeout` and `StoreOccupied`. `save` is
create-if-absent-or-identical, never an overwrite, and the way to make that
airtight is an atomic conditional write — `If-None-Match: *`, or a unique
constraint. `MemoryStore` is the worked reference and the test double, and it
enforces the rule rather than approximating it.

## What you get

- **The output on disk before anything risky happens**, atomically, with no
  clobbering: a second owner of a run id is refused, not merged.
- **Four distinguishable outcomes.** `saved` means read back and compared.
  `absent` means known not written. `conflict` means the id already held
  someone else's bytes, which were left alone. `unknown` means exactly that,
  with the id to look for.
- **A verified read-back before cleanup.** Accepted is not stored.
- **Size capping that does not eat the tail.** `fit` is applied after staging,
  and when the store holds less than the artifact the artifact is kept — with
  a warning that says why.
- **A reader for after the restart.** `pending()` lists what did not land,
  `read()` returns it digest-verified, `recommit()` offers it again.
- **Refusals instead of tidy-ups.** Corrupt artifacts are reported, never
  deleted; a discard proves the file is still the recorded one first.
- **Bounded everything.** Payload ceiling, attempt ceiling, exponential
  backoff through an injected clock so tests never sleep.
- **No payload in any log line**, summary or repr.

## MCP Adapter

The optional installed `workrecovery.mcp` adapter adds local staging and inspection. It does not
configure a destination store, schedule work, or claim that a staged artifact is a completed
commit. `recovery_stage` reports `preserved`, with `saved: false`; full commit/recommit
remains the Python API with the caller's `Store` implementation.

The operator supplies `--config <settings.json>` explicitly.
The three grants `allow_stage`, `allow_inspect`, and `allow_payload_reads` all default to false.
The operator may set an absolute `recovery_root`; callers can pass only validated run IDs.

```json
{
  "recovery_root": "/var/lib/my-app/recovery",
  "allow_stage": true,
  "allow_inspect": true,
  "allow_payload_reads": false,
  "max_payload_bytes": 131072,
  "max_scan_entries": 200
}
```

Use an actual operator-owned directory on durable storage, and restart after configuring it.
Without an override, artifacts sit beside the settings file in `artifacts/`.
Inspect and commit/export pending results before removing any operator data.
The adapter offers no deletion, path-based read/export, arbitrary store loader or grant tool.
Set `SETTINGS_FILE` to the reviewed absolute settings-file path. Commands below run from
this library directory; they were not executed in this documentation sweep.

```bash
python -m pip install '.[mcp]'
python tests/mcp_smoke.py
workrecovery-mcp --config "$SETTINGS_FILE"
```

This tests staging, restart/read-back, no-clobber, corruption and scope refusals using temporary
directories. The library remains standard-library-only; MCP dependencies are an optional extra.
Its [CONTRACT.md](CONTRACT.md) documents the distinction between preservation and destination persistence.
This standalone adapter is distinct from the implemented
[framework host](../harness-guide/framework/README.md#composition-contract), which adds fixed bindings,
exact grants and execution context. Old skill-root registrations are retired; neither
installation nor discovery launches a server or grants recovery access.

## Standalone Python Install

Copy the folder, then install it into the environment that will import it:

```bash
python3 -m pip install ./.github/skills/recoverable-jobs
python3 -c "import workrecovery; print(workrecovery.__file__)"
```

An ordinary non-editable install. The last line should print a path under
`site-packages`, from any working directory, with no `PYTHONPATH` and no
`sys.path` edit — copying the folder alone does not achieve that, because the
importable package sits one level down inside it.

No runtime dependencies: `requirements.txt` is a comment, `pyproject.toml`
declares an empty `dependencies`, and the install needs the network only to
fetch `setuptools` for the build when it is not cached. `workrecovery` and its CLI
modules are installed; `tests/` and `examples/` stay in the library source.

Write the adapter for your store:

```python
from workrecovery import StoreRefused, StoreTimeout, StoreUnavailable

class MyStore:
    def save(self, run_id: str, content: bytes, content_type: str) -> None:
        try:
            self.client.put(run_id, content, content_type)
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

Point `root` at a volume that outlives the process — see Limits.

## Verify

```bash
python3 tests/selftest.py                       # framework-free, offline
for f in examples/*.py; do python3 "$f"; done   # six worked examples
pip install -r requirements-dev.txt && python3 -m pytest tests
```

`tests/selftest.py` needs no test framework, writes only under a temporary
directory it deletes, and asserts the ordering claim from inside the store's
own `save()`: the artifact already exists when the risky call begins. The
pytest suite adds a thread race for one run id, a symlink planted at the target
path, a symlink swapped in *after* the pre-open check, a traversal attempt, a
malformed envelope field per contract row, and a genuine second interpreter
that reads an artifact this one wrote. Both put the copied folder on
`sys.path` themselves, so they test the folder in front of you rather than
whatever is installed.

Operator tooling, read-only apart from an explicit export:

```bash
workrecovery list   /var/lib/recovery
workrecovery verify /var/lib/recovery
workrecovery export /var/lib/recovery --run-id <id> --out ./out.json
```

## Failure model

- Programming and configuration errors raise: `InvalidRunId`,
  `PayloadNotSupported`, `PayloadTooLarge`, `ValueError`. Nothing is written.
- Losing the safety net raises: `StagingFailed`, **before** the store write is
  attempted, under the default policy.
- Ownership conflicts raise: `ArtifactExists`, and the existing file is
  untouched.
- Store failures do **not** raise. They are `CommitOutcome.state` —
  `saved`, `absent`, `conflict` or `unknown` — with `detail`, `error`,
  `attempts` and a `warnings` tuple.
- Corruption raises on read: `ArtifactCorrupt`. Nothing is deleted. That
  includes a file that is oversized, deeply nested, a symlink or not a regular
  file — all of them are one file's problem, never the listing's.
- Unsafe cleanup raises: `StaleArtifact`. Nothing is deleted.
- `KeyboardInterrupt` and every other `BaseException` propagate untouched, and
  the artifact stays where it is.

## Limits

Stated because a recovery mechanism that overstates its reach is worse than
none:

- **Local disk is not durable storage.** This survives a failed or slow store
  write, a killed process and a container restart that keeps its volume. It
  does **not** survive host loss, disk loss, or an ephemeral filesystem
  discarded on eviction. Point `root` at a volume that outlives the process.
- **`fsync` is best effort.** The file is flushed and the directory entry is
  synced where the filesystem allows it. Some filesystems and container
  storage drivers do not honour that, and this box cannot verify that they did.
- **Read-back can be eventually consistent.** A correct write can read back as
  absent on a store that has not caught up, which is reported as `unknown`.
  `unknown` never means "lost", and re-running on `unknown` risks a duplicate:
  look first.
- **Run-id uniqueness is yours.** There is no distributed lock and no leader
  election. `ArtifactExists` catches a second local owner; it cannot catch a
  second machine. On the store side, the no-clobber guarantee is **your
  adapter's**: the engine reads before it writes, which narrows the window but
  does not close it. Only an atomic conditional write does, and an adapter
  without one leaves a race this package cannot close for you.
- **The recovery directory is a trust boundary.** Anyone who can write into it
  can plant a file. Reads open with `O_NOFOLLOW` and decide from the
  descriptor, so a symlink cannot be swapped in after a check, a FIFO cannot
  park the reader, and one planted file can neither hide the rest nor exhaust
  memory. The **root's own path** is not covered: a parent directory replaced
  between calls needs `openat` on a held directory descriptor, which this
  package does not do, so every component of the root is trusted host
  configuration. Nothing stronger is claimed.
- **Synchronous only.** If your store client is async, wrap the calls.
- **No encryption at rest.** The recovery directory is created owner-only
  (`0o700`), which is a permission, not a protection.
- **Not a scheduler.** Nothing here retries a job, resumes a partial
  computation or runs anything. It preserves and re-offers finished output.
- **Payload shapes are deliberately narrow** — bytes, or plain JSON. Anything
  else, serialise yourself and pass bytes.

## Removal

The box owns files, so removal has an order:

1. Run `workrecovery list <root>` and commit or export anything
   still pending — those are runs that did not land.
2. `grep -rn workrecovery <your-repo>` and remove the call sites.
3. `python3 -m pip uninstall recoverable-jobs`.
4. Delete the folder.
5. Delete the recovery directory **after** step 1, never before.

There are no third-party dependencies to uninstall, no schema to migrate and no
cloud resource to revoke. Artifacts already written stay readable without this
code — they are plain JSON, and [CONTRACT.md](CONTRACT.md) specifies the
envelope.

## Files

| Path | What it is |
| --- | --- |
| [GUIDE.md](GUIDE.md) | Agent-facing: decide, install, use, verify, remove |
| [CONTRACT.md](CONTRACT.md) | The spec, including the full outcome state table |
| [GOTCHAS.md](GOTCHAS.md) | G1–G16, symptom first, cited from the code |
| `pyproject.toml` | Packaging metadata: installs `workrecovery`, nothing else |
| `workrecovery/` | The mechanism: payload, artifacts, clock, store, commit |
| `examples/` | Six runnable worked examples, offline, all asserting |
| `tests/` | `selftest.py` (no framework), the pytest suite, and the regression suite |
| `workrecovery.cli` | Installed operator CLI: list, show, verify, export |
