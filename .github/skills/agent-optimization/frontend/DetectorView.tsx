import { SourceCodeViewer } from "@agentcraft/source-code";
import { ActionBullets } from "./views";
import type { ApplicationDetector, DetectorVersion } from "./types";

export function DetectorView({ versions, selected, onSelect, reference }: {
  versions: DetectorVersion[]; selected: number | null; onSelect: (version: number) => void; reference?: ApplicationDetector | null;
}) {
  const current = versions.find(version => version.version === selected) ?? versions.at(-1);
  return <div className="opt-detector-content">
    {current ? <>
      <div className="opt-detector-list" aria-label="Situation detector versions">
        {versions.map(version => <button type="button" key={version.version} data-detector-version={version.version}
          aria-pressed={current.version === version.version} onClick={() => onSelect(version.version)}>
          <strong>v{version.version} {version.name}</strong>
          <small>{version.rules.length} rules / {version.parent_version ? `from detector v${version.parent_version}` : "baseline"}</small>
        </button>)}
      </div>
      <section className="opt-detail" aria-label={`Situation detector v${current.version} profile`}>
        <h3>Detector v{current.version}: {current.name}</h3>
        <p className="opt-empty">{current.scope}</p>
        <dl className="opt-facts">
          <div><dt>First agent use</dt><dd>{current.first_agent_version == null ? "Not assigned" : `v${current.first_agent_version}`}</dd></div>
          <div><dt>Last agent use</dt><dd>{current.last_agent_version == null ? "Not assigned" : `v${current.last_agent_version}`}</dd></div>
          <div><dt>Created</dt><dd>{current.created_at}</dd></div>
          <div><dt>Digest</dt><dd><code>{current.digest}</code></dd></div>
        </dl>
        <h4>Changes</h4><ActionBullets items={current.change_rationale} />
        {current.configuration && <section aria-label="Ruleset composition">
          <h4>Ruleset composition</h4>
          <ul className="opt-ruleset-composition">{current.configuration.rule_sets.map(ruleSet => <li key={ruleSet.id}>
            <label><input type="checkbox" checked={ruleSet.enabled} disabled />{ruleSet.name}</label>
            <small>{ruleSet.id} / {ruleSet.rules.filter(rule => rule.enabled).length} enabled rules</small>
          </li>)}</ul>
          <dl className="opt-facts"><div><dt>Window cap</dt><dd>{current.configuration.max_window_seconds} seconds</dd></div>
            <div><dt>Configuration digest</dt><dd><code>{current.configuration_digest}</code></dd></div></dl>
        </section>}
        <h4>Detection rules</h4>
        {current.rules.map(rule => <details className="opt-detector-rule" key={rule.id} data-rule-id={rule.id}>
          <summary>{rule.name} / r{rule.revision}{rule.enabled === false ? " / disabled" : ""}</summary>
          <p>{rule.description}</p><code>{rule.id}</code>
          {rule.query && <><h4>Standardized query</h4>
            <SourceCodeViewer code={rule.query} filename={`${rule.id}.sql`} language="sql" maxHeight={240} defaultWrap />
            <h4>Parameters</h4><SourceCodeViewer code={JSON.stringify(rule.parameters, null, 2)} filename={`${rule.id}-parameters.json`} language="json" maxHeight={180} defaultWrap />
            <h4>Processing</h4></>}
          <SourceCodeViewer code={rule.code} filename={`${rule.id}.py`} language="python" maxHeight={340} defaultWrap />
        </details>)}
      </section>
    </> : <section className="opt-detail">
      <h3>No detector versions recorded</h3>
      <p className="opt-empty">This experiment measured agent triage only. Its cases were already grouped into incidents.</p>
    </section>}
    {reference && <details className="opt-detector-reference" open={!current}>
      <summary>Application reference: {reference.name}</summary>
      <p className="opt-empty">{reference.scope}</p>
      <dl className="opt-facts"><div><dt>Registry version</dt><dd><code>{reference.version}</code></dd></div></dl>
      {reference.rules.map(rule => <details className="opt-detector-rule" key={rule.rule_id}>
        <summary>{rule.name} / {rule.version}</summary>
        <p>{rule.description}</p>
        <dl className="opt-facts"><div><dt>Role</dt><dd>{rule.role}</dd></div>
          <div><dt>Threshold</dt><dd>{rule.threshold}</dd></div><div><dt>Score</dt><dd>{rule.score}</dd></div></dl>
        <p>{rule.evidence_semantics}</p>
        <SourceCodeViewer code={rule.query} filename={`${rule.rule_id}.kql`} language="kusto" maxHeight={320} defaultWrap />
      </details>)}
    </details>}
  </div>;
}