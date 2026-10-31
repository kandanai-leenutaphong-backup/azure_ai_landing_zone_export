# Harness Guide

Local discovery for the complete skill and protocol package. Python 3.11+, standard library only.
No account, MCP daemon, model call, network access, or client settings change.

Install `repository-inspection` using [the library README](../../README.md).
Supply the catalogue package root explicitly:

```bash
repository-catalogue --root /path/to/catalogue-package --find "remove dead code" --json
repository-catalogue --root /path/to/catalogue-package --show protocol-garbage-collect
repository-catalogue --root /path/to/catalogue-package --list --kind protocol
repository-catalogue --root /path/to/catalogue-package --check
python -B .github/skills/harness-guide/repository-inspection/tests/catalogue/selftest.py
```

No default root is inferred from the installed code or the caller's working directory.
The package ships no catalogue or skill runtime. Its selftest uses temporary metadata and
the installed API/CLI; it needs no sibling checkout.

Run the source selftest from the repository root. The v1 inputs are
`${CATALOGUE_ROOT}/skills/catalogue.json` and `${CATALOGUE_ROOT}/protocols/catalogue.json`,
relative to the supplied package. [Workspace discovery](../../../../../../libraries/README.md#discovery-and-mcp)
owns the generated projection and explicit external export.
Optional module metadata lives in the skill catalogue's
`source_skills` array; those entries are not silently included in plugin skill counts.
Promoted source entries use `superseded_by` and route to their bundled owner without a duplicate
result.
Exact `aliases` support requested names such as `ghcp_cli_frontend` while the portable skill remains
`ghcp-cli-frontend`. Both search and `--show` resolve that name without duplicating the capability.
Embedded skill entries live in their parent's `components` array and are discoverable without
being counted as separate plugin installs.
Use `--source-root` only to inspect a deliberately supplied repository containing those modules.

`--list`, `--find QUERY`, `--show NAME`, and `--check` are mutually exclusive. `--kind skill|protocol`
filters listing/search. `--json` returns structured results. `--limit` bounds search results to
1-50. Empty queries, unknown names, invalid catalogues, and escaping paths exit nonzero.
An unmatched nonempty query returns zero matches and an explicit full-list fallback, not a guess.

The Python API is [repository_inspection.catalogue](../../src/repository_inspection/catalogue.py): `skill_catalogue`,
`protocol_catalogue`, `capability_catalogue`, `search`, `report`, and `print_report`.
Host installers should call these functions, not a removed skill script. See [CONTRACT.md](CONTRACT.md) for invariants and
[GOTCHAS.md](GOTCHAS.md) for limits.