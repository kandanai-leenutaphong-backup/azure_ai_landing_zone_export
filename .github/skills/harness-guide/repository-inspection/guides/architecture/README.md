# Architecture placement

Advisory ownership and dependency analysis, with a bundled standard-library checker.
The skill returns a placement packet; it does not implement the proposed change or authorize it.

## Use and verification

Install `repository-inspection` as described in the [library README](../../README.md).
Python 3.11+ is required. From the repository root:

```bash
python -B .github/skills/harness-guide/repository-inspection/tests/architecture/selftest.py
repository-architecture --root /path/to/project
```

The checker reads the target's `architecture.json` and Python/JavaScript/TypeScript imports.
It reports overlapping ownership, undeclared edges, cycles and private-surface imports. Missing
or empty boundaries are advisory. Unresolved imports and unowned sources are reported, not proven.
It performs no writes to the target repository and requires no notebook, sibling skill or agent.

The [legacy fitness audit](../../tests/architecture/fitness.py) preserves the optional
source-only legacy harness audit. It requires an actual legacy installation and is not
the installed library's acceptance gate.

## Dependency and provenance

Historical origin: workflow, legacy fitness and checker paths are preserved in the
migration manifest, not advertised as current source files.
The current owner is [repository_inspection.architecture](../../src/repository_inspection/architecture.py).
The [migration manifest](../../MIGRATION.json) records the exact transfer and original hashes.
The library does not import repository tool wrappers; consumers call the public API.

Selftests create temporary repositories and verify a permitted graph and matching negative
cases. They do not establish architectural correctness of a consuming project. No runtime state,
MCP server or installation hook is introduced.

## Removal

Removing thin discovery does not uninstall the library. Uninstall `repository-inspection`
only when its callers no longer need it. Target repositories, manifests and notebook records
remain unchanged.