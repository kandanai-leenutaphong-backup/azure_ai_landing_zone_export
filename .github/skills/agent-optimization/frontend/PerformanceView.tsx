import { TrajectoryChart } from "./TrajectoryChart";
import { formatMs, formatScore, macroF1, medianMs, versionAssessment } from "./trajectory";
import type { Experiment } from "./types";
import { ActionBullets, MetricsSummary } from "./views";

export function PerformanceView({ experiment, selected, onSelect }: {
  experiment: Experiment; selected: number | null; onSelect: (version: number) => void;
}) {
  const versions = [...experiment.versions].sort((left, right) => left.version - right.version);
  const validation = versions.map((version) => ({ ...version, metrics: version.validation_metrics ?? null }));
  const full = experiment.protocol === "full-10" || Boolean(experiment.workflow);
  const training = versions.map((version) => ({ ...version, metrics: version.training_metrics ?? null }));
  const evaluation = versions.map((version) => ({ ...version, metrics: version.evaluation_metrics ?? null }));
  const latency = versions.map((version) => {
    const metrics = version.training_metrics && version.evaluation_metrics;
    return { ...version, metrics: metrics && version.mean_latency_ms != null ? { ...metrics, mean_ms: version.mean_latency_ms } : null };
  });
  return <div className="opt-performance-content">
    {experiment.workflow && <p className="opt-empty">{experiment.workflow.scored}. Diagnosis and proposed actions are unscored.</p>}
    {full ? <>
      <TrajectoryChart title="Training macro-F1" versions={training} pick={macroF1} format={(value) => value.toFixed(3)} selected={selected} onSelect={onSelect} />
      <TrajectoryChart title="Evaluation macro-F1" versions={evaluation} pick={macroF1} format={(value) => value.toFixed(3)} selected={selected} onSelect={onSelect} />
      <TrajectoryChart title="Average case latency" versions={latency} pick={(metrics) => metrics.mean_ms!} format={(value) => `${Math.round(value)} ms`} selected={selected} onSelect={onSelect} />
    </> : <>
    <TrajectoryChart title="Validation macro-F1" versions={validation} pick={macroF1} format={(value) => value.toFixed(3)}
      selected={selected} onSelect={onSelect} />
    <TrajectoryChart title="Validation median latency" versions={validation} pick={medianMs} format={(value) => `${Math.round(value)} ms`}
      selected={selected} onSelect={onSelect} />
    </>}
    {experiment.repeat_comparison && <section aria-label="Unchanged repeat measurements">
      <h3 className="opt-section-title">Unchanged repeats</h3>
      <table className="opt-table">
        <thead><tr><th>Agent</th><th>Validation macro-F1, run order</th></tr></thead>
        <tbody>
          <tr><th>v{experiment.repeat_comparison.baseline_version} baseline</th>
            <td>{experiment.repeat_comparison.baseline_validation_f1.map(formatScore).join(" / ")}</td></tr>
          <tr><th>v{experiment.repeat_comparison.candidate_version} candidate</th>
            <td>{experiment.repeat_comparison.candidate_validation_f1.map(formatScore).join(" / ")}</td></tr>
        </tbody>
      </table>
    </section>}
    <h3 className="opt-section-title">Agent progression</h3>
    {versions.map((version) => {
      const assessment = versionAssessment(full ? { ...version, validation_metrics: version.evaluation_metrics } : version);
      const parent = versions.find((item) => item.version === version.parent_version);
      const interventions = experiment.interventions?.filter((record) => record.after_version === version.version) ?? [];
      return <article key={version.version} className="opt-progression-card" data-agent-version={version.version}>
        <button type="button" aria-pressed={selected === version.version} onClick={() => onSelect(version.version)}>
          <span>v{version.version} {version.name}</span><small>{version.status}</small>
        </button>
        <time>{new Date(version.created_at).toLocaleString()}</time>
        <p className="opt-score-line">{full ? `Training ${formatScore(version.training_metrics?.macro_f1)} / Evaluation ${formatScore(version.evaluation_metrics?.macro_f1)} / Mean ${formatMs(version.evaluation_metrics ? version.mean_latency_ms : null)}`
          : `F1 ${formatScore(version.validation_metrics?.macro_f1)} / Accuracy ${formatScore(version.validation_metrics?.accuracy)} / ${formatMs(version.validation_metrics?.median_ms)}`}</p>
        {version.improvements?.length ? <ActionBullets items={version.improvements} /> : null}
        <dl>
          <div><dt>Strength</dt><dd>{assessment.strength}</dd></div>
          <div><dt>Remaining gap</dt><dd>{assessment.weakness}</dd></div>
          <div><dt>Progress</dt><dd>{full && version.evaluation_metrics && parent?.evaluation_metrics
            ? `Evaluation F1 change from v${parent.version}: ${(version.evaluation_metrics.macro_f1 - parent.evaluation_metrics.macro_f1).toFixed(3)}`
            : assessment.comparison}</dd></div>
        </dl>
        {version.design_audit && <details>
          <summary>Generation {version.generation}: design rationale</summary>
          {!version.improvements?.length && <ActionBullets items={version.rationale} />}
          <dl><div><dt>Audited gap</dt><dd><ActionBullets items={version.design_audit.observed_gaps} /></dd></div>
            <div><dt>Design response</dt><dd><ActionBullets items={version.design_audit.changes} /></dd></div>
            <div><dt>Tradeoffs</dt><dd><ActionBullets items={version.design_audit.expected_tradeoffs} /></dd></div></dl>
        </details>}
        {interventions.length > 0 && <details className="opt-operator-audit">
          <summary>Operator audit after v{version.version} ({interventions.length})</summary>
          {interventions.map((record) => <div key={record.id}>
            <time dateTime={record.at}>{new Date(record.at).toLocaleString()}</time>
            <p>{record.guidance}</p>
          </div>)}
        </details>}
      </article>;
    })}
    {experiment.final_verification && <section aria-label="Reserved final validation">
      <h3 className="opt-section-title">Reserved final check: v{experiment.final_verification.agent_version}</h3>
      <p>{experiment.final_verification.status}</p>
      {experiment.final_verification.error && <p className="opt-error">{experiment.final_verification.error}</p>}
      <MetricsSummary metrics={experiment.final_verification.metrics ?? null} />
    </section>}
  </div>;
}