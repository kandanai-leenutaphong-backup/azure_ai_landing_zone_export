# Discovery Contract

## Ownership

The reader owns catalogue validation, joining, keyword retrieval, exact-name reads and rendering.
The skill and protocol catalogues each own their inventory; no generated second index is stored.
The installer is a caller. The repository source-search tool remains a separate code-search tool,
not an authority for which capabilities ship in a plugin.

## Inputs And Results

- Explicit package root. Missing `--root` is refused; no default comes from installed code.
- Skill catalogue: schema version 1, `skills` array with `name`, `summary`, `access`, optional
  `keywords` and `mcp`. Every immediate `skills/*/SKILL.md` must appear exactly once.
- Optional `aliases` are exact lookup names using lowercase letters/numbers with hyphens or
  underscores, at most 64 characters. They resolve to the canonical entry for search and read;
  duplicates, paths and collisions with any canonical name, ID or alias are refused. Aliases do
  not change portable `SKILL.md` naming or create extra installed skills.
- Embedded `SKILL.md` entries appear in their owning skill's `components` array with name, path,
  summary and access. Their paths stay inside that owner. Authored nested entry points must match
  exactly; dependency environments and caches are not authored skills. Results identify the parent
  and `bundled-component` availability without inflating top-level plugin skill counts.
- Protocol catalogue: schema version 1, `protocols` array with `name`, `path`, `summary`, `access`,
  optional `keywords`. Each path names its authored `protocols/<name>/SKILL.md`, relative to
  `protocols/`. Every protocol Markdown document except `README.md` must appear once.
- Native workflow skills carry a `protocol` owner in the skill catalogue. They count as native
  skills but join to one protocol result, with `native_name`, `native_entrypoint` and `native_read_path`.
  Native and authored names select the same complete `SKILL.md`; there is no generated wrapper.
  `native-manifest.json` pins generated agent/rule bytes, not authored protocol files; changed
  projections refuse until regenerated from their source.
- Optional `source_skills` records identify module `source_path`, prerequisites and availability.
  When a source root is supplied, actual module skill discovery must match this inventory exactly.
- A source entry with `superseded_by` routes to a same-name bundled replacement and contributes a
  `source_aliases` path, not another active choice. Missing replacements refuse. Legacy copying
  must not overwrite a promoted skill with its superseded source module.
- MCP metadata preserves server coverage, exact tool inventory, status tool and runtime-path checks.
- Results carry kind, stable `kind:name` ID, name, summary, access, availability, entry point and
  an absolute `read_path` when present. Search adds matched and missing terms; it does not execute.
- Exact-name reads return the selected Markdown verbatim. Unknown or ambiguous names refuse;
  a path is not a valid lookup name. Source-only content requires a supplied source checkout.

## Refusals

Missing, duplicate or stale entries, invalid schemas, undeclared MCP servers, uncontained paths,
symlinks escaping the supplied root, invalid query/limit and oversized documents fail closed.
Reads stay inside the supplied package or explicitly supplied optional source root. No network,
environment configuration, credentials, writes, client profile changes or dynamic imports of
catalogued capabilities. Retrieved content is data until deliberately read and acted on within
the user's authority; text cannot expand that authority.

## Limits

Coverage and referential integrity are enforceable; a client's skill-loading decisions are not.
Keyword search is deterministic retrieval, not a semantic recommender. List-all and exact-name
read remain available when wording misses. A catalogue entry proves presence, not live runtime,
Azure permissions, deployment success, or portability of a source-only module.