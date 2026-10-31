import type { CandidateVersion, Experiment, Metrics } from "./types";

/**
 * The measurement layer of the trajectory view, kept free of React so the unit
 * suite runs it directly.
 *
 * One rule governs everything here: a number exists only where the scorer
 * produced one. An unmeasured, pending, failed or cancelled candidate has no
 * point on the chart and no zero standing in for a score.
 */

export const MISSING = "\u2014";

export interface PlotPoint {
  version: number;
  label: string;
  value: number;
  origin: CandidateVersion["origin"];
  /** Position inside the plot box, in the SVG's own units. */
  x: number;
  y: number;
}

export interface Plot {
  points: PlotPoint[];
  /** Axis bounds actually used, after padding a degenerate range. */
  min: number;
  max: number;
  ticks: number[];
}

export type MetricPick = (metrics: Metrics) => number;

export const macroF1: MetricPick = (metrics) => metrics.macro_f1;
export const medianMs: MetricPick = (metrics) => metrics.median_ms;

export function resizePair(widths: number[], index: number, delta: number): number[] {
  const total = widths[index] + widths[index + 1];
  const left = Math.max(0, Math.min(total, widths[index] + delta));
  return widths.map((width, position) => position === index ? left : position === index + 1 ? total - left : width);
}

export function toggleColumn(widths: number[], index: number): number[] {
  const next = [...widths];
  if (next[index] > 0) {
    const recipient = next.findIndex((width, position) => position !== index && width > 0);
    if (recipient >= 0) next[recipient] += next[index];
    next[index] = 0;
  } else {
    const total = next.reduce((sum, width) => sum + width, 0);
    const restored = total ? 25 : 100;
    for (let position = 0; position < next.length; position++) next[position] *= total ? (100 - restored) / total : 0;
    next[index] = restored;
  }
  return next;
}

export function chronologicalTools<T extends { created_at: string; id: string }>(tools: T[]): T[] {
  return [...tools].sort((left, right) => left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id));
}

export function versionAssessment(version: CandidateVersion): { strength: string; weakness: string; comparison: string } {
  const metrics = version.validation_metrics;
  if (!metrics) return { strength: "No validation result recorded.", weakness: version.error || `Evaluation ${version.status}.`, comparison: "Unmeasured; no improvement claim." };
  const classes = Object.entries(metrics.per_class).filter(([, result]) => result.support > 0);
  const strongest = [...classes].sort((left, right) => right[1].f1 - left[1].f1)[0];
  const weakest = [...classes].sort((left, right) => left[1].recall - right[1].recall)[0];
  return {
    strength: strongest && strongest[1].f1 > 0
      ? `${strongest[0]} is strongest: F1 ${formatScore(strongest[1].f1)}, precision ${formatPercent(strongest[1].precision)}, recall ${formatPercent(strongest[1].recall)}.`
      : "No grade was predicted correctly in validation.",
    weakness: weakest ? `${weakest[0]} recall ${formatPercent(weakest[1].recall)} across ${weakest[1].support} cases${weakest[1].fn != null ? `; ${weakest[1].fn} missed` : ""}.` : "No class support recorded.",
    comparison: version.evaluations.at(-1)?.validation_comparison?.reason ?? version.evaluations.at(-1)?.comparison?.reason
      ?? (version.parent_version == null ? "Baseline measurement; no predecessor." : "No comparable parent run recorded."),
  };
}

/** Versions the scorer actually measured, in version order. */
export function measured(versions: CandidateVersion[]): CandidateVersion[] {
  return versions.filter((version) => version.metrics != null)
    .sort((left, right) => left.version - right.version);
}

export interface PlotBox { width: number; height: number; left: number; right: number; top: number; bottom: number }

export function buildPlot(versions: CandidateVersion[], pick: MetricPick, box: PlotBox): Plot {
  const rows = measured(versions);
  const values = rows.map((version) => pick(version.metrics as Metrics));
  const rawMin = values.length ? Math.min(...values) : 0;
  const rawMax = values.length ? Math.max(...values) : 1;
  // A single measured candidate, or a flat series, would otherwise divide by zero
  // and paint every point on the same pixel row.
  const span = rawMax - rawMin;
  const pad = span === 0 ? Math.max(Math.abs(rawMax) * 0.1, 0.05) : span * 0.12;
  const min = rawMin - pad;
  const max = rawMax + pad;
  const versionMin = rows.length ? rows[0].version : 0;
  const versionMax = rows.length ? rows[rows.length - 1].version : 1;
  const versionSpan = versionMax - versionMin || 1;
  const plotWidth = box.width - box.left - box.right;
  const plotHeight = box.height - box.top - box.bottom;
  const points = rows.map((version, index) => {
    const value = values[index];
    const ratio = rows.length === 1 ? 0.5 : (version.version - versionMin) / versionSpan;
    return {
      version: version.version,
      label: version.name,
      value,
      origin: version.origin,
      x: box.left + ratio * plotWidth,
      y: box.top + (1 - (value - min) / (max - min)) * plotHeight,
    };
  });
  const ticks = [min, min + (max - min) / 2, max];
  return { points, min, max, ticks };
}

/** Fixed-precision number, or an em dash where nothing was measured. */
export function formatScore(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : MISSING;
}

export function formatMs(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)} ms` : MISSING;
}

export function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : MISSING;
}

/** The experiment's baseline, which is the only candidate the host creates itself. */
export function baselineOf(experiment: Experiment | null): CandidateVersion | null {
  return experiment?.versions.find((version) => version.origin === "baseline") ?? null;
}

/**
 * Whether the CLI may be given the optimize action.
 *
 * The instruction the host prepares is grounded in baseline failures, so it does
 * not exist before the baseline has been measured. Offering the button earlier
 * would submit a task with nothing to improve on.
 */
export function baselineReady(experiment: Experiment | null): boolean {
  const baseline = baselineOf(experiment);
  return baseline?.status === "completed" && baseline.metrics != null;
}

export function isRunning(experiment: Experiment | null): boolean {
  return experiment?.status === "baseline_running" || experiment?.status === "running";
}

export interface FieldDiff { field: string; before: string; after: string; changed: boolean }

/** What this candidate changed relative to the version it was derived from. */
export function diffAgainstParent(version: CandidateVersion, versions: CandidateVersion[]): FieldDiff[] {
  const parent = version.parent_version == null ? null
    : versions.find((entry) => entry.version === version.parent_version) ?? null;
  const rows: FieldDiff[] = [
    { field: "Model", before: parent?.model ?? MISSING, after: version.model, changed: parent != null && parent.model !== version.model },
    {
      field: "Tool versions",
      before: parent ? parent.tool_ids.join(", ") || "none" : MISSING,
      after: version.tool_ids.join(", ") || "none",
      changed: parent != null && parent.tool_ids.join("\u0000") !== version.tool_ids.join("\u0000"),
    },
    {
      field: "System prompt",
      before: parent ? `${parent.system_prompt.length} characters` : MISSING,
      after: `${version.system_prompt.length} characters`,
      changed: parent != null && parent.system_prompt !== version.system_prompt,
    },
  ];
  return rows;
}

/** Cases the scorer marked wrong or errored, newest evaluation first. */
export function failingCases(version: CandidateVersion | null) {
  const evaluation = version?.evaluations.at(-1);
  return (evaluation?.cases ?? []).filter((item) => !item.correct || item.error);
}

/** Tool versions grouped by tool name, each group newest version first. */
export function groupTools<T extends { name: string; version: number }>(tools: T[]): { name: string; versions: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const tool of tools) groups.set(tool.name, [...(groups.get(tool.name) ?? []), tool]);
  return [...groups.entries()]
    .map(([name, versions]) => ({ name, versions: [...versions].sort((left, right) => right.version - left.version) }))
    .sort((left, right) => left.name.localeCompare(right.name));
}
