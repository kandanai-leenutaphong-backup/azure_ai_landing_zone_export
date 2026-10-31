---
name: harness-guide
description: "Find the right harness skill or protocol before starting unfamiliar work. Use for onboarding a new project, listing available capabilities, choosing a workflow, or requests involving modularization, legacy migration, dead-code cleanup, documentation, regression verification, demonstrations, durable notebook findings, Azure data/models, deployment, authentication, frontend work, or UI audits. Searches a validated local catalogue and returns exact entry points; no MCP server, network lookup, or special agent is required. Read the selected entry before acting."
---

# Harness Guide

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Native skill entries are the usable discovery surface here. Root `libraries/` and its
capability catalogue are absent; no validated complete local catalogue is established.
Read direct entrypoints instead of installing a harness or treating a failed catalogue query
as proof that a capability does not exist.

Read [the canonical guide](repository-inspection/guides/catalogue/GUIDE.md).
An explicitly configured catalogue may use bundled `repository_inspection.catalogue` or
`repository-catalogue --root <explicit-catalogue-package> --find "task" --json`.
The source reader is bundled under `repository-inspection/src/`, but this checkout has no
root catalogue inputs. Do not run the imported `--root .github` recipe as a mandatory gate.
No catalogue is guessed, installed or downloaded. Read selected guidance; a match grants no authority.