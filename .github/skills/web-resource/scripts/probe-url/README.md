# probe-url

**Function:** verify remote URLs resolve, and record status and size, without downloading
their bodies.

## When to use

Checking whether a download link, dataset mirror, or API endpoint is still live — before
committing to a retrieval, or when reporting on sources you deliberately are *not*
fetching. For material whose text you actually want, use
[fetch-page](../fetch-page/README.md); for appearance, use
[capture-screenshot](../capture-screenshot/README.md).

This is the right tool for multi-gigabyte artefacts. It answers "does this still exist,
how big is it, and does it redirect to a login" at the cost of one request.

## Usage

```bash
python3 -m webres.cli.probe_url --url https://example.com/dataset.tar.gz \
  --subject attack-telemetry-datasets \
  --out research/probes \
  --catalogue research/manifest.json
```

Batch from a file, one URL per line, `#` for comments:

```bash
python3 -m webres.cli.probe_url --urls targets.txt --subject attack-telemetry-datasets --out research/probes
```

## Arguments

| Flag | Meaning |
| --- | --- |
| `--url` | A URL to probe. Repeatable. |
| `--urls` | File of URLs, one per line. |
| `--out` | Directory for the results artefact. Created if absent. |
| `--name` | Artefact stem. Defaults to the slugified subject. |
| `--catalogue` | Manifest JSON to record provenance in. |
| `--subject` | Subject tag, used to group the catalogue. |
| `--ignore-robots` | Skip the robots.txt check. Only with permission. |
| `--timeout` | Seconds per request. Default 30. |

## Output

One `<stem>-probe.json` holding a record per URL: outcome, HTTP status, final URL after
redirects, content type, content length, last-modified, and which method answered. Exit
code is non-zero if any URL failed to resolve.

Outcomes are `ok`, `http-error`, `refused` (URL or robots policy rejected the request),
and `unreachable` (DNS, TLS, or timeout).

## Behaviour worth knowing

- **HEAD first, ranged GET as fallback.** Servers explicitly rejecting the method with 405/501
  are retried with `Range: bytes=0-0`, so at most one byte is read. A 401/403 is not retried.
- **robots.txt, rate limiting, and URL guards are the same as every other script**,
  because every adapter uses the installed `webres` transport.
- **A failure is a result, not an abort.** Every URL is probed and recorded.

## Known limits

- `Content-Length` is often absent on chunked or dynamically generated responses, and is
  the *compressed* size when the server negotiates encoding. Treat it as a lower bound on
  the real dataset, never as an authoritative size.
- A `200` proves the URL answers, not that the body is the dataset you want. Portals
  routinely return `200` on a login or consent page. Check `final_url` before believing a
  link is fetchable unattended.
- Cloud storage links carrying signatures expire; a `200` today says nothing about
  tomorrow.
