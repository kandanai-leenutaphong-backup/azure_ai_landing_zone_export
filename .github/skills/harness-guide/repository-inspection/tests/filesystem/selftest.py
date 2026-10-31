"""Run the bundled inventory tests without a consuming project or dependencies."""

from pathlib import Path
import unittest


def main():
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parent), pattern="test_*.py"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun == 0:
        return 1
    print("codebase-cleanup selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())