import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, ClipboardCheck, Database, Wrench, X } from "lucide-react";
import { SourceCodeViewer } from "@agentcraft/source-code";
import { useOptimizationApi } from "./api";
import { formatMs } from "./trajectory";
import type { CandidateVersion, RunExample, RunStage } from "./types";

export function RunReplay({ experimentId, version, initialStage, onClose }: {
  experimentId: string; version: CandidateVersion; initialStage: RunStage; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const optimizationApi = useOptimizationApi();
  const [stage, setStage] = useState(initialStage);
  const [examples, setExamples] = useState<RunExample[] | null>(null);
  const [error, setError] = useState("");
  const run = (stage === "training" ? version.training_runs : version.evaluations)?.at(-1);
  const runId = run?.exemplars?.best && run.exemplars.worst ? run.id : null;

  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setExamples(null);
    setError("");
    if (runId) {
      Promise.all((["best", "worst"] as const).map((kind) => optimizationApi.exemplar(experimentId, version.version, runId, kind, controller.signal)))
        .then((records) => { if (!controller.signal.aborted) setExamples(records); })
        .catch((failure: Error) => { if (!controller.signal.aborted) setError(failure.message); });
    }
    return () => controller.abort();
  }, [experimentId, version.version, runId]);

  return <dialog ref={dialog} className="opt-replay-dialog" aria-labelledby="opt-replay-title" onClose={onClose}>
    <header className="opt-replay-header">
      <div><h2 id="opt-replay-title">v{version.version} {version.name}</h2><p>Recorded agent runs</p></div>
      <button type="button" aria-label="Close run replay" title="Close run replay" onClick={onClose}><X size={20} /></button>
    </header>
    <div className="opt-replay-tabs" role="tablist" aria-label="Replay stage">
      {(["training", "evaluation"] as const).map((value) => <button key={value} type="button" role="tab"
        aria-selected={stage === value} aria-controls="opt-replay-content" onClick={() => setStage(value)}>
        {value === "training" ? "Training" : "Evaluation"}
      </button>)}
      <span>{run?.case_count?.toLocaleString() ?? 0} cases / {run?.status ?? "not started"}</span>
    </div>
    <div id="opt-replay-content" role="tabpanel" aria-label={`${stage} run comparison`} className="opt-replay-content">
      {error && <p className="opt-error" role="alert">{error}</p>}
      {!error && !examples && <p className="opt-empty" role="status">{runId ? "Loading recorded runs..." : "No completed replay for this stage yet."}</p>}
      {examples?.map((example) => <ReplayConversation key={example.selection} example={example} />)}
    </div>
  </dialog>;
}

function ReplayConversation({ example }: { example: RunExample }) {
  const result = example.case;
  const trace = result.transcript;
  const best = example.selection === "best";
  return <section className="opt-replay-conversation" aria-label={`${example.selection} ${example.stage} run`}>
    <header className="opt-replay-case" data-outcome={result.correct ? "correct" : "incorrect"}>
      {best ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
      <h3>{best ? "Best retained run" : "Worst retained run"}</h3>
      <strong>{formatMs(result.elapsed_ms)}</strong>
      <code>{result.case_id}</code>
      <span>{result.error ? "Execution error" : result.correct ? "Correct" : "Incorrect"} / {result.split}</span>
    </header>
    <div className="opt-replay-messages">
      <details className="opt-replay-system"><summary>System instructions</summary>
        <SourceCodeViewer code={trace.request.instructions} filename="system-prompt.md" language="markdown" maxHeight={280} defaultWrap />
      </details>
      <article className="opt-replay-message opt-replay-user" data-message-role="user">
        <h4><Database size={15} />Incident</h4>
        <p>Classify this incident and return JSON.</p>
        <dl><div><dt>Start</dt><dd>{trace.evidence.time_window.start}</dd></div>
          <div><dt>End</dt><dd>{trace.evidence.time_window.end}</dd></div></dl>
      </article>
      {trace.evidence.situation_detector && <details className="opt-replay-system" data-message-role="detector">
        <summary>Situation detector v{trace.evidence.situation_detector.version}: {trace.evidence.situation_detector.situations.length} proposed situations</summary>
        <SourceCodeViewer code={JSON.stringify(trace.evidence.situation_detector, null, 2)} filename="detector-result.json" language="json" maxHeight={300} defaultWrap />
      </details>}
      {trace.evidence.tools.map((tool, index) => <details key={index} className="opt-replay-tool" data-message-role="tool">
        <summary><Wrench size={15} />{tool.name}</summary>
        <code>{trace.tool_ids[index]}</code>
        <SourceCodeViewer code={JSON.stringify(tool.result, null, 2)} filename={`${tool.name}-result.json`} language="json" maxHeight={260} defaultWrap />
      </details>)}
      {trace.evidence.knowledge && <details className="opt-replay-system" data-message-role="knowledge">
        <summary>Advisory knowledge: {trace.evidence.knowledge.tool}</summary>
        <SourceCodeViewer code={JSON.stringify(trace.evidence.knowledge, null, 2)} filename="knowledge-result.json" language="json" maxHeight={320} defaultWrap />
      </details>}
      <article className="opt-replay-message opt-replay-assistant" data-message-role="assistant">
        <h4><Bot size={16} />Agent response</h4>
        {trace.response ? <><strong>{trace.response.grade}</strong><p>{trace.response.rationale}</p></> : <p>No successful model response recorded.</p>}
        {trace.response?.diagnosis && <><h4>Diagnosis hypothesis</h4><p>{trace.response.diagnosis}</p></>}
        {trace.response?.proposed_actions && <><h4>Proposed actions / not executed</h4>
          {trace.response.proposed_actions.length ? <ul>{trace.response.proposed_actions.map((action, index) => <li key={index}>{action}</li>)}</ul> : <p>No action proposed.</p>}</>}
        {trace.response?.citations?.length ? <><h4>Knowledge citations</h4><ul>{trace.response.citations.map((citation, index) => <li key={index}><code>{citation}</code></li>)}</ul></> : null}
        {trace.error && <p className="opt-error">{trace.error}</p>}
      </article>
      <aside className="opt-replay-grader" data-outcome={result.correct ? "correct" : "incorrect"}>
        <h4><ClipboardCheck size={16} />Grader</h4>
        <dl><div><dt>Expected</dt><dd>{result.expected}</dd></div><div><dt>Predicted</dt><dd>{result.predicted ?? "No prediction"}</dd></div></dl>
      </aside>
      <details className="opt-replay-system"><summary>{trace.model_call_attempted === false ? "Prepared model request / not sent" : "Recorded model request"}</summary>
        <SourceCodeViewer code={JSON.stringify(trace.request, null, 2)} filename="model-request.json" language="json" maxHeight={280} defaultWrap />
      </details>
    </div>
  </section>;
}