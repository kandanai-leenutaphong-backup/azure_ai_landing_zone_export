import { useEffect, useRef, useState } from "react";
import { generateDistantArchitecture, paintDistantArchitecture, type PainterlyArchitectureMask } from "./distantArchitecture";
import { loadPainterlyArchitectureMasks } from "./painterlyArchitecture";
import "./distant-architecture.css";

export type ArchitectureStyle = "Painterly" | "Geometric";

export function DistantArchitecture({ seed, visible = true, tint = "#345a80", variant = "Geometric", onFallback }: { seed: number; visible?: boolean; tint?: string; variant?: ArchitectureStyle; onFallback?: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const fallbackHandler = useRef(onFallback);
  const [image, setImage] = useState<{ source: string; seed: number; width: number; height: number; milliseconds: number; variant: ArchitectureStyle; maskCount: number } | null>(null);
  useEffect(() => { fallbackHandler.current = onFallback; }, [onFallback]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const scene = generateDistantArchitecture(seed);
    const canvas = document.createElement("canvas");
    const reducedTransparency = matchMedia("(prefers-reduced-transparency: reduce)");
    const forcedColors = matchMedia("(forced-colors: active)");
    let lastSize = "";
    let disposed = false;
    let loading = false;
    let ready = variant === "Geometric";
    let renderedVariant = variant;
    let masks: readonly PainterlyArchitectureMask[] = [];
    const render = () => {
      if (disposed || reducedTransparency.matches || forcedColors.matches) return;
      const bounds = element.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      if (!ready) {
        if (!loading) {
          loading = true;
          void loadPainterlyArchitectureMasks().then(loaded => {
            if (disposed) return;
            masks = loaded;
            ready = true;
            render();
          }, () => {
            if (disposed) return;
            ready = true;
            renderedVariant = "Geometric";
            fallbackHandler.current?.();
            render();
          });
        }
        return;
      }
      const size = `${Math.round(bounds.width)}x${Math.round(bounds.height)}`;
      if (lastSize === size) return;
      const started = performance.now();
      const source = paintDistantArchitecture(canvas, scene, bounds.width, bounds.height, tint, masks);
      lastSize = size;
      setImage({ source, seed: scene.seed, width: canvas.width, height: canvas.height, milliseconds: performance.now() - started, variant: renderedVariant, maskCount: masks.length });
    };
    const observer = new ResizeObserver(render);
    observer.observe(element);
    reducedTransparency.addEventListener("change", render);
    forcedColors.addEventListener("change", render);
    render();
    return () => {
      disposed = true;
      observer.disconnect();
      reducedTransparency.removeEventListener("change", render);
      forcedColors.removeEventListener("change", render);
    };
  }, [seed, tint, variant]);
  return <div className="azs-distant-architecture" ref={host} hidden={!visible} aria-hidden="true" data-architecture-seed={image?.seed} data-architecture-style={image?.variant} data-mask-count={image?.maskCount} data-render-ms={image?.milliseconds.toFixed(2)}>
    {image && <img src={image.source} alt="" width={image.width} height={image.height} draggable={false} />}
  </div>;
}