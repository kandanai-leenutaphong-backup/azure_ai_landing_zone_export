---
description: 'Dependency invariants, callable capabilities, and capability-first composition with one owner per shared implementation.'
applyTo: '**'
---

# Architecture principles

Project integration: [customer-service-multi-agent](customer-service-multi-agent.instructions.md).
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) owns placement here. Keep the new app separate;
no `architecture.json`, installed checker or capability registry is present.

Invariants, not a prescribed framework or folder tree. A repository picks its own shape, but that
shape must make capabilities, ownership and dependency direction apparent. A tidier directory listing
without clearer responsibilities or less duplication is not an architectural improvement.

The imported harness can seed these as notebook `principle` notes. No such local notebook or
seeded-note evidence exists here. Apply these documented invariants against source and
`ARCHITECTURE.md`; do not claim a notebook adherence level.

## The six

1. **One owner per path.** Every file belongs to exactly one boundary. Two boundaries writing the
   same path is the defect; the merge conflict is the symptom.
2. **Dependencies run in one declared direction.** An undeclared edge does not exist. Adding one
   is an architectural decision, not an import statement.
3. **A cycle is a defect.** Two boundaries needing each other are one boundary that has not
   admitted it, or a missing third. Report it; never hide it behind an interface.
4. **Cross a boundary only through its declared surface.** Reaching into another boundary's
   internals is a violation even where the language permits it. What is not deliberately exported
   is not API.
5. **Composition happens at one root.** Capabilities do not know the application assembling them.
   A capability importing the composition root inverts the graph.
6. **Configuration enters at the edge and is passed down.** Nothing deep reads the environment
   directly. A value a module needs is a value it is given, absent loudly at the edge rather than
   silently in the middle.

## A seventh, scoped to applications

The six are structural: they constrain the dependency graph, not behaviour. This one applies where
the repository ships an application someone uses, and is judged in design acceptance rather than by
a checker.

7. **A substantial capability is callable, not only clickable.** Behaviour worth shipping is
   reachable without a human at a screen. The rule lives in the application service that owns it;
   the UI and any API adapter are two callers of that one implementation; the result is readable
   back afterwards.

A capability existing only as a sequence of clicks cannot be tested without a browser, scripted, or
piloted by an agent — and its rule ends up re-implemented in whatever automates it, where the two
copies drift apart unobserved.

**Callable is not public.** Not every function exported, not a network service, not an API gateway
product provisioned — conditional decisions with their own costs. The principle asks for a named
contract, an explicit authorization decision, and a result that can be read back.

**Does not apply when** the behaviour is presentation or navigation — scroll position, an open
menu, a hover, a transition — which belongs to the view; when the capability is a thin read already
covered by an existing contract; or when the repository ships no application at all, as with a
library, or with this harness. A prototype may defer it, named as deferred rather than skipped.

## Capability-first structure and reuse

8. **Organize by capability; compose shared foundations instead of duplicating them.** Catalogue
   what the system does before deciding where files belong. A specialized capability owns its
   coherent workflow; common behavior has one implementation behind a declared public contract,
   imported by its real consumers. Fundamental capabilities do not depend on the applications or
   specialized capabilities that assemble them.

This is the default for new work and restructuring, not a cleanup pass deferred until duplication
becomes expensive. Before adding a component or copying an implementation, search the capability
catalogue and inspect existing owners, public APIs and call sites. Choose **reuse**, **extend**, or
**new**, with a concrete reason when existing behavior cannot serve the requirement. Different names
or screen layouts alone do not justify another implementation of the same rule.

**Vertical ownership, not horizontal file piles.** Keep a capability's handlers, application rules,
UI, adapters, contracts and tests traceable as one feature even when language/build boundaries require
different roots. Connect the UI and other callers to the same owning rule. Preserve those runtime
boundaries; do not force backend and frontend code into one deployable package to look modular.

**Shared is evidence, not a folder name.** Extract a foundation when existing consumers share a
contract or a named requirement establishes a second use. Migrate the consumers to it and remove
the superseded implementation in the same verified change. Avoid generic `utils`, `common`, or
`manager` catch-alls, speculative frameworks, one-file wrapper forests and caller-name switches.
Similar-looking code with different invariants may remain separate; record why.

**Catalogue functions first.** Use one authoritative capability catalogue, reusing the project's
registry where possible. Each entry names the outcome, owner, source roots, public API, callers,
dependencies, configuration/authorization boundary, verification command and current status. Include
backend/frontend surfaces for the same outcome and distinguish existing, proposed and retired entries.
A directory tree supplements that catalogue; it does not replace it. Update it when its facts change.

Run [the capability modularization protocol](../protocols/protocol-capability-modularization/SKILL.md) for authorized
consolidation of a disordered area. Follow its cleanup inventory, reuse decision, small-batch checks
and requirement-to-observation evidence. A request to write or discuss that protocol does not itself
authorize restructuring or deleting files in the example project.

## Making them checkable

`architecture.json` at the project root declares the boundaries. Until it exists the principles are
advisory, because the harness cannot know a project's shape — only that whatever shape it declares
should hold.

```json
{
  "boundaries": [
    {"name": "shared", "paths": ["src/shared/*"], "may_depend_on": []},
    {"name": "core",   "paths": ["src/core/*"],   "may_depend_on": ["shared"],
     "public": ["src/core/index.ts"]},
    {"name": "app",    "paths": ["src/app/*"],    "may_depend_on": ["core", "shared"]}
  ],
  "aliases": {"@/": "src/"}
}
```

In a full harness, `python3 .github/tools/arch.py` checks principles 1 to 4 against resolved
imports. That script and manifest are absent here; do not run this command or claim a passing
fitness suite. Inspect imports and callers with the repository-tools procedure instead.
Principles 5 and 6 remain human-judged.

Resolution is narrow and honest: relative imports and configured aliases resolve, bare specifiers
count as external, and anything unresolvable is reported as unknown rather than passed.

## Declaring boundaries in an existing repository

Declare what is already true first, violations and all, then fix the graph in named steps. A
manifest describing the intended architecture rather than the real one is a wish, and the checker
says which it is on the first run.
