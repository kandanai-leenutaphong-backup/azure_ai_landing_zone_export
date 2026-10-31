# Collection: soc-dashboards

Interface references for security operations and observability products — how mainstream
platforms present detection, triage, and investigation.

## Why these sources

Documentation pages, not marketing pages. Product sites show idealised dashboards with
flattering data; reference documentation shows realistic volumes, real empty states, and
the controls an analyst actually operates.

Three subjects are mixed in this collection deliberately, because the interesting
comparison is between them:

| Subject tag | Products | What it shows |
| --- | --- | --- |
| `soc-dashboards` | Sentinel, Defender XDR, Elastic Security, Chronicle, Datadog Cloud SIEM | Conventional alert-centric triage |
| `agentic-soc` | Security Copilot, Datadog Bits AI | Conversational investigation over telemetry |
| `observability` | Grafana Explore | Ad-hoc exploration rather than fixed dashboards |

## Refresh

Set `LIBRARY_ROOT` to the canonical library or installed `share/web-resource` guidance directory,
`RUNTIME_ROOT` to its optional browser
environment, and `OUTPUT_ROOT` to an operator-selected holdings directory. These commands contact
the listed publishers; source observations below are not current liveness evidence.

```bash
"$RUNTIME_ROOT/bin/python" -m webres.cli.capture_screenshot \
  --targets "$LIBRARY_ROOT/collections/soc-dashboards/targets.json" \
  --out "$OUTPUT_ROOT/screenshots" \
  --catalogue "$OUTPUT_ROOT/manifest.json"

python3 -m webres.cli.catalogue \
  --catalogue "$OUTPUT_ROOT/manifest.json" --verify \
  --index "$OUTPUT_ROOT/INDEX.md"
```

## Known refusals

**Historical source observation:** Splunk documentation returned `403` to automated clients.
Splunk Enterprise Security is a significant reference for analyst queue design, so cite it
by URL and describe it from the public documentation text rather than working around the
refusal.

## What these references are good for

Layout, density, colour discipline, information hierarchy, and the vocabulary these
products have taught analysts to expect.

## What they are not good for

Interaction, latency, error states, and behaviour when data is missing. A documentation
screenshot is an image of a product at its best moment. It is evidence of intent, not of
behaviour. Do not assume the alert-rich examples resemble a consuming project's actual corpus.
