# Codebase Cleanup Failure Modes

## G1 - Partial scan is not an empty tree

**Symptom:** Scan exits 2 with `complete: false` and a nonzero `error_count`.

Unreadable or changing entries produced a partial report. Resolve permissions or concurrent
writers, then scan to a new external report. Comparison refuses incomplete inventories; do not
treat missing measurements as proof that a directory is empty or disposable.

## G2 - Comparison refuses different roots or counting scope

**Symptom:** `compare` reports `Comparison requires identical roots and counting scope`.

Use the same resolved root, exclusion patterns and counting rules for both scans. Do not remove
large trees from the second scan's scope to manufacture a reduction. A negative net removal means
files were added or regenerated; it is not clamped to zero.

## G3 - Report output is refused

**Symptom:** A report inside the measured root or at an existing output path exits 2.

Choose a new file outside the measured workspace. This keeps reports out of measured totals and
preserves earlier evidence. Parent directories may be created, but existing reports are not replaced.

## G4 - File bytes disagree with disk usage or memory

**Symptom:** Inventory totals do not match allocated disk blocks or editor process RSS.

The tool counts logical regular-file bytes, including each hard-linked name. It does not follow
symlinks, measure allocated storage or inspect memory. Root Git metadata is excluded while nested
Git metadata counts unless explicitly excluded. Report other metrics only when separately measured.

## G5 - Historical paths are mistaken for an approved plan

**Symptom:** A proposed deletion list is copied from the bundled source-era catalogue.

Historical evidence is not authorization or reachability proof for the current project. The example
plan starts `approved: false` with `unproven` candidates. Prove current consumers, protect user changes
and data, verify recovery and obtain approval for the exact current set. The scanner executes no plan.