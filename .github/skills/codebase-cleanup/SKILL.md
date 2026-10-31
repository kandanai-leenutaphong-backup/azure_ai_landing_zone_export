---
name: codebase-cleanup
description: 'Use when a workspace has excessive files, stale artifacts, duplicate restore trees, unused research mirrors, or editor indexing and memory pressure, and the user asks for aggressive codebase cleanup. Measure first, prove candidates unused, protect data and user changes, capture recoverable evidence, delete only an authorized frozen manifest, validate the app, and prevent regrowth. Not permission to delete canonical data, security controls, backups, dependencies in use, or cloud resources.'
---

# Codebase Cleanup

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
This adaptation authorizes no cleanup or restructuring. Preserve dirty work, parent-owned
deployment files and the reserved landing-zone summary; report candidates, never delete them.
The optional inventory CLI must be verified available before use.

Read [the canonical guide](../harness-guide/repository-inspection/guides/filesystem/GUIDE.md).
Optional bundled package `repository-inspection` exposes `repository_inspection.filesystem` or
`repository-inventory scan <root>`. Inventory and comparison never delete inputs.
Deletion decisions require host authorization and a frozen manifest; preserve data and user changes.