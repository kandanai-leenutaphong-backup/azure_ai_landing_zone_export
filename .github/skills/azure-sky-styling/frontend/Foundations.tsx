import { ArrowUpRight, Bookmark, Check, Copy, Layers3 } from "lucide-react";
import { useState } from "react";
import { Badge, IconButton, Section, type Notice } from "./primitives";
import { Materials } from "./Materials";
import { DepthStudy } from "./DepthStudy";

export const palette = [
  { name: "Cloud", token: "cloud", hex: "#EFF3F8", dark: false },
  { name: "Porcelain", token: "porcelain", hex: "#F7FBFF", dark: false },
  { name: "Mist", token: "mist", hex: "#EAF3FF", dark: false },
  { name: "Open Sky", token: "sky", hex: "#4F8ED8", dark: false },
  { name: "Action Azure", token: "action", hex: "#2463B3", dark: true },
  { name: "Cobalt", token: "cobalt", hex: "#123F91", dark: true },
  { name: "Naval Ink", token: "ink", hex: "#102D50", dark: true },
];

export function Foundations({ notify }: { notify: Notice }) {
  const [bookmarks, setBookmarks] = useState<string[]>([]);
  async function copyColor(name: string, color: string) {
    try { await navigator.clipboard.writeText(color); notify(`${name} ${color} copied`); }
    catch { notify("Clipboard unavailable. Color values remain visible.", "error"); }
  }
  return <Section id="foundations" index="01" title="The spectrum of daylight" trailing={<span className="azs-section-tag"><Layers3 size={14} /> Foundations</span>}>
    <div className="azs-palette">{palette.map(color => <button type="button" className="azs-swatch" key={color.name} aria-label={`Copy ${color.name} ${color.hex}`} onClick={() => void copyColor(color.name, color.hex)}><span className="azs-swatch-color" style={{ background: `var(--azs-${color.token})`, color: color.dark ? "white" : "var(--azs-ink)" }}><Copy size={14} /></span><span className="azs-swatch-name">{color.name}</span><span className="azs-mono azs-muted">{color.hex}</span></button>)}</div>
    <div className="azs-three-surfaces">{["Porcelain", "Mist", "Cobalt"].map((surface, index) => <div className={`azs-surface-sample azs-sample-${surface.toLowerCase()} ${surface === "Cobalt" ? "azs-inverse" : ""}`} key={surface}><div className="azs-row azs-between"><span className="azs-eyebrow">SURFACE / 0{index + 1}</span><IconButton label={`${bookmarks.includes(surface) ? "Unpin" : "Pin"} ${surface}`} aria-pressed={bookmarks.includes(surface)} onClick={() => setBookmarks(current => current.includes(surface) ? current.filter(value => value !== surface) : [...current, surface])}><Bookmark size={17} fill={bookmarks.includes(surface) ? "currentColor" : "none"} /></IconButton></div><h3>{surface === "Porcelain" ? "Room to think." : surface === "Mist" ? "Between earth & sky." : "A deeper perspective."}</h3><div className="azs-specimen-number">12,408<span className="azs-mono">records</span></div><div className="azs-row azs-between"><Badge tone={surface === "Cobalt" ? "neutral" : "success"}>Reviewed</Badge><button className={`azs-button ${surface === "Cobalt" ? "azs-button-cloud" : ""}`} onClick={() => notify(`${surface} specimen opened`, "info")}>View <ArrowUpRight size={14} /></button></div></div>)}</div>
    <div className="azs-type-row"><div><span className="azs-eyebrow azs-muted">BARLOW CONDENSED / 600</span><p className="azs-type-display">Clarity at every altitude.</p></div><div><span className="azs-eyebrow azs-muted">IBM PLEX SANS / 400, 500, 600</span><p className="azs-type-body">The horizon is wide. The details are precise.</p><span className="azs-mono azs-muted">IBM PLEX MONO / AS-001 : 09:42:08 UTC</span></div><div className="azs-contrast-stamp"><Check size={18} /><strong>13.35:1</strong><span>Ink on Porcelain</span></div></div>
    <Materials notify={notify} />
    <DepthStudy notify={notify} />
  </Section>;
}