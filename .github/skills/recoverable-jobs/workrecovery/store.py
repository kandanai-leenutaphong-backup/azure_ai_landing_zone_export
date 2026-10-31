"""What a store has to look like, and an in-memory one to test against.

WHY A PROTOCOL AND NOT AN SDK
-----------------------------
The destination is the caller's: a document database, an object store, a
queue, an HTTP API. Importing any of them here would make this package
untestable without that service, and untestable-without-a-service is the
reason recovery paths are the least exercised code in most systems.

Two methods. ``save`` writes; ``load`` answers "is it there". ``load`` is the
one that is easy to leave out and impossible to do without: a write that timed
out client-side **may already have succeeded**, so "the save timed out" and
"nothing was saved" are different claims. Looking costs one cheap read; not
looking costs a re-run of everything the job did.

WHAT AN ADAPTER MUST TRANSLATE
------------------------------
Its client's failures into the four cases in ``errors``: ``StoreRefused``
(rejected, nothing landed), ``StoreUnavailable`` (never sent), ``StoreTimeout``
(sent, outcome unknown), ``StoreOccupied`` (the id already holds different
content, which was left alone). Everything else is treated as an unknown
outcome, which is the safe reading but a less useful one.

WHAT ``save`` MUST DO, AND WHY IT IS NOT "WRITE"
------------------------------------------------
``save`` is **create-if-absent, or accept byte-identical content**. It is not
an overwrite. A run id belongs to one run's output; a second writer under the
same id is an ownership bug, and letting it win destroys the first run's only
committed copy while telling the second one it succeeded.

Three cases, all required:

1. nothing under ``run_id`` — write it;
2. ``content`` byte-identical to what is there — succeed, change nothing. This
   is what makes ``recommit`` after a restart safe to run twice;
3. different bytes under ``run_id`` — raise ``StoreOccupied`` and leave the
   stored bytes untouched.

The only way to make case 3 airtight is an **atomic conditional write** in the
adapter, because a read-then-write has a window between the two. Cosmos DB
offers ``if-none-match: *`` on create; Azure Blob Storage offers the same
header on ``Put Blob``; S3 offers ``If-None-Match: *``; a SQL store offers a
unique constraint on the id column and translates the violation. Use one of
those. An adapter that cannot must say so, and its callers inherit a race this
package cannot close for them: the engine's pre-write check narrows the window,
it does not remove it.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from typing import Protocol

from workrecovery.errors import (
    StoreOccupied,
    StoreRefused,
    StoreTimeout,
    StoreUnavailable,
)


class Store(Protocol):
    """The two calls this package makes against the authoritative store."""

    def save(self, run_id: str, content: bytes, content_type: str) -> None:
        """Create ``run_id`` holding ``content``, or accept identical content.

        Never an overwrite. Raise ``StoreOccupied`` when ``run_id`` already
        holds different bytes, and leave those bytes where they are. Prefer an
        atomic conditional write (``if-none-match: *``, a unique constraint)
        over a read-then-write, which has a race.

        Raise ``StoreRefused``, ``StoreUnavailable`` or ``StoreTimeout`` to
        distinguish the other three outcomes. Returning normally means the
        store accepted the write; it does not mean this package believes it —
        the read-back decides that.
        """

    def load(self, run_id: str) -> bytes | None:
        """The bytes stored under ``run_id``, or None when there are none.

        "Not there" must be ``None``, not an exception: absent is an answer.
        Raise only when the store would not tell you, which is reported as an
        unknown outcome rather than as an absence.
        """


class MemoryStore:
    """An in-memory store for tests, including the failures a real one has.

    It implements the ``save`` contract rather than approximating it: an id
    that already holds different bytes raises ``StoreOccupied`` and keeps the
    original. A double that clobbers would make every test of the no-clobber
    guarantee vacuous, which is exactly how the guarantee got overstated.

    ``timeout`` with ``lands=True`` is the combination that matters: the item
    is recorded and *then* the call raises, which is exactly what a store does
    when a client-side read timeout fires after the write was committed.
    Without it, the reconciliation path could only ever be tested against a
    store where nothing arrived — the case it was not written for.

    Args:
        items: Pre-existing content, keyed by run id. Use it to place a
            *foreign* document under the id this run is about to use.
        refuse: Non-empty to make every save raise ``StoreRefused``.
        unavailable_times: How many saves fail as ``StoreUnavailable`` before
            one succeeds. Drives the bounded-retry path with no sleeping.
        timeout: A ``StoreTimeout`` to raise from ``save``.
        lands: Whether that timed-out save records the item anyway.
        load_error: Raised by ``load`` — the store that will not answer.
        load_blind: When True, ``load`` returns None even for stored items,
            modelling a read-back that has not caught up yet.
    """

    def __init__(
        self,
        *,
        items: dict[str, bytes] | None = None,
        refuse: str = "",
        unavailable_times: int = 0,
        timeout: StoreTimeout | None = None,
        lands: bool = False,
        load_error: Exception | None = None,
        load_blind: bool = False,
    ) -> None:
        self.items: dict[str, bytes] = {
            key: bytes(value) for key, value in dict(items or {}).items()
        }
        self.content_types: dict[str, str] = {}
        self.refuse = refuse
        self.unavailable_times = unavailable_times
        self.timeout = timeout
        self.lands = lands
        self.load_error = load_error
        self.load_blind = load_blind
        self.saves = 0
        self.loads = 0

    def _place(self, run_id: str, content: bytes, content_type: str) -> None:
        """Create-if-absent-or-identical, the contract in three lines."""
        existing = self.items.get(run_id)
        if existing is not None:
            if existing == content:
                return
            raise StoreOccupied(
                f"run {run_id!r} already holds {len(existing)} different bytes; "
                "they were left exactly as they were"
            )
        # A snapshot: a caller that mutates its buffer afterwards must not be
        # able to change what this store claims to hold.
        self.items[run_id] = bytes(content)
        self.content_types[run_id] = content_type

    def save(self, run_id: str, content: bytes, content_type: str) -> None:
        self.saves += 1
        if self.unavailable_times > 0:
            self.unavailable_times -= 1
            raise StoreUnavailable("the store could not be reached")
        if self.refuse:
            raise StoreRefused(self.refuse)
        if self.timeout is not None:
            if self.lands:
                self._place(run_id, content, content_type)
            raise self.timeout
        self._place(run_id, content, content_type)

    def load(self, run_id: str) -> bytes | None:
        self.loads += 1
        if self.load_error is not None:
            raise self.load_error
        if self.load_blind:
            return None
        stored = self.items.get(run_id)
        return None if stored is None else bytes(stored)


__all__ = ["MemoryStore", "Store"]
