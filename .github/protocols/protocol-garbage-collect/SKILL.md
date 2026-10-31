---
name: protocol-garbage-collect
description: "Use when dead code or abandoned files are suspected in a named slice and must be proven dead before removal: reachability across imports, entrypoints, registries, dynamic imports, config, build manifests and CI; a dead/live/unproven table; one deletion batch. Requires explicit deletion authorization."
metadata:
  protocol: protocol-garbage-collect
---

# Protocol: garbage collect

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). This instruction/protocol adaptation
authorizes no deletion, agent-count reduction, cloud cleanup or restructuring. Preserve dirty
work, synthetic test cases, real human-label provenance and failed calibration evidence.
No notebook CLI exists; return bounded reachability findings to the caller without new records.

Proof before deletion. Caution-by-default leaves rot; deleting on a grep leaves outages. Both errors are real.

## When it earns its cost

A **named slice** suspected of carrying dead surface, run deliberately. Never as a background tidy alongside other work, never across a whole repository in one pass.

Skip it when the candidate is one obvious file, one owner, one inbound reference — delete that, with the acceptance command.

## Authorization

Deletion needs explicit user authorization. The executor must enforce that boundary; no particular
agent persona or hook is required.

Everything before step 4 is **read-only**. Present the `dead` set and its blast radius, confirm it
fits existing approval or ask for missing authority, then delete only what was authorized.
Approval of a plan does not authorize a set that grew afterwards.

## Steps

1. Enumerate candidates in the slice: files, symbols, routes, config keys, assets, fixtures.
2. For each candidate prove reachability or death across **all** of:
   - direct imports and requires;
   - entrypoints, including test entrypoints and CLI scripts;
   - generated or hand-maintained registries, rosters, and enums;
   - dynamic or string-based imports, and anything resolved by name at runtime;
   - configuration files;
   - build manifests, bundler config, and package scripts;
   - CI definitions and deploy scripts.

   A grep for the symbol name alone is not a proof. Name the path that reaches it, or the searches that found nothing.
3. Table it:

   ```
   | Candidate | Reached by | Verdict | Confidence |
   ```

   Verdict is `dead`, `live`, or `unproven`. **`unproven` is never deleted.**
4. Authorization gate. Match the `dead` set and blast radius against the user's explicit approval.
   Ask only for missing authority or a set that expanded after approval.
5. Delete the authorized set, one coherent group per step.
6. Run the recorded acceptance command.
7. Record the outcome, including every `unproven` candidate and the reason it could not be settled.
   Use an existing notebook when the finding is worth preserving; no ticket or notebook is required.

## Gates

- `unproven` stays. Say so; never quietly promote it to `dead` to finish the batch.
- Reachable only from tests is a distinct verdict. Name it explicitly rather than folding it into `dead`.
- Never delete a guard, a migration, or a schema without a confirmed replacement.
- One authorized batch. No opportunistic extras discovered mid-deletion.
- A pinned reference clone or gitignored vendor tree is out of scope by default — not ours to collect.

## Records

When rediscovery would cost more than recording the result, retain the reachability table in the
project's existing notebook or owning migration record. No new record system is required.

- The procedure itself, if refined: `type: method`.
- A specific run: acceptance and residuals in its `work-issue` note.
- A candidate that turns out load-bearing in a surprising way: `type: gotcha`.

## Failure loop

Red acceptance after deletion means something was reachable by a path the proof missed. Restore that item, **add the missed path as a new bullet in step 2**, continue with the rest. The taxonomy is the deliverable that outlives the run.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
