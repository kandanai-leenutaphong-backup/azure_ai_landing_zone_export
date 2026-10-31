#!/usr/bin/env python3
"""Run the wrapper's positive and refusal checks using an explicit external runtime."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    node = runtime / "node_modules/node/bin/node"
    if not node.is_file():
        parser.error("run npm ci in the external runtime first; its locked Node executable is missing")
    result = subprocess.run([str(node), "--test", str(Path(__file__).with_name("test_wrapper.mjs"))],
                            env={**os.environ, "HYPERFRAMES_TEST_RUNTIME": str(runtime)}, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())