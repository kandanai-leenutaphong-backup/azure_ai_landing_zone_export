"""Offline command-line entry point for the installed framework."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentcraft",
        description="Explicit composition of installed Agentcraft capabilities.",
    )
    parser.add_argument("--version", action="version", version=f"agentcraft {__version__}")
    commands = parser.add_subparsers(dest="command")
    describe = commands.add_parser("describe", help="List installed capability contracts without provider I/O.")
    describe.add_argument("name", nargs="?")
    catalogue = commands.add_parser("catalogue", help="Find or read installed task guidance (tooling extra).")
    selection = catalogue.add_mutually_exclusive_group()
    selection.add_argument("--find")
    selection.add_argument("--show")
    catalogue.add_argument("--kind", choices=("skill", "protocol"))
    catalogue.add_argument("--limit", type=int, default=5)
    mcp = commands.add_parser("mcp", help="Run the optional composition-only MCP stdio host.")
    mcp.add_argument("--offline", action="store_true", required=True)
    options = parser.parse_args(argv)
    if options.command == "mcp":
        from .mcp import main as serve

        return serve()
    if options.command in {"describe", "catalogue"}:
        from .catalogue import load_catalogue, report

        try:
            if options.command == "describe":
                document = load_catalogue()
                capabilities = document["capabilities"]
                if options.name:
                    capabilities = [entry for entry in capabilities if entry["id"] == options.name]
                    if not capabilities:
                        raise ValueError("unknown_capability")
                result = {"schema_version": document["schema_version"],
                          "capabilities": capabilities, "readiness": "unverified"}
            else:
                result = report(query=options.find, name=options.show,
                                kind=options.kind, limit=options.limit)
        except (ValueError, OSError, RuntimeError):
            print("Catalogue request refused; check the name and installed tooling/guidance artifacts.", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())