# Rights and Provenance

Authored summary of the rights basis for every retained painterly holding. It
replaces a previously stored copy of the publisher's documentation page, which
carried no demonstrated redistribution licence. Read the publisher's own pages
for the authoritative wording; the links below are the citations, not a copy.

## Sources of authority

| Authority | Link | What it establishes |
| --- | --- | --- |
| Met Collection API documentation | <https://metmuseum.github.io/> | The API serves Open Access data and corresponding high-resolution JPEG images that are in the public domain, and defines `isPublicDomain: true` as marking an artwork in the public domain. |
| Met Open Access | <https://www.metmuseum.org/about-the-met/policies-and-documents/open-access> | Programme terms for the public-domain image release. |

Two distinct instruments, not interchangeable:

- **Object metadata** is released by the museum under Creative Commons Zero
  (CC0 1.0). That covers the JSON records retained under `holdings/records/`.
- **Images** of works the museum marks `isPublicDomain: true` are in the public
  domain because the underlying works are; the museum asserts no separate image
  copyright over them. Metadata openness alone would not establish image rights,
  so the per-object flag is the operative evidence and is stored locally.

## Per-artifact basis

Each retained record is checked in the repository, not recalled. `isPublicDomain`
was read from the stored JSON.

| Artifact | Work | Object | `isPublicDomain` | Basis |
| --- | --- | --- | --- | --- |
| `records/met-343077.json` | Jean Laurent Legeay, *Architectural Fantasy*, ca. 1785-90 | [343077](https://www.metmuseum.org/art/collection/search/343077) | `true` | Metadata: CC0 1.0 |
| `records/met-343439.json` | Charles Michel Ange Challe, *Architectural Fantasy*, 18th century | [343439](https://www.metmuseum.org/art/collection/search/343439) | `true` | Metadata: CC0 1.0 |
| `records/met-437853.json` | Joseph Mallord William Turner, *Venice, from the Porch of Madonna della Salute*, ca. 1835 | [437853](https://www.metmuseum.org/art/collection/search/437853) | `true` | Metadata: CC0 1.0 |
| `records/met-10499.json` | Thomas Cole, *The Titan's Goblet*, 1833 | [10499](https://www.metmuseum.org/art/collection/search/10499) | `true` | Metadata: CC0 1.0 |
| `images/legeay-architectural-fantasy.jpg` | Legeay, as above | 343077 | `true` | Image: public domain, unmodified download |
| `images/challe-architectural-fantasy.jpg` | Challe, as above | 343439 | `true` | Image: public domain, unmodified download |
| `images/turner-venice.jpg` | Turner, as above | 437853 | `true` | Image: public domain, unmodified download |
| `images/cole-titans-goblet.jpg` | Cole, as above | 10499 | `true` | Image: public domain, unmodified download |
| `originals/met-343077-original.jpg` | Legeay, as above | 343077 | `true` | Image: public domain, full-resolution mask input |
| `originals/met-343439-original.jpg` | Challe, as above | 343439 | `true` | Image: public domain, full-resolution mask input |

Verify the flags directly:

```bash
python3 - <<'PY'
import json, pathlib
for path in sorted(pathlib.Path("research/painterly/holdings/records").glob("met-*.json")):
    record = json.loads(path.read_text())
    print(path.name, record["objectID"], record["isPublicDomain"], record["artistDisplayName"])
PY
```

`scripts/generate-painterly-masks.mjs` re-asserts `isPublicDomain === true` and the
recorded source hash for every mask it produces, so a mask cannot be generated from
an unverified original.

## What this does not grant

- No museum endorsement, sponsorship or affiliation is claimed or implied.
- Nothing here licenses the publisher's own website text, page markup, logos or
  photography of non-public-domain works.
- Artist, title, object number and museum provenance travel with every derived
  mask, in `public/THIRD_PARTY_NOTICES.txt` and [ASSETS.md](../../ASSETS.md).
- No licence is asserted beyond what the linked publisher documents state.
