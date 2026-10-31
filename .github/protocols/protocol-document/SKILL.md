---
name: protocol-document
description: "Use when a comprehensive documentation sweep of a repository or named area is explicitly requested: coverage inventory, re-running each existing claim, filling gaps in the tier owning each fact, comment discipline. Not triggered by an individual change."
metadata:
  protocol: protocol-document
---

# Protocol: document

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md)
and [ARCHITECTURE.md](../../../ARCHITECTURE.md). Documentation follows observed source and
supplied evidence, not imported receipts. Verify exact four-judge names, strict JSON,
independent criterion context, task/tone separation, variant review and uncalibrated gates.
No root architecture manifest, notebook CLI or `.github/tools/` exists here. Use the direct
link check below; return the drift table rather than creating notebook/tracking Markdown.
Do not edit reserved summary, root docs or parent-owned deployment files in this assignment.

Two tests, applied to everything in scope:

- **Repeatable** — anything executable runs again from what is written, by someone else, with the
  expected result stated precisely enough to tell success from almost-success.
- **Explainable** — anything non-obvious has its reason recorded somewhere findable. The reason,
  not the mechanism; the code already shows what it does.

Neither means a finding, not a paragraph. A thing nobody can explain is a defect wearing
documentation's clothes.

An individual change does not trigger this; it updates the documentation it makes wrong, and may
delegate that to `documentation_curator`. This is the requested sweep that finds what no single
change owned.

## When it earns its cost

Before a handover, after a milestone, or when the repository has outgrown its description. Also
whenever the same question has been answered twice in conversation — the second time is the signal
that the answer belongs somewhere durable.

Never as a background activity alongside other work: a sweep interleaved with feature work produces
prose written from memory instead of from source.

## The tiers, and one home per fact

A fact recorded in two places is drift waiting for a date. Write it in the tier that owns it, link
from the others.

| Tier | Owns | Not this |
| --- | --- | --- |
| Project `README.md` | what exists, what works, what is left | how any of it is built |
| `ARCHITECTURE.md` | boundaries, ownership, dependency direction | per-function behaviour |
| Boundary `README.md` | what this part is for and how to work in it | the whole system |
| `CONTRACT.md` | the promise a boundary makes to callers | the implementation behind it |
| `deploy/README.md` | the runnable sequence, and what to do when it fails | architecture rationale |
| Notebook | durable findings, principles, decisions, dead ends | current state, which rots |
| Code comment | why this line is this way | what the line does |

## 1. Inventory what should be documented

A sweep without an inventory stops when the writer tires, not when the repository is covered.
Enumerate, then mark each `documented`, `stale`, or `missing`:

- every observed boundary in `ARCHITECTURE.md` and source, and every entry point;
- every public surface and `CONTRACT.md`;
- every environment variable and configuration key, with who sets it;
- every deployment step, and every failure met at least once;
- every connected data source, its shape and credential path;
- every scheduled job, migration, and one-way door;
- every non-obvious dependency and version pin, with the reason for the pin.

## 2. Verify what is already written

Existing prose is a claim until checked. Table it, one row per factual claim — a path, a command, a
flag, a column name, a default:

```
| Document | Claim | Reality | Verdict |
```

Verdict is `accurate`, `stale`, `missing`, or `unverifiable`. `unverifiable` is reported, never
quietly rewritten into something that sounds right.

The imported `docaudit.py` is unavailable and disabled. From repository root, check the
adapted entrypoint links with the existing Python interpreter and standard library only:

```bash
python3 -c '
from pathlib import Path
from urllib.parse import unquote
import re
patterns = [".github/instructions/*.md", ".github/agents/*.md", ".github/skills/*/SKILL.md", ".github/protocols/*/SKILL.md", ".github/copilot-instructions.md"]
files = [p for pattern in patterns for p in Path(".").glob(pattern) if "azure-ai-landing-zone-summary" not in p.parts]
bad = []
for p in files:
    text = re.sub(r"^```[^\n]*\n.*?^```[ \t]*$", "", p.read_text(), flags=re.S | re.M)
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
        if re.match(r"(?:[A-Za-z][\w+.-]*:|#)", target):
            continue
        path = p.parent / unquote(target.split("#")[0])
        if not path.exists():
            bad.append((str(p), target))
for issue in bad:
    print(*issue, sep=" -> ")
print(f"{len(files)} entrypoints; {len(bad)} missing relative targets")
raise SystemExit(bool(bad))
'
```

Success: zero missing relative targets and exit `0`. This does not verify fragments,
external URLs, commands, runtime status or the full contents of linked guides. Inspect
those separately within scope; do not claim a full `docaudit.py` equivalent.

Then the part no tool can do: **run the commands**. A command in a README that does not run is a
defect, not a typo. Fix the command or fix the code; never delete the command to make the page look
clean. Run it in a fresh checkout where feasible — the machine that wrote the instructions is the
one machine they are guaranteed to work on.

Use a separate read-only reviewer when that resolves a named risk or reduces substantial reading
cost. No particular agent persona or delegation stage is required.

Prefer deleting a wrong sentence to adding three that qualify it. Content still true but superseded
gets a forward pointer to its replacement, not deletion — a reader arriving from an old link needs
to land somewhere, and silence reads as a missing page rather than a moved one.

## 3. Fill the gaps, in the owning tier

Write for the reader with the least context and the most urgency, ordered by what saves them time:
what this is for, how to run it, what it depends on, how it fails, and only then how it works.

- **Name the reason, not the retelling.** "Retries three times because the upstream returns 503
  during its nightly reindex" is documentation. "Retries three times" is a comment on a
  retry-three-times line.
- **State the evidence for any claim of working.** A status without evidence is a hope.
- **Record what was tried and rejected** where it would otherwise be re-attempted. A dead end
  documented once saves the next person the whole detour.
- **A doc compensating for a bad name is the wrong fix.** Rename it.

## 4. Comment discipline

Default is no comment. Comments earn their place by carrying what the code cannot.

Write one for: a non-obvious constraint, a workaround with its cause, an ordering that matters, a
deliberate deviation, a unit or bound absent from the type, a one-way door.

Not for: what the next line does, a change made for a reviewer, a heading over an obvious block, a
restatement of the signature, or commented-out code — that is what history is for.

A comment that disagrees with its code is worse than none, because it is believed. The sweep is
when those get deleted.

## 5. Close the loop

When root README ownership is assigned, update it last, once the rest is true, since it summarises them. Anything found
but not fixed becomes a gap record, not a promise in prose.

## Gates

- Every command written down was run, or is marked unverified with the reason.
- Every claim carries a verdict, and no `unverifiable` was promoted to `accurate` to finish the
  table.
- No fact lives in two tiers.
- Nothing documented that should have been deleted instead. Sweep with
  [protocol-lean](../protocol-lean/SKILL.md) in mind: a well-documented dead module is worse than
  an undocumented one, because now it looks maintained.
- No secret, credential, or chat transcript entered a document.
- Anything that could not be explained is recorded as a gap, not smoothed over.

## Records

- The procedure, if refined: `type: method`.
- A rationale that will outlive the current code: `type: decision` or `type: principle`.
- The sweep, its inventory with outcomes, and what remained unexplained: its `work-issue` note.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
