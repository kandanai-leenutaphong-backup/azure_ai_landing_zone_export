# Web Resource

Public page fetch, URL probe, embedded-image acquisition, browser screenshot and local provenance
verification. Canonical owner: `.github/skills/web-resource`. Distribution `harness-web-resource`
exports `webres` and five installed command adapters. Guides, tests and target collections ship
under `share/web-resource` in the Python environment; installation acquires no web material.

Set `LIBRARY_ROOT` to this directory and `RUNTIME_ROOT` to an isolated environment. Core operations
need Python 3.11+ and no third-party runtime dependency:

```bash
uv venv "$RUNTIME_ROOT"
uv pip install --python "$RUNTIME_ROOT/bin/python" "$LIBRARY_ROOT"
"$RUNTIME_ROOT/bin/python" "$LIBRARY_ROOT/tests/selftest.py"
"$RUNTIME_ROOT/bin/python" -m unittest discover -s "$LIBRARY_ROOT/tests" -p 'test_*.py' -v
"$RUNTIME_ROOT/bin/python" "$LIBRARY_ROOT/examples/catalogue_roundtrip.py"
```

Public APIs: `webres.fetch`, `open_public`, `validate_url`, `Catalogue`, `Provenance`,
`AcquisitionError`, `RobotsDisallowed`; screenshot adapter `webres.cli.capture_screenshot.capture`.
The [offline example](examples/catalogue_roundtrip.py) records and reads back a synthetic artefact.

Only after explicit acquisition authorization:

```bash
"$RUNTIME_ROOT/bin/web-resource-fetch-page" --url https://example.com \
  --out "$OUTPUT_ROOT" --text
"$RUNTIME_ROOT/bin/web-resource-catalogue" --catalogue "$OUTPUT_ROOT/manifest.json" --verify
```

The other entry points are `web-resource-probe-url`, `web-resource-extract-images` and
`web-resource-capture-screenshot`; each supports `--help` without network access.
`OUTPUT_ROOT` is an explicit operator-selected acquisition directory, outside the installed package.
Default provenance is saved beside output; plain-text derivatives are separately catalogued.
Verification reads holdings and reports missing/changed/orphan files without rewriting the manifest.
Adoption/pruning are explicit mutations. Material remains subject to its publisher's rights.

Screenshots use the declared optional Python Playwright extra, not a guessed Node package:

```bash
uv pip install --python "$RUNTIME_ROOT/bin/python" "$LIBRARY_ROOT[browser,test]"
PLAYWRIGHT_BROWSERS_PATH="$BROWSER_ROOT" "$RUNTIME_ROOT/bin/python" -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$BROWSER_ROOT" "$RUNTIME_ROOT/bin/python" -B \
  "$LIBRARY_ROOT/tests/browser_smoke.py" --out "$EVIDENCE_ROOT"
```

Choose external runtime/browser/evidence directories. The `test` extra adds Pillow for pixel checks,
not a production dependency. A live screenshot uses the capture script and the same interpreter;
`--browser-executable` optionally names an existing Chromium binary. No script installs a browser
implicitly. Linux browser execution passed; Windows/macOS remain unverified.

No login/cookie session or access-control bypass is supported. Robots absence (404/410) permits;
unreachable/denied robots refuses. A `403` is not retried through another access path. Browser
subresources use guarded public GET/HEAD and may be blocked; capture provenance records the count.
This is a reference-acquisition tool, not a faithful authenticated-app browser or an OS sandbox.

Contracts: [CONTRACT.md](CONTRACT.md). Limits: [GOTCHAS.md](GOTCHAS.md).
Origin: [PROVENANCE.md](PROVENANCE.md). Collection links are starting points, not newly verified holdings.
Acquisition procedure: [GUIDE.md](GUIDE.md). Old skill script paths are retired; install the package
instead of extending `sys.path`. No public website was fetched to validate this migration.

## Migration Verification

2026-09-16: installed Python 3.11 wheel passed 64 selftest checks, 12 transport/provenance tests,
the offline catalogue example and all five CLI help entries outside the checkout. Real sockets
and live DNS were blocked during in-process tests. Optional browser capture and collection
liveness were not rerun. URL/DNS/redirect/robots/rate/provenance rules remain with `webres`.

Framework scope: F2 packaging/types and F3 public-only input/configuration boundaries are retained;
F4 uses `AcquisitionError`, `RobotsDisallowed` and explicit provenance; F5 is a synchronous operator
exception with bounded transport/browser cleanup; F6 retains deadline, byte and host-rate bounds,
not a shared run budget; F7 catalogue state remains operator-owned; F8 adapters call one guarded
implementation. The [catalogue](../../../libraries/capabilities.json) owns F1 discovery metadata;
[conformance](../harness-guide/framework/CONFORMANCE.md) separates native, artifact and live evidence.