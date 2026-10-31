#!/usr/bin/env python3
"""selftest.py — proves this skill works here, on a bare interpreter.

No test framework. Run it:

    python3 tests/selftest.py

One line per check, a non-zero exit on any failure, and the two halves of every
round trip driven together — serialise and parse, provider and consumer, start
and stop — because drift lives between halves, never inside one.

The only dependency is the one ``requirements.txt`` declares.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import appcompose  # noqa: E402
from appcompose import (  # noqa: E402
    Asset,
    AssetConflict,
    CapabilityFactoryFailed,
    CapabilityNotAllowed,
    CompositionError,
    Contribution,
    CredentialShaped,
    DocumentInvalid,
    PartialStartup,
    Placement,
    Request,
    Response,
    ResponseInvalid,
    Route,
    RouteConflict,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    ShutdownFailed,
    StartupFailed,
    UnknownMetadata,
    UnsupportedVersion,
    allowlist,
    asgi_app,
    canonical_json,
    compose,
    from_json,
    from_yaml,
    parse,
    plain,
    route_template_error,
    to_mapping,
    to_yaml,
)
from appcompose.demo.digest import digest_capability  # noqa: E402
from appcompose.demo.notes import NoteStore, notes_capability  # noqa: E402
from appcompose.serialisation import MAX_DOCUMENT_BYTES  # noqa: E402

CHECKS: list = []


def check(fn):
    CHECKS.append(fn)
    return fn


def base(**changes) -> dict:
    payload = {
        "schemaVersion": 1,
        "kind": "portable.app-composition",
        "name": "Selftest",
        "members": [{"id": "only", "capability": "demo.one"}],
    }
    payload.update(changes)
    return payload


def expect(kind, fn, *, field=None):
    try:
        fn()
    except kind as exc:
        if field is not None:
            got = getattr(exc, "field", None)
            assert got == field, f"expected field {field!r}, got {got!r} ({exc})"
        return exc
    raise AssertionError(f"expected {kind.__name__}, nothing was raised")


def ok(handler=None):
    def reply(_: Request) -> Response:
        return Response(body=b"ok")
    return handler or reply


# ----------------------------------------------------------------------
# Document: shape, identity, immutability.
# ----------------------------------------------------------------------


@check
def round_trip_is_byte_identical():
    document = parse(base(
        id="app", description="d",
        members=[{"id": "store", "capability": "notes.store",
                  "settings": {"seed": ["a"], "nested": {"z": 1, "a": [1, 2]}}},
                 {"id": "digest", "capability": "notes.digest",
                  "requires": ["store"]}],
        layout={"store": {"slot": "main", "order": 1}},
        ownership={"/assets/shared.css": "store"}))
    canonical = canonical_json(document)
    assert canonical_json(from_json(canonical)) == canonical
    assert canonical_json(from_yaml(to_yaml(document))) == canonical
    assert canonical.endswith(b"\n")


@check
def canonical_bytes_ignore_authoring_order():
    a = parse(base(members=[{"id": "only", "capability": "demo.one",
                             "settings": {"b": 1, "a": 2}}]))
    b = parse(base(members=[{"capability": "demo.one", "id": "only",
                             "settings": {"a": 2, "b": 1}}]))
    assert canonical_json(a) == canonical_json(b)


@check
def omitted_blocks_stay_omitted():
    payload = to_mapping(parse(base()))
    assert "layout" not in payload and "ownership" not in payload
    assert "description" not in payload and "id" not in payload


@check
def parsing_deep_copies_its_input():
    payload = base(members=[{"id": "only", "capability": "demo.one",
                             "settings": {"seed": ["a"]}}])
    document = parse(payload)
    payload["members"][0]["settings"]["seed"].append("b")
    payload["name"] = "changed"
    assert document.name == "Selftest"
    assert document.member("only").settings["seed"] == ("a",)


@check
def stored_settings_are_immutable_and_copyable():
    document = parse(base(members=[{"id": "only", "capability": "demo.one",
                                    "settings": {"seed": ["a"], "n": {"k": 1}}}]))
    settings = document.member("only").settings

    def assign_top():
        settings["seed"] = []

    def assign_nested():
        settings["n"]["k"] = 2

    expect(TypeError, assign_top)
    expect(TypeError, assign_nested)
    mutable = document.member("only").settings_copy()
    mutable["n"]["k"] = 99
    assert document.member("only").settings["n"]["k"] == 1
    assert plain(settings) == {"seed": ["a"], "n": {"k": 1}}


@check
def placement_defaults_are_neutral():
    document = parse(base(layout={"only": {"slot": "main", "lazy": True}}))
    assert document.placement("only") == Placement("main", 0, True)
    assert parse(base()).placement("only") == Placement()


# ----------------------------------------------------------------------
# Document: refusals.
# ----------------------------------------------------------------------


@check
def version_is_checked_before_anything_else():
    for value, kind in ((None, UnsupportedVersion), ("1", UnsupportedVersion),
                        (True, UnsupportedVersion), (1.0, UnsupportedVersion)):
        payload = base()
        payload["schemaVersion"] = value
        expect(kind, lambda p=payload: parse(p), field="schemaVersion")
    payload = base()
    del payload["schemaVersion"]
    expect(UnsupportedVersion, lambda: parse(payload), field="schemaVersion")
    newer = expect(UnsupportedVersion, lambda: parse(base(schemaVersion=99)))
    assert "newer release" in newer.detail and newer.supported == (1,)
    older = expect(UnsupportedVersion, lambda: parse(base(schemaVersion=0)))
    assert "predates" in older.detail


@check
def kind_and_types_are_checked():
    expect(DocumentInvalid, lambda: parse(base(kind="something.else")),
           field="kind")
    expect(DocumentInvalid, lambda: parse(base(members={})), field="members")
    expect(DocumentInvalid, lambda: parse(base(name=7)), field="name")
    expect(DocumentInvalid, lambda: parse(base(name="a\nb")), field="name")
    expect(DocumentInvalid, lambda: parse(base(layout=[])), field="layout")
    expect(DocumentInvalid, lambda: parse("not a mapping"), field="<document>")


@check
def unknown_keys_refuse_and_executable_keys_explain():
    expect(DocumentInvalid, lambda: parse(base(extra=1)), field="extra")
    exc = expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one", "module": "os"}])),
        field="members[0].module")
    assert "never code" in exc.detail
    for key in ("entrypoint", "callable", "factory", "plugin", "command"):
        expect(DocumentInvalid, lambda k=key: parse(base(members=[
            {"id": "only", "capability": "demo.one", k: "x"}])),
            field=f"members[0].{key}")


@check
def ids_are_unique_and_shaped():
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one"},
        {"id": "only", "capability": "demo.two"}])), field="members[1].id")
    for bad in ("", "a", "_lead", "has space", "path/segment", "x" * 65):
        expect(DocumentInvalid, lambda b=bad: parse(base(members=[
            {"id": b, "capability": "demo.one"}])), field="members[0].id")
    for bad in ("Demo.One", "", "x"):
        expect(DocumentInvalid, lambda b=bad: parse(base(members=[
            {"id": "only", "capability": b}])), field="members[0].capability")


@check
def references_must_resolve_and_not_cycle():
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one", "requires": ["ghost"]}])),
        field="members[0].requires[0]")
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one", "requires": ["only"]}])),
        field="members[0].requires[0]")
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one"},
        {"id": "other", "capability": "demo.two", "requires": ["only", "only"]}])),
        field="members[1].requires[1]")
    exc = expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "aaa", "capability": "demo.one", "requires": ["bbb"]},
        {"id": "bbb", "capability": "demo.two", "requires": ["ccc"]},
        {"id": "ccc", "capability": "demo.three", "requires": ["aaa"]}])),
        field="members")
    assert "aaa -> bbb -> ccc -> aaa" in exc.detail, exc.detail
    expect(DocumentInvalid, lambda: parse(base(layout={"ghost": {}})),
           field="layout.ghost")
    expect(DocumentInvalid,
           lambda: parse(base(ownership={"/assets/a.css": "ghost"})),
           field="ownership['/assets/a.css']")


@check
def dependency_order_is_deterministic():
    members = [{"id": "last", "capability": "demo.c", "requires": ["mid"]},
               {"id": "mid", "capability": "demo.b", "requires": ["first"]},
               {"id": "first", "capability": "demo.a"}]
    assert parse(base(members=members)).order() == ("first", "mid", "last")
    independent = parse(base(members=[
        {"id": "bbb", "capability": "demo.b"},
        {"id": "aaa", "capability": "demo.a"}]))
    assert independent.order() == ("bbb", "aaa")  # document order breaks ties


@check
def bounds_are_finite():
    many = [{"id": f"m{n:03d}", "capability": "demo.one"} for n in range(65)]
    expect(DocumentInvalid, lambda: parse(base(members=many)), field="members")
    expect(DocumentInvalid, lambda: parse(base(name="x" * 121)), field="name")
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one",
         "settings": {"blob": "x" * 20000}}])), field="members[0].settings")
    deep = {"k": 1}
    for _ in range(12):
        deep = {"k": deep}
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one", "settings": deep}])))
    oversize = b'{"padding":"' + b"x" * (MAX_DOCUMENT_BYTES + 10) + b'"}'
    expect(DocumentInvalid, lambda: from_json(oversize), field="<json>")
    expect(DocumentInvalid, lambda: from_yaml(oversize.decode()), field="<yaml>")


@check
def non_finite_numbers_are_refused():
    expect(DocumentInvalid, lambda: from_json(
        '{"schemaVersion":1,"kind":"portable.app-composition","name":"A",'
        '"members":[{"id":"only","capability":"demo.one",'
        '"settings":{"r":Infinity}}]}'), field="<json>")
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one",
         "settings": {"r": float("nan")}}])), field="members[0].settings.r")
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one",
         "settings": {"r": {1, 2}}}])), field="members[0].settings.r")


@check
def credential_shapes_are_refused_and_references_are_not():
    for key in ("api_key", "apiKey", "password", "clientSecret",
                "connection_string", "sasToken", "private_key"):
        expect(CredentialShaped, lambda k=key: parse(base(members=[
            {"id": "only", "capability": "demo.one",
             "settings": {k: "abcdef123456"}}])),
            field=f"members[0].settings.{key}")
    allowed = parse(base(members=[{"id": "only", "capability": "demo.one",
                                   "settings": {"api_key": "${VAULT_REF}",
                                                "secret_name": "env:TOKEN_NAME"}}]))
    assert allowed.member("only").settings["api_key"] == "${VAULT_REF}"


# ----------------------------------------------------------------------
# Serialisation.
# ----------------------------------------------------------------------


@check
def yaml_refuses_duplicates_aliases_and_tags():
    head = "schemaVersion: 1\nkind: portable.app-composition\n"
    exc = expect(DocumentInvalid, lambda: from_yaml(
        head + "name: A\nname: B\nmembers: []\n"), field="<yaml>")
    assert "twice" in exc.detail
    exc = expect(DocumentInvalid, lambda: from_yaml(
        head + "name: &a Selftest\ndescription: *a\nmembers: []\n"),
        field="<yaml>")
    assert "alias" in exc.detail
    expect(DocumentInvalid, lambda: from_yaml(
        head + "name: !!python/object/apply:os.system ['echo hi']\n"
               "members: []\n"), field="<yaml>")
    expect(DocumentInvalid, lambda: from_yaml("name: [unclosed\n"),
           field="<yaml>")
    expect(DocumentInvalid, lambda: from_yaml(""), field="<yaml>")
    expect(DocumentInvalid, lambda: from_json(b"\xff\xfe"), field="<json>")
    expect(DocumentInvalid, lambda: from_json("{oops}"), field="<json>")


@check
def yaml_billion_laughs_cannot_expand():
    bomb = ("schemaVersion: 1\nkind: portable.app-composition\nname: A\n"
            "a: &a [x,x,x,x,x,x,x,x,x]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
            "c: [*b,*b,*b,*b,*b,*b,*b,*b,*b]\nmembers: []\n")
    expect(DocumentInvalid, lambda: from_yaml(bomb), field="<yaml>")


@check
def asset_paths_cannot_traverse():
    for bad in ("/assets/../etc/passwd", "assets/a.css", "/assets//a.css",
                "/assets/./a.css", "/assets\\a.css", "/assets/a\x00.css",
                "/" + "x" * 300):
        expect(DocumentInvalid, lambda b=bad: parse(base(ownership={b: "only"})))


# ----------------------------------------------------------------------
# Composition.
# ----------------------------------------------------------------------


@check
def resolver_is_the_allowlist():
    document = parse(base())
    exc = expect(CapabilityNotAllowed,
                 lambda: compose(document, resolve=allowlist({})))
    assert exc.member == "only" and exc.capability == "demo.one"

    def raiser(capability, member):
        raise KeyError(capability)
    expect(CapabilityNotAllowed, lambda: compose(document, resolve=raiser))

    def wrong(capability, member):
        return "not a contribution"
    expect(CompositionError, lambda: compose(document, resolve=wrong))
    expect(TypeError, lambda: compose(document, resolve="nope"))

    def explodes(capability, member):
        raise ValueError("the caller's own failure")
    expect(ValueError, lambda: compose(document, resolve=explodes))


@check
def route_ownership_is_explicit():
    two = parse(base(members=[{"id": "alpha", "capability": "demo.a"},
                              {"id": "beta", "capability": "demo.b"}]))
    def build(method, path):
        return lambda m: Contribution(routes=(Route(method, path, ok()),))
    exc = expect(RouteConflict, lambda: compose(two, resolve=allowlist({
        "demo.a": build("GET", "/items/{id}"),
        "demo.b": build("GET", "/items/{key}")})))
    assert exc.members == ("alpha", "beta") and exc.path == "/items/{}"
    expect(RouteConflict, lambda: compose(two, resolve=allowlist({
        "demo.a": build("get", "/api/x"), "demo.b": build("GET", "/api/x")})))
    shared = compose(two, resolve=allowlist({
        "demo.a": build("GET", "/api/x"), "demo.b": build("POST", "/api/x")}))
    assert len(shared.route_table) == 2
    expect(CompositionError, lambda: compose(two, resolve=allowlist({
        "demo.a": build("FETCH", "/api/x"), "demo.b": build("GET", "/api/y")})))
    expect(CompositionError, lambda: compose(two, resolve=allowlist({
        "demo.a": build("GET", "/api/../x"), "demo.b": build("GET", "/api/y")})))


@check
def asset_ownership_is_explicit():
    asset = Asset("/assets/app.css", b"body{}\n", "text/css")
    contributions = {"demo.a": lambda m: Contribution(assets=(asset,)),
                     "demo.b": lambda m: Contribution(assets=(asset,))}
    members = [{"id": "alpha", "capability": "demo.a"},
               {"id": "beta", "capability": "demo.b"}]
    expect(AssetConflict, lambda: compose(parse(base(members=members)),
                                          resolve=allowlist(contributions)))
    owned = compose(parse(base(members=members,
                               ownership={"/assets/app.css": "beta"})),
                    resolve=allowlist(contributions))
    assert owned.asset_table == (("/assets/app.css", "beta"),)
    expect(CompositionError, lambda: compose(
        parse(base(members=members, ownership={"/assets/other.css": "beta"})),
        resolve=allowlist(contributions)))
    expect(CompositionError, lambda: compose(
        parse(base(ownership={"/assets/app.css": "only"})),
        resolve=allowlist({"demo.one": lambda m: Contribution(
            routes=(Route("GET", "/assets/app.css", ok()),),
            assets=(asset,))})))


@check
def contribution_metadata_is_closed():
    document = parse(base())
    exc = expect(UnknownMetadata, lambda: compose(document, resolve=allowlist(
        {"demo.one": lambda m: Contribution(metadata={"slot": "main"})})))
    assert exc.keys == ("slot",)
    expect(CompositionError, lambda: compose(document, resolve=allowlist(
        {"demo.one": lambda m: Contribution(metadata={"title": 3})})))
    fine = compose(document, resolve=allowlist(
        {"demo.one": lambda m: Contribution(metadata={"title": "Only"})}))
    assert fine.members[0].title == "Only"


# ----------------------------------------------------------------------
# Lifecycle.
# ----------------------------------------------------------------------


def _lifecycle_document():
    return parse(base(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]},
        {"id": "third", "capability": "demo.c", "requires": ["second"]}]))


@check
def startup_is_ordered_and_shutdown_is_reversed():
    log: list[str] = []

    def member(name, fail_start=False, fail_stop=False):
        def build(m):
            def start():
                if fail_start:
                    raise RuntimeError(f"{name} cannot start")
                log.append(f"start:{name}")

            def stop():
                if fail_stop:
                    raise RuntimeError(f"{name} cannot stop")
                log.append(f"stop:{name}")
            return Contribution(startup=start, shutdown=stop)
        return build

    app = compose(_lifecycle_document(), resolve=allowlist({
        "demo.a": member("first"), "demo.b": member("second"),
        "demo.c": member("third")}))
    assert app.availability() is True
    assert app.readiness() == (False, "not started")
    assert app.startup() == ("first", "second", "third")
    assert app.readiness() == (True, "")
    assert log == ["start:first", "start:second", "start:third"]
    expect(CompositionError, app.startup)
    assert app.shutdown() == ("third", "second", "first")
    assert log[-3:] == ["stop:third", "stop:second", "stop:first"]
    assert app.shutdown() == ()                       # exactly once
    assert log.count("stop:first") == 1
    assert app.readiness() == (False, "not started")


@check
def startup_failure_rolls_back_and_can_be_retried():
    stopped: list[str] = []
    state = {"fail": True}

    def flaky(m):
        def start():
            if state["fail"]:
                raise RuntimeError("second cannot start")
        return Contribution(startup=start)

    def good(name):
        return lambda m: Contribution(shutdown=lambda: stopped.append(name))

    app = compose(_lifecycle_document(), resolve=allowlist({
        "demo.a": good("first"), "demo.b": flaky, "demo.c": good("third")}))
    exc = expect(StartupFailed, app.startup)
    assert exc.member == "second" and exc.rolled_back == ("first",)
    assert stopped == ["first"], stopped
    assert app.readiness() == (False, "not started")
    state["fail"] = False
    assert app.startup() == ("first", "second", "third")
    app.shutdown()


@check
def rollback_failure_is_reported_not_swallowed():
    def bad_stop(m):
        def stop():
            raise RuntimeError("stuck")
        return Contribution(shutdown=stop)

    def bad_start(m):
        def start():
            raise RuntimeError("no")
        return Contribution(startup=start)

    document = parse(base(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
    app = compose(document, resolve=allowlist({"demo.a": bad_stop,
                                               "demo.b": bad_start}))
    exc = expect(StartupFailed, app.startup)
    assert exc.rolled_back == () and exc.rollback_failures[0][0] == "first"
    assert "stuck" in exc.rollback_failures[0][1]


@check
def shutdown_continues_past_a_failure_and_then_reports():
    stopped: list[str] = []

    def member(name, fail=False):
        def build(m):
            def stop():
                if fail:
                    raise RuntimeError(f"{name} stuck")
                stopped.append(name)
            return Contribution(shutdown=stop)
        return build

    app = compose(_lifecycle_document(), resolve=allowlist({
        "demo.a": member("first"), "demo.b": member("second", fail=True),
        "demo.c": member("third")}))
    app.startup()
    exc = expect(ShutdownFailed, app.shutdown)
    assert stopped == ["third", "first"], stopped     # the failure stopped nothing
    assert exc.failures[0][0] == "second"
    assert app.shutdown() == ()


@check
def shutdown_before_startup_is_a_noop():
    app = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(
            shutdown=lambda: (_ for _ in ()).throw(AssertionError("ran")))}))
    assert app.shutdown() == ()


@check
def context_manager_starts_and_stops():
    log: list[str] = []
    app = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(startup=lambda: log.append("up"),
                                           shutdown=lambda: log.append("down"))}))
    with app as running:
        assert running.readiness() == (True, "")
    assert log == ["up", "down"]


# ----------------------------------------------------------------------
# Dispatch.
# ----------------------------------------------------------------------


@check
def dispatch_routes_and_refuses():
    def build(m):
        def item(request: Request) -> Response:
            return Response(body=f"item {request.params['id']}".encode())

        def new(_: Request) -> Response:
            return Response(body=b"new")

        def create(request: Request) -> Response:
            return Response(status=201, body=request.body)
        return Contribution(
            routes=(Route("GET", "/items/{id}", item),
                    Route("GET", "/items/new", new),
                    Route("POST", "/items", create)),
            assets=(Asset("/assets/a.css", b"css\n", "text/css"),))

    app = compose(parse(base()), resolve=allowlist({"demo.one": build}))
    app.startup()
    assert app.dispatch("GET", "/items/new").body == b"new"   # static wins
    assert app.dispatch("GET", "/items/7").body == b"item 7"
    assert app.dispatch("get", "/items/7").status == 200      # case-insensitive
    assert app.dispatch("POST", "/items", body=b"x").status == 201
    missing = app.dispatch("GET", "/nope")
    assert missing.status == 404 and b"no route" in missing.body
    wrong = app.dispatch("DELETE", "/items")
    assert wrong.status == 405 and wrong.headers["Allow"] == "POST"
    asset = app.dispatch("GET", "/assets/a.css")
    assert asset.status == 200 and asset.media_type == "text/css"
    head = app.dispatch("HEAD", "/assets/a.css")
    assert head.status == 200 and head.body == b""
    assert app.dispatch("POST", "/assets/a.css").status == 405
    assert app.dispatch("GET", "/items").status == 405
    app.shutdown()


# ----------------------------------------------------------------------
# The round trip that matters: publisher and consumer, driven together.
# ----------------------------------------------------------------------


@check
def provider_and_consumer_round_trip_from_a_written_document():
    text = (
        "schemaVersion: 1\n"
        "kind: portable.app-composition\n"
        "name: Field notes\n"
        "members:\n"
        "  - id: digest\n"
        "    capability: notes.digest\n"
        "    requires: [store]\n"
        "    settings: {limit: 1}\n"
        "  - id: store\n"
        "    capability: notes.store\n"
        "    settings: {seed: [one, two]}\n"
        "ownership:\n"
        "  /assets/shared.css: store\n"
    )
    document = from_json(canonical_json(from_yaml(text)))
    store = NoteStore()
    events: list[str] = []
    app = compose(document, resolve=allowlist({
        "notes.store": notes_capability(store),
        "notes.digest": digest_capability(store.all, events=events)}))
    assert app.member_ids == ("store", "digest")
    app.startup()
    assert json.loads(app.dispatch("GET", "/api/notes").body)["notes"] == [
        "one", "two"]
    assert json.loads(app.dispatch("GET", "/api/digest").body) == {
        "count": 2, "head": ["one"]}
    created = app.dispatch("POST", "/api/notes", body=b'{"text":"three"}')
    assert created.status == 201
    assert json.loads(app.dispatch("GET", "/api/notes/2").body) == {
        "text": "three"}
    assert app.dispatch("POST", "/api/notes", body=b"not json").status == 400
    assert app.dispatch("GET", "/api/notes/xyz").status == 400
    assert app.dispatch("GET", "/api/notes/99").status == 404
    app.shutdown()
    assert store.close_calls == 1 and events == ["digest:startup",
                                                 "digest:shutdown"]


@check
def removing_a_consumer_recomposes_and_removing_a_provider_names_the_dependency():
    document = parse(base(members=[
        {"id": "store", "capability": "notes.store"},
        {"id": "digest", "capability": "notes.digest", "requires": ["store"]}],
        layout={"digest": {"slot": "aside"}},
        ownership={"/assets/shared.css": "store"}))
    smaller = document.without("digest")
    assert [m.id for m in smaller.members] == ["store"]
    assert "digest" not in smaller.layout
    store = NoteStore()
    app = compose(smaller, resolve=allowlist({
        "notes.store": notes_capability(store)}))
    app.startup()
    assert app.dispatch("GET", "/api/digest").status == 404
    app.shutdown()
    # The consumer is members[0] once the provider is gone; the field path is
    # the path in the *resulting* document, which is the one you would edit.
    exc = expect(DocumentInvalid, lambda: document.without("store"),
                 field="members[0].requires[0]")
    assert "'store'" in exc.detail
    expect(KeyError, lambda: document.without("ghost"))


@check
def a_consumer_composed_without_its_provider_started_fails_loudly():
    # The order guarantee is only worth having if breaking it is observable.
    store = NoteStore()
    document = parse(base(members=[
        {"id": "digest", "capability": "notes.digest"}]))
    app = compose(document, resolve=allowlist({
        "notes.digest": digest_capability(store.all)}))
    exc = expect(StartupFailed, app.startup)
    assert isinstance(exc.cause, RuntimeError)
    assert "not open" in str(exc.cause)


@check
def demo_capability_rejects_bad_settings_at_compose_time():
    document = parse(base(members=[{"id": "digest", "capability": "notes.digest",
                                    "settings": {"limit": 0}}]))
    expect(ValueError, lambda: compose(document, resolve=allowlist({
        "notes.digest": digest_capability(NoteStore().all)})))


# ----------------------------------------------------------------------
# Encoding: every admissible string, not every ASCII string.
# ----------------------------------------------------------------------

#: The characters a serialiser loses quietly. U+0085 is the one that actually
#: broke: safe_dump wrote it raw and the loader folded it back to a space.
AWKWARD = ("a\u0085b", "a\u2028b", "a\u2029b", "a\tb", "a\r\nb", "a\rb",
           "a\nb", "a\u00a0b", "e\U0001F600e", "e\U00020000e", "  padded  ",
           "\u0085", "trailing\u0085")


@check
def round_trip_survives_every_admissible_string():
    for probe in AWKWARD:
        document = parse(base(
            description=probe,
            members=[{"id": "only", "capability": "demo.one",
                      "settings": {"v": probe, "n": {"deep": [probe, {"k": probe}]}}}]))
        identity = canonical_json(document)
        assert canonical_json(from_json(identity)) == identity, repr(probe)
        assert canonical_json(from_yaml(to_yaml(document))) == identity, repr(probe)
        assert from_yaml(to_yaml(document)).description == probe, repr(probe)
    # `name` admits every non-control character, U+0085 among them.
    for probe in ("n\u0085m", "n\u2028m", "n\u00a0m", "n\U0001F600m"):
        document = parse(base(name=probe))
        assert from_yaml(to_yaml(document)).name == probe, repr(probe)


@check
def deeply_nested_and_cyclic_inputs_name_their_field():
    expect(DocumentInvalid, lambda: from_json('{"a":' * 6000 + "1" + "}" * 6000),
           field="<json>")
    expect(DocumentInvalid, lambda: from_yaml("[" * 6000 + "]" * 6000),
           field="<yaml>")
    expect(DocumentInvalid, lambda: from_yaml("a: " + "[" * 100 + "]" * 100),
           field="<yaml>")
    nested: dict = {"k": 1}
    for _ in range(40):
        nested = {"k": nested}
    expect(DocumentInvalid, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one", "settings": nested}])))
    cyclic: dict = base()
    cyclic["members"][0]["settings"] = cyclic
    exc = expect(DocumentInvalid, lambda: parse(cyclic))
    assert "cycle" in exc.detail or "nests deeper" in exc.detail, exc.detail


@check
def a_credential_key_cannot_hide_behind_a_list_or_an_object():
    for value in (["AbCdEf0123456789"], {"v": "AbCdEf0123456789"},
                  ("AbCdEf0123456789",), 1234567890123, True):
        expect(CredentialShaped, lambda v=value: parse(base(members=[
            {"id": "only", "capability": "demo.one",
             "settings": {"api_key": v}}])),
            field="members[0].settings.api_key")
    expect(CredentialShaped, lambda: parse(base(members=[
        {"id": "only", "capability": "demo.one",
         "settings": {"nested": {"client_secret": ["AbCdEf0123456789"]}}}])),
        field="members[0].settings.nested.client_secret")
    # The documented value forms still pass: a reference, blank, or null.
    fine = parse(base(members=[{"id": "only", "capability": "demo.one",
                                "settings": {"api_key": "${VAULT}",
                                             "password": "",
                                             "access_token": None}}]))
    assert fine.member("only").settings["password"] == ""


# ----------------------------------------------------------------------
# Lifecycle: the state after a rollback that itself failed.
# ----------------------------------------------------------------------


@check
def a_failed_rollback_latches_and_refuses_a_second_startup():
    log: list[str] = []
    state = {"fail": True}

    def stuck(m):
        def stop():
            raise RuntimeError("stuck")
        return Contribution(startup=lambda: log.append("start:first"),
                            shutdown=stop)

    def flaky(m):
        def start():
            if state["fail"]:
                raise RuntimeError("second cannot start")
            log.append("start:second")
        return Contribution(startup=start)

    document = parse(base(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
    app = compose(document, resolve=allowlist({"demo.a": stuck, "demo.b": flaky}))
    exc = expect(StartupFailed, app.startup)
    assert exc.rolled_back == () and exc.rollback_failures[0][0] == "first"
    assert app.unsafe_state() == exc.rollback_failures
    assert app.availability() is False       # the honest half says so too
    assert app.readiness() == (False, "unsafe: stop failed for ['first']")

    state["fail"] = False
    refusal = expect(CompositionError, app.startup)
    assert "first" in str(refusal) and "twice" in str(refusal)
    assert log == ["start:first"], log       # not started a second time

    expect(CompositionError, lambda: app.clear_unsafe_state(resolved=[]))
    expect(CompositionError, lambda: app.clear_unsafe_state(resolved=["second"]))
    assert app.unsafe_state() != ()
    app.clear_unsafe_state(resolved=["first"])
    assert app.unsafe_state() == () and app.availability() is True
    assert app.startup() == ("first", "second")
    assert log == ["start:first", "start:first", "start:second"]
    expect(ShutdownFailed, app.shutdown)


@check
def a_clean_rollback_leaves_nothing_latched():
    stopped: list[str] = []
    document = parse(base(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
    app = compose(document, resolve=allowlist({
        "demo.a": lambda m: Contribution(shutdown=lambda: stopped.append("first")),
        "demo.b": lambda m: Contribution(
            startup=lambda: (_ for _ in ()).throw(RuntimeError("no")))}))
    expect(StartupFailed, app.startup)
    assert app.unsafe_state() == () and app.availability() is True
    assert stopped == ["first"]
    expect(CompositionError, lambda: app.clear_unsafe_state(resolved=[]))


@check
def a_failed_shutdown_latches_and_refuses_a_second_startup():
    # The same hazard as a failed rollback, reached by the other door: the
    # composition started cleanly, then could not stop a member. Starting again
    # would start that member twice.
    log: list[str] = []

    def stuck(m):
        def stop():
            raise RuntimeError("port still held")
        return Contribution(startup=lambda: log.append("start:first"),
                            shutdown=stop)

    def clean(m):
        return Contribution(startup=lambda: log.append("start:second"),
                            shutdown=lambda: log.append("stop:second"))

    document = parse(base(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
    app = compose(document, resolve=allowlist({"demo.a": stuck, "demo.b": clean}))
    assert app.startup() == ("first", "second")

    exc = expect(ShutdownFailed, app.shutdown)
    assert exc.failures[0][0] == "first" and "port still held" in exc.failures[0][1]
    # Every other member still stopped: shutdown does not abandon the sweep.
    assert log == ["start:first", "start:second", "stop:second"], log

    assert app.unsafe_state() == exc.failures
    assert app.availability() is False
    assert app.readiness() == (False, "unsafe: stop failed for ['first']")

    refusal = expect(CompositionError, app.startup)
    assert "first" in str(refusal) and "twice" in str(refusal)
    assert log == ["start:first", "start:second", "stop:second"], log

    # Recovery is the operator naming exactly what they released, as before.
    expect(CompositionError, lambda: app.clear_unsafe_state(resolved=["second"]))
    app.clear_unsafe_state(resolved=["first"])
    assert app.startup() == ("first", "second")
    expect(ShutdownFailed, app.shutdown)


@check
def a_clean_shutdown_latches_nothing():
    document = parse(base(members=[{"id": "only", "capability": "demo.one"}]))
    app = compose(document, resolve=allowlist({
        "demo.one": lambda m: Contribution(startup=lambda: None,
                                           shutdown=lambda: None)}))
    app.startup()
    assert app.shutdown() == ("only",)
    assert app.unsafe_state() == () and app.availability() is True
    assert app.shutdown() == ()
    assert app.startup() == ("only",)      # a clean stop may be started again
    app.shutdown()


@check
def an_interrupt_in_a_lifecycle_hook_is_re_raised_not_wrapped():
    # A caller who pressed Ctrl-C must not have to catch StartupFailed to be
    # interrupted, and the member that was mid-hook must not go unreported.
    for interrupt in (KeyboardInterrupt, SystemExit):
        stopped: list[str] = []

        def boom():
            raise interrupt()

        document = parse(base(members=[
            {"id": "first", "capability": "demo.a"},
            {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
        app = compose(document, resolve=allowlist({
            "demo.a": lambda m: Contribution(
                shutdown=lambda: stopped.append("first")),
            "demo.b": lambda m: Contribution(startup=boom)}))
        expect(interrupt, app.startup)
        assert not isinstance(expect(CompositionError, app.startup), StartupFailed)
        assert stopped == ["first"], stopped       # cleanup still ran
        latched = dict(app.unsafe_state())
        assert list(latched) == ["second"], latched
        assert interrupt.__name__ in latched["second"], latched

    # In shutdown, every remaining hook still runs and then the interrupt wins.
    order: list[str] = []

    def interrupting():
        order.append("stop:second")
        raise KeyboardInterrupt()

    document = parse(base(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
    app = compose(document, resolve=allowlist({
        "demo.a": lambda m: Contribution(shutdown=lambda: order.append("stop:first")),
        "demo.b": lambda m: Contribution(shutdown=interrupting)}))
    app.startup()
    expect(KeyboardInterrupt, app.shutdown)
    assert order == ["stop:second", "stop:first"], order
    assert dict(app.unsafe_state()).keys() == {"second"}
    expect(CompositionError, app.startup)


@check
def a_startup_hook_that_kept_resources_says_so_and_is_latched():
    def cannot_unwind():
        raise PartialStartup("child process 4141 would not die")

    document = parse(base(members=[{"id": "only", "capability": "demo.one"}]))
    app = compose(document, resolve=allowlist({
        "demo.one": lambda m: Contribution(startup=cannot_unwind)}))
    exc = expect(StartupFailed, app.startup)
    assert exc.left_behind == (("only",
                                "startup left resources behind: child process "
                                "4141 would not die"),)
    assert app.unsafe_state() == exc.left_behind
    assert app.availability() is False
    expect(CompositionError, app.startup)
    app.clear_unsafe_state(resolved=["only"])
    assert app.availability() is True

    # A hook that cleaned up after itself latches nothing: the ordinary case.
    tidy = compose(document, resolve=allowlist({
        "demo.one": lambda m: Contribution(
            startup=lambda: (_ for _ in ()).throw(RuntimeError("no")))}))
    exc = expect(StartupFailed, tidy.startup)
    assert exc.left_behind == () and tidy.unsafe_state() == ()


@check
def asynchronous_hooks_and_handlers_are_refused_not_dropped():
    async def never_awaited() -> None:
        raise AssertionError("this coroutine must never run")

    app = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(startup=never_awaited)}))
    exc = expect(StartupFailed, app.startup)
    assert "awaitable" in str(exc.cause), exc.cause

    async def handler(_: Request):
        return Response(body=b"never")

    served = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(
            routes=(Route("GET", "/x", handler),))}))
    served.startup()
    exc = expect(CompositionError, lambda: served.dispatch("GET", "/x"))
    assert "awaitable" in str(exc)
    served.shutdown()


@check
def a_handler_that_returns_the_wrong_type_names_its_member():
    app = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(
            routes=(Route("GET", "/x", lambda r: "a string"),))}))
    app.startup()
    exc = expect(CompositionError, lambda: app.dispatch("GET", "/x"))
    assert "only" in str(exc) and "expected Response" in str(exc)
    app.shutdown()


# ----------------------------------------------------------------------
# Dispatch: the running window, HEAD, and template bounds.
# ----------------------------------------------------------------------


def _one_route(method="GET", path="/x", handler=None):
    return compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(
            routes=(Route(method, path, handler or ok()),))}))


@check
def dispatch_serves_only_inside_the_running_window():
    app = _one_route()
    before = app.dispatch("GET", "/x")
    assert before.status == 503 and b"not started" in before.body
    app.startup()
    assert app.dispatch("GET", "/x").status == 200
    app.shutdown()
    after = app.dispatch("GET", "/x")
    assert after.status == 503, after
    assert app.dispatch("HEAD", "/x").status == 503
    assert app.dispatch("GET", "/nope").status == 503   # closed before routed


@check
def head_is_served_wherever_get_is():
    def body(_: Request) -> Response:
        return Response(body=b"handler")

    app = _one_route(handler=body)
    app.startup()
    head = app.dispatch("HEAD", "/x")
    assert head.status == 200 and head.body == b""
    assert head.headers["Content-Length"] == "7", dict(head.headers)
    for status, path in ((404, "/nope"), (200, "/x")):
        assert app.dispatch("HEAD", path).status == status
    missing = app.dispatch("HEAD", "/nope")
    assert missing.body == b"" and int(missing.headers["Content-Length"]) > 0
    wrong = app.dispatch("POST", "/x")
    assert wrong.status == 405 and wrong.headers["Allow"] == "GET, HEAD"
    app.shutdown()

    explicit = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(routes=(
            Route("GET", "/x", body),
            Route("HEAD", "/x", lambda r: Response(status=204,
                                                   headers={"X-Head": "yes"}))))}))
    explicit.startup()
    served = explicit.dispatch("HEAD", "/x")
    assert served.status == 204 and served.headers["X-Head"] == "yes"
    explicit.shutdown()


@check
def route_templates_have_a_stated_syntax():
    for bad in ("/a/{p}c", "/a/x{p}", "/a/{p}{q}", "/a/{}", "/a/{1p}",
                "/{p}/{p}", "/a/{p/q}"):
        exc = expect(CompositionError,
                     lambda b=bad: _one_route(path=b))
        assert "route" in str(exc), (bad, exc)
    for good in ("/a/{p}", "/{p}", "/a/b", "/a/{p}/b/{q}"):
        _one_route(path=good)
    assert route_template_error("/a/{p}c").startswith("segment")
    assert route_template_error("/a/{p}") == ""


@check
def overlapping_templates_are_ordered_by_specificity_or_refused():
    two = parse(base(members=[{"id": "alpha", "capability": "demo.a"},
                              {"id": "beta", "capability": "demo.b"}]))

    def build(*routes):
        return lambda m: Contribution(routes=routes)

    # Crossing templates: neither is more specific, so declaration order would
    # decide. Refused, in either declaration order.
    for first, second in (("/{a}/y", "/x/{b}"), ("/x/{b}", "/{a}/y")):
        exc = expect(RouteConflict, lambda f=first, s=second: compose(
            two, resolve=allowlist({"demo.a": build(Route("GET", f, ok())),
                                    "demo.b": build(Route("GET", s, ok()))})))
        assert "neither is more specific" in str(exc), exc
        assert "x/y" in str(exc), exc          # a checkable witness path

    # Nested but ordered: the literal dominates segment by segment, so the rule
    # decides and the declaration order does not.
    for order in (("/items/{id}", "/items/new"), ("/items/new", "/items/{id}")):
        app = compose(two, resolve=allowlist({
            "demo.a": build(Route("GET", order[0],
                                  lambda r: Response(body=order[0].encode()))),
            "demo.b": build(Route("GET", order[1],
                                  lambda r: Response(body=order[1].encode())))}))
        app.startup()
        assert app.dispatch("GET", "/items/new").body == b"/items/new"
        assert app.dispatch("GET", "/items/7").body == b"/items/{id}"
        app.shutdown()

    # Different methods never overlap, and neither do different lengths.
    compose(two, resolve=allowlist({"demo.a": build(Route("GET", "/{a}/y", ok())),
                                    "demo.b": build(Route("POST", "/x/{b}", ok()))}))
    compose(two, resolve=allowlist({"demo.a": build(Route("GET", "/{a}/y", ok())),
                                    "demo.b": build(Route("GET", "/x/{b}/z", ok()))}))


@check
def an_asset_cannot_shadow_any_route_it_would_match():
    two = parse(base(members=[{"id": "alpha", "capability": "demo.a"},
                              {"id": "beta", "capability": "demo.b"}]))
    asset = Asset("/files/a.txt", b"asset-bytes", "text/plain")
    for template in ("/files/{name}", "/files/a.txt", "/{section}/{name}"):
        exc = expect(CompositionError, lambda t=template: compose(two, resolve=allowlist({
            "demo.a": lambda m, t=t: Contribution(routes=(Route("GET", t, ok()),)),
            "demo.b": lambda m: Contribution(assets=(asset,))})))
        assert "shadow" in str(exc), (template, exc)
    # A route it cannot match is not a conflict.
    fine = compose(two, resolve=allowlist({
        "demo.a": lambda m: Contribution(
            routes=(Route("GET", "/files/{name}/meta", ok()),)),
        "demo.b": lambda m: Contribution(assets=(asset,))}))
    fine.startup()
    assert fine.dispatch("GET", "/files/a.txt").body == b"asset-bytes"
    fine.shutdown()


@check
def an_allowed_factory_that_fails_is_not_a_refused_capability():
    def factory(member):
        raise KeyError("settings['missing']")

    exc = expect(CapabilityFactoryFailed,
                 lambda: compose(parse(base()),
                                 resolve=allowlist({"demo.one": factory})))
    assert "missing" in str(exc) and "does not allow" not in str(exc)
    assert isinstance(exc.cause, KeyError) and exc.member == "only"
    assert not isinstance(exc, CapabilityNotAllowed)
    # A resolver the caller wrote by hand keeps the documented compatibility:
    # its own KeyError still reads as a refusal.
    def by_hand(capability, member):
        raise KeyError(capability)
    expect(CapabilityNotAllowed,
           lambda: compose(parse(base()), resolve=by_hand))


# ----------------------------------------------------------------------
# ASGI: driven at the message layer, because that is the contract.
# ----------------------------------------------------------------------


def drive_http(app, method, path, *, chunks=None, body=b"", headers=()):
    """One http request through the adapter. Returns (status, headers, body)."""
    incoming = list(chunks if chunks is not None else
                    [{"type": "http.request", "body": body, "more_body": False}])
    sent: list[dict] = []

    async def receive():
        return incoming.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "http", "method": method, "path": path,
                     "headers": list(headers)}, receive, send))
    if not sent:
        return 0, {}, None
    start = sent[0]
    return (start["status"],
            {k.decode("latin-1"): v.decode("latin-1") for k, v in start["headers"]},
            sent[1]["body"] if len(sent) > 1 else None)


def drive_lifespan(app, messages):
    """Feed lifespan messages, collect replies, and let the coroutine end."""
    replies: list[dict] = []

    async def run():
        inbox = asyncio.Queue()
        for message in messages:
            inbox.put_nowait(message)

        async def receive():
            return await inbox.get()

        async def send(message):
            replies.append(message)

        await asyncio.wait_for(app({"type": "lifespan"}, receive, send), 5)

    asyncio.run(run())
    return replies


def _asgi_fixture(handler=None, **kwargs):
    def build(m):
        def echo(request: Request) -> Response:
            return Response(body=b"len:" + str(len(request.body)).encode())
        return Contribution(
            routes=(Route("GET", "/x", handler or (lambda r: Response(body=b"body"))),
                    Route("POST", "/echo", echo)),
            assets=(Asset("/assets/a.css", b"css\n", "text/css"),))

    composition = compose(parse(base()), resolve=allowlist({"demo.one": build}))
    return composition, asgi_app(composition, **kwargs)


@check
def asgi_http_carries_status_headers_and_body():
    composition, app = _asgi_fixture()
    composition.startup()
    status, headers, body = drive_http(app, "GET", "/x")
    assert status == 200 and body == b"body"
    assert headers["content-length"] == "4" and "content-type" in headers
    assert all(name == name.lower() for name in headers), headers

    status, headers, body = drive_http(app, "HEAD", "/x")
    assert status == 200 and body == b"", (status, body)
    assert headers["content-length"] == "4", headers   # what GET would send

    status, _, body = drive_http(app, "HEAD", "/assets/a.css")
    assert status == 200 and body == b""

    status, headers, body = drive_http(app, "HEAD", "/nope")
    assert status == 404 and body == b"" and int(headers["content-length"]) > 0

    status, headers, _ = drive_http(app, "PUT", "/x")
    assert status == 405 and headers["allow"] == "GET, HEAD"

    status, _, body = drive_http(app, "POST", "/echo", chunks=[
        {"type": "http.request", "body": b"ab", "more_body": True},
        {"type": "http.request", "body": b"cd", "more_body": False}])
    assert status == 200 and body == b"len:4", body
    composition.shutdown()


@check
def asgi_bounds_the_request_body_before_dispatch():
    seen: list[int] = []

    def counting(request: Request) -> Response:
        seen.append(len(request.body))
        return Response(body=b"ok")

    composition, app = _asgi_fixture(handler=counting, max_request_bytes=1024)
    composition.startup()

    over = [{"type": "http.request", "body": b"x" * 256, "more_body": True}
            for _ in range(8)]
    over.append({"type": "http.request", "body": b"", "more_body": False})
    status, _, body = drive_http(app, "POST", "/echo", chunks=over)
    assert status == 413 and b"exceeds 1024" in body
    assert seen == [], "the handler saw a body that was over the limit"

    # Declared oversize is refused without reading the body at all.
    status, _, _ = drive_http(app, "POST", "/echo", chunks=[],
                              headers=[(b"content-length", b"99999")])
    assert status == 413

    # HEAD is held to the same limit.
    status, _, body = drive_http(app, "HEAD", "/x", chunks=[
        {"type": "http.request", "body": b"y" * 2048, "more_body": False}])
    assert status == 413 and body == b""

    # Exactly at the limit is allowed.
    status, _, _ = drive_http(app, "POST", "/echo", body=b"z" * 1024)
    assert status == 200
    composition.shutdown()

    for bad in (0, -1, None, 1.5, True, "1024"):
        expect(ValueError, lambda b=bad: asgi_app(composition, max_request_bytes=b))


@check
def asgi_handles_disconnect_and_malformed_messages():
    composition, app = _asgi_fixture()
    composition.startup()
    status, _, body = drive_http(app, "POST", "/echo", chunks=[
        {"type": "http.request", "body": b"half", "more_body": True},
        {"type": "http.disconnect"}])
    assert (status, body) == (0, None), "nothing may be sent after a disconnect"

    status, _, body = drive_http(app, "POST", "/echo", chunks=[
        {"type": "http.weird", "body": b""}])
    assert status == 400 and b"unexpected ASGI message" in body

    status, _, body = drive_http(app, "POST", "/echo", chunks=[
        {"type": "http.request", "body": "text not bytes", "more_body": False}])
    assert status == 400 and b"not bytes" in body
    composition.shutdown()


@check
def asgi_refuses_a_response_it_cannot_frame():
    def splitter(_: Request) -> Response:
        return Response(body=b"x", headers={"X-Note": "ok\r\nX-Injected: yes"})

    composition, app = _asgi_fixture(handler=splitter)
    composition.startup()
    exc = expect(ResponseInvalid, lambda: drive_http(app, "GET", "/x"))
    assert "U+000D" in str(exc)
    composition.shutdown()

    for headers, media_type, fragment in (
            ({"X Note": "ok"}, "text/plain", "header name"),
            ({"X-Note:": "ok"}, "text/plain", "header name"),
            ({"X-Note": "caf\u00e9\u2028"}, "text/plain", "U+2028"),
            ({"Content-Type": "text/html"}, "text/plain", "adapter"),
            ({"Content-Length": "nine"}, "text/plain", "not a number"),
            ({}, "text/plain\r\nX: y", "U+000D")):
        composition, app = _asgi_fixture(
            handler=lambda r, h=headers, m=media_type: Response(
                body=b"x", media_type=m, headers=h))
        composition.startup()
        exc = expect(ResponseInvalid, lambda a=app: drive_http(a, "GET", "/x"))
        assert fragment in str(exc), (headers, media_type, exc)
        composition.shutdown()

    # A handler-set content-length is checked against the bytes, not honoured.
    composition, app = _asgi_fixture(
        handler=lambda r: Response(body=b"abc", headers={"Content-Length": "3"}))
    composition.startup()
    status, headers, _ = drive_http(app, "GET", "/x")
    assert status == 200 and headers["content-length"] == "3"
    composition.shutdown()


@check
def asgi_frames_a_response_from_its_bytes_and_never_from_a_handler_header():
    # The defect this check exists for: a handler claiming Content-Length: 1
    # beside a three-byte body used to be believed, and the client either
    # truncates the body or waits for bytes nobody will send.
    composition, app = _asgi_fixture(
        handler=lambda r: Response(body=b"abc", headers={"Content-Length": "1"}))
    composition.startup()
    exc = expect(ResponseInvalid, lambda: drive_http(app, "GET", "/x"))
    assert "says 1 and the body is 3 bytes" in str(exc), exc
    composition.shutdown()

    # HEAD still states what GET would have sent, measured before the strip.
    composition, app = _asgi_fixture(
        handler=lambda r: Response(body=b"0123456789"))
    composition.startup()
    status, headers, body = drive_http(app, "HEAD", "/x")
    assert (status, body) == (200, b"") and headers["content-length"] == "10"
    # …and a HEAD whose handler lies about the length is refused too, rather
    # than slipping through because the body was empty by the time it was seen.
    composition.shutdown()

    composition, app = _asgi_fixture(
        handler=lambda r: Response(body=b"0123456789",
                                   headers={"Content-Length": "2"}))
    composition.startup()
    expect(ResponseInvalid, lambda: drive_http(app, "HEAD", "/x"))
    composition.shutdown()

    # Exactly one content-length reaches the wire, in every case.
    for handler in (lambda r: Response(body=b"abcd"),
                    lambda r: Response(body=b"abcd",
                                       headers={"Content-Length": "4"})):
        composition, app = _asgi_fixture(handler=handler)
        composition.startup()
        _, headers, _ = drive_http(app, "GET", "/x")
        assert headers["content-length"] == "4"
        composition.shutdown()


@check
def asgi_refuses_hop_by_hop_headers_and_a_second_framing_statement():
    for name in ("Transfer-Encoding", "Connection", "Keep-Alive", "TE",
                 "Trailer", "Upgrade", "Proxy-Authenticate",
                 "Proxy-Authorization"):
        composition, app = _asgi_fixture(
            handler=lambda r, n=name: Response(body=b"abc", headers={n: "chunked"}))
        composition.startup()
        exc = expect(ResponseInvalid, lambda a=app: drive_http(a, "GET", "/x"))
        assert "connection-scoped" in str(exc), (name, exc)
        composition.shutdown()


@check
def asgi_holds_bodyless_statuses_to_their_framing_rules():
    for status in (100, 101, 199, 204, 304):
        composition, app = _asgi_fixture(
            handler=lambda r, s=status: Response(status=s))
        composition.startup()
        code, headers, body = drive_http(app, "GET", "/x")
        assert code == status and body == b""
        assert "content-length" not in headers, (status, headers)
        composition.shutdown()

        # A body on one of them is a desynchronised connection, not a warning.
        composition, app = _asgi_fixture(
            handler=lambda r, s=status: Response(status=s, body=b"bytes"))
        composition.startup()
        exc = expect(ResponseInvalid, lambda a=app: drive_http(a, "GET", "/x"))
        assert "carries no body" in str(exc), (status, exc)
        composition.shutdown()

        # Nor may a handler state a length the framing has already denied.
        composition, app = _asgi_fixture(
            handler=lambda r, s=status: Response(
                status=s, headers={"Content-Length": "0"}))
        composition.startup()
        exc = expect(ResponseInvalid, lambda a=app: drive_http(a, "GET", "/x"))
        assert "no content-length" in str(exc), (status, exc)
        composition.shutdown()

    # 200 with an empty body still carries an explicit zero.
    composition, app = _asgi_fixture(handler=lambda r: Response(body=b""))
    composition.startup()
    _, headers, _ = drive_http(app, "GET", "/x")
    assert headers["content-length"] == "0"
    composition.shutdown()


@check
def asgi_refuses_a_response_whose_shape_cannot_become_a_message():
    for response, field, fragment in (
            (Response(status=True), "status", "not an int"),
            (Response(status="200"), "status", "not an int"),
            (Response(status=99), "status", "outside 100-599"),
            (Response(status=600), "status", "outside 100-599"),
            (Response(body="text"), "body", "not bytes"),
            (Response(body=bytearray(b"ab")), "body", "not bytes"),
            (Response(headers={"X-Count": 7}), "headers['X-Count']", "not a str"),
            (Response(media_type=None), "media_type", "not a str")):
        composition, app = _asgi_fixture(handler=lambda r, v=response: v)
        composition.startup()
        exc = expect(ResponseInvalid, lambda a=app: drive_http(a, "GET", "/x"),
                     field=field)
        assert fragment in str(exc), (field, exc)
        composition.shutdown()


@check
def asgi_lifespan_reports_startup_shutdown_and_refuses_a_second_startup():
    composition, app = _asgi_fixture()
    replies = drive_lifespan(app, [{"type": "lifespan.startup"},
                                   {"type": "lifespan.shutdown"}])
    assert replies == [{"type": "lifespan.startup.complete"},
                       {"type": "lifespan.shutdown.complete"}], replies
    assert composition.readiness() == (False, "not started")

    # After shutdown the app answers 503 rather than routing at closed members.
    status, _, _ = drive_http(app, "GET", "/x")
    assert status == 503

    # A second lifespan.startup is a server bug. It is reported through the
    # protocol and terminal, exactly as a genuine startup failure is.
    second, app_two = _asgi_fixture()
    replies = drive_lifespan(app_two, [{"type": "lifespan.startup"},
                                       {"type": "lifespan.startup"}])
    assert len(replies) == 2, replies
    assert replies[1]["type"] == "lifespan.startup.failed"
    assert "not re-entrant" in replies[1]["message"], replies[1]
    second.shutdown()

    def boom():
        raise RuntimeError("upstream is unreachable")

    broken = compose(parse(base()), resolve=allowlist({
        "demo.one": lambda m: Contribution(startup=boom)}))
    replies = drive_lifespan(asgi_app(broken), [{"type": "lifespan.startup"}])
    assert replies == [{"type": "lifespan.startup.failed",
                        "message": replies[0]["message"]}]
    assert "upstream is unreachable" in replies[0]["message"]


@check
def asgi_refuses_protocols_it_does_not_serve():
    _, app = _asgi_fixture()

    async def run():
        await app({"type": "websocket", "path": "/x"}, None, None)

    expect(NotImplementedError, lambda: asyncio.run(run()))


# ----------------------------------------------------------------------
# Packaging: the installed thing and the imported thing are one thing.
# ----------------------------------------------------------------------


@check
def the_packaging_metadata_agrees_with_the_code_it_ships():
    import tomllib

    box = Path(__file__).resolve().parent.parent
    meta = tomllib.loads((box / "pyproject.toml").read_text(encoding="utf-8"))
    project = meta["project"]

    # A version in two files is a version that drifts, and the drift only shows
    # up in a consumer's dependency resolution, months later.
    assert project["version"] == appcompose.__version__, (
        project["version"], appcompose.__version__)

    # …and neither of them is the document schema version, which moves for
    # entirely different reasons.
    assert project["version"] != str(SCHEMA_VERSION)
    assert SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS

    # requirements.txt and the install metadata state one dependency surface.
    stated = [line.strip() for line in
              (box / "requirements.txt").read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")]
    assert stated == project["dependencies"], (stated, project["dependencies"])

    # Only the importable packages are installed. Shipping tests/ or examples/
    # into a consumer's site-packages is how `import tests` starts resolving to
    # somebody else's box.
    packages = meta["tool"]["setuptools"]["packages"]
    assert packages == ["appcompose", "appcompose.demo"], packages
    for excluded in ("tests", "examples", "scripts"):
        assert not any(p.split(".")[0] == excluded for p in packages), excluded


def main() -> int:
    failures = 0
    for fn in CHECKS:
        name = fn.__name__.replace("_", " ")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report every check, not the first
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {name}")
    print(f"{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
