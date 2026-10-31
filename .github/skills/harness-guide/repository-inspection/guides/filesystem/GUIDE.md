---
name: codebase-cleanup
description: 'Use when a workspace has excessive files, stale artifacts, duplicate restore trees, unused research mirrors, or editor indexing and memory pressure, and the user asks for aggressive codebase cleanup. Measure first, prove candidates unused, protect data and user changes, capture recoverable evidence, delete only an authorized frozen manifest, validate the app, and prevent regrowth. Not permission to delete canonical data, security controls, backups, dependencies in use, or cloud resources.'
---

# Codebase Cleanup

Reduce filesystem weight without breaking the application or erasing work the user asked to keep.
Optimize the requested problem: file count for indexing, bytes for storage, stale references for
attention. A smaller directory does not prove lower process RSS; report RAM only when measured.

The native skill name is `codebase-cleanup`. The harness catalogue also resolves the source name
`codebase_cleanup` to this entry; there is no second implementation. The installed
`repository_inspection.filesystem` module owns inventory and comparison.

## Resources

- [Usage and integration](README.md): dependencies, public CLI, ownership and removal.
- [Failure modes](GOTCHAS.md): incomplete scans, counting scope and report refusal.
- [Anonymized case study](references/anonymized-cleanup.md): what was purged, retained and verified.
- [Anonymized historical catalogue](references/anonymized-cleanup.catalogue.json): all 335 recorded path groups, protections and follow-up edits with generalized names and no source-receipt fingerprints. Never use these example paths as a deletion policy.
- [Plan template](assets/cleanup-plan.example.json): evidence and approval fields, not a ready-to-run delete list.
- [Read-only inventory tool](../../src/repository_inspection/filesystem.py): streaming metadata scan and same-scope comparison, Python 3.11+ standard library only.
- [Inventory tests](../../tests/filesystem/test_inventory.py): links, hidden files, empty directories, errors, comparisons and non-overwriting reports.
- [Self-test](../../tests/filesystem/selftest.py): runs the retained tests against the installed library.

The case study is historical evidence, never authorization to delete the same paths elsewhere.
The skill runs no deletion automatically. Do not start a cleanup merely because this skill loaded.

## 1. Establish Scope and Protection

1. Read the request, repository instructions, architecture and existing cleanup decisions.
   Use the project's normal notebook or decision log if present; do not introduce one just for cleanup.
2. Record worktree status and current commit without resetting, stashing, staging or committing.
   Existing user edits and nested repositories are protected until examined.
3. Declare the protected set: runnable source and assets, tests, guards, schemas, migrations,
   canonical inputs, required build/rebuild sources, active dependencies, credentials, accepted
   outputs, original trust hashes and any promised backup or reproduction bundle.
4. Identify active writers. Inspect process identity and working directory without printing
   command-line secrets or environments. Do not remove a live database, cache or dependency tree
   while an application, watcher, restore job or measurement is using it.
5. Limit the scope to filesystem cleanup unless cloud operations are separately authorized.
   A stale screenshot does not authorize teardown; a large raw dataset does not become disposable.

Choose acceptance commands before editing. Use the cheapest checks capable of disproving that
the chosen paths are unused, plus the real application journey affected by the removal.

## 2. Measure Before Searching Contents

- Count regular files, directories, symlinks and logical file-content bytes by subtree. Include
  ignored/hidden directories intentionally; Git-tracked counts alone miss caches and mirrors.
- Exclude the root Git object store and never follow symlinks. Record the exact exclusions,
  timestamp, errors and counting rules. Count hard-linked names separately when reporting logical
  file bytes; do not call that filesystem space reclaimed.
- Stream directory metadata and aggregate counts. Do not read every file, print every path, load
  a million-file list into memory or start a full-repository language-server scan.
- Sort the aggregates by both file count and bytes. A few huge archives and a million tiny JSON
  files cause different problems. Measure the application subtree separately from the repository.
- Put receipts, scratch restores and optional archives outside the indexed workspace. Keep only
  compact durable documentation inside it. Reuse measured aggregates instead of rescanning for each question.
- An unreadable directory, symlink or changed input is an explicit unknown, not a zero-sized pass.

Install `repository-inspection` using [the library README](../../README.md).
Run from the repository being assessed, with an explicit target and external reports:

```bash
ROOT="$PWD"
REPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codebase-cleanup.XXXXXX")"
repository-inventory scan "$ROOT" --group-depth 5 --output "$REPORT_DIR/before.json"
```

The scanner reads metadata only and uses one iterator per directory depth, not one list of every
file. Directory-group depth is capped; scan depth is not. Nested Git metadata is counted unless
explicitly excluded, matching the original case study's root-Git-only convention. `--exclude`
accepts relative `fnmatch` patterns; a matched directory is skipped entirely. Do not exclude the
largest suspect tree just to make the baseline look small. Reports refuse existing output files
and destinations inside the measured root. Scan errors produce a partial report and exit 2;
comparisons refuse partial inventories. Quiesce concurrent writers for meaningful measurements.

## 3. Prove Each Candidate

For each candidate, inspect direct imports, dynamic/string-based loads, registries, entry points,
tests and fixtures, configuration, build/package manifests, deployment scripts and CI. Step from
wiring to the implementation that decides whether the path is used. Search only first-party
surfaces; do not grep the entire suspect mirror for references to itself.

| Candidate | Proof needed before a deletion verdict |
| --- | --- |
| Legacy docs/reference copies | No current caller or operator entry point; valuable findings captured; current references redirected; provenance and license notices retained. |
| Screenshots/build outputs | Producer is known, outputs are reproducible, and no runtime or acceptance contract reads the existing copy. |
| Restore-test copies and trial bundles | No active process; canonical source/data and one verified complete preservation package survive outside the deletion set. |
| Per-case or other generated caches | Owning builder recreates a missing cache from retained inputs; prove regeneration in a temporary directory. |
| Installed dependencies | Identify the owning app and its package lock, tests and active process. Remove an abandoned app's install tree only; keep the running app's dependencies. |
| Acquired mirrors | Resolve actual source selectors and source pins. Preserve every required mirror, canonical dataset and modified nested repository. A URL alone does not guarantee future recovery of the same revision. |
| Apparently dead code | Prove unreachable across all the surfaces above. Test-only, migration-only and failure-path consumers are still consumers. |
| Existing environments | Check configured interpreter/tooling and processes. An unfamiliar environment is not proof of non-use. |

For every nested Git checkout in a proposed removal, inspect `git status --porcelain` including
untracked files without refreshing or checking out anything. Local changes, unknown status or
unresolved consumers mean `keep`. Inspect ignored generated versus user-owned content separately;
a clean root worktree says nothing about a nested checkout's untracked data.

Use these verdicts: `delete` (proven unused), `capture` (preserve knowledge then delete), `keep`
(load-bearing), `unproven` (retain), or `revive` (separate work, not a cleanup side effect).
Never relabel an unknown as dead to reach a target percentage.

## 4. Capture and Freeze the Manifest

- Record each repository-relative path, reason, evidence for every reachability surface, measured
  counts, recovery method and acceptance check. Distinguish an empty directory from an unmeasured one.
- Separate payload recovery from provenance recovery. An archived reference tree can be restored;
  resource URLs, commit IDs and hashes alone cannot restore deleted payloads offline.
- Verify archives against the source before removal, and verify retained reproduction bundles
  against the previously recorded trusted digest. Do not replace a trust hash to make a check pass.
- Preserve locally useful notes in the existing durable record. Use a private external archive
  when retaining the expanded files would reproduce the indexing problem. Never copy credentials
  or raw sensitive telemetry into a shared skill, note or source-controlled manifest.
- Present the exact deletion groups, blast radius, recovery limits and retained exceptions.
  Obtain explicit authorization for that set unless the user's request already unambiguously
  grants it. If the set grows or the consequences change, stop for new approval.
- Freeze the approved manifest. One owner writes each path. Narrowing the set for safety is
  allowed; opportunistic additions are not. No commits or branches unless separately requested.

## 5. Remove Bounded Batches and Validate Immediately

1. Recheck that inputs and active writers have not changed since discovery. Review symlinked
   ancestors, mount points and nested working changes; stop on an unexpected state.
2. Resolve each explicit relative candidate under the confirmed repository root. Refuse the root,
   filesystem root, traversal, symlink traversal, protected paths and any ancestor/descendant
   overlap with protected content. Never build destructive commands from raw search results,
   untrusted metadata or unconstrained glob expansion.
3. Delete the first coherent group using the repository's allowed file tools. Bulk removal may
   use a fixed manifest and guarded filesystem APIs. Do not shell-evaluate file names.
4. Check every intended path is absent and protected paths still exist; save a batch receipt.
5. Immediately run the agreed behavior-scoped check before another deletion or adjacent edit.
   If it fails, restore the affected recoverable batch, record the missed consumer, repair the
   same slice and rerun. If recovery is unavailable, stop and report the blocker.
6. Continue only through the approved set. Do not delete test/security coverage to make acceptance green.

## 6. Prevent Regrowth and Reconcile the Project

- Move scratch screenshot and restore defaults outside the workspace, using configurable
  temporary locations. Keep accepted artifacts where the user expects them.
- Merge narrow editor watcher/search exclusions for raw data, caches and dependency installs;
  do not replace the user's settings or hide application source. Exclusions reduce indexing;
  they neither delete files nor prove memory improvement.
- Check test discovery, search tools, bundlers and architecture tools independently. `.gitignore`
  is not a universal scanner exclusion. Declaring an architecture owner does not stop scanning it.
- Update active instructions, boundary manifests, registries, runbooks and references to retired
  paths. Mark historical provenance as historical instead of falsifying it or erasing licenses.
- Preserve current API behavior and frozen experimental records. Do not regenerate model results,
  drop recorded errors or change authentication while validating cleanup.
- Update the root README only when its project-state claims changed. Keep the result concise.

## 7. Close With Evidence

Run required checks in proportion to the removal: retained-input rebuild dry runs, cache regeneration,
focused tests, production build, saved-artifact hash/readback and the real app journey. Report existing
warnings and unresolved imports separately. Do not start a new expensive model run to replay saved results.

Measure again with the same exclusions and counting rules. Report net change, remaining files,
application-subtree change, new files created by checks, and measurement timing. Logical bytes,
allocated disk space and process memory are different metrics. No measurement means `unknown`.

After the approved cleanup and its acceptance checks, using the same root and report directory:

```bash
repository-inventory scan "$ROOT" --group-depth 5 --output "$REPORT_DIR/after.json"
repository-inventory compare "$REPORT_DIR/before.json" "$REPORT_DIR/after.json" --output "$REPORT_DIR/comparison.json"
```

The comparison requires identical roots and counting scope. It reports net additions as negative
removals, never clamps them away. It does not perform cleanup or validate the deletion manifest.
To verify the installed tool from the library directory:

```bash
python tests/filesystem/selftest.py
```

Close the existing work record if used. Give the user:

- Removed categories and exact manifest location, not a million-path response.
- Before/after counts and measured byte reduction, with the metric definition.
- Protected outputs, required sources and modified/unproven items deliberately kept.
- Tests/build/journey results and any unverified areas.
- Recovery location and limits; reacquisition is not an offline backup.
- Recurrence-prevention changes. Suggest editor reload only to discard old indexes, not as
  proof that a memory leak was fixed.

Stop after the declared acceptance passes. Do not turn a successful cull into an unrequested
rewrite of architecture, dependency policy or infrastructure.