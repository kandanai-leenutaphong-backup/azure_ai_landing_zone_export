import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, ChartNoAxesCombined, CircleStop, Database, Expand, PanelLeftClose, Plus, Radar, RotateCcw, ScrollText, TerminalSquare, Wrench, X } from "lucide-react";
import { CopilotTerminal, type TerminalAction } from "copilot-terminal";
import { useOptimizationApi } from "./api";
import { DataPane, ToolsPane } from "./panes";
import { VersionList, VersionsView } from "./views";
import { baselineReady, measured } from "./trajectory";
import { PerformanceView } from "./PerformanceView";
import { RunReplay } from "./RunReplay";
import { DetectorView } from "./DetectorView";
import { useOptimizationColumns } from "./columns";
import type { Experiment, OptimizationProtocol, RunStage, Snapshot } from "./types";
import "./optimization.css";

const COLUMNS = [
  { id: "dataset", label: "Dataset", icon: Database },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "agents", label: "Agents", icon: Bot },
  { id: "performance", label: "Agent Optimization", icon: ChartNoAxesCombined },
] as const;

export interface OptimizationWorkspaceProps {
  active: boolean;
  /** A request from elsewhere in the application to show one experiment. */
  openRequest?: { experimentId: string; at: number } | null;
}

export function OptimizationWorkspace({ active, openRequest }: OptimizationWorkspaceProps) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [experimentId, setExperimentId] = useState("");
  const [name, setName] = useState("");
  const [protocol, setProtocol] = useState<OptimizationProtocol>("joint-10");
  const [workflow, setWorkflow] = useState(true);
  const [creative, setCreative] = useState(true);
  const [profileTab, setProfileTab] = useState<"agent" | "detector">("agent");
  const [selectedDetector, setSelectedDetector] = useState<number | null>(null);
  const [replayStage, setReplayStage] = useState<RunStage | null>(null);
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState("");
  const optimizationApi = useOptimizationApi();
  const [showProcess, setShowProcess] = useState(false);
  const processDialog = useRef<HTMLDialogElement>(null);
  const layout = useOptimizationColumns();
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [inspectedTool, setInspectedTool] = useState("");
  const [trace, setTrace] = useState("");
  const [traceError, setTraceError] = useState("");
  const versionTouched = useRef("");

  /**
   * One poll in flight at a time.
   *
   * The next request is scheduled after the previous one settles rather than on
   * an interval, so a slow host cannot accumulate overlapping snapshots, and the
   * loop stops entirely when the tab is not the visible one.
   */
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    async function tick() {
      try {
        const value = await optimizationApi.snapshot(controller.signal);
        if (stopped) return;
        setSnapshot(value);
        setLoadError("");
      } catch (failure) {
        if (!stopped && !controller.signal.aborted) {
          setLoadError((failure as Error).message);
        }
      } finally {
        if (!stopped) {
          setLoaded(true);
          timer = setTimeout(() => void tick(), 2000);
        }
      }
    }
    void tick();
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [active]);

  const experiments = snapshot?.experiments ?? [];
  const selected = experiments.find((entry) => entry.id === experimentId) ?? null;

  useEffect(() => {
    if (!experimentId && experiments.length) setExperimentId(experiments[experiments.length - 1].id);
  }, [experimentId, experiments]);

  useEffect(() => {
    if (!openRequest) return;
    setExperimentId(openRequest.experimentId);
    if (layout.widths[2] === 0) layout.toggle(2);
  }, [openRequest]);

  useEffect(() => {
    if (showProcess && !processDialog.current?.open) processDialog.current?.showModal();
    if (!showProcess && processDialog.current?.open) processDialog.current?.close();
  }, [showProcess]);

  // Follow the newest measured candidate until the analyst picks one themselves.
  useEffect(() => {
    if (!selected) return;
    if (versionTouched.current === selected.id) return;
    const latest = measured(selected.versions).at(-1) ?? selected.versions.at(-1);
    setSelectedVersion(latest?.version ?? null);
  }, [selected]);

  function chooseVersion(version: number) {
    if (selected) versionTouched.current = selected.id;
    setSelectedVersion(version);
    setProfileTab("agent");
    setInspectedTool("");
    if (layout.widths[2] === 0) layout.toggle(2);
  }

  const version = selected?.versions.find((entry) => entry.version === selectedVersion) ?? null;
  const experimentTools = (snapshot?.tools ?? []).filter((entry) => entry.experiment_id === selected?.id);
  const experimentDetectors = (snapshot?.detectors ?? []).filter((entry) => entry.experiment_id === selected?.id);

  const patch = useCallback((experiment: Experiment) => {
    setSnapshot((current) => current && {
      ...current,
      experiments: current.experiments.some((entry) => entry.id === experiment.id)
        ? current.experiments.map((entry) => entry.id === experiment.id ? experiment : entry)
        : [...current.experiments, experiment],
    });
  }, []);

  async function createExperiment() {
    if (busy || !name.trim()) return;
    setBusy("create");
    setActionError("");
    try {
      const experiment = await optimizationApi.createExperiment(name.trim(), protocol, workflow,
        creative && ["joint-10", "joint-12"].includes(protocol) && snapshot?.creative_supported === true);
      patch(experiment);
      versionTouched.current = "";
      setExperimentId(experiment.id);
      setName("");
    } catch (failure) {
      setActionError((failure as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function stopExperiment() {
    if (busy || !selected) return;
    setBusy("cancel");
    setActionError("");
    try {
      patch(await optimizationApi.cancel(selected.id));
    } catch (failure) {
      setActionError((failure as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function loadTrace() {
    if (busy || !selected) return;
    setBusy("trace");
    setTraceError("");
    try {
      setTrace((await optimizationApi.trace(selected.id)).text);
    } catch (failure) {
      setTrace("");
      setTraceError((failure as Error).message);
    } finally {
      setBusy("");
    }
  }

  /**
   * The optimize action exists only once the baseline has a measurement.
   *
   * The host grounds the prepared instruction in baseline failures, so offering
   * it earlier would submit a task with nothing measured to improve on.
   */
  const actions = useMemo<TerminalAction[]>(() => {
    if (!selected || !baselineReady(selected) || !["ready", "failed"].includes(selected.status)) return [];
    return [{
      id: "optimize",
      label: "Optimize agent",
      title: `Ask the CLI to improve ${selected.name}`,
      autopilot: true,
      prepare: { operation: "prepare", payload: { experiment_id: selected.id } },
    }];
  }, [selected]);

  const available = snapshot?.available ?? false;

  function inspect(id: string) {
    setInspectedTool(id);
    if (layout.widths[1] === 0) layout.toggle(1);
  }

  function inspectDetector(detector: number) {
    setSelectedDetector(detector);
    setProfileTab("detector");
  }

  const content = [
    <DataPane dataset={snapshot?.dataset ?? null} detail={snapshot?.detail ?? (loaded ? loadError : "Loading dataset...")} full={["full-10", "joint-10", "joint-12"].includes(selected?.protocol ?? "")} />,
    <ToolsPane tools={experimentTools} inspected={inspectedTool} onInspect={inspect} />,
    selected ? <div className="opt-agent-content">
      <div className="opt-profile-tabs" role="tablist" aria-label="Versioned components" onKeyDown={(event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? "agent" : event.key === "End" ? "detector" : profileTab === "agent" ? "detector" : "agent";
        setProfileTab(next);
        event.currentTarget.querySelector<HTMLButtonElement>(`[data-profile-tab="${next}"]`)?.focus();
      }}>
        <button type="button" role="tab" id="opt-agent-tab" aria-selected={profileTab === "agent"} aria-controls="opt-component-profile"
          data-profile-tab="agent" tabIndex={profileTab === "agent" ? 0 : -1} onClick={() => setProfileTab("agent")}><Bot size={15} />Agent</button>
        <button type="button" role="tab" id="opt-detector-tab" aria-selected={profileTab === "detector"} aria-controls="opt-component-profile"
          data-profile-tab="detector" tabIndex={profileTab === "detector" ? 0 : -1} onClick={() => setProfileTab("detector")}><Radar size={15} />Situation Detector</button>
      </div>
      <div id="opt-component-profile" role="tabpanel" aria-labelledby={profileTab === "agent" ? "opt-agent-tab" : "opt-detector-tab"}>
      {profileTab === "agent" ? <>
      <VersionList versions={selected.versions} selected={selectedVersion} onSelect={chooseVersion} />
      <VersionsView experiment={selected} version={version} tools={experimentTools} onInspect={inspect} onReplay={setReplayStage} onDetector={inspectDetector} />
      </> : <DetectorView versions={experimentDetectors} selected={selectedDetector ?? version?.situation_detector_version ?? null}
        onSelect={setSelectedDetector} reference={snapshot?.detector_reference} />}
      </div>
    </div> : <p className="opt-empty">No agent versions recorded.</p>,
    selected ? <PerformanceView experiment={selected} selected={selectedVersion} onSelect={chooseVersion} />
      : <p className="opt-empty">No performance measurements recorded.</p>,
  ];

  return <div className="optimization-shell opt-four-workspace" data-testid="optimization">
    <form className="opt-controls" onSubmit={(event) => { event.preventDefault(); void createExperiment(); }}>
      <label htmlFor="opt-experiment"><span id="opt-experiment-label">Experiment</span>
        <select id="opt-experiment" aria-labelledby="opt-experiment-label" value={experimentId} disabled={!experiments.length}
          onChange={(event) => { versionTouched.current = ""; setExperimentId(event.target.value); setInspectedTool(""); setSelectedDetector(null); setProfileTab("agent"); setTrace(""); }}>
          {!experiments.length && <option value="">No experiment</option>}
          {experiments.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
        </select>
      </label>
      <label htmlFor="opt-name">Experiment name
        <input id="opt-name" value={name} disabled={!available || busy !== ""} onChange={(event) => setName(event.target.value)} placeholder="New experiment" />
      </label>
      <label htmlFor="opt-protocol">Test protocol
        <select id="opt-protocol" aria-label="Test protocol" value={protocol} disabled={busy !== ""}
          onChange={(event) => { setProtocol(event.target.value as OptimizationProtocol); if (event.target.value === "stress-10") setWorkflow(false); if (event.target.value.startsWith("joint-")) setWorkflow(true); }}>
          <option value="joint-10">Joint system / 10 generations / full cohorts</option>
          <option value="joint-12">Joint system / 12 generations / full cohorts</option>
          <option value="joint-smoke">Joint system / smoke / host cohort</option>
          <option value="full-10">10 generations / full training + evaluation</option>
          <option value="stress-10">10 generations / stress cohort</option>
          <option value="smoke">Smoke / host cohort</option>
        </select>
      </label>
      <label className="opt-workflow-choice"><input type="checkbox" checked={workflow} disabled={busy !== "" || protocol === "stress-10" || protocol.startsWith("joint-")}
        onChange={(event) => setWorkflow(event.target.checked)} />Detector + agent workflow</label>
      {snapshot?.creative_supported && <label className="opt-workflow-choice"><input type="checkbox"
        checked={creative && ["joint-10", "joint-12"].includes(protocol)} disabled={busy !== "" || !["joint-10", "joint-12"].includes(protocol)}
        onChange={(event) => setCreative(event.target.checked)} />Creative exploration</label>}
      <button type="submit" disabled={!available || busy !== "" || !name.trim() || (workflow && !snapshot?.knowledge_configured)}><Plus size={14} aria-hidden="true" />{busy === "create" ? "Creating..." : "Create experiment"}</button>
      <button type="button" onClick={() => setShowProcess(true)}><TerminalSquare size={15} aria-hidden="true" />Coding agent</button>
      <button type="button" className="opt-stop" disabled={busy !== "" || !selected || ["completed", "cancelled"].includes(selected.status)} onClick={() => void stopExperiment()}>
        <CircleStop size={14} aria-hidden="true" />{busy === "cancel" ? "Stopping..." : "Stop experiment"}
      </button>
      <p className="opt-status" role="status">{selected ? `${selected.name}: ${selected.status.replace("_", " ")}` : "No experiment selected"}</p>
    </form>
    {!available && loaded && <p className="opt-error" role="alert">{snapshot?.detail || loadError || "Optimization service unavailable."}</p>}
    {actionError && <p className="opt-error" role="alert">{actionError}</p>}
    {selected?.error && <p className="opt-error" role="alert">{selected.error}</p>}
    <div className="opt-column-controls" aria-label="Column visibility">
      {COLUMNS.map((column, index) => <button key={column.id} type="button" aria-label={`${layout.widths[index] ? "Collapse" : "Restore"} ${column.label} column`}
        aria-pressed={layout.widths[index] > 0} title={`${column.label} column`} onClick={() => layout.toggle(index)}><column.icon size={16} /></button>)}
      <button type="button" aria-label="Reset column widths" title="Reset column widths" onClick={layout.reset}><RotateCcw size={15} /></button>
      <span>{selected?.stage_counts ? `${selected.versions.length} agent versions / Training ${selected.stage_counts.training.toLocaleString()} / Evaluation ${selected.stage_counts.evaluation.toLocaleString()}`
        : selected ? `${selected.versions.length} agent versions / ${selected.case_count} fixed cases${selected.protocol === "stress-10" ? " / baseline + 10 generations" : ""}` : "No experiment selected"}</span>
    </div>
    <div className="opt-columns" ref={layout.shell} style={{ gridTemplateColumns: layout.widths.map((width) => `minmax(0, ${width}fr)`).join(" 8px ") }}>
      {COLUMNS.map((column, index) => <Fragment key={column.id}>
        <section className="opt-column" data-column={column.id} aria-label={`${column.label} column`} hidden={layout.widths[index] === 0}>
          <header className="opt-column-header">
            <column.icon size={15} aria-hidden="true" /><h2>{column.label}</h2>
            <button type="button" aria-label={`Focus ${column.label} column`} title={`Focus ${column.label}`} onClick={() => layout.focus(index)}><Expand size={13} /></button>
            <button type="button" aria-label={`Hide ${column.label} column`} title={`Collapse ${column.label}`} onClick={() => layout.toggle(index)}><PanelLeftClose size={14} /></button>
          </header>
          <div className="opt-column-body">{content[index]}</div>
        </section>
        {index < 3 && <div {...layout.separator(index, `Resize ${column.label} and ${COLUMNS[index + 1].label}`)} />}
      </Fragment>)}
    </div>
    <dialog ref={processDialog} className="opt-process-dialog" aria-label="Coding agent process" onClose={() => setShowProcess(false)}>
      <header><h2>GitHub Copilot CLI</h2><button type="button" aria-label="Close coding agent" title="Close coding agent" onClick={() => setShowProcess(false)}><X size={18} /></button></header>
      <div className="opt-cli-layout">
        <CopilotTerminal apiBase={optimizationApi.terminalBase} active={active && showProcess} actions={actions} />
        <div className="opt-process-side">
          <div className="opt-trace-head"><h3>Process history</h3><button type="button" disabled={!selected || busy !== ""} onClick={() => void loadTrace()}><ScrollText size={14} />{busy === "trace" ? "Loading..." : "Trace"}</button></div>
          {traceError && <p className="opt-error" role="alert">{traceError}</p>}
          {trace && <pre className="opt-trace" tabIndex={0}>{trace}</pre>}
          <ol className="opt-events">{(selected?.events ?? []).map((entry, index) => <li key={`${entry.at}-${index}`}><time>{entry.at}</time><b>{entry.event}</b><span>{entry.detail}</span></li>)}</ol>
          {(selected?.rejections ?? []).map((rejection) => <details key={rejection.id}><summary>Rejected proposal: {rejection.at}</summary><p className="opt-error">{rejection.error}</p><pre className="opt-trace">{JSON.stringify(rejection.proposal, null, 2)}</pre></details>)}
        </div>
      </div>
    </dialog>
    {selected && version && replayStage && <RunReplay experimentId={selected.id} version={version} initialStage={replayStage} onClose={() => setReplayStage(null)} />}
  </div>;
}
