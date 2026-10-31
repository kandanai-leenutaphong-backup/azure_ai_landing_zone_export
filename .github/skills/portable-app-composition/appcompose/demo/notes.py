"""The provider capability: a note store with an HTTP surface.

Independent of :mod:`appcompose.demo.digest` — it does not import it, does not
know it exists, and was not modified to be composed with it. That is what
"composed, not coupled" has to mean to be worth claiming.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

from appcompose.compose import Asset, Contribution, Request, Response, Route
from appcompose.document import Member

__all__ = ["NoteStore", "SHARED_STYLESHEET", "notes_capability"]

#: Bytes both demo capabilities ship at the same path, on purpose: it is how the
#: examples reach a real asset collision rather than a contrived one.
SHARED_STYLESHEET = b"body{font-family:system-ui;margin:2rem}\n"


class NoteStore:
    """The provider's state. Refuses reads and writes before it is opened."""

    def __init__(self) -> None:
        self._notes: list[str] = []
        self.opened = False
        self.closed = False
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        self.open_calls += 1
        self.opened = True
        self.closed = False

    def close(self) -> None:
        self.close_calls += 1
        self.opened = False
        self.closed = True

    def _require_open(self) -> None:
        if not self.opened:
            raise RuntimeError(
                "note store is not open; its member has not started yet")

    def add(self, text: str) -> int:
        self._require_open()
        self._notes.append(text)
        return len(self._notes) - 1

    def get(self, index: int) -> str:
        self._require_open()
        return self._notes[index]

    def all(self) -> tuple[str, ...]:
        self._require_open()
        return tuple(self._notes)


def _json(payload: Any, status: int = 200) -> Response:
    return Response(status=status,
                    body=json.dumps(payload, sort_keys=True).encode("utf-8"),
                    media_type="application/json")


def notes_capability(
    store: NoteStore,
    *,
    title: str = "Notes",
) -> Callable[[Member], Contribution]:
    """A factory the caller puts in its own allowlist. Wiring stays the caller's.

    ``member.settings`` is honoured here — ``{"seed": ["..."]}`` preloads the
    store on startup — which is how a document configures a capability without
    naming any code.
    """

    def build(member: Member) -> Contribution:
        seed: Sequence[str] = tuple(
            str(item) for item in member.settings.get("seed", ()))

        def startup() -> None:
            store.open()
            for text in seed:
                store.add(text)

        def list_notes(_: Request) -> Response:
            return _json({"notes": list(store.all())})

        def add_note(request: Request) -> Response:
            try:
                payload: Mapping[str, Any] = json.loads(
                    request.body.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return _json({"error": "body is not JSON"}, status=400)
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                return _json({"error": "text is required"}, status=400)
            return _json({"id": store.add(text)}, status=201)

        def read_note(request: Request) -> Response:
            raw = request.params["note_id"]
            if not raw.isdigit():
                return _json({"error": f"{raw!r} is not a note id"}, status=400)
            try:
                return _json({"text": store.get(int(raw))})
            except IndexError:
                return _json({"error": "no such note"}, status=404)

        return Contribution(
            routes=(
                Route("GET", "/api/notes", list_notes),
                Route("POST", "/api/notes", add_note),
                Route("GET", "/api/notes/{note_id}", read_note),
            ),
            assets=(Asset("/assets/shared.css", SHARED_STYLESHEET, "text/css"),),
            startup=startup,
            shutdown=store.close,
            metadata={"title": title},
        )

    return build
