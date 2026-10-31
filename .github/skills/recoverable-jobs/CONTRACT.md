# Contract

The specification. Everything here is asserted by `tests/selftest.py`,
`tests/test_recovery.py` or a worked example, and this document is sufficient
to reimplement the box without reading its source.

Import name: `workrecovery`. Python 3.10+, matching `requires-python` in
`pyproject.toml`; standard library only.

## MCP Adapter

The optional MCP adapter owns local artifact preservation, not a destination store. It calls
`ArtifactStore` directly and never substitutes a memory store while claiming durable destination
persistence. The full `RecoverableJobs` commit/recommit API below remains available to Python callers.

| Tool | Inputs | Output |
| --- | --- | --- |
| `recovery_status` | empty object | root, grants, bounds, configuration path, `destination_store_configured: false` |
| `recovery_stage` | `run_id`, `payload_json` string | `state: "preserved"`, `saved: false`, artifact summary |
| `recovery_list` | empty object | artifact summaries, unreadable count, `saved: false` |
| `recovery_read` | `run_id` | verified JSON payload plus artifact summary |

Operator settings: optional absolute `recovery_root`, `allow_stage`, `allow_inspect`,
`allow_payload_reads` (all false), `max_payload_bytes` (131072; 1-1048576), and
`max_scan_entries` (200; 1-2000). A missing root uses `artifacts/` beside the explicit settings file.
Production recovery should use an explicitly owned durable volume. Package uninstall must not
remove operator data. Status does not create an artifact directory. Unknown settings are refused.

Stage validates raw UTF-8 and encoded payload byte limits before writing, then uses the library's
atomic no-clobber stage. JSON only; no metadata, byte payloads, arbitrary paths or labels in this
adapter. IDs retain the library's 1-128-character rules and traversal refusal. Inspection checks
the directory entry bound before scanning; an oversized directory is refused, not silently truncated.
The bound is a per-request scan guard, not a concurrent disk quota. The root and artifact symlink
checks remain active. Reads verify the digest and refuse non-JSON payloads or corruption.

There are no MCP delete, discard, export-to-path, commit-to-store or grant tools. Corrupt and
conflicting files remain in place. Errors set `isError` and name categories without logging payloads.
The [MCP smoke check](tests/mcp_smoke.py) stages output, restarts the actual server, reads it back,
and tests no-clobber, traversal, size and corruption refusals. Export/commit pending work through
the existing Python/CLI surfaces before uninstalling or deleting client data.

Install the `mcp` extra and run `workrecovery-mcp --config <settings.json>`, or import
`workrecovery.mcp.Settings`, `RecoveryTools`, and `serve`. Nothing starts on import.
The old `workrecovery_*` tool names and automatic environment bootstrap are retired;
the [framework host](../harness-guide/framework/README.md#composition-contract) is implemented and opt-in.
It requires an explicit absolute root, fixed binding, exact tool grants and execution
context in addition to native stage/inspect/payload-read permission. That host does not
inherit this standalone settings-file fallback or add a destination-store commit tool.

## Model of the world

- A **job** produces one **completed output**. This package starts when the
  work is finished. It never runs, re-runs or resumes a computation.
- A **run id** is minted by the caller *before* the work starts, is unique to
  one attempt, and is both the store key and the artifact file name. An id
  nobody recorded cannot be looked for after a timeout.
- An **artifact** is the local durable copy of the completed output, written
  before anything fallible is attempted.
- A **store** is the caller's authoritative destination, injected, never
  imported here.
- The **identity** of an output is the sha256 of its canonically encoded
  bytes. Not the source, not a row count.

## Payload

Exactly two shapes, and anything else raises `PayloadNotSupported`:

| Shape | Content type | Encoding |
| --- | --- | --- |
| `bytes`, `bytearray` | `application/octet-stream` | verbatim |
| JSON value | `application/json` | canonical UTF-8 |

A JSON value is built only from `dict` with `str` keys, `list`, `str`, `int`,
`float`, `bool`, `None`, nested at most 64 deep. Tuples, sets, `NaN`,
`Infinity` and non-string keys are refused by name — each would round-trip to
something other than what was put in.

Canonical encoding is `sort_keys=True`, `separators=(",", ":")`,
`ensure_ascii=False`, `allow_nan=False`. It is deterministic across processes,
which is what makes digest comparison meaningful.

- `encode_payload(payload) -> (bytes, content_type)`
- `decode_payload(content, content_type) -> payload`
- `digest(content) -> str` — sha256 hex of the output bytes.
- `JSON_CONTENT_TYPE`, `BYTES_CONTENT_TYPE`

## Artifact envelope, version 1

A UTF-8 JSON object. `schema` is `recoverable-job/artifact`
(`ENVELOPE_SCHEMA`), `version` is `1` (`ENVELOPE_VERSION`). A reader that sees
either field differ refuses rather than guesses. The field set is **closed**: a
document carrying a field this table does not list is `ArtifactCorrupt`, because
a reader that ignores an unknown key accepts a document whose meaning it does
not share.

| Field | Type | Rule enforced on read |
| --- | --- | --- |
| `schema` | `str` | equals `ENVELOPE_SCHEMA` |
| `version` | `int` | equals `ENVELOPE_VERSION`; a `bool` is refused, because `True == 1` |
| `run_id` | `str` | passes `validate_run_id`, **and** the file is named `<run_id>.artifact.json` |
| `created_at` | `str` | non-empty, ≤64 characters |
| `label` | `str` | optional, ≤`MAX_LABEL_CHARS` (512) |
| `content_type` | `str` | one of the two content types |
| `content_sha256` | `str` | 64 lowercase hex characters |
| `content_bytes` | `int` | not a `bool` |
| `metadata` | `object` | optional; a JSON object that re-encodes to ≤`max_metadata_bytes` |
| `content` | JSON | the payload, when JSON — stored decoded, so it is readable and greppable |
| `content_base64` | `str` | the payload, when bytes |

`content` and `content_base64` are mutually exclusive, and the one present must
match `content_type`.

The file name check is load-bearing rather than tidy: `recommit` writes to
`artifact.run_id`, which comes out of the file, and `discard` matches on it. A
file whose name and id disagree would let anyone who can write in the recovery
directory choose the store key a recovery writes to.

Every one of these refusals is `ArtifactCorrupt`, which is a `RecoveryError`,
which is what keeps `list()` total: one malformed file yields one entry in
`problems()` and hides nothing.

On read the content is re-encoded canonically and both the digest and the
length are compared. Any mismatch is `ArtifactCorrupt`; the file is never
repaired and never deleted.

File name is `<run_id>.artifact.json`, directly inside the root.

The envelope is written with `indent=2` so a person can read it. That is not
free — pretty-printing a payload of many small values measured 4.9× its
canonical size — so `stage` measures the encoded envelope, falls back to the
compact encoding when the readable one would exceed `max_artifact_bytes`, and
refuses with `StagingFailed` if even that does not fit. Nothing is written in
that case: a staged file the reader rejects is work preserved nowhere while
looking preserved.

## Run ids

`validate_run_id(run_id) -> str`. Accepts 1–128 characters from
`[A-Za-z0-9._-]` beginning with a letter or digit. Everything else —
separators, `..`, leading dot, whitespace, NUL, absolute paths, non-strings —
raises `InvalidRunId` before anything is opened.

## `ArtifactStore`

`ArtifactStore(root, *, clock=SystemClock(), dir_mode=0o700,
max_artifact_bytes=DEFAULT_MAX_ARTIFACT_BYTES,
max_metadata_bytes=DEFAULT_MAX_METADATA_BYTES)`

| Method | Behaviour |
| --- | --- |
| `path_for(run_id)` | the validated path, asserted to be inside the root |
| `stage(run_id, payload, *, label="", metadata=None, content=None, content_type=None)` | writes the artifact atomically; returns `Artifact` |
| `read(path)` | one artifact, digest verified |
| `read_run(run_id)` | the same, by id |
| `read_inside_root(path)` | as `read`, refusing any path outside the root |
| `list()` | every readable artifact, sorted by name |
| `problems()` | `(path, reason)` for every file that does not read back |
| `discard(artifact)` | deletes only after re-reading and matching id + digest, and only inside the root |

`stage` writes to a temporary file in the same directory, `fsync`s it, creates
the final name with `os.link` (atomic and **non-clobbering**), then `fsync`s
the directory best-effort. The temporary file is always removed. The root is
created with `dir_mode` if absent; a symlinked root is refused rather than
followed.

`stage` also refuses before it touches the filesystem: a `label` that is not a
string or is over `MAX_LABEL_CHARS`, and `metadata` that is not a JSON object
or encodes to more than `max_metadata_bytes`, raise `PayloadNotSupported` or
`PayloadTooLarge` with the root not even created. Metadata is a **snapshot**,
round-tripped through the canonical encoding for the same reason the payload
is: a caller that mutates a nested object afterwards cannot change the record.

`Artifact.payload` is a **snapshot** too, decoded from the bytes the digest
covers. Mutating the object passed to `stage` afterwards changes neither the
record nor what a later `recommit` stores.

### Reading is bounded, and total

The recovery directory is a place other processes can write, so anything found
there is untrusted input. `read` makes every decision from the descriptor it is
about to read, not from a check on the name a moment earlier:

- the file is opened with `O_NOFOLLOW`, so a final-component symlink is refused
  by the syscall itself and there is no interval in which one can be swapped in;
- `O_NONBLOCK`, so a planted FIFO returns instead of parking the reader — and
  every process listing that directory — until somebody writes to it;
- type and size come from `fstat` on that descriptor: a directory, a device, a
  socket, a FIFO or anything over `max_artifact_bytes` is `ArtifactCorrupt`
  before its content is read;
- where `O_NOFOLLOW` does not exist (Windows), the fallback is an `lstat`
  before and a `(st_dev, st_ino)` comparison after, which **detects** a swap
  rather than preventing it, and refuses with a message that says so;
- unparseable at any depth, including `RecursionError` from deeply nested JSON
  and any `ValueError` or `MemoryError` from the decoder — `ArtifactCorrupt`.

Refusing a planted symlink never unlinks it. Removing the link would not undo
the read that the old check-then-open order allowed, and deleting a file a
reader does not recognise is how somebody else's only copy disappears.

#### Root path trust boundary

The defences above cover the **final component**. They do not cover the root's
own path: a parent directory replaced between two calls is not detected, because
detecting it needs a directory descriptor held open across calls and `openat`,
which this package does not do. The root's path — every component of it — is
therefore trusted host configuration, the same way `dir_mode=0o700` assumes the
host is not handing out write access to it.

Concretely: another process that can write *inside* the root is defended
against; another process that can replace the root, or a directory above it, is
not, and no bound here should be read as claiming otherwise.

`DEFAULT_MAX_ARTIFACT_BYTES` is `artifact_ceiling(DEFAULT_MAX_PAYLOAD_BYTES)`:
twice the payload ceiling plus 64 KiB of envelope, which covers base64
inflation, JSON escaping and the bounded `metadata` and `label`.
`RecoverableJobs` derives the store's ceiling from its own `max_payload_bytes`,
so raising one raises the other. `stage` never writes a file outside that
ceiling, so nothing this store writes is something its own `read` refuses.

`_scan` — and therefore `list()` and `problems()` — isolates every file: one
bad file yields one problem entry, never an exception past the call, and a file
that disappears mid-scan is a race, not a problem. No file is ever deleted by a
read path. A root that becomes unlistable raises `StagingFailed`, because that
is not one file's problem and must not be reported as an empty directory.

Raises: `InvalidRunId`, `ArtifactExists` (existing file untouched),
`StagingFailed` (any filesystem refusal), `ArtifactMissing`, `ArtifactCorrupt`,
`StaleArtifact`.

`Artifact` is frozen: `run_id`, `created_at`, `label`, `content_type`,
`content_sha256`, `content_bytes`, `metadata`, `payload`, `path`, plus
`summary()`. `summary()` and `__repr__` never contain the payload.

## `RecoverableJobs` — the adoption boundary

```python
RecoverableJobs(
    *, store, root=None, artifacts=None, clock=None,
    max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES,   # 64 MiB
    max_attempts=DEFAULT_MAX_ATTEMPTS,             # 3
    backoff_seconds=DEFAULT_BACKOFF_SECONDS,       # 1.0
    staging_policy="require",                      # or "proceed"
    keep_artifact=False,
)
```

`ValueError` at construction for: neither `root` nor `artifacts`;
`max_attempts < 1`; `max_payload_bytes < 1`; negative backoff; an unknown
`staging_policy`.

`StagingPolicy` is the literal type of that argument: `"require"` (default,
refuse the store write when no local copy could be made) or `"proceed"` (run
unprotected, and say so in `CommitOutcome.warnings`).

### `commit(run_id, payload, *, label="", metadata=None, fit=None)`

The order is normative:

1. validate the run id; encode the **full** payload; take `staged_sha256`;
2. refuse with `PayloadTooLarge` if it exceeds `max_payload_bytes` — before
   anything is written;
3. stage the artifact. On `StagingFailed`: raise under `"require"`, or
   continue under `"proceed"` with a warning. `ArtifactExists` always raises;
4. **then** apply `fit`, if given, to a copy. Returning `None` means unchanged.
   A larger result or a changed content type is a `ValueError`;
5. `store.save`. A pre-write `store.load` narrows the collision window: bytes
   already there and identical means the write is skipped entirely and the
   outcome is `saved`; different bytes means `conflict` with no write
   attempted. `StoreUnavailable` retries up to `max_attempts` with exponential
   backoff via `clock.sleep`. `StoreRefused` does not retry. `StoreTimeout` is
   never retried. `StoreOccupied` — the adapter's own no-clobber refusal — is
   `conflict`, and is the authoritative one, because the pre-write read is not
   atomic;
6. read back with `store.load` and compare digests;
7. discard the artifact only if the read-back matched **and** nothing was
   capped.

Any other `BaseException` — including `KeyboardInterrupt` — propagates, and the
artifact stays.

### `recommit(artifact)`

Re-encodes the artifact's payload, checks it against the recorded digest
(`ArtifactCorrupt` if it differs), then runs steps 5–7. It does not re-stage
and does not re-run anything.

### Reading

- `pending() -> list[Artifact]` — outputs still on disk: the runs that did not
  land.
- `problems() -> list[tuple[Path, str]]`
- `read(run_id) -> Artifact` — **by run id**. Dispatch is by type, never by the
  shape of the string: `"nightly.0001"` is a run id, not a file name. A
  `pathlib.Path` argument is forwarded to `read_path`.
- `read_path(path) -> Artifact` — by path, refusing anything that resolves
  outside the recovery root with `InvalidRunId`.
- `discard(artifact)`

## `CommitOutcome`

Frozen. Store failures are outcomes, not exceptions.

| Field | Meaning |
| --- | --- |
| `state` | `saved`, `absent`, `unknown`, `conflict` (`CommitState`) |
| `run_id` | the id, and the id to look for |
| `content_sha256` | digest of the bytes offered to the store |
| `staged_sha256` | digest of the full completed output |
| `artifact` | the local copy, or None when discarded or never written |
| `capped` | whether the stored payload is smaller than the produced one |
| `verified` | whether a read-back returned identical bytes |
| `attempts` | store write attempts made |
| `detail` | one sentence, payload-free |
| `error` | the store failure that ended the attempt, if any |
| `warnings` | tuple of caveats: not recoverable, capped, stale artifact |

Plus `saved`, `recoverable`, `sentence()`, `summary()`. None of them contain
the payload.

**State table** — the whole contract in one place:

| Situation | `state` | `verified` | artifact |
| --- | --- | --- | --- |
| identical bytes already stored | `saved` | True | discarded unless capped or `keep_artifact` |
| different bytes already stored | `conflict` | False | kept |
| `StoreOccupied` from the adapter | `conflict` | False | kept |
| accepted, read-back identical | `saved` | True | discarded unless capped or `keep_artifact` |
| accepted, read-back returned nothing | `unknown` | False | kept |
| accepted, read-back returned other content | `unknown` | False | kept |
| read-back raised | `unknown` | False | kept |
| timed out, read-back identical | `saved` | True | discarded |
| timed out, read-back returned nothing | `absent` | False | kept |
| timed out, read-back returned other content | `unknown` | False | kept |
| refused | `absent` | False | kept |
| unreachable after `max_attempts` | `absent` | False | kept |
| other `StoreError` | `unknown` | False | kept |

## `Store` protocol

```python
def save(self, run_id: str, content: bytes, content_type: str) -> None: ...
def load(self, run_id: str) -> bytes | None: ...
```

### The store contract

`save` is **create-if-absent, or accept byte-identical content**. Not an
overwrite. Three cases, all required of an adapter:

1. nothing under `run_id` — write it;
2. `content` byte-identical to what is stored — succeed, change nothing. This
   is what makes `recommit` after a restart safe to run twice;
3. different bytes under `run_id` — raise `StoreOccupied` and leave the stored
   bytes exactly as they were.

**Case 3 is airtight only with an atomic conditional write**, because a
read-then-write has a window. Cosmos DB and Azure Blob Storage accept
`If-None-Match: *` on create; S3 accepts the same; a SQL store gets it from a
unique constraint on the id column, translated to `StoreOccupied`. An adapter
that cannot do this must say so: its callers inherit a race this package cannot
close, and the engine's pre-write check narrows the window without removing it.
The artifact-side guarantee is unconditional — `os.link` is atomic — and it is a
different guarantee from this one.

`load` returns `None` for "not there" — absence is an answer, not an error. An
adapter translates its client's failures into `StoreRefused`,
`StoreUnavailable`, `StoreTimeout(operation="write"|"read-back")` or
`StoreOccupied`; anything else is treated as an unknown outcome.

`MemoryStore(*, items=None, refuse="", unavailable_times=0, timeout=None,
lands=False, load_error=None, load_blind=False)` is the test double. It
**implements** the contract above rather than approximating it — a double that
clobbered would make every no-clobber test vacuous — and it snapshots the bytes
it is given. It includes `timeout` with `lands=True`, the write that timed out
**and landed**, which is the case the reconciliation exists for. It records
`saves` and `loads`.

## Clock

`Clock` protocol: `now() -> str`, `monotonic() -> float`, `sleep(seconds)`.
`SystemClock` is the default. `FixedClock(start, step)` never waits and records
every requested delay in `slept`, so a backoff schedule is asserted as data.

## Errors

`RecoveryError` is the base. `PayloadNotSupported`, `PayloadTooLarge`,
`InvalidRunId`, `StagingFailed`, `ArtifactExists`, `ArtifactMissing`,
`ArtifactCorrupt`, `StaleArtifact`, and `StoreError` with `StoreRefused`,
`StoreUnavailable`, `StoreTimeout`, `StoreOccupied`.

`__version__` is the package version string.

## Invariants a reimplementation must preserve

1. The artifact is written before any fallible or slow operation.
2. Size capping happens after staging; the artifact keeps the full output.
3. `saved` requires a read-back that matched. "Accepted" is not "stored".
4. The artifact is deleted only when the store holds identical bytes *and*
   nothing was capped.
5. Nothing is clobbered by this package or by a conforming adapter: not an
   artifact, not a foreign file, not a foreign document already under the run
   id. The artifact guarantee is unconditional; the store guarantee is the
   adapter's, and is only airtight with an atomic conditional write.
6. Nothing is deleted without first proving it is the recorded file, inside
   the recovery root.
7. Absent, unknown, conflict and saved are four distinct outcomes and never
   collapse.
8. A timed-out write is never retried.
9. Corrupt, oversized, deep, symlinked and non-regular files are reported,
   never repaired, never followed and never removed; one of them never hides
   the readable ones.
10. No payload appears in any log line, summary or repr.
11. A record never disagrees with its own digest: `Artifact.payload` is a
    snapshot of the bytes that were hashed.

## Out of scope

- Scheduling, queueing, or resuming an unfinished computation.
- Any specific store, cloud SDK, database or serialisation format beyond the
  two payload shapes.
- Distributed locking or leader election. Run-id uniqueness is the caller's.
- Encryption at rest, and durability beyond the local filesystem.
- Async I/O: the surface is synchronous. Wrap it if your store is not.
