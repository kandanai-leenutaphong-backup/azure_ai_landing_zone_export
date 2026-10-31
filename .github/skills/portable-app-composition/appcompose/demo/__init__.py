"""Two small capabilities used by the worked examples and the selftest.

They live in the package rather than in ``examples/`` for one practical reason:
the conformance gate executes every ``examples/*.py`` as a standalone script,
so a shared helper parked there would be run as though it were an example and
would assert nothing. Helpers belong in the package; examples stay executable.

They are illustration, not mechanism. Nothing in :mod:`appcompose.compose`
imports them, and deleting this subpackage leaves the skill working.
"""

from __future__ import annotations

__all__ = ["digest", "notes"]
