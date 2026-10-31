# fetch-page

**Function:** retrieve HTML or JSON documents to disk with provenance.

## When to use

Reference documentation, product pages, changelogs, specifications — anything whose
*text* is the material. For anything whose *appearance* is the material, use
[capture-screenshot](../capture-screenshot/README.md) instead.

## Usage

```bash
python3 -m webres.cli.fetch_page --url https://example.com/docs \
  --subject soc-dashboards \
  --out app/data/reference/pages \
  --catalogue app/data/reference/manifest.json \
  --text
```

Batch from a file, one URL per line, `#` for comments:

```bash
python3 -m webres.cli.fetch_page --urls sources.txt --subject observability --out refs/ --catalogue refs/manifest.json
```

## Arguments

| Flag | Meaning |
| --- | --- |
| `--url` | A URL to fetch. Repeatable. |
| `--urls` | File of URLs, one per line. |
| `--out` | Directory for artefacts. Created if absent. |
| `--catalogue` | Manifest JSON to record provenance in. |
| `--subject` | Subject tag, used to group the catalogue. |
| `--text` | Also write a tag-stripped `.txt` rendering. |
| `--ignore-robots` | Skip the robots.txt check. Only with permission. |

## Output

`<slug>-<url-hash>.html` per URL, optionally a `.txt` derivative, with separate catalogue entries carrying
source URL, retrieval time, HTTP status, content type, SHA-256, and byte count.

## Behaviour worth knowing

- **robots.txt is consulted first.** A disallow is a skip, not a warning, and the run
  exits non-zero.
- **Two seconds minimum between requests to one host.** Batch runs are slow on purpose.
- **The user agent identifies the toolkit** rather than impersonating a browser.
- **Failures do not stop the batch.** Every URL is attempted; the exit code reports whether
  any failed.

## Known limits

Some publishers return `403` to any non-browser client regardless of robots.txt.
Microsoft Learn and Elastic serve automation fine; Splunk documentation does not.
When a fetch is refused, cite its URL. Do not change access methods to work around the refusal.

Pages rendered entirely by client-side JavaScript arrive as an empty shell here, because
this script does not execute scripts. Use capture-screenshot for those.
