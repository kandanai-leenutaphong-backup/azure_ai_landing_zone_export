import { useState, type CSSProperties } from "react";
import { ArrowUpRight, Bookmark, Check, Copy, Layers3, RotateCcw } from "lucide-react";
import { IconButton, Segmented, type Notice } from "./primitives";

const highlights = [
  { name: "Mint", token: "mint", hex: "#E5F1EC" },
  { name: "Mist", token: "mist", hex: "#EAF3FF" },
] as const;

export function Materials({ notify }: { notify: Notice }) {
  const [gradation, setGradation] = useState(60);
  const [opacity, setOpacity] = useState(82);
  const [separation, setSeparation] = useState(16);
  const [highlight, setHighlight] = useState<"Mint" | "Mist">("Mint");
  const [ground, setGround] = useState("Porcelain");
  const [frosted, setFrosted] = useState(true);
  const [pinned, setPinned] = useState(true);
  const styles = {
    "--azs-material-strength": gradation / 100,
    "--azs-material-alpha": opacity / 100,
    "--azs-material-gap": `${separation}px`,
    "--azs-material-blur": frosted ? "10px" : "0px",
  } as CSSProperties;
  const reset = () => {
    setGradation(60);
    setOpacity(82);
    setSeparation(16);
    setHighlight("Mint");
    setGround("Porcelain");
    setFrosted(true);
  };
  async function copyRecipe() {
    const recipe = `.azure-sky .azs-material-study {\n  --azs-material-strength: ${gradation / 100};\n  --azs-material-alpha: ${opacity / 100};\n  --azs-material-gap: ${separation}px;\n  --azs-material-blur: ${frosted ? "10px" : "0px"};\n}\n/* data-highlight="${highlight}" data-ground="${ground}" */`;
    try { await navigator.clipboard.writeText(recipe); notify("Material recipe copied"); }
    catch { notify("Clipboard unavailable. Material values remain visible.", "error"); }
  }
  return <div id="materials" className="azs-material-study" role="region" aria-labelledby="azs-materials-title" data-highlight={highlight} data-ground={ground} style={styles}>
    <div className="azs-material-heading">
      <div><span className="azs-eyebrow azs-muted">MATERIAL STUDY / 01.B</span><h3 id="azs-materials-title">Light through layers.</h3></div>
      <div className="azs-row"><IconButton label="Copy material recipe" onClick={() => void copyRecipe()}><Copy size={17} /></IconButton><IconButton label="Reset materials" onClick={reset}><RotateCcw size={17} /></IconButton></div>
    </div>
    <div className="azs-material-layout">
      <div className="azs-material-plane">
        <div className="azs-material-stack">
          <div className="azs-material-sheet azs-material-sheet-far" aria-hidden="true" />
          <div className="azs-material-sheet azs-material-sheet-near" aria-hidden="true" />
          <div className="azs-material-window">
            <div className="azs-material-window-header"><span className="azs-eyebrow">AS-001 / COLLECTION</span><IconButton label={pinned ? "Unpin material reference" : "Pin material reference"} aria-pressed={pinned} onClick={() => setPinned(value => !value)}><Bookmark size={16} fill={pinned ? "currentColor" : "none"} /></IconButton></div>
            <h4>Reference atlas</h4>
            <div className="azs-material-summary"><strong>12,408</strong><span>source records</span></div>
            <div className="azs-material-reference"><span className="azs-material-marker"><Bookmark size={14} /></span><span>North observatory</span><span className="azs-material-label">{pinned ? "Pinned" : "Reference"}</span></div>
            <div className="azs-material-window-footer"><span className="azs-mono">09:42 UTC</span><button className="azs-button" onClick={() => notify("Reference atlas opened", "info")}>Open atlas <ArrowUpRight size={14} /></button></div>
          </div>
        </div>
      </div>
      <div className="azs-material-controls">
        <fieldset className="azs-fieldset"><legend>Highlight</legend><div className="azs-highlight-choices">{highlights.map(color => <button type="button" key={color.name} aria-pressed={highlight === color.name} onClick={() => setHighlight(color.name)}><span className="azs-highlight-swatch" style={{ background: `var(--azs-${color.token})` }}><Check size={13} style={{ visibility: highlight === color.name ? "visible" : "hidden" }} /></span><span>{color.name}<small className="azs-mono">{color.hex}</small></span></button>)}</div></fieldset>
        <label className="azs-field" htmlFor="azs-gradation">Gradation <output className="azs-inline-value azs-mono" htmlFor="azs-gradation">{gradation}%</output><input id="azs-gradation" type="range" min={0} max={100} step={1} value={gradation} onChange={event => setGradation(Number(event.target.value))} /></label>
        <label className="azs-field" htmlFor="azs-material-opacity">Surface opacity <output className="azs-inline-value azs-mono" htmlFor="azs-material-opacity">{opacity}%</output><input id="azs-material-opacity" type="range" min={65} max={100} step={1} value={opacity} onChange={event => setOpacity(Number(event.target.value))} /></label>
        <label className="azs-field" htmlFor="azs-layer-gap">Layer separation <output className="azs-inline-value azs-mono" htmlFor="azs-layer-gap">{separation}px</output><input id="azs-layer-gap" type="range" min={0} max={24} step={1} value={separation} onChange={event => setSeparation(Number(event.target.value))} /></label>
        <div className="azs-material-ground"><span className="azs-field">Ground</span><Segmented label="Material ground" value={ground} options={["Porcelain", "Cobalt"]} onChange={setGround} /></div>
        <label className="azs-toggle-row"><span>Frosted surface</span><input type="checkbox" role="switch" checked={frosted} onChange={event => setFrosted(event.target.checked)} /></label>
      </div>
    </div>
    <div className="azs-material-applications">
      <div className="azs-material-application"><span className="azs-eyebrow azs-muted">01 / GRADATION</span><div className="azs-material-ramp"><span>Azure</span><Layers3 size={22} /><span>Porcelain</span></div></div>
      <div className="azs-material-application"><span className="azs-eyebrow azs-muted">02 / EMPHASIS</span><div className="azs-material-emphasis"><Bookmark size={18} /><span>Selected reference</span><span className="azs-mono">AS-001</span></div></div>
      <div className="azs-material-application"><span className="azs-eyebrow azs-muted">03 / NEXT ACTION</span><div className="azs-material-command"><span>Collection ready</span><button className="azs-button" onClick={() => notify("Collection added to the review preview")}>Add to review <ArrowUpRight size={14} /></button></div></div>
    </div>
  </div>;
}
