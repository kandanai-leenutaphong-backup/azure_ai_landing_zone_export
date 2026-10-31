#!/usr/bin/env python3
"""Inspect, verify, and repair an acquisition catalogue.

    python3 catalogue.py --catalogue app/data/reference/manifest.json --verify
    python3 catalogue.py --catalogue manifest.json --adopt app/data/reference/screenshots \
        --subject soc-dashboards --function screenshot
    python3 catalogue.py --catalogue manifest.json --index app/data/reference/INDEX.md

`--verify` reports artefacts missing from disk, entries whose hash no longer
matches, and files on disk that nothing catalogues. `--adopt` back-fills entries
for files acquired before the catalogue existed, marking their provenance as
unrecorded rather than inventing one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from webres import Catalogue, Provenance, now_iso, sha256_bytes

MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".html", ".txt", ".json", ".pdf", ".svg"}
CONTENT_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".html": "text/html", ".txt": "text/plain", ".json": "application/json",
    ".pdf": "application/pdf", ".svg": "image/svg+xml",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--verify", action="store_true", help="check artefacts against their recorded hashes")
    parser.add_argument("--adopt", type=Path, help="back-fill entries for files in this directory")
    parser.add_argument("--subject", default="uncategorised", help="subject tag for adopted files")
    parser.add_argument("--function", default="unknown", help="function tag for adopted files")
    parser.add_argument("--prune", action="store_true", help="drop entries whose artefact is gone")
    parser.add_argument("--index", type=Path, help="write a human-readable index to this path")
    args = parser.parse_args()

    args.catalogue = args.catalogue.resolve()
    catalogue = Catalogue(args.catalogue)
    root = args.catalogue.parent
    status = 0

    if args.adopt:
        adopted = 0
        for path in sorted(args.adopt.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in MEDIA:
                continue
            key = catalogue.key_for(path)
            if key in catalogue.entries:
                continue
            payload = path.read_bytes()
            catalogue.record(
                Provenance(
                    # Provenance is unknown by construction; say so rather than guess.
                    source_url="",
                    retrieved_at=now_iso(),
                    status=0,
                    content_type=CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"),
                    sha256=sha256_bytes(payload),
                    bytes=len(payload),
                    subject=args.subject,
                    function=args.function,
                    artefact=key,
                    notes="adopted into catalogue; original source URL not recorded at acquisition time",
                )
            )
            adopted += 1
        print(f"adopted {adopted} file(s)")

    if args.prune:
        gone = catalogue.drop_missing(root)
        print(f"pruned {len(gone)} missing entry(ies)" + (f": {gone}" if gone else ""))

    if args.verify:
        missing, changed = [], []
        for key, entry in sorted(catalogue.entries.items()):
            path = catalogue.artefact_path(key)
            if not path.exists():
                missing.append(key)
                continue
            if entry.get("sha256") and sha256_bytes(path.read_bytes()) != entry["sha256"]:
                changed.append(key)
        catalogued = set(catalogue.entries)
        on_disk = {
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in MEDIA and p != args.catalogue
        }
        orphans = sorted(on_disk - catalogued)

        print(f"entries    {len(catalogue.entries)}")
        print(f"missing    {len(missing)}" + (f"  {missing}" if missing else ""))
        print(f"changed    {len(changed)}" + (f"  {changed}" if changed else ""))
        print(f"uncatalogued {len(orphans)}" + (f"  {orphans[:6]}" if orphans else ""))
        no_source = [k for k, e in catalogue.entries.items() if not e.get("source_url")]
        print(f"no source url {len(no_source)}")
        if missing or changed or orphans:
            status = 1

    if args.index:
        lines = [
            "# Acquisition index",
            "",
            f"{len(catalogue.entries)} artefact(s). Generated {now_iso()}.",
            "",
            "Third-party material is held for internal reference only and remains the property",
            "of its publisher. Do not redistribute.",
            "",
        ]
        for subject, entries in sorted(catalogue.by_subject().items()):
            lines += [f"## {subject}", "", "| Artefact | Publisher | Source | Retrieved |", "| --- | --- | --- | --- |"]
            for entry in sorted(entries, key=lambda e: str(e.get("artefact", ""))):
                url = str(entry.get("source_url") or "")
                link = f"[link]({url})" if url else "_not recorded_"
                lines.append(
                    f"| `{entry.get('artefact')}` | {entry.get('publisher') or '—'} | {link} | {entry.get('retrieved_at')} |"
                )
            lines.append("")
        args.index.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {args.index}")

    if args.adopt or args.prune:
        catalogue.save()
    return status


if __name__ == "__main__":
    sys.exit(main())
