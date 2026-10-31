---
name: recoverable-jobs
description: >
  Use when a job's completed output must not be lost between finishing the work
  and getting it stored. Use for expensive batch runs, model pipelines, report
  builds and exports where the save is slow or unreliable; for a store write
  that timed out and may or may not have landed; for telling "nothing was
  saved" apart from "unknown status"; for verifying a write by reading it back
  before deleting the local copy; for recovering finished output after a crash
  or restart and committing it again; for size caps that must not silently drop
  the tail; and for artifacts that must never be clobbered, never be deleted
  without proof, and never contain payload in a log line. Do not use for
  scheduling, retrying jobs, resuming an unfinished computation, or as a cache
  or queue.
---

# Recoverable Jobs

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Use only for an approved durable-output boundary, not as the multi-agent scheduler.
Preserve completed judge outputs after ambiguous writes; no store or recovery root is
configured by this import. Never log customer payloads or fabricate saved-result receipts.

Read [the canonical guide](GUIDE.md).
For an explicitly selected integration, package `recoverable-jobs` provides `workrecovery`.
The host owns the destination store, durable recovery root and separate access grants.
Never delete pending output. Installation grants no access; MCP registration remains host work.