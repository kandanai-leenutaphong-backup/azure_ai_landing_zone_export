"""A minimal ASGI adapter, so a composition is a real HTTP application.

WHY IT IS HERE AND NOT IN THE COMPOSER
--------------------------------------
:mod:`appcompose.compose` knows nothing about HTTP servers, and that is the
point: a capability written against :class:`~appcompose.compose.Contribution`
is not written against a web framework. This module is the thin translation
of one wire protocol into that neutral shape — stdlib only, and entirely
optional. Delete it and the skill still composes.

WHAT IT COVERS
--------------
The ``lifespan`` protocol, mapped onto :meth:`Composition.startup` and
:meth:`Composition.shutdown`, and the ``http`` protocol, mapped onto
:meth:`Composition.dispatch`. A startup failure is reported back through
``lifespan.startup.failed`` with the composer's message, which is what makes an
orchestrator stop the rollout instead of routing traffic at a half-built app.

THE ADAPTER OWNS THE WIRE, THE HANDLER OWNS THE MEANING
-------------------------------------------------------
A ``Response`` is in-process data; only a transport knows what may legally go
on the wire. So this module, and not ``dispatch``, is where request bodies are
capped, response shape is checked, header names and values are validated,
hop-by-hop fields are refused, ``Content-Length`` is *measured*, and ``HEAD`` is
guaranteed to carry no body. A handler is trusted to decide *what* to answer,
and never trusted to frame it — a ``Content-Length`` it supplies is checked
against the bytes and refused when it disagrees, because a framing claim that
is merely well-formed is not a framing claim that is true.

WHAT THE HOST STILL OWES
------------------------
TLS, authentication and authorisation, cache-control policy, request-path
normalisation before ``path`` reaches here, concurrency limits, timeouts and
access logging. The list is written out in ``CONTRACT.md`` §5.1. Websockets,
streaming request bodies and server-sent events are out of scope.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, MutableMapping

from appcompose.compose import Composition, Response
from appcompose.errors import ResponseInvalid

__all__ = ["DEFAULT_MAX_REQUEST_BYTES", "asgi_app"]

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

#: How many request bytes this adapter accumulates before answering 413.
#: Finite by default: an unbounded buffer is one client away from the process.
DEFAULT_MAX_REQUEST_BYTES = 1_048_576

#: RFC 9110 token characters. A header name outside this set cannot be framed.
_TOKEN = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")

#: Header fields the adapter settles itself; a handler may not also send them.
_ADAPTER_OWNED = ("content-type",)

#: Connection-scoped fields (RFC 9110 §7.6.1) plus the transfer coding. The
#: server owns every one of them, and a handler that also sends one produces
#: two disagreeing statements about how the message is framed — which is the
#: shape of request smuggling, not a merge.
_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
})


def asgi_app(
    composition: Composition,
    *,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
    """Wrap a composition as an ASGI 3 application.

    ``max_request_bytes`` caps the buffered request body, whether the length was
    declared in a header or streamed without one. It must be a positive integer;
    anything else is refused at construction rather than at the first large
    request, and there is deliberately no unbounded setting.
    """
    limit = _checked_limit(max_request_bytes)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await _lifespan(composition, receive, send)
            return
        if scope["type"] != "http":
            raise NotImplementedError(
                f"{scope['type']!r} is not handled; this adapter serves http "
                f"and lifespan only")
        await _http(composition, scope, receive, send, limit)

    return app


def _checked_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"max_request_bytes must be a positive integer, found "
            f"{type(value).__name__}. A body with no ceiling is the whole "
            f"process, so there is no unbounded setting")
    if value <= 0:
        raise ValueError(f"max_request_bytes must be positive, found {value}")
    return value


async def _lifespan(composition: Composition, receive: Receive,
                    send: Send) -> None:
    while True:
        message = await receive()
        if message.get("type") == "lifespan.startup":
            try:
                composition.startup()
            except Exception as exc:  # noqa: BLE001 - the protocol wants the text
                # Terminal: the server stops rather than routing traffic at a
                # half-built application, so this coroutine stops too.
                await send({"type": "lifespan.startup.failed",
                            "message": str(exc)})
                return
            await send({"type": "lifespan.startup.complete"})
        elif message.get("type") == "lifespan.shutdown":
            try:
                composition.shutdown()
            except Exception as exc:  # noqa: BLE001 - the protocol wants the text
                await send({"type": "lifespan.shutdown.failed",
                            "message": str(exc)})
            else:
                await send({"type": "lifespan.shutdown.complete"})
            return


async def _http(composition: Composition, scope: Scope, receive: Receive,
                send: Send, limit: int) -> None:
    method = str(scope.get("method", "GET")).upper()
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }

    declared = _declared_length(headers)
    if declared is not None and declared > limit:
        await _send(send, method, _refusal(413, limit))
        return

    chunks: list[bytes] = []
    total = 0
    more = True
    while more:
        message = await receive()
        kind = message.get("type")
        if kind == "http.disconnect":
            # The client is gone: nothing is dispatched and nothing is sent.
            # Sending after a disconnect is what turns a cancelled request into
            # an exception in the server's log.
            return
        if kind != "http.request":
            await _send(send, method, _refusal(
                400, limit, f"unexpected ASGI message {kind!r}"))
            return
        chunk = message.get("body", b"") or b""
        if not isinstance(chunk, (bytes, bytearray)):
            await _send(send, method, _refusal(
                400, limit, f"body chunk is {type(chunk).__name__}, not bytes"))
            return
        total += len(chunk)
        if total > limit:
            # Refused before dispatch. Accounting is on the running total, so a
            # large body costs one pass rather than one copy per chunk.
            await _send(send, method, _refusal(413, limit))
            return
        chunks.append(bytes(chunk))
        more = bool(message.get("more_body", False))

    response = composition.dispatch(
        method, scope["path"], headers=headers, body=b"".join(chunks),
        elide_head=False)
    await _send(send, method, response)


def _declared_length(headers: MutableMapping[str, str]) -> int | None:
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _refusal(status: int, limit: int, detail: str = "") -> Response:
    text = detail or (f"request body exceeds {limit} bytes"
                      if status == 413 else "bad request")
    return Response(status=status, body=text.encode("utf-8"))


async def _send(send: Send, method: str, response: Response) -> None:
    _checked_response(response)
    # Measured, here, from the bytes themselves — and measured *before* HEAD
    # drops them, which is the only reason the adapter asks dispatch not to
    # elide. A length recovered from a header the handler wrote is the handler
    # framing the message.
    length = len(response.body)
    raw = _wire_headers(response, length)
    await send({"type": "http.response.start", "status": response.status,
                "headers": raw})
    # A HEAD response carries no body whatever the handler returned, and the
    # Content-Length above still states what GET would have sent.
    body = b"" if method == "HEAD" else response.body
    await send({"type": "http.response.body", "body": body})


def _bodyless(status: int) -> bool:
    """Statuses RFC 9110 gives no body at all: informational, 204, 304."""
    return status < 200 or status in (204, 304)


def _checked_response(response: Response) -> None:
    """Refuse a response whose *shape* cannot become an HTTP message.

    ``Response`` is a plain dataclass with no validation, on purpose: it is
    in-process data and a composer that policed it would be policing meaning.
    The wire is where the shape has to be true, so it is checked once, here,
    before any of it is encoded.
    """
    status = response.status
    if isinstance(status, bool) or not isinstance(status, int):
        raise ResponseInvalid(
            "status",
            f"is {type(status).__name__}, not an int. A status is a number on "
            f"the wire; True is not 200")
    if not 100 <= status <= 599:
        raise ResponseInvalid(
            "status", f"{status} is outside 100-599 and has no HTTP meaning")
    if not isinstance(response.body, bytes):
        raise ResponseInvalid(
            "body",
            f"is {type(response.body).__name__}, not bytes. The wire is bytes; "
            f"encode it in the handler, where the encoding is known")
    if _bodyless(status) and response.body:
        raise ResponseInvalid(
            "body",
            f"a {status} response carries no body, and this one carries "
            f"{len(response.body)} bytes. A server that honours the status "
            f"drops them; one that honours the bytes desynchronises the "
            f"connection")


def _wire_headers(response: Response,
                  length: int) -> list[tuple[bytes, bytes]]:
    """Validate and normalise every header, or refuse to put it on the wire.

    Lowercased because ASGI says so and no server is required to fix it;
    de-duplicated because two ``content-length`` fields are request smuggling
    written down; CRLF-refused because a header value carrying one *is*
    response splitting, and the classic source is a handler echoing a request
    value it never validated.

    ``content-length`` is settled from ``length``, which was measured from the
    body. A handler may still state it — an asset route does — but only as a
    claim that is checked: a value disagreeing with the bytes is refused, never
    honoured, because the handler owns the meaning and the adapter owns the
    framing.
    """
    media_type = _checked_value("media_type", response.media_type)
    raw: list[tuple[bytes, bytes]] = [(b"content-type",
                                       media_type.encode("latin-1"))]
    seen = {"content-type"}
    for key, value in response.headers.items():
        name = _checked_name(key)
        text = _checked_value(f"headers[{key!r}]", value)
        if name in _ADAPTER_OWNED:
            raise ResponseInvalid(
                f"headers[{key!r}]",
                f"{name!r} is set by the adapter from media_type; sending it "
                f"twice leaves the framing ambiguous")
        if name in _HOP_BY_HOP:
            raise ResponseInvalid(
                f"headers[{key!r}]",
                f"{name!r} is connection-scoped and belongs to the server, not "
                f"to a handler. Sent alongside content-length it makes the "
                f"message length ambiguous, and this adapter never streams")
        if name in seen:
            raise ResponseInvalid(
                f"headers[{key!r}]",
                f"{name!r} is sent twice; a repeated field is a framing "
                f"ambiguity, not a merge")
        seen.add(name)
        if name == "content-length":
            _check_declared_length(key, text, response.status, length)
            continue
        raw.append((name.encode("latin-1"), text.encode("latin-1")))
    if not _bodyless(response.status):
        raw.append((b"content-length", str(length).encode("latin-1")))
    return raw


def _check_declared_length(key: Any, text: str, status: int,
                           length: int) -> None:
    if _bodyless(status):
        raise ResponseInvalid(
            f"headers[{key!r}]",
            f"a {status} response is framed as having no body, so it states no "
            f"content-length; the adapter omits the field rather than sending "
            f"one a server would have to overrule")
    if not text.strip().isdigit():
        raise ResponseInvalid(
            f"headers[{key!r}]", f"content-length {text!r} is not a number")
    if int(text.strip()) != length:
        raise ResponseInvalid(
            f"headers[{key!r}]",
            f"content-length says {text.strip()} and the body is {length} "
            f"bytes. The adapter frames the response from the bytes, so a "
            f"disagreeing value is refused rather than believed: a client that "
            f"trusts it either truncates the body or waits for bytes nobody "
            f"will send")


def _checked_name(key: Any) -> str:
    if not isinstance(key, str) or not _TOKEN.match(key):
        raise ResponseInvalid(
            f"headers[{key!r}]",
            "is not a header name; RFC 9110 tokens only, and a name carrying "
            "a colon, a space or a newline cannot be framed at all")
    return key.lower()


def _checked_value(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ResponseInvalid(
            field,
            f"is {type(value).__name__}, not a str. Coercing it here would "
            f"decide an encoding on the handler's behalf, and a repr is not a "
            f"header value")
    text = value
    for char in text:
        code = ord(char)
        if code < 0x20 or code == 0x7F:
            raise ResponseInvalid(
                field,
                f"contains the control character U+{code:04X}. A CR or LF in a "
                f"header value is response splitting; it is refused here rather "
                f"than forwarded for a server to notice")
        if code > 0xFF:
            raise ResponseInvalid(
                field,
                f"contains U+{code:04X}, which has no latin-1 encoding. Header "
                f"values are bytes on the wire; encode it before returning it")
    return text
