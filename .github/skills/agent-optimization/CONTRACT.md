# Optimization Contract

## Inputs And Authority

`OptimizationService(dataset, root, model, predict, *, authorize, profile, identify, ...)`
receives host-owned dependencies. `authorize(caller)` supplies the authorized storage
owner and `identify(caller)` supplies record ownership. Every record read checks both.
Predictor receives prompt, evidence and model only, never the case's expected label.
`profile.model_request` describes replay input; it is not a second execution path.
The host binds model execution to `llm_interface`; `model_predictor` was retired.

`SQLiteReader(path, *, allowed_tables=...)` snapshots trusted table policy. A query's
`tables` can only narrow it. `labels`, SQLite catalogues, writes, DDL, extensions,
attached databases and unlisted functions refuse. Rows and elapsed work are bounded.
This is an evidence database, not permission to supply an arbitrary caller path.
Construction cannot make label-bearing host views safe; the host must classify its
tables and must never put evaluator labels in an allowed evidence table.

`PythonToolRunner` requires explicit Bubblewrap and libseccomp. Missing isolation
refuses; there is no unsandboxed fallback. Its result kind is
`optimization_tool_result`, replacing the application's `cybereye_tool_result`.

## Detector Workflow

`detector_version` accepts schema-2 definitions with `configuration`; `detect` executes
only those pinned definitions through `situation_detector.run_battery`. The host supplies
`detector_query(case_id, rule, window)` and `detector_process(case_id, rule, envelope, window)`.
Configuration normalization, enabled-rule selection and ordered battery execution belong
to `situation_detector`; the optimizer retains its bounded observation contract and pins.
An explicit case window is required. Expected labels never enter these callbacks.

Schema-1 `rules[].code` definitions are read-only. `verify_detector` retains their digest
checks for historical readback, not execution. New schema-1 definitions, direct detection,
and `OptimizationService.measure` of an old detector refuse. Measurement refuses before
appending a run or dispatching callbacks. Start a new schema-2 experiment; do not rewrite
old detector files or pins. See [the migration mapping](MIGRATION.md#schema-2-consolidation).

## Results And State

Generations, detector definitions, tools, probe receipts and cohort files are immutable.
Experiment status is a mutable local ledger. Host-owned roots are single-process,
not a multi-replica storage service. Owner-only persisted read-back is the result.
Unknown/denied/malformed operations raise documented Python exceptions; model failures
remain scored errors, not successful empty cases. Expected labels stay evaluator-only;
authorized development feedback and replay may show recorded outcomes after measurement.

New case `error` fields contain fixed codes, never exception text or exception type names:
`detection_failed`, `no_situation`, `tool_failed`, `knowledge_unavailable`, `knowledge_failed`,
`prediction_failed`, `invalid_grade`, `invalid_diagnosis`, `invalid_proposed_actions`,
`invalid_citations`, or `invalid_rationale`. Run-level capture failures record
`measurement_failed` or `measurement_cancelled`. Control-flow `BaseException` values
propagate. Opt-in captured requests, evidence and responses, including rejected responses,
remain payloads, not sanitized diagnostics. Historical errors are not rewritten.

New publish rejection records and `candidate_rejected` events contain fixed diagnostics:
`candidate_rejected` with category `invalid` for `ValueError`, or `publish_failed` with
category `failed` for other `Exception` values. Both carry additive `failure` metadata
with `code`, `category`, `capability_id="agent-optimization"`, `operation="publish"`,
the native `experiment_id` and `rejection_id`, `effect="unknown"`,
`retry="read_back_first"`, and `action="inspect_record"`. Earlier immutable writes may
have succeeded; rejection does not prove no effect or authorize an automatic retry.
Validation retains its native `ValueError` and existing caller-visible validation message;
programming exceptions also retain their identity and propagate, never becoming public
validation errors. Control-flow `BaseException`
values propagate without rejection capture. These diagnostics never inspect or persist
exception text or type names. Submitted proposals remain payloads under the existing field
allowlist; historical proposals, rejection records and immutable pins are not rewritten.

Outer evaluation and final-verification failures also use `measurement_failed` or
`measurement_cancelled`. Their additive `failure` object contains fixed `code`,
`category` (`failed` or `interrupted`), `capability_id` (`agent-optimization`),
`operation` (`evaluate` or `verify_final`), and the native evaluation ID as `run_id`.
`effect="unknown"`, `retry="read_back_first"`, and `action="inspect_record"` never
claim that a dispatched callback had no effect or authorize replay. Evaluation versions
mirror this metadata. Exception text and type names are not inspected or persisted by
these handlers; control-flow `BaseException` values still propagate through the future.

For new rows, `tool_calls` counts attempted evidence-tool callbacks (`dataset.run_tool`),
including a failed attempt but excluding an unreached tail. It does not count detector,
knowledge or model callbacks. Captured `model_call_attempted` records predictor dispatch,
not provider usage or billing. Historical `tool_calls` retain their configured-tool-count
meaning; cross-generation comparisons must account for that change. Failed cases remain
in the scoring denominator. Final case results and detector observations retain input order;
progress callbacks and streamed case files retain completion order.

`measure_run` writes case rows and exemplar files, then stages its completed manifest
through `workrecovery`. `run.json` is create-if-absent-or-identical and verified by
read-back. `RunSaveError.outcome` distinguishes failed/unknown/conflicting saves and
preserves staged bytes. Recovery never reruns a predictor:

```python
from agent_optimization import run_recovery

jobs = run_recovery(authorized_run_directory, saved_run_id)
artifact = jobs.read(saved_run_id)
outcome = jobs.recommit(artifact)
assert outcome.saved and outcome.verified
```

Only authorized host code receives the run directory. The `.recovery` directory is
operator state and must not be deleted. Case streaming and exemplar creation precede
manifest recovery; an earlier filesystem failure remains a limitation, not a claim
that unfinished computation can resume.

## Lifecycle And Limits

The service owns one evaluation executor. `cancel` sets the experiment stop signal;
`close(*, timeout=5.0) -> None` signals all owned runs, including final verification,
and waits for their settlement without holding the record lock. The finite, nonnegative
timeout covers lock acquisition and future settlement together. Invalid values raise
`ValueError("invalid_close_timeout")` before changing lifecycle state.

Once closing is marked under the lock, `create`, `evaluate`, `measure`, and `verify_final`
raise `RuntimeError("optimization_service_closing")` before persisting new work. Creation
and baseline submission, and training-to-evaluation handoff, share that lock boundary.
Every submitted future remains tracked by identity even when the latest-per-experiment
lookup changes. Queued tasks drain cooperatively under their stop signal so their records
can become cancelled instead of being stranded by executor-level future cancellation.
Normal return means all owned executor tasks settled; none can still persist a record.
Repeated close calls are supported, including after a timeout. Record read-back remains
available while closing and after settlement.

`TimeoutError("optimization_close_timeout")` means workers remain unsettled and may still
persist; admission stays closed. `TimeoutError("optimization_close_lock_timeout")` means
the record lock could not be acquired, so stop signalling and admission closure have not
begun. Neither outcome is clean shutdown. The host must stop admitting requests and keep
borrowed clients, credentials and storage alive until a later close settles the tasks.
Async hosts must offload this synchronous call and handle timeout before dependent-resource
teardown; an exit stack that continues cleanup on exceptions cannot establish settlement.
Existing no-argument calls remain valid, but callers must now handle the timeout outcome.

The Custom Optimizer host closes its terminal first and offloads service close from its
event loop. Only successful service settlement drains borrowed knowledge, model and
credential resources, in that order. A timeout propagates and leaves
`app.state.optimization_cleanup_complete=False`; `app.state.optimization_resources` and
the async `app.state.optimization_cleanup()` callback retain cleanup ownership. The host
must retain the application and its original event loop, then retry that callback after
workers settle. Repeated or concurrent cleanup calls serialize; completed cleanup is a
no-op and borrowed resources close once. Existing service, knowledge and unrelated
application state remain available for read-back. This is not automatic retry or forced
thread termination. Normal shutdown and partial-startup failures still release resources.

Running synchronous native work cannot be forcibly terminated; there is no exactly-once
side-effect guarantee. Model binding, credentials, dataset and terminal host lifetime remain
caller-owned. Protocol limits bound versions/tools/workers; SQL and sandbox have separate
bounds. No retry wraps a model call. Full campaign protocols remain opt-in and were not run.

Each service and parallel-case submission receives a fresh `contextvars.copy_context()`.
An active host `ExecutionContext` retains the same budget object, deadline and correlation
across nested submissions: no child allowance or renewed deadline is created. Native
synchronous callbacks without an execution context remain supported. Context propagation
grants no calls; participating callbacks such as `llm_interface` own reservation/dispatch.

## Conformance

| Standard | Selected Result / Remaining Gap |
| --- | --- |
| F1 | Named distribution/API and capability references here; generated framework descriptor/catalogue belongs to parent and is pending |
| F2 | Normal dependencies, wheel/npm owners and public imports; no skill runtime lookup; Python 3.12 selected profile; portable artifact checks recorded in migration evidence |
| F3 | Host authorization/identity, schema-2 detector configuration and matching label/write refusals; host profile is not an appcompose schema |
| F4 | Immutable receipts, fixed new case/run and outer evaluation/final failure codes, native safe failure metadata, scored failures and workrecovery outcomes; no universal result wrapper |
| F5 | Synchronous close with a five-second default bound, explicit incomplete timeout, closed admission and identity-tracked task settlement; native work cannot be forcibly terminated |
| F6 | Fresh service/case contexts preserve shared host reservations and deadlines; actual evidence-tool attempts and protocol/SQL/sandbox bounds remain; no billing or distributed quota guarantee |
| F7 | Persisted owner ledger, replay and recovery; historical event schema retained, not claimed as common framework event conformance |
| F8 | Injected collaborators, offline positive/refusal tests; live model, sandbox, app browser and cloud workflows remain separately unverified |

These gaps are not full-framework acceptance. No license for customer data or external
assets is created by source movement.