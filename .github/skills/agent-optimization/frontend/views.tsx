import { SourceCodeViewer } from "@agentcraft/source-code";
import { MessagesSquare } from "lucide-react";
import { diffAgainstParent, failingCases, formatMs, formatPercent, formatScore, MISSING } from "./trajectory";
import type { CandidateVersion, Experiment, Metrics, RunStage, ToolVersion } from "./types";

export function ActionBullets({ items }: { items: string | string[] | undefined }) {
  if (!items) return null;
  return <ul className="opt-action-list">{(Array.isArray(items) ? items : [items]).map((item, index) => <li key={index}>{item}</li>)}</ul>;
}

function statusLabel(version: CandidateVersion): string {
  return version.status === "completed" ? "measured" : version.status;
}

export function MetricsSummary({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) return <p className="opt-empty" role="status">No score exists for this candidate: the scorer has not measured it.</p>;
  return <>
    <dl className="opt-facts opt-metrics">
      <div><dt>Macro-F1</dt><dd>{formatScore(metrics.macro_f1)}</dd></div>
      <div><dt>Accuracy</dt><dd>{formatScore(metrics.accuracy)}</dd></div>
      <div><dt>Macro precision</dt><dd>{formatScore(metrics.macro_precision)}</dd></div>
      <div><dt>Macro recall</dt><dd>{formatScore(metrics.macro_recall)}</dd></div>
      <div><dt>Weighted F1</dt><dd>{formatScore(metrics.weighted_f1)}</dd></div>
      <div><dt>Median latency</dt><dd>{formatMs(metrics.median_ms)}</dd></div>
      {metrics.mean_ms != null && <div><dt>Mean latency</dt><dd>{formatMs(metrics.mean_ms)}</dd></div>}
      <div><dt>p95 latency</dt><dd>{formatMs(metrics.p95_ms)}</dd></div>
      <div><dt>Elapsed</dt><dd>{formatMs(metrics.elapsed_ms)}</dd></div>
      <div><dt>Error rate</dt><dd>{formatPercent(metrics.error_rate)}</dd></div>
      <div><dt>Cases scored</dt><dd>{metrics.case_count}</dd></div>
    </dl>
    <table className="opt-table">
      <caption>Per-class precision, recall and F1</caption>
      <thead><tr><th scope="col">Grade</th><th scope="col">Precision</th><th scope="col">Recall</th><th scope="col">F1</th><th scope="col">Support</th></tr></thead>
      <tbody>
        {Object.entries(metrics.per_class).map(([grade, value]) => <tr key={grade}>
          <th scope="row">{grade}</th>
          <td>{formatScore(value.precision)}</td>
          <td>{formatScore(value.recall)}</td>
          <td>{formatScore(value.f1)}</td>
          <td>{value.support}</td>
        </tr>)}
      </tbody>
    </table>
    {metrics.confusion_matrix && <table className="opt-table opt-confusion">
      <caption>Confusion matrix: actual grade by predicted grade</caption>
      <thead><tr><th scope="col">Actual / predicted</th>{Object.keys(Object.values(metrics.confusion_matrix)[0] ?? {}).map((grade) => <th key={grade} scope="col">{grade}</th>)}</tr></thead>
      <tbody>{Object.entries(metrics.confusion_matrix).map(([grade, counts]) => <tr key={grade}><th scope="row">{grade}</th>{Object.entries(counts).map(([predicted, count]) => <td key={predicted} data-correct={predicted === grade}>{count}</td>)}</tr>)}</tbody>
    </table>}
  </>;
}

export function VersionList({ versions, selected, onSelect }: {
  versions: CandidateVersion[];
  selected: number | null;
  onSelect: (version: number) => void;
}) {
  return <div className="opt-version-list" aria-label="Agent versions">
    {[...versions].sort((left, right) => left.version - right.version).map((version) => <button key={version.version} type="button" data-version={version.version}
      aria-pressed={selected === version.version} onClick={() => onSelect(version.version)}>
      <span className="opt-version-head">v{version.version} {version.name}<em data-status={version.status}>{statusLabel(version)}</em></span>
      <small>{version.origin === "baseline" ? "baseline" : "CLI candidate"}
        {version.parent_version != null && ` \u00b7 from v${version.parent_version}`}
        {version.training_runs?.length ? ` \u00b7 Train ${formatScore(version.training_metrics?.macro_f1)} / Eval ${formatScore(version.evaluation_metrics?.macro_f1)}`
          : ` \u00b7 validation F1 ${formatScore(version.validation_metrics?.macro_f1)}`}</small>
    </button>)}
  </div>;
}

/** Every candidate stays inspectable, including the ones that failed or regressed. */
export function VersionsView({ experiment, version, tools, onInspect, onReplay, onDetector }: {
  experiment: Experiment;
  version: CandidateVersion | null;
  tools: ToolVersion[];
  onInspect: (id: string) => void;
  onReplay?: (stage: RunStage) => void;
  onDetector?: (version: number) => void;
}) {
  if (!version) return <p className="opt-empty" role="status">Select a candidate version.</p>;
  return <section className="opt-detail opt-agent-profile" aria-label={`Agent v${version.version} profile`}>
    <h3>v{version.version} {version.name}</h3>
    <dl className="opt-facts">
      <div><dt>Status</dt><dd>{statusLabel(version)}</dd></div>
      <div><dt>Origin</dt><dd>{version.origin === "baseline" ? "baseline" : "GitHub Copilot CLI"}</dd></div>
      <div><dt>Parent</dt><dd>{version.parent_version == null ? MISSING : `v${version.parent_version}`}</dd></div>
      <div><dt>Model</dt><dd>{version.model}</dd></div>
      <div><dt>Created</dt><dd>{version.created_at}</dd></div>
      <div><dt>Agent ID</dt><dd><code>{experiment.agent_id}</code></dd></div>
      <div><dt>Tool runtime</dt><dd>{experiment.tool_runtime ?? "Legacy SQL"}</dd></div>
      <div><dt>Situation detector</dt><dd>{version.situation_detector_version != null
        ? <button type="button" className="opt-detector-pin" onClick={() => onDetector?.(version.situation_detector_version!)}>Detector v{version.situation_detector_version}</button>
        : "Not recorded / pre-grouped incidents"}</dd></div>
      {experiment.workflow && <><div><dt>Knowledge tool</dt><dd>{version.knowledge_access ? "search_mitre_attack / read-only" : "Disabled for this version"}</dd></div>
        <div><dt>Actions</dt><dd>Proposed only / not executed</dd></div></>}
    </dl>
    {version.error && <p className="opt-error" role="alert">{version.error}</p>}
    <h4>Rationale</h4>
    <ActionBullets items={version.improvements?.length ? version.improvements : version.rationale || MISSING} />
    {version.process_contract && <section className="opt-process-receipt" aria-label="Replicable generation process">
      <h4>Joint generation</h4>
      {version.design_audit?.hypothesis && <p>{version.design_audit.hypothesis}</p>}
      <dl className="opt-facts">{Object.entries(version.design_audit?.levers ?? {}).map(([lever, decision]) => <div key={lever}>
        <dt>{lever.replaceAll("_", " ")}{version.lever_changes?.[lever] ? " / changed" : " / retained"}</dt><dd>{decision}</dd></div>)}</dl>
      {version.design_audit?.experiment && <details aria-label="Creative experiment design">
        <summary>{version.design_audit.experiment.approach_id} / {version.design_audit.experiment.kind}</summary>
        <dl className="opt-tool-descriptors">
          <div><dt>Mechanism</dt><dd>{version.design_audit.experiment.mechanism}</dd></div>
          <div><dt>Alternatives considered</dt><dd><ActionBullets items={version.design_audit.experiment.alternatives} /></dd></div>
          <div><dt>Disconfirmation</dt><dd>{version.design_audit.experiment.disconfirmation}</dd></div>
        </dl>
      </details>}
      {version.design_audit?.investigation_plan && <details aria-label="Question and evidence plan">
        <summary>Investigation questions / {version.design_audit.investigation_plan.questions.length}</summary>
        {version.design_audit.investigation_plan.questions.map(question => <section key={question.id} aria-label={question.question}>
          <h4>{question.question}</h4>
          <dl className="opt-tool-descriptors">
            <div><dt>Decision</dt><dd>{question.decision}</dd></div>
            <div><dt>Data</dt><dd>{question.data}</dd></div>
            <div><dt>View</dt><dd>{question.view}</dd></div>
            <div><dt>Tool / status</dt><dd>{question.tool ?? question.status}</dd></div>
            <div><dt>Limits</dt><dd>{question.limits}</dd></div>
          </dl>
        </section>)}
        <dl className="opt-tool-descriptors">
          <div><dt>Code changes</dt><dd><ActionBullets items={version.design_audit.investigation_plan.code_changes} /></dd></div>
          <div><dt>Agent changes</dt><dd><ActionBullets items={version.design_audit.investigation_plan.agent_changes} /></dd></div>
          <div><dt>Held fixed</dt><dd><ActionBullets items={version.design_audit.investigation_plan.held_fixed} /></dd></div>
          <div><dt>Acceptance checks</dt><dd><ActionBullets items={version.design_audit.investigation_plan.acceptance_checks} /></dd></div>
        </dl>
      </details>}
      {version.probe_receipt ? <details><summary>Verified development probe / {version.probe_receipt.case_ids.length} cases</summary>
        <dl className="opt-facts"><div><dt>Receipt</dt><dd><code>{version.probe_receipt.id}</code></dd></div>
          <div><dt>Exact proposal digest</dt><dd><code>{version.probe_receipt.proposal_digest}</code></dd></div>
          <div><dt>Probe macro-F1</dt><dd>{formatScore(version.probe_receipt.metrics.macro_f1)}</dd></div>
          <div><dt>Varying detector observations</dt><dd>{version.probe_receipt.detector_summary_varies ? "Verified" : "Not verified"}</dd></div></dl>
      </details> : <p className="opt-empty">Baseline / no predecessor probe</p>}
    </section>}
    {version.design_audit && <details className="opt-design-audit" aria-label="Design audit">
      <summary>Gap audit and design response</summary>
      <dl className="opt-tool-descriptors">
        {version.design_audit.approach && <div><dt>Approach</dt><dd>{version.design_audit.approach}</dd></div>}
        <div><dt>Observed gaps</dt><dd><ActionBullets items={version.design_audit.observed_gaps} /></dd></div>
        <div><dt>Changes</dt><dd><ActionBullets items={version.design_audit.changes} /></dd></div>
        <div><dt>Expected tradeoffs</dt><dd><ActionBullets items={version.design_audit.expected_tradeoffs} /></dd></div>
        {version.design_audit.lesson_from_parent && <div><dt>Lesson from parent</dt><dd>{version.design_audit.lesson_from_parent}</dd></div>}
        <div><dt>Parent run</dt><dd><code>{version.design_audit.parent_training_run_id ?? version.design_audit.parent_evaluation_id}</code></dd></div>
      </dl>
    </details>}
    <h4>Assigned tools</h4>
    <ul className="opt-profile-tools">{version.tool_ids.map((id) => {
      const tool = tools.find((tool) => tool.id === id);
      return <li key={id}><button type="button" onClick={() => onInspect(id)}>{tool ? `${tool.name} r${tool.revision ?? 1}` : id}</button></li>;
    })}</ul>
    {version.knowledge_access && experiment.knowledge_reference && <details><summary>Knowledge tool provenance</summary>
      <dl className="opt-facts"><div><dt>Source digest</dt><dd><code>{experiment.knowledge_reference.source_digest}</code></dd></div>
        <div><dt>Index</dt><dd>{experiment.knowledge_reference.index}</dd></div></dl>
    </details>}
    <h4>Prompt / system instruction</h4>
    <SourceCodeViewer code={version.system_prompt} filename="system-prompt.md" language="markdown" maxHeight={300} />
    <details className="opt-profile-config"><summary>Configuration</summary>
      <dl className="opt-facts">{Object.entries(version.runtime ?? { execution: "Legacy SQL then one model grade request", reasoning_effort: "none", max_output_tokens: 350 }).map(([name, value]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>
      {version.exploration_contract && <dl className="opt-facts">
        <div><dt>Exploration contract</dt><dd>{version.exploration_contract.version}</dd></div>
        <div><dt>Skill digest</dt><dd><code>{version.exploration_contract.skill_digest}</code></dd></div>
        <div><dt>Case workers</dt><dd>{version.exploration_contract.workers}</dd></div>
      </dl>}
    </details>
    <h4>Change against parent</h4>
    <table className="opt-table">
      <thead><tr><th scope="col">Field</th><th scope="col">Parent</th><th scope="col">This version</th></tr></thead>
      <tbody>
        {diffAgainstParent(version, experiment.versions).map((row) => <tr key={row.field} data-changed={row.changed}>
          <th scope="row">{row.field}</th><td>{row.before}</td><td>{row.after}</td>
        </tr>)}
      </tbody>
    </table>
    {experiment.stage_counts ? <FullRunsView version={version} onReplay={onReplay} /> : <>
    <h4>Validation metrics</h4>
    <MetricsSummary metrics={version.validation_metrics ?? null} />
    {version.evaluations.at(-1)?.audit?.validation && <table className="opt-table">
      <caption>Validation stress slices</caption>
      <thead><tr><th>Evidence size</th><th>Cases</th><th>Macro-F1</th><th>Accuracy</th><th>Errors</th></tr></thead>
      <tbody>{Object.entries(version.evaluations.at(-1)?.audit?.validation.evidence_bands ?? {}).map(([band, metrics]) =>
        <tr key={band}><th scope="row">{band}</th><td>{metrics.case_count}</td><td>{formatScore(metrics.macro_f1)}</td><td>{formatScore(metrics.accuracy)}</td><td>{formatPercent(metrics.error_rate)}</td></tr>)}</tbody>
    </table>}
    {(version.evaluations.at(-1)?.validation_comparison ?? version.evaluations.at(-1)?.comparison) &&
      <p>{(version.evaluations.at(-1)?.validation_comparison ?? version.evaluations.at(-1)?.comparison)?.reason}</p>}
    <h4>Evaluation history</h4>
    {version.evaluations.map((evaluation, index) => <details key={evaluation.id}>
      <summary>Run {index + 1}: {evaluation.status}, validation F1 {formatScore(evaluation.metrics?.validation_macro_f1)}, {evaluation.completed_at ?? evaluation.started_at}</summary>
      <p><code>{evaluation.id}</code></p>
      {evaluation.error && <p className="opt-error">{evaluation.error}</p>}
      <MetricsSummary metrics={evaluation.validation_metrics ?? null} />
      <table className="opt-table opt-cases">
        <thead><tr><th scope="col">Case</th><th scope="col">Split</th><th scope="col">Expected</th><th scope="col">Predicted</th><th scope="col">Result</th></tr></thead>
        <tbody>{evaluation.cases.map((item) => <tr key={item.case_id}>
          <th scope="row"><code>{item.case_id}</code></th><td>{item.split}</td><td>{item.expected}</td>
          <td>{item.predicted ?? MISSING}</td><td>{item.error || (item.correct ? "correct" : "incorrect")}</td>
        </tr>)}</tbody>
      </table>
    </details>)}
    <details><summary>Incorrect or errored cases</summary><FailuresView version={version} /></details>
    </>}
  </section>;
}

function FullRunsView({ version, onReplay }: { version: CandidateVersion; onReplay?: (stage: RunStage) => void }) {
  return <div className="opt-stage-history">
    {(["training", "evaluation"] as const).map((stage) => {
      const runs = stage === "training" ? version.training_runs ?? [] : version.evaluations;
      const latest = runs.at(-1);
      return <section key={stage} aria-label={`${stage} measurements`}>
        <header className="opt-stage-heading"><h4>{stage === "training" ? "Training" : "Evaluation"}</h4>
          {onReplay && <button type="button" disabled={!latest?.exemplars?.best || !latest.exemplars.worst}
            onClick={() => onReplay(stage)} title={`Compare best and worst ${stage} runs`} aria-label={`Compare ${stage} runs`}>
            <MessagesSquare size={16} aria-hidden="true" />Compare runs</button>}
        </header>
        <p className="opt-empty">{latest ? `${latest.status} / ${(latest.cases_finished ?? 0).toLocaleString()} of ${(latest.case_count ?? 0).toLocaleString()} cases` : "Not started"}</p>
        {latest?.status === "running" && <progress aria-label={`${stage} progress`} value={latest.cases_finished ?? 0} max={latest.case_count} />}
        {runs.map((run, index) => <details key={run.id} open={run.status === "completed" && index === runs.length - 1}>
          <summary>Run {index + 1}: macro-F1 {formatScore(run.metrics?.macro_f1)}</summary>
          {run.error && <p className="opt-error">{run.error}</p>}
          <MetricsSummary metrics={run.metrics} />
        </details>)}
      </section>;
    })}
  </div>;
}

export function FailuresView({ version }: { version: CandidateVersion | null }) {
  const cases = failingCases(version);
  if (!version) return <p className="opt-empty" role="status">Select a candidate version.</p>;
  if (!version.evaluations.length) return <p className="opt-empty" role="status">This candidate has no evaluation run yet.</p>;
  if (!cases.length) return <p className="opt-empty" role="status">No incorrect or errored case in the latest evaluation.</p>;
  return <section className="opt-detail">
    <h3>v{version.version}: {cases.length} failing cases</h3>
    <table className="opt-table opt-cases">
      <thead><tr>
        <th scope="col">Case</th><th scope="col">Split</th><th scope="col">Expected</th>
        <th scope="col">Predicted</th><th scope="col">Latency</th><th scope="col">Reason</th>
      </tr></thead>
      <tbody>
        {cases.map((item) => <tr key={item.case_id}>
          <th scope="row"><code>{item.case_id}</code></th>
          <td>{item.split}</td>
          <td>{item.expected}</td>
          <td>{item.predicted ?? MISSING}</td>
          <td>{formatMs(item.elapsed_ms)}</td>
          <td>{item.error ? <span className="opt-error-text">{item.error}</span> : item.rationale}</td>
        </tr>)}
      </tbody>
    </table>
  </section>;
}
