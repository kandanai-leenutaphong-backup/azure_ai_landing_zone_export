#!/usr/bin/env python3
"""Fetch web pages to disk with provenance.

    python3 fetch_page.py --url https://example.com/docs --subject soc-dashboards \
        --out app/data/reference/pages --catalogue app/data/reference/manifest.json

    python3 fetch_page.py --urls urls.txt --subject observability --out refs/ --text

Consults robots.txt, rate limits per host, and records source URL, retrieval
time, content hash, and status for every artefact. Exits non-zero if any URL
fails, but continues through the rest of the list first.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import sys
from pathlib import Path

from webres import (
    AcquisitionError,
    Catalogue,
    RobotsDisallowed,
    fetch,
    sha256_bytes,
    slugify,
)

# Strip scripts and styles when saving text, since neither is reference material.
try:
    import re

    _STRIP = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
    _TAGS = re.compile(r"<[^>]+>")
    _WS = re.compile(r"\n{3,}")
except Exception:  # pragma: no cover
    raise


def to_text(html: str) -> str:
    body = _STRIP.sub(" ", html)
    body = _TAGS.sub("\n", body)
    return _WS.sub("\n\n", body).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", action="append", default=[], help="a URL to fetch; repeatable")
    source.add_argument("--urls", type=Path, help="file of URLs, one per line, # comments allowed")
    parser.add_argument("--out", type=Path, required=True, help="directory to write artefacts into")
    parser.add_argument("--catalogue", type=Path, help="manifest JSON to record provenance in")
    parser.add_argument("--subject", default="uncategorised", help="subject tag for the catalogue")
    parser.add_argument("--text", action="store_true", help="also write a plain-text rendering")
    parser.add_argument("--ignore-robots", action="store_true", help="skip the robots.txt check; use only with permission")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    urls = list(args.url)
    if args.urls:
        urls += [
            line.strip()
            for line in args.urls.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not urls:
        print("no URLs supplied", file=sys.stderr)
        return 2

    args.out = args.out.resolve()
    args.catalogue = (args.catalogue or args.out / "manifest.json").resolve()
    catalogue = Catalogue(args.catalogue)
    catalogue.key_for(args.out / "output.html")
    args.out.mkdir(parents=True, exist_ok=True)

    failures = 0
    for url in urls:
        try:
            payload, provenance = fetch(url, timeout=args.timeout, obey_robots=not args.ignore_robots)
        except RobotsDisallowed as exc:
            print(f"  SKIP  {url}\n        {exc}")
            failures += 1
            continue
        except AcquisitionError as exc:
            print(f"  FAIL  {url}\n        {exc}")
            failures += 1
            continue

        name = slugify(provenance.title or url.rsplit("/", 1)[-1] or provenance.publisher) + "-" + sha256_bytes(url.encode())[:10]
        target = args.out / f"{name}.html"
        target.write_bytes(payload)

        provenance.subject = args.subject
        provenance.function = "page-fetch"
        provenance.artefact = catalogue.key_for(target)
        if args.ignore_robots:
            provenance.notes = "robots.txt override explicitly requested by operator"
        catalogue.record(provenance)
        if args.text and "html" in provenance.content_type.lower():
            text_path = args.out / f"{name}.txt"
            text = to_text(payload.decode("utf-8", errors="replace"))
            text_path.write_text(text, encoding="utf-8")
            catalogue.record(replace(provenance, artefact=catalogue.key_for(text_path),
                                     content_type="text/plain", sha256=sha256_bytes(text.encode()),
                                     bytes=len(text.encode()), function="page-text"))
        print(f"  ok    {target.name}  {provenance.bytes:,}B  {provenance.title[:60]}")

    if catalogue:
        catalogue.save()
        print(f"catalogued {len(catalogue.entries)} artefact(s) -> {args.catalogue}")

    print(f"{len(urls) - failures}/{len(urls)} fetched")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
