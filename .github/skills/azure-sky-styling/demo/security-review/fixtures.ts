export type EvidenceRow = {
  id: string;
  time: string;
  host: string;
  principal: string;
  product: string;
  event: string;
  eventId: string;
  detail: string;
};
export type PreviewSituation = {
  id: string;
  host: string;
  principal: string;
  severity: "high" | "medium";
  confidence: string;
  summary: string;
  headline: string;
  narrative: string;
  alternative: string;
  patterns: { id: string; label: string; score: number; count: number; role: string; observation: string }[];
  steps: { time: string; description: string; evidence: string[] }[];
  evidence: EvidenceRow[];
};

export const scenarios = [
  { id: "credentials", name: "Credential activity review", start: "2026-08-13T02:40", end: "2026-08-13T03:30" },
  { id: "dns", name: "DNS activity review", start: "2026-08-13T03:00", end: "2026-08-13T03:20" },
  { id: "quiet", name: "Quiet interval", start: "2026-08-13T01:00", end: "2026-08-13T01:15" },
] as const;

const credentialEvidence: EvidenceRow[] = [
  { id: "fixture:evt-001", time: "02:48:12", host: "ws-alpha-01", principal: "OPS\\review.user", product: "Windows Security", event: "Explicit credential logon", eventId: "4648", detail: "A process supplied explicit credentials. Destination: archive-01. The fixture does not establish authorization or intent." },
  { id: "fixture:evt-002", time: "02:48:16", host: "ws-alpha-01", principal: "OPS\\review.user", product: "Windows Security", event: "Authentication failure", eventId: "4625", detail: "Logon type 3. Account credentials were rejected in this synthetic record." },
  { id: "fixture:evt-003", time: "02:48:19", host: "ws-alpha-01", principal: "OPS\\review.user", product: "Windows Security", event: "Authentication failure", eventId: "4625", detail: "Second synthetic failure for the same principal. No source process is present." },
  { id: "fixture:evt-004", time: "02:48:24", host: "ws-alpha-01", principal: "OPS\\review.user", product: "Windows Security", event: "Authentication failure", eventId: "4625", detail: "Third synthetic failure. Time proximity alone does not establish causation." },
  { id: "fixture:evt-005", time: "02:49:03", host: "ws-alpha-01", principal: "OPS\\review.user", product: "Windows Security", event: "Successful logon", eventId: "4624", detail: "Synthetic successful network logon. Whether it belongs to the same process remains unknown." },
  { id: "fixture:evt-006", time: "02:49:09", host: "ws-alpha-01", principal: "OPS\\review.user", product: "Privileged session", event: "Session observation", eventId: "session", detail: "A read-only session observation was recorded. No recorded command or action is implied." },
];
const dnsEvidence: EvidenceRow[] = [
  { id: "fixture:evt-007", time: "03:08:10", host: "dns-review-02", principal: "Service account", product: "DNS", event: "DNS lookup", eventId: "query", detail: "Query for archive.example.test. Reserved example domain; not a real destination." },
  { id: "fixture:evt-008", time: "03:08:12", host: "dns-review-02", principal: "Service account", product: "DNS", event: "DNS lookup", eventId: "query", detail: "Repeated query for archive.example.test in the same synthetic interval." },
  { id: "fixture:evt-009", time: "03:08:18", host: "dns-review-02", principal: "Service account", product: "DNS", event: "DNS response", eventId: "response", detail: "Synthetic response. The fixture has no process-to-query attribution." },
];

export const situations: PreviewSituation[] = [
  {
    id: "fixture:situation-01", host: "ws-alpha-01", principal: "OPS\\review.user", severity: "high", confidence: "medium",
    summary: "Explicit credential use and repeated authentication failures appear on the same host in the replay window. A later successful logon is present; its relationship to the earlier activity remains unverified.",
    headline: "Credential activity followed by a successful network logon",
    narrative: "The records support a sequence of authentication activity, not a confirmed compromise. An authorized administrator retrying credentials remains a plausible alternative.",
    alternative: "Process attribution and an approved change record could distinguish routine administration from unauthorized activity.",
    patterns: [
      { id: "fixture.credentials", label: "Explicit credential activity", score: 30, count: 1, role: "anchor", observation: "One synthetic Event 4648 record names ws-alpha-01 and OPS\\review.user." },
      { id: "fixture.authentication", label: "Authentication burst", score: 25, count: 3, role: "context", observation: "Three synthetic Event 4625 records occur within eight seconds. The preview does not execute a detection rule." },
    ],
    steps: [
      { time: "02:48:12", description: "A process supplies explicit credentials for a network logon.", evidence: ["fixture:evt-001"] },
      { time: "02:48:16", description: "Three authentication failures follow within the same interval.", evidence: ["fixture:evt-002", "fixture:evt-003", "fixture:evt-004"] },
      { time: "02:49:03", description: "A successful network logon appears in the recorded window.", evidence: ["fixture:evt-005"] },
      { time: "02:49:09", description: "A privileged-session observation provides additional context.", evidence: ["fixture:evt-006"] },
    ],
    evidence: credentialEvidence,
  },
  {
    id: "fixture:situation-02", host: "dns-review-02", principal: "Service account", severity: "medium", confidence: "low",
    summary: "Repeated queries for one example domain appear in the selected interval. No process attribution or destination reputation evidence is present.",
    headline: "Repeated DNS activity with incomplete process context",
    narrative: "This synthetic sequence shows repeated lookups and a response. It does not establish malicious communication or data transfer.",
    alternative: "Client process details and a longer baseline could explain whether these queries are routine retries.",
    patterns: [{ id: "fixture.dns", label: "DNS lookup volume", score: 25, count: 2, role: "context", observation: "Two synthetic queries name archive.example.test. Query count is not a finding of compromise." }],
    steps: [
      { time: "03:08:10", description: "The resolver receives a query for archive.example.test.", evidence: ["fixture:evt-007"] },
      { time: "03:08:12", description: "A second query repeats the same name.", evidence: ["fixture:evt-008"] },
      { time: "03:08:18", description: "A response appears without client-process attribution.", evidence: ["fixture:evt-009"] },
    ],
    evidence: dnsEvidence,
  },
];

export const replayRules = [
  { id: "fixture.credentials", label: "Explicit credential activity", hit: true, count: 1 },
  { id: "fixture.authentication", label: "Authentication burst", hit: true, count: 3 },
  { id: "fixture.dns", label: "DNS lookup volume", hit: true, count: 2 },
  { id: "fixture.session", label: "Privileged session activity", hit: false, count: 0 },
  { id: "fixture.firewall", label: "Firewall context", hit: false, count: 0 },
];

export type PreviewSource = { id: string; name: string; provider: string; kind: "ADX" | "Graph" | "Search"; objects: { name: string; rows: number; columns: string[] }[] };
export const sources: PreviewSource[] = [
  { id: "fixture-events", name: "Security event replay", provider: "Azure Data Explorer", kind: "ADX", objects: [{ name: "EventsUnified", rows: 9, columns: ["resource_id", "source_time", "host", "principal", "product", "event_id"] }] },
  { id: "fixture-endpoint", name: "Endpoint telemetry replay", provider: "Azure Data Explorer", kind: "ADX", objects: [{ name: "EndpointEvents", rows: 3, columns: ["resource_id", "source_time", "host", "event_type"] }] },
  { id: "fixture-ontology", name: "Ontology graph", provider: "Cosmos DB for Gremlin", kind: "Graph", objects: [{ name: "Entities", rows: 4, columns: ["id", "label", "name"] }, { name: "Relationships", rows: 4, columns: ["source", "target", "relationship"] }] },
  { id: "fixture-mitre", name: "Open-source technique references", provider: "Azure AI Search", kind: "Search", objects: [{ name: "Technique references", rows: 2, columns: ["technique_id", "name", "source"] }] },
];

export const agentTools = [
  { id: "get_situation_evidence", label: "Situation evidence", sources: ["fixture-events", "fixture-endpoint"], purpose: "Read cited rows for a bounded situation." },
  { id: "query_event_timeline", label: "Event timeline", sources: ["fixture-events"], purpose: "Read events in a bounded UTC interval." },
  { id: "inspect_entity", label: "Entity relationships", sources: ["fixture-ontology"], purpose: "Read the selected entity and its immediate relationships." },
  { id: "search_mitre_attack", label: "MITRE ATT&CK references", sources: ["fixture-mitre"], purpose: "Read technique references, not telemetry facts." },
];