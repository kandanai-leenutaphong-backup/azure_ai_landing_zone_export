---
name: protocol-regression-loop
description: "Use when a change to source, configuration or deployed infrastructure needs proving: fix the acceptance command in writing first, implement, gate locally, deploy if not exercised in place, confirm the new artefact, sweep acceptance, fix and reverify until green or a structural blocker is declared."
metadata:
  protocol: protocol-regression-loop
---

# Protocol: regression loop

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Use the app's actual checks and parent-owned `deploy/deploy.sh` actions, not guessed harness
commands. Test four focused strict-JSON judge contracts, task scoring independent of politeness,
malformed/unscorable handling and optional three same-model prompt variants. Spread > 3
requires human review. A batch/schema/local pass cannot establish real-label calibration:
50-100 genuine human-labeled examples and kappa > 0.7 are required for calibrated quality gates.
Keep system/journey-type/agent metrics reconciled. Return evidence; no notebook setup is required.

The loop is implement → gate → deploy → confirm identity → sweep → observe, repeated until the named
acceptance command passes. Its value is not the steps but that the acceptance command is written
down before the work starts, so "done" cannot move mid-work.

An explicitly requested documentation sweep uses [protocol-document](../protocol-document/SKILL.md).
An individual prose edit needs only its affected claims checked. Where done means a
person verifying it, this loop is the mechanical half of
[protocol-demonstrate](../protocol-demonstrate/SKILL.md), not a substitute for its blind walk.

## When it earns its cost

A change proven against something real: a test suite, a build, a deployed service, a data pipeline.
Especially where the artefact under test is rebuilt or redeployed — that is where confident false
passes come from.

Skip it for a change already covered by one command you were going to run anyway. Announcing a loop
to run one test is ceremony.

## Steps

1. **Fix the acceptance command in writing.** Runnable verbatim by someone else, pass condition
   stated. Not runnable as written is the first defect — fix it before touching anything else.
   Every step below depends on it.
2. **Implement**, then run the cheapest check covering the changed slice: a compile, the owning
   test, the focused selftest. Cheap and specific beats broad and slow; a broad suite hides which
   change broke it.
3. **Rebuild or redeploy only if the change is not exercised in place.** An edit to a running
   interpreter's source needs no deploy; a container image does.
4. **Confirm artefact identity before probing.** Revision, digest, build id, process start time, or
   output timestamp. This separates a real pass from a cached one; skipping it is how a green sweep
   gets reported against the previous build.
5. **Sweep acceptance.** Each case reports its own status and error count. Run cases separately
   where a bulk run would hide which case failed and how far it got.
6. **Observe.** Table of case, result, errors, plus artefact identity and wall-clock time. Timing is
   evidence: a suite that passed impossibly fast did not run.

## The failure loop

Any failure stops the sweep. Diagnose before fixing — produce the reproducer and root cause, then
change code. Re-verify from step 2, not from the failing case.

**Three iterations.** Still red after the third is a structural blocker, not an unlucky run: say so,
name what is in the way, ask for direction rather than starting a fourth. The fourth iteration of an
unchanged approach is where hours go.

## Gates

- Keep failures attributable. A sweep whose output cannot say which case failed is not evidence.
- Never anchor a result on an intermediate event when a terminal event carries it: a request
  accepted is not a job finished; a rollout started is not a revision serving.
- A backgrounded call is not a finished call. Use the runtime's completion notification or result
   mechanism; do not infer completion from an acknowledgement or busy-poll a notified process.
- Immutable inputs stay immutable. Never edit a generated artefact whose generator owns it — change
  the generator and regenerate, or the next run silently reverts the fix.
- Never weaken, skip, or special-case a check to make the sweep green. A disabled assertion is a
  defect with a green light on it.
- On real infrastructure, create and update freely within what is authorized; confirm before
  deleting, tearing down, force-pushing, or changing shared network posture.
- Secrets stay out of the transcript, the arguments, and the notes. Probe results are reported by
  status and count, never by response body.

## Acceptance

One line carrying the artefact it was measured against:
`regression PASS — <artefact identity>, N/N cases, 0 errors`.

A partial is reported as a partial. "Passing except for" is a fail with extra words.

## Records

- The procedure, if refined: `type: method`.
- A reachable failure mode and its reproducer: `type: bug`, fixed or not.
- The run's acceptance contract, artefact identity and outcome: its `work-issue` note. Not the run
  log.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
