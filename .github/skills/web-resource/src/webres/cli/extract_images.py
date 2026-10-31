#!/usr/bin/env python3
"""Extract embedded product imagery from documentation pages.

    python3 extract_images.py --targets targets.json --out shots/ --catalogue manifest.json

A full-page capture of a documentation article is mostly prose. The material
worth keeping is the product screenshot embedded inside it. This fetches the
page, finds the content images, and downloads them with provenance pointing at
both the image and the article it came from.

Icons, logos, avatars, and anything below a size floor are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from webres import (
    AcquisitionError,
    Catalogue,
    Provenance,
    RobotsDisallowed,
    fetch,
    slugify,
)

IMG = re.compile(r"<img[^>]+>", re.I)
ATTR = re.compile(r'(src|data-src|srcset|alt)\s*=\s*["\']([^"\']+)["\']', re.I)
# Microsoft Learn wraps the full-resolution asset in a #lightbox anchor.
LIGHTBOX = re.compile(r'href\s*=\s*["\']([^"\']+?)#lightbox["\']', re.I)

# Path fragments that mark chrome rather than content.
CHROME = ("icon", "logo", "avatar", "favicon", "sprite", "badge", "banner", "spacer", "pixel")
CONTENT_HINT = ("/media/", "/images/", "/img/", "/assets/", "/screenshots/", "/static/")

# Below this a file is decoration, not a reference screenshot.
MIN_BYTES = 25_000


def candidates(html: str, base: str) -> list[tuple[str, str]]:
    """Return (absolute_url, alt_text) for plausible content images."""
    found: dict[str, str] = {}

    for href in LIGHTBOX.findall(html):
        found.setdefault(urllib.parse.urljoin(base, href), "")

    for tag in IMG.findall(html):
        attrs = {k.lower(): v for k, v in ATTR.findall(tag)}
        src = attrs.get("src") or attrs.get("data-src") or ""
        if not src and attrs.get("srcset"):
            src = attrs["srcset"].split(",")[0].strip().split(" ")[0]
        if not src or src.startswith("data:"):
            continue
        url = urllib.parse.urljoin(base, src)
        found.setdefault(url, attrs.get("alt", "")[:120])

    out = []
    for url, alt in found.items():
        low = url.lower()
        if low.endswith(".svg") or any(term in low for term in CHROME):
            continue
        if not any(hint in low for hint in CONTENT_HINT):
            continue
        out.append((url, alt))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", action="append", default=[])
    source.add_argument("--targets", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path)
    parser.add_argument("--subject", default="uncategorised")
    parser.add_argument("--per-page", type=int, default=4, help="max images to keep per page")
    parser.add_argument("--min-bytes", type=int, default=MIN_BYTES)
    args = parser.parse_args()

    if args.targets:
        targets = json.loads(args.targets.read_text(encoding="utf-8"))
    else:
        targets = [{"url": u, "name": slugify(u), "subject": args.subject} for u in args.url]

    args.out = args.out.resolve()
    args.catalogue = (args.catalogue or args.out / "manifest.json").resolve()
    catalogue = Catalogue(args.catalogue)
    catalogue.key_for(args.out / "image.png")
    args.out.mkdir(parents=True, exist_ok=True)

    kept = skipped = 0
    for target in targets:
        page_url, stem = target["url"], slugify(target.get("name") or target["url"])
        try:
            payload, page_prov = fetch(page_url)
        except (AcquisitionError, RobotsDisallowed) as exc:
            print(f"  FAIL  {stem}: {exc}")
            continue

        html = payload.decode("utf-8", errors="replace")
        found = candidates(html, page_url)
        print(f"  {stem}: {len(found)} candidate image(s)")

        taken = 0
        for url, alt in found:
            if taken >= args.per_page:
                break
            try:
                blob, prov = fetch(url, accept="image/*,*/*;q=0.8")
            except (AcquisitionError, RobotsDisallowed):
                continue
            if len(blob) < args.min_bytes or "image" not in prov.content_type.lower():
                skipped += 1
                continue

            suffix = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".png"
            name = f"{stem}-{taken + 1}{suffix}"
            path = args.out / name
            path.write_bytes(blob)

            prov.subject = target.get("subject", args.subject)
            prov.function = "embedded-image"
            prov.title = alt or page_prov.title
            prov.notes = f"embedded in {page_url}"
            prov.artefact = catalogue.key_for(path)
            catalogue.record(prov)
            print(f"    ok  {name}  {len(blob):,}B  {(alt or '')[:58]}")
            kept += 1
            taken += 1

    if catalogue:
        catalogue.save()
        print(f"catalogued {len(catalogue.entries)} artefact(s) -> {args.catalogue}")
    print(f"kept {kept}, skipped {skipped} below {args.min_bytes:,}B")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
