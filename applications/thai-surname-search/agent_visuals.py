from __future__ import annotations

import json
import math
from dataclasses import dataclass
from html import escape

from foundry_agent import COMPARISON_LABELS, COMPARISON_SKUS, AgentConnectionProbe, AgentTimings


PRICING_CHECKED = "2026-10-15"
PRICING_SOURCE = "https://prices.azure.com/api/retail/prices"
PEERING_USD_PER_GB = {"sea": 0.09, "westus3": 0.035}
PRIVATE_LINK_USD_PER_GB = 0.01
PRIVATE_ENDPOINT_USD_PER_HOUR = 0.01

THEME = """
<script>
  (() => {
    const param = new URLSearchParams(window.location.search).get("scoutTheme");
    const theme =
      param || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  })();
</script>
<style>
:root {
  color-scheme: light;
  --cp-bg: #f7f4ef;
  --cp-bg-elevated: #fcfbf8;
  --cp-surface: #ffffff;
  --cp-surface-soft: #f5f5f5;
  --cp-border: #dedede;
  --cp-border-strong: #919191;
  --cp-text: #242424;
  --cp-text-muted: #5c5c5c;
  --cp-text-soft: #6f6f6f;
  --cp-accent: #b11f4b;
  --cp-accent-hover: #9a1a41;
  --cp-accent-soft: rgba(177, 31, 75, 0.08);
  --cp-accent-fg: #ffffff;
  --cp-success: #16a34a;
  --cp-danger: #dc2626;
  --cp-warning: #f59e0b;
  --cp-link: #0078d4;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
  --cp-overlay: rgba(255, 255, 255, 0.8);
  --cp-panel: rgba(255, 255, 255, 0.86);
  --cp-panel-strong: rgba(255, 255, 255, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.55);
  --cp-highlight: rgba(177, 31, 75, 0.12);
}
html[data-theme="dark"] {
  color-scheme: dark;
  --cp-bg: #3d3b3a;
  --cp-bg-elevated: #343231;
  --cp-surface: #292929;
  --cp-surface-soft: #2e2e2e;
  --cp-border: #474747;
  --cp-border-strong: #5f5f5f;
  --cp-text: #dedede;
  --cp-text-muted: #919191;
  --cp-text-soft: #b0b0b0;
  --cp-accent: #fd8ea1;
  --cp-accent-hover: #fb7b91;
  --cp-accent-soft: rgba(253, 142, 161, 0.14);
  --cp-accent-fg: #1a1a1a;
  --cp-success: #4ade80;
  --cp-danger: #f87171;
  --cp-warning: #fbbf24;
  --cp-link: #4da6ff;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
  --cp-overlay: rgba(41, 41, 41, 0.88);
  --cp-panel: rgba(41, 41, 41, 0.72);
  --cp-panel-strong: rgba(41, 41, 41, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.04);
  --cp-highlight: rgba(253, 142, 161, 0.12);
}
body { margin: 0; padding: 12px; background: var(--cp-bg); color: var(--cp-text);
  font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif; }
svg { width: 100%; min-width: 900px; height: auto; max-height: 535px; }
text { fill: var(--cp-text); font-size: 14px; }
.muted { fill: var(--cp-text-muted); font-size: 12px; }
.node { fill: var(--cp-surface); stroke: var(--cp-border-strong); stroke-width: 1.5; }
.region { fill: var(--cp-surface-soft); stroke: var(--cp-border); }
.edge { fill: none; stroke: var(--cp-accent); stroke-width: 2; }
.internal { stroke-dasharray: 5 5; stroke: var(--cp-border-strong); }
.bar { display: flex; height: 28px; border: 1px solid var(--cp-border); border-radius: 10px; overflow: hidden; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; margin-top: 12px; }
.legend span { border-left: 8px solid var(--cp-border-strong); padding-left: 8px; }
p { margin: 8px 0; font-size: 13px; color: var(--cp-text-muted); }
</style>
"""


def estimate_transfer(region: str, request_bytes: float, response_bytes: float, calls: int = 1) -> dict:
    if region not in PEERING_USD_PER_GB:
        raise ValueError("Transfer estimate requires SEA or West US 3.")
    if (
        not all(math.isfinite(value) and value >= 0 for value in (request_bytes, response_bytes))
        or not isinstance(calls, int) or isinstance(calls, bool) or calls < 0
    ):
        raise ValueError("Payload sizes and call counts must be finite and nonnegative.")
    request_gb = request_bytes * calls / 1_000_000_000
    response_gb = response_bytes * calls / 1_000_000_000
    if max(request_gb, response_gb) > 1_000_000:
        raise ValueError("This first-tier estimate supports at most 1 PB per direction per month.")
    if region == "westus3":
        sea_peering = (request_gb + response_gb) * PEERING_USD_PER_GB["sea"]
        west_peering = (request_gb + response_gb) * PEERING_USD_PER_GB["westus3"]
    else:
        sea_peering = west_peering = 0.0
    private_link = (request_gb + response_gb) * PRIVATE_LINK_USD_PER_GB
    return {
        "request_gb": request_gb, "response_gb": response_gb,
        "sea_peering_usd": sea_peering, "westus3_peering_usd": west_peering,
        "private_link_usd": private_link,
        "total_usd": sea_peering + west_peering + private_link,
    }


def timing_stages(timings: AgentTimings, setup_ms: float, total_ms: float) -> list[tuple[str, float]]:
    values = [setup_ms, total_ms, timings.response_ms]
    if timings.first_token_ms is not None:
        values.append(timings.first_token_ms)
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise ValueError("Timing measurements must be finite and nonnegative.")
    local_ms = total_ms - setup_ms - timings.response_ms
    if local_ms < -0.01:
        raise ValueError("The measured API and setup intervals exceed the app total.")
    stages = [("Client/conversation setup", setup_ms)]
    if timings.first_token_ms is None:
        stages.append(("Responses API stream (first text unavailable)", timings.response_ms))
    else:
        if timings.first_token_ms > timings.response_ms + 0.01:
            raise ValueError("First-text time exceeds the complete Responses API interval.")
        first_ms = min(timings.first_token_ms, timings.response_ms)
        stages.extend([
            ("API wait until first text", first_ms),
            ("API after first text", timings.response_ms - first_ms),
        ])
    stages.append(("Local response processing", max(0.0, local_ms)))
    return stages


def timeline_html(timings: AgentTimings, setup_ms: float, total_ms: float) -> str:
    stages = timing_stages(timings, setup_ms, total_ms)
    colors = ["--cp-border-strong", "--cp-accent", "--cp-highlight", "--cp-border"]
    bars, legend = [], []
    for (label, elapsed), color in zip(stages, colors):
        width = elapsed / total_ms * 100 if total_ms else 0
        caption = f"{label}: {elapsed / 1000:.3f} s"
        bars.append(
            f'<div style="width:{width:.8f}%;background:var({color})" title="{escape(caption)}"></div>'
        )
        legend.append(f'<span style="border-color:var({color})">{escape(caption)}</span>')
    return (
        '<!doctype html><html><head>' + THEME + '</head><body>'
        f'<strong>Additive app timeline = {total_ms / 1000:.3f} s</strong>'
        f'<div class="bar">{"".join(bars)}</div><div class="legend">{"".join(legend)}</div>'
        '<p>These segments add to the app total. API first-text time excludes setup; app first-text time '
        'includes setup. The coarse Foundry server reference overlaps these stages and is NOT added.</p>'
        '</body></html>'
    )


@dataclass(frozen=True)
class FlowNode:
    key: str
    x: int
    y: int
    width: int
    height: int
    lines: tuple[str, ...]


def flow_nodes(mode: str, rows: list[dict], blocked_reason: str = "") -> list[FlowNode]:
    if mode not in COMPARISON_SKUS:
        raise ValueError("Unknown matched regional comparison mode.")
    sku = COMPARISON_SKUS[mode]
    measured = {row["agent_region"]: row for row in rows}
    nodes = [
        FlowNode("browser", 20, 10, 220, 80, ("Browser", "Outside app timers")),
        FlowNode("gateway", 320, 10, 250, 80, ("Application Gateway + WAF", "SEA hub VNet")),
        FlowNode("app", 670, 10, 320, 80, ("Container App in SEA", "Measurement starts here")),
    ]
    for region, label, x in (("sea", "Southeast Asia", 40), ("westus3", "West US 3", 720)):
        row = measured.get(label)
        unavailable = bool(blocked_reason) and mode == "standard" and region == "sea"
        if row:
            api = f'API {row["responses_stream_ms"] / 1000:.2f} s'
            first = row["responses_first_token_ms"]
            api += " | first text " + ("unavailable" if first is None else f"{first / 1000:.2f} s")
            total = f'Full app {row["app_response_ms"] / 1000:.2f} s'
        else:
            api, total = "API time: not measured", "Full app time: not measured"
        nodes.append(FlowNode(
            f"{region}_agent", x, 235, 560, 112,
            (f"{label} private endpoint / Foundry agent",
             f"{sku}" + (" - UNAVAILABLE" if unavailable else " - COMPARISON BLOCKED" if blocked_reason else ""),
             api, total),
        ))
        model_lines = (
            ("GlobalStandard model", "Global inference routing", "Serving region not exposed")
            if mode == "global" else
            ("Standard model deployment", "Azure geography processing policy",
             "Unavailable in SEA" if unavailable else "West US 3 resource")
        )
        nodes.extend([
            FlowNode(f"{region}_model", x, 430, 320, 80, model_lines),
            FlowNode(f"{region}_tools", x + 360, 430, 200, 80,
                     ("Optional file search", "AI Search / Blob / Cosmos", "Not separately timed")),
        ])
    return nodes


FLOW_EDGES = [
    ("browser", "gateway", False), ("gateway", "app", False),
    ("app", "sea_agent", False), ("app", "westus3_agent", False),
    ("sea_agent", "sea_model", True), ("sea_agent", "sea_tools", True),
    ("westus3_agent", "westus3_model", True), ("westus3_agent", "westus3_tools", True),
]


def flow_html(
    mode: str, rows: list[dict], probes: dict[str, AgentConnectionProbe], blocked_reason: str = "",
) -> str:
    nodes = flow_nodes(mode, rows, blocked_reason)
    lookup = {node.key: node for node in nodes}
    parts = [
        '<svg viewBox="0 0 1320 550" role="img" aria-label="Regional agent data flow and measured times">'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="var(--cp-accent)"/></marker></defs>'
    ]
    for x, label in ((20, "SEA workload VNet 10.10.0.0/16"), (700, "West US 3 agent VNet 10.80.0.0/16")):
        parts.append(
            f'<rect class="region" x="{x}" y="180" width="600" height="200" rx="16"/>'
            f'<text x="{x + 20}" y="204">{escape(label)}</text>'
        )
    for source, target, internal in FLOW_EDGES:
        a, b = lookup[source], lookup[target]
        if a.y == b.y:
            path = f"M {a.x + a.width} {a.y + a.height / 2} H {b.x}"
        else:
            sx, sy, tx = a.x + a.width / 2, a.y + a.height, b.x + b.width / 2
            bend = sy + (30 if target == "sea_agent" else 55) if source == "app" else sy + 40
            path = f"M {sx} {sy} V {bend} H {tx} V {b.y}"
        parts.append(
            f'<path class="edge{" internal" if internal else ""}" d="{path}" '
            'marker-start="url(#arrow)" marker-end="url(#arrow)"/>'
        )
    for node in nodes:
        parts.append(
            f'<rect class="node" x="{node.x}" y="{node.y}" width="{node.width}" height="{node.height}" rx="10"/>'
        )
        for index, line in enumerate(node.lines):
            parts.append(
                f'<text x="{node.x + node.width / 2}" y="{node.y + 24 + index * 22}" '
                f'text-anchor="middle" class="{"muted" if index else ""}">{escape(line)}</text>'
            )
    for region, x, route in (
        ("sea", 320, "Same VNet / Private Link; no global peering"),
        ("westus3", 1000, "Direct global VNet peering / Private Link"),
    ):
        probe = probes.get(region)
        tcp = f"TCP connect {probe.median_tcp_ms:.1f} ms" if probe else "TCP connect not measured"
        parts.append(
            f'<text x="{x + 18}" y="150" class="muted">{escape(route)}</text>'
            f'<text x="{x + 18}" y="170" class="muted">{escape(tcp)}</text>'
        )
    parts.extend([
        '<text x="250" y="36" class="muted">not timed</text>',
        '<text x="580" y="36" class="muted">not timed</text>', '</svg>',
    ])
    return (
        '<!doctype html><html><head>' + THEME + '</head><body>'
        f'<strong>{escape(COMPARISON_LABELS[mode])}</strong>' + "".join(parts)
        + '<p>Arrows are bidirectional request/response paths, not separate timed stages. Solid lines show '
        'the application path; dashed lines show service internals that are not separately instrumented. '
        'TCP connect is a separate probe, not model latency. Browser, Gateway/WAF and rendering are not timed. '
        'No hub transit is used between the SEA app and West US 3 endpoint. '
        'Backend boxes are logical services outside the VNet boundary, not known physical serving locations.</p>'
        + (f'<p>{escape(blocked_reason)}</p>' if blocked_reason else '')
        + '</body></html>'
    )


def flow_excalidraw(mode: str, rows: list[dict], blocked_reason: str = "") -> str:
    nodes = flow_nodes(mode, rows, blocked_reason)
    elements = []
    for region, x, label, route in (
        ("sea", 20, "SEA workload VNet 10.10.0.0/16", "Same VNet / Private Link"),
        ("westus3", 700, "West US 3 agent VNet 10.80.0.0/16", "Direct global VNet peering / Private Link; no hub transit"),
    ):
        elements.extend([
            {
                "id": f"{region}_vnet", "type": "rectangle", "x": x, "y": 180,
                "width": 600, "height": 200, "strokeColor": "#919191",
                "backgroundColor": "transparent", "strokeWidth": 1, "fillStyle": "solid",
            },
            {
                "id": f"{region}_route", "type": "text", "x": x + 20, "y": 185,
                "width": 560, "height": 60, "fontSize": 11, "fontFamily": 2,
                "strokeColor": "#000000", "text": f"{label}\n{route}",
            },
        ])
    for node in nodes:
        text_height = len(node.lines) * 11 * 2.5
        elements.extend([
            {
                "id": node.key, "type": "rectangle", "x": node.x, "y": node.y,
                "width": node.width, "height": max(node.height, text_height + 20),
                "strokeColor": "#919191", "backgroundColor": "#ffffff",
                "fillStyle": "solid", "strokeWidth": 1, "roundness": {"type": 3},
                "boundElements": [{"type": "text", "id": f"{node.key}_text"}],
            },
            {
                "id": f"{node.key}_text", "type": "text", "x": node.x + 12, "y": node.y + 10,
                "width": node.width - 24, "height": text_height, "text": "\n".join(node.lines),
                "fontSize": 11, "fontFamily": 2, "strokeColor": "#000000",
                "containerId": node.key, "textAlign": "center", "verticalAlign": "middle",
            },
        ])
    lookup = {node.key: node for node in nodes}
    for source, target, internal in FLOW_EDGES:
        a, b = lookup[source], lookup[target]
        height = max(a.height, len(a.lines) * 11 * 2.5 + 20)
        sx, sy = (a.x + a.width, a.y + height / 2) if a.y == b.y else (a.x + a.width / 2, a.y + height)
        tx, ty = (b.x, b.y + b.height / 2) if a.y == b.y else (b.x + b.width / 2, b.y)
        elements.append({
            "id": f"{source}_to_{target}", "type": "arrow", "x": sx, "y": sy,
            "width": abs(tx - sx), "height": abs(ty - sy), "points": [[0, 0], [tx - sx, ty - sy]],
            "strokeColor": "#b11f4b", "strokeWidth": 2, "strokeStyle": "dashed" if internal else "solid",
            "startArrowhead": "arrow", "endArrowhead": "arrow",
            "startBinding": {"elementId": source, "focus": 0, "gap": 1},
            "endBinding": {"elementId": target, "focus": 0, "gap": 1},
        })
    return json.dumps({
        "type": "excalidraw", "version": 2, "source": "copilot",
        "elements": elements, "appState": {"viewBackgroundColor": "#f7f4ef"},
    })
