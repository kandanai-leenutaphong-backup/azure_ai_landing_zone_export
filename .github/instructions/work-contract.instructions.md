---
applyTo: '**'
description: 'Do the task, delegate only for clear gain, verify in proportion to the change.'
---

# Work contract

Project integration: [customer-service-multi-agent](customer-service-multi-agent.instructions.md)
owns the supplied target, synthetic-data boundary, telemetry and acceptance. Its deployment,
DNS and route grant does not include secret retrieval, RBAC grants, Entra registration changes
or unrelated restructuring. Imported procedures do not expand that scope.
The central four-judge contract also owns strict JSON, prompt-variant review and real
human-label calibration gates. Do not fabricate labels, agreement or a calibrated release.

**Do the task. Delegate only where a specialist clearly beats doing it yourself. Verify in
proportion to what could break.**

One contract, replacing the per-role process mandates this harness used to carry. Nothing below
requires a charter, an envelope, a sign-off, an audit pass, or a second agent to approve work.

## Do the task

- Smallest change that achieves the asked outcome. No adjacent fixes, no speculative abstraction,
  no test infrastructure nobody asked for.
- Delegation is a cost. Use a specialist when it removes real risk or real unknowns — unfamiliar
  source, contested placement, a user-visible surface you cannot see. Otherwise implement directly.
- One writer per path, contract, deployment target, and cloud resource at a time.
- Make repeatable actions reproducible before running them. If an action is likely to be repeated
  (data acquisition, preparation, deployment or verification), use an existing owning script or
  save a version-controlled script with explicit inputs and documented invocation. Shell history
  and one-off commands are not the procedure. Preserve provenance, verify outputs and make reruns
  safe; never embed credentials. One-off read-only inspection does not require a new script.

## Python dependency and package management

- All agents use `uv` for authorized Python dependency and package management, including generated
  setup instructions and specifications. No bare `pip`, `python -m pip`, Poetry or Pipenv fallback.
- Never configure, create, recreate or activate Python environments, including virtual environments;
  use existing interpreters/environments only. Do not run `uv venv`, `python -m venv`, `virtualenv`,
  Conda environment setup, activation scripts or equivalent indirect setup.
  Target it explicitly with `uv pip install --python <existing-python> ...` or
  `uv pip sync --python <existing-python> <requirements-file>`; synchronize only when replacing
  that environment's package set is authorized. Use `uv pip uninstall --python <existing-python> ...`
  for authorized removals. Preserve declared dependencies and reproducible pins in the owning manifest/lockfile.
- For project manifests, use `uv add --no-sync` / `uv remove --no-sync` and `uv lock` as applicable;
  avoid implicit environment creation by `uv sync`, `uv run` or setup recipes. Respect locked versions
  and repository compatibility constraints; no unrelated upgrades or package-manager migration.
- Missing `uv` blocks package operations; no alternative package manager is permitted. Missing tooling
  or dependencies are prerequisite gaps, not permission to install tooling or expand mutation authority.
  This policy takes precedence over conflicting setup examples in skills;
  read-only roles and restricted agents retain their existing tool and execution limits.

## Verify in proportion

Scale evidence to blast radius, and stop there:

| Change | Evidence that closes it |
| --- | --- |
| Prose or comment | the edit reads correctly |
| Refactor with no behaviour change | the existing check covering that code, run |
| Code with an existing check covering it | that check, run |
| Runnable UI behaviour | operate the real control, observe the result, read back what persisted |
| Auth, ownership, integrity, concurrency | the positive path plus the matching negative refusing |
| Cloud or deployed configuration | read back the field you wrote; a 200 is not evidence |

Reuse evidence that already exists. A pass already run does not need an independent second signoff.
State what was not verified as plainly as what was.

## Escalate

Stop and ask only for:

- authority you do not have — credentials, a billable or tenant-mutating action, deleting or moving
  files, force-push, teardown;
- a destructive choice with no obvious reversal;
- material scope expansion beyond what was asked.

Not for permission to proceed with the work already asked for.

## Keep the record honest

- For AgentCraft projects, deliver all observable assigned actions, changes, retries, failures, concise
  rationales and measured outputs to the overseer for direct publication. Preserve primary evidence;
  do not replace it with a success summary. The overseer owns standardized JSON publication and snapshots,
  while workers retain implementation ownership. Report missing capture and unknown telemetry explicitly.
- Update the documentation that a behaviour change makes wrong, in the same change. Nothing else.
- Record durable knowledge when rediscovering it would cost more than writing it down. Otherwise
  skip it and say so.

## Scope versus safety

The user's chosen scope controls which steps are taken: when they are steering turn by turn and
have named the next step, do that step and no more. Scope never removes the evidence a step's own
blast radius requires, and never removes escalation for authority, destruction, auth, or cloud
mutation.
