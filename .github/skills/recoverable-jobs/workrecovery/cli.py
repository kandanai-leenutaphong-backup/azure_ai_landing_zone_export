#!/usr/bin/env python3
"""recover.py — look at what did not land, and get the bytes back out.

    workrecovery list   /var/lib/recovery
    workrecovery show   /var/lib/recovery --run-id nightly-0001
    workrecovery verify /var/lib/recovery
    workrecovery export /var/lib/recovery --run-id nightly-0001 \
        --out ./nightly-0001.json

Read-only apart from ``export``, which writes one new file and refuses to
overwrite an existing one. It never deletes an artifact: cleanup happens after
a verified store write, and this tool has no store.

Re-committing needs the destination store, which is the caller's, so it is a
library call rather than a subcommand::

    jobs = RecoverableJobs(store=my_store, root="/var/lib/recovery")
    outcome = jobs.recommit(jobs.read("nightly-0001"))

Exit codes: 0 fine, 1 something is corrupt or missing, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workrecovery import ArtifactStore, RecoveryError
from workrecovery.payload import BYTES_CONTENT_TYPE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workrecovery",
        description="Inspect and export completed job output preserved on disk.",
    )
    parser.add_argument("action", choices=("list", "show", "verify", "export"))
    parser.add_argument("root", help="the recovery directory")
    parser.add_argument("--run-id", help="required by show and export")
    parser.add_argument("--out", help="file to write, for export; must not exist")
    args = parser.parse_args(argv)

    store = ArtifactStore(args.root)
    if not store.root.is_dir():
        print(f"no such recovery directory: {store.root}", file=sys.stderr)
        return 2

    if args.action in ("show", "export") and not args.run_id:
        print(f"--run-id is required for {args.action}", file=sys.stderr)
        return 2

    try:
        if args.action == "list":
            artifacts = store.list()
            problems = store.problems()
            for artifact in artifacts:
                print(json.dumps(artifact.summary()))
            for path, reason in problems:
                print(f"PROBLEM {path}: {reason}", file=sys.stderr)
            print(
                f"\n{len(artifacts)} recoverable, {len(problems)} unreadable",
                file=sys.stderr,
            )
            return 1 if problems else 0

        if args.action == "verify":
            problems = store.problems()
            for path, reason in problems:
                print(f"PROBLEM {path}: {reason}")
            count = len(store.list())
            print(f"{count} artifact(s) verified against their own digests")
            return 1 if problems else 0

        artifact = store.read_run(args.run_id)

        if args.action == "show":
            print(json.dumps(artifact.summary(), indent=2))
            return 0

        if not args.out:
            print("--out is required for export", file=sys.stderr)
            return 2
        target = Path(args.out)
        if target.exists():
            print(f"{target} already exists; refusing to overwrite", file=sys.stderr)
            return 2
        if artifact.content_type == BYTES_CONTENT_TYPE:
            target.write_bytes(artifact.payload)
        else:
            target.write_text(
                json.dumps(artifact.payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"wrote {target} ({artifact.content_bytes} bytes of output)")
        return 0

    except RecoveryError as refused:
        print(f"{refused}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
