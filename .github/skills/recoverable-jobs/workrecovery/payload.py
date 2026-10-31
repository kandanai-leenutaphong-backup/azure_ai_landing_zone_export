"""What a payload is, exactly, and how it becomes bytes that hash stably.

TWO SHAPES, DEFINED RATHER THAN IMPLIED
---------------------------------------
A payload is either:

1. **bytes** (``bytes`` or ``bytearray``) — preserved verbatim, content type
   ``application/octet-stream``; or
2. a **JSON value** built only from ``dict`` with ``str`` keys, ``list``,
   ``str``, ``int``, ``float``, ``bool`` and ``None`` — serialised
   canonically, content type ``application/json``.

Anything else is refused by name. Tuples and sets are the common surprise:
``json`` serialises a tuple as an array, which decodes back as a list, so a
round trip would not return what was put in. A recovery mechanism whose output
differs from its input is not one. See GOTCHAS.md, G2.

WHY CANONICAL JSON
------------------
The digest is the identity of the output. If the same value can serialise two
ways — key order, float formatting, whitespace, escaping — then two identical
outputs get two digests and a correct read-back is reported as a mismatch.
``sort_keys=True``, no whitespace, no ASCII escaping, and ``NaN``/``Infinity``
refused because they are not JSON and do not survive most stores.

WHAT IS NOT HASHED
------------------
The *source*. The digest covers the completed output bytes and nothing else.
An input hash and an item count answer "did we process the same thing", which
is a different question from "is the thing in the store the thing we produced".
See GOTCHAS.md, G8.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from workrecovery.errors import PayloadNotSupported

JSON_CONTENT_TYPE = "application/json"
BYTES_CONTENT_TYPE = "application/octet-stream"

_MAX_DEPTH = 64


def _check_json(value: Any, *, path: str = "payload", depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise PayloadNotSupported(
            f"{path}: nested more than {_MAX_DEPTH} levels deep; flatten it or "
            "pass bytes instead"
        )
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise PayloadNotSupported(
                f"{path}: NaN and Infinity are not JSON and do not survive a round trip"
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PayloadNotSupported(
                    f"{path}: object keys must be strings, got {type(key).__name__}"
                )
            _check_json(item, path=f"{path}[{key!r}]", depth=depth + 1)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_json(item, path=f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, tuple):
        raise PayloadNotSupported(
            f"{path}: a tuple serialises as an array and decodes as a list, so the "
            "recovered payload would not equal the original — convert it to a list "
            "yourself, deliberately"
        )
    raise PayloadNotSupported(
        f"{path}: {type(value).__name__} is not a JSON value and is not bytes; "
        "serialise it yourself and pass bytes, or convert it to plain JSON types"
    )


def encode_payload(payload: Any) -> tuple[bytes, str]:
    """Return ``(content, content_type)`` for one completed output.

    Raises:
        PayloadNotSupported: for anything that is neither bytes nor a JSON
            value made of the exact types listed in this module's docstring.
    """
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload), BYTES_CONTENT_TYPE
    _check_json(payload)
    text = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8"), JSON_CONTENT_TYPE


def decode_payload(content: bytes, content_type: str) -> Any:
    """Turn stored bytes back into the payload that produced them."""
    if content_type == BYTES_CONTENT_TYPE:
        return content
    if content_type == JSON_CONTENT_TYPE:
        try:
            return json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PayloadNotSupported(
                f"the stored content is not valid {JSON_CONTENT_TYPE}"
            ) from exc
    raise PayloadNotSupported(f"unknown content type {content_type!r}")


def digest(content: bytes) -> str:
    """The sha256 hex digest of the output bytes. The identity of the output."""
    return hashlib.sha256(content).hexdigest()


__all__ = [
    "BYTES_CONTENT_TYPE",
    "JSON_CONTENT_TYPE",
    "decode_payload",
    "digest",
    "encode_payload",
]
