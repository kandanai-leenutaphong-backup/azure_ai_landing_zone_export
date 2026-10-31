"""Time, injected — so tests exercise every ordering without ever sleeping.

WHY A CLOCK IS A DEPENDENCY
---------------------------
Two things in this package need time: the timestamp stamped into an artifact,
and the wait between bounded retries. Both are untestable when they are
imported directly. A test that proves "the second attempt happens after a
backoff" by sleeping for a second is a test nobody runs.

:class:`FixedClock` advances only when asked and records what it was told to
sleep, so the retry schedule is asserted as data.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """What this package needs from time. Three methods."""

    def now(self) -> str:
        """The current instant as an RFC 3339 UTC timestamp."""

    def monotonic(self) -> float:
        """A monotonic reading, for measuring elapsed work."""

    def sleep(self, seconds: float) -> None:
        """Wait. Called only between bounded retries."""


class SystemClock:
    """The real one. The default everywhere outside tests."""

    def now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FixedClock:
    """A clock that never really waits.

    Attributes:
        slept: Every duration ``sleep()`` was asked for, in order. This is how
            a backoff schedule is asserted without a test taking that long.
    """

    def __init__(self, start: str = "2001-01-01T00:00:00Z", step: float = 1.0) -> None:
        self._now = start
        self._monotonic = 0.0
        self._step = step
        self.slept: list[float] = []

    def now(self) -> str:
        return self._now

    def set(self, value: str) -> None:
        """Move the wall clock, for a test that needs two distinct timestamps."""
        self._now = value

    def monotonic(self) -> float:
        self._monotonic += self._step
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


__all__ = ["Clock", "FixedClock", "SystemClock"]
