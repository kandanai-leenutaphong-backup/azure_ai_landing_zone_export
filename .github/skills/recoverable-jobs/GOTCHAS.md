# Gotchas

Numbered, symptom-first. Every one of these has cost somebody a completed run.
Code cites them as `GOTCHAS.md, Gn`.

## G1 — "The save failed" sends someone to redo work that already exists

**Symptom.** A job reports failure, an operator re-runs it, and the store ends
up with a duplicate — or the second run overwrites something that was fine.

**Cause.** Treating every store exception as "nothing was written". A write
that times out **client-side may already have succeeded**: the request was
sent, the item was committed, and only the answer was lost.

**Fix.** Three outcomes, not two. `StoreRefused` and `StoreUnavailable` mean
nothing landed. `StoreTimeout` means look. `CommitOutcome.state` is `saved`,
`absent` or `unknown`, and `unknown` is a legitimate result rather than a
failure to produce one.

## G2 — The recovered payload is not the payload that was produced

**Symptom.** A recovered run differs from the original in a way nobody
intended: tuples came back as lists, a set is gone, a float is `NaN`, a dict
key was an integer and is now a string.

**Cause.** Accepting "anything JSON-serialisable". `json` happily serialises
things it cannot reproduce.

**Fix.** A payload is exactly bytes, or a JSON value built from `dict` with
`str` keys, `list`, `str`, `int`, `float`, `bool` and `None`. Everything else
is refused by name, at the boundary, with the reason. Round-tripping is
asserted for every accepted shape.

## G3 — The safety net silently was not there

**Symptom.** A run fails at the store, the operator goes to the recovery
directory, and it is empty. The filesystem was read-only, or full, and nobody
was told.

**Cause.** Best-effort staging whose failure is logged at debug level, or
swallowed, while the expensive store write proceeds as if protected.

**Fix.** The default `staging_policy="require"` raises `StagingFailed`
**before** the store write is attempted, while the caller still holds the
output and can decide. The weaker `"proceed"` policy exists, is explicit, and
puts "this run is not recoverable" in `CommitOutcome.warnings`.

## G4 — A run id becomes a path

**Symptom.** Files appear outside the recovery directory, or an unrelated file
is overwritten.

**Cause.** Run ids are used as file names, and a caller-supplied id can contain
`..`, a separator, a leading dot or a NUL.

**Fix.** `validate_run_id` accepts 1–128 characters of `[A-Za-z0-9._-]`
starting with a letter or digit, and the derived path is asserted to sit
directly inside the root. Traversal attempts are refused before anything is
opened.

## G5 — Two workers, one run id, one surviving copy

**Symptom.** Two processes believe they own a run. One overwrites the other's
artifact, and one of the two outputs is gone.

**Cause.** `os.replace` is atomic *and* destructive: it silently clobbers.

**Fix.** The final name is created through a hard link from a temporary file
in the same directory, which is atomic **and** fails when the name exists.
A second owner gets `ArtifactExists` and the first one's bytes are untouched.
A planted symlink at the target is refused for the same reason, rather than
followed.

## G6 — A half-written artifact reads as a good one

**Symptom.** Recovery "succeeds" and commits truncated output, or a
hand-edited file is committed as if it were the original.

**Cause.** No digest, or a digest over the wrong thing, or a digest nobody
checks on read.

**Fix.** The envelope records the sha256 of the output bytes, and every read
re-derives it and compares. Schema and version are checked too. A mismatch is
`ArtifactCorrupt`, the file is **not** deleted, and `problems()` reports it
without hiding the artifacts that are fine.

## G7 — Cleanup deletes the only copy of something else's work

**Symptom.** An unrelated run's output disappears during a tidy-up.

**Cause.** Deleting by pattern, by directory sweep, or by a stale record whose
path now holds a different file.

**Fix.** `discard` re-reads the file and compares run id *and* digest with the
record in hand. Anything else raises `StaleArtifact` and the file stays.
Nothing in this package deletes a file it did not just verify, and nothing
deletes on a glob.

## G8 — The wrong thing is hashed

**Symptom.** A read-back is reported as matching when the store holds a
different document, or as mismatching when it holds the right one.

**Cause.** Identifying the output by its *source* — an input file's hash, a
row count, a job id — instead of by its own bytes. Two different outputs from
one source have the same source hash and the same item count.

**Fix.** Identity is `sha256` of the canonically encoded **output**.
Canonical, so two equal values cannot produce two digests: sorted keys, no
whitespace, no ASCII escaping, `NaN`/`Infinity` refused. Stability across
processes is asserted by running the encoder in a second interpreter.

## G9 — The artifact promises a full output it does not contain

**Symptom.** A message says "the full set is in the local artifact"; the tail
that was dropped to fit the store is in neither place.

**Cause.** Applying the store's size cap *before* writing the local copy. This
one shipped: the cap ran first, the artifact was written from the capped
value, and the reassuring sentence was written from the original intent.

**Fix.** The artifact is written from the full output before `fit` is called at
all, and `CommitOutcome` carries two digests — `staged_sha256` for what was
produced, `content_sha256` for what was stored. When they differ, the artifact
is **kept even after a verified save**, because it is then the only place the
whole output exists, and the outcome says so in `warnings`.

## G10 — "Durable" means more than it can

**Symptom.** A host dies, the artifact directory comes back empty, and
everybody assumed the local copy covered that.

**Cause.** Treating a local file as durable storage.

**Fix.** Honest scope, stated rather than implied. This protects against a
failed, slow or refused store write, a killed process, and a container
restart that keeps its volume. It does not protect against a host or disk
loss, an ephemeral filesystem discarded on eviction, or a store whose
read-back is eventually consistent — where a correct write can read back as
`unknown`, which is why `unknown` never means "lost". Point the recovery root
at a volume that outlives the process, and read the limits section of the
README before relying on it.

## G11 — The record disagrees with its own digest

**Symptom.** An in-memory `Artifact` reports a payload that does not hash to
its `content_sha256`, and a `recommit` of it is refused as corrupt.

**Cause.** Keeping a reference to the caller's mutable payload object. The
digest was taken from a snapshot of the bytes; the object kept changing.

**Fix.** `stage` stores `decode_payload(content, content_type)` — a value
decoded from exactly the bytes that were hashed. Mutating the object you passed
in afterwards changes nothing this package believes. `MemoryStore` snapshots
its bytes for the same reason.

## G12 — One planted file hides every pending run

**Symptom.** `pending()` or `workrecovery list` raises instead of
listing, and every run that did not land becomes invisible to the operator.

**Cause.** A read path that trusts the recovery directory. `json.loads` on
deeply nested JSON raises `RecursionError`, which is not a `RecoveryError` and
escapes `read()`, `_scan()`, `list()` and `problems()` alike. The unbounded
`read_bytes()` next to it has the same shape of problem with a large file, and
a planted symlink or FIFO has it again.

**Fix.** The directory is untrusted input. `read` opens with `O_NOFOLLOW` and
`O_NONBLOCK` and decides type and size from `fstat` on that descriptor, so a
symlink, a directory, a FIFO or anything over `max_artifact_bytes` is refused
before its content is read; and every parser failure — `RecursionError`,
`ValueError`, `MemoryError` — becomes `ArtifactCorrupt`. Every envelope field
is type- and bound-checked too (see G14). `_scan` isolates each file, so one
bad file is one problem entry and never an exception. Nothing suspect is
deleted: it is reported and left.

## G13 — A recovery API that reads anywhere also deletes anywhere

**Symptom.** `read("nightly.0001")` cannot find work that is plainly on disk;
or `read("/somewhere/else.artifact.json")` returns a file this store never
wrote, which `discard` will then happily delete.

**Cause.** Dispatching on the *shape* of the argument — "it has a suffix, so it
must be a path". A run id may contain a dot, so a valid id silently became a
CWD-relative path lookup, and an absolute path from anywhere was accepted as if
it belonged here.

**Fix.** Dispatch by type. `read(str)` is always a run id; `read_path()` — and
`read(Path)` — is a path, and refuses anything that resolves outside the
recovery root with `InvalidRunId`. `discard` applies the same containment, so a
hand-built `Artifact` pointing at another directory cannot delete a file there.
In-process code is trusted with the objects it constructs; the filesystem
boundary is enforced regardless.

## G14 — A field out of the file is used before it is checked

**Symptom.** `list()` raises `TypeError: 'int' object is not iterable` and the
operator sees no pending runs at all. Or, quieter: a `recommit` writes to a
store key nobody chose.

**Cause.** Parsing stops at "it is valid JSON". `dict(document.get("metadata")
or {})` accepts a mapping, and raises `TypeError` for an integer and
`ValueError` for a list of one-element lists — neither is a `RecoveryError`, so
one planted file escapes `read`, `_scan`, `list` and `problems` together and
takes the whole listing with it. The same trust applies to the rest: `run_id`
becomes the key `recommit` writes to and the identity `discard` matches on;
`created_at` and `label` go straight into the record; `"version": true` passes
`!= 1` because `True == 1`; and an unknown field means the document was written
by something that did not share this reader's meaning.

**Fix.** Every field is checked before it is used, and every refusal is
`ArtifactCorrupt` so `list()` stays total: closed field set, `bool` rejected
where an `int` is required, `content_sha256` matched against 64 lowercase hex,
`metadata` required to be a JSON object within `max_metadata_bytes`, `label`
and `created_at` bounded, and `run_id` both validated and required to match the
file name — because a file whose name and id disagree lets whoever can write in
the directory choose a recovery's destination.

## G15 — A staged file the reader then refuses

**Symptom.** `stage()` returns an `Artifact`, the file is on disk, and
`read()`, `pending()` and `recommit()` all refuse it as oversized. The work is
preserved nowhere while looking preserved.

**Cause.** Two bounds that were never reconciled. `max_payload_bytes` caps the
*payload*; `max_artifact_bytes` caps the *file*; and the envelope in between is
larger than either — `indent=2` measured 4.9× the canonical size for a payload
of many small values, which is past the read ceiling's 2× allowance, and
`metadata` was unbounded on top of that.

**Fix.** Bound the inputs and measure the output. `metadata` is capped at
`max_metadata_bytes` and `label` at `MAX_LABEL_CHARS`, both refused before the
root is created. Then the encoded envelope's own byte length is measured: the
readable form is dropped for the compact one when it does not fit, and if that
still does not fit, `stage` raises `StagingFailed` and writes nothing. A
refusal the caller can act on beats a file that cannot be read back.

## G16 — The symlink check that a symlink walks straight past

**Symptom.** None, which is the problem. "Symlinks are never followed" is
asserted by a test that plants a symlink and sees a refusal, and is false in
production against the writer it was written for.

**Cause.** `lstat(path)` then `open(path)` are two separate lookups of one
name. Another process that replaces a regular file with a symlink between them
gets its target opened and read: the check inspected one file, the open got
another. Unlinking the offending symlink afterwards does not help either — the
unlink removes the link, never the file that was already read.

**Fix.** Refuse at the syscall that matters. The file is opened once with
`O_NOFOLLOW`, which fails on a final-component symlink, and with `O_NONBLOCK`,
so a planted FIFO cannot park the reader; type, size and identity all come from
`fstat` on the descriptor that is about to be read. Where `O_NOFOLLOW` does not
exist, an `lstat` before and a `(st_dev, st_ino)` comparison after detects the
swap and says so. The **root's own path** is out of scope and documented as
such: defending a parent-directory swap needs `openat` on a held directory
descriptor. A promise that holds for the final component and not for the root
is worth stating precisely, and worth not overstating.
