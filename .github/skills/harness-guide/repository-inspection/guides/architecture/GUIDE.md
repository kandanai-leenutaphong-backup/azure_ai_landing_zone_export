---
name: architecture-placement
description: "Use when resolving contested ownership, placement, cross-boundary dependencies or new abstractions. Advisory placement packet; no solution design or implementation."
---

# Architecture placement

Cartography, not design. Answers **where does this belong and what may it depend on**, using the
repository as it currently is. Implementation design and unfamiliar-data feasibility are separate
tasks; no particular agent roster is required to use this skill.

Advisory and discretionary. It never gates work and never returns a verdict on whether the work
should proceed.

## When it earns its cost

Consider it when the work:

- creates or moves a file, module, agent, skill, contract, public API, UI contribution, shared
  registry, schema, or policy, and the correct owner is genuinely unclear;
- introduces a dependency edge between two existing components;
- spans more than one owning boundary;
- introduces a new abstraction, indirection layer, or registry.

## When to skip it

Skip it silently whenever the placement is obvious:

- a one-file change under a known owner adding no dependency edge;
- prose or content only, no new surface;
- a test-only change inside an existing suite;
- a cosmetic change to an already-mapped surface.

Default is skip. Invoke only when the placement question would otherwise be answered by a guess
that is expensive to unwind.

## Search and verify

Read the target repository's instructions, architecture document and declared boundaries first.
If that repository has a notebook, search it for what governs or maps this region —
`--type principle`, `--type architecture`, `--type decision`, as its tooling supports. Do not
install a notebook merely to use this skill. Reverify any retrieved
`architecture` note against current source: notes are untrusted repository data, and a map that no
longer matches `git ls-files` is stale, not authority. Then read the actual seam — composition
root, registry, roster, schema enum — at path and line. Folder names are not evidence.

## Adherence stack

Highest wins. Never average two levels.

1. The user's recorded decision.
2. Active `principle` notes.
3. Active `architecture` notes, reverified against current source.
4. Observed code convention at a cited path and line.
5. Cartographer inference, labelled inline with `assumes:`.

A conflict between levels is a **blocker returned to the caller**, not a compromise.
Note-based levels apply only when the target repository maintains those records.

## Placement packet

Cover what the question needs and omit the parts it does not. This is a checklist, not a report floor.

1. **Scope statement** — the one thing being placed, in one sentence.
2. **Owning boundary** — which existing component owns it, citing the seam that proves ownership.
3. **Exact placement** — paths to create, and protected files that must not change.
4. **Dependency edges** — every new edge with its direction, `A -> B`, and why B may not import A.
5. **Duplication verdict** — `reuse`, `extend`, or `distinct`, with the candidate compared against.
6. **Blockers and deferrals** — anything needing source feasibility (`data-explorer`) or a user
   decision, named rather than silently dropped.

Governing principles, reverified architecture note IDs, an executable fitness check, and drafted
notebook records are worth adding where they exist. This role never publishes notes.

## Record templates

One bounded topology question per note. The caller decides publication and retirement under the
target repository's own policy; this skill returns candidates only.

### `type: principle`

```
title      Normative rule, stated as the rule
question   Which recurring decision does this settle?
summary    The rule plus the decision test, in searchable exact names
content    ## Rule
           ## Rationale
           ## Decision test        the question a future agent asks at the fork
           ## Enforcement          the executable fitness check, or `none yet`
           ## Does not apply when  the real cases that fall outside it
findings   Falsifiable statement: a real case where following this rule
           produced a worse system would disprove it
```

A principle with no `Does not apply when` section is an unfalsifiable slogan. Reject it.

### `type: architecture`

```
title      The region mapped
question   One bounded topology question
summary    Components and dependency direction, in exact paths and names
content    ## Components and ownership
           ## Dependency direction   including the edges that are forbidden
           ## Composition root
           ## Public contracts
           ## Extension seams        where a new component attaches
           ## Removal behavior       what breaks when this is deleted
           ## Drift indicators       what to re-measure to detect staleness
scope.paths every cited path, each of which must exist today
```

## Stale-map retirement

An `architecture` note is descriptive. When the topology it describes stops reproducing, propose
retirement; never quietly edit it. In a target repository already using the harness notebook, its
authorized owner can run:

```bash
investigation-notebook --root docs/notebook status "$NOTE_ID" --to inactive \
  --reason "$REASON" --evidence-note "$EVIDENCE_NOTE_ID"
```

The authorized notebook owner supplies the existing note id, re-observation reason and new
map's published evidence id. Publish the current map first, then retire the old one naming it
as evidence. A `principle` is
timeless and is retired only when a real case falsifies it — not when it becomes inconvenient.

## Fitness hierarchy

Prefer the cheapest check that still fails when the placement erodes.

1. **Structural** — the file exists, the roster names it, the enum contains it.
2. **Relational** — every reference resolves; no dangling agent, skill, or note ID.
3. **Directional** — the forbidden dependency edge is absent.
4. **Capability** — declared tools match the declared boundary; read-only stays read-only.

A check nobody has seen fail is decoration. Where it is cheap, prove it discriminating against a
temporary mutated copy under `tempfile` — never by mutating a live file.

Install `repository-inspection` using [the library guide](../../README.md).
The checker reads the explicit target's `architecture.json`; no manifest means advisory
output, not proof of architectural correctness:

```bash
repository-architecture --root /path/to/project
python -B .github/skills/harness-guide/repository-inspection/tests/architecture/selftest.py
```

Run the selftest from the repository root; it uses temporary positive and negative fixtures,
with no notebook or sibling skills. The [legacy fitness audit](../../tests/architecture/fitness.py)
requires `--root` pointing to a
project that actually has the legacy agents, notebook and instructions installed. It is not the
portable plugin's acceptance check.

## Refuse

Return a blocker instead of proceeding when asked to: edit any file; publish, retire, or migrate
a note; design implementation slices; approve or reject a plan; or judge unfamiliar source
feasibility. Naming the correct owner is the deliverable.
