import { useState } from "react";
import { createRoot } from "react-dom/client";
import { OptimizationApiProvider, RunReplay, createOptimizationApi, type CandidateVersion, type RequestJson } from "@agentcraft/agent-optimization";
import type { RunExample, RunStage } from "@agentcraft/agent-optimization/types";
import "@agentcraft/agent-optimization/styles";

const retained = { case_id: "synthetic-case", expected: "accept", predicted: "accept", correct: true, elapsed_ms: 10, error: "" };
const run = (stage: RunStage) => ({ id: stage, stage, status: "completed" as const, started_at: "2024-01-01T00:00:00Z",
  case_count: 1, cases: [], metrics: null, exemplars: { best: retained, worst: retained } });
const version: CandidateVersion = {
  version: 1, name: "Synthetic fixture", parent_version: null, system_prompt: "Synthetic classification instructions",
  model: "synthetic-model", tool_ids: ["synthetic-tool"], created_at: "2024-01-01T00:00:00Z",
  status: "completed", rationale: "Hand-authored fixture, not a measured campaign", origin: "baseline",
  metrics: null, training_runs: [run("training")], evaluations: [run("evaluation")],
};

declare global {
  interface Window { replayReads: string[]; }
}
window.replayReads = [];
const request: RequestJson = async <Result,>(path: string, options?: RequestInit): Promise<Result> => {
  if (options?.method && options.method !== "GET") throw new Error("Synthetic replay is read-only");
  const match = path.match(/\/runs\/(training|evaluation)\/examples\/(best|worst)$/);
  if (!match) throw new Error("Unknown synthetic replay read");
  window.replayReads.push(path);
  const stage = match[1] as RunStage;
  const selection = match[2] as "best" | "worst";
  const example: RunExample = {
    run_id: stage, agent_version: 1, stage, selection,
    case: { ...retained, split: stage === "training" ? "development" : "validation", rationale: "Synthetic fixture",
      transcript: {
        request: { model: "synthetic-model", instructions: version.system_prompt, input: "Synthetic observation", max_output_tokens: 128 },
        evidence: { time_window: { start: "2024-01-01T00:00:00Z", end: "2024-01-01T01:00:00Z" },
          tools: [{ name: "synthetic_evidence", result: { rows: [["synthetic observation"]] } }] },
        response: { grade: "accept", rationale: "Hand-authored fixture, no model inference" },
        error: "", model_call_attempted: false, tool_ids: ["synthetic-tool"],
      },
    },
  };
  return structuredClone(example) as Result;
};
const client = createOptimizationApi(request, "/synthetic");

function Fixture() {
  const [open, setOpen] = useState(false);
  return <main className="optimization-shell fixture">
    <h1>Synthetic Optimization Replay</h1>
    <button type="button" onClick={() => setOpen(true)}>Open recorded runs</button>
    <OptimizationApiProvider client={client}>
      {open && <RunReplay experimentId="synthetic" version={version} initialStage="training" onClose={() => setOpen(false)} />}
    </OptimizationApiProvider>
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);