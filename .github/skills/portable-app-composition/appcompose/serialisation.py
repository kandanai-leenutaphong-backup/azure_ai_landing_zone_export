"""Serialisation: canonical JSON bytes, and a YAML form that refuses tricks.

CANONICAL BYTES, NOT "EQUIVALENT JSON"
--------------------------------------
:func:`canonical_json` is the identity of a document. Keys are sorted, the
separators carry no whitespace, no ASCII escaping is applied, and a trailing
newline is written so the file ends like a file. Two documents that mean the
same thing produce the same bytes, which is what makes a round trip testable by
comparison rather than by eye.

WHY YAML IS PARSED WITH ITS OWN LOADER
--------------------------------------
``yaml.safe_load`` blocks arbitrary object construction and nothing else. It
accepts duplicate keys silently — last one wins, and the value a person read in
the file is not the value the program used. It accepts anchors and aliases,
which is how a kilobyte of YAML expands into gigabytes of memory. Both are
refused here, by name, before they can become a defect.

SIZE IS CHECKED BEFORE PARSING, NOT AFTER
-----------------------------------------
A cap applied to the parsed result is applied after the memory was already
spent. Both entry points measure the encoded input first, and the JSON reader
measures nesting depth on the text before handing it to a recursive parser.

THE YAML WRITER VERIFIES ITS OWN ROUND TRIP
-------------------------------------------
``yaml.safe_dump(allow_unicode=True)`` writes U+0085 raw, and the loader folds
it back to a space — a silent corruption of a string the document validator
admits. So :func:`to_yaml` reads its own output back and compares canonical
bytes, falling back to fully escaped output when the readable form does not
survive. The identity in ``CONTRACT.md`` §2 is enforced by the writer, not
hoped for.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from appcompose.document import Document, parse, to_mapping
from appcompose.errors import DocumentInvalid

__all__ = [
    "MAX_DOCUMENT_BYTES",
    "MAX_NESTING_DEPTH",
    "canonical_json",
    "from_json",
    "from_yaml",
    "to_yaml",
]

#: A hand-authored application document is kilobytes. Anything past this is a
#: generated file, a pasted dump, or an attack, and none of the three should be
#: parsed just because it arrived.
MAX_DOCUMENT_BYTES = 256_000

#: How deep a serialised document may nest. Well under the interpreter's own
#: recursion limit, because ``json.loads`` and ``yaml.load`` both recurse and a
#: ``RecursionError`` is not a fixable message with a field in it.
MAX_NESTING_DEPTH = 32


def canonical_json(document: Document) -> bytes:
    """The document's canonical bytes. Byte-identical for equivalent documents."""
    payload = to_mapping(document)
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _measure(data: bytes | str, form: str) -> bytes:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if not isinstance(raw, (bytes, bytearray)):
        raise DocumentInvalid(f"<{form}>", "expected text or bytes")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise DocumentInvalid(
            f"<{form}>",
            f"is {len(raw)} bytes; limit {MAX_DOCUMENT_BYTES}. Checked before "
            f"parsing, because a cap applied afterwards is applied too late")
    return bytes(raw)


def _refuse_constant(token: str) -> Any:
    raise DocumentInvalid(
        "<json>",
        f"contains the non-finite constant {token}; JSON has no NaN or "
        f"Infinity and accepting one produces a document that cannot be "
        f"re-serialised")


def _refuse_deep_nesting(text: str, form: str) -> None:
    """Refuse over-nested input by counting brackets, before any parser recurses.

    Cheap, single pass, string-aware. It is a guard on the *text*: a mapping
    handed straight to :func:`~appcompose.document.parse` is bounded there
    instead.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_NESTING_DEPTH:
                raise DocumentInvalid(
                    f"<{form}>",
                    f"nests deeper than {MAX_NESTING_DEPTH} levels. Checked "
                    f"on the text, because a recursive parser reports depth as "
                    f"a RecursionError with no field in it")
        elif char in "]}":
            depth -= 1


def from_json(data: bytes | str) -> Document:
    """Parse canonical (or merely valid) JSON into a validated document."""
    raw = _measure(data, "json")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentInvalid("<json>", f"is not valid UTF-8: {exc}") from exc
    _refuse_deep_nesting(text, "json")
    try:
        payload = json.loads(text, parse_constant=_refuse_constant)
    except json.JSONDecodeError as exc:
        raise DocumentInvalid(
            "<json>", f"is not valid JSON: {exc.msg} at line {exc.lineno} "
                      f"column {exc.colno}") from exc
    except RecursionError as exc:  # defensive: the depth guard should win first
        raise DocumentInvalid("<json>", "nests too deeply to parse") from exc
    return parse(payload)


def to_yaml(document: Document) -> str:
    """The document as YAML. Round-trips back to identical canonical bytes.

    The readable form is tried first and *verified*; if any string in the
    document does not survive it — U+0085 is the one that does not — the fully
    escaped form is written instead. A writer that cannot produce a form that
    round-trips refuses rather than emitting a file that reads back different.
    """
    identity = canonical_json(document)
    for allow_unicode in (True, False):
        text = _dump(document, allow_unicode)
        if _round_trips(text, identity):
            return text
    raise DocumentInvalid(
        "<yaml>",
        "cannot be written as YAML that reads back identical. Every admissible "
        "string must survive the round trip; this document contains one that "
        "does not, and emitting it would corrupt the value silently")


def _dump(document: Document, allow_unicode: bool) -> str:
    return yaml.safe_dump(
        to_mapping(document),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=allow_unicode,
        width=100,
    )


def _round_trips(text: str, identity: bytes) -> bool:
    try:
        return canonical_json(from_yaml(text)) == identity
    except DocumentInvalid:
        return False


class _StrictLoader(yaml.SafeLoader):
    """``SafeLoader`` with the two holes a configuration file cares about closed."""

    def compose_node(self, parent, index):  # type: ignore[override]
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            raise DocumentInvalid(
                "<yaml>",
                f"uses the alias '*{event.anchor}'. Aliases are refused: they "
                f"make a small file expand without bound, and they hide what a "
                f"reader thinks the file says. Write the value out")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):  # type: ignore[override]
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                hashable = key in seen
            except TypeError as exc:
                raise DocumentInvalid(
                    "<yaml>", f"uses the unhashable key {key!r}") from exc
            if hashable:
                raise DocumentInvalid(
                    "<yaml>",
                    f"declares the key {key!r} twice in one mapping. YAML "
                    f"would keep the last one silently, so the value you read "
                    f"is not the value the program used")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def from_yaml(text: bytes | str) -> Document:
    """Parse YAML into a validated document, refusing tags, aliases and duplicates."""
    raw = _measure(text, "yaml")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentInvalid("<yaml>", f"is not valid UTF-8: {exc}") from exc
    _refuse_deep_nesting(decoded, "yaml")
    try:
        payload = yaml.load(decoded, Loader=_StrictLoader)
    except DocumentInvalid:
        raise
    except yaml.constructor.ConstructorError as exc:
        raise DocumentInvalid(
            "<yaml>",
            f"asks for a Python object the safe loader will not build "
            f"({exc.problem}). A document is data") from exc
    except yaml.YAMLError as exc:
        raise DocumentInvalid("<yaml>", f"is not valid YAML: {exc}") from exc
    except RecursionError as exc:
        raise DocumentInvalid("<yaml>", "nests too deeply to parse") from exc
    if payload is None:
        raise DocumentInvalid("<yaml>", "is empty")
    return parse(payload)
