# Codebase Cleanup

Measure filesystem weight, prove unused candidates, preserve recoverable evidence and apply only
an explicitly authorized deletion manifest. The executable tool scans metadata and compares
reports; it never deletes project files or executes a plan. Loading or installing the skill grants
no deletion or cloud authority.

## Use

Python 3.11+ standard library only. Install `repository-inspection` using the
[library README](../../README.md). No environment-variable configuration, network access,
or imports from the inspected project are required. From the repository root:

```bash
python -B .github/skills/harness-guide/repository-inspection/tests/filesystem/selftest.py
repository-inventory scan "$PROJECT_ROOT" --group-depth 5 --output "$REPORT_DIR/before.json"
repository-inventory scan "$PROJECT_ROOT" --group-depth 5 --output "$REPORT_DIR/after.json"
repository-inventory compare "$REPORT_DIR/before.json" "$REPORT_DIR/after.json" --output "$REPORT_DIR/comparison.json"
```

`PROJECT_ROOT` is the confirmed directory being measured. `REPORT_DIR` must exist or be creatable
outside it. Use a new report name for each write; existing files are never overwritten. The two
scans bracket separately authorized work, not cleanup performed by the scanner.

## Contract And Limits

| Surface | Contract |
| --- | --- |
| Owner | `repository_inspection.filesystem`; implementation, templates and tests belong to the library |
| Callers | Operators and agents via the public module or `repository-inventory scan` and `compare` |
| Configuration | Explicit root, optional repeated `--exclude`, `--group-depth` from 1 to 8, optional `--output` |
| Inventory | `codebase-cleanup-inventory-v1`: root, scope, totals, groups, measurement time and scan errors |
| Comparison | `codebase-cleanup-comparison-v1`: before/after totals, signed net removals and limits |
| Output | JSON on stdout unless an external, new output file is supplied |
| Exit status | 0 for complete scan/comparison; 2 for partial scans, invalid arguments or refused reports |
| Dependencies | Python standard library; no consuming-application or other capability imports |
| Authorization | Read metadata and write the requested report only; deletion remains a separate operator decision |
| Verification | [Filesystem selftest](../../tests/filesystem/selftest.py); isolated temporary fixtures, positive and refusal paths |

The root `.git` is excluded; hidden/ignored files and nested Git metadata otherwise count.
Symlinks are counted but not followed. Hard-linked names count separately. Bytes are logical file
content, not allocated storage or process RSS. A metadata scan is not an atomic snapshot; stop
concurrent writers before interpreting comparisons. Partial scans cannot be compared.

This package adds a measured filesystem-cleanup workflow and reusable scanner. `protocol-lean`
still owns broader repository-weight surveys, including dependency, CI and infrastructure policy;
`protocol-garbage-collect` still owns reachability-led dead-code removal. Neither protocol is
replaced or copied into another implementation.

## Anonymized Example

Native metadata uses `codebase-cleanup`; the catalogue retains `codebase_cleanup` as an alias.
The inventory implementation, tests and unapproved plan template remain independently usable.

The [case study](references/anonymized-cleanup.md) and
[anonymized catalogue](references/anonymized-cleanup.catalogue.json) preserve historical
measurements and retention decisions. Project names, private paths and original receipt
fingerprints are omitted or generalized. These are not synthetic measurements, results reproduced
by this package, recoverable backups or an executable deletion policy. The
[plan template](assets/cleanup-plan.example.json) starts unapproved and unproven.
Full procedure: [GUIDE.md](GUIDE.md).

## Removal

Removing thin discovery does not remove the library or external reports. Keep reports and
independently created recovery archives until their operator approves removal. Library uninstall
does not remove inspected inputs, credentials, cloud resources or application state.