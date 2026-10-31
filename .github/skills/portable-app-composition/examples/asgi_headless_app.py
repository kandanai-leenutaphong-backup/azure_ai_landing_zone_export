#!/usr/bin/env python3
"""Worked example: the same composition as a real ASGI application, offline.

Run it:

    python3 examples/asgi_headless_app.py

There is no server and no network here on purpose — the ASGI protocol is a pair
of coroutines and a dict, so the whole contract can be driven directly and its
actual bytes asserted. Mount the same object under uvicorn or hypercorn and the
messages below are the messages the server sends.

It asserts the halves an adapter usually gets wrong: the ``lifespan`` protocol,
including what a *failed* startup reports back; the ``http`` protocol's status,
headers and body; ``HEAD`` served by a ``GET`` route with no body and a truthful
``Content-Length``; a request body refused with ``413`` before any handler sees
it; a client disconnect that sends nothing at all; and a header value carrying
CRLF, which is refused rather than framed.
"""

from __future__ import annotations

import asyncio
import json

from appcompose import (  # noqa: E402
    Contribution,
    Response,
    Route,
    allowlist,
    asgi_app,
    compose,
    from_yaml,
)
from appcompose.errors import ResponseInvalid  # noqa: E402
from appcompose.demo.digest import digest_capability  # noqa: E402
from appcompose.demo.notes import NoteStore, notes_capability  # noqa: E402

DOCUMENT = """
schemaVersion: 1
kind: portable.app-composition
name: Headless field notes
members:
  - id: store
    capability: notes.store
    settings:
      seed: [alpha, beta]
  - id: digest
    capability: notes.digest
    requires: [store]
ownership:
  /assets/shared.css: store
"""


class Wire:
    """One request's worth of ASGI messages, recorded rather than sent."""

    def __init__(self, incoming: list[dict]) -> None:
        self._incoming = list(incoming)
        self.sent: list[dict] = []

    async def receive(self) -> dict:
        return self._incoming.pop(0)

    async def send(self, message: dict) -> None:
        self.sent.append(message)


class LifespanSession:
    """The lifespan coroutine a server keeps alive for the process's whole life."""

    def __init__(self, app) -> None:
        self._app = app
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._replies: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def _receive(self) -> dict:
        return await self._inbox.get()

    async def _send(self, message: dict) -> None:
        await self._replies.put(message)

    async def start(self) -> dict:
        self._task = asyncio.create_task(
            self._app({"type": "lifespan"}, self._receive, self._send))
        await self._inbox.put({"type": "lifespan.startup"})
        reply = await self._replies.get()
        if reply["type"] != "lifespan.startup.complete":
            await self._task  # a failed startup ends the lifespan coroutine
            self._task = None
        return reply

    async def stop(self) -> dict:
        await self._inbox.put({"type": "lifespan.shutdown"})
        reply = await self._replies.get()
        assert self._task is not None
        await self._task
        self._task = None
        return reply


async def request(app, method: str, path: str, body: bytes = b"",
                  chunks: list[dict] | None = None) -> tuple[int, dict, bytes]:
    incoming = chunks if chunks is not None else [
        {"type": "http.request", "body": body, "more_body": False}]
    wire = Wire(incoming)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "method": method,
             "path": path, "headers": [(b"accept", b"application/json")]}
    await app(scope, wire.receive, wire.send)
    if not wire.sent:
        return 0, {}, b""
    start, chunk = wire.sent[0], wire.sent[1]
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    return start["status"], headers, chunk["body"]


async def main() -> int:
    store = NoteStore()
    document = from_yaml(DOCUMENT)
    composition = compose(document, resolve=allowlist({
        "notes.store": notes_capability(store),
        "notes.digest": digest_capability(store.all),
    }))
    app = asgi_app(composition, max_request_bytes=4096)

    # Lifespan startup, then real requests.
    session = LifespanSession(app)
    started = await session.start()
    assert started == {"type": "lifespan.startup.complete"}, started
    assert composition.readiness() == (True, "")

    status, headers, body = await request(app, "GET", "/api/notes")
    assert status == 200, status
    assert headers["content-type"] == "application/json", headers
    assert json.loads(body) == {"notes": ["alpha", "beta"]}, body

    status, _, body = await request(
        app, "POST", "/api/notes", json.dumps({"text": "gamma"}).encode())
    assert status == 201 and json.loads(body) == {"id": 2}

    status, _, body = await request(app, "GET", "/api/digest")
    assert json.loads(body) == {"count": 3, "head": ["alpha", "beta", "gamma"]}

    status, headers, body = await request(app, "GET", "/assets/shared.css")
    assert status == 200 and headers["content-type"] == "text/css"
    assert headers["content-length"] == str(len(body)), headers

    status, _, body = await request(app, "GET", "/api/missing")
    assert status == 404, status
    assert b"no route" in body

    status, headers, _ = await request(app, "PUT", "/api/notes")
    assert status == 405 and headers["allow"] == "GET, HEAD, POST", headers

    # HEAD is served by the GET route: no body on the wire, and a
    # Content-Length stating what GET would have sent.
    get_status, _, get_body = await request(app, "GET", "/api/notes")
    status, headers, body = await request(app, "HEAD", "/api/notes")
    assert status == get_status == 200 and body == b"", (status, body)
    assert headers["content-length"] == str(len(get_body)), headers

    # A HEAD that misses still carries no body, whatever the status.
    status, headers, body = await request(app, "HEAD", "/api/missing")
    assert status == 404 and body == b"" and int(headers["content-length"]) > 0

    # A body over the cap is refused before any handler runs, streamed or not.
    oversize = [{"type": "http.request", "body": b"x" * 1024, "more_body": True}
                for _ in range(8)]
    oversize.append({"type": "http.request", "body": b"", "more_body": False})
    status, _, body = await request(app, "POST", "/api/notes", chunks=oversize)
    assert status == 413, status
    assert json.loads((await request(app, "GET", "/api/digest"))[2])[
        "count"] == 3          # the refused body never reached the store

    # A client that goes away mid-body gets nothing sent to it at all.
    status, _, _ = await request(app, "POST", "/api/notes", chunks=[
        {"type": "http.request", "body": b"partial", "more_body": True},
        {"type": "http.disconnect"}])
    assert status == 0, "a disconnected client must not be sent a response"

    stopped = await session.stop()
    assert stopped == {"type": "lifespan.shutdown.complete"}, stopped
    assert store.closed is True

    # Once shutdown has run, the adapter serves 503 rather than routing at
    # resources the shutdown hooks already released.
    status, _, _ = await request(app, "GET", "/api/notes")
    assert status == 503, status

    # A failed startup is reported through the protocol, not raised into the
    # server. This is the message an orchestrator reads before routing traffic.
    def explode() -> None:
        raise RuntimeError("upstream is unreachable")

    broken = compose(
        from_yaml("schemaVersion: 1\nkind: portable.app-composition\n"
                  "name: Broken\nmembers:\n  - id: only\n    capability: x.y\n"),
        resolve=allowlist({"x.y": lambda member: Contribution(startup=explode)}),
    )
    failed = await LifespanSession(asgi_app(broken)).start()
    assert failed["type"] == "lifespan.startup.failed", failed
    assert "upstream is unreachable" in failed["message"], failed
    assert broken.readiness()[0] is False

    # A header value carrying CRLF is response splitting. The adapter refuses
    # to frame it; the handler is trusted for meaning, never for framing.
    def splitter(_):
        return Response(body=b"x", headers={"X-Note": "ok\r\nX-Injected: yes"})

    splitting = compose(
        from_yaml("schemaVersion: 1\nkind: portable.app-composition\n"
                  "name: Splitting\nmembers:\n  - id: only\n    capability: x.y\n"),
        resolve=allowlist({"x.y": lambda member: Contribution(
            routes=(Route("GET", "/x", splitter),))}),
    )
    splitting.startup()
    try:
        await request(asgi_app(splitting), "GET", "/x")
    except ResponseInvalid as exc:
        assert "U+000D" in str(exc), exc
    else:
        raise AssertionError("a CRLF header value reached the wire")
    splitting.shutdown()

    print("ASGI lifespan, http, HEAD, limits and header framing verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
