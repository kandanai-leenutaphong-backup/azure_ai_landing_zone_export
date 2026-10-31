import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { resizePair, toggleColumn } from "./trajectory";

export function useOptimizationColumns() {
  const [widths, setWidths] = useState<number[]>(() => {
    const defaults = window.matchMedia("(max-width: 900px)").matches ? [0, 0, 0, 100] : [18, 23, 28, 31];
    try {
      const saved = JSON.parse(localStorage.getItem("agent-optimization.columns") || "null");
      if (Array.isArray(saved) && saved.length === 4 && saved.every((width) => Number.isFinite(width) && width >= 0)) {
        const total = saved.reduce((sum, width) => sum + width, 0);
        return total ? saved.map((width) => width * 100 / total) : saved;
      }
    } catch { /* An unavailable local preference does not block the workspace. */ }
    return defaults;
  });
  const shell = useRef<HTMLDivElement>(null);

  function update(next: number[]) {
    setWidths(next);
    try { localStorage.setItem("agent-optimization.columns", JSON.stringify(next)); } catch { /* Optional preference. */ }
  }

  function pointer(index: number, event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const start = [...widths];
    const origin = event.clientX;
    const available = Math.max(1, (shell.current?.clientWidth ?? window.innerWidth) - 24);
    const move = (next: globalThis.PointerEvent) => update(resizePair(start, index, (next.clientX - origin) * 100 / available));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  }

  function keyboard(index: number, event: KeyboardEvent<HTMLDivElement>) {
    const delta = event.key === "Home" ? -100 : event.key === "End" ? 100
      : event.key === "ArrowLeft" ? -2 : event.key === "ArrowRight" ? 2 : 0;
    if (delta) { event.preventDefault(); update(resizePair(widths, index, delta)); }
  }

  return { widths, shell, toggle: (index: number) => update(toggleColumn(widths, index)),
    reset: () => update([18, 23, 28, 31]), focus: (index: number) => update(widths.map((_, position) => position === index ? 100 : 0)),
    separator: (index: number, name: string) => ({
      className: "opt-separator", role: "separator", tabIndex: 0, "aria-label": name,
      "aria-orientation": "vertical" as const, "aria-valuenow": Math.round(widths[index]),
      "aria-valuemin": 0, "aria-valuemax": Math.round(widths[index] + widths[index + 1]),
      onPointerDown: (event: PointerEvent<HTMLDivElement>) => pointer(index, event),
      onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => keyboard(index, event),
      onDoubleClick: () => update(resizePair(widths, index, (widths[index + 1] - widths[index]) / 2)),
    }),
  };
}