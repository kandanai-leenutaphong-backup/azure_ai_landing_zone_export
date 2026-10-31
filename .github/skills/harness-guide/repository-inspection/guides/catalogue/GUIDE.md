---
name: harness-guide
description: "Find the right harness skill or protocol before starting unfamiliar work. Use for onboarding a new project, listing available capabilities, choosing a workflow, or requests involving modularization, legacy migration, dead-code cleanup, documentation, regression verification, demonstrations, durable notebook findings, Azure data/models, deployment, authentication, frontend work, or UI audits. Searches a validated local catalogue and returns exact entry points; no MCP server, network lookup, or special agent is required. Read the selected entry before acting."
---

# Harness Guide

Optional lookup and diagnostics beside native skill discovery. Find the existing capability before
inventing a workflow or implementing another copy; this guide is not a mandatory gateway.
The catalogue distinguishes executable/domain **skills** from procedural **protocols** and
source-only optional skills. A match is a candidate, not authorization or proof of suitability.
Embedded skill entries identify their parent; load its integration contract as well. They ship
inside that parent, not as independently discovered plugin skills.

## Select The Catalogue Root

Install `repository-inspection` using [the library README](../../README.md).
The public `repository_inspection.catalogue` module owns discovery. Supply the operator-selected
catalogue package explicitly; nothing is inferred from this guide or downloaded.
No `PLUGIN_ROOT`, original checkout, Git metadata, profile, or notebook is needed.

Run with Python 3.11+:

```text
repository-catalogue --root <catalogue-package> --find "the user's task" --json
repository-catalogue --root <catalogue-package> --show protocol-restructure --json
repository-catalogue --root <catalogue-package> --list --kind protocol --json
```

The placeholder is an explicitly supplied metadata package, not a guessed sibling checkout.
See [README.md](README.md) for the input format and installed usage.

## Choose And Read

Protocols are authored in `protocols/<name>/SKILL.md`; each entry contains the complete procedure.
Use this catalogue when selection, inventory, exact-name read or diagnostics would help.

1. Search using the user's concrete problem. Matches report their matched and missing terms;
   keyword ranking is not a semantic guarantee. Inspect more than one when the distinction matters.
2. Read the selected entry using `--show NAME` or its returned `read_path`. Read its prerequisites,
   exclusions, permissions and relevant companion files before invoking anything.
3. Select the smallest applicable method. Modularization organizes capabilities and shared rules;
   restructure migrates a legacy shape; garbage collection proves a named dead set; lean surveys
   several categories. Regression checks prove behavior; demonstrate proves a user walkthrough.
4. Follow the existing owner and public contract. A catalogue result never grants deletion, cloud
   changes, paid inference, access to user data, or permission to overwrite another writer's work.
5. If no match, simplify the query or list everything. Never interpret no keyword match as proof
   that a capability does not exist. Unknown names and stale catalogues fail loudly.

Source-only entries are clearly marked and cannot be read from a plugin-only installation.
Their metadata identifies the source location and missing prerequisites. Do not silently download,
install, or substitute them. Explicit `--source-root` permits reading a reviewed source checkout.

## When The Client Misses This Skill

No catalogue can force a client or model to load a skill. A user can explicitly request
**"Use harness-guide to find the skill or protocol for this task"**, then supply the known
catalogue root. Parent integration must wire checkout installer shortcuts to this reader.
If the package cannot be accessed, report that missing prerequisite; do not invent a GitHub URL
or pretend discovery ran.

## Verify

Run [the catalogue selftest](../../tests/catalogue/selftest.py) for isolated positive and negative checks.
[CONTRACT.md](CONTRACT.md) fixes the data and path boundary. The script reads catalogue metadata
and selected documents only; it creates no client state and executes no retrieved instructions.