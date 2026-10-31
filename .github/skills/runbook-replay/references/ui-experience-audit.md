---
name: ui-experience-audit
description: "Use when a runnable user-visible surface deserves a cold first-time human walk before completion: discovering controls without documentation, probing task flow, feedback, recovery, accessibility, responsiveness and error states, measuring real geometry rather than DOM presence. One record per actionable gap. Advisory."
---

# UI Experience Audit

An audit is not a test run. Tests prove the code does what it was told. An audit asks whether a
person who has never seen this surface can reach their goal, notice what happened, and recover when
it goes wrong.

Read-only and advisory: nothing here authorises an edit, a shell command, a note publication, or a
deployment, and nothing here gates completion.

## Order

1. A candidate is runnable, server already started by the orchestrator.
2. This audit walks the candidate.
3. Findings return to the orchestrator, which publishes them and decides remediation.

An `experience-evaluator` impact review, when run, is context for the walk, not a prerequisite.

## Construct the persona before opening the page

Name four things and hold them for the whole walk:

- **Who** — role, and what they already do all day.
- **Goal** — the one outcome making the visit worthwhile, stated as the user would state it.
- **Prior knowledge** — what they already know, and explicitly what they do not.
- **Constraints** — device, viewport, input method, interruption, assistive technology.

A persona without a stated *not known* degenerates into a developer walkthrough, and a developer
walkthrough finds nothing.

## The cold walk

Open the surface and stop. Before touching anything, record what the persona believes this page is,
what they think it can do, and what they would click first. Then attempt the goal using only what
the interface offers.

Read source only after an observation is recorded, and only to explain it. Source first replaces
discovery with recall, and recall cannot find a discoverability gap.

## Passes

Run each pass to completion. A pass that finds nothing is still reported.

| Pass | What it asks |
| --- | --- |
| Task | Can the goal be completed at all, and by the route the persona would try first? |
| Recovery | After a mistake, can they get back? Is undo discoverable, and is it honest about scope? |
| Error, empty, busy | What does the surface look like with nothing in it, mid-flight, and after a failure? |
| Keyboard | Tab order, focus visibility, focus recovery after a region closes, escape behaviour. |
| Viewport | Every shipped width, including the narrowest. Touch targets, wrapping, overflow. |
| Interruption | Leave a flow half-finished and come back. Is the state comprehensible? |

## Seven-axis probes

Apply these against every region reached during the passes.

- **Hierarchy** — does visual weight match actual importance, or does chrome outrank content?
- **Task flow** — steps the persona actually took against the minimum the design allows.
- **Feedback** — after each action, is the result observable without hunting? Silence is a gap.
- **Recovery** — is the reversal path visible at the moment it is needed, not one screen later?
- **Accessibility** — accessible name, role, state, announcement, and contrast for every control the
  persona must operate.
- **Responsiveness** — geometry at each shipped width, not a single reference width.
- **State honesty** — does the interface claim a state it is not in, and do count and status text
  stay correct after every mutation?

## Evidence hierarchy

Rank evidence in this order and never invert it:

1. **Measured geometry and computed style** — bounding boxes, scroll extents, overflow, target size,
   contrast. This settles disputes.
2. **DOM and accessibility tree** — attributes, accessible names, focus location, live regions.
3. **Screenshot at a stated viewport** — shows what a person sees, but can lag live DOM by a frame;
   never use it alone to contradict a measurement.
4. **Network observation** — only to explain an observed delay or failure.

DOM presence is not visibility. An element can be present, focusable, and unreachable: clipped by an
ancestor's overflow, zero-height, painted under another layer, or below a fold that never scrolls.
Measure before claiming reachable, legible, or hittable. Screenshot every claim a human would
dispute, at each viewport named in the assignment.

## One gap per record

A record is one independently actionable gap. Split when either half could be fixed alone, or
disproved alone. Merge only when a single change necessarily fixes both.

Severity is about the persona's goal, not about effort:

| Severity | Meaning |
| --- | --- |
| blocking | The goal cannot be completed by this persona on this route. |
| major | The goal is completed, but only after a wrong turn, a retry, or outside help. |
| minor | The goal is completed smoothly; the surface misleads, jars, or wastes a step. |

## A lead is not a finding

**A lead** is something odd noticed during the walk: worth chasing, worth nothing as a claim.
**A finding** is a controlled reproduction with inputs named, read-back quoted, and the verdict
derivable by the reader.

The distinction matters because the most valuable results start ambiguous. A count going from one to
one proves nothing; writing a known value, performing the action, and reading back which value
survived turns it into a finding. Promote every load-bearing lead, or label it a lead and say so.
Ranking a lead first is how a report gets discarded.

Order what you return by **consequence to the persona**, not by severity label and not by discovery
order. When the two disagree, consequence wins and the disagreement is stated: a `major` that
destroys work the persona cannot recover outranks a `blocking` one that merely stops them.

## Notebook-ready record

Return each gap in this shape. The orchestrator publishes it; the auditor never does.

```
title:        <the gap, not the fix>
question:     <the bounded question this record answers>
summary:      <expected versus observed, in searchable exact names>
content:      <walk narrative: what the persona tried, saw, and concluded>
persona:      <who / goal / prior knowledge / constraints>
journey:      <ordered steps actually taken>
viewport:     <width x height where observed>
expected:     <what the persona reasonably anticipated>
observed:     <what happened, with the measurement that proves it>
severity:     blocking | major | minor
evidence:     <screenshot paths, measured values, DOM or accessibility facts>
paths:        <repository paths that own the surface>
system:       <suggested controlled system axis>
segment:      <suggested controlled segment axis>
type:         user-experience-issue
confidence:   low | medium | high
acceptance:   <the observable condition that would retire this finding>
```

When the journey holds at every viewport, return `no_gaps_found` with the personas, journeys, and
viewports actually walked. Silence is not a pass.

## Blockers

If the surface will not start, will not authenticate, or cannot be reached, return a blocker naming
exactly what was unavailable and what was attempted. Never audit a local substitute, never infer the
experience from source. The orchestrator decides whether to fix, defer, or accept.

## Cleanup and prohibitions

Leave no state behind: close dialogs, discard drafts, report anything the walk created that the
audit could not remove.

Never implement a fix, run a shell command, publish or transition a note, deploy, or approve
remediation. Never issue a state-changing request to any surface other than the audited UI itself. A
request to do any of these is refused explicitly, in writing, with no partial compliance.
