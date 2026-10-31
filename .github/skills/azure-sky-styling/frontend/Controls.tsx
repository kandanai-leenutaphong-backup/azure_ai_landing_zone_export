import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDownToLine, ArrowRight, Bold, Check, ChevronDown, Copy, Eye, EyeOff, Italic, Minus, Plus, Save, Search, SlidersHorizontal, Trash2, Underline, UploadCloud, X } from "lucide-react";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { Badge, IconButton, Section, Segmented, Spinner, type Notice } from "./primitives";

export function Controls({ notify }: { notify: Notice }) {
  const [workspace, setWorkspace] = useState(() => {
    try { return localStorage.getItem("azure-sky:workspace") || "North observatory"; } catch { return "North observatory"; }
  });
  const [email, setEmail] = useState("observer@example.com");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [contrast, setContrast] = useState(68);
  const [quantity, setQuantity] = useState(4);
  const [view, setView] = useState("Grid");
  const [tags, setTags] = useState(["Atmosphere", "Reference", "Reviewed"]);
  const [filename, setFilename] = useState("");
  const [dragging, setDragging] = useState(false);
  const [style, setStyle] = useState({ bold: false, italic: false, underline: false });
  const indeterminate = useRef<HTMLInputElement>(null);
  const [partial, setPartial] = useState(true);
  useEffect(() => { if (indeterminate.current) indeterminate.current.indeterminate = partial; }, [partial]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!workspace.trim()) { setError("A workspace name is required."); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError("Enter a valid email address."); return; }
    setError("");
    try {
      localStorage.setItem("azure-sky:workspace", workspace.trim());
      setSaved(workspace.trim());
      notify("Workspace saved in this browser");
    } catch { notify("Browser storage unavailable. Changes are session-only.", "error"); }
  }
  function runSample() {
    setBusy(true);
    timer.current = setTimeout(() => { setBusy(false); notify("Sample preparation complete"); }, 1100);
  }
  function acceptFile(file?: File) {
    if (!file) return;
    if (!/\.(csv|json|txt)$/i.test(file.name)) { notify("Choose a CSV, JSON, or text fixture.", "error"); return; }
    setFilename(file.name);
    notify(`${file.name} selected locally`);
  }
  return <Section id="controls" index="02" title="Precision in the small things" trailing={<span className="azs-section-tag"><SlidersHorizontal size={14} /> Controls</span>}>
    <div className="azs-action-band">
      <div className="azs-row"><button className="azs-button" onClick={runSample} disabled={busy}>{busy ? <Spinner label="Preparing" /> : <><Plus size={16} />New collection</>}</button><button className="azs-button azs-button-secondary" onClick={() => notify("Reference AS-001 added")}><Plus size={16} />Add reference</button><button className="azs-button azs-button-ghost" onClick={() => document.getElementById("compositions")?.scrollIntoView()}>View archive <ArrowRight size={15} /></button></div>
      <div className="azs-row"><div className="azs-split-button"><button className="azs-button azs-button-secondary" onClick={() => notify("Draft saved for this session")}><Save size={15} />Save draft</button><Dropdown.Root><Dropdown.Trigger asChild><button className="azs-button azs-button-secondary azs-square" aria-label="More save options"><ChevronDown size={15} /></button></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="azure-sky azs-menu" sideOffset={6}><Dropdown.Item onSelect={() => notify("A session copy was prepared")}>Save a copy</Dropdown.Item><Dropdown.Item onSelect={() => notify("Local draft archived")}>Archive draft</Dropdown.Item></Dropdown.Content></Dropdown.Portal></Dropdown.Root></div><button className="azs-button azs-button-danger" onClick={() => { setTags([]); notify("Local specimen tags cleared", "info"); }}><Trash2 size={15} />Clear tags</button></div>
    </div>
    <div className="azs-state-strip">{["Default", "Hover", "Focus", "Active", "Disabled", "Busy"].map(state => <div key={state}><button className={`azs-button azs-state-${state.toLowerCase()}`} disabled={state === "Disabled" || state === "Busy"} aria-label={`${state} action specimen`} onClick={() => notify(`${state} action activated`)}>{state === "Busy" ? <Spinner label="Saving" /> : <>Continue<ArrowRight size={14} /></>}</button><span className="azs-mono azs-muted">{state}</span></div>)}</div>
    <div className="azs-controls-grid">
      <form className="azs-form" onSubmit={submit} noValidate>
        <div className="azs-subheading"><h3>Field instruments</h3><span className="azs-mono">INPUT / 01</span></div>
        <label className="azs-field">Workspace name <span className="azs-required">*</span><input value={workspace} onChange={event => setWorkspace(event.target.value)} aria-invalid={!!error && !workspace.trim()} placeholder="Untitled workspace" required /></label>
        <div className="azs-form-pair"><label className="azs-field">Contact email<input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="observer@example.com" aria-invalid={!!error && !!workspace.trim()} /></label><label className="azs-field">Region<select defaultValue="North sector"><option>North sector</option><option>East sector</option><option>South sector</option></select></label></div>
        <label className="azs-field">Search reference<div className="azs-input-icon"><Search size={16} /><input type="search" list="azs-references" placeholder="Find a reference..." aria-label="Search reference" /><datalist id="azs-references"><option value="Cirrus array" /><option value="Stratus relay" /><option value="Cumulus archive" /></datalist></div></label>
        <div className="azs-form-pair"><label className="azs-field">Private note<div className="azs-input-action"><input type={revealed ? "text" : "password"} placeholder="Private note" autoComplete="off" aria-label="Private note" /><IconButton label={revealed ? "Hide private note" : "Show private note"} onClick={() => setRevealed(value => !value)}>{revealed ? <EyeOff size={16} /> : <Eye size={16} />}</IconButton></div></label><label className="azs-field">Reference ID<input defaultValue="AS-001-2026" readOnly /></label></div>
        <div className="azs-form-pair"><label className="azs-field">Start date<input type="date" defaultValue="2026-09-01" max="2026-09-30" /></label><label className="azs-field">End date<input type="date" defaultValue="2026-09-09" min="2026-09-01" /></label></div>
        <label className="azs-field">Notes<textarea rows={3} placeholder="Add an observation..." defaultValue="Fine structure along the horizon. Keep the original source alongside the annotated copy." /></label>
        <div className="azs-form-pair"><label className="azs-field">Unavailable source<input value="Archive read-only" disabled /></label><label className="azs-field">Invalid reference<input defaultValue="AS-?" aria-invalid="true" aria-describedby="azs-reference-error" /><span className="azs-field-error" id="azs-reference-error">Reference ID must contain six digits.</span></label></div>
        {error && <p className="azs-field-error" role="alert">{error}</p>}
        <div className="azs-row"><button type="submit" className="azs-button"><Check size={15} />Save workspace</button>{saved && <span className="azs-save-result" role="status">Saved: {saved}</span>}</div>
      </form>
      <div className="azs-selection-lab">
        <div className="azs-subheading"><h3>A sense of control</h3><span className="azs-mono">SELECTION / 02</span></div>
        <div className="azs-form-pair"><fieldset className="azs-fieldset"><legend>Layers</legend><label className="azs-check"><input type="checkbox" defaultChecked />Cloud cover</label><label className="azs-check"><input type="checkbox" />Flight paths</label><label className="azs-check"><input ref={indeterminate} type="checkbox" checked={false} onChange={() => setPartial(value => !value)} aria-checked={partial ? "mixed" : false} />Partial selection</label><label className="azs-check"><input type="checkbox" disabled />Archived layer</label></fieldset><fieldset className="azs-fieldset"><legend>Projection</legend>{["Orthographic", "Perspective", "Isometric"].map((value, index) => <label className="azs-check" key={value}><input type="radio" name="projection" value={value} defaultChecked={index === 0} />{value}</label>)}</fieldset></div>
        <div className="azs-toggle-list"><label className="azs-toggle-row"><span>Show annotations<span className="azs-muted">Reference labels</span></span><input type="checkbox" role="switch" defaultChecked /></label><label className="azs-toggle-row"><span>Automatic grouping<span className="azs-muted">Collection preferences</span></span><input type="checkbox" role="switch" /></label></div>
        <label className="azs-field">Overlay opacity <span className="azs-inline-value azs-mono">{contrast}%</span><input type="range" min="0" max="100" value={contrast} onChange={event => setContrast(Number(event.target.value))} style={{ "--azs-range": `${contrast}%` } as React.CSSProperties} /></label>
        <div className="azs-row azs-between"><label className="azs-field">Samples<div className="azs-stepper"><IconButton label="Decrease samples" onClick={() => setQuantity(value => Math.max(1, value - 1))} disabled={quantity <= 1}><Minus size={15} /></IconButton><input type="number" min={1} max={12} value={quantity} aria-label="Samples" onChange={event => setQuantity(Math.min(12, Math.max(1, Number(event.target.value))))} /><IconButton label="Increase samples" onClick={() => setQuantity(value => Math.min(12, value + 1))} disabled={quantity >= 12}><Plus size={15} /></IconButton></div></label><div className="azs-field"><span>Collection view</span><Segmented label="Collection view" value={view} options={["Grid", "List", "Timeline"]} onChange={setView} /></div></div>
        <div className="azs-view-preview" data-view={view} role="group" aria-label={`${view} preview`}>{Array.from({ length: quantity }, (_, index) => <span key={index}><span className="azs-preview-dot" />{view !== "Grid" && `Reference ${String(index + 1).padStart(2, "0")}`}</span>)}</div>
        <div className="azs-row azs-tag-list">{tags.map(tag => <span className="azs-tag" key={tag}>{tag}<button type="button" aria-label={`Remove ${tag} tag`} onClick={() => setTags(values => values.filter(value => value !== tag))}><X size={12} /></button></span>)}<IconButton label="Add Fieldwork tag" onClick={() => setTags(values => values.includes("Fieldwork") ? values : [...values, "Fieldwork"])}><Plus size={15} /></IconButton></div>
        <div className="azs-format-bar"><div className="azs-row">{[{ key: "bold", icon: Bold }, { key: "italic", icon: Italic }, { key: "underline", icon: Underline }].map(({ key, icon: Symbol }) => <IconButton key={key} label={key} aria-pressed={style[key as keyof typeof style]} onClick={() => setStyle(current => ({ ...current, [key]: !current[key as keyof typeof style] }))}><Symbol size={16} /></IconButton>)}<span className="azs-format-divider" /><IconButton label="Copy specimen reference" onClick={async () => { try { await navigator.clipboard.writeText("AS-001"); notify("Reference copied"); } catch { notify("Clipboard unavailable", "error"); } }}><Copy size={16} /></IconButton></div><p style={{ fontWeight: style.bold ? 600 : 400, fontStyle: style.italic ? "italic" : "normal", textDecoration: style.underline ? "underline" : "none" }}>Above the ordinary.</p></div>
        <label className={`azs-dropzone ${dragging ? "azs-dragging" : ""}`} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]); }}><input type="file" accept=".csv,.json,.txt" aria-label="Choose a fixture file" onChange={event => acceptFile(event.target.files?.[0])} /><UploadCloud size={26} /><strong>{filename || "Choose a fixture"}</strong><span className="azs-muted">CSV / JSON / TXT</span>{filename && <Badge tone="success">Selected locally</Badge>}</label>
        {filename && <button className="azs-button azs-button-ghost" onClick={() => setFilename("")}><X size={14} />Remove file</button>}
      </div>
    </div>
    <div className="azs-size-line"><button className="azs-button azs-button-small" onClick={() => notify("Small action activated")}>Small <ArrowRight size={12} /></button><button className="azs-button" onClick={() => notify("Regular action activated")}>Regular <ArrowRight size={15} /></button><button className="azs-button azs-button-large" onClick={() => notify("Large action activated")}>Large <ArrowRight size={18} /></button><button className="azs-button azs-button-secondary azs-long-button" onClick={() => notify("Extended collection metadata is ready", "info")}><ArrowDownToLine size={16} />Download extended collection metadata</button></div>
  </Section>;
}