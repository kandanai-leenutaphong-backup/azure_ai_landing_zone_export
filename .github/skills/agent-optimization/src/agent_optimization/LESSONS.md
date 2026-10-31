# Optimization Lessons

These lessons govern the repeatable process, not a guaranteed score. Actual campaign
measurements remain in the owner-partitioned local ledger and are never rewritten by this
document. [PROCESS.md](PROCESS.md) owns the generation method.

## Show the Climb Honestly

- Start from a defensible generic baseline, not an intentionally broken control. The baseline
  is generation 0; `joint-12` adds twelve successors, making thirteen measured versions.
- Plot each measured score and latency, including regressions. An incumbent is the strongest
  measured candidate so far, not a relabeling of the latest one.
- Ground the next hypothesis in development failures and inspect the actual tool outputs.
  Evaluation aggregates are reused feedback, not an untouched test or proof of generalization.
- Prefer understandable evidence changes and useful comparisons over a headline score. Do
  not reduce an algorithm's capability to fabricate gradual progress or suppress worse runs.
- Distinct tools answer distinct questions. Inventory, ordering, evidence concentration,
  technique combinations, calibration and uncertainty are different views where supported.
  A higher tool count or different approach name alone proves nothing.
- Schedule detector changes and diversity early. A long sequence of prompt-only refinements
  can exhaust the generation budget before the required comparisons are measured.

## Execution Lessons

| Observed failure | Repeatable response |
| --- | --- |
| Typed evaluator rejected otherwise valid JSON diagnoses/citations | Host supplies a strict response schema and citation values derived only from returned knowledge. Legacy request formats stay unchanged. |
| Full-cohort baseline exceeded a short browser wait | Budget the wait for training plus evaluation; recover the same experiment from persisted terminal run state, not another baseline. |
| A long campaign outlived the browser driver's CLI session allowance | Native CLI credentials expire within one hour. `joint-12` permits two session attempts per declared version; each resume uses the same ledger and unchanged case/configuration pins. |
| Truncated or mistyped development case IDs produced misleading terminal refusals | Reuse exact returned IDs. A refused case is not a reason to broaden data permissions. |
| A large/arbitrary profile slice produced constant or irrelevant scores | Match current evidence features, use an explicit prior row, deduplicate and inspect contrasting incidents. |
| Multiple model campaigns competed for provider capacity | Run the requested campaign alone when possible; keep worker count fixed and preserve all throttling/error outcomes. A configured quota is not a guaranteed throughput. |
| Rich evidence and long prose exhausted bounded output | Return compact question-specific observations and concise model responses. Source/result limits are ceilings, not targets. |
| A useful source/tool existed but was invisible to the coding agent | Read the registry-backed capability catalogue before designing tools; distinguish visibility, permission, actual usage and measured usefulness. |
| Runtime or skill changed during a campaign | Preserve recorded task/skill/source identity. Restart only at a safe boundary; a changed fixed contract requires a new experiment. |

## Local Evidence Contract

Before launch record the command, protocol, baseline/successor count, full case membership,
model, resource bounds, source/profile identities, knowledge policy, skill/task and access
contract. Never depend on a temporary terminal session as the only record.

Each generation keeps immutable detector/tool/prompt/plan pins and its exact passed probe;
both stages keep every case outcome, metrics and genuine best/worst request/response examples.
Finish only when every requested version completed both stages and the coverage gates pass.
Recompute metrics and membership from saved results, then verify the browser plots and replays.

[scripts/verify_campaign.py](scripts/verify_campaign.py) performs one read-only scan of an
experiment, pins the baseline's immutable artifacts once, rechecks those hashes, recomputes
completed-stage metrics and writes `ledger-integrity.json` plus `trajectory.csv` to a separate
proof directory. `--complete` additionally requires the declared version, stage and exploration
counts. [tests/test_verify_campaign.py](../../tests/test_verify_campaign.py) includes edited-case,
changed-baseline, forged-receipt and incomplete-campaign negatives. Neither a partial pass nor
internally consistent model-response records prove that a whole campaign finished.

Local persistence is not an external backup. A host interruption retains failed/partial
attempts; partial results do not count as a completed generation. Never replace a failed run
file or claim a submitted CLI task finished the campaign.

## Current Limits

The originating dataset's incidents were already grouped, its labels covered grades only, and
development profiles make training F1 in-sample. Diagnosis and action correctness are unscored;
recommendations are never executed. There were no verified joins to unrelated replay telemetry.
The current investigator receives host-scheduled evidence and knowledge, not a dynamic
tool-choice loop.

New measurements belong below only after they finish, with experiment/version/run IDs and
read-back evidence. An unfinished campaign is not a lesson about achieved performance.