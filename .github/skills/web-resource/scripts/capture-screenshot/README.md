# capture-screenshot

**Function:** capture rendered pages as PNG with provenance.

## When to use

When *appearance* is the material: interface layouts, colour and density decisions,
component arrangement, information hierarchy. For text, use
[fetch-page](../fetch-page/README.md), which is faster and needs no browser.

## Usage

Single capture:

```bash
python3 -m webres.cli.capture_screenshot \
  --url https://learn.microsoft.com/en-us/azure/sentinel/investigate-cases \
  --name sentinel-investigation-graph \
  --subject soc-dashboards \
  --out app/data/reference/screenshots \
  --catalogue app/data/reference/manifest.json
```

Batch from a target file, which is the reusable form:

```bash
python3 -m webres.cli.capture_screenshot --targets targets.json \
  --out app/data/reference/screenshots \
  --catalogue app/data/reference/manifest.json
```

```json
[
  {
    "url": "https://example.com/docs/incidents",
    "name": "example-incident-queue",
    "subject": "soc-dashboards",
    "wait": "main img",
    "hide": [".promo-banner"],
    "notes": "Analyst queue with severity grouping"
  }
]
```

## Arguments

| Flag | Meaning |
| --- | --- |
| `--url` / `--targets` | One URL, or a JSON list of targets. |
| `--name` | Artefact name for a single URL. Slugified. |
| `--out` | Directory for PNGs. |
| `--catalogue` | Manifest JSON to record provenance in. |
| `--subject` | Subject tag for grouping. |
| `--width`, `--height` | Viewport. Defaults 1600×1000 at 2× scale. |
| `--viewport-only` | Capture the viewport rather than the full page. |
| `--ignore-robots` | Skip the robots.txt check. Only with permission. |
| `--browser-executable` | Explicit existing Chromium binary; otherwise use the selected Python environment's Playwright browser. |

Per-target keys: `wait` (selector to await), `hide` (extra selectors to suppress),
`width`, `height`, `fullPage`, `notes`.

## Output

`<name>.png` at 2× device scale, plus a catalogue entry with source URL, page title,
SHA-256, and byte count.

## Behaviour worth knowing

- **Installs nothing.** Playwright and Chromium must already exist; if they do not, the
  script says so and exits 3 rather than reaching for a package manager.
- **Consent and chat overlays are suppressed** by default — OneTrust, cookie banners,
  Intercom, Drift. Add page-specific noise through the target's `hide` list.
- **Waits for DOM content**, the optional `wait` selector, and the load event. Screenshots disable
  animations for a stable reference frame; continuous telemetry does not require network-idle.
- **All browser HTTP requests use the guarded Python transport.** Blocked-resource counts are
  recorded; cookies, service workers, WebSockets and write requests are not enabled.
- **A failed capture deletes its partial file** so a broken PNG is never catalogued.

## Known limits

Documentation screenshots are images of a product, not the product. They show layout and
density but not interaction, latency, or empty states. Treat them as evidence of intent,
not of behaviour.

Marketing pages flatter the product. Prefer documentation and reference pages, where
screenshots tend to show realistic data volumes.
