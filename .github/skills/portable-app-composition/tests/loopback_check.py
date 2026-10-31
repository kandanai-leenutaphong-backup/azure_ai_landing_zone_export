#!/usr/bin/env python3
"""loopback_check.py — the framing rules, read off a real socket.

    python3 tests/loopback_check.py

``tests/selftest.py`` drives the adapter at the ASGI message layer, which is
the contract and is where every framing rule is asserted. It cannot catch one
class of mistake: a header pair that a *server* rejects or rewrites. h11 has its
own opinion about ``Content-Length`` on a ``HEAD``, a ``204`` and a ``304``, and
"the adapter emitted the right messages" is not the same claim as "a client read
the right bytes".

So this runs the composition under uvicorn on an ephemeral loopback port, speaks
HTTP/1.1 with a socket, and asserts on the response bytes. The server is started
and stopped inside one function; nothing is left listening.

It is **not** part of the box's dependency surface. uvicorn is imported inside
the function, and the script says so and exits non-zero if it is missing rather
than passing quietly:

    python3 -m pip install '.[dev]'      # from the box directory
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from appcompose import (  # noqa: E402
    Asset,
    Contribution,
    Request,
    Response,
    Route,
    allowlist,
    asgi_app,
    compose,
    parse,
)

DOCUMENT = {
    "schemaVersion": 1,
    "kind": "portable.app-composition",
    "name": "Loopback",
    "members": [{"id": "wire", "capability": "demo.wire"}],
}


def build(_member) -> Contribution:
    return Contribution(
        routes=(
            Route("GET", "/text", lambda r: Response(body=b"hello")),
            Route("GET", "/empty", lambda r: Response(status=204)),
            Route("GET", "/cached", lambda r: Response(status=304)),
            Route("GET", "/declared",
                  lambda r: Response(body=b"twelve bytes",
                                     headers={"Content-Length": "12"})),
        ),
        assets=(Asset("/a.css", b"body{}\n", "text/css"),),
    )


def request(port: int, raw: bytes) -> bytes:
    """One request, one connection, read to EOF. No client library involved."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(raw)
        chunks = []
        while True:
            piece = sock.recv(65536)
            if not piece:
                break
            chunks.append(piece)
    return b"".join(chunks)


def split(raw: bytes) -> tuple[bytes, dict[str, str], bytes]:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        headers.setdefault(name.decode("latin-1").lower(),
                           value.decode("latin-1").strip())
    return lines[0], headers, body


def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print("SKIPPED-NOT-RUN: uvicorn is not installed, so no server protocol "
              "was exercised. Install it with: python3 -m pip install '.[dev]'")
        return 2

    composition = compose(parse(DOCUMENT),
                          resolve=allowlist({"demo.wire": build}))
    server = uvicorn.Server(uvicorn.Config(
        asgi_app(composition), host="127.0.0.1", port=0, log_level="error",
        lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        print("FAIL  server did not start within 20s")
        return 1
    port = server.servers[0].sockets[0].getsockname()[1]

    failures = 0
    try:
        for name, method, path, check in CASES:
            raw = request(port, f"{method} {path} HTTP/1.1\r\nHost: loopback\r\n"
                                f"Connection: close\r\n\r\n".encode("latin-1"))
            status, headers, body = split(raw)
            try:
                check(status, headers, body, raw)
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}\n      {raw!r}")
            else:
                print(f"ok    {name}")
    finally:
        server.should_exit = True
        thread.join(timeout=20)
        if thread.is_alive():
            print("FAIL  server thread did not exit")
            failures += 1

    print(f"{len(CASES) - failures}/{len(CASES)} loopback checks passed "
          f"(uvicorn {uvicorn.__version__})")
    return 1 if failures else 0


def _get_text(status, headers, body, raw):
    assert status == b"HTTP/1.1 200 OK", status
    assert headers["content-length"] == "5", headers
    assert body == b"hello", body
    assert framing_fields(raw) == 1, raw


def _head_text(status, headers, body, raw):
    # The one the message-layer test cannot prove: h11 accepts a HEAD carrying
    # the length GET would have sent, and sends no body with it.
    assert status == b"HTTP/1.1 200 OK", status
    assert headers["content-length"] == "5", headers
    assert body == b"", body
    assert framing_fields(raw) == 1, raw


def _declared(status, headers, body, raw):
    assert headers["content-length"] == "12", headers
    assert body == b"twelve bytes", body
    # A handler that states an agreeing length must not produce two fields.
    assert framing_fields(raw) == 1, raw


def _no_content(status, headers, body, raw):
    assert status == b"HTTP/1.1 204 No Content", status
    assert "content-length" not in headers, headers
    assert "transfer-encoding" not in headers, headers
    assert body == b"", body


def _not_modified(status, headers, body, raw):
    assert status == b"HTTP/1.1 304 Not Modified", status
    assert "content-length" not in headers, headers
    assert body == b"", body


def _asset(status, headers, body, raw):
    assert status == b"HTTP/1.1 200 OK", status
    assert headers["content-length"] == "7" and body == b"body{}\n", (headers, body)


def _missing(status, headers, body, raw):
    assert status.startswith(b"HTTP/1.1 404"), status
    assert headers["content-length"] == str(len(body)), (headers, body)


def framing_fields(raw: bytes) -> int:
    """How many message-length statements the server actually put on the wire."""
    head = raw.partition(b"\r\n\r\n")[0].lower()
    return sum(line.split(b":")[0].strip() in (b"content-length",
                                               b"transfer-encoding")
               for line in head.split(b"\r\n")[1:])


CASES = [
    ("GET carries the measured length", "GET", "/text", _get_text),
    ("HEAD carries what GET would send, and no body", "HEAD", "/text", _head_text),
    ("a handler-declared length that agrees is sent once", "GET", "/declared",
     _declared),
    ("204 is framed with no length and no body", "GET", "/empty", _no_content),
    ("304 is framed with no length and no body", "GET", "/cached", _not_modified),
    ("an asset states its own bytes", "GET", "/a.css", _asset),
    ("a refusal is framed like any other response", "GET", "/nope", _missing),
]


if __name__ == "__main__":
    raise SystemExit(main())
