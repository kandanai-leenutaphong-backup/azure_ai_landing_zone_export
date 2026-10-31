---
name: protocol-demonstrate
description: "Optional recipe, on request or when done means a demonstration rather than a passing suite: write the requirement-to-observation contract first, run in the agreed runtime, walk it as the user, and hand over a reproducible walkthrough. Cloud deployment requires explicit authority."
metadata:
  protocol: protocol-demonstrate
---

# Protocol: demonstrate

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Demonstrate synthetic journeys and navigable system aggregate -> journey-type -> agent
accuracy/latency/errors/tokens on the accepted app revision. Show four separate judge criteria,
same-model prompt-variant labels/mean/spread, human-review state for spread > 3 and explicit
`uncalibrated` gates until genuine human-label agreement qualifies. A demonstration creates
no calibration labels and proves no business impact. Parent owns root deployment/TLS/activation.
Notebook records below are optional taxonomy; no local notebook is installed and this sweep
creates no records. Return requirement observations to the caller.

Automated tests prove the software does what the author expected. They cannot prove a person can
find the button, understand what happened, or tell that it worked. Done here is an artefact in the
agreed runtime that a human walks through unaided. The agent walks it first before handing over.

Uses [ui-experience-audit](../../skills/ui-experience-audit/SKILL.md) for the cold walk and the deployment
convention for the runtime. `protocol-restructure` shapes the code; this shapes the delivery.

## When it earns its cost

Work whose value is only visible in use: a user-facing capability, a new end-to-end path, a
demonstrable milestone. The signal is a request phrased as a list of things that should be possible,
rather than a change to make.

Skip it for work with no user-visible surface. A library change is proved by its tests; dressing it
in a walkthrough wastes both.

## 1. The requirement-to-observation contract

Before building anything, turn the request into a numbered table — spec, acceptance criteria, test
plan and handover script, written once.

```
| # | Requirement | Observed how | Where | Evidence |
```

Rules that make it worth writing:

- **Observed by a person, from outside.** "The deployment succeeds" is not observable. "Within N
  minutes the item appears in the list with status Ready, without reloading" is.
- **Name the surface, not the mechanism.** A requirement satisfied only by reading a log or calling
  an API directly is not satisfied. State which screen, which control.
- **Asynchronous work names its terminal state and how the user learns of it.** The acknowledgement
  is not the outcome. Calling an accepted request done is the most common way this protocol fails.
- **Failure is a requirement too.** What the user sees when it does not work is part of the
  deliverable, not a follow-up.

Agree the table before implementation. A requirement added later is a new row with a stated reason,
not a quiet edit.

## 2. Build against the contract

Implement to the table. Keep safety evidence running as you go: typecheck, build, unit tests. That
layer proves nothing was broken; it does not prove the feature works and must not be reported as if
it does.

## 3. Run in the agreed runtime

Use the runtime named in the acceptance contract and record its identity and URL. Localhost is
sufficient for a local demonstration. A requested deployed demonstration requires the authorized
deployment through `deploy/deploy.sh`; local success does not prove cloud behavior. Obtain authority
before a cloud mutation. Any deployment step discovered by hand belongs in the deployment entry point.

## 4. The blind walk

Drive the **agreed runtime's** surface as the persona, with only the URL, the goal, and what a real
first-time user would plausibly know — deliberately without the source, API shapes, element
selectors, or the ordering the implementer had in mind.

The same person who built it may walk it, reusing the evidence already gathered. A separate blind
auditor is one option, not a required stage: delegate to `ui-experience-auditor` or
`experience-evaluator` when self-assessment is the named unresolved risk, and then withhold the
requirement table, because an auditor told what to find will find it.

Record per requirement: what was clicked, what appeared, how long it took, and the artefact. An
outcome that needed knowledge the persona would not have is a **failure of the feature**, not of the
walk. A gap found is fixed and the walk repeated, never explained away: a control nobody finds has
not shipped.

## 5. Hand over something reproducible

The deliverable is what lets someone else find out for themselves:

- the URL, and how to authenticate;
- numbered steps matching the requirement table, in the order a person should do them;
- the expected observation at each step, precise enough to tell success from almost-success;
- what to do when a step does not do that;
- the known limits — what is stubbed, what is slow, what is not implemented;
- the running cost, and the teardown command.

## Gates

- The requirement table existed before implementation started.
- Every observation happened against the agreed artefact; deployed acceptance is not claimed from localhost.
- The asynchronous path was observed reaching its terminal state, not merely accepted.
- The walk was actually run against that artefact, as the persona.
- A requirement not met is reported as not met. A partial is not a pass.

## Records

- The procedure, if refined: `type: method`.
- Experience gaps found in the walk: one `user-experience-issue` note each, independently
  actionable.
- The run, its requirement table with outcomes, the runtime URL, the walkthrough and the residuals:
  its `work-issue` note.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
