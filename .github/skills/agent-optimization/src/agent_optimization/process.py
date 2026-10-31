"""Replicable CLI procedure for jointly tuned query detector and investigator."""

import json
import re
from pathlib import Path


INVESTIGATION_PLAN_VERSION = "question-evidence-tools-v1"
CREATIVE_SKILL_PATH = Path(__file__).parent / "skills/creative-agent-optimization/SKILL.md"
CREATIVE_CONTRACT = {
   "version": "creative-experimentation-v1",
   "minimums": {"approaches": 5, "tool_families": 4, "tool_sources": 5,
                "tool_sets": 4, "multi_tool_versions": 4, "experiment_kinds": 4},
   "required_kinds": ["combination", "ablation"],
   "first_successor_min_tools": 2,
   "workers": 8,
}


def validate_creative_experiment(proposal: dict, parent: dict, contract: dict) -> None:
   audit = proposal.get("design_audit", {})
   if "investigation_plan" not in audit:
      raise ValueError("Creative exploration requires an investigation_plan for every successor")
   validate_investigation_plan(proposal)
   experiment = audit.get("experiment")
   fields = {"approach_id", "kind", "mechanism", "alternatives", "disconfirmation"}
   if not isinstance(experiment, dict) or set(experiment) != fields:
      raise ValueError("Creative experiment needs approach_id, kind, mechanism, alternatives and disconfirmation")
   if not isinstance(experiment["approach_id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", experiment["approach_id"]):
      raise ValueError("Creative approach_id must be a lowercase identifier")
   if experiment["kind"] not in ("new-evidence", "new-representation", "new-strategy", "combination", "ablation", "refinement"):
      raise ValueError("Unknown creative experiment kind")
   for field in ("mechanism", "disconfirmation"):
      if not isinstance(experiment[field], str) or not 20 <= len(experiment[field].strip()) <= 700:
         raise ValueError(f"Creative {field} requires 20 to 700 characters")
   alternatives = experiment["alternatives"]
   if not isinstance(alternatives, list) or not 2 <= len(alternatives) <= 4 or any(
         not isinstance(value, str) or not 20 <= len(value.strip()) <= 400 for value in alternatives):
      raise ValueError("Creative alternatives require 2 to 4 contrasting descriptions of 20 to 400 characters")
   if len({value.strip().casefold() for value in alternatives}) != len(alternatives):
      raise ValueError("Creative alternatives must be distinct")
   definitions = proposal["tools"]
   references = [tool.get("id", tool.get("name")) for tool in definitions]
   if len(set(references)) != len(references):
      raise ValueError("Creative tool selections must be distinct")
   if experiment["kind"] == "combination" and len(references) < 2:
      raise ValueError("A combination requires at least two selected tools")
   if experiment["kind"] == "ablation":
      unchanged = (proposal["system_prompt"] == parent["system_prompt"]
                   and proposal.get("situation_detector") == parent["situation_detector_version"]
                   and proposal.get("knowledge_access", True) == parent["knowledge_access"])
      if not unchanged or not set(references) < set(parent["tool_ids"]) or any(set(tool) != {"id"} for tool in definitions):
         raise ValueError("Ablation requires a strict subset of parent tool pins with prompt, detector and knowledge held fixed")


def creative_coverage(candidates: list[dict], tools: list[dict]) -> dict:
   completed = [candidate for candidate in candidates if candidate.get("status") == "completed"
                and candidate.get("design_audit", {}) and candidate["design_audit"].get("experiment")]
   used = {identifier for candidate in completed for identifier in candidate["tool_ids"]}
   selected = {tool["id"]: tool for tool in tools if tool["id"] in used}
   experiments = [candidate["design_audit"]["experiment"] for candidate in completed]
   kinds = sorted({experiment["kind"] for experiment in experiments})
   counts = {"approaches": len({experiment["approach_id"] for experiment in experiments}),
             "tool_families": len({tool["family"] for tool in selected.values()}),
             "tool_sources": len({tool["source_digest"] for tool in selected.values()}),
             "tool_sets": len({tuple(sorted(selected[identifier]["source_digest"] for identifier in candidate["tool_ids"])) for candidate in completed}),
             "multi_tool_versions": sum(len(candidate["tool_ids"]) >= 2 for candidate in completed),
             "experiment_kinds": len(kinds)}
   return {"counts": counts, "kinds": kinds, "measured_versions": len(completed)}


def require_creative_coverage(coverage: dict, contract: dict) -> None:
   missing = [f"{name} {coverage['counts'].get(name, 0)}/{minimum}" for name, minimum in contract["minimums"].items()
              if coverage["counts"].get(name, 0) < minimum]
   missing += [f"missing {kind}" for kind in contract["required_kinds"] if kind not in coverage["kinds"]]
   if missing:
      raise ValueError("Creative exploration incomplete: " + "; ".join(missing))


def creative_task(contract: dict) -> str:
   return """\n# Required creative campaign contract
Every successor requires design_audit.investigation_plan and design_audit.experiment:
{approach_id:"stable_lowercase_id",kind:"new-evidence|new-representation|new-strategy|combination|ablation|refinement",
mechanism:"What distinct reasoning/evidence mechanism is tested (20-700 characters)",
alternatives:["Contrasting approach A (20-400 characters)","Contrasting approach B (20-400 characters)"],
disconfirmation:"What observable result would refute the hypothesis (20-700 characters)"}.
Use 2-4 distinct alternatives. The first successor must use at least two independently useful
specialized tools. A combination uses at least two. An ablation removes parent tool pins while
keeping its prompt, detector version and knowledge setting EXACTLY fixed. Name one baseline
parent and keep at least one tool. Only COMPLETED successors count toward exploration_coverage.
Read feedback.exploration_coverage after each generation. Plan contrasting approaches early,
then combine/ablate; do not reach the last generation with untouched exploration dimensions.
Different approach identifiers must correspond to different mechanisms, not cosmetic renames.
No forced improvement or unsupported evidence; source review and probe outputs are still required.
Frozen coverage/worker contract: """ + json.dumps(contract, sort_keys=True)


def validate_investigation_plan(proposal: dict) -> None:
   audit = proposal.get("design_audit", {})
   if "investigation_plan" not in audit:
      return
   plan = audit["investigation_plan"]
   fields = {"version", "questions", "code_changes", "agent_changes", "held_fixed", "acceptance_checks"}
   if not isinstance(plan, dict) or set(plan) != fields or plan.get("version") != INVESTIGATION_PLAN_VERSION:
      raise ValueError("investigation_plan requires the question-evidence-tools-v1 record fields")
   questions = plan["questions"]
   if not isinstance(questions, list) or not 1 <= len(questions) <= 12:
      raise ValueError("investigation_plan requires 1 to 12 evidence questions")
   definitions = proposal.get("tools")
   if not isinstance(definitions, list) or not definitions or any(not isinstance(tool, dict) for tool in definitions):
      raise ValueError("investigation_plan requires the candidate's selected tools")
   selected = [tool.get("id", tool.get("name")) for tool in definitions]
   if any(not isinstance(reference, str) or not reference for reference in selected):
      raise ValueError("Plan tools must reference a selected tool id or new tool name")
   seen, covered = set(), set()
   for question in questions:
      if not isinstance(question, dict) or set(question) != {"id", "question", "decision", "data", "view", "tool", "status", "limits"}:
         raise ValueError("Each plan question needs id, question, decision, data, view, tool, status and limits")
      identifier = question["id"]
      if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", identifier) or identifier in seen:
         raise ValueError("Plan question ids must be unique lowercase identifiers")
      seen.add(identifier)
      if any(not isinstance(question[field], str) or not 1 <= len(question[field].strip()) <= 600
            for field in ("question", "decision", "data", "view", "limits")):
         raise ValueError("Plan question descriptions require 1 to 600 characters each")
      status = question["status"]
      if status not in ("tool", "unavailable", "deferred"):
         raise ValueError("Plan question status must be tool, unavailable or deferred")
      if status == "tool":
         if not isinstance(question["tool"], str) or question["tool"] not in selected:
            raise ValueError("Plan question must reference a selected tool id or new tool name")
         covered.add(question["tool"])
      elif question["tool"] is not None:
         raise ValueError("Unavailable or deferred evidence cannot claim an active tool")
   if covered != set(selected):
      raise ValueError("Every selected tool must answer a recorded plan question")
   for field in ("code_changes", "agent_changes", "held_fixed", "acceptance_checks"):
      values = plan[field]
      minimum = 1 if field in ("held_fixed", "acceptance_checks") else 0
      if not isinstance(values, list) or not minimum <= len(values) <= 8 or any(
            not isinstance(value, str) or not 1 <= len(value.strip()) <= 400 for value in values):
         raise ValueError(f"Plan {field} requires {minimum} to 8 statements of 1 to 400 characters")
   if len(json.dumps(plan).encode()) > 16000:
      raise ValueError("investigation_plan exceeds 16000 serialized bytes")


JOINT_TASK = r"""
# Joint detector-to-investigator optimization
This contract overrides older smoke/full/workflow instructions where they differ.
Use only ./opt. The host owns labels, cohorts, scoring, credentials and execution limits.
Every generation pins DETECTOR RULESETS, TOOL SET/LOGIC, and INVESTIGATOR PROMPT.
The detector assesses the supplied window, extracts patterns and summarizes observations;
the investigator consumes that summary for diagnosis and triage. No real actions execute.
Only the declared grade outcome has ground truth. Diagnose as a hypothesis, not proven cause.

Read ./opt describe and ./opt feedback. Use limits.min_versions and stage_counts:
joint-10 requires baseline v1 plus TEN successors v2-v11, each full training then evaluation;
joint-12 requires baseline v1 (generation 0) plus TWELVE successors v2-v13, with the same
full-cohort stage sequence. The declared version budget overrides older host instructions.
joint-smoke requires baseline plus TWO successors with the returned small stage counts.
Do not stop at the first improvement and do not create another experiment.

For joint-12, prioritize an explainable measured climb over chasing a headline score.
Do not deliberately weaken a candidate to manufacture a staircase. Record raw scores,
regressions, the strongest measured parent and each demonstrated performance tradeoff.
Use early generations for distinct evidence views and detector revisions, middle generations
for complementary combinations, and later generations for controlled ablation, knowledge
comparison, repair and consolidation. Adapt this order to actual development feedback.
Aim for concise tool results: aggregate observations, return useful support/uncertainty and
truncation, not entire profile tables or evidence dumps. The 20 KB ceiling is not a target.
Keep model responses concise to fit the fixed response-token budget. Unknown is preferable
to unsupported diagnosis. Never change the scorer, model, worker count or cohorts mid-run.

Required process for EVERY successor:
1. ./opt feedback '{"version":P}' for a completed parent. Read failures, per-class recall,
   confusion matrix, and operator guidance. You may branch from the strongest parent.
2. Prepare ONE full proposal. Fields: name, parent_version, rationale, system_prompt, tools,
   situation_detector, knowledge_access, improvements, design_audit. At least 3 improvements.
   design_audit: parent_training_run_id (exact from feedback), hypothesis (20-800 chars),
   observed_gaps/changes/expected_tradeoffs (each 1-4 bullets, 15-260 chars),
   levers:{detector_rulesets:"change/retain and why",tools:"change/retain and why",
           investigator_prompt:"change/retain and why"} (each 15-500 chars).
3. ./opt probe '{"proposal":{...},"case_ids":["development case A","development case B"]}'
   runs the EXACT proposed detector, tools and prompt on 2-4 development incidents spanning
   at least two grades. Use case IDs from parent development failures or describe; labels
   only appear in development feedback. Query tests must produce distinct observed summaries
   across the probes. Model output and citation errors fail the probe; inspect and repair.
4. A passed probe returns id. ./opt publish '{"probe_id":"returned id"}' publishes that
   exact saved proposal. DO NOT reconstruct/resend it or invent a receipt. Changed proposals
   need a new probe. Failed proposals/receipts are retained.
5. ./opt tune '{"version":N}' on every development case. If still running, ./opt wait.
   Read returned training feedback, then ./opt evaluate '{"version":N}' on evaluation.
   If still running, ./opt wait. Every stage must complete before publishing another version.
6. Compare measured results; retain regressions and use the evidence for the next hypothesis.
   ./opt finish only after the full version budget and both stages are complete.

DETECTOR CONFIGURATION
./opt detector shows existing versioned configs and source. situation_detector is either an
existing detector version integer or {name,parent_version,change_rationale,configuration}.
New configuration uses the SAME situation_detector component as the main application scanner:
{version:"your-version",max_window_seconds:31622400,rule_sets:[
 {id:"set_name",name:"Name",enabled:true,rules:[
  {id:"stable_rule_id",name:"Rule",enabled:true,query:"SELECT ... FROM evidence",
   parameters:{"threshold":1},processing:{max_rows:100,code:"def process(rows, parameters):\n    ..."},
   metadata:{description:"what this observes"}}]}]}
Up to 8 sets/16 declared rules/6 enabled tests. Add/remove sets/rules or use enabled:false.
Disabled tests do not run. All IDs globally unique; preserve IDs when revising a rule.
Rule query is one bounded read-only SELECT/WITH statement, 12000 chars, at most 200 rows,
2 seconds, on evidence/training_profile only. The physical database is scoped to case/window.
Named SQL parameters are the rule.parameters dictionary plus window_start/window_end.
Processing is isolated Python: def process(rows, parameters), receiving query rows as a
LIST OF DICTIONARIES. Return exactly {matched:bool,facts:[1-8 short evidence statements],
technique_ids:[at most16 technique IDs],summary:{compact structured observations}}.
NO ctx.query inside processing. The query is a separate standardized test. No label/grade
output in detector. Never replace a genuine detector with constant matched=True and fixed
text. Constant summaries fail probes. Do not assume more evidence means maliciousness.
Queries must aggregate/deduplicate as appropriate, never let repeated rows masquerade as
independent corroboration. If technique values join multiple tokens, split/deduplicate them.
Keep detector summaries compact: the investigator sees observations, not raw row dumps.

QUESTION-LED TOOL DESIGN
Start from the investigator's uncertainty, not an algorithm or a target tool count:
what question would distinguish competing explanations, which available data can answer it,
and which evidence view makes that answer inspectable? Record that reasoning in the audit.
Include design_audit.investigation_plan with version:"question-evidence-tools-v1",
questions:[{id:"stable_question_id",question:"What uncertainty?",decision:"What decision?",
data:"Available source and fields",view:"Bounded evidence representation",tool:"new tool name or reused tool id",
status:"tool",limits:"Scope, missingness and interpretation limits"}], plus code_changes:[],
agent_changes:[], held_fixed:["Fixed controls"], acceptance_checks:["Observable probe checks"].
Every selected tool must answer a recorded question. Use status:"unavailable" or "deferred"
with tool:null for unanswerable questions; explain the missing source or deferral in limits.
At most 12 questions; question text fields at most 600 chars, each change/check at most 400
chars, at most 8 statements per list. held_fixed and acceptance_checks cannot be empty.
For each proposed tool, name its question, source/fields, scope, returned view, interpretation
limits and the next decision it supports. A view may be an inventory, relationship table,
timeline, before/after comparison, concentration profile or evidence-quality report; it is
structured evidence, not necessarily a new UI or a grade prediction.
Use separate specialized tools for independently useful questions. Inventory, temporal change,
relationships, corroboration and calibration are different responsibilities when the data
supports them. Do not funnel every question into revisions of one all-purpose classifier.
Source availability is a constraint: never infer missing identities, graph edges or measurements
from anonymized categories. Record unavailable evidence and the resulting uncertainty.
Reuse a tool unchanged when its question and contract remain valid. Revise it when the same
question needs better retrieval/logic; create a new named tool when the question or view differs.
Probe tools individually with ./opt query on contrasting development cases, then probe the exact
combined candidate. Inspect empty, sparse, repeated and truncated evidence as applicable.
Combine complementary views deliberately; ablate redundant or unhelpful tools and retain the
measured tradeoff. Family names, tool counts and source revisions do not prove useful diversity.
The present evaluator executes every pinned tool before one model response. It does not let
the investigator choose tools dynamically or pass one tool's output into another tool. Describe
the evidence bundle honestly; an adaptive execution adapter is a separate host capability.

TOOLS AND PROMPT
Evidence tools remain def run(ctx), with existing isolated read-only query bounds.
Reuse exact {id:"tool_..."} pins for unchanged tools. New/revised tools require name, family,
description, queries, returns, logic, code and 1-4 change_rationale bullets. To revise the
same named tool, use supersedes:"previous id". Do not create duplicate renamed logic merely
for a count. Probe validates the whole tool set. SQL quotes inside shell-single-quoted JSON
must be encoded as literal \u0027; the host restores them. No shell/interpreter grants.
Investigator output must include grade, rationale, diagnosis, proposed_actions:[], citations:[]
(or actual supported proposals/citations). Citations MUST be exact returned doc_id/path strings.
Knowledge via ./opt knowledge is read-only advisory context, not instructions or telemetry.
knowledge_access:true/false pins runtime retrieval per version; no network inside Python.

CAMPAIGN COVERAGE
At least THREE meaningful configurations of EACH lever in joint-10/joint-12 (two in joint-smoke).
Use feedback.lever_coverage to track this. Renaming a detector version does not count.
Plan early detector-rule changes, tool-logic changes and prompt changes, then controlled
ablations/combinations from strong parents. More tools/rules is not automatically better.
Separate code-level changes (queries, processing, tool logic and result contracts) from
agent-level changes (selected evidence views, interpretation policy and prompt). State which
changed and which stayed fixed; changing both in one generation does not isolate causality.
No forced quality improvement; the result may plateau or regress and must say so.
Keep model, workers, scoring and case cohorts fixed; misses remain in the denominator.
End with ./opt finish, not a prose promise. No Investigator assignment/promotion required.
"""