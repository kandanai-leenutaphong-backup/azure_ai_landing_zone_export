# Repository Inspection

One distribution, three distinct modules. Python 3.11+, standard library only.
No generic execution engine, network service, implicit repository root, or cleanup operation.

```bash
python -m pip install ./.github/skills/harness-guide/repository-inspection
```

Run from the repository root with the caller's chosen environment. Distribution
`repository-inspection`; public imports:

```python
from repository_inspection import architecture, catalogue, filesystem
```

| Module | Public Operations | State And Authority |
| --- | --- | --- |
| `architecture` | `check(root)`, `hotspots(root, limit=15)`, `ArchError`, `main(argv)` | Reads one explicit repository and its `architecture.json`; no manifest is advisory, not verified correctness. |
| `catalogue` | `capability_catalogue(package, source_root=None)`, `report(...)`, `search(entries, query, limit=5)`, `main(argv)` | Reads validated catalogue metadata and contained Markdown documents; never imports or executes selected entries. |
| `filesystem` | `scan(root, group_depth=4, exclude=())`, `compare(before, after)`, `write_report(report, output=None)`, `main(argv)` | Reads metadata without following child symlinks. An explicit report output must be new and outside the scanned root. Never deletes inputs. |

## CLI

```bash
repository-architecture --root /path/to/project --json
repository-catalogue --root /path/to/catalogue-package --find "dead code" --json
repository-catalogue --root /path/to/catalogue-package --show protocol-garbage-collect --json
repository-inventory scan /path/to/project --output /tmp/new-inventory.json
repository-inventory compare /tmp/before.json /tmp/after.json
```

The equivalent module entrypoints are `python -m repository_inspection.architecture`,
`python -m repository_inspection.catalogue`, and `python -m repository_inspection.filesystem`.
Architecture and catalogue require `--root`; inventory requires its positional root.
No root is discovered relative to this installation or supplied through hidden environment state.

The catalogue reader retains the validated v1 package format beneath the explicit root:
`${CATALOGUE_ROOT}/skills/catalogue.json`, `${CATALOGUE_ROOT}/protocols/catalogue.json`,
registered Markdown paths, and optional integrity/MCP metadata.
It installs no catalogue and downloads no missing entries. A missing, stale, oversized,
escaping or inconsistent document refuses. An explicit `--source-root` is required for
reviewed source-only entries. The [canonical catalogue](../../../../libraries/capabilities.json) generates
discovery projections; this package reads them and does not author a second registry.

## Example And Checks

After installation, run from this library directory:

```bash
python examples/inspect_repository.py
python tests/architecture/selftest.py
python tests/filesystem/selftest.py
python tests/catalogue/selftest.py
```

The example calls all three public modules with temporary synthetic inputs, including
a forbidden dependency and net file additions. Tests retain graph ownership/cycle/public
surface refusals, missing-import reporting, catalogue aliases/staleness/traversal/symlink
guards, partial-scan refusal, logical hard-link counts, and non-overwriting external reports.

Architecture uses bounded static import resolution, not Python execution or whole-program
proof. Filesystem inventory is streaming but not an atomic snapshot or a scan-time quota;
quiesce writers and supply a bounded target. Logical bytes are not allocated disk or RAM savings.
Hosts own authorization, concurrent writers, and every destructive decision.

## Guidance And Integration

- [Architecture placement](guides/architecture/GUIDE.md), [limitations](guides/architecture/GOTCHAS.md).
- [Filesystem cleanup procedure](guides/filesystem/GUIDE.md), [inventory limits](guides/filesystem/GOTCHAS.md).
- [Catalogue discovery](guides/catalogue/GUIDE.md), [catalogue contract](guides/catalogue/CONTRACT.md).
- [Exact source migration paths and original hashes](MIGRATION.json).
- Original licenses: [architecture](guides/architecture/LICENSE), [filesystem](guides/filesystem/LICENSE), [catalogue](guides/catalogue/LICENSE).

This distribution is enrolled in the [shared workspace](../../../../libraries/README.md#installation).
The framework's `tooling` extra exposes installed catalogue lookup. The
[workspace guide](../../../../libraries/README.md#discovery-and-mcp) owns regeneration/export; editor
registration is an operator decision, never activated by this package.

The retained [legacy fitness audit](tests/architecture/fitness.py) is source-only historical
coverage for projects with the old roster and copied-notebook installation. It is not
installed, not modern package acceptance, and not evidence that the current host is integrated.