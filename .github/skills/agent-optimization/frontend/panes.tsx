import { useState } from "react";
import { ChartColumn, Database, Table2, Wrench } from "lucide-react";
import { SourceCodeViewer } from "@agentcraft/source-code";
import { useOptimizationApi } from "./api";
import { chronologicalTools } from "./trajectory";
import type { DatasetInfo, TablePreview, ToolVersion } from "./types";

function PreviewTable({ preview, caption }: { preview: TablePreview; caption: string }) {
  return <div className="opt-preview" role="region" aria-label={caption} tabIndex={0}>
    <table>
      <caption>{caption}: {preview.rows.length} rows</caption>
      <thead><tr>{preview.columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
      <tbody>
        {preview.rows.map((row, index) => <tr key={index}>
          {row.map((cell, cellIndex) => <td key={cellIndex}>{cell === null || cell === undefined ? "" : String(cell)}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}

/**
 * The dataset the experiment is frozen against.
 *
 * Counts, feature and label vocabulary and coverage bounds come from the host;
 * the previews are bounded reads of the same evidence the candidate may query.
 * Final-split labels are not among them.
 */
export function DataPane({ dataset, detail, full = false }: { dataset: DatasetInfo | null; detail: string; full?: boolean }) {
  const [preview, setPreview] = useState<{ caption: string; data: TablePreview } | null>(null);
  const optimizationApi = useOptimizationApi();
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  async function load(kind: "preview" | "profiles") {
    if (loading) return;
    setLoading(kind);
    setError("");
    try {
      const data = kind === "preview" ? await optimizationApi.preview() : await optimizationApi.profiles();
      setPreview({ caption: kind === "preview" ? "Evidence sample" : "Training-derived profiles", data });
    } catch (failure) {
      setPreview(null);
      setError((failure as Error).message);
    } finally {
      setLoading("");
    }
  }

  return <>
    <header className="rex-header">
      <span className="opt-source-label"><Database size={14} aria-hidden="true" />Dataset</span>
      <div className="rex-controls">
        <span>{dataset ? dataset.dataset_id : "No dataset"}</span>
        <button type="button" aria-label="Preview evidence" title="Preview evidence" aria-busy={loading === "preview"}
          disabled={!dataset || loading !== ""} onClick={() => void load("preview")}>
          <Table2 size={14} aria-hidden="true" />
        </button>
        <button type="button" aria-label="Training profiles" title="Training profiles" aria-busy={loading === "profiles"}
          disabled={!dataset || loading !== ""} onClick={() => void load("profiles")}>
          <ChartColumn size={14} aria-hidden="true" />
        </button>
      </div>
    </header>
    <div className="opt-pane-body">
      {!dataset && <p className="opt-empty" role="status">{detail || "The optimization dataset is not loaded."}</p>}
      {dataset && <>
        <section className="opt-block">
          <h3>Problem statement</h3>
          <p className="opt-empty">{dataset.problem_statement ?? `Compare predictions with the host's recorded labels: ${dataset.labels.join(", ")}.`}</p>
        </section>
        <section className="opt-block">
          <h3>Objective function</h3>
          <p className="opt-empty">{dataset.objective ?? (full ? "Compare development and evaluation macro-F1 across the same frozen cohorts." : `Compare mean F1 across ${dataset.labels.length} declared labels on the same cases, retaining latency and errors.`)}</p>
        </section>
        <section className="opt-block">
          <h3>Metrics</h3>
          <p className="opt-empty">{full ? "Training macro-F1, evaluation macro-F1, mean case latency, per-class precision/recall and execution errors." : "Precision measures how often a predicted grade is right; recall measures how often that grade is found. F1 balances both. Accuracy, confusion counts, median/p95 latency and error rate complete the validation profile."}</p>
        </section>
        <dl className="opt-facts">
          <div><dt>Evidence rows</dt><dd>{dataset.counts.evidence.toLocaleString()}</dd></div>
          <div><dt>Development cases</dt><dd>{dataset.counts.development.toLocaleString()}</dd></div>
          <div><dt>Validation cases</dt><dd>{dataset.counts.validation.toLocaleString()}</dd></div>
          <div><dt>Final cases</dt><dd>{dataset.counts.final.toLocaleString()}</dd></div>
          {full && <div><dt>Combined evaluation</dt><dd>{(dataset.counts.validation + dataset.counts.final).toLocaleString()}</dd></div>}
          <div><dt>Coverage</dt><dd>{dataset.time_start} to {dataset.time_end}</dd></div>
        </dl>
        <section className="opt-block">
          <h3><Table2 size={13} aria-hidden="true" />Labels</h3>
          <ul className="opt-chips">{dataset.labels.map((label) => <li key={label}>{label}</li>)}</ul>
        </section>
        <section className="opt-block">
          <h3>Visible features ({dataset.features.length})</h3>
          <ul className="opt-chips">{dataset.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
        </section>
        {dataset.limitations.length > 0 && <section className="opt-block">
          <h3>Limitations</h3>
          <ul className="opt-notes">{dataset.limitations.map((note) => <li key={note}>{note}</li>)}</ul>
          {full && <p className="opt-empty">Former final cases are included in every evaluation. No untouched test remains. Training scores are in-sample.</p>}
        </section>}
      </>}
      {error && <p className="opt-error" role="alert">{error}</p>}
      {preview && <PreviewTable preview={preview.data} caption={preview.caption} />}
    </div>
  </>;
}

/**
 * Basic and generated tooling, by tool name.
 *
 * A generated tool is a version of a tool, so the pinned identifier a candidate
 * references stays visible next to the query it actually runs.
 */
export function ToolsPane({ tools, inspected, onInspect }: {
  tools: ToolVersion[];
  inspected: string;
  onInspect: (id: string) => void;
}) {
  const ordered = chronologicalTools(tools);
  return <>
    <div className="opt-pane-body opt-tool-list">
      {!tools.length && <p className="opt-empty" role="status">No tool versions published yet.</p>}
      {ordered.map((tool, index) => <article key={`${tool.experiment_id}:${tool.id}`} className="opt-tool-card" data-tool-id={tool.id}>
        <button type="button" className="opt-tool-title" aria-pressed={inspected === tool.id} onClick={() => onInspect(tool.id)}>
          <Wrench size={14} aria-hidden="true" /><span>{index + 1}. {tool.name} <em>r{tool.revision ?? 1}</em></span>
        </button>
        <small>{tool.language === "python" ? "Python" : "Legacy SQL"} · {tool.status} · {new Date(tool.created_at).toLocaleTimeString()}</small>
        {tool.family && <small>{tool.family.replaceAll("-", " ")}</small>}
        <dl className="opt-tool-usage">
          <div><dt>First agent</dt><dd>{tool.first_agent_version == null ? "Unassigned" : `v${tool.first_agent_version}`}</dd></div>
          <div><dt>Last agent</dt><dd>{tool.last_agent_version == null ? "Unassigned" : `v${tool.last_agent_version}`}</dd></div>
        </dl>
        {!!tool.change_rationale?.length && <ul className="opt-action-list" aria-label={`Tool r${tool.revision ?? 1} change rationale`}>
          {tool.change_rationale.map((reason, position) => <li key={position}>{reason}</li>)}
        </ul>}
        {tool.supersedes && <button className="opt-lineage-link" type="button" onClick={() => onInspect(tool.supersedes!)}
          title="Inspect the preceding immutable tool revision">Previous revision: r{(tool.revision ?? 2) - 1}</button>}
        <dl className="opt-tool-descriptors">
          <div><dt>Queries</dt><dd>{tool.queries || "Incident evidence and development profiles; original SQL retained below."}</dd></div>
          <div><dt>Returns</dt><dd>{tool.returns || tool.description}</dd></div>
          <div><dt>Logic</dt><dd>{tool.logic || "SQL-only historical tool. No Python logic was executed in this version."}</dd></div>
        </dl>
        <small>Agents {tool.agent_versions.map((version) => `v${version}`).join(", ") || "none"}</small>
        <details open={inspected === tool.id}>
          <summary>{tool.language === "python" ? "Python script" : "Original SQL"}</summary>
          <SourceCodeViewer code={tool.code ?? tool.sql ?? ""} filename={`${tool.name}.${tool.language === "python" ? "py" : "sql"}`} maxHeight={420} defaultWrap />
          <p className="opt-tool-digest">{tool.digest}</p>
        </details>
      </article>)}
    </div>
  </>;
}
