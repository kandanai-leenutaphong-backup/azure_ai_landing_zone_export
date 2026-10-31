---
name: frontend-implementation
description: "Use when building or changing a frontend surface: React + TypeScript + Tailwind, Vocs/MDX docs components, or framework-free static. Verify data contracts, accessibility and responsive geometry with typecheck, build, Playwright and screenshots."
---

# Frontend implementation

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
The app must provide navigable **system aggregate -> journey-type -> per-agent
accuracy/latency/errors/tokens** views, with reconciled filters and denominators, unknown
coverage labels and synthetic fixtures identified. Do not hardcode a reference agent count
or invent business KPIs. Verify actual drill-down controls, back navigation and correlated
detail on the running accepted revision. Match the app's actual manifest, not a presumed stack.
Expose the four criterion names, prompt-variant mean/spread and human-review state distinctly;
missing real-label calibration must display `uncalibrated`, not a reassuring fabricated score.

Implementation only. Cold-walk gap discovery and contested architectural placement are separate
tasks. Optional companion skills `ui-experience-audit` and `architecture-placement` can help when
available; this skill neither loads sibling files nor requires those companions.

The runnable half — per-surface gate commands, geometry-probe pattern, browser tooling, observed failure signatures — is [references/verification-loop.md](references/verification-loop.md).

## Decide before writing

| Situation | Use this skill? |
| --- | --- |
| A component, view, state, responsive, or accessibility change in an existing frontend | Yes |
| A new interactive surface with routing, cross-filtering, or a shared component library | Yes |
| Prose or content only in an MDX page, no new component surface | No — edit the page |
| A runnable surface needs first-time-user gap discovery, not implementation | No — `ui-experience-audit` |
| Where the new surface belongs is genuinely contested | No — `architecture-placement` first |

## Surfaces and their owners

A repository often holds several frontends on different stacks. Match the surface you are in; never
migrate one toward another as a side effect.

Establish the surface inventory before writing code, from the project's own record:

1. [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) at repository root, authority for which surfaces exist and which
   boundary owns each.
2. Each surface's `package.json`, or its absence, which is itself the constraint.
3. The project's search tool, or `rg --files` and a focused `rg` query, when ownership is unclear.

If the project has no architecture document, cite the actual entry point, manifest and callers.
Do not create a harness installation merely to obtain an inventory.

Stack, gate commands and hard constraints per surface belong in the project's architecture document,
not here. A surface with zero dependencies stays at zero: adding a bundler, framework, or package to
a deliberately framework-free surface is a boundary break, not an upgrade.

## Stack

For a **new** component surface default to React 19 + TypeScript + Tailwind, unless the repository
already has a React surface — then match it. Justify any deviation in the report; never deviate
silently.

- **shadcn/ui** when a component library is warranted: it copies source into the repository instead of importing an opaque package, so every component stays readable and editable in place. Install through the CLI or the registry MCP server; never paste component source from memory.
- **Tailwind** keeps styling in the file being edited, with no parallel stylesheet to drift. Where a surface already uses CSS modules or design tokens, follow that surface.
- **TypeScript strict.** Types on data row shapes are the cheapest place to catch a contract break.
- Add a dependency only when a named requirement cannot be met by the present stack. Record the requirement in the report.

## Data contract

Type the row shape explicitly; derive nothing from `any`. Parse once at the boundary — downstream components receive typed values, not strings awaiting interpretation.

Consume an upstream contract as given: field names, ordering, timezone behavior, and the wording separating observed fact from inference all cross unchanged. Do not re-derive, invent fields, or recompute an aggregate a producer owns.

Where a surface renders fixture or mock data, say so on the surface. A demo that reads as live is a defect.

## Verification loop — this is what gates done

An implementation without a check the agent can read is not finished. In order:

1. **Static gate.** Typecheck and lint. Exit code is the signal.
2. **Build gate.** Production build succeeds. Skip only where the surface has no build step.
3. **Behavioral gate.** Serve the surface, drive it with Playwright. Prefer the CLI for routine checks — it keeps verbose tool schemas and accessibility trees out of context. Use a browser tool when the loop is exploratory and needs persistent state.
4. **Visual gate.** Screenshot the viewports the change affects, compare against target or prior screenshot, list differences, fix. Show evidence; do not assert success.

Evidence precedence: measured geometry and computed style, then DOM and accessibility tree, then screenshot, then network observation. **DOM presence is not visibility.** A screenshot can serve a frame behind live DOM and never overrides measurement alone.

Report the command and what it returned. "Looks correct" with no artifact is an unverified residual and is labeled one.

## Accessibility is part of the gate, not a follow-up

Every interactive element you add or change carries an accessible name, role, and state. Keyboard reaches every action in sensible order with a visible focus ring. Contrast meets the stated target. Empty, busy, and error states exist and say something specific. Status never rides on colour alone. Verify in the accessibility tree, not by reading the JSX. Touch targets meet the surface's asserted minimum at mobile widths, and no affected viewport scrolls horizontally.

## Scope discipline

Implement the assigned slice. No refactoring adjacent components, no abstraction for one call site, no defensive handling for impossible states, no docstrings on code you did not change. A second problem revealed by the slice is reported, not absorbed.

After two failed corrections on the same defect, stop and report what was tried. Do not iterate blindly.

## Never

Never edit output a generator owns. Never add a build step or dependency to a surface that declares
zero. Return findings to the caller; any notebook publication follows the project's own policy.
Never deploy. Installing this guidance installs no framework, browser, MCP server or application.
