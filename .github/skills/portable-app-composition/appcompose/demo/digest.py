"""The consumer capability: a digest over notes it never learns the source of.

It takes a ``read`` callable and nothing else. It does not import
:mod:`appcompose.demo.notes`, so the only thing binding the two together is the
document's ``requires`` edge and the caller's own wiring — which is exactly the
coupling this skill is willing to have.

Its startup reads through that callable, so composing it *before* its provider
raises rather than silently producing an empty digest. That is deliberate: a
dependency order that only matters sometimes is a dependency order nobody
maintains.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from appcompose.compose import Asset, Contribution, Request, Response, Route
from appcompose.document import Member

__all__ = ["digest_capability"]

_SHARED_STYLESHEET = b"body{font-family:system-ui;margin:2rem}\n"


def digest_capability(
    read: Callable[[], Sequence[str]],
    *,
    title: str = "Digest",
    events: list[str] | None = None,
) -> Callable[[Member], Contribution]:
    """A factory over any zero-argument reader. ``events`` records lifecycle order."""
    log = events if events is not None else []

    def build(member: Member) -> Contribution:
        limit = member.settings.get("limit", 3)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError(
                f"members[{member.id}].settings.limit must be a positive "
                f"integer, found {limit!r}")

        def startup() -> None:
            read()  # raises if the provider has not started; that is the test
            log.append(f"{member.id}:startup")

        def shutdown() -> None:
            log.append(f"{member.id}:shutdown")

        def digest(_: Request) -> Response:
            items = list(read())
            payload: dict[str, Any] = {
                "count": len(items),
                "head": items[:limit],
            }
            return Response(status=200,
                            body=json.dumps(payload, sort_keys=True).encode("utf-8"),
                            media_type="application/json")

        return Contribution(
            routes=(Route("GET", "/api/digest", digest),),
            assets=(Asset("/assets/shared.css", _SHARED_STYLESHEET, "text/css"),),
            startup=startup,
            shutdown=shutdown,
            metadata={"title": title},
        )

    return build
