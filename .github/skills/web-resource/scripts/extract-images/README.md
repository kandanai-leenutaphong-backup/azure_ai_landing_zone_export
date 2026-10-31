# extract-images

**Function:** pull embedded product imagery out of documentation pages.

## When to use

Almost always, in preference to a full-page capture of a documentation article. A doc page
is mostly prose; the reference material is the product screenshot inside it. Full-page
capture is for pages where the *page itself* is the artefact.

## Usage

```bash
python3 -m webres.cli.extract_images --targets "$LIBRARY_ROOT/collections/soc-dashboards/targets.json" \
  --out app/data/reference/product-imagery \
  --catalogue app/data/reference/manifest.json --per-page 3
```

## Arguments

| Flag | Meaning |
| --- | --- |
| `--url` / `--targets` | One URL, or the same target JSON the capture script uses. |
| `--out` | Directory for images. |
| `--catalogue` | Manifest to record provenance in. |
| `--per-page` | Max images kept per page. Default 4. |
| `--min-bytes` | Size floor. Default 25,000. |

## Output

`<page-slug>-<n>.<ext>` per image, plus a catalogue entry whose `source_url` is the image
and whose `notes` name the article it was embedded in. `alt` text becomes the title, which
is often the best one-line description of what the screenshot shows.

## Behaviour worth knowing

- **Follows Microsoft Learn `#lightbox` anchors** to the full-resolution asset rather than
  the inline thumbnail.
- **Filters chrome by path and size.** Icons, logos, avatars, sprites, SVGs, and anything
  under the size floor are skipped.
- **Requires a content path** — `/media/`, `/images/`, `/img/`, `/assets/`, `/static/` —
  which is what separates article figures from page furniture.

## Known limits

Sites that render documentation images through JavaScript return zero candidates, because
this parses HTML and does not execute scripts. Datadog and parts of Elastic behave this
way; use `capture-screenshot` for those.

Yield varies sharply by publisher: Microsoft Learn and Elastic embed many figures, Datadog
embeds almost none.
