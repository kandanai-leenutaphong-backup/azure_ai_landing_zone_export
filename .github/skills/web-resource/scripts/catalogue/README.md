# catalogue

**Function:** maintain, verify, and index an acquisition manifest.

## When to use

After any acquisition run, and before trusting a collection you did not just create.
A manifest that nobody verifies is a list of claims, not a record.

## Usage

Verify holdings against disk:

```bash
python3 -m webres.cli.catalogue --catalogue app/data/reference/manifest.json --verify
```

Back-fill entries for files acquired before the catalogue existed:

```bash
python3 -m webres.cli.catalogue --catalogue app/data/reference/manifest.json \
  --adopt app/data/reference/screenshots \
  --subject soc-dashboards --function screenshot
```

Write a human-readable index:

```bash
python3 -m webres.cli.catalogue --catalogue app/data/reference/manifest.json \
  --index app/data/reference/INDEX.md
```

## Arguments

| Flag | Meaning |
| --- | --- |
| `--catalogue` | Manifest JSON. Required. |
| `--verify` | Check every entry against disk and hash; exit 1 on any discrepancy. |
| `--adopt DIR` | Create entries for uncatalogued files under `DIR`. |
| `--subject`, `--function` | Tags applied to adopted files. |
| `--prune` | Drop entries whose artefact no longer exists. |
| `--index PATH` | Write a grouped Markdown index. |

## What `--verify` reports

| Line | Meaning |
| --- | --- |
| `missing` | Catalogued, but the file is gone. |
| `changed` | On disk, but the hash no longer matches — the artefact was modified. |
| `uncatalogued` | On disk, but nothing catalogues it. |
| `no source url` | Entry exists but provenance was never recorded. |

Any of the first three sets the exit code to 1.

## Behaviour worth knowing

- **`--adopt` does not invent provenance.** Adopted entries carry an empty `source_url`
  and a note saying the source was not recorded at acquisition time. An unknown origin is
  recorded as unknown.
- **Re-recording replaces rather than appends,** so the manifest states current holdings
  rather than accumulating history.
- **Entries sort by subject then artefact,** so the file diffs cleanly.

## Manifest shape

```json
{
  "generated": "2026-08-31T03:00:00Z",
  "count": 11,
  "usage": "Third-party material held for internal reference only. Do not redistribute.",
  "entries": [
    {
      "source_url": "https://learn.microsoft.com/...",
      "retrieved_at": "2026-08-31T03:00:00Z",
      "status": 200,
      "content_type": "image/png",
      "sha256": "…",
      "bytes": 481203,
      "title": "Investigate incidents",
      "publisher": "learn.microsoft.com",
      "subject": "soc-dashboards",
      "function": "screenshot",
      "artefact": "screenshots/sentinel-investigation-graph.png",
      "usage": "internal reference only; third-party content remains the property of its publisher",
      "notes": ""
    }
  ]
}
```
