import { useState, type ReactNode, type ButtonHTMLAttributes } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Check, CircleAlert, Info, LoaderCircle, X } from "lucide-react";

export type Notice = (message: string, tone?: "success" | "error" | "info") => void;

export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <Tooltip.Root><Tooltip.Trigger asChild><button type="button" className="azs-icon-button" aria-label={label} {...props}>{children}</button></Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="azure-sky azs-tooltip" sideOffset={8}>{label}<Tooltip.Arrow /></Tooltip.Content></Tooltip.Portal></Tooltip.Root>;
}

export function Section({ id, index, title, children, trailing }: { id: string; index: string; title: string; children: ReactNode; trailing?: ReactNode }) {
  return <section className="azs-section" id={id} aria-labelledby={`${id}-title`}><div className="azs-section-heading"><span className="azs-index">{index}</span><h2 id={`${id}-title`}>{title}</h2>{trailing}</div>{children}</section>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" | "warning" | "error" | "info" }) {
  const Symbol = tone === "success" ? Check : tone === "warning" || tone === "error" ? CircleAlert : Info;
  return <span className={`azs-badge azs-badge-${tone}`}><Symbol size={12} />{children}</span>;
}

export function Segmented({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return <div className="azs-segmented" role="group" aria-label={label}>{options.map(option => <button type="button" key={option} aria-pressed={value === option} onClick={() => onChange(option)}>{option}</button>)}</div>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <span className="azs-loading" role="status"><LoaderCircle className="azs-spin" size={16} />{label}</span>;
}

export function useLocalPreference<Value extends string>(key: string, fallback: Value, allowed: readonly Value[]) {
  const [value, setValue] = useState<Value>(() => {
    try { const saved = localStorage.getItem(key) as Value; return allowed.includes(saved) ? saved : fallback; } catch { return fallback; }
  });
  function update(next: Value) {
    setValue(next);
    try { localStorage.setItem(key, next); } catch { return; }
  }
  return [value, update] as const;
}

export function Toast({ message, tone, onClose }: { message: string; tone: "success" | "error" | "info"; onClose: () => void }) {
  return <div className={`azs-toast azs-toast-${tone}`} role={tone === "error" ? "alert" : "status"}><span className="azs-toast-symbol">{tone === "success" ? <Check size={18} /> : tone === "error" ? <CircleAlert size={18} /> : <Info size={18} />}</span><span>{message}</span><button type="button" className="azs-icon-button" aria-label="Dismiss notification" onClick={onClose}><X size={16} /></button></div>;
}

export function downloadText(filename: string, content: string, type = "text/plain") {
  const address = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = address;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(address), 1000);
}