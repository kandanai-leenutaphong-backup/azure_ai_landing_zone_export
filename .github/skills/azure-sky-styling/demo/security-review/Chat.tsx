import { useEffect, useRef, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { ArrowUpRight, Bot, Brain, Check, ChevronDown, FileText, Maximize2, Minimize2, Send, Sparkles, Square, Wrench } from "lucide-react";
import { IconButton } from "../../frontend/primitives";
import { type PreviewSituation } from "./fixtures";
import { Empty, type PreviewState } from "./Investigation";

type Message = { id: number; role: "Analyst" | "Review agent"; text: string; citations?: string[]; host?: string };
export function Chat({ selected, state, request, expanded, onExpandedChange, onEvidence }: { selected: PreviewSituation; state: PreviewState; request: { id: number; text: string } | null; expanded: boolean; onExpandedChange: () => void; onEvidence: () => void }) {
  const [tab, setTab] = useState("defender");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);
  const [stopped, setStopped] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const applied = useRef(0);
  const nextId = useRef(0);
  const scroll = useRef<HTMLDivElement>(null);
  const current = state === "results";
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }, [messages, running]);
  useEffect(() => {
    if (!request || applied.current === request.id) return;
    applied.current = request.id;
    setTab("defender");
    setInput(request.text);
  }, [request]);
  function send(text: string) {
    const prompt = text.trim();
    if (!prompt || running || !current) return;
    const context = selected;
    setMessages(previous => [...previous, { id: ++nextId.current, role: "Analyst", text: prompt }]);
    setInput("");
    setRunning(true);
    setStopped(false);
    timer.current = setTimeout(() => {
      setMessages(previous => [...previous, { id: ++nextId.current, role: "Review agent", text: `${context.summary} ${context.alternative}`, citations: context.evidence.slice(0, 2).map(row => row.id), host: context.host }]);
      setRunning(false);
    }, 450);
  }
  function stop() { if (timer.current) clearTimeout(timer.current); setRunning(false); setStopped(true); }
  return <section className={`rv-column rv-chat ${expanded ? "rv-expanded" : ""}`} aria-label="Review agent chat">
    <div className="rv-agent-context"><span className="rv-agent-dot" /><div><strong>Review agent <span>preview</span></strong><p>{current ? `${selected.host} / ${selected.principal}` : "No situation pinned"}</p></div><IconButton label={expanded ? "Restore agent chat" : "Expand agent chat"} onClick={onExpandedChange}>{expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</IconButton></div>
    <Tabs.Root value={tab} onValueChange={setTab} className="rv-chat-shell"><Tabs.List className="rv-chat-tabs" aria-label="Agent workloads"><Tabs.Trigger value="defender"><Bot size={13} />Review agent</Tabs.Trigger><Tabs.Trigger value="summary"><FileText size={13} />Situation Summary</Tabs.Trigger></Tabs.List>
      <Tabs.Content value="defender" className="rv-chat-tab" forceMount hidden={tab !== "defender"}>
        <div className="rv-messages" ref={scroll} aria-label="Conversation">
          {current ? <article className="rv-agent-investigation"><div className="rv-message-label"><Sparkles size={13} /><span>Investigation of the selected situation</span></div><div className="rv-workload-status"><Check size={12} /><span>Fixture complete</span><small>{selected.confidence} confidence</small></div><details className="rv-thinking"><summary><Brain size={14} /><span>Assessment rationale</span><ChevronDown size={12} /></summary><p>Fixture reasoning, not evidence: compare record times, identify missing attribution, and retain plausible alternatives.</p></details><details className="rv-chat-tool"><summary><Wrench size={13} /><span>Situation evidence</span><span className="rv-success">{selected.evidence.length} rows</span><ChevronDown size={11} /></summary><pre>{JSON.stringify({ situation_id: selected.id, source: "synthetic fixture", rows: selected.evidence.length }, null, 2)}</pre><button onClick={onEvidence}>Open cited records<ArrowUpRight size={12} /></button></details><div className="rv-agent-result"><strong>{selected.headline}</strong><p>{selected.narrative}</p><div className="rv-citations">{selected.evidence.slice(0, 2).map(row => <button key={row.id} onClick={onEvidence}><FileText size={10} />{row.id}</button>)}</div></div></article> : <Empty title="No situation context" detail="Replay a fixture window to populate the investigation." />}
          {messages.length === 0 && current && <div className="rv-starters"><span className="azs-eyebrow">CONTINUE THE INVESTIGATION</span>{["Reconstruct the timeline and cite evidence.", "What would change this assessment?"].map(prompt => <button key={prompt} disabled={running} onClick={() => send(prompt)}>{prompt}<ArrowUpRight size={13} /></button>)}</div>}
          {messages.map(message => <article key={message.id} className={`rv-message ${message.role === "Analyst" ? "rv-message-user" : "rv-message-agent"}`}><span className="rv-message-label">{message.role}</span><p>{message.text}</p>{message.citations && <><span className="rv-fixture-note">Fixed fixture response / {message.host} / no model call</span><div className="rv-citations">{message.citations.map(id => <span key={id}>{id}</span>)}</div></>}</article>)}
          {running && <p className="rv-chat-running" role="status"><span className="rv-agent-dot" />Preparing fixture response...</p>}
          {stopped && <p className="rv-fixture-note" role="status">Fixture response stopped.</p>}
        </div>
        <form className="rv-composer" onSubmit={event => { event.preventDefault(); send(input); }}><label className="azs-sr-only" htmlFor="rv-chat-input">Message Review agent</label><textarea id="rv-chat-input" rows={3} value={input} disabled={running || !current} placeholder="Ask Review agent to investigate..." onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(input); } }} /><div className="rv-composer-footer"><span>Fixture response / no model connected</span>{running ? <IconButton label="Stop fixture response" onClick={stop}><Square size={15} /></IconButton> : <IconButton label="Send message" type="submit" disabled={!input.trim() || !current}><Send size={16} /></IconButton>}</div></form>
      </Tabs.Content>
      <Tabs.Content value="summary" className="rv-chat-tab" forceMount hidden={tab !== "summary"}><div className="rv-messages">{current ? <article className="rv-message rv-message-agent"><div className="rv-message-label"><FileText size={13} /><span>Situation summary</span></div><div className="rv-workload-status"><Check size={12} />Fixture complete</div><p>{selected.summary}</p><span className="rv-fixture-note">Synthetic situation envelope / no model call</span><button className="azs-button azs-button-ghost" onClick={onEvidence}>Review the evidence<ArrowUpRight size={13} /></button></article> : <Empty title="No summary context" detail="Select a situation to view its fixture summary." />}</div></Tabs.Content>
    </Tabs.Root>
  </section>;
}