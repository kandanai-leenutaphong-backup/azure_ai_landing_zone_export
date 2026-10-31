#!/usr/bin/env python3
"""inspect_document.py — validate a document and print what it would compose.

    appcompose-inspect appcompose/demo/field-notes.yaml
    appcompose-inspect app.json --canonical > app.canonical.json

Reads JSON or YAML, chosen by file extension. Prints the members in the order
they would start, their placement, and their declared dependencies. Exits 0 when
the document is valid, 1 with the offending field when it is not, 2 on usage.

It resolves no capability and imports nothing the document names, so it is safe
to point at a file you did not write.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from appcompose import DocumentInvalid, canonical_json, from_json, from_yaml


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="appcompose-inspect",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("path", help="the document to read (.json, .yaml or .yml)")
    ap.add_argument("--canonical", action="store_true",
                    help="print canonical JSON bytes instead of the summary")
    args = ap.parse_args(argv)

    path = Path(args.path)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    raw = path.read_bytes()
    reader = from_yaml if path.suffix.lower() in (".yaml", ".yml") else from_json

    try:
        document = reader(raw)
    except DocumentInvalid as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1

    if args.canonical:
        sys.stdout.write(canonical_json(document).decode("utf-8"))
        return 0

    print(f"{document.name} (schemaVersion {document.schema_version})")
    print("  members, in startup order — shutdown reverses this:")
    for member_id in document.order():
        member = document.member(member_id)
        placement = document.placement(member_id)
        needs = f" requires {list(member.requires)}" if member.requires else ""
        where = f" [{placement.slot}]" if placement.slot else ""
        print(f"    {member_id}: {member.capability}{where}{needs}")
    if document.ownership:
        print("  contested assets, owned by:")
        for asset_path, owner in sorted(document.ownership.items()):
            print(f"    {asset_path} -> {owner}")
    print("  capabilities to allow in your resolver:")
    for capability in sorted({m.capability for m in document.members}):
        print(f"    {capability}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
