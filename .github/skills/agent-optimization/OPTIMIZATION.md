# Foundry Agent Optimization

> Research only: upstream capabilities and historical evidence, not implemented library support.

Evidence reviewed 2026-09-15. Microsoft-documented behavior, not a local or cloud
measurement. Preview availability and model lists must be rechecked before adoption.

## Distinguish The Products

| Surface | What Changes | Evidence It Produces | Important Boundary |
| --- | --- | --- | --- |
| Agent Optimizer, preview | Agent instructions, selected tool descriptions, model selection; hosted agents can also change skills | Baseline/candidate evaluation scores, configuration comparisons, and available token measurements | A scored search over configurations, not model-weight training or guaranteed improvement |
| Prompt Optimizer, preview | Text system instructions in the Foundry playground | Suggested text and paragraph-level explanations | No dataset-scored search is established by this workflow; run an evaluation afterwards |
| Model fine-tuning | Model weights through a separate training workflow | Training/validation artifacts and separately evaluated model behavior | Not the same API, permissions, cost model, or artifact as agent configuration optimization |

Primary references: [Agent Optimizer overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview),
[Prompt Optimizer](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/prompt-optimizer).
Model-weight training and Agent Lightning are covered below as separate capabilities.

## Agent Optimizer Contract

The service evaluates a baseline on tasks, generates candidate configurations, evaluates
candidates, and ranks them. Computation runs in the cloud. The operator reviews and applies
a selected candidate; discovering a winner is not itself a production rollout.

| Target | Prompt Agent | Hosted Agent |
| --- | --- | --- |
| Instructions | Selected agent version supplies the baseline | Baseline `instructions.md` activates instruction tuning |
| Skills | Not supported | Baseline `skills/` with `SKILL.md` files activates skill improvement |
| Function-calling tool descriptions | Tool and parameter descriptions can change | Baseline `tools.json` activates tool-description optimization |
| Model selection | Choose candidate deployments in the portal wizard | Configure `model_search_space` in `eval.yaml` |

Tool optimization does not change parameter types, defaults, or required fields. It covers
function-calling tools, not arbitrary tool implementation changes. Prompt-agent function
tools execute client-side: the optimizer can change their descriptions but cannot evaluate
their execution during tool-description optimization.

For hosted agents, the optimizer changes configuration loaded by the agent, not arbitrary
application code. `load_config()` supplies the normal baseline outside optimization and
candidate configuration during an optimization run. Runtime integration is required;
Foundry Toolkit can scaffold it.

Sources: [overview and target matrix](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview),
[optimizer-ready integration](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/make-agent-optimizer-ready),
[target configuration](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/optimize-agent-targets).

## Entry Points And Artifacts

**Prompt agents:** select an agent version in the portal's Optimize tab; choose or upload
a dataset, evaluators, and models; review the estimate; submit; inspect baseline/candidate
comparisons; promote a selected candidate to a new agent version. Existing registered
datasets and trace-derived datasets are supported. No agent code integration is required.

**Hosted agents:** make the runtime optimizer-ready, provide baseline configuration and
evaluation settings, start through Foundry Toolkit or Azure Developer CLI, inspect results,
apply a selected candidate locally, review the diff, and redeploy. The documentation names
`azd ai agent optimize apply --candidate <candidate-id>` and a separate `azd deploy` step.
Neither command was executed for this research.

Hosted-agent optimization supports local JSONL and registered Foundry datasets. The
overview requires the Responses protocol and excludes Norway East from otherwise supported
hosted-agent regions. This is a dated product constraint, not proof that a specific tenant
or deployment is eligible.

Sources: [prompt-agent quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-optimize-prompt-agent),
[hosted-agent quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-optimize-hosted-agent),
[dataset preparation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/create-optimizer-dataset),
[availability](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview#limitations-and-availability).

### Native SDK Optimization Jobs

The current official SDK sample exposes a callable route in addition to portal and CLI
workflows: `project_client.beta.agents.begin_create_optimization_job(job=...)`.
Its typed inputs include `AgentOptimizationJob`, `AgentOptimizationJobInputs`,
`OptimizedAgentIdentifier`, `AgentOptimizationReferenceDatasetInput`, evaluator references,
and `AgentOptimizationOptions`. The returned long-running-operation poller yields baseline,
best candidate, and candidate details including scores, tokens, and evaluation IDs.

Release history records the transition to `begin_create_optimization_job` in 2.4 and the
`AgentOptimization*` model renames plus `poller.details["job_id"]` in 2.5. The current
sample still advertises `>=2.4.0` while importing the later renamed types. Treat that
minimum as stale guidance, not a tested compatibility range. No SDK job was executed here.

Sources: [native optimization sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/samples/agents/optimization/sample_optimization_job_basic.py),
[SDK release history](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/main/sdk/ai/azure-ai-projects/CHANGELOG.md).

### Hosted Configuration And Dataset Shape

The integration package is `azure-ai-agentserver-optimization`; its loader is
`azure.ai.agentserver.optimization.load_config`. The baseline directory is
`.agent_configs/baseline/`, with required `metadata.yaml` and `instructions.md`, and
optional tool/skill files. If no configuration source exists, `load_config()` returns
`None`; an adopting host must handle that explicitly rather than assume a baseline exists.

Optimizer task JSONL requires unique `name` and `query` fields; `ground_truth` and
`criteria` are optional. Each task-level criterion has `name` and `instruction`.
Registered datasets use name/version references; local datasets use `local_uri` in
`eval.yaml`. This is not automatically interchangeable with every generic evaluation or
fine-tuning dataset schema.

The documented `azd ai agent eval generate` workflow generates seed data, evaluators, and
`eval.yaml`; `azd ai agent eval update` registers edited rubric criteria as a new version.
Generation still needs review. Its small-dataset size suggestions are iteration guidance,
not a statistical claim of comprehensive production coverage.

Sources: [runtime integration](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/make-agent-optimizer-ready),
[optimizer dataset contract](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/create-optimizer-dataset),
[CLI evaluation assets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/azure-developer-cli-evaluation).

## Judges, Models, And Scores

- The agent model performs the task. The evaluation model judges responses. The optimization
  model proposes better configurations. These are distinct cost and reproducibility inputs.
- Hosted configuration names `eval_model` and required `optimization_model`; CLI overrides
  include `--eval-model` and `--optimize-model`.
- The overview documents a moving list of supported optimization models. Deployment names
  and actual model versions must be recorded, not inferred from example names.
- Candidate composite scores range from 0 to 1. Raw evaluator scores are rescaled, reversed
  when lower is better, and averaged across evaluators and tasks.
- The displayed winning candidate has the highest composite score. That does not establish
  significance, safety on every task, held-out generalization, or acceptable operating cost.
- Microsoft's score-improvement bands are interpretation guidance, not a reproduced
  statistical confidence interval or an application-specific acceptance threshold.

Source: [models and score computation](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview).

**Recommendation:** preserve per-evaluator and per-case results alongside the aggregate.
Averaging can hide a regression in a critical safety or task category. Use explicit refusal
criteria and an untouched final evaluation set before applying a candidate. Label a reused
training/evaluation dataset honestly; the service can use the training set for evaluation
when no separate validation set is supplied.

## Cost And Token Accounting

The [cost documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-costs)
separates pre-run modeled cost from post-run measured tokens. Neither is the Azure invoice.

| Layer | Work | What Increases It |
| --- | --- | --- |
| `agent`, Running your agent | Baseline and candidate executions | Dataset rows, candidates, multi-step/tool behavior, selected model |
| `judge`, Scoring responses | Evaluator calls on agent results | Dataset rows, candidates, selected evaluators, judge model |
| `reflection`, Generating improvements | Candidate generation and analysis | Optimization settings, model, reflection and early-stopping behavior |

The portal exposes Minimum, Estimated, and Maximum modeled values for **prompt-agent**
runs. Hosted-agent flows do not currently show that pre-run portal estimate. Requesting an
estimate does not start optimization or call models. It uses resolved settings, reference
prices, and static token assumptions rather than measuring future behavior.

Critical limitations:

- Maximum is **not an enforced budget**. Reference prices and assumed tokens can differ from
  actual subscription, region, model, cached-token, and reasoning-token charges.
- Missing reference prices produce explicitly unpriced layers excluded from the modeled
  total. Do not treat a partial estimate as a complete one.
- Model-selection estimates use the baseline model where resolvable, not a separately priced
  execution for every model in the search space; the documented fallback is the eval model.
- External APIs, search, databases, and other called tools are excluded from this estimate.
- Post-run usage can be available for both agent types. Hosted-agent usage depends on usage
  being present in its evaluation samples or traces.
- Missing usage is unknown, not zero. Missing model attribution prevents reliable
  deployment-specific pricing of that row.
- Cached tokens are a subset of input tokens. Reasoning tokens are a subset of output
  tokens. Adding those subsets again double-counts usage.
- Estimated cost derived from measured tokens is still not the final bill.

No monetary estimate or optimization benchmark was produced in this repository.

## Side Effects And Adoption Safety

The optimizer invokes agents against evaluation tasks. External tool calls can therefore
execute repeatedly for the baseline and candidates, causing charges, mutations, or rate
limiting. Microsoft's overview explicitly warns about this behavior.

**Recommendation:** use authorized nonproduction targets, read-only tools where possible,
or purpose-built tool fixtures. Preserve the real authorization decision. Never infer that
a dataset run is safe because its purpose is evaluation. Check tool-description tuning
against actual execution separately when the service cannot execute the client-side tool.

Agent Optimizer is preview, without an SLA; the overview does not recommend production
workloads. Successful optimization is not evidence of production readiness, complete tool
coverage, or an approved deployment.

Source: [workflow warning and preview terms](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview).

## Prompt Optimizer Is A Different Workflow

The playground feature accepts a purpose or existing instructions, optionally accepts
suggestions, rewrites text, and explains paragraph-level changes. Reoptimization uses the
latest suggested text as the new baseline. Selecting Use prompt applies that text.

- It works on text instructions, not tool definitions or knowledge-source configuration.
- Results are ephemeral until applied; closing the dialog can discard them.
- It does not automatically retain a prompt version history.
- Availability depends on the Foundry project's region. The feature guide lists supported
  regions; lack of the control can be a region issue.
- Explanations describe intended improvements, not measured task quality. The guide
  explicitly recommends evaluation on the application's own dataset afterwards.

Source: [Prompt Optimizer workflow, limits, and regions](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/prompt-optimizer).

## Model-Weight Training

These are separate workflows; an agent optimizer candidate does not update model weights.

| Method | Training Signal | Key Boundary |
| --- | --- | --- |
| Supervised fine-tuning | Demonstrations of desired behavior | Curate training/validation examples; evaluate the resulting model independently |
| Direct preference optimization, DPO | Preferred/non-preferred response pairs | Adjusts weights using preferences; its dataset is not ordinary query/response evaluation data |
| Reinforcement fine-tuning, RFT | A grader-derived reward | Grader quality and reward exploitation become training risks; model/access support is restricted |

DPO uses `input`, `preferred_output`, and `non_preferred_output`. The current guide lists
specific supported model versions and permits DPO on supported base or previously
supervised-fine-tuned models. Do not extrapolate support to every deployed chat model.

RFT requires training and validation JSONL, a `messages` array ending with a user message,
and a grader. A multigrader can combine component scores. The guide lists `o4-mini` support
and gated, invitation-only `gpt-5` access despite its GA label. Its preview endpoint-grader
API is described as unpublished; do not invent a public contract for it.

The RFT guide documents automatic pause at **$5,000** in combined training/grading costs;
resuming continues billing without a further cost-based limit. This is a dated RFT rule,
**not** a spending cap for Agent Optimizer. RFT Python-grader limits also differ from
cloud custom-evaluator limits: the cited RFT page specifies one CPU core.

Sources: [when to fine-tune](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/fine-tuning-considerations),
[fine-tuning guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning),
[DPO](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning-direct-preference-optimization),
[RFT](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reinforcement-fine-tuning),
[fine-tuning costs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning-cost-management).

Model routing is another separate selection surface. Collect its own
[evaluation](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/evaluate-model-router)
and [monitoring](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/monitor-model-router)
evidence; do not attribute a router's results to a fixed-model optimizer candidate.

## Agent Lightning

Microsoft's Agent Lightning is an open-source agentic reinforcement-learning framework,
not the managed Foundry Agent Optimizer. The current repository explicitly identifies a
v1.0 rewrite and retains earlier releases on the `v0.x` branch.

Its documented components are a Trainer using `verl`/vLLM, an API Gateway capturing model
interactions, and a Rollout Controller running agents locally or as Kubernetes Jobs. The
agent's real harness, tools, and execution environment remain in the rollout loop.
Training infrastructure and model-weight access are different requirements from deploying
a Foundry judge model or rewriting a prompt-agent configuration.

Use current v1 documentation when assessing adoption. Earlier Agent Lightning examples
and architecture descriptions are not presumed compatible. Upstream benchmark claims were
not reproduced; no training hardware, cluster, model weights, or package was installed.

Sources: [Microsoft repository README](https://raw.githubusercontent.com/microsoft/agent-lightning/main/README.md),
[current documentation](https://microsoft.github.io/agent-lightning/stable/),
[v1 concepts](https://microsoft.github.io/agent-lightning/stable/05-basics/).

## Repository Implications

**Recommendation, not implementation:** reuse Foundry evaluators and optimizer adapters
where their contracts fit; retain application-owned authorization, frozen comparison
inputs, result persistence, release acceptance, and rollback. The existing repository
optimization capability has additional host-owned rules; a native optimizer's ranked
candidate does not replace those rules by itself.

The native service and portal workflows documented here are not an installed replacement
for any existing local optimization runtime. No migration, package registration, model call,
resource grant, or deployment is authorized by this research collection.