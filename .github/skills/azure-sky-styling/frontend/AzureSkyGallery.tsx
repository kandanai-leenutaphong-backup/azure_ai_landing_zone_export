import { lazy, Suspense, useEffect, useRef, useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ArrowDown, ArrowUpRight, Building2, Download, FileCode2, Layers3, Shuffle } from "lucide-react";
import { Foundations } from "./Foundations";
import { DistantArchitecture, type ArchitectureStyle } from "./DistantArchitecture";
import { Controls } from "./Controls";
import { DataGallery } from "./DataGallery";
import { Overlays } from "./Overlays";
import { Feedback } from "./Feedback";
import { Compositions } from "./Compositions";
import { IconButton, Segmented, Toast, downloadText, useLocalPreference, type Notice } from "./primitives";
import themeSource from "./azure-sky.css?raw";
import depthSource from "./depth-effects.css?raw";
import grainData from "./assets/surface-grain.png?inline";

const styleSource = themeSource.replace('@import "./depth-effects.css";', depthSource.replace('url("./assets/surface-grain.png")', `url("${grainData}")`));
const densities = ["Comfortable", "Compact"] as const;
const Visualizations = lazy(() => import("./Visualizations"));
const sections = [["foundations", "Foundations"], ["controls", "Controls"], ["data", "Data"], ["charts", "Visualizations"], ["overlays", "Overlays"], ["feedback", "States"], ["compositions", "Compositions"]];

function initialArchitectureSeed() {
  const seed = new URLSearchParams(window.location.search).get("architecture");
  if (seed && /^\d{1,10}$/.test(seed) && Number(seed) <= 4294967295) return Number(seed);
  return crypto.getRandomValues(new Uint32Array(1))[0];
}

export function AzureSkyGallery({ applicationPreview }: { applicationPreview?: { href: string; label: string } } = {}) {
  const [density, setDensity] = useLocalPreference("azure-sky:density", "Comfortable", densities);
  const [architectureSeed, setArchitectureSeed] = useState(initialArchitectureSeed);
  const [architectureVisible, setArchitectureVisible] = useState(true);
  const [architectureStyle, setArchitectureStyle] = useState<ArchitectureStyle>(() => new URLSearchParams(window.location.search).get("architectureStyle") === "geometric" ? "Geometric" : "Painterly");
  const [notice, setNotice] = useState<{ message: string; tone: "success" | "error" | "info" } | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notify: Notice = (message, tone = "success") => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    setNotice({ message, tone });
    noticeTimer.current = setTimeout(() => setNotice(null), 5000);
  };
  useEffect(() => () => { if (noticeTimer.current) clearTimeout(noticeTimer.current); }, []);
  return (
    <Tooltip.Provider delayDuration={250}><div className="azure-sky" data-density={density}>
      <DistantArchitecture seed={architectureSeed} visible={architectureVisible} variant={architectureStyle} onFallback={() => notify("Painterly masks unavailable. Showing geometric architecture.", "error")} />
      <a className="azs-skip" href="#specimens">Skip to specimens</a>
      <header className="azs-topbar">
        <a className="azs-wordmark" href="#"><Layers3 size={24} /><span>AZURE SKY</span></a>
        <span className="azs-mono">THE COMPONENT ATLAS / VOL. 001</span>
        <div className="azs-row"><span className="azs-badge azs-badge-inverse">Synthetic data</span><a href="/plain.html" className="azs-icon-button azs-html-link" aria-label="Open plain HTML specimen" title="Open plain HTML specimen"><FileCode2 size={18} /></a><IconButton label="Download Azure Sky stylesheet" onClick={() => { downloadText("azure-sky.css", styleSource, "text/css"); notify("Stylesheet downloaded"); }}><Download size={18} /></IconButton></div>
      </header>
      <main>
        <section className="azs-intro" aria-labelledby="azs-title">
          <div>
            <span className="azs-eyebrow">COMPONENT ATLAS / 2026</span>
            <h1 id="azs-title">Azure Sky</h1>
          </div>
          <div className="azs-row"><a className="azs-button azs-button-cloud" href="#specimens">The collection <ArrowDown size={16} /></a><a className="azs-button azs-button-glass" href="#materials">Material study <ArrowUpRight size={16} /></a><a className="azs-button azs-button-glass" href="#depth">Surface depth <ArrowUpRight size={16} /></a>{applicationPreview && <a className="azs-button azs-button-cloud" href={applicationPreview.href}>{applicationPreview.label}<ArrowUpRight size={16} /></a>}</div>
        </section>
        <nav className="azs-section-nav" aria-label="Collection sections">{sections.map(([id, title], index) => <a href={`#${id}`} key={id}><span className="azs-mono">0{index + 1}</span>{title}</a>)}</nav>
        <div className="azs-workbench" id="specimens" tabIndex={-1}>
          <div className="azs-workbench-heading"><span className="azs-eyebrow">COMPONENTS / MATERIALS / INTERACTIONS</span><div className="azs-workbench-tools"><div className="azs-architecture-controls" role="group" aria-label="Distant architecture"><IconButton label="Distant architecture" aria-pressed={architectureVisible} onClick={() => setArchitectureVisible(value => !value)}><Building2 size={18} /></IconButton><IconButton label="Generate new distant architecture" disabled={!architectureVisible} onClick={() => setArchitectureSeed(current => (current + 2654435761) >>> 0)}><Shuffle size={17} /></IconButton><Segmented label="Architecture style" value={architectureStyle} options={["Painterly", "Geometric"]} onChange={value => setArchitectureStyle(value as ArchitectureStyle)} /></div><Segmented label="Density" value={density} options={[...densities]} onChange={value => setDensity(value as typeof density)} /></div></div>
          <Foundations notify={notify} />
          <Controls notify={notify} />
          <DataGallery notify={notify} />
          <Suspense fallback={<div className="azs-chart-loading" role="status">Loading visualizations...</div>}><Visualizations /></Suspense>
          <Overlays notify={notify} sections={sections} />
          <Feedback notify={notify} />
          <Compositions notify={notify} />
        </div>
      </main>
      <footer className="azs-footer"><Layers3 size={22} /><span>AZURE SKY</span><span className="azs-mono">VISUAL STUDY 001 / SYNTHETIC FIXTURES</span><a href="#">Back to top <ArrowUpRight size={14} /></a></footer>
      {notice && <Toast {...notice} onClose={() => setNotice(null)} />}
    </div></Tooltip.Provider>
  );
}