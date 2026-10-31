#!/usr/bin/env python3
"""Worked example: what this skill refuses, and the message you get back.

Run it:

    python3 examples/refusals.py

Every refusal below is asserted on its ``field`` or its type, not on prose, so
this file is also the compatibility test for those messages. If you are here
because something was rejected, find the shape that matches yours and read the
comment above it.

The last two sections are the ones people are surprised by: an asset shipped by
two members is refused until the document names an owner, and authorisation is
never the composition's job.
"""

from __future__ import annotations

import json

from appcompose import (  # noqa: E402
    Asset,
    AssetConflict,
    CapabilityFactoryFailed,
    CapabilityNotAllowed,
    CompositionError,
    Contribution,
    CredentialShaped,
    DocumentInvalid,
    Request,
    Response,
    Route,
    RouteConflict,
    StartupFailed,
    UnknownMetadata,
    UnsupportedVersion,
    allowlist,
    compose,
    from_json,
    from_yaml,
    parse,
)

BASE = {
    "schemaVersion": 1,
    "kind": "portable.app-composition",
    "name": "Refusals",
    "members": [{"id": "one", "capability": "demo.one"}],
}


def document(**changes):
    payload = json.loads(json.dumps(BASE))
    payload.update(changes)
    return payload


def refused(callable_, *, field=None, kind=DocumentInvalid):
    """Run something that must fail, and hand back the exception it raised."""
    try:
        callable_()
    except kind as exc:
        if field is not None:
            assert getattr(exc, "field", None) == field, (field, exc)
        return exc
    raise AssertionError(f"expected {kind.__name__}, nothing was raised")


def main() -> int:
    # --- the document -------------------------------------------------
    # A version this build has no migration for. Not "invalid": unsupported.
    exc = refused(lambda: parse(document(schemaVersion=99)),
                  field="schemaVersion", kind=UnsupportedVersion)
    assert exc.supported == (1,) and exc.found == 99

    # A key nobody defined. Silently ignoring it is how a typo becomes a
    # setting that never took effect.
    refused(lambda: parse(document(members=[{"id": "one",
                                             "capability": "demo.one",
                                             "retries": 3}])),
            field="members[0].retries")

    # A key that would turn data into an execution instruction. Refused by
    # name, with the reason, because "unknown key" does not teach the lesson.
    exc = refused(lambda: parse(document(members=[{
        "id": "one", "capability": "demo.one",
        "entrypoint": "os.system"}])), field="members[0].entrypoint")
    assert "names capabilities, never code" in exc.detail

    # Two members with one id. Ids are one namespace, shared with layout.
    refused(lambda: parse(document(members=[
        {"id": "one", "capability": "demo.one"},
        {"id": "one", "capability": "demo.two"}])), field="members[1].id")

    # A requirement nobody satisfies, and a cycle nobody can start.
    refused(lambda: parse(document(members=[
        {"id": "one", "capability": "demo.one", "requires": ["ghost"]}])),
        field="members[0].requires[0]")
    exc = refused(lambda: parse(document(members=[
        {"id": "alpha", "capability": "demo.one", "requires": ["beta"]},
        {"id": "beta", "capability": "demo.two", "requires": ["alpha"]}])),
        field="members")
    assert "alpha -> beta -> alpha" in exc.detail, exc.detail

    # A credential-shaped key with a literal value. A backstop, not a proof.
    refused(lambda: parse(document(members=[{
        "id": "one", "capability": "demo.one",
        "settings": {"api_key": "9f2c1d5b7a3e"}}])),
        field="members[0].settings.api_key", kind=CredentialShaped)

    # Wrapping the same value in a list is not an exemption. Only a reference
    # string, a blank string or null may sit under a credential-shaped key.
    exc = refused(lambda: parse(document(members=[{
        "id": "one", "capability": "demo.one",
        "settings": {"api_key": ["9f2c1d5b7a3e"]}}])),
        field="members[0].settings.api_key", kind=CredentialShaped)
    assert "not an exemption" in exc.detail

    # Depth is bounded before a recursive parser reports it as a RecursionError
    # with no field in it.
    refused(lambda: from_json('{"a":' * 500 + "1" + "}" * 500), field="<json>")

    # An ownership path that could escape the asset namespace.
    refused(lambda: parse(document(ownership={"/assets/../etc/passwd": "one"})),
            field="ownership['/assets/../etc/passwd']")

    # --- serialisation ------------------------------------------------
    # YAML keeps the last duplicate key silently. Here it is a refusal.
    exc = refused(lambda: from_yaml(
        "schemaVersion: 1\nkind: portable.app-composition\nname: A\nname: B\n"
        "members: []\n"), field="<yaml>")
    assert "twice" in exc.detail

    # An alias is how a kilobyte of YAML becomes gigabytes of memory.
    refused(lambda: from_yaml(
        "schemaVersion: 1\nkind: portable.app-composition\nname: &n A\n"
        "description: *n\nmembers: []\n"), field="<yaml>")

    # A tag asking the loader to build a Python object.
    refused(lambda: from_yaml(
        "schemaVersion: 1\nkind: portable.app-composition\n"
        "name: !!python/object/apply:os.system ['echo hi']\nmembers: []\n"),
        field="<yaml>")

    # JSON has no NaN, whatever a producer wrote.
    refused(lambda: from_json(
        '{"schemaVersion":1,"kind":"portable.app-composition","name":"A",'
        '"members":[{"id":"one","capability":"demo.one",'
        '"settings":{"ratio":NaN}}]}'), field="<json>")

    # --- composition --------------------------------------------------
    def handler(_: Request) -> Response:
        return Response(body=b"ok")

    # The resolver is the allowlist. A capability outside it is a named refusal.
    exc = refused(lambda: compose(parse(document()), resolve=allowlist({})),
                  kind=CapabilityNotAllowed)
    assert exc.member == "one" and exc.capability == "demo.one"

    # Two members, one route shape. Parameter *names* do not make it different.
    two = parse(document(members=[{"id": "alpha", "capability": "demo.a"},
                                  {"id": "beta", "capability": "demo.b"}]))
    exc = refused(lambda: compose(two, resolve=allowlist({
        "demo.a": lambda m: Contribution(
            routes=(Route("GET", "/items/{id}", handler),)),
        "demo.b": lambda m: Contribution(
            routes=(Route("GET", "/items/{key}", handler),)),
    })), kind=RouteConflict)
    assert exc.members == ("alpha", "beta") and exc.path == "/items/{}"

    # Metadata the composition does not define is refused, not ignored.
    refused(lambda: compose(parse(document()), resolve=allowlist({
        "demo.one": lambda m: Contribution(metadata={"slot": "main"})})),
        kind=UnknownMetadata)

    # Two templates that cross: /{a}/y and /x/{b} both match /x/y, and neither
    # is more specific, so only the declaration order would decide. Refused.
    exc = refused(lambda: compose(two, resolve=allowlist({
        "demo.a": lambda m: Contribution(
            routes=(Route("GET", "/{a}/y", handler),)),
        "demo.b": lambda m: Contribution(
            routes=(Route("GET", "/x/{b}", handler),)),
    })), kind=RouteConflict)
    assert "neither is more specific" in str(exc), exc

    # A segment is either a literal or exactly one {name}. /a/{p}c is neither,
    # and a matcher and a conflict check that disagree about it refuse two
    # genuinely different paths.
    exc = refused(lambda: compose(parse(document()), resolve=allowlist({
        "demo.one": lambda m: Contribution(
            routes=(Route("GET", "/a/{p}c", handler),))})),
        kind=CompositionError)
    assert "mixes literal text with a parameter" in str(exc), exc

    # An asset that would be matched by a route is a shadow, not a coexistence.
    exc = refused(lambda: compose(two, resolve=allowlist({
        "demo.a": lambda m: Contribution(
            routes=(Route("GET", "/files/{name}", handler),)),
        "demo.b": lambda m: Contribution(
            assets=(Asset("/files/a.txt", b"bytes"),))})),
        kind=CompositionError)
    assert "shadow" in str(exc), exc

    # An *allowed* capability whose factory raises a KeyError is the factory's
    # problem. Sending the reader to the allowlist would be a misdiagnosis.
    def missing_setting(member):
        raise KeyError("settings['endpoint']")

    exc = refused(lambda: compose(parse(document()),
                                  resolve=allowlist({"demo.one": missing_setting})),
                  kind=CapabilityFactoryFailed)
    assert "endpoint" in str(exc) and "does not allow" not in str(exc)

    # --- assets: identical bytes are not an excuse to guess ------------
    shared = Asset("/assets/app.css", b"body{margin:0}\n", "text/css")
    contributions = {
        "demo.a": lambda m: Contribution(assets=(shared,)),
        "demo.b": lambda m: Contribution(assets=(shared,)),
    }
    exc = refused(lambda: compose(two, resolve=allowlist(contributions)),
                  kind=AssetConflict)
    assert exc.members == ("alpha", "beta")

    # The document decides. There is no first-wins fallback to rely on.
    owned = parse(document(members=[{"id": "alpha", "capability": "demo.a"},
                                    {"id": "beta", "capability": "demo.b"}],
                           ownership={"/assets/app.css": "beta"}))
    resolved = compose(owned, resolve=allowlist(contributions))
    assert resolved.asset_table == (("/assets/app.css", "beta"),)

    # --- lifecycle -----------------------------------------------------
    stopped: list[str] = []

    def boom() -> None:
        raise RuntimeError("no disk")

    pair = parse(document(members=[
        {"id": "first", "capability": "demo.a"},
        {"id": "second", "capability": "demo.b", "requires": ["first"]}]))
    app = compose(pair, resolve=allowlist({
        "demo.a": lambda m: Contribution(shutdown=lambda: stopped.append("first")),
        "demo.b": lambda m: Contribution(startup=boom),
    }))
    exc = refused(app.startup, kind=StartupFailed)
    assert exc.member == "second" and exc.rolled_back == ("first",)
    assert stopped == ["first"], stopped          # rolled back, not left running
    assert app.readiness() == (False, "not started")

    # A rollback that *itself* fails leaves unknown external state, so a second
    # startup is refused until an operator says the member was released.
    def wont_stop() -> None:
        raise RuntimeError("port still bound")

    unsafe = compose(pair, resolve=allowlist({
        "demo.a": lambda m: Contribution(shutdown=wont_stop),
        "demo.b": lambda m: Contribution(startup=boom),
    }))
    refused(unsafe.startup, kind=StartupFailed)
    assert unsafe.availability() is False
    exc = refused(unsafe.startup, kind=CompositionError)
    assert "clear_unsafe_state" in str(exc), exc
    unsafe.clear_unsafe_state(resolved=["first"])
    assert unsafe.availability() is True

    # --- authorisation is the caller's, before dispatch ----------------
    guarded = compose(parse(document()), resolve=allowlist({
        "demo.one": lambda m: Contribution(
            routes=(Route("GET", "/api/secret", handler),))}))
    guarded.startup()

    def call(path: str, principal: str) -> int:
        if not principal:            # the caller's trust boundary, checked here
            return 401
        return guarded.dispatch("GET", path).status

    assert call("/api/secret", "") == 401
    assert call("/api/secret", "someone") == 200
    guarded.shutdown()

    # And once it is shut down it refuses to serve at all, rather than running
    # handlers against resources their own shutdown hook already released.
    assert guarded.dispatch("GET", "/api/secret").status == 503

    print("every refusal named its field or its member")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
