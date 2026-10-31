"""The composer: one document in, one running application out.

THE ADOPTION BOUNDARY
---------------------
:func:`compose` is the only function a consumer has to call. It takes a
validated :class:`~appcompose.document.Document` and a ``resolve`` callable the
caller owns, and returns a :class:`Composition`.

THE COMPOSITION IS A PROJECTION, NOT A SECOND SOURCE OF TRUTH
-------------------------------------------------------------
Everything a composition knows — which members exist, in what order they start,
where a shell should place them, who owns a contested asset — is read from the
document it was built from, and the document it was built from is kept on the
composition. There is no second file to edit and no way to add a member without
editing the document, so the two cannot drift apart.

THE RESOLVER IS THE ALLOWLIST
-----------------------------
A document names capabilities. It never names code, and nothing here imports
anything: ``resolve(capability, member)`` is the caller's own mapping from a
capability identifier to an implementation, and a capability the caller did not
put in that mapping is a named refusal. That is the whole security posture of
loading a document somebody else wrote, and it is why there is no ``module:
attribute`` string anywhere in this skill.

AUTHORIZATION IS THE CALLER'S, BEFORE DISPATCH
----------------------------------------------
:meth:`Composition.dispatch` authenticates nobody and authorises nothing. It is
a router. A caller with a trust boundary checks it *before* calling dispatch and
keeps owning it; a composition that silently authorised requests would be a
second, invisible policy. Layout slots are metadata for a shell, not isolation,
and this skill never claims otherwise.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping, Sequence

from appcompose.document import Document, Member, Placement, asset_path_error
from appcompose.errors import (
    AssetConflict,
    CapabilityFactoryFailed,
    CapabilityNotAllowed,
    CompositionError,
    PartialStartup,
    RouteConflict,
    ShutdownFailed,
    StartupFailed,
    UnknownMetadata,
)

__all__ = [
    "Asset",
    "ComposedMember",
    "Composition",
    "Contribution",
    "METADATA_KEYS",
    "METHODS",
    "MAX_ROUTE_PARAMS",
    "Request",
    "Response",
    "Route",
    "allowlist",
    "compose",
    "route_template_error",
]

#: Methods a route may declare. A closed set, because a typo'd method silently
#: routes nothing and that is a hard afternoon.
METHODS: tuple[str, ...] = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE",
                            "OPTIONS")

#: Contribution metadata this composition understands. Anything else is a
#: refusal rather than a value quietly ignored: an ignored key looks exactly
#: like a working one until somebody looks for its effect.
METADATA_KEYS: tuple[str, ...] = ("title", "description")

#: How many parameters one route template may declare. A template is a routing
#: rule, not a query language.
MAX_ROUTE_PARAMS = 16

_PARAM = re.compile(r"\{[^/{}]+\}")
_PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


# ----------------------------------------------------------------------
# What a capability hands back.
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Request:
    """One inbound request, already authorised by whoever owns that decision."""

    method: str
    path: str
    params: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class Response:
    """One outbound response. ``body`` is bytes because the wire is bytes."""

    status: int = 200
    body: bytes = b""
    media_type: str = "text/plain; charset=utf-8"
    headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class Route:
    """One handler, at one method and path template. ``{name}`` marks a parameter."""

    method: str
    path: str
    handler: Callable[[Request], Response]


@dataclass(frozen=True, slots=True)
class Asset:
    """One static byte string at one path, owned by exactly one member."""

    path: str
    body: bytes
    media_type: str = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class Contribution:
    """What one capability contributes: routes, assets, and a lifecycle.

    Neutral by construction — no framework type appears in it, so a capability
    written for this skill is not written for a web framework.
    """

    routes: tuple[Route, ...] = ()
    assets: tuple[Asset, ...] = ()
    startup: Callable[[], None | Awaitable[None]] | None = None
    shutdown: Callable[[], None | Awaitable[None]] | None = None
    metadata: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class ComposedMember:
    """One member as composed: its identity, its placement, its contribution."""

    id: str
    capability: str
    placement: Placement
    contribution: Contribution

    @property
    def title(self) -> str:
        return str(self.contribution.metadata.get("title", "") or "")


# ----------------------------------------------------------------------
# Resolvers.
# ----------------------------------------------------------------------


def allowlist(
    mapping: Mapping[str, Callable[[Member], Contribution]],
) -> Callable[[str, Member], Contribution | None]:
    """A resolver from a literal ``{capability: factory}`` mapping.

    The convenience form of the rule: what is in the mapping can be composed,
    what is not cannot. Nothing is looked up by name at import time.

    Lookup and construction are kept apart. A ``KeyError`` raised *inside* an
    allowed factory — a missing settings key, most often — is re-raised as
    :class:`~appcompose.errors.CapabilityFactoryFailed`, so it can never be
    mistaken for the allowlist refusing the capability.
    """
    frozen = dict(mapping)

    def resolve(capability: str, member: Member) -> Contribution | None:
        factory = frozen.get(capability)
        if factory is None:
            return None
        try:
            return factory(member)
        except (KeyError, LookupError) as exc:
            raise CapabilityFactoryFailed(member.id, capability, exc) from exc

    return resolve


# ----------------------------------------------------------------------
# The composition.
# ----------------------------------------------------------------------


class Composition:
    """An assembled application. Built by :func:`compose`; never constructed directly."""

    def __init__(self, document: Document, members: tuple[ComposedMember, ...],
                 routes: tuple[tuple[str, str, str, Callable[[Request], Response]], ...],
                 assets: Mapping[str, tuple[str, Asset]]) -> None:
        self.document = document
        self.members = members
        self._routes = routes
        self._assets = dict(assets)
        self._started: list[str] = []
        self._running = False
        self._shutdown_done = False
        self._unsafe: tuple[tuple[str, str], ...] = ()
        self._transitioning = False
        self._async_mode = False

    # -- introspection ------------------------------------------------

    @property
    def member_ids(self) -> tuple[str, ...]:
        return tuple(m.id for m in self.members)

    @property
    def route_table(self) -> tuple[tuple[str, str, str], ...]:
        """``(method, path template, owning member id)``, in composition order."""
        return tuple((method, path, owner) for method, path, owner, _ in self._routes)

    @property
    def asset_table(self) -> tuple[tuple[str, str], ...]:
        """``(path, owning member id)`` for every static asset."""
        return tuple(sorted((path, owner) for path, (owner, _) in self._assets.items()))

    def placement(self) -> tuple[tuple[str, Placement], ...]:
        """Member placements a shell may read, ordered by ``order`` then id.

        Projected from the document's ``layout``. A shell that ignores it is
        still a correct shell: nothing in this skill acts on a slot.
        """
        entries = [(m.id, m.placement) for m in self.members]
        return tuple(sorted(entries, key=lambda item: (item[1].order, item[0])))

    # -- health -------------------------------------------------------

    def availability(self) -> bool:
        """Is the process up, the application assembled, and its state known?

        Answers ``True`` before startup and after a clean shutdown — those are
        readiness questions, and an availability probe that only answers once
        every member has started makes a slow member look like a dead process.

        Answers ``False`` in exactly one case: a member could not be stopped,
        so it may still hold resources nobody can account for. That process
        cannot be recovered by waiting, and saying ``True`` would be a lie an
        orchestrator acts on.
        """
        return not self._unsafe

    def readiness(self) -> tuple[bool, str]:
        """Has every member started? ``(ready, reason)``; reason is empty when ready."""
        if self._unsafe:
            names = [member for member, _ in self._unsafe]
            return False, f"unsafe: stop failed for {names}"
        if not self._running:
            return False, "not started"
        pending = [m.id for m in self.members if m.id not in self._started]
        if pending:
            return False, f"members not started: {pending}"
        return True, ""

    def unsafe_state(self) -> tuple[tuple[str, str], ...]:
        """``(member id, error)`` for every member this composition could not stop.

        Three sources, one meaning: a rollback hook that raised, a
        :meth:`shutdown` hook that raised, and a startup hook that declared it
        kept resources by raising
        :class:`~appcompose.errors.PartialStartup`. Non-empty means the
        composition does not know whether those members are stopped. Nothing
        here can find out, so nothing here pretends to.
        """
        return self._unsafe

    def clear_unsafe_state(self, *, resolved: Sequence[str]) -> None:
        """Record that the named members were released by hand; re-enable startup.

        The one recovery route, and it is deliberately not a flag: the caller
        names every member it has cleaned up, and a list that does not match the
        recorded failures exactly is refused. There is no automatic retry,
        because only the operator can know whether the port was freed.
        """
        if self._transitioning:
            raise CompositionError("composition lifecycle transition in progress")
        if not self._unsafe:
            raise CompositionError(
                "clear_unsafe_state: nothing to clear; this composition is not "
                "in an unsafe state")
        pending = sorted(member for member, _ in self._unsafe)
        named = sorted(str(member) for member in resolved)
        if named != pending:
            raise CompositionError(
                f"clear_unsafe_state: resolved={named} does not match the "
                f"members this composition could not stop ({pending}). Name "
                f"every one of them, or leave the composition unsafe")
        self._unsafe = ()

    # -- lifecycle ----------------------------------------------------

    def _begin_startup(self, *, asynchronous: bool) -> None:
        if self._transitioning:
            raise CompositionError("composition lifecycle transition in progress")
        if self._unsafe:
            names = [member for member, _ in self._unsafe]
            raise CompositionError(
                f"refusing to start: this composition could not stop {names}, "
                f"so it does not know whether they are stopped. Starting again "
                f"would start them twice. Release them by hand, then call "
                f"clear_unsafe_state(resolved={names})")
        if self._running:
            raise CompositionError("already started; startup() is not re-entrant")
        self._transitioning = True
        self._async_mode = asynchronous

    def _begin_shutdown(self, *, asynchronous: bool) -> list[str] | None:
        if self._transitioning:
            raise CompositionError("composition lifecycle transition in progress")
        if self._running and self._async_mode != asynchronous:
            method = "aclose" if self._async_mode else "shutdown"
            raise CompositionError(f"active lifecycle requires {method}")
        if self._shutdown_done or not self._running:
            self._shutdown_done = True
            return None
        self._transitioning = True
        started, self._started = self._started, []
        self._running = False
        self._shutdown_done = True
        return started

    def startup(self) -> tuple[str, ...]:
        """Start every member in dependency order. Returns the order used.

        If a member raises, everything already started is shut down in reverse
        order and :class:`~appcompose.errors.StartupFailed` is raised. When
        every rollback succeeded, and the failing hook cleaned up after itself,
        the composition is left cleanly not-running and a caller may fix the
        cause and call ``startup`` again.

        Otherwise it may not. The composition latches an unsafe state, and a
        second ``startup`` is refused naming the members that would be started
        twice — see :meth:`unsafe_state` and :meth:`clear_unsafe_state`.

        ``KeyboardInterrupt`` and ``SystemExit`` are never converted into
        ``StartupFailed``. Rollback still runs and the state is still recorded,
        and then the original exception is re-raised, because a caller that
        pressed Ctrl-C must not have to catch a composition error to be
        interrupted.
        """
        self._begin_startup(asynchronous=False)
        started: list[str] = []
        try:
            for member in self.members:
                hook = member.contribution.startup
                try:
                    _run_hook(member.id, "startup", hook)
                except BaseException as exc:  # noqa: BLE001 - roll back, then re-raise
                    residue = _startup_residue(member.id, exc)
                    rolled_back, failures, interrupt = self._stop(started)
                    self._unsafe = failures + residue
                    if not isinstance(exc, Exception):
                        raise
                    if interrupt is not None:
                        raise interrupt from exc
                    raise StartupFailed(member.id, exc, rolled_back, failures,
                                        residue) from exc
                started.append(member.id)
            self._started = started
            self._running = True
            self._shutdown_done = False
            return tuple(started)
        finally:
            self._transitioning = False
            if not self._running:
                self._async_mode = False

    def _stop(self, member_ids: Sequence[str]) -> tuple[
            tuple[str, ...], tuple[tuple[str, str], ...], BaseException | None]:
        """Run every named member's shutdown hook, newest first, never stopping early.

        Returns ``(stopped, failures, interrupt)``. An interrupt is reported
        *and* recorded as a failure: the hook it happened in did not finish, so
        that member is exactly as unaccounted-for as one that raised.
        """
        by_id = {m.id: m for m in self.members}
        stopped: list[str] = []
        failures: list[tuple[str, str]] = []
        interrupt: BaseException | None = None
        for member_id in reversed(list(member_ids)):
            hook = by_id[member_id].contribution.shutdown
            try:
                _run_hook(member_id, "shutdown", hook)
            except BaseException as exc:  # noqa: BLE001 - report, never swallow
                failures.append((member_id, f"{type(exc).__name__}: {exc}"))
                if not isinstance(exc, Exception) and interrupt is None:
                    interrupt = exc
            else:
                stopped.append(member_id)
        return tuple(stopped), tuple(failures), interrupt

    def shutdown(self) -> tuple[str, ...]:
        """Shut every started member down in reverse dependency order, exactly once.

        A second call is a no-op returning ``()``; a call before ``startup`` is a
        no-op too. Every member's hook runs even if an earlier one raised, and
        the collected failures are then raised as
        :class:`~appcompose.errors.ShutdownFailed`.

        A failure here **latches the composition unsafe**, exactly as a failed
        rollback does. A member whose stop hook raised may still hold its port,
        so a later ``startup()`` would start it twice; it is refused until
        :meth:`clear_unsafe_state` says an operator released it by hand.

        ``KeyboardInterrupt`` and ``SystemExit`` raised by a hook do not stop
        the sweep and are not converted into ``ShutdownFailed``: every remaining
        hook still runs, the state is recorded, and then the original exception
        is re-raised.
        """
        started = self._begin_shutdown(asynchronous=False)
        if started is None:
            return ()
        try:
            stopped, failures, interrupt = self._stop(started)
            if failures:
                self._unsafe = failures
            if interrupt is not None:
                raise interrupt
            if failures:
                raise ShutdownFailed(failures)
            return stopped
        finally:
            self._transitioning = False
            self._async_mode = False

    def __enter__(self) -> "Composition":
        self.startup()
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        self.shutdown()
        return False

    async def astartup(self) -> tuple[str, ...]:
        """Run explicit async/sync hooks in dependency order with owned rollback."""
        self._begin_startup(asynchronous=True)
        started: list[str] = []
        try:
            for member in self.members:
                try:
                    await self._ahook(member.contribution.startup)
                except BaseException as error:
                    residue = _startup_residue(member.id, error)
                    stopped, failures, interrupt = await self._astop(started)
                    self._unsafe = failures + residue
                    if not isinstance(error, Exception):
                        raise
                    if interrupt is not None:
                        raise interrupt from None
                    raise StartupFailed(member.id, error, stopped, failures,
                                        residue) from None
                started.append(member.id)
            self._started = started
            self._running = True
            self._shutdown_done = False
            return tuple(started)
        finally:
            self._transitioning = False
            if not self._running:
                self._async_mode = False

    @staticmethod
    async def _ahook(hook: Callable[[], None | Awaitable[None]] | None) -> None:
        import asyncio
        import inspect

        if hook is None:
            return
        value = hook() if inspect.iscoroutinefunction(hook) else await asyncio.to_thread(hook)
        if inspect.isawaitable(value):
            value = await value
        if value is not None:
            raise CompositionError("lifecycle hooks must return None")

    async def _astop(self, member_ids: Sequence[str]) -> tuple[
            tuple[str, ...], tuple[tuple[str, str], ...], BaseException | None]:
        by_id = {member.id: member for member in self.members}
        stopped: list[str] = []
        failures: list[tuple[str, str]] = []
        interrupt: BaseException | None = None
        for member_id in reversed(member_ids):
            try:
                await self._ahook(by_id[member_id].contribution.shutdown)
            except BaseException as error:
                failures.append((member_id, type(error).__name__))
                if not isinstance(error, Exception) and interrupt is None:
                    interrupt = error
            else:
                stopped.append(member_id)
        return tuple(stopped), tuple(failures), interrupt

    async def aclose(self) -> tuple[str, ...]:
        started = self._begin_shutdown(asynchronous=True)
        if started is None:
            return ()
        try:
            stopped, failures, interrupt = await self._astop(started)
            if failures:
                self._unsafe = failures
            if interrupt is not None:
                raise interrupt from None
            if failures:
                raise ShutdownFailed(failures)
            return stopped
        finally:
            self._transitioning = False
            self._async_mode = False

    async def __aenter__(self) -> "Composition":
        await self.astartup()
        return self

    async def __aexit__(self, *exception: Any) -> bool:
        await self.aclose()
        return False

    # -- dispatch -----------------------------------------------------

    def dispatch(self, method: str, path: str, *,
                 headers: Mapping[str, str] | None = None,
                 body: bytes = b"",
                 elide_head: bool = True) -> Response:
        """Route one request. Authorisation is the caller's, checked before this.

        Serves only inside the running window: ``503`` before ``startup()`` and
        after ``shutdown()``, because a handler run then is a handler run
        against resources its own shutdown hook already released. Making that
        the host's problem means every host has to solve it.

        404 for an unrouted path, 405 with an ``Allow`` header for a path that
        exists under another method. Static routes win over parameterised ones,
        so ``/items/new`` reaches its own handler rather than ``/items/{id}``.
        ``HEAD`` is served by the ``GET`` route unless a ``HEAD`` route is
        declared, with the body suppressed and ``Content-Length`` carrying what
        ``GET`` would have returned.

        ``elide_head=False`` returns that response **before** the body is
        dropped. A transport has to measure the bytes it is not going to send,
        and reconstructing the count from a header it did not write is how a
        handler ends up framing the response. The ASGI adapter passes it; a
        caller reading responses in-process should not.
        """
        method = method.upper()
        headers = MappingProxyType(dict(headers or {}))
        if not self._running:
            _, reason = self.readiness()
            response = Response(
                status=503,
                body=f"composition is not running ({reason})".encode("utf-8"))
        else:
            response = self._route(method, path, headers, body)
        return _head_of(response) if (method == "HEAD" and elide_head) else response

    def _route(self, method: str, path: str, headers: Mapping[str, str],
               body: bytes) -> Response:
        allowed: set[str] = set()

        hit = self._assets.get(path)
        if hit is not None:
            allowed.update({"GET", "HEAD"})
            if method in ("GET", "HEAD"):
                _, asset = hit
                return Response(
                    status=200,
                    body=asset.body,
                    media_type=asset.media_type,
                    headers=MappingProxyType(
                        {"Content-Length": str(len(asset.body))}),
                )

        chosen: tuple[str, Callable[[Request], Response], dict[str, str]] | None = None
        head_of_get: tuple[str, Callable[[Request], Response],
                           dict[str, str]] | None = None
        for route_method, template, owner, handler in self._routes:
            params = _match(template, path)
            if params is None:
                continue
            allowed.add(route_method)
            if route_method == "GET":
                allowed.add("HEAD")     # HTTP: HEAD is served wherever GET is
            if route_method == method:
                if chosen is None:
                    chosen = (owner, handler, params)
            elif method == "HEAD" and route_method == "GET" and head_of_get is None:
                head_of_get = (owner, handler, params)

        target = chosen or head_of_get
        if target is not None:
            owner, handler, params = target
            request = Request(method=method, path=path,
                              params=MappingProxyType(params),
                              headers=headers, body=body)
            return _require_response(owner, method, path, handler(request))

        if allowed:
            return Response(
                status=405,
                body=f"{method} not allowed for {path}".encode("utf-8"),
                headers=MappingProxyType({"Allow": ", ".join(sorted(allowed))}),
            )
        return Response(status=404, body=f"no route for {path}".encode("utf-8"))


def _head_of(response: Response) -> Response:
    """The same response with no body, and a truthful ``Content-Length``.

    Applied to every response including 404 and 405, because a HEAD that
    carries a body is a protocol violation whatever its status.
    """
    headers = dict(response.headers)
    if not any(key.lower() == "content-length" for key in headers):
        headers["Content-Length"] = str(len(response.body))
    return Response(status=response.status, body=b"",
                    media_type=response.media_type,
                    headers=MappingProxyType(headers))


def _require_response(owner: str, method: str, path: str, value: Any) -> Response:
    if isinstance(value, Response):
        return value
    if inspect.isawaitable(value):
        close = getattr(value, "close", None)
        if callable(close):
            close()
        raise CompositionError(
            f"{owner}: handler for {method} {path} returned an awaitable. "
            f"Handlers and lifecycle hooks are synchronous here; an async "
            f"handler would be scheduled by nobody and never run. Wrap the "
            f"await in the adapter you own, or make the handler synchronous")
    raise CompositionError(
        f"{owner}: handler for {method} {path} returned "
        f"{type(value).__name__}, expected Response")


def _startup_residue(member_id: str,
                     exc: BaseException) -> tuple[tuple[str, str], ...]:
    """What the failing member itself is still holding, if anything is known.

    A startup hook is expected to be a transaction. Two cases say it was not:
    the hook raised :class:`~appcompose.errors.PartialStartup` to declare it
    kept resources, or it was interrupted, which means it neither finished nor
    reached its own cleanup. Both leave the member unaccounted for, and an
    unaccounted-for member is latched rather than forgotten.
    """
    partial = exc if isinstance(exc, PartialStartup) else None
    if partial is None and isinstance(exc.__cause__, PartialStartup):
        partial = exc.__cause__
    if partial is not None:
        return ((member_id, f"startup left resources behind: {partial.detail}"),)
    if not isinstance(exc, Exception):
        return ((member_id,
                 f"startup interrupted by {type(exc).__name__} before it "
                 f"finished or cleaned up"),)
    return ()


def _run_hook(member_id: str, phase: str,
              hook: Callable[[], None | Awaitable[None]] | None) -> None:
    """Call one lifecycle hook, refusing an awaitable rather than dropping it."""
    if hook is None:
        return
    result = hook()
    if inspect.isawaitable(result):
        close = getattr(result, "close", None)
        if callable(close):
            close()
        raise CompositionError(
            f"{member_id}: {phase} returned an awaitable. Lifecycle hooks are "
            f"synchronous here; an un-awaited coroutine never runs, so it is "
            f"refused rather than silently skipped")


def _segments(template: str) -> list[str]:
    return template.split("/")


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}") and len(segment) > 2


def route_template_error(template: str) -> str:
    """Why ``template`` is not a usable route template, or ``""``.

    The template language is deliberately tiny, and its bound is stated here
    rather than implied by a matcher: a segment is **either** a literal **or**
    exactly one ``{name}`` parameter that spans the whole segment. ``/a/{p}c``
    is neither, and a matcher that reads it as a literal while a conflict check
    reads it as a parameter is how two distinct paths refuse each other.
    """
    problem = asset_path_error(template)
    if problem:
        return problem
    names: list[str] = []
    for segment in _segments(template)[1:]:
        if "{" not in segment and "}" not in segment:
            continue
        if not _is_param(segment):
            return (f"segment {segment!r} mixes literal text with a parameter. "
                    f"A segment is either a literal or exactly one '{{name}}'")
        name = segment[1:-1]
        if not _PARAM_NAME.match(name):
            return (f"parameter {segment!r} is not named "
                    f"{_PARAM_NAME.pattern}")
        if name in names:
            return f"declares the parameter {name!r} twice"
        names.append(name)
    if len(names) > MAX_ROUTE_PARAMS:
        return f"declares {len(names)} parameters; limit {MAX_ROUTE_PARAMS}"
    return ""


def _match(template: str, path: str) -> dict[str, str] | None:
    expected = _segments(template)
    actual = _segments(path)
    if len(expected) != len(actual):
        return None
    params: dict[str, str] = {}
    for want, have in zip(expected, actual):
        if _is_param(want):
            if not have:
                return None
            params[want[1:-1]] = have
        elif want != have:
            return None
    return params


def _shape(path: str) -> str:
    """The path with parameter names erased.

    ``/items/{id}`` and ``/items/{key}`` are the same route to a router and a
    different route to a careless conflict check, so the names go before the
    comparison.
    """
    return _PARAM.sub("{}", path)


def _specificity(template: str) -> tuple[int, ...]:
    """1 per literal segment, 0 per parameter. Compared position by position."""
    return tuple(0 if _is_param(seg) else 1 for seg in _segments(template))


def _templates_intersect(first: str, second: str) -> bool:
    """Is there any path both templates match?"""
    left, right = _segments(first), _segments(second)
    if len(left) != len(right):
        return False
    return all(_is_param(a) or _is_param(b) or a == b
               for a, b in zip(left, right))


def _dominates(first: tuple[int, ...], second: tuple[int, ...]) -> bool:
    """Is ``first`` at least as specific as ``second`` in every segment?"""
    return all(a >= b for a, b in zip(first, second))


# ----------------------------------------------------------------------
# The adoption boundary.
# ----------------------------------------------------------------------


def compose(
    document: Document,
    *,
    resolve: Callable[[str, Member], Contribution | None],
) -> Composition:
    """Assemble an application from ``document`` using the caller's ``resolve``.

    ``resolve(capability, member)`` returns a :class:`Contribution`, or ``None``
    when the caller does not allow that capability. Raising ``KeyError`` or
    ``LookupError`` means the same thing. Any other exception is the caller's
    and propagates unchanged.

    Refuses, rather than guessing, when two members claim one method and path
    shape, when two members ship one asset path and the document names no owner,
    when ``ownership`` names a path or member the composition does not have, or
    when a contribution carries metadata this composition does not define.
    """
    if not callable(resolve):
        raise TypeError("resolve must be callable: resolve(capability, member)")

    ordered_ids = document.order()
    by_id = {m.id: m for m in document.members}

    members: list[ComposedMember] = []
    for member_id in ordered_ids:
        member = by_id[member_id]
        try:
            contribution = resolve(member.capability, member)
        except (KeyError, LookupError) as exc:
            raise CapabilityNotAllowed(
                member.id, member.capability,
                f"the resolver does not allow {member.capability!r} ({exc}). "
                f"The resolver is the allowlist: add it there, or remove the "
                f"member") from exc
        if contribution is None:
            raise CapabilityNotAllowed(
                member.id, member.capability,
                f"the resolver does not allow {member.capability!r}. The "
                f"resolver is the allowlist: add it there, or remove the member")
        if not isinstance(contribution, Contribution):
            raise CompositionError(
                f"{member.id}: resolver returned "
                f"{type(contribution).__name__}, expected Contribution")
        _check_metadata(member.id, contribution)
        members.append(ComposedMember(
            id=member.id,
            capability=member.capability,
            placement=document.placement(member.id),
            contribution=contribution,
        ))

    routes = _collect_routes(members)
    assets = _collect_assets(members, document, routes)
    return Composition(document, tuple(members), routes, assets)


def _check_metadata(member_id: str, contribution: Contribution) -> None:
    metadata = contribution.metadata or {}
    unknown = tuple(sorted(set(metadata) - set(METADATA_KEYS)))
    if unknown:
        raise UnknownMetadata(member_id, unknown, METADATA_KEYS)
    for key, value in metadata.items():
        if not isinstance(value, str):
            raise CompositionError(
                f"{member_id}: metadata[{key!r}] is "
                f"{type(value).__name__}, expected a string")


def _collect_routes(
    members: Sequence[ComposedMember],
) -> tuple[tuple[str, str, str, Callable[[Request], Response]], ...]:
    claimed: dict[tuple[str, str], str] = {}
    collected: list[tuple[str, str, str, Callable[[Request], Response]]] = []
    for member in members:
        for route in member.contribution.routes:
            method = str(route.method).upper()
            if method not in METHODS:
                raise CompositionError(
                    f"{member.id}: route method {route.method!r} is not one of "
                    f"{list(METHODS)}")
            problem = route_template_error(route.path)
            if problem:
                raise CompositionError(f"{member.id}: route {route.path!r} {problem}")
            if not callable(route.handler):
                raise CompositionError(
                    f"{member.id}: route {method} {route.path} has no callable handler")
            key = (method, _shape(route.path))
            owner = claimed.get(key)
            if owner is not None:
                raise RouteConflict(method, _shape(route.path), owner, member.id)
            claimed[key] = member.id
            collected.append((method, route.path, member.id, route.handler))
    _refuse_ambiguous_overlaps(collected)
    # More specific first, segment by segment, so a literal declared second is
    # not swallowed by a parameter declared first. Every remaining overlap has
    # one strictly more specific template, so this order is total and stated.
    collected.sort(key=lambda item: tuple(-v for v in _specificity(item[1])))
    return tuple(collected)


def _refuse_ambiguous_overlaps(
    collected: Sequence[tuple[str, str, str, Callable[[Request], Response]]],
) -> None:
    """Refuse two templates that overlap with no rule saying which wins.

    ``/items/new`` and ``/items/{id}`` overlap, and the literal is more specific
    in every segment, so the winner is a rule rather than a declaration order.
    ``/{a}/y`` and ``/x/{b}`` also overlap, and neither is more specific: only
    the order they happened to be listed in decides, which is a routing table
    that changes when somebody sorts a dictionary. That is refused.
    """
    for index, (method, template, owner, _handler) in enumerate(collected):
        for other_method, other, other_owner, _ in collected[index + 1:]:
            if method != other_method:
                continue
            if not _templates_intersect(template, other):
                continue
            mine, theirs = _specificity(template), _specificity(other)
            if _dominates(mine, theirs) or _dominates(theirs, mine):
                continue
            raise RouteConflict(
                method, f"{template} and {other} overlap on paths such as "
                        f"{_witness(template, other)}, and neither is more "
                        f"specific", owner, other_owner)


def _witness(first: str, second: str) -> str:
    """One concrete path both templates match, so the refusal is checkable."""
    parts = []
    for left, right in zip(_segments(first), _segments(second)):
        if not _is_param(left):
            parts.append(left)
        elif not _is_param(right):
            parts.append(right)
        else:
            parts.append(left[1:-1])
    return "/".join(parts)


def _collect_assets(
    members: Sequence[ComposedMember],
    document: Document,
    routes: Sequence[tuple[str, str, str, Callable[[Request], Response]]],
) -> dict[str, tuple[str, Asset]]:
    servable = [(path, owner) for method, path, owner, _ in routes
                if method in ("GET", "HEAD")]
    assets: dict[str, tuple[str, Asset]] = {}
    for member in members:
        for asset in member.contribution.assets:
            problem = asset_path_error(asset.path)
            if problem:
                raise CompositionError(f"{member.id}: asset {asset.path!r} {problem}")
            if not isinstance(asset.body, (bytes, bytearray)):
                raise CompositionError(
                    f"{member.id}: asset {asset.path} body is "
                    f"{type(asset.body).__name__}, expected bytes")
            # Assets are served before any route is matched, so the collision
            # test has to be the *matcher*, not a string comparison: a static
            # file shadowing GET /files/{name} is the bug nobody finds by
            # reading the code, and only _match sees it.
            for template, owner in servable:
                if _match(template, asset.path) is not None:
                    raise CompositionError(
                        f"{member.id}: asset {asset.path} is already served by "
                        f"route GET {template} ('{owner}'). One path, one "
                        f"owner — an asset that shadows a handler answers "
                        f"first and silently")
            existing = assets.get(asset.path)
            if existing is None:
                assets[asset.path] = (member.id, asset)
                continue
            owner = document.ownership.get(asset.path)
            contenders = (existing[0], member.id)
            if owner is None or owner not in contenders:
                raise AssetConflict(asset.path, existing[0], member.id)
            assets[asset.path] = (owner, asset if owner == member.id else existing[1])
    for path, owner in document.ownership.items():
        if path not in assets:
            raise CompositionError(
                f"ownership[{path!r}]: no composed member ships that asset")
        if assets[path][0] != owner:
            raise CompositionError(
                f"ownership[{path!r}]: names {owner!r}, but only "
                f"{assets[path][0]!r} ships it")
    return assets
