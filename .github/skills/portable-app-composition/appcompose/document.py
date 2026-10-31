"""The document — one human-authored file that describes the whole application.

WHAT THIS IS
------------
A versioned JSON object listing the *members* an application is assembled from,
what each member requires, and — optionally — where a shell should put it. It
is the durable artefact: a person hand-edits it, a program rewrites it, a file
round-trips it, a composer projects an application from it.

CANONICAL IS JSON. YAML IS A SERIALISATION.
-------------------------------------------
One canonical shape, two ways in and out of it. Round-tripping through YAML
produces byte-identical canonical JSON or it is a defect; :mod:`appcompose.
serialisation` is where that is enforced.

A DOCUMENT NAMES CAPABILITIES, NEVER CODE
-----------------------------------------
``capability`` is an opaque identifier. Nothing here imports anything, and no
key may carry a module path, an entry point, or a callable name: the keys that
usually smuggle one in are refused by name with the reason. What a capability
identifier *means* is decided by the resolver the caller injects into
:func:`appcompose.compose`, and that resolver is the allowlist.

EVERY REFUSAL NAMES ITS FIELD
-----------------------------
Validation is hand-rolled so that ``members[1].requires[0]`` can be the message.

LAYOUT IS OPTIONAL, AND THAT IS WHAT MAKES THE FILE HUMAN-WRITABLE
------------------------------------------------------------------
``layout`` and ``ownership`` may both be absent. A format that demands
coordinates before it will parse is a format only a program can write.

NO CREDENTIAL, EVER
-------------------
A credential-shaped key with a literal value is refused, naming the field. That
is a backstop for a mistake, not a proof of absence — see ``GOTCHAS.md``, G7.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from appcompose.errors import CredentialShaped, DocumentInvalid, UnsupportedVersion

__all__ = [
    "Document",
    "KIND",
    "Member",
    "Placement",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "asset_path_error",
    "parse",
    "plain",
    "to_mapping",
]

#: The document's own version. A stored file outlives the release of the code
#: that accepted it, so this is versioned independently of any wire schema.
SCHEMA_VERSION = 1

#: Every version this build can read. Adding a version means adding a migration
#: here, not widening a comparison somewhere else.
SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1,)

#: What this file is, stated in the file, so a JSON object found on a disk with
#: no context is identifiable by itself alone.
KIND = "portable.app-composition"

MAX_MEMBERS = 64
MAX_NAME_CHARS = 120
MAX_DESCRIPTION_CHARS = 2_000
MAX_LABEL_CHARS = 120
MAX_SETTINGS_BYTES = 16_384
MAX_SETTINGS_DEPTH = 8
MAX_PATH_CHARS = 256
MAX_SLOT_CHARS = 64

#: How deep any part of a document may nest before the parser refuses it.
#: Checked while walking, not by catching ``RecursionError`` afterwards: a
#: mapping handed straight to :func:`parse` never passes through a parser that
#: would have hit its own limit first.
MAX_DOCUMENT_DEPTH = 32

#: Ids share one namespace across the document: ``layout`` and ``ownership``
#: are keyed by member id, so two members called ``x`` would fight over one
#: entry. Shaped so an id can never be a path segment or a shell word.
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")

#: A capability identifier. Lowercase and dotted, because it is a name in the
#: caller's allowlist rather than anything the filesystem or an importer sees.
CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")

NAME = re.compile(r"^[^\x00-\x1f]{1,120}$")

_DOCUMENT_KEYS = frozenset(
    {"schemaVersion", "kind", "id", "name", "description", "members",
     "layout", "ownership"}
)
_MEMBER_KEYS = frozenset({"id", "capability", "label", "settings", "requires"})
_PLACEMENT_KEYS = frozenset({"slot", "order", "lazy"})

#: Keys that would turn a data file into an execution instruction. Refused by
#: name, with the reason, because "unknown key" does not teach the lesson.
_EXECUTABLE_KEYS = frozenset(
    {"entry", "entrypoint", "entry_point", "module", "import", "callable",
     "factory", "plugin", "class", "exec", "eval", "command", "shell"}
)

_CREDENTIAL_KEY = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|client[_-]?secret|"
    r"connection[_-]?string|sas[_-]?token|access[_-]?token|private[_-]?key|"
    r"credential)"
)

#: Values that name where a credential lives rather than being one. Never add
#: an empty string here: ``"" in anything`` is true, and the whole scan silently
#: stops finding anything at all.
_CREDENTIAL_ALLOWED = ("<", ">", "${", "{{", "env:", "os.", "keyvault",
                       "placeholder", "example", "unset", "none", "null")


# ----------------------------------------------------------------------
# Immutability.
# ----------------------------------------------------------------------


def _freeze(value: Any) -> Any:
    """Deep-freeze parsed data so a document cannot be edited through a handle.

    Mappings become read-only views and sequences become tuples, all the way
    down. A caller that wants to mutate calls :func:`plain` and gets its own
    copy; a caller that mutates by accident gets a ``TypeError``.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def plain(value: Any) -> Any:
    """A mutable deep copy of frozen document data. The inverse of freezing."""
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


# ----------------------------------------------------------------------
# The record types.
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Member:
    """One member of the application: what it is, and what it needs first.

    ``settings`` is the member's own configuration, opaque to this skill and
    handed unchanged to whatever the resolver returns for ``capability``.
    """

    id: str
    capability: str
    label: str = ""
    settings: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    requires: tuple[str, ...] = ()

    def settings_copy(self) -> dict[str, Any]:
        """A mutable deep copy the caller owns. The stored mapping stays frozen."""
        return plain(self.settings)


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a shell should put a member. Metadata, carried, never enforced.

    This skill has no opinion about what a slot is: ``slot`` is whatever string
    the shell that reads it understands. ``lazy`` is a hint that the shell may
    defer loading; nothing here acts on it.
    """

    slot: str = ""
    order: int = 0
    lazy: bool = False


@dataclass(frozen=True, slots=True)
class Document:
    """One validated document. Constructed only by :func:`parse`."""

    name: str
    id: str = ""
    description: str = ""
    members: tuple[Member, ...] = ()
    layout: Mapping[str, Placement] = field(default_factory=lambda: MappingProxyType({}))
    ownership: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    schema_version: int = SCHEMA_VERSION
    kind: str = KIND

    def member(self, member_id: str) -> Member:
        for entry in self.members:
            if entry.id == member_id:
                return entry
        raise KeyError(member_id)

    def order(self) -> tuple[str, ...]:
        """Member ids in dependency order: every provider before its consumers.

        Deterministic — ties break on document order, so the same document
        always starts in the same sequence.
        """
        return _topological_order(self.members)

    def placement(self, member_id: str) -> Placement:
        """The member's placement, or the neutral default when none is declared."""
        return self.layout.get(member_id, Placement())

    def without(self, member_id: str) -> "Document":
        """The same document minus one member, re-validated.

        Removing a *consumer* yields a smaller working document. Removing a
        *provider* somebody still requires raises ``DocumentInvalid`` naming
        the dependency that no longer resolves — which is the whole point of
        re-validating rather than splicing the tuple.
        """
        if not any(entry.id == member_id for entry in self.members):
            raise KeyError(member_id)
        payload = to_mapping(self)
        payload["members"] = [m for m in payload["members"]
                              if m["id"] != member_id]
        payload["layout"] = {k: v for k, v in payload.get("layout", {}).items()
                             if k != member_id}
        payload["ownership"] = {k: v for k, v
                                in payload.get("ownership", {}).items()
                                if v != member_id}
        return parse(payload)


# ----------------------------------------------------------------------
# Field helpers. Each one names the field it refuses.
# ----------------------------------------------------------------------


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DocumentInvalid(field, f"expected an object, found {_kind(value)}")
    for key in value:
        if not isinstance(key, str):
            raise DocumentInvalid(field, f"key {key!r} is not a string")
    return value


def _require_sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        raise DocumentInvalid(field, f"expected a list, found {_kind(value)}")
    return value


def _require_str(value: Any, field: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise DocumentInvalid(field, f"expected a string, found {_kind(value)}")
    if len(value) > limit:
        raise DocumentInvalid(field, f"is {len(value)} characters; limit {limit}")
    return value


def _require_int(value: Any, field: str) -> int:
    # bool is an int in Python and that has bitten every hand-rolled parser.
    if isinstance(value, bool) or not isinstance(value, int):
        raise DocumentInvalid(field, f"expected an integer, found {_kind(value)}")
    return value


def _kind(value: Any) -> str:
    return type(value).__name__


def _reject_unknown_keys(payload: Mapping[str, Any], allowed: Iterable[str],
                         field: str) -> None:
    unknown = sorted(set(payload) - set(allowed))
    if not unknown:
        return
    executable = [k for k in unknown if k.lower().replace("-", "_") in _EXECUTABLE_KEYS]
    if executable:
        raise DocumentInvalid(
            f"{field}.{executable[0]}" if field else executable[0],
            "a document names capabilities, never code. Nothing here imports "
            "anything: map the capability identifier to an implementation in "
            "the resolver you pass to compose(), which is the allowlist",
        )
    raise DocumentInvalid(
        f"{field}.{unknown[0]}" if field else unknown[0],
        f"unknown key; this document accepts {sorted(allowed)}",
    )


def asset_path_error(path: str) -> str:
    """Why ``path`` is unusable as an asset or route path, or ``""``.

    Shared by the parser and the composer so a document and a contribution are
    held to one rule. Traversal, backslashes, empty segments and control
    characters are all refused, because an asset path becomes a lookup key and
    a lookup key that can escape is a bug waiting for a filesystem.
    """
    if not isinstance(path, str):
        return f"expected a string, found {_kind(path)}"
    if not path.startswith("/"):
        return "must start with '/'"
    if len(path) > MAX_PATH_CHARS:
        return f"is {len(path)} characters; limit {MAX_PATH_CHARS}"
    if "\\" in path:
        return "contains a backslash"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in path):
        return "contains a control character"
    segments = path.split("/")[1:]
    if ".." in segments:
        return "contains a '..' traversal segment"
    if "." in segments:
        return "contains a '.' segment"
    if any(seg == "" for seg in segments[:-1]) or (
            len(segments) > 1 and segments[-1] == ""):
        return "contains an empty path segment"
    return ""


def _scan_for_credentials(value: Any, field: str, depth: int = 0,
                          ancestors: tuple[Any, ...] = ()) -> None:
    """Walk the whole payload once, bounded in depth and safe against cycles.

    Bounded because this runs *before* any field-level limit, so an unbounded
    walk here is the cheapest denial of service the parser offers. Cycle-aware
    because a mapping passed directly to :func:`parse` can contain itself,
    which no JSON or YAML reader could have produced.
    """
    if isinstance(value, (Mapping, list, tuple)):
        if depth > MAX_DOCUMENT_DEPTH:
            raise DocumentInvalid(
                field or "<document>",
                f"nests deeper than {MAX_DOCUMENT_DEPTH} levels")
        for ancestor in ancestors:
            if ancestor is value:
                raise DocumentInvalid(
                    field or "<document>",
                    "contains a reference cycle; a document is a tree and a "
                    "cycle has no canonical form")
        ancestors = ancestors + (value,)
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{field}.{key}" if field else str(key)
            if _CREDENTIAL_KEY.search(str(key)):
                _check_credential_value(here, item)
            _scan_for_credentials(item, here, depth + 1, ancestors)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_for_credentials(item, f"{field}[{index}]", depth + 1,
                                  ancestors)


def _check_credential_value(field: str, value: Any) -> None:
    """What a credential-shaped key is allowed to hold: a reference, or nothing.

    A list or an object under ``api_key`` is not an exemption — that loophole
    is exactly how a pasted secret survives a scan that only reads strings.
    Still a backstop: see ``GOTCHAS.md``, G7.
    """
    if value is None:
        return
    if isinstance(value, str):
        low = value.strip().lower()
        if not low:
            return
        if len(low) >= 8 and not any(t in low for t in _CREDENTIAL_ALLOWED):
            raise CredentialShaped(
                field,
                "a credential-shaped key was given a literal value. A "
                "document carries public coordinates only; name where "
                "the secret lives, never the secret",
            )
        return
    raise CredentialShaped(
        field,
        f"a credential-shaped key holds {_kind(value)}. It may hold a string "
        f"naming where the secret lives, an empty string, or null — wrapping a "
        f"value in a list or object is not an exemption. Rename the key if it "
        f"names something that is not a credential",
    )


def _check_settings(value: Any, field: str, depth: int = 0) -> None:
    if depth > MAX_SETTINGS_DEPTH:
        raise DocumentInvalid(field, f"nests deeper than {MAX_SETTINGS_DEPTH} levels")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DocumentInvalid(field, f"key {key!r} is not a string")
            _check_settings(item, f"{field}.{key}", depth + 1)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_settings(item, f"{field}[{index}]", depth + 1)
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise DocumentInvalid(
                field, "is not a finite number; JSON has no NaN or Infinity")
    elif not isinstance(value, (str, int, bool)) and value is not None:
        raise DocumentInvalid(
            field, f"{_kind(value)} is not JSON data; use objects, lists, "
                   f"strings, numbers, booleans or null")


def _topological_order(members: Sequence[Member]) -> tuple[str, ...]:
    """Kahn's algorithm, ties broken on document order for determinism."""
    remaining = {m.id: set(m.requires) for m in members}
    document_order = [m.id for m in members]
    ordered: list[str] = []
    while remaining:
        ready = [mid for mid in document_order
                 if mid in remaining and not remaining[mid]]
        if not ready:
            raise DocumentInvalid(
                "members", "dependency cycle: " + _describe_cycle(remaining))
        for mid in ready:
            ordered.append(mid)
            del remaining[mid]
        for pending in remaining.values():
            pending.difference_update(ready)
    return tuple(ordered)


def _describe_cycle(remaining: Mapping[str, set[str]]) -> str:
    """One concrete cycle, written out, rather than "there is a cycle"."""
    start = sorted(remaining)[0]
    seen: list[str] = []
    node = start
    while node not in seen:
        seen.append(node)
        candidates = sorted(d for d in remaining[node] if d in remaining)
        if not candidates:
            break
        node = candidates[0]
    if node in seen:
        cycle = seen[seen.index(node):] + [node]
        return " -> ".join(cycle)
    return " -> ".join(seen)


# ----------------------------------------------------------------------
# Parsing.
# ----------------------------------------------------------------------


def parse(payload: Mapping[str, Any]) -> Document:
    """Validate a plain mapping and return an immutable :class:`Document`.

    The input is never retained: everything kept is deep-copied and frozen, so
    mutating the mapping afterwards cannot change the parsed document.
    """
    payload = _require_mapping(payload, "<document>")
    try:
        _scan_for_credentials(payload, "")
    except RecursionError as exc:  # defensive: the depth bound above should win
        raise DocumentInvalid(
            "<document>", "nests too deeply to validate") from exc
    _reject_unknown_keys(payload, _DOCUMENT_KEYS, "")

    if "schemaVersion" not in payload:
        raise UnsupportedVersion(
            "schemaVersion",
            f"is missing; this build reads {list(SUPPORTED_SCHEMA_VERSIONS)}",
            supported=SUPPORTED_SCHEMA_VERSIONS)
    version = payload["schemaVersion"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise UnsupportedVersion(
            "schemaVersion", f"expected an integer, found {_kind(version)}",
            found=version, supported=SUPPORTED_SCHEMA_VERSIONS)
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        direction = ("was written by a newer release"
                     if version > SCHEMA_VERSION else "predates this build")
        raise UnsupportedVersion(
            "schemaVersion",
            f"{version} {direction}; this build reads "
            f"{list(SUPPORTED_SCHEMA_VERSIONS)} and has no migration for it",
            found=version, supported=SUPPORTED_SCHEMA_VERSIONS)

    kind = _require_str(payload.get("kind", KIND), "kind", limit=MAX_NAME_CHARS)
    if kind != KIND:
        raise DocumentInvalid("kind", f"is {kind!r}; expected {KIND!r}")

    name = _require_str(payload.get("name", ""), "name", limit=MAX_NAME_CHARS)
    if not NAME.match(name):
        raise DocumentInvalid(
            "name", "must be 1-120 characters and carry no control characters")
    doc_id = _require_str(payload.get("id", ""), "id", limit=64)
    if doc_id and not ID.match(doc_id):
        raise DocumentInvalid("id", f"{doc_id!r} does not match {ID.pattern}")
    description = _require_str(payload.get("description", ""), "description",
                               limit=MAX_DESCRIPTION_CHARS)

    members = _parse_members(payload.get("members", []))
    known = {m.id for m in members}
    _topological_order(members)  # cycles refuse here, not at compose time

    layout = _parse_layout(payload.get("layout", {}), known)
    ownership = _parse_ownership(payload.get("ownership", {}), known)

    return Document(
        name=name,
        id=doc_id,
        description=description,
        members=members,
        layout=MappingProxyType(layout),
        ownership=MappingProxyType(ownership),
        schema_version=version,
        kind=kind,
    )


def _parse_members(raw: Any) -> tuple[Member, ...]:
    entries = _require_sequence(raw, "members")
    if len(entries) > MAX_MEMBERS:
        raise DocumentInvalid(
            "members", f"declares {len(entries)} members; limit {MAX_MEMBERS}")

    members: list[Member] = []
    seen: dict[str, int] = {}
    for index, item in enumerate(entries):
        field = f"members[{index}]"
        item = _require_mapping(item, field)
        _reject_unknown_keys(item, _MEMBER_KEYS, field)

        member_id = _require_str(item.get("id", ""), f"{field}.id", limit=64)
        if not ID.match(member_id):
            raise DocumentInvalid(
                f"{field}.id", f"{member_id!r} does not match {ID.pattern}")
        if member_id in seen:
            raise DocumentInvalid(
                f"{field}.id",
                f"duplicate id {member_id!r}; already declared at "
                f"members[{seen[member_id]}]. Ids are one namespace, shared "
                f"with layout and ownership")
        seen[member_id] = index

        capability = _require_str(item.get("capability", ""),
                                  f"{field}.capability", limit=64)
        if not CAPABILITY.match(capability):
            raise DocumentInvalid(
                f"{field}.capability",
                f"{capability!r} does not match {CAPABILITY.pattern}")

        label = _require_str(item.get("label", ""), f"{field}.label",
                             limit=MAX_LABEL_CHARS)

        settings = _require_mapping(item.get("settings", {}), f"{field}.settings")
        _check_settings(settings, f"{field}.settings")
        encoded = json.dumps(plain(settings), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_SETTINGS_BYTES:
            raise DocumentInvalid(
                f"{field}.settings",
                f"serialises to {len(encoded)} bytes; limit {MAX_SETTINGS_BYTES}")

        requires: list[str] = []
        for r_index, dependency in enumerate(
                _require_sequence(item.get("requires", []), f"{field}.requires")):
            r_field = f"{field}.requires[{r_index}]"
            dependency = _require_str(dependency, r_field, limit=64)
            if dependency == member_id:
                raise DocumentInvalid(r_field, "a member cannot require itself")
            if dependency in requires:
                raise DocumentInvalid(r_field, f"{dependency!r} is listed twice")
            requires.append(dependency)

        members.append(Member(
            id=member_id,
            capability=capability,
            label=label,
            settings=_freeze(settings),
            requires=tuple(requires),
        ))

    known = {m.id for m in members}
    for index, member in enumerate(members):
        for r_index, dependency in enumerate(member.requires):
            if dependency not in known:
                raise DocumentInvalid(
                    f"members[{index}].requires[{r_index}]",
                    f"names {dependency!r}, which no member declares. Add that "
                    f"member back, or drop the requirement")
    return tuple(members)


def _parse_layout(raw: Any, known: set[str]) -> dict[str, Placement]:
    layout = _require_mapping(raw, "layout")
    parsed: dict[str, Placement] = {}
    for member_id, value in layout.items():
        field = f"layout.{member_id}"
        if member_id not in known:
            raise DocumentInvalid(
                field, f"names {member_id!r}, which no member declares")
        value = _require_mapping(value, field)
        _reject_unknown_keys(value, _PLACEMENT_KEYS, field)
        slot = _require_str(value.get("slot", ""), f"{field}.slot",
                            limit=MAX_SLOT_CHARS)
        order = _require_int(value.get("order", 0), f"{field}.order")
        lazy = value.get("lazy", False)
        if not isinstance(lazy, bool):
            raise DocumentInvalid(f"{field}.lazy",
                                  f"expected true or false, found {_kind(lazy)}")
        parsed[member_id] = Placement(slot=slot, order=order, lazy=lazy)
    return parsed


def _parse_ownership(raw: Any, known: set[str]) -> dict[str, str]:
    ownership = _require_mapping(raw, "ownership")
    parsed: dict[str, str] = {}
    for path, owner in ownership.items():
        field = f"ownership[{path!r}]"
        problem = asset_path_error(path)
        if problem:
            raise DocumentInvalid(field, problem)
        owner = _require_str(owner, field, limit=64)
        if owner not in known:
            raise DocumentInvalid(
                field, f"names {owner!r}, which no member declares")
        parsed[path] = owner
    return parsed


# ----------------------------------------------------------------------
# Back out again.
# ----------------------------------------------------------------------


def to_mapping(document: Document) -> dict[str, Any]:
    """A plain, mutable, JSON-ready mapping. Optional empty blocks are omitted.

    Omission is deliberate: a hand-authored file that never mentioned ``layout``
    must not grow one on the first save, or every round trip is a diff.
    """
    payload: dict[str, Any] = {
        "schemaVersion": document.schema_version,
        "kind": document.kind,
        "name": document.name,
    }
    if document.id:
        payload["id"] = document.id
    if document.description:
        payload["description"] = document.description
    payload["members"] = [_member_mapping(m) for m in document.members]
    if document.layout:
        payload["layout"] = {
            member_id: _placement_mapping(placement)
            for member_id, placement in document.layout.items()
        }
    if document.ownership:
        payload["ownership"] = dict(document.ownership)
    return payload


def _member_mapping(member: Member) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": member.id, "capability": member.capability}
    if member.label:
        payload["label"] = member.label
    if member.settings:
        payload["settings"] = plain(member.settings)
    if member.requires:
        payload["requires"] = list(member.requires)
    return payload


def _placement_mapping(placement: Placement) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if placement.slot:
        payload["slot"] = placement.slot
    if placement.order:
        payload["order"] = placement.order
    if placement.lazy:
        payload["lazy"] = placement.lazy
    return payload
