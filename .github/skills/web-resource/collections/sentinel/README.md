# Collection — sentinel

Microsoft Sentinel's feature surface, held as a reference for deciding what an analyst
application should and should not replicate. Reading material only: nothing here is telemetry,
and nothing here is used at runtime.

[targets.json](targets.json) is the canonical machine-readable list. It contains reference URLs,
not acquired pages or new liveness evidence. Set `LIBRARY_ROOT` to the canonical library or installed
`share/web-resource` guidance directory and choose
an external `OUTPUT_ROOT` before acquisition.

## Acquire

```bash
python3 -m webres.cli.fetch_page \
  --urls <(python3 -c 'import json,sys; print("\n".join(target["url"] for target in json.load(open(sys.argv[1]))))' "$LIBRARY_ROOT/collections/sentinel/targets.json") \
  --subject sentinel \
  --out "$OUTPUT_ROOT/sentinel" --catalogue "$OUTPUT_ROOT/manifest.json"
```

## Verify

```bash
python3 -m webres.cli.catalogue \
  --catalogue "$OUTPUT_ROOT/manifest.json" --verify
```

## Known limits

Microsoft Learn pages are versioned and change without notice; the catalogue records retrieval
time and SHA-256 so drift is detectable. `--verify` reports changed artefacts rather than
silently re-fetching.

The source project's earlier captures were retired. Only the reusable target list was migrated;
no publisher content is bundled or claimed newly verified.
