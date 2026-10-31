---
name: runbook-replay
description: "Use when explicitly replaying an operator runbook whose accuracy is a named risk. Record dated per-step evidence, deliberate mistakes, responsive checks, ranked findings and reconciliation. State-changing commands require separate authorization."
---

# Runbook replay

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Replay only an available app runbook against the intended WAF URL/revision. Parent owns
root `deploy/`, TLS and gateway activation; no root deployment runner existed at initial
inspection. A stopped gateway or missing TLS is a blocker, not permission to use a local
substitute, create registrations or retrieve secrets. Exercise system -> journey-type ->
per-agent drill-downs with synthetic cases. This adaptation creates no replay/tracking files
and makes no commits; a later replay needs an explicitly authorized evidence location.

A replay walks a surface's **own documented runbook**, step for step, as a first-time operator, and
writes what happened into a dated folder readable months later. It returns two things a test cannot:
findings ranked by consequence, and a verdict on the runbook itself.

Optional and deliberately invoked: a runbook is a claim no test reads, so it decays silently — walk
it when someone must know whether it is still true.

## This skill, or the audit skill

They split on one line: **the audit reads nothing and touches nothing; the replay follows the
documentation and leaves an artefact.**

| | [UI audit method](references/ui-experience-audit.md) | runbook-replay |
| --- | --- | --- |
| Input | the surface, documentation deliberately unread | the surface **and** its runbook |
| Finds | what the interface never explains | where the runbook lies, plus what the walk hits |
| Authority | read-only; no shell, no mutation, no artefact | runs a driver; may create and destroy real state |
| Output | notebook-ready gap records, advisory | a dated folder, ranked findings, a runbook verdict |

Persona construction, probe taxonomy, evidence hierarchy and severity vocabulary are retained in
the bundled [audit method](references/ui-experience-audit.md). No sibling skill or particular agent
roster is required. Follow the runbook for this replay; do not claim it was a documentation-blind
cold audit. Installation performs no commands or cloud changes.

## Reach for it when

| Situation | This skill? |
| --- | --- |
| A surface has a written operator runbook and someone must confirm it is still true | Yes |
| A human needs to review the walk later, or compare two walks across revisions | Yes |
| The pass must exercise real dependencies — real cloud, real data, real latency | Yes |
| Gap discovery on a surface with no runbook, or where documentation must stay unread | No — `ui-experience-audit` |
| A regression signal that must fail a build | No — an assertion suite |
| The surface will not start | No — report the blocker; do not walk a substitute |

## Where a replay lives

`replays/<YYYYMMDDTHHMMSSZ>/` at the repository root, one directory per walk, named for the UTC
instant the walk began. Not under the surface it walked, and not in `evidence/`: `evidence/` is
overwritten by the next run, while a replay is written once, pinned to a revision, and never re-run
in place — comparing two walks is the value. The folder is unowned and immutable once the walk
closes; the **findings** are owned by whoever owns the walked surface.

## What a replay is made of

Four artefacts, no more:

| File | What it is |
| --- | --- |
| `README.md` | the reading — verdict, ranked findings, the step table, the runbook reconciliation, cleanup |
| `observations.json` | the machine record — per step, every control with accessible name, box and contrast; every timing; every refusal |
| `capture.py` (or equivalent) | the driver, so the walk is re-runnable and the numbers re-derivable |
| `shots/` | screenshots, numbered in flow order, plus lettered crops for the findings |

Judgement lives only in `README.md`. The driver records what was on screen, what was pressed and how
long it took; it never decides what that means. Pin the revision in the header — `git rev-parse
--short HEAD`, and whether the tree was clean. An unpinned replay cannot be argued with.
## The walk

Number every step to match the runbook's own numbering, quote the sentence being tested, and record
what actually happened beside it. Per step: at least one screenshot, at least one measurement, and
the elapsed time.

Add, in the same pass:

- **deliberate mistakes** — the wrong first move, the empty required field, the input the surface
  should refuse. Refusal quality is a headline result, not a footnote. Screenshot even when nothing
  changed: a byte-identical pair is the honest record of *nothing happened, and nothing was said*.
- **a responsive sweep** — every shipped viewport, then a finer geometry sweep to **locate the
  break**, not merely observe one. "Collapses between 920 and 900" is worth an order of magnitude
  more than "looks cramped on a laptop".
- **the full keyboard path** — tab order, focus visibility, escape and recovery.
- **the wire** — every response `>= 400`, counted. Unexplained 4xx means the walk found something;
  4xx that are all its own deliberate mistakes means the walk proved something.

## Ranking, worst first

Order findings by **consequence to the operator**, not by severity label and not by discovery order.
Name one **fix this first** and give the reasoning in the open.

When consequence and severity disagree, consequence wins and the disagreement is written down: a
`major` destroying work the operator cannot get back outranks two `blocking` findings that merely
stop them.

Each finding carries what it costs the operator, the measurement that proves it, the viewport and
route it happens on, and the crop that shows it.

## Runbook reconciliation

A separate section, and the one nothing else produces. Walk the runbook line by line and tabulate:
**step · what the runbook says, quoted · what was measured**.

- A control the runbook names that does not exist is a **product** defect, not a prose defect. Say so
  explicitly, or the fix will be to delete the sentence.
- A number that has moved is a prose defect. Give the measured replacement, so the fix is a one-line
  edit rather than a second investigation.
- **List what the runbook got right, by name.** A reconciliation listing only errors reads as hostile
  and gets argued with instead of applied.
- Count the mismatches. Eight of eleven steps is a different conversation from one of eleven, and
  only the count makes that visible.

## Praise is evidence too

Say what is genuinely good with the specificity used for the defects — the measurement, the verbatim
string, the timing. Unsupported praise devalues the criticism beside it.

## Committed, ignored, redacted

Screenshots taken against a real environment show real resource names and real identifiers.

- `shots/` is **ignored**, by a `.gitignore` inside the replay folder whose comment says why.
- `README.md`, `observations.json` and the driver are **committed**.
- **Redact on the way out, in the driver, not by hand afterwards.** Identifiers and subscription ids
  become placeholders as the record is written; hand-redaction misses one.
- Resource *names* are kept deliberately: a replay that cannot name what it touched cannot be
  reproduced.
- No secret, key, token, or connection string reaches any of the four files, screenshots included.

## Cloud cleanup, read back

A replay that creates real resources owns their removal and proves it. Close `README.md` with a
read-back block: what was created, what was deleted, and the query showing nothing survived. A `204`
is a response, not evidence; the listing after it is.

Say what was **not** cleaned and why. In-memory state that dies with the process still gets named,
because the operator saw it. Say plainly what was left running.

A replay relaxes no standing authority. Obtain explicit approval for the target, permitted
mutations and cleanup before creating anything. Use the project's deployment entry point; never
delete shared resources or change tenants merely because a runbook says to. Stop if authority is
missing. Read back every authorized mutation.

## Reporting

Return to the caller: the replay path, the revision, the verdict in one line, the ranked
findings with the fix-this-first named, the runbook mismatch count, the cleanup read-back, and what
was **not** covered.

Each finding is a notebook candidate in the audit skill's record shape, one gap per record. The
replay never publishes notes and never edits the runbook it graded — a walk that fixes its own
subject destroys the evidence that the fix was needed. Publication and remediation belong to the
authorized owner. A notebook is optional; the replay files are the durable output.
