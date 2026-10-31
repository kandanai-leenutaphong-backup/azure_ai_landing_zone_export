# Collection: attack-telemetry-datasets

Open telemetry corpora that contain attack activity with usable ground truth, for large-scale
historical replay. This list originated as a supplement to the source project's knowledge base;
it is not an exhaustive dataset inventory. Reverify labels, terms and availability before use.

## Why these sources

Selection was driven by one question: **can a machine fetch it, and does the fetch land on
telemetry with a defensible attack label?** Three qualities were required, and sources
failing any of them are recorded here anyway so the failure does not get rediscovered.

| Quality | Why it decides inclusion |
| --- | --- |
| Unattended fetchability | A form, a licence signature, or a JavaScript file browser turns a corpus into a manual errand. Worth knowing *before* planning a pipeline. |
| Attack ground truth | Timestamped attack windows, per-line labels, or a red-team report. Without one, "anomaly" and "attack" quietly become the same word — the failure mode in the log-parsing corpora listed below. |
| Scale | Multi-gigabyte, multi-host, multi-day. Small clean corpora are useful for correctness, not for load. |

Two sources are included **despite** failing a quality, because the failure is the finding:

- **Loghub** carries anomaly labels for *failures*, not intrusions. Excellent volume, wrong
  semantics. Listed so it is not mistaken for an attack corpus.
- **CIC** datasets sit behind a name/email/organisation form at `cicresearch.ca`, which the
  dataset landing pages do not mention. Listed so the gate is discovered once.

## One list, two tools

[targets.json](targets.json) is canonical. Each entry carries a `kind`: `page` for landing and metadata
pages, read by `fetch-page`; `endpoint` for direct download and index URLs, read by
`probe-url`, which reads headers only.

Never aim `fetch-page` at an `endpoint`. Several are multi-gigabyte.

## Refresh

Set `LIBRARY_ROOT` to the canonical library or installed `share/web-resource` guidance directory
and choose an external `OUTPUT_ROOT`. The Bash examples filter the structured list. Network acquisition is separate
from the package's offline acceptance.

```bash
COLLECTION="$LIBRARY_ROOT/collections/attack-telemetry-datasets/targets.json"
SELECT='import json,sys; print("\n".join(target["url"] for target in json.load(open(sys.argv[1])) if target["kind"] == sys.argv[2]))'

python3 -m webres.cli.fetch_page \
  --urls <(python3 -c "$SELECT" "$COLLECTION" page) --subject attack-telemetry-datasets \
  --out "$OUTPUT_ROOT/pages" --catalogue "$OUTPUT_ROOT/manifest.json" --text

python3 -m webres.cli.probe_url \
  --urls <(python3 -c "$SELECT" "$COLLECTION" endpoint) --subject attack-telemetry-datasets \
  --name direct-download-endpoints \
  --out "$OUTPUT_ROOT/probes" --catalogue "$OUTPUT_ROOT/manifest.json"
```

## Known limits

- Google Drive folder URLs answer `200` with a JavaScript shell. The probe cannot tell a
  populated folder from an empty one, and neither can `fetch-page`.
- `share.netresec.com` disallows automated access in robots.txt. The MACCDC and container
  honeypot captures behind it are browser-only by the publisher's choice.
- Historical source observation: Zenodo declared `Crawl-delay: 10`. The transport now uses the
  larger of its two-second floor and the parsed publisher crawl-delay/request-rate interval.
