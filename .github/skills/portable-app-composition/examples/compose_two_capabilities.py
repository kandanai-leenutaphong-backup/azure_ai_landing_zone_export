#!/usr/bin/env python3
"""Worked example: one document, two independent capabilities, one application.

Run it:

    python3 examples/compose_two_capabilities.py

It goes the whole way round, and asserts at every step rather than printing and
hoping:

1. a person hand-writes YAML;
2. it parses, exports to canonical JSON, and imports back to the same bytes;
3. it composes through a resolver the *caller* owns — the allowlist;
4. the members start in dependency order and answer real requests;
5. they shut down in reverse order, exactly once;
6. the consumer is removed and the application recomposes without it;
7. the provider is removed instead, and the failure names the dependency.
"""

from __future__ import annotations

import json

from appcompose import (  # noqa: E402
    DocumentInvalid,
    allowlist,
    canonical_json,
    compose,
    from_json,
    from_yaml,
)
from appcompose.demo.digest import digest_capability  # noqa: E402
from appcompose.demo.notes import NoteStore, notes_capability  # noqa: E402

DOCUMENT = """
schemaVersion: 1
kind: portable.app-composition
id: field-notes
name: Field notes
description: Two capabilities, one origin, no import between them.
members:
  - id: digest
    capability: notes.digest
    label: Rolling digest
    requires: [store]
    settings:
      limit: 2
  - id: store
    capability: notes.store
    label: Note store
    settings:
      seed:
        - first note
        - second note
layout:
  store:
    slot: main
    order: 1
  digest:
    slot: aside-trailing
    order: 2
    lazy: true
ownership:
  /assets/shared.css: store
"""


def build_resolver(events: list[str]):
    """The caller's allowlist. What is in it composes; what is not, refuses."""
    store = NoteStore()
    return store, allowlist({
        "notes.store": notes_capability(store, title="Notes"),
        "notes.digest": digest_capability(store.all, title="Digest",
                                          events=events),
    })


def main() -> int:
    # 1-2. Author, export, re-import. Canonical bytes are the identity.
    document = from_yaml(DOCUMENT)
    exported = canonical_json(document)
    assert canonical_json(from_json(exported)) == exported, "round trip drifted"
    assert document.order() == ("store", "digest"), document.order()

    # The document lists the consumer first; dependency order is not file order.
    assert [m.id for m in document.members] == ["digest", "store"]

    # 3. Compose through the caller-owned resolver.
    events: list[str] = []
    store, resolve = build_resolver(events)
    app = compose(document, resolve=resolve)
    assert app.member_ids == ("store", "digest"), app.member_ids
    assert app.asset_table == (("/assets/shared.css", "store"),), app.asset_table
    assert app.availability() is True
    assert app.readiness() == (False, "not started"), app.readiness()

    # Placement is a projection of the document, not a second source of truth.
    assert [(mid, p.slot, p.lazy) for mid, p in app.placement()] == [
        ("store", "main", False), ("digest", "aside-trailing", True)]

    # 4. Start, then answer real requests.
    assert app.startup() == ("store", "digest")
    assert app.readiness() == (True, "")
    assert store.opened is True

    listed = app.dispatch("GET", "/api/notes")
    assert listed.status == 200, listed.status
    assert json.loads(listed.body) == {"notes": ["first note", "second note"]}

    created = app.dispatch("POST", "/api/notes",
                           body=json.dumps({"text": "third note"}).encode())
    assert created.status == 201, created.status
    assert json.loads(created.body) == {"id": 2}

    one = app.dispatch("GET", "/api/notes/1")
    assert json.loads(one.body) == {"text": "second note"}

    digest = app.dispatch("GET", "/api/digest")
    assert json.loads(digest.body) == {
        "count": 3, "head": ["first note", "second note"]}, digest.body

    css = app.dispatch("GET", "/assets/shared.css")
    assert css.status == 200 and css.media_type == "text/css"

    assert app.dispatch("GET", "/api/nothing").status == 404
    assert app.dispatch("DELETE", "/api/notes").status == 405

    # 5. Reverse-order shutdown, exactly once.
    assert app.shutdown() == ("digest", "store")
    assert app.shutdown() == ()
    assert store.close_calls == 1, store.close_calls
    assert events == ["digest:startup", "digest:shutdown"], events

    # 6. Remove the consumer; the rest still composes and runs.
    smaller = document.without("digest")
    store2, resolve2 = build_resolver([])
    trimmed = compose(smaller, resolve=resolve2)
    assert trimmed.member_ids == ("store",)
    assert "/api/digest" not in [path for _, path, _ in trimmed.route_table]
    trimmed.startup()
    assert json.loads(trimmed.dispatch("GET", "/api/notes").body)["notes"] == [
        "first note", "second note"]
    trimmed.shutdown()

    # 7. Remove the provider instead. The refusal names the dependency.
    try:
        document.without("store")
    except DocumentInvalid as exc:
        assert exc.field == "members[0].requires[0]", exc.field
        assert "'store'" in exc.detail, exc.detail
    else:  # pragma: no cover - the example fails loudly if this ever happens
        raise AssertionError("removing a required provider must not succeed")

    print("composed, served, torn down and recomposed:", app.member_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
