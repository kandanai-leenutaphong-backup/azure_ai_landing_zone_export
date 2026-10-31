---
name: architecture-placement
description: "Use when resolving contested ownership, placement, cross-boundary dependencies or new abstractions. Advisory placement packet; no solution design or implementation."
---

# Architecture Placement

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). Place the separate new app without moving
landing-zone infrastructure or sibling apps. No root architecture manifest or installed
`repository-architecture` command is established; inspect source/callers directly when absent.

Read [the canonical guide](../harness-guide/repository-inspection/guides/architecture/GUIDE.md).
Optional bundled package `repository-inspection` exposes `repository_inspection.architecture` or
`repository-architecture --root <project>`. Placement advice remains advisory.
No manifest means unknown architecture, not proof. Inspection grants no authority to edit or deploy.