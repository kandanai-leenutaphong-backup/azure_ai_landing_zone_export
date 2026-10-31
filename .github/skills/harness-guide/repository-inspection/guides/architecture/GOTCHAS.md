# Architecture placement gotchas

## G1 - A relocated checker inspects the plugin instead of the project

**Symptom:** analysis reports files from the installation tree rather than the requested project.

Deriving the target from the script's parent directories ties the result to installation layout.
The portable CLI requires `--root`; the selftest proves calls from an unrelated directory.

## G2 - A standalone copy fails a legacy harness audit

**Symptom:** a copy reports missing agents or notebook files despite having valid skill metadata.

The inherited fitness suite checks harness agents, instructions and notebook parity. Those are
not portable plugin components. Use `tests/selftest.py` for package acceptance; use the retained
`tests/fitness.py` only against an explicitly supplied legacy installation.

## G3 - An empty manifest prints no violations without proving a boundary

**Symptom:** the checker exits successfully while reporting `declared: false`.

Missing or empty `boundaries` yields `declared: false`. This is advisory, not architecture proof.
The selftest checks both that result and a declared graph with forbidden-edge fixtures.