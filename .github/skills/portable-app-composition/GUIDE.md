---
name: portable-app-composition
description: >
  Use when a human-authored configuration document must become a running
  application — members, routes, static assets, startup and shutdown order —
  without the document being allowed to name code. Use for versioned canonical
  JSON with a safe YAML form, byte-identical round trips, field-addressed
  validation, unique ids, dependency DAGs and credential refusal; and for
  assembling capabilities through a caller-owned allowlist resolver with
  explicit route and asset ownership, dependency-ordered startup with rollback,
  reverse-order exactly-once shutdown, and availability separated from
  readiness. Trigger phrases: config-driven app, manifest composition, plugin
  entrypoint is unsafe, two members claim the same route, asset collision,
  startup ordering, remove a member and recompose, YAML duplicate key or alias.
---

# portable-app-composition

One document in, one composed application out. The document names capabilities;
the caller's resolver — not the document — decides what those capabilities are.

## Decide

Use it when **all** of these hold:

- a person or a program authors a file that describes which parts an application
  is made of;
- those parts contribute HTTP routes, static assets, or a start/stop lifecycle;
- the file must never be able to name code to import.

Do not use it when the application has one fixed set of parts (wire them
directly), when you need a process supervisor or a scheduler, or when you were
looking for an authorisation layer — this skill deliberately has none.

## MCP Integration

The optional installed adapter and its SDK test live with this library; see
[README.md](README.md#mcp-adapter). It validates without resolving code and
runs only a fixed in-memory allowlist. The
[framework client example](../harness-guide/framework/README.md#offline-mcp-client) exercises the
implemented opt-in host. Installation and generated discovery activate no server or grant.

## Standalone Python Install

```bash
python3 -m pip install ./.github/skills/portable-app-composition    # from the repository root
```

Install it, do not just copy it. From your own repository root with `PYTHONPATH`
clear, `from appcompose import compose` on a bare copy is a `ModuleNotFoundError`
— and the usual fix, a `sys.path.insert` in your entry point, is the same kind of
fragility this skill exists to remove. A plain, **non-editable** install puts
`appcompose` in site-packages, where nothing about your working directory can
reach it. `appcompose` and `appcompose.demo` include CLI modules and demo data;
`tests/` and standalone `examples/` stay in the library source.

PyYAML is needed only for `to_yaml` / `from_yaml`. The JSON path — `parse`,
`from_json`, `canonical_json` — is stdlib. `pip install '.[dev]'` adds uvicorn,
needed by one optional check and by nothing else.

## Use

Write the document:

```yaml
schemaVersion: 1
kind: portable.app-composition
name: Field notes
members:
  - id: store
    capability: notes.store
    settings: {seed: [first note]}
  - id: digest
    capability: notes.digest
    requires: [store]          # starts after store, stops before it
ownership:
  /assets/shared.css: store    # two members ship it; this one owns it
```

Write a capability. It returns a neutral `Contribution` and never learns it was
composed:

```python
from appcompose import Asset, Contribution, Response, Route

def build_store(member):
    store = Store(seed=member.settings.get("seed", ()))
    return Contribution(
        routes=(Route("GET", "/api/notes", lambda req: Response(body=store.json())),),
        assets=(Asset("/assets/shared.css", CSS, "text/css"),),
        startup=store.open,
        shutdown=store.close,
        metadata={"title": "Notes"},
    )
```

Compose it, through your own allowlist:

```python
from appcompose import allowlist, compose, from_yaml

document = from_yaml(text)
app = compose(document, resolve=allowlist({
    "notes.store": build_store,
    "notes.digest": build_digest,
}))

app.startup()                                  # dependency order
app.dispatch("GET", "/api/notes")              # authorise BEFORE this call
app.shutdown()                                 # reverse order, exactly once
```

Serve it over HTTP, if you want to:

```python
from appcompose import asgi_app
application = asgi_app(app, max_request_bytes=1_048_576)   # uvicorn application:application
```

Edit and recompose:

```python
smaller = document.without("digest")           # consumer gone, app still runs
document.without("store")                      # DocumentInvalid: members[…].requires[0]
```

Five rules worth internalising:

1. **The resolver is the allowlist.** A capability outside it raises
   `CapabilityNotAllowed`. Nothing is imported by name, ever.
2. **Contested paths need an owner.** Two members shipping one asset refuse
   until `ownership` names one — identical bytes included. Two route templates
   that overlap with neither more specific refuse outright.
3. **Authorisation is yours.** `dispatch` routes; it does not authenticate, and
   it serves only between `startup()` and `shutdown()` — `503` outside that.
4. **A member this composition could not stop latches it.** A failed rollback, a
   failed `shutdown()`, or a startup hook that raised `PartialStartup` all
   refuse the next `startup()` until `clear_unsafe_state(resolved=[...])`;
   nothing here can know a port was freed. `KeyboardInterrupt` and `SystemExit`
   are re-raised unchanged after cleanup, never wrapped.
5. **The adapter owns the wire, and measures it.** `Content-Length` is computed
   from the body's bytes; a handler value that disagrees is refused, not
   believed. Hop-by-hop headers are refused, bodyless statuses carry no length,
   and `HEAD` is measured before the body is dropped. TLS, auth, path
   normalisation, caching and concurrency stay the host's — `CONTRACT.md` §5.1.

## Verify

```bash
python3 tests/selftest.py                        # every rule, no test framework
python3 examples/compose_two_capabilities.py     # document -> serve -> recompose
python3 examples/asgi_headless_app.py            # real ASGI lifespan, http, HEAD, 413
python3 examples/refusals.py                     # every refusal, by field name
python3 tests/loopback_check.py                  # optional: real uvicorn/h11 framing
```

Each exits non-zero on failure. The examples assert their own output rather than
printing it, so a silent regression is not possible. `loopback_check.py` needs
the `dev` extra and exits `2`, saying so, when uvicorn is absent — it is the only
place framing claims are read off a socket rather than off an ASGI message.

Verify it in *your* repository the same way: copy the folder somewhere with no
relation to where it came from, install it into a fresh virtual environment,
clear `PYTHONPATH`, and run the commands from the copy.

## Remove

```bash
python3 -m pip uninstall portable-app-composition
```

Then delete the folder, and drop PyYAML if nothing else needs it. Nothing is
registered globally, no file is written, no state persists. Your capabilities
are untouched — they were never modified to be composed — and existing documents
stay readable, because they are plain JSON or YAML described by `CONTRACT.md`.

## Files

- `README.md` — why it exists, the adoption boundary, the failure model, limits.
- `CONTRACT.md` — the specification, sufficient to reimplement from.
- `GOTCHAS.md` — numbered, symptom-first, cited from the code.
- `appcompose/` — the mechanism. `appcompose/demo/` is illustration only.
- `pyproject.toml` — what gets installed, and the version that must match
  `appcompose.__version__`.
- `examples/`, `tests/`; installed `appcompose.cli` and optional `appcompose.mcp`.
