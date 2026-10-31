# portable-app-composition

Canonical library owner for the `appcompose` public API. Python 3.11+.
Enrolled in the [shared workspace](../../../libraries/README.md#installation). For this library alone,
run from the repository root and install into your chosen environment:

```bash
python -m pip install ./.github/skills/portable-app-composition
```

Minimal executable example:

```python
from appcompose import Contribution, Response, Route, allowlist, compose, parse

document = parse({
  "schemaVersion": 1, "kind": "portable.app-composition", "name": "Example",
  "members": [{"id": "health", "capability": "health.read"}],
})
application = compose(document, resolve=allowlist({
  "health.read": lambda member: Contribution(routes=(
    Route("GET", "/health", lambda request: Response(body=b"ok")),
  )),
}))
application.startup()
try:
  assert application.dispatch("GET", "/health").body == b"ok"
finally:
  application.shutdown()
assert application.dispatch("GET", "/health").status == 503
```

The host authorizes requests before dispatch. No network or persistent state is
created by this example. [Guide](GUIDE.md), [contract](CONTRACT.md),
[failure knowledge](GOTCHAS.md), [source migration manifest](MIGRATION.json).

A person writes one file. An application comes out of it — routes, static
assets, startup and shutdown ordering — assembled from capabilities the *host*
allowed, never from code the file named.

```yaml
schemaVersion: 1
kind: portable.app-composition
name: Field notes
members:
  - id: digest
    capability: notes.digest
    requires: [store]
  - id: store
    capability: notes.store
    settings:
      seed: [first note, second note]
ownership:
  /assets/shared.css: store
```

```python
from appcompose import allowlist, compose, from_yaml

document = from_yaml(Path("app.yaml").read_text())
app = compose(document, resolve=allowlist({
    "notes.store": build_note_store,     # your code, in your allowlist
    "notes.digest": build_digest,
}))
app.startup()                            # store first: the document says so
app.dispatch("GET", "/api/digest")
```

## Why this exists

Configurable applications drift into one of two failure modes.

The first is a plugin loader: the document grows an `entrypoint: "pkg.mod:app"`
field, and now anyone who can edit a config file can execute code. Every
mitigation after that point is a patch on a design decision.

The second is a second source of truth: the document describes the app, and a
separate manifest describes how it is assembled. They are edited by different
people at different times, and one day the manifest lists a member the document
removed.

This skill takes the other route on both. A document names **capabilities**,
which are opaque identifiers; the mapping from identifier to implementation is a
resolver the caller passes in, and that resolver is the allowlist. Nothing here
imports anything. And the composition is a **projection** of the document — it
holds the document it was built from and derives everything from it, so there is
no second file to drift.

## Adoption boundary

One import, one call:

```python
from appcompose import allowlist, compose, from_yaml   # or from_json, parse
composition = compose(document, resolve=resolver)
```

`compose(document, *, resolve)` is the single public entry point. `resolve` is
`(capability: str, member: Member) -> Contribution | None` — yours, and the only
place a capability identifier becomes code. Returning `None` refuses a
capability; `allowlist({...})` is the convenience form over a literal mapping.

Everything else in the namespace is vocabulary those two lines use: `Document`,
`Member` and `Placement` on the way in; `Contribution`, `Route`, `Asset`,
`Request` and `Response` on the way back; `Composition`, `ComposedMember` and
the errors on the way out. `asgi_app(composition)` is an optional adapter, not a
second boundary — delete it and the skill still composes.

Adopting this skill does not require a member to be modified. A capability
returns a `Contribution` and never learns it was composed, what else was
composed, or where a shell placed it.

## Failure model

Everything refuses by name, and nothing guesses.

- **Parse time** — `DocumentInvalid` with `.field`: `members[1].requires[0]`,
  not "invalid configuration". `UnsupportedVersion` for a schema this build has
  no migration for; `CredentialShaped` for a secret pasted into a document.
  Depth and cycles are bounded and named too, so a caller that catches
  `DocumentInvalid` catches every parse failure.
- **Compose time** — `CapabilityNotAllowed` when the resolver does not allow a
  capability, and `CapabilityFactoryFailed` when an *allowed* factory raised a
  lookup error, because those have opposite remedies; `RouteConflict` and
  `AssetConflict` when two members claim one path and the document names no
  owner, including two templates that overlap with neither more specific;
  `UnknownMetadata` for a key that would otherwise be silently ignored.
- **Startup** — a member that raises rolls back everything already started, in
  reverse order, and reports what was rolled back and what failed to roll back.
  A clean rollback, after a hook that cleaned up after itself, leaves the
  composition startable again.
- **Anything this composition could not stop latches it** — a rollback that
  failed, a `shutdown()` that failed, or a startup hook that raised
  `PartialStartup` to say it kept resources. `availability()` goes `False` and
  `startup()` refuses until an operator calls
  `clear_unsafe_state(resolved=[...])`, because nothing here can know whether a
  port was released. A member that could not be stopped and is then started
  again is running twice, which is the failure worth being loud about.
- **Shutdown** — reverse order, exactly once, and every hook runs even if an
  earlier one raised; the collected failures are raised afterwards.
- **Interrupts** — `KeyboardInterrupt` and `SystemExit` in a hook are never
  wrapped into `StartupFailed` or `ShutdownFailed`. The remaining cleanup runs,
  the state is latched, and the original exception is re-raised, so Ctrl-C still
  means Ctrl-C.
- **Dispatch** — `503` outside the running window, `404`, `405` with `Allow`,
  and `ResponseInvalid` from the adapter for a response that cannot be framed:
  a bad status or body type, a hop-by-hop header, a body on a `204`, or a
  `Content-Length` disagreeing with the bytes.

`CONTRACT.md` is the full specification. `GOTCHAS.md` is what actually bites.

## Limits — what this does not do

- **It does not authorise anything.** `dispatch` is a router. A trust boundary
  is the caller's, checked before dispatch — and assets are served before any
  route is matched, so the guard wraps the whole call. Layout slots are metadata
  for a shell; they are not isolation, and this skill never claims same-origin
  separation of any kind.
- **It ships no UI.** `layout` carries `slot`, `order` and `lazy` for whatever
  shell reads them. Nothing here renders, and nothing here acts on `lazy`.
- **It is not a plugin loader.** There is no import-by-string, by design. A
  capability the caller did not allow cannot be composed.
- **The credential scan is a backstop, not a proof.** It recognises common key
  shapes and constrains what may sit under them. Do not treat a passing document
  as evidence that no secret is in it.
- **No process supervision.** Startup and shutdown call your hooks in order;
  they do not restart, retry, or health-check a member for you. After a member
  could not be stopped, recovery is an operator's explicit call, not an
  automatic one — and a startup hook is expected to be a transaction, because
  nothing here can reach inside a half-finished one.
- **It is synchronous, and not thread-safe.** Hooks and handlers are called
  directly; one that returns an awaitable is refused rather than dropped. The
  caller serialises lifecycle calls — nothing here takes a lock.
- **HTTP coverage is deliberately small**: routing, static assets, and the ASGI
  `lifespan` and `http` protocols. No websockets, no streaming bodies. The host
  still owns TLS, authentication, path normalisation, caching policy,
  concurrency and logging — `CONTRACT.md` §5.1 lists them.

## MCP Adapter

The installed `appcompose.mcp` adapter validates documents and runs a fixed synthetic demo.
It exposes no external resolver, credentials or network target. Install this
library's `mcp` extra, then run `appcompose-mcp --config <settings.json>`
from any directory. The sole setting is `max_document_bytes` (default 131072,
range 1-1048576). `python tests/mcp_smoke.py` checks the real stdio SDK exchange.

The optional [unified MCP host](../../../libraries/README.md#discovery-and-mcp) also exposes
`composition_status`, `composition_validate`, and `composition_demo`; registration
and grants remain explicit. No launcher installs dependencies. Canonical output can
contain document data; validation is not authorization or proof of no secrets.

## Standalone Python Install

Install reviewed source or package artifacts into the caller's environment; do not
copy a skill runtime or patch `sys.path`. For a source install, run from the repository
root with `PYTHONPATH` clear:

```bash
python3 -m pip install ./.github/skills/portable-app-composition
```

That installs `appcompose` and `appcompose.demo` into site-packages and brings
PyYAML (needed only for the YAML form; the JSON path is stdlib). CLI implementations
and fixed demo data are installed; tests and standalone examples stay in the source
checkout. Run the following from this library directory after installation:

```bash
python3 tests/selftest.py
python3 examples/compose_two_capabilities.py
python3 examples/asgi_headless_app.py
python3 examples/refusals.py
appcompose-inspect appcompose/demo/field-notes.yaml
python3 tests/loopback_check.py        # optional; needs pip install '.[dev]'
```

The version in `pyproject.toml` and `appcompose.__version__` are one string, and
`selftest.py` fails if they drift. Neither is `SCHEMA_VERSION`, which versions
the document format and moves for different reasons.

## Removal

```bash
python3 -m pip uninstall portable-app-composition
```

Nothing is registered globally and nothing is written to disk, so the rest of
removal is deletion. Delete the folder and replace the one `compose(...)` call
site with whatever wiring you had before. Your capabilities are unaffected: they
were never modified to be composed, so they keep working with any other
assembly. Documents already written stay readable — they are plain JSON or YAML
— and `CONTRACT.md` is the spec for reading them without this code.
