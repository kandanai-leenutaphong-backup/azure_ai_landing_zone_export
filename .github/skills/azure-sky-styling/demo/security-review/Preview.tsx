import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tabs from "@radix-ui/react-tabs";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ArrowLeft, Layers3, RotateCcw, Settings, X } from "lucide-react";
import { IconButton, Segmented } from "../../frontend/primitives";
import { Scanner, ToolBoard, type BoardView, type PreviewState } from "./Investigation";
import { Chat } from "./Chat";
import { Explorer } from "./Explorer";
import { situations, type PreviewSituation } from "./fixtures";

export function SecurityReviewPreview() {
  const [workspace, setWorkspace] = useState("investigation");
  const [state, setState] = useState<PreviewState>("results");
  const [selected, setSelected] = useState(situations[0]);
  const [view, setView] = useState<BoardView>("situation");
  const [request, setRequest] = useState<{ id: number; text: string } | null>(null);
  const requestId = useRef(0);
  const [mobilePanel, setMobilePanel] = useState("Tool board");
  const [expanded, setExpanded] = useState<"board" | "chat" | null>(null);
  const [columns, setColumns] = useState([25, 45, 30]);
  const layout = useRef<HTMLDivElement>(null);
  const drag = useRef<{ index: number; start: number; columns: number[] } | null>(null);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setExpanded(null); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  function select(situation: PreviewSituation) { setSelected(situation); setView("situation"); }
  function ask(text: string) { setRequest({ id: ++requestId.current, text }); setMobilePanel("Chat"); }
  function adjust(index: number, offset: number, original = columns) {
    const next = [...original];
    const delta = Math.max(20 - original[index], Math.min(original[index + 1] - 20, offset));
    next[index] += delta;
    next[index + 1] -= delta;
    setColumns(next);
  }
  function resize(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current || !layout.current) return;
    adjust(drag.current.index, (event.clientX - drag.current.start) / layout.current.getBoundingClientRect().width * 100, drag.current.columns);
  }
  function divider(index: number, label: string) {
    return <div role="separator" aria-orientation="vertical" aria-label={label} aria-valuenow={Math.round(columns[index])} aria-valuemin={20} aria-valuemax={columns[index] + columns[index + 1] - 20} tabIndex={0} className="rv-divider" onPointerDown={event => { drag.current = { index, start: event.clientX, columns: [...columns] }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={resize} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); adjust(index, event.key === "ArrowRight" ? 2 : -2); } }} />;
  }
  return <Tooltip.Provider delayDuration={200}><div className="azure-sky rv-preview">
    <a className="azs-skip" href="#rv-workspace">Skip to workspace</a>
    <Tabs.Root value={workspace} onValueChange={setWorkspace} className="rv-app">
      <header className="rv-header">
        <a className="rv-brand" href="./security-review.html"><span className="rv-brand-mark">S</span><span><strong>Security Review</strong><small>Security operations workspace</small></span></a>
        <span className="rv-replay">Historical replay</span>
        <Tabs.List className="rv-workspace-tabs" aria-label="Workspace"><Tabs.Trigger value="investigation">Investigation</Tabs.Trigger><Tabs.Trigger value="explorer">Explorer</Tabs.Trigger></Tabs.List>
        <div className="rv-header-actions"><a href="./index.html" className="rv-back" title="Back to the Azure Sky atlas"><ArrowLeft size={14} /><span>Style atlas</span></a><Dialog.Root><Dialog.Trigger asChild><button className="azs-icon-button" aria-label="Configuration" title="Configuration"><Settings size={18} /></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="azure-sky azs-dialog-overlay" /><Dialog.Content className="azure-sky azs-dialog rv-config"><div className="azs-dialog-heading"><Dialog.Title>Configuration</Dialog.Title><Dialog.Close asChild><button className="azs-icon-button" aria-label="Close configuration"><X size={18} /></button></Dialog.Close></div><Dialog.Description className="azs-dialog-description">Azure Sky preview / synthetic fixtures</Dialog.Description><dl className="azs-detail-list"><div><dt>ADX</dt><dd>Not connected</dd></div><div><dt>Model</dt><dd>Not connected</dd></div><div><dt>Identity</dt><dd>Local visual preview</dd></div></dl></Dialog.Content></Dialog.Portal></Dialog.Root></div>
      </header>
      <div className="rv-preview-strip"><span><Layers3 size={13} />Azure Sky <span className="rv-strip-divider" />Synthetic fixtures / no live connections</span><div className="rv-preview-options"><label htmlFor="rv-preview-state">Preview state</label><select id="rv-preview-state" value={state} disabled={state === "loading"} onChange={event => setState(event.target.value as PreviewState)}><option value="results">Results</option><option value="idle">Idle</option><option value="empty">Empty</option><option value="error">Error</option>{state === "loading" && <option value="loading">Loading</option>}</select><IconButton label="Reset column widths" onClick={() => setColumns([25, 45, 30])}><RotateCcw size={13} /></IconButton></div></div>
      <div id="rv-workspace" className="rv-workspace" tabIndex={-1}>
        <Tabs.Content value="investigation" className="rv-workspace-content" forceMount hidden={workspace !== "investigation"}>
          <div className="rv-mobile-panels"><Segmented label="Investigation panels" value={mobilePanel} options={["Scanner", "Tool board", "Chat"]} onChange={setMobilePanel} /></div>
          <div className="rv-investigation" ref={layout} data-mobile={mobilePanel} data-expanded={expanded || "none"} style={{ "--rv-left": `${columns[0]}fr`, "--rv-center": `${columns[1]}fr`, "--rv-right": `${columns[2]}fr` } as CSSProperties}>
            <Scanner selected={selected} onSelect={select} onInvestigate={situation => { select(situation); setMobilePanel("Tool board"); }} state={state} onStateChange={setState} />
            {divider(0, "Resize scanner and tool board")}
            <ToolBoard selected={selected} state={state} view={view} onViewChange={setView} onAsk={ask} expanded={expanded === "board"} onExpandedChange={() => setExpanded(value => value === "board" ? null : "board")} />
            {divider(1, "Resize tool board and agent chat")}
            <Chat selected={selected} state={state} request={request} expanded={expanded === "chat"} onExpandedChange={() => setExpanded(value => value === "chat" ? null : "chat")} onEvidence={() => { setView("evidence"); setMobilePanel("Tool board"); }} />
          </div>
        </Tabs.Content>
        <Tabs.Content value="explorer" className="rv-workspace-content" forceMount hidden={workspace !== "explorer"}><Explorer /></Tabs.Content>
      </div>
    </Tabs.Root>
  </div></Tooltip.Provider>;
}