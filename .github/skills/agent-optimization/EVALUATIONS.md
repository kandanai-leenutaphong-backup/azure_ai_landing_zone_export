# Foundry Agent Evaluations

> Research only: upstream capabilities and historical evidence, not implemented library support.

Evidence reviewed 2026-09-15. This is a source-grounded reference, not measured evaluator
accuracy or a completed Foundry evaluation. Preview labels below follow individual sources;
one preview feature does not make every evaluation feature preview, or vice versa.

## Evaluation Surfaces

| Starting Point | What Runs | Official Workflow |
| --- | --- | --- |
| Existing query/response data | Score supplied outputs | [Dataset evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-datasets) |
| Queries or input messages and an agent/model | Generate new outputs, then score them | [Target evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-targets) |
| Stored deployed interactions | Evaluate captured responses or traces | [Deployed interactions](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-deployed-interactions) |
| Complete conversation dataset | Score an interaction as a whole | [Conversation datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-conversations) |
| Complete deployed conversations | Evaluate captured multi-turn behavior | [Deployed conversations](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-deployed-conversations) |
| Scenarios describing a user's goals | Simulate user-agent conversations and score the result | [Conversation simulation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-simulate-conversations) |
| Production traffic | Sample live outputs for recurring assessment | [Continuous evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard#set-up-continuous-evaluation) |

Current cloud setup uses `AIProjectClient`, its `get_openai_client()`, and the OpenAI Evals
surface. The [introduction](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation)
specifies `azure-ai-projects>=2.2.0` for Python and documents .NET and JavaScript/TypeScript
clients too. That is documentation guidance, not a package version tested here.

The important distinction is **scoring a captured output versus invoking a target**.
Generating a new response can invoke tools and consume model capacity. A stored-response
evaluation does not establish that an agent still produces that response today.

## Agent Evaluator Matrix

The [agent evaluator reference](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators)
separates system outcomes from the steps used to reach them.

| Evaluator | Primary Signal | Data Or Interpretation Constraint |
| --- | --- | --- |
| Task Completion, preview | End-to-end requested deliverable; binary | `query`, `response`; optional tool definitions. Judge assessment is not independent state read-back. |
| Task Adherence, preview | Compliance with task instructions; binary | Include system instructions and interaction context to make policy assessable. |
| Customer Satisfaction, preview | Conversation-level satisfaction; 1-5 | Uses `messages`; a model's judgment, not an actual customer survey. |
| Intent Resolution, preview | Understanding the user's intent; thresholded 1-5 | Correct intent alone does not establish completion. |
| Task Navigation Efficiency | Expected versus observed action path | Requires `actions` and `expected_actions`; no judge model parameter. |
| Tool Call Accuracy | Overall tool choice and parameters; thresholded 1-5 | Needs tool definitions and response/tool calls, not only final text. |
| Tool Selection | Necessary and appropriate tools; binary | Measures choice, not whether an external side effect actually occurred. |
| Tool Input Accuracy | Strict parameter correctness; binary | Checks grounding, types, format, required/unexpected parameters, and values. |
| Tool Output Utilization | Correct use of returned tool information; binary | Preserve tool outputs and subsequent interaction context. |
| Tool Call Success | Technical execution success; binary | A technically successful call can still be the wrong call. |
| Quality Grader, preview | Relevance, abstention, completeness; binary | Groundedness/context coverage additionally depend on supplied context; turn-level assessment. |

Task Navigation Efficiency supports `exact_match`, `in_order_match`, and `any_order_match`.
The latter two can allow extra steps. Actual `actions` use OpenAI message-schema objects;
`expected_actions` can use tool names or the documented richer tool/parameter form.
Its output also includes precision, recall, and F1. Do not substitute a string list for
the actual action-message structure.

### Tool Coverage Is Not Universal

The reference lists File Search, Function Tool, MCP, and Knowledge-based MCP as supported.
It explicitly warns of limited support for Azure AI Search, Bing Grounding, Bing Custom
Search, SharePoint Grounding, Code Interpreter, Fabric Data Agent, and Web Search.

For conversations containing those limited-support tools, the guide says to avoid the
listed accuracy/input/output/success/groundedness evaluators. Preserve that restriction
when selecting evaluators; availability of a tool in Agent Service is not proof that a
particular evaluator understands its trace format.

Source: [model and tool support](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators#model-and-tool-support).

## Other Built-In Families

| Family | Included Measures | Appropriate Use |
| --- | --- | --- |
| General quality | Coherence, Fluency | Readability and logical flow, not factual correctness |
| Textual similarity | Similarity, F1, BLEU, GLEU, ROUGE, METEOR | Compare against reference outputs; lexical overlap is not semantic task success |
| RAG process | Retrieval, Document Retrieval | Separate relevance of retrieved content from quality of the generated answer |
| RAG output | Groundedness, Groundedness Pro, Relevance, Response Completeness | Separate support in context, relevance, and coverage of the expected answer |
| Risk and safety | Content harms, protected material, indirect attacks, code vulnerability, ungrounded attributes, prohibited actions, sensitive-data leakage | Risk-specific assessment, not an authorization mechanism or a complete security audit |
| Azure OpenAI graders | Model Labeler, String Checker, Text Similarity, Model Scorer | Label, compare, or score using the grader's own declared contract |
| Rubric/custom | Weighted domain criteria or custom scoring | Business-specific acceptance beyond generic quality labels |

References: [complete catalogue](https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators),
[general purpose](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/general-purpose-evaluators),
[textual similarity](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/textual-similarity-evaluators),
[RAG](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators),
[OpenAI graders](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/azure-openai-graders).

### RAG Details Worth Preserving

- Groundedness measures support in the supplied context; Response Completeness compares
  coverage with ground truth. These address different failure modes.
- Groundedness, Relevance, Retrieval, and Response Completeness use 1-5 quality scales and
  thresholded labels; the reference describes a default pass threshold of 3.
- Groundedness Pro, preview, uses hosted Azure AI Content Safety and returns a boolean;
  it is not the same scoring contract as the model-judged Groundedness evaluator.
- Retrieval uses `query` and `context`. Document Retrieval instead needs labeled
  `retrieval_ground_truth` and `retrieved_documents`.
- Document Retrieval returns Fidelity, NDCG, XDCG, relevance, and missing-label/Holes
  measures. Preserve all metrics and missing-label coverage, not a single invented score.
- Agent grounding can use structured tool results. A plain text output mapping loses
  information needed to assess tool-grounded answers.

Source: [RAG evaluator contracts](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators).

### Safety Semantics

Content-harm severity is 0-7, **lower is better**; the cited guide's default threshold is
3, with scores at or below it passing. Other risk detectors can be binary. Aggregate
defect rate measures undesirable outputs and is not interchangeable with a quality score.

Hosted safety evaluators do not require the caller's `deployment_name` judge parameter;
they still require a supported Foundry project and service availability. The reference
marks indirect-attack evaluation model-only. Prohibited Actions and Sensitive Data Leakage
are preview, agent-target-only, and require tool-call data; they are not general dataset
or model-target graders.

Sources: [risk and safety contracts](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/risk-safety-evaluators),
[transparency note](https://learn.microsoft.com/en-us/azure/foundry/concepts/safety-evaluations-transparency-note),
[regional constraints](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network).

## Dataset And Mapping Contract

Use either `messages` or separate `query`/`response` for each case. Full message history
can carry system instructions, typed text, tool calls, and tool results. A stored interaction
ends with the response being scored; target-input messages normally end with the user
message so the service can generate the next assistant output.

| Field | Meaning |
| --- | --- |
| `messages` | Input/history and, for captured interactions, output; supports multi-turn and tool context |
| `query`, `response` | Separate input/output; strings or supported message arrays |
| `ground_truth` | Reference answer required by applicable evaluators |
| `context` | Supporting material where it is not already present in structured messages |
| `tool_definitions` | Available tool names, descriptions, and parameter schemas, not merely the tools called |
| `test_case_description` | Required simulation seed describing the user's situation and goal |
| `desired_num_turns` | Optional simulation-length guidance, not the completed conversation |

For target evaluation, a stored `response` in the row is ignored: the target generates a
new one. CSV is supported for simple string query/response cases; JSONL represents richer
message structures. Some trace/response-ID workflows do not need an input dataset.

Mappings distinguish `{{item.field}}` from generated outputs. `{{sample.output_text}}`
supplies plain text; `{{sample.output_items}}` supplies structured agent output. Selecting
the wrong one can remove exactly the evidence a tool or adherence evaluator needs.

Source: [dataset schema](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-dataset-schema).

### Turn Versus Conversation

`evaluation_level` defaults to `turn`; `conversation` evaluates the complete interaction.
The same message row can be used at different levels, but all evaluators in a run must
support its chosen level. Check `supported_evaluation_levels` in the evaluator catalogue.
Do not mix incompatible evaluators or average turn scores and call that a native
conversation-level judgment.

Source: [evaluation levels](https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators#evaluation-levels).

## Rubrics And Custom Evaluators

**Rubric, preview:** define weighted dimensions or generate them from an agent, system
prompt, or reference documents. Production traces can supplement those inputs but cannot
be the sole generation input. Each applicable dimension is judged on 1-5; the overall
weighted score is normalized to 0-1. Preserve dimension IDs, descriptions, weights,
applicability, reasons, and the configured pass threshold across comparisons.

`always_applicable` forces scoring of a criterion. The documentation recommends validating
rubrics against human judgment on a small dataset before scaling. Auto-generated criteria
are candidates for review, not independent ground truth.

Source: [rubric generation and scoring](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rubric-evaluators).

| Custom Type, Preview | Contract | Constraints |
| --- | --- | --- |
| Code | Python `grade(sample, item)` returns 0-1 | No network; code under 256 KB; 2 minutes/call; 2 GB RAM, 1 GB disk, 2 CPU cores; fixed package set |
| Prompt | Judge returns JSON `result` and `reason` | Ordinal, continuous, or binary; declare model, range where applicable, and threshold |
| Endpoint | Registered project connection points to operator-owned HTTP scoring endpoint | Schema version `0.0.1`; structured status, score, reason, and error contract; separate endpoint auth and availability |

Code graders that raise or time out produce a 0.0 score **and an error marker**. Retain
that distinction from a valid low-quality result. The current guide accesses generated
target text through `item.get("sample", {}).get("output_text")` and explicitly warns this
shape can change. It also requires a valid `deployment_name` for orchestration even though
the code grader itself does not call an LLM.

Endpoint responses distinguish `completed`, `error`, and `skipped`; scores/pass flags can
be null on error or skip. Documentation describes API-key and Entra-backed connection
options. This research creates no connection or credential; repository adoption should
use the approved identity policy, not copy credential-bearing examples.

Source: [custom evaluator contracts and limits](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators).

## Retrieve And Interpret Results

Create an evaluation definition, create a run, retain both IDs, poll terminal state,
and retrieve item results. The guide treats `completed`, `failed`, and `canceled` as
terminal. Only `completed` follows its success path.

Python uses `evals.runs.retrieve()` and `evals.runs.output_items.list()`; fully iterating
the latter retrieves all pages. .NET protocol examples page explicitly. Keep `report_url`
as a navigation aid, not a substitute for the actual item evidence.

Preserve raw score, label, threshold, `passed`, reason, evaluator identity, details, and
execution status. Run aggregates and per-criterion pass rates answer different questions.
Do not infer that a completed run contains no item-level errors.

**Recommendation:** retain requested, completed, errored, and skipped case counts; explicitly
define the denominator of every acceptance rate. Treat missing/errored grades as unresolved
evidence, not silently omitted successes. Freeze evaluator version, judge deployment,
thresholds, dataset version, agent version, and input mappings for reproducible comparisons.

Source: [results, pagination, cancellation, and troubleshooting](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-results).

## Additional Workflows

| Need | Official Entry Point | Research Boundary |
| --- | --- | --- |
| Portal-first evaluation | [Run evaluations](https://learn.microsoft.com/en-us/azure/foundry/how-to/evaluate-generative-ai-app) | Portal operation not replayed here |
| Hosted-agent evaluation | [Quickstart](https://learn.microsoft.com/en-us/azure/foundry/observability/quickstarts/quickstart-evaluate-hosted-agent) | No hosted deployment or tool execution performed |
| Generate data | [Synthetic datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-dataset-synthetic) | Synthetic examples require review; generation is not reference truth |
| Reuse production cases | [Traces to datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/traces-to-dataset) | Capture, privacy, sampling, and case selection affect coverage |
| Human review | [Human evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/human-evaluation) | Separate human labels from model-generated judgments |
| Investigate result patterns | [Cluster analysis](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cluster-analysis) | Patterns guide investigation, not proof of root cause |
| Compare against standard tasks | [Benchmark evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/benchmark-evaluations) | A benchmark is not an application-specific acceptance set |
| CI/CD | [GitHub Actions](https://learn.microsoft.com/en-us/azure/foundry/how-to/evaluation-github-action), [Azure DevOps](https://learn.microsoft.com/en-us/azure/foundry/how-to/evaluation-azure-devops) | Review workflow generation, versions, permissions, and costs before execution |
| Developer CLI | [Azure Developer CLI evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/azure-developer-cli-evaluation) | CLI extension/version compatibility remains untested here |
| Adversarial testing | [Red-teaming overview](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent), [cloud scans](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/run-ai-red-teaming-cloud), [local orchestration](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/run-scans-ai-red-teaming-agent) | A scan needs separate target/data/tool authorization; local orchestration is not necessarily offline |

### Red-Teaming Boundaries

Foundry's AI Red Teaming Agent combines Microsoft PyRIT capabilities with safety evaluation.
Attack Success Rate is the fraction of tested attacks judged successful. It measures that
adversarial population, not the probability of a production compromise or the ordinary
user-traffic defect rate.

The overview documents text-based scenarios, synthetic data, imperfect sandboxing, and
possible false positives/nondeterministic judgments. Agentic risks are cloud-only. Sensitive
Data Leakage and Prohibited Actions have stated single-turn, English-only limitations;
the former excludes memory/training-set leakage. A scan is not a substitute for real
authorization, tool-side validation, or independent security assessment.

The red-teaming support matrix differs from the ordinary agent-evaluator matrix. It lists
Foundry prompt/container agents and Azure tools, while excluding workflow/non-Foundry
agents and several tool types, including function tools. Do not transfer tool support
between evaluation and red-teaming surfaces.

**Unresolved documentation conflict:** the centralized evaluation-region page lists East
US 2 and North Central US for cloud red teaming. The red-teaming overview additionally
names France Central, Sweden Central, and Switzerland West. Verify the exact workflow and
target region before planning a scan; this collection does not select one list as a tested
service guarantee.

Sources: [red-teaming capability and limitations](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent),
[central region matrix](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network),
[Microsoft PyRIT](https://github.com/microsoft/PyRIT).

## Recommended Acceptance Discipline

These are application recommendations, not claimed Foundry guarantees:

- Define business outcomes and important refusal cases before choosing proxy metrics.
- Use a representative development set and an untouched acceptance set; prevent trace or
  synthetic-data leakage across them.
- Calibrate judges and rubrics against human-labeled positive and negative cases.
- Separate model-judged task completion from externally verified persistence and permission.
- Retain per-case regressions even when composite quality improves.
- Compare latency, token use, external-tool cost, and failure rate alongside quality.
- Preserve missing-data and error counts; a percentage without its denominator is insufficient.
- Re-run acceptance after prompt, model, tool, retrieval, evaluator, or safety-policy changes.