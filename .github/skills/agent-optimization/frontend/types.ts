/**
 * Wire types for `/api/cyber/optimization`.
 *
 * The task is analyst-grade classification of alert evidence — TruePositive,
 * BenignPositive, FalsePositive — not raw-log detection, so grade classes are
 * whatever the dataset declares in `labels` rather than a hardcoded union.
 */

export type VersionStatus = "pending" | "tuning" | "tuned" | "running" | "completed" | "failed" | "cancelled";
export type RunStage = "training" | "evaluation";
export type OptimizationProtocol = "smoke" | "stress-10" | "full-10" | "joint-smoke" | "joint-10" | "joint-12";
export type ExperimentStatus = "baseline_running" | "ready" | "running" | "completed" | "failed" | "cancelled";
export type VersionOrigin = "baseline" | "copilot-cli";

export interface ExplorationContract {
  version: string;
  minimums: Record<string, number>;
  required_kinds: string[];
  first_successor_min_tools: number;
  workers: number;
  skill_digest: string;
}

export interface InvestigationPlan {
  version: string;
  questions: { id: string; question: string; decision: string; data: string; view: string; tool: string | null; status: "tool" | "unavailable" | "deferred"; limits: string }[];
  code_changes: string[];
  agent_changes: string[];
  held_fixed: string[];
  acceptance_checks: string[];
}

export interface ClassMetrics {
  precision: number;
  recall: number;
  f1: number;
  support: number;
  tp?: number;
  fp?: number;
  fn?: number;
  tn?: number;
}

export interface Metrics {
  macro_f1: number;
  accuracy: number;
  median_ms: number;
  mean_ms?: number;
  p95_ms: number;
  elapsed_ms: number;
  error_rate: number;
  case_count: number;
  per_class: Record<string, ClassMetrics>;
  validation_macro_f1: number;
  development_macro_f1: number;
  macro_precision?: number;
  macro_recall?: number;
  weighted_f1?: number;
  confusion_matrix?: Record<string, Record<string, number>>;
}

export interface CaseResult {
  case_id: string;
  split: string;
  expected: string;
  predicted: string | null;
  correct: boolean;
  elapsed_ms: number;
  rationale: string;
  error?: string;
}

export interface Evaluation {
  id: string;
  status: VersionStatus;
  started_at: string;
  completed_at?: string;
  metrics: Metrics | null;
  cases: CaseResult[];
  stage?: RunStage;
  cases_finished?: number;
  case_count?: number;
  exemplars?: Partial<Record<"best" | "worst", Pick<CaseResult, "case_id" | "correct" | "expected" | "predicted" | "elapsed_ms" | "error">>>;
  error?: string;
  validation_metrics?: Metrics | null;
  validation_comparison?: Evaluation["comparison"];
  audit?: Record<string, { metrics: Metrics; evidence_bands: Record<string, Metrics>; confusions: { actual: string; predicted: string; count: number }[]; errors: number }> | null;
  comparison?: {
    reference_version: number;
    reference_evaluation_id: string;
    verdict: string;
    reason: string;
    validation_macro_f1_delta: number;
    median_ms_delta: number;
    error_rate_delta: number;
  } | null;
}

export interface CandidateVersion {
  version: number;
  name: string;
  parent_version: number | null;
  system_prompt: string;
  model: string;
  /** Exact tool-version identifiers, pinned. Never a tool name. */
  tool_ids: string[];
  situation_detector_version?: number;
  situation_detector_digest?: string;
  knowledge_access?: boolean;
  process_contract?: { version: string; sequence: string[]; levers: string[] };
  exploration_contract?: ExplorationContract;
  probe_receipt?: { id: string; created_at: string; proposal_digest: string; case_ids: string[]; metrics: Metrics; detector_summary_varies: boolean } | null;
  lever_changes?: Record<string, boolean>;
  created_at: string;
  status: VersionStatus;
  rationale: string;
  origin: VersionOrigin;
  metrics: Metrics | null;
  evaluations: Evaluation[];
  training_runs?: Evaluation[];
  training_metrics?: Metrics | null;
  evaluation_metrics?: Metrics | null;
  mean_latency_ms?: number | null;
  improvements?: string[];
  error?: string;
  validation_metrics?: Metrics | null;
  runtime?: Record<string, string | number>;
  generation?: number;
  design_audit?: {
    hypothesis?: string; levers?: Record<string, string>;
    investigation_plan?: InvestigationPlan;
    experiment?: { approach_id: string; kind: string; mechanism: string; alternatives: string[]; disconfirmation: string };
    parent_evaluation_id?: string; parent_training_run_id?: string; approach?: string;
    observed_gaps: string | string[]; changes: string | string[];
    expected_tradeoffs: string | string[]; lesson_from_parent?: string;
  } | null;
}

export interface ExperimentEvent {
  at: string;
  event: string;
  detail: string;
}

export interface Experiment {
  id: string;
  name: string;
  /** Present on the wire; never rendered. */
  owner_id?: string;
  agent_id: string;
  created_at: string;
  dataset_id: string;
  status: ExperimentStatus;
  error?: string;
  objective: string;
  case_count: number;
  versions: CandidateVersion[];
  events: ExperimentEvent[];
  rejections?: { id: string; at: string; proposal: Record<string, unknown>; error: string }[];
  tool_runtime?: string;
  protocol?: OptimizationProtocol;
  process_contract?: { version: string; sequence: string[]; levers: string[] };
  exploration_contract?: ExplorationContract;
  stage_counts?: Record<RunStage, number>;
  evaluation_policy?: string;
  workflow?: { version: number; input: string; stages: string[]; knowledge_tool: string; action_policy: string; scored: string; unscored: string[] };
  knowledge_reference?: { name: string; source_digest: string; endpoint: string; index: string; access: string } | null;
  interventions?: { id: string; at: string; after_version: number; actor: string; guidance: string }[];
  repeat_comparison?: {
    baseline_version: number; candidate_version: number;
    baseline_validation_f1: number[]; candidate_validation_f1: number[];
  };
  final_verification?: { status: VersionStatus; agent_version: number; metrics?: Metrics; error?: string };
}

export interface ToolVersion {
  id: string;
  name: string;
  version: number;
  description: string;
  sql?: string;
  code?: string;
  language?: "python" | "sql";
  queries?: string;
  returns?: string;
  logic?: string;
  family?: string;
  digest: string;
  experiment_id: string;
  agent_versions: number[];
  revision?: number;
  lineage_id?: string;
  supersedes?: string | null;
  change_rationale?: string[];
  introduced_agent_version?: number;
  first_agent_version?: number | null;
  last_agent_version?: number | null;
  status: "validated" | "rejected";
  created_at: string;
}

export interface DatasetInfo {
  problem_statement?: string;
  objective?: string;
  dataset_id: string;
  counts: { evidence: number; development: number; validation: number; final: number };
  features: string[];
  labels: string[];
  time_start: string;
  time_end: string;
  limitations: string[];
}

export interface Snapshot {
  available: boolean;
  creative_supported?: boolean;
  detail?: string;
  dataset?: DatasetInfo | null;
  experiments: Experiment[];
  tools: ToolVersion[];
  detectors?: DetectorVersion[];
  detector_reference?: ApplicationDetector | null;
  knowledge_configured?: boolean;
}

export interface DetectorVersion {
  version: number;
  name: string;
  parent_version: number | null;
  digest: string;
  scope: string;
  created_at: string;
  change_rationale: string[];
  experiment_id: string;
  agent_versions: number[];
  first_agent_version: number | null;
  last_agent_version: number | null;
  schema_version?: number;
  configuration_digest?: string;
  configuration?: { version: string; max_window_seconds: number; rule_sets: { id: string; name: string; enabled: boolean; rules: { id: string; enabled: boolean }[] }[] };
  rules: { id: string; name: string; description: string; code: string; digest: string; revision: number; query?: string; rule_set_id?: string; enabled?: boolean; parameters?: Record<string, unknown> }[];
}

export interface ApplicationDetector {
  name: string;
  version: string;
  scope: string;
  rules: { rule_id: string; version: string; name: string; description: string; query: string; threshold: number; score: number; role: string; evidence_semantics: string; technique_ids: string[] }[];
}

export interface TablePreview {
  columns: string[];
  rows: unknown[][];
}

export interface RunExample {
  run_id: string;
  agent_version: number;
  stage: RunStage;
  selection: "best" | "worst";
  case: CaseResult & {
    transcript: {
      request: { model: string; instructions: string; input: string; max_output_tokens: number };
      evidence: {
        time_window: { start: string; end: string }; tools: { name: string; result: unknown }[];
        situation_detector?: { version: number; digest: string; situations: { rule_id: string; rule_revision: number; name: string; matched: boolean; facts: string[]; technique_ids: string[] }[]; rule_results: unknown[] };
        knowledge?: { tool: string; arguments: Record<string, unknown>; result: Record<string, unknown> };
      };
      response: { grade: string; rationale?: string; diagnosis?: string; proposed_actions?: string[]; citations?: string[] } | null;
      error: string;
      model_call_attempted?: boolean;
      tool_ids: string[];
    };
  };
}

/** The optimizer's agent versions as the agent editor's catalogue reports them. */
export interface OptimizationAgentSummary {
  id: string;
  name: string;
  experiment_id: string;
  versions: CandidateVersion[];
}
