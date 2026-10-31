"""Read-only filesystem inventory and before/after comparison; never deletes inputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import stat
import sys
import time


FORMAT = "codebase-cleanup-inventory-v1"
COUNTERS = ("files", "logical_bytes", "directories", "symlinks", "special_files")


def scan(root, *, group_depth=4, exclude=()):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Inventory root must be a directory")
    if type(group_depth) is not int or not 1 <= group_depth <= 8:
        raise ValueError("group_depth must be between 1 and 8")
    exclusions = sorted({".git", *exclude})
    if any(not isinstance(pattern, str) or not pattern for pattern in exclusions):
        raise ValueError("Exclusions must be nonempty relative glob patterns")
    started = time.monotonic()
    totals = dict.fromkeys(COUNTERS, 0)
    groups = {}
    errors = []
    error_count = 0
    excluded_entries = 0
    stack = []

    def record_error(path, error):
        nonlocal error_count
        error_count += 1
        if len(errors) < 20:
            errors.append({"path": path, "kind": type(error).__name__, "errno": error.errno})

    def group(path):
        return groups.setdefault(path, {"files": 0, "logical_bytes": 0})

    try:
        try:
            stack.append(("", os.scandir(root)))
        except OSError as error:
            record_error(".", error)
        while stack:
            parent, entries = stack[-1]
            try:
                entry = next(entries)
            except StopIteration:
                entries.close()
                stack.pop()
                continue
            except OSError as error:
                record_error(parent or ".", error)
                entries.close()
                stack.pop()
                continue
            relative = f"{parent}/{entry.name}" if parent else entry.name
            if any(fnmatch.fnmatchcase(relative, pattern) for pattern in exclusions):
                excluded_entries += 1
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as error:
                record_error(relative, error)
                continue
            if stat.S_ISLNK(info.st_mode):
                totals["symlinks"] += 1
            elif stat.S_ISDIR(info.st_mode):
                totals["directories"] += 1
                if len(relative.split("/")) <= group_depth:
                    group(relative)
                try:
                    stack.append((relative, os.scandir(entry.path)))
                except OSError as error:
                    record_error(relative, error)
            elif stat.S_ISREG(info.st_mode):
                totals["files"] += 1
                totals["logical_bytes"] += info.st_size
                ancestors = relative.split("/")[:-1]
                for depth in range(1, min(len(ancestors), group_depth) + 1):
                    aggregate = group("/".join(ancestors[:depth]))
                    aggregate["files"] += 1
                    aggregate["logical_bytes"] += info.st_size
            else:
                totals["special_files"] += 1
    finally:
        for _, entries in stack:
            entries.close()

    return {"format": FORMAT, "root": str(root),
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "scope": {"excluded_patterns": exclusions, "follow_symlinks": False,
                      "hardlinks": "each regular-file directory entry counted separately",
                      "bytes": "logical file-content bytes, not allocated blocks or RAM"},
            "group_depth": group_depth, "totals": totals,
            "groups": [{"path": path, **value} for path, value in sorted(groups.items())],
            "excluded_entries": excluded_entries, "complete": error_count == 0,
            "error_count": error_count, "error_samples": errors}


def compare(before, after):
    for report in (before, after):
        if report.get("format") != FORMAT or report.get("complete") is not True or report.get("error_count") != 0:
            raise ValueError("Comparison requires two complete inventories with no scan errors")
        if any(type(report.get("totals", {}).get(name)) is not int or report["totals"][name] < 0 for name in COUNTERS):
            raise ValueError("Inventory counters must be nonnegative integers")
    if before["root"] != after["root"] or before["scope"] != after["scope"]:
        raise ValueError("Comparison requires identical roots and counting scope")
    removed = {name: before["totals"][name] - after["totals"][name] for name in COUNTERS}
    count = before["totals"]["files"]
    return {"format": "codebase-cleanup-comparison-v1", "root": before["root"],
            "scope": before["scope"], "before": before["totals"], "after": after["totals"],
            "net_removed": removed,
            "file_reduction_percent": round(100 * removed["files"] / count, 6) if count else None,
            "measurement_times": [before["measured_at"], after["measured_at"]],
            "limits": ["Net counters include files added or regenerated between scans.",
                       "Concurrent filesystem activity is not an atomic snapshot.",
                       "Logical bytes are not allocated disk savings or process memory savings."]}


def write_report(report, output=None):
    content = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if output is None:
        print(content, end="")
        return
    target = Path(output).resolve()
    root = Path(report["root"])
    if target == root or root in target.parents:
        raise ValueError("Write inventory reports outside the measured workspace")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as destination:
        destination.write(content)
    print(json.dumps({"report": str(target), "complete": report.get("complete"),
                      "totals": report.get("totals"), "net_removed": report.get("net_removed")}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("scan", help="read filesystem metadata; no file contents or deletion")
    inventory.add_argument("root", type=Path)
    inventory.add_argument("--group-depth", type=int, default=4)
    inventory.add_argument("--exclude", action="append", default=[], help="relative fnmatch pattern; .git at root is always excluded")
    inventory.add_argument("--output", type=Path, help="new JSON report outside root; stdout if omitted")
    difference = commands.add_parser("compare", help="compare complete inventories from the same root and scope")
    difference.add_argument("before", type=Path)
    difference.add_argument("after", type=Path)
    difference.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "scan":
            report = scan(arguments.root, group_depth=arguments.group_depth, exclude=arguments.exclude)
        else:
            report = compare(json.loads(arguments.before.read_text()), json.loads(arguments.after.read_text()))
        write_report(report, arguments.output)
        return 0 if report.get("complete", True) else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())