---
name: protocol-capability-modularization
description: "Catalogue functional capabilities, reuse shared foundations, and migrate vertical workflows in verified batches."
metadata:
  protocol: capability-modularization
---

# Capability-First Modularization

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). The separate app is not authorization to
restructure sibling apps or shared landing-zone infrastructure. Reuse the owning app's
existing contracts; no root capability manifest, installed harness checker or notebook exists.
Four judge criteria are separate focused evaluators, not four copies of batching/logging glue.
Preserve system/journey-type/agent attribution, strict JSON and uncalibrated quality gates.
Return any catalogue/record findings to the caller rather than creating tracking Markdown.

Turn a disordered working area into coherent vertical capabilities built on shared foundations.
Success is simpler ownership, fewer independent implementations of the same rule, and working
consumer workflows. Fewer files in a directory, more folders, or more components prove none of that.

Authority: [architecture principles](../../instructions/architecture-principles.instructions.md),
especially one owner per path, declared dependency direction, public surfaces, one composition root,
configuration at the edge, callable behavior, and capability-first reuse.

## Trigger And Scope

Use when a named application area has mixed responsibilities, duplicate behavior, unclear ownership,
or a real change is expensive because related code is scattered. This is not a mandate to refactor
working code unrelated to the task, reach a folder-count target, or extract every small function.

Inputs:

- The concrete user workflows and backend/frontend roots to preserve.
- The permitted shared-capability root, if one already exists; for example `app/components`.
- Existing architecture declarations, capability registry, build and deployment entry points.
- Explicit authorization for any file moves, removals and generated-artifact cleanup.
- Other writers' owned paths and contracts, current worktree changes, and a reversible baseline.

If the user names a repository as an example while requesting a reusable protocol, author the
protocol only unless execution there is also requested. Never infer cloud, permission, infrastructure
or production-data changes from authorization to rearrange source.

## 1. Baseline One Real Workflow

Start at the behavior that owns the outcome, not a directory listing. Trace one caller through its
application rule, dependencies and result. Record the cheapest executable acceptance command for that
workflow before editing. Run existing tests/build checks that cover the affected boundary; name any
pre-existing failures instead of claiming an unmeasured green baseline.

For a frontend change, operate the integrated control and observe the result; for stored behavior,
read it back. Authentication, ownership, integrity and concurrency need the matching refusal or race
case as well as the positive path. Keep established APIs and semantics unless a separate change is
authorized. A business-rule change hidden inside file movement defeats the baseline.

## 2. Catalogue Capabilities Before Folders

Search existing source and callers with focused `rg -n "<capability>" applications bicep scripts`
and inspect owning contracts. The imported `.github/tools/find.py` is absent and must not run.
Do not create a parallel registry merely to follow this protocol. Enrich an existing registry or,
where none exists, return a concise capability table to the caller. Creating a new authority
requires separately assigned documentation ownership; this sweep creates no tracking record.

The unit is a meaningful function/outcome, such as ingesting evidence, evaluating a finding,
recovering completed work, or managing access. It is not a language, layer, screen, filename or team.

| Catalogue Field | Required Evidence |
| --- | --- |
| Capability ID and outcome | What a caller accomplishes; input and observable result |
| Responsibility and owner | What this capability owns and deliberately does not own |
| Classification | Foundation, specialized workflow, adapter or composition root |
| Source roots | Exact backend/frontend/library/test roots implementing the outcome |
| Public contract | Import surface or callable API; schema and error/empty behavior |
| Consumers and dependencies | Actual callers and allowed directed edges, not intended reuse |
| State and security | State owner, configuration entry, authorization decision, read-back |
| Verification | Runnable command and the behavior or invariant it proves |
| Status | Existing, proposed, migrating, retired, or unverified; outstanding gaps |

Pair that functional catalogue with the directory/boundary manifest rather than duplicating its
ownership facts in another authoritative file. Describe what exists first. Record proposed moves
and known violations separately; a target diagram is not evidence of the current dependency graph.

## 3. Triage Disorder And Duplication

For each candidate, identify its implementation, callers, public contract and tests. Search imports,
registries, dynamic loading, build inputs, configuration and scripts before declaring code unused.
Textual similarity is a lead, not proof of interchangeable behavior. Compare inputs, invariants,
state, permissions, concurrency, failures and performance constraints.

Record one decision per candidate:

| Decision | When It Applies | Required Result |
| --- | --- | --- |
| Reuse | Existing public behavior already meets the requirement | Import it; remove the duplicate caller-side rule |
| Extend | One compatible addition serves existing and named new consumers | Extend the owner with regression checks for both |
| Extract | Real consumers share one contract but implementations are duplicated or app-bound | One foundation, both callers migrated, no app imports back into it |
| Keep separate | Similar code has materially different invariants | Name the difference; do not add a mode-switching mega-module |
| Retire | No supported caller remains across all loading paths | Remove only after authorized salvage and verification |
| Defer | Evidence, authority or a required interface is missing | Keep it; name the unresolved fact and next discriminating check |

Do not invent a shared component because there is a directory named components. A proposed shared
module with no real consumer migration is extra maintenance, not deduplication. Prefer extending an
existing foundation to adding another component, when its ownership contract remains coherent.

## 4. Declare The Smallest Useful Structure

Choose one boundary at a time. Specialized capabilities should contain related behavior vertically,
with foundation imports directed downward and a composition root assembling the application.
Keep adapters thin; the same application rule serves the UI, API and automation where applicable.

When backend and frontend have separate build roots, give corresponding feature directories a
shared capability ID and catalogue entry. Keep contracts, tests and shared ownership explicit across
them. Do not merge deployment lifecycles, languages or authorization boundaries just to co-locate files.

For reusable capabilities in an existing `app/components` root, use functional names and one public
entry point. Move generic rules out of app-specific orchestration; pass configuration and dependencies
at the edge. The component must not import its parent application, assume its working directory, or
read another component's private files. Runtime dependencies must be declared and tested.

Code reused inside one codebase should be imported from its canonical owner, not copied into each
feature or vendored locally to avoid a dependency declaration. An independently distributed package
may bundle a dependency when portability requires it, with provenance and an explicit update policy;
that is a distribution choice, not permission for duplicate in-repository implementations.

## 5. Clean Generated Artifacts Deliberately

Artifact cleanup is its own bounded operation, not a prerequisite to designing every capability.
An authorized path such as a frontend artifact directory may be cleaned without deleting its parent.

1. Resolve and inspect the exact path, including hidden files, symlinks and tracked entries.
2. Distinguish reproducible output from fixtures, source assets, migration evidence and user data.
3. Retain needed evidence outside the doomed output set; record any authorized non-reproducible loss.
4. Delete only the approved contents. Do not follow symlinks into other trees or sweep similarly named
   directories. If already empty, report that rather than manufacturing a deletion.
5. Add an anchored ignore rule to the owning repository. Existing tracked artifacts are not untracked
   by an ignore rule; remove them from tracking only as part of the authorized change.
6. Verify the directory is empty, a future nested output is ignored, and source inputs are untouched.
   Run the existing regeneration command where loss of required output is a risk.

Move build/test screenshots, caches and reports into one predictable generated-output location.
Never ignore a failing check's only evidence or hide source code under an artifact rule.

## 6. Migrate One Vertical Batch

For the chosen capability, list every old path and its destination or replacement before removal.
Preserve contracts, examples, tests and hard-won failure knowledge. A clean commit is useful if the
user requests commits; it is not permission to commit, reset, stash or overwrite another writer's work.

1. Establish or select the public owner and tests.
2. Move or extract the smallest behavior-preserving unit.
3. Change real consumers to import the owner; update routes, registries, build inputs and test paths.
4. Run the narrow acceptance check immediately. Repair only that batch, then rerun it before expanding.
5. Remove the now-superseded implementation and unnecessary forwarding wrappers after its callers move.
6. Update the capability catalogue and boundary declarations in the same batch.

A temporary compatibility adapter needs named consumers and a removal condition. It must not become
a second implementation of the rule. Do not add dual writes, silent import fallbacks or deprecated
copies just to keep old tests green. Stop and ask if preserving behavior requires a material scope
or authority change.

## 7. Prove Reuse And Close The Record

Use existing checks rather than building a parallel test framework. Verify:

- Every affected path has one owner and cross-boundary imports use declared public surfaces.
- Dependency cycles are absent; unknown/dynamic edges are disclosed, not treated as a pass.
- Each extraction has real consumers importing it and the duplicated behavior is retired.
- Existing caller behavior and negative authorization/integrity cases still work.
- Backend/frontend paths meet through the same contract; the integrated user workflow still works.
- Builds, asset loading and deployment scripts resolve the new paths; no secrets or auth bypasses
  were introduced to make a relocated service run.
- The catalogue, architecture overview and affected READMEs describe the actual final state.

No `.github/tools/arch.py` or boundary manifest is present here. Inspect actual imports/callers
against `ARCHITECTURE.md`; report unknown edges, not an automated pass. A checker in another
checkout cannot decide that two business rules are the same capability; retain consumer evidence.

## Deliverables And Stop Condition

Provide the updated functional catalogue, a compact old-path-to-owner mapping, reuse decisions,
shared public APIs and migrated callers, artifact cleanup/ignore result, and exact verification output.
Report measured before/after facts: independent implementations of each consolidated rule, their
callers, declared dependency violations and unsupported remnants. File-count reduction is secondary.

Stop when the named workflows work, known duplicates in the authorized slice have a single owner
or justified separation, and the next change to an existing rule can be located from the catalogue
and made in that owner. Do not demand zero duplication globally or continue speculative polishing.

List unverified behavior, deferred candidates and authority blockers explicitly. A reorganized tree
with duplicated rules, unused shared modules or a catalogue describing only aspirations is not done.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
