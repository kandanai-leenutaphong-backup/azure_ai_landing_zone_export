import { buildPlot, type MetricPick, type PlotBox } from "./trajectory";
import type { CandidateVersion } from "./types";

const BOX: PlotBox = { width: 640, height: 240, left: 56, right: 16, top: 16, bottom: 34 };

interface Props {
  title: string;
  versions: CandidateVersion[];
  pick: MetricPick;
  format: (value: number) => string;
  selected: number | null;
  onSelect: (version: number) => void;
}

/**
 * One measured series against version number.
 *
 * Every mark is a point the scorer produced. Candidates that are pending,
 * running, failed or cancelled are absent rather than drawn at zero, so the
 * line never implies progress that was not measured.
 */
export function TrajectoryChart({ title, versions, pick, format, selected, onSelect }: Props) {
  const plot = buildPlot(versions, pick, BOX);
  const unmeasured = versions.length - plot.points.length;
  const path = plot.points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");

  if (!plot.points.length) {
    return <figure className="opt-chart">
      <figcaption>{title}</figcaption>
      <p className="opt-empty" role="status">No measured candidate yet. Points appear once an evaluation completes.</p>
    </figure>;
  }

  return <figure className="opt-chart">
    <figcaption>{title}</figcaption>
    <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} role="img"
      aria-label={`${title} by agent version, ${plot.points.length} measured points`}>
      <line x1={BOX.left} y1={BOX.top} x2={BOX.left} y2={BOX.height - BOX.bottom} className="opt-axis" />
      <line x1={BOX.left} y1={BOX.height - BOX.bottom} x2={BOX.width - BOX.right} y2={BOX.height - BOX.bottom} className="opt-axis" />
      {plot.ticks.map((tick, index) => {
        const y = BOX.top + (1 - (tick - plot.min) / (plot.max - plot.min)) * (BOX.height - BOX.top - BOX.bottom);
        return <g key={index}>
          <line x1={BOX.left} y1={y} x2={BOX.width - BOX.right} y2={y} className="opt-grid" />
          <text x={BOX.left - 8} y={y + 4} textAnchor="end" className="opt-tick">{format(tick)}</text>
        </g>;
      })}
      {plot.points.length > 1 && <polyline points={path} className="opt-line" />}
      {plot.points.map((point) => <g key={point.version}>
        <text x={point.x} y={BOX.height - BOX.bottom + 18} textAnchor="middle" className="opt-tick">v{point.version}</text>
        <circle cx={point.x} cy={point.y} r={selected === point.version ? 8 : 5}
          className={`opt-point opt-point-${point.origin === "baseline" ? "baseline" : "candidate"}`}
          aria-hidden="true" onClick={() => onSelect(point.version)}><title>{`Agent v${point.version}: ${format(point.value)}`}</title></circle>
      </g>)}
    </svg>
    <div className="opt-chart-points">
      {plot.points.map((point) => <button key={point.version} type="button"
        aria-pressed={selected === point.version} onClick={() => onSelect(point.version)}
        title={`${point.label}: ${format(point.value)}`}>
        v{point.version} {format(point.value)}
      </button>)}
    </div>
    <div className="opt-legend">
      <span><i className="opt-swatch opt-point-baseline" aria-hidden="true" />Baseline</span>
      <span><i className="opt-swatch opt-point-candidate" aria-hidden="true" />CLI candidate</span>
      {unmeasured > 0 && <span>{unmeasured} candidate{unmeasured === 1 ? "" : "s"} unmeasured, not plotted</span>}
    </div>
  </figure>;
}
