---
name: protocol-lean
description: "Use when a repository has accumulated weight: stale documentation, unused code, unimported dependencies, unset configuration, CI steps gating nothing, unused infrastructure. Surveys every category, orders by cost, records a verdict per candidate, measures the result. Requires authorization; deletes."
metadata:
  protocol: protocol-lean
---

# Protocol: lean

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
No cleanup or cloud mutation is authorized by this documentation follow-up. Focus any
assigned survey on observed drift; preserve four focused judges, required telemetry,
calibration provenance and human-review safeguards. No `.github/tools/` or notebook exists.
Return verdicts to the caller; do not create tracking records or invent savings.

A survey, not a delete. It finds weight across every category a repository accumulates it in, and
routes each candidate to a verdict.
[protocol-garbage-collect](../protocol-garbage-collect/SKILL.md) is the mechanism for proving code
dead and removing it; this protocol decides what to point it at, and covers the categories it does
not reach.

## When it earns its cost

After a milestone, before onboarding someone, or when the repository has started to mislead — a
document routing work down a road that ended, a directory nobody can explain, a resource on the
bill nobody claims. Run it deliberately, timeboxed, scope named up front. Leanness passes sprawl
too, and a sprawling one competes with the work it was meant to help.

Skip it when the answer is already known. One obvious dead file is a deletion, not a protocol.

## Order by what the weight costs

Cheapest to find is not most expensive to keep. Work in this order:

1. **Money.** Unused provisioned cloud resources bill every hour. Start here.
2. **Attention.** Stale documentation — in this harness documents are authorities and agents act on
   them. A wrong map is worse than no map.
3. **Time.** CI steps and test suites that gate nothing and slow every change after.
4. **Comprehension.** Dead code, abandoned experiments, one-implementation abstractions.
5. **Surface.** Dependencies nobody imports, configuration nobody sets.

## Survey

Each category has a proof. An adjective is not a finding.

| Category | How a candidate is found |
| --- | --- |
| Infrastructure | resources in the subscription with no reference in `deploy/`; no traffic or no logs since a stated date |
| Documentation | direct relative-link check in [protocol-document](../protocol-document/SKILL.md); compare claims with source |
| CI and pipelines | a step whose failure would block nothing, or that has not run in months |
| Dead code | `protocol-garbage-collect` for each named slice; inspect actual imports/callers and dynamic references |
| Fat | an abstraction with one implementation; a wrapper that adds no behaviour; a flag with one value in every environment |
| Dependencies | declared in the manifest, imported nowhere |
| Configuration | a key read by no code, or set by no environment |
| Data and fixtures | a fixture no test loads; a migration already applied everywhere and superseded |

Use focused `rg -n "<term>" applications bicep scripts` and inspect loading/configuration
paths. Missing `.github/tools/find.py`, `docaudit.py` and `arch.py` are disabled recipes,
not checks to run or passes to infer. A textual no-match alone does not prove death.

## Verdicts

Deletion is one outcome of four. Recording only the deletions is how a leanness pass turns into an
argument later.

| Verdict | Meaning |
| --- | --- |
| `delete` | proven unused, and its knowledge is either worthless or captured first |
| `capture` | the artefact goes, the knowledge stays — publish the note, then delete |
| `revive` | it should be used and is not. Wire it or fix it, as separate work, and say so |
| `keep` | it stays, with the reason recorded so the next pass does not relitigate it |

A `keep` with no reason is an `unproven`, and `unproven` is never deleted.

## Steps

1. Name the scope and the timebox. Record the baseline: repository size, file and document count,
   dependency count, CI duration, monthly cost of the resources in scope.
2. Survey each category in the cost order above, gathering evidence per candidate.
3. Table every candidate with its verdict and the evidence behind it.
4. Capture first into an existing authorized record, or return the knowledge to its owner
   before deletion. No local notebook exists; lack of an approved retention location blocks
   destruction of evidence, not permission to create a parallel notebook.
5. Authorization gate. Present the `delete` set, its blast radius, and anything irreversible.
   Reuse explicit approval for that set; ask for missing authority or an expanded set.
6. Remove in coherent, reversible batches, running acceptance commands between batches. Do not
   commit, stage, or alter cloud resources without the corresponding authority. Infrastructure
   work, when authorized, stops the bill soonest.
7. Reconcile what described the removed things: `deploy/README.md`, the architecture document, the
   project `README.md`, any register that listed them.
8. Measure against step 1 and publish the delta. "Leaner" without a number is a feeling.

## Gates

- Nothing irreversible without an explicit answer to an explicit question.
- Infrastructure is stopped or deallocated before deletion where the platform allows it: the bill
  stops immediately and recovery stays possible for a while longer.
- Never remove a guard, a migration, a schema, a backup, or a security control on the grounds that
  nothing calls it. Those exist for the case that has not happened yet.
- A wrong document is corrected or deleted, never left because deleting feels lossy.
- Deletion is not deferred to a branch to be merged later. It lands or it does not.
- Acceptance commands pass between batches, not only at the end.

## Records

- The procedure, if refined: `type: method`.
- Knowledge rescued from a deleted artefact: whichever type fits it, published before deletion.
- The run, its candidate table, verdicts, measured delta and residuals: its `work-issue` note.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
