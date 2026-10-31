"""Every refusal this skill can raise, and the field or member it names.

Two families, because they fail at two different times and a caller handles
them differently:

* :class:`DocumentInvalid` — the *document* is unusable. Raised while parsing
  or serialising, before any capability is resolved and before any code the
  document names could run. It always carries ``field``, the path a person
  must edit.
* :class:`CompositionError` — the document was fine, but assembling or running
  the application from it failed. Raised by :func:`appcompose.compose` and by
  the lifecycle methods of the composition it returns.

A caller that catches only ``Exception`` and prints ``str(exc)`` still gets a
fixable message: every subclass formats itself as ``<what>: <why>``.
"""

from __future__ import annotations

__all__ = [
    "AssetConflict",
    "CapabilityFactoryFailed",
    "CapabilityNotAllowed",
    "CompositionError",
    "CredentialShaped",
    "DocumentInvalid",
    "PartialStartup",
    "ResponseInvalid",
    "RouteConflict",
    "ShutdownFailed",
    "StartupFailed",
    "UnknownMetadata",
    "UnsupportedVersion",
]


class DocumentInvalid(ValueError):
    """The document cannot be used. ``field`` is the path a caller must edit.

    ``members[1].requires[0]`` is a fixable message; "invalid configuration"
    is a puzzle. Every raise in the parser carries the path.
    """

    def __init__(self, field: str, detail: str) -> None:
        super().__init__(f"{field}: {detail}")
        self.field = field
        self.detail = detail


class UnsupportedVersion(DocumentInvalid):
    """``schemaVersion`` is absent, malformed, or a version this build cannot read.

    Separate from a generic field error because the caller's remedy is
    different: upgrade, downgrade, or migrate the file — not edit a value.
    """

    def __init__(self, field: str, detail: str, *, found: object = None,
                 supported: tuple[int, ...] = ()) -> None:
        super().__init__(field, detail)
        self.found = found
        self.supported = supported


class CredentialShaped(DocumentInvalid):
    """A credential-shaped key was assigned a literal value.

    A backstop, not a proof: it recognises common shapes and nothing more.
    See ``GOTCHAS.md``, G7.
    """


class CompositionError(RuntimeError):
    """Assembly or lifecycle failed. The document itself was valid."""


class CapabilityNotAllowed(CompositionError):
    """The caller's resolver did not allow the capability a member declares.

    The resolver *is* the allowlist. This is what the composer raises when the
    resolver returns ``None`` or raises a lookup error, so an unknown or
    withdrawn capability is a named refusal rather than an import attempt.
    """

    def __init__(self, member: str, capability: str, detail: str) -> None:
        super().__init__(f"members[{member}].capability: {detail}")
        self.member = member
        self.capability = capability


class CapabilityFactoryFailed(CompositionError):
    """An *allowed* capability's factory raised a lookup error while building.

    Separate from :class:`CapabilityNotAllowed` because the remedy is the
    opposite one. A ``KeyError`` raised inside a factory reads exactly like a
    resolver refusing the capability, and sending the reader to the allowlist
    for a missing settings key costs an afternoon. ``cause`` is the original.
    """

    def __init__(self, member: str, capability: str,
                 cause: BaseException) -> None:
        super().__init__(
            f"members[{member}].capability: the capability {capability!r} is "
            f"allowed, and its factory raised "
            f"{type(cause).__name__}: {cause}. The allowlist is not the "
            f"problem; the factory is"
        )
        self.member = member
        self.capability = capability
        self.cause = cause


class RouteConflict(CompositionError):
    """Two members claim the same method and path shape, and neither owns it."""

    def __init__(self, method: str, path: str, first: str, second: str) -> None:
        super().__init__(
            f"{method} {path}: claimed by both '{first}' and '{second}'; "
            f"one of them must change, there is no first-wins fallback"
        )
        self.method = method
        self.path = path
        self.members = (first, second)


class ResponseInvalid(CompositionError):
    """A handler's response cannot be put on the wire as written.

    Raised by the ASGI adapter, never by :meth:`Composition.dispatch`: the
    neutral ``Response`` is in-process data, and only a transport knows what a
    header name, a header value or a media type may legally contain. A CRLF in
    a header value is response splitting, so it is refused loudly rather than
    forwarded and left for the server to notice.
    """

    def __init__(self, field: str, detail: str) -> None:
        super().__init__(f"{field}: {detail}")
        self.field = field
        self.detail = detail


class AssetConflict(CompositionError):
    """Two members ship the same asset path and the document names no owner."""

    def __init__(self, path: str, first: str, second: str) -> None:
        super().__init__(
            f"{path}: shipped by both '{first}' and '{second}'; add "
            f"ownership[{path!r}] naming the member that owns it, or rename "
            f"one — identical bytes are not an excuse to guess"
        )
        self.path = path
        self.members = (first, second)


class UnknownMetadata(CompositionError):
    """A contribution carried a metadata key the composition does not define."""

    def __init__(self, member: str, keys: tuple[str, ...],
                 allowed: tuple[str, ...]) -> None:
        super().__init__(
            f"{member}: unknown contribution metadata {list(keys)}; "
            f"allowed keys are {list(allowed)}"
        )
        self.member = member
        self.keys = keys


class PartialStartup(CompositionError):
    """A startup hook failed **and** could not release what it had already built.

    A startup hook is a transaction: it either finishes, or it unwinds its own
    partial work before raising. A hook that genuinely cannot unwind — a child
    process that would not die, a lock it no longer holds the token for — raises
    this instead of a bare exception, and the composition latches an unsafe
    state naming that member. That is the difference between a failure the
    caller may retry and a resource nobody is accounting for.

    It is raised **by the caller's hook**, never by this package.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class StartupFailed(CompositionError):
    """One member's startup raised. Everything already started was rolled back.

    ``rolled_back`` lists the members whose shutdown ran, newest first.
    ``rollback_failures`` lists members whose rollback *also* raised, because
    swallowing those would hide a leak behind the original failure.
    ``left_behind`` names the failing member itself when its hook declared, by
    raising :class:`PartialStartup`, that it kept resources.
    """

    def __init__(self, member: str, cause: BaseException,
                 rolled_back: tuple[str, ...],
                 rollback_failures: tuple[tuple[str, str], ...] = (),
                 left_behind: tuple[tuple[str, str], ...] = ()) -> None:
        detail = f"{member}: startup failed ({type(cause).__name__}: {cause})"
        if rolled_back:
            detail += f"; rolled back {list(rolled_back)}"
        if rollback_failures:
            detail += f"; rollback also failed for {[m for m, _ in rollback_failures]}"
        if left_behind:
            detail += f"; resources left behind by {[m for m, _ in left_behind]}"
        super().__init__(detail)
        self.member = member
        self.cause = cause
        self.rolled_back = rolled_back
        self.rollback_failures = rollback_failures
        self.left_behind = left_behind


class ShutdownFailed(CompositionError):
    """One or more members failed to shut down. Every other member still ran.

    Shutdown never stops at the first failure: a member that leaks because an
    earlier member raised is a worse outcome than a late error.

    A shutdown failure also **latches** the composition unsafe, for the same
    reason a failed rollback does: a member whose stop hook raised may still
    hold its port, and starting it again would start it twice.
    """

    def __init__(self, failures: tuple[tuple[str, str], ...]) -> None:
        super().__init__(
            "shutdown failed for "
            + ", ".join(f"{member} ({detail})" for member, detail in failures)
        )
        self.failures = failures
