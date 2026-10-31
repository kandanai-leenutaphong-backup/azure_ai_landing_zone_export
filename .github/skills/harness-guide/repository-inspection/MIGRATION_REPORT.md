# Bounded Capability Migration

Status: local bounded migration verified. Root enrollment, generated portable discovery,
shared MCP registration and consuming-project integration remain parent-owned.
This is not a claim that the complete unified-library specification is finished.

## Source Ownership

The frozen owned inventory contains 91 original source/guidance/test/metadata files:
89 moved to canonical libraries and two automatic environment bootstraps retired.
Each of the six former skill roots now contains only its native `SKILL.md` file;
all six names and descriptions match the original metadata exactly. Entries are
11-22 lines. This is a scoped result, not a new portfolio baseline measurement.

Exact original paths, final paths, retirements and original SHA-256 values:

- [Composition manifest](../app-composition/MIGRATION.json): 27 original records.
- [Recovery manifest](../recoverable-jobs/MIGRATION.json): 30 original records.
- [Notebook manifest](../investigation-notebook/MIGRATION.json): six original records.
- [Inspection manifest](MIGRATION.json): 28 original records across three skills.

Retired original bootstraps:

```text
.github/skills/portable-app-composition/scripts/serve_mcp.py
.github/skills/recoverable-jobs/scripts/serve_mcp.py
```

Their replacements are explicit installed entrypoints `appcompose.mcp:main` and
`workrecovery.mcp:main`, not automatic dependency installers. CLI/MCP implementation
formerly in source scripts now lives in each package's `cli.py` and `mcp.py`.
The manifests also list six retired library-local launcher paths.

All six original license files were checked against their original source hashes.
Historical guidance, fixtures, cleanup evidence and provenance were retained.
No user notes, notebook database, pending job output or recovery root was moved.
[Generated-artifact receipt](GENERATED_ARTIFACTS.json) records 10 generated build
directories containing 65 files moved into the private temporary evidence area,
plus six retired launcher residues preserved there without deletion. During that
build-artifact move, all 29 canonical runtime/resource files remained byte-identical.

## Public Contracts

Requirements below identify local distributions/artifacts; registry publication was not performed.

| Root Requirement | Library Root | Public Import | Runtime Dependencies |
| --- | --- | --- | --- |
| `portable-app-composition==1.1.0` | `libraries/app-composition` | `appcompose` | `PyYAML>=6.0`; Python >=3.11 |
| `recoverable-jobs==1.0.0` | `libraries/recoverable-jobs` | `workrecovery` | None; Python >=3.10 |
| `investigation-notebook==0.1.0` | `libraries/investigation-notebook` | `investigation_notebook` | None; Python >=3.10 with SQLite FTS5 |
| `repository-inspection==0.1.0` | `libraries/repository-inspection` | `repository_inspection.architecture`, `.catalogue`, `.filesystem` | None; Python >=3.11 |

All four use `setuptools>=68` as their declared build backend requirement.
Composition and recovery each declare optional `mcp` dependencies:
`mcp>=1.27.1,<2` and `pydantic>=2`. Composition's `dev` extra is `uvicorn>=0.30`;
recovery's is `pytest>=8`. No child metadata contains an unresolved workspace dependency.

Installed console entrypoints:

```text
appcompose-inspect       appcompose.cli:main
appcompose-mcp           appcompose.mcp:main
workrecovery            workrecovery.cli:main
workrecovery-mcp         workrecovery.mcp:main
investigation-notebook  investigation_notebook:main
repository-architecture repository_inspection.architecture:main
repository-catalogue    repository_inspection.catalogue:main
repository-inventory   repository_inspection.filesystem:main
```

Core composition and recovery APIs retain their existing import names and behavior.
Notebook exports the existing `InvestigationNotebook` class, `NotebookError`,
`SCHEMA_VERSION`, `load_schema`, `validate_note`, `scan_sensitive` and `main`.
Its CLI requires `--root`; schema data stays in the installed package, not copied
beside notes. Existing note formats remain readable; no corpus migration was run.

Inspection retains separate engines: architecture `check`/`hotspots`, catalogue
`capability_catalogue`/`report`/`search`, filesystem `scan`/`compare`/`write_report`.
Catalogue requires an explicit root and retains the validated v1 metadata reader;
it installs no catalogue and executes no selected entry. Inventory never deletes inputs.

Installed MCP modules expose composition `Settings`, `validate`, `demo`, `serve`
and recovery `Settings`, `RecoveryTools`, `serve`. Selected tool names are
`composition_status`, `composition_validate`, `composition_demo`, `recovery_status`,
`recovery_stage`, `recovery_list`, `recovery_read`. Old tool-name aliases are not advertised.
Installation starts no server and grants no access. Recovery grants remain separate
and false by default; staging never claims a destination-store commit.

## Executed Verification

Environment: Linux, CPython 3.11.14. Dependencies resolved offline from existing cache.
Commands below run from the indicated library directory after installation into the
isolated interpreter. No existing project environment was modified.

| Owner | Check | Observed Result |
| --- | --- | --- |
| Composition | `python tests/selftest.py` | 61/61, before and after relocation; lifecycle, rollback, ownership, parser and ASGI refusals retained |
| Composition | `python tests/mcp_smoke.py` | PASS, real SDK stdio validation, fixed demo lifecycle and malformed/oversized/executable-field refusals; repeated from clean wheels |
| Composition | `appcompose-inspect` valid YAML and invalid executable-field document | Canonical output succeeds; invalid document exits 1 |
| Recovery | `python tests/selftest.py` | 26/26, before and after relocation |
| Recovery | `python -m pytest tests -q -p no:cacheprovider` | 67/67, final run under inherited restrictive umask |
| Recovery | `python tests/mcp_smoke.py` | PASS, real SDK grant refusal, stage/restart/read, no-clobber, traversal, size, corruption and unavailable deletion; repeated from clean wheels |
| Notebook | `python tests/selftest.py` | Original eight checks pass; installed version passes 10/10 without copied mechanism/schema files |
| Notebook | `python -m unittest discover -s tests -p 'test_*.py' -v` | 7/7: persistence, duplicate/secret refusal, corruption retention, status refusal and required root |
| Inspection | `python tests/architecture/selftest.py` | PASS: permitted graph, five negative fixtures and isolated CLI checks |
| Inspection | `python tests/filesystem/selftest.py` | 8/8, before and after relocation |
| Inspection | `python tests/catalogue/selftest.py` | Original 14/14; installed version 15/15 including implicit-root refusal |
| Inspection | `python examples/inspect_repository.py` | PASS across all three public modules |
| Composition/recovery | All nine retained standalone examples with `python -I -B` from a temporary working directory | 9/9; examples no longer inject source paths |
| All four | First Python example in each README | 4/4 |
| All four | Wheel build, archive inspection and installation into a second fresh environment | Four wheels installed; notices/resources present; no skill source, user notes, drafts or database in archives |
| All four | [Installed-profile acceptance](tests/installed_profile.py) | PASS with `PYTHONPATH` unset and checkout/network access denied; all observed capability modules loaded from temporary site-packages |
| All four | Installed console `--help` checks | 8/8 |
| Scoped source | Exact original hashes, final paths and native metadata comparison | 91 source records validated; six unchanged licenses; six discovery-only skill roots |
| Runtime source | AST/path inspection of 27 Python files | No skill-source references, `sys.path` injection or checkout module loaders |

Observed failures were resolved, not omitted:

- Initial recovery permission assertion depended on shell umask `022`, while inherited
  umask was `077`. The test now sets/restores its own umask; production permissions are unchanged.
- Two new notebook assertions omitted the existing `show()` annotation
  `category: "uncategorized"`. Corrected expectations; no mechanism behavior changed.
- Recreated launcher paths retained stale editor-buffer bodies, and editor deletion reports
  did not remove files on disk. Public CLI tests exposed the syntax defect. Source launchers
  were retired and moved through guarded filesystem operations, then absence was read back.
- An initial attempt to install the additional `wheel` distribution could not resolve offline.
  The cached declared setuptools backend built all four wheels without that extra package.

## Parent Integration And Limits

- Enroll the four roots/dependencies in the root library project and its lock through the
  parent's integration change. Root package metadata and external locks were not edited here.
- Regenerate the canonical catalogue/native projection and reconcile shared MCP registration,
  packaging and installer callers. Workspace skill links intentionally remain local for now.
- Replace the duplicate [tool-level architecture checker](../../.github/tools/arch.py)
  with the installed API. Twelve engine functions, including `check` and `hotspots`, remain
  AST-identical to the new owner; this protected file was read, not modified.
- Reconcile out-of-scope consumers/instructions that still invoke copied notebook mechanisms
  or removed skill scripts. No installed notebook or user corpus was changed.
- The source-only legacy architecture fitness audit was retained but not run: it requires
  the old roster/copied-notebook installation and is not current package acceptance.
- No network/cloud service calls, resource changes, real HTTP loopback test, deployment,
  release publication, root integration, generated plugin acceptance, or non-Linux/Python
  runtime verification was performed. No agents, commits or user-data deletion were used.
- The referenced architecture overview was absent. Explicit user ownership and the governing
  core/chapter-04 specification controlled placement; no speculative boundary manifest was added.

Raw wheel/source/import/example/CLI receipts are retained under
`/tmp/agentcraft-migration.fTQyVn/`; [verification record](MIGRATION_VERIFICATION.json)
contains their structured results. Temporary artifact paths are evidence, not release URLs.
Migration manifests/report are the durable record; no out-of-scope notebook note was created.