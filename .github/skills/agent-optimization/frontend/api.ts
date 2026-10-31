import { createContext, createElement, useContext, type ReactNode } from "react";
import type { Experiment, OptimizationProtocol, RunExample, Snapshot, TablePreview } from "./types";

/** The host owns transport: it decides credentials, error shape and session handling. */
export type RequestJson = <T>(path: string, options?: RequestInit) => Promise<T>;

export interface OptimizationApi {
  base: string;
  terminalBase: string;
  snapshot: (signal?: AbortSignal) => Promise<Snapshot>;
  createExperiment: (name: string, protocol?: OptimizationProtocol, workflow?: boolean, creative?: boolean) => Promise<Experiment>;
  experiment: (id: string, signal?: AbortSignal) => Promise<Experiment>;
  cancel: (id: string) => Promise<Experiment>;
  trace: (id: string, signal?: AbortSignal) => Promise<{ text: string }>;
  preview: (signal?: AbortSignal) => Promise<TablePreview>;
  profiles: (signal?: AbortSignal) => Promise<TablePreview>;
  exemplar: (id: string, version: number, run: string, kind: "best" | "worst", signal?: AbortSignal) => Promise<RunExample>;
}

/**
 * Local-only routes in the composition that mounts them. A cloud composition that does not
 * answers 404 here; the workspace renders that refusal as the truth it is rather than as a
 * transient failure.
 */
export function createOptimizationApi(requestJson: RequestJson, base = "/api/cyber/optimization"): OptimizationApi {
  const post = (path: string) => requestJson<Experiment>(`${base}${path}`, { method: "POST", body: "{}" });
  return {
    base,
    terminalBase: `${base}/terminal`,
    snapshot: (signal?: AbortSignal) => requestJson<Snapshot>(base, { signal }),
    createExperiment: (name: string, protocol: OptimizationProtocol = "joint-10", workflow = false, creative = false) => requestJson<Experiment>(`${base}/experiments`, {
      method: "POST", body: JSON.stringify({ name, protocol, workflow, creative }),
    }),
    experiment: (id: string, signal?: AbortSignal) => requestJson<Experiment>(
      `${base}/experiments/${encodeURIComponent(id)}`, { signal }),
    cancel: (id: string) => post(`/experiments/${encodeURIComponent(id)}/cancel`),
    trace: (id: string, signal?: AbortSignal) => requestJson<{ text: string }>(
      `${base}/experiments/${encodeURIComponent(id)}/trace`, { signal }),
    preview: (signal?: AbortSignal) => requestJson<TablePreview>(`${base}/sources/preview`, { signal }),
    profiles: (signal?: AbortSignal) => requestJson<TablePreview>(`${base}/profiles`, { signal }),
    exemplar: (id: string, version: number, run: string, kind: "best" | "worst", signal?: AbortSignal) => requestJson<RunExample>(
      `${base}/experiments/${encodeURIComponent(id)}/versions/${version}/runs/${encodeURIComponent(run)}/examples/${kind}`, { signal }),
  };
}

const OptimizationApiContext = createContext<OptimizationApi | null>(null);

export function OptimizationApiProvider({ client, children }: { client: OptimizationApi; children: ReactNode }) {
  return createElement(OptimizationApiContext.Provider, { value: client }, children);
}

export function useOptimizationApi(): OptimizationApi {
  const client = useContext(OptimizationApiContext);
  if (!client) {
    throw new Error("Wrap the optimization workspace in OptimizationApiProvider with a host client");
  }
  return client;
}
