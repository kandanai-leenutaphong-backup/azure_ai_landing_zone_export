---
name: agent-optimization
description: "Use when composing frozen-cohort agent evaluation, immutable generations, evidence tools, development probes, native CLI authoring or persisted replay. Canonical agent_optimization library; no model grant or live campaign implied."
---

# Agent Optimization

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Use synthetic cases and four specialized judges: `factual_accuracy`, `task_completion`, `tone`,
`consistency`. Keep independent focused context and strict JSON; the task judge ignores politeness.
Optional three same-model prompt variants retain mean/spread, with spread > 3 sent to human review.
Calibration requires 50-100 real human-labeled examples and kappa > 0.7; no data means uncalibrated
quality gates, not a pass. Optional `azure-ai-evaluation` custom-callable JSONL batching must
preserve these contracts and actual SDK prerequisites. Reconcile system, journey-type and per-agent
metrics with pinned denominators. No campaign, business improvement or installed dependency is
established here. Bundled source is optional, not the app's chosen runtime; inspect its manifest
and existing interpreter before any separately authorized `uv` package operation.

Read the [canonical library guide](README.md)
and [contract](CONTRACT.md).
For an explicitly selected integration, the package is `agent-optimization`, import `agent_optimization`. React consumers use
`@agentcraft/agent-optimization` and its `styles` export.

Host supplies authorized data, predictor, identity, storage and sandbox prerequisites.
Use `llm_interface`, `situation_detector`, `workrecovery` and `copilot_terminal`
public APIs. Labels stay evaluator-only; preserve immutable pins and `.local` records.
Run the library's offline tests and example before host acceptance. No inference,
cloud write, grant, publication or long campaign is authorized by discovery.

This is a source-workspace entry. Portable plugin generation belongs to the parent
catalogue owner. The independently editable implementation archive is retired.