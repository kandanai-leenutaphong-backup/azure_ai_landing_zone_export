# CONTRACT — portable-app-composition

The specification. Everything here is enforced by `tests/selftest.py`; a
reimplementation that satisfies this file is a valid replacement for the code in
`appcompose/`.

Version `1.1.0`. Document schema version `SCHEMA_VERSION = 1`;
`SUPPORTED_SCHEMA_VERSIONS = (1,)`.

---

## MCP Adapter

The optional MCP server offers document validation and one fixed, in-memory demonstration.
It is not a host for caller-named capabilities or a remotely configurable application server.

| Tool | Inputs | Output |
| --- | --- | --- |
| `composition_status` | empty object | configuration path, document bound, `arbitrary_execution: false`, `network: false` |
| `composition_validate` | `document` string, optional `format` (`json` or `yaml`; JSON default) | canonical JSON, SHA-256 of canonical UTF-8 bytes, dependency order |
| `composition_demo` | empty object | marked fixture results, startup/shutdown order and idempotent second shutdown |

The only operator setting is `max_document_bytes`: default 131072, range 1-1048576. Document
input also has a one-million-character ceiling. Parsing retains all library validation, including
duplicate YAML key/alias, credential-shape, cycle, version and unknown-field refusals. Validation
never calls a resolver. Canonical output can contain submitted document values; do not submit secrets.

The demo reads the packaged [field-notes.yaml](appcompose/demo/field-notes.yaml), resolves
only `notes.store` and `notes.digest` through a literal allowlist, dispatches its fixed reads,
and shuts down in `finally`. No caller-provided document, route, body, import or command is accepted
by the demo tool. It leaves no application running and writes no file.

Errors set MCP `isError` and return the exception category/field, without reflecting the submitted
document. The official SDK handles protocol and argument validation. The
[MCP smoke check](tests/mcp_smoke.py) proves canonical round trips, lifecycle and refusals;
the original selftest remains the authority for the wider composition and HTTP contracts below.

Install the `mcp` extra and run `appcompose-mcp --config <settings.json>`, or import
`appcompose.mcp.Settings`, `validate`, `demo`, and `serve`. Nothing starts on import.
The old `appcompose_*` tool names and automatic environment bootstrap are retired;
the [framework host](../harness-guide/framework/README.md#offline-mcp-client) is implemented and opt-in.
Its tools add a fixed `binding` selector and exact host grants/context; those requirements
do not change this standalone adapter's native schemas or authorize arbitrary composition.

## 1. The document

One JSON object. `KIND` is the literal `"portable.app-composition"`, written in
the file so an object found with no context identifies itself.

```jsonc
{
  "schemaVersion": 1,                       // required, int, must be supported
  "kind": "portable.app-composition",       // required by value
  "id": "field-notes",                      // optional, id shape
  "name": "Field notes",                    // required, 1-120 chars, no controls
  "description": "…",                       // optional, ≤ 2000 chars
  "members": [                               // required, ≤ 64 entries
    {
      "id": "store",                        // required, unique across the document
      "capability": "notes.store",          // required, opaque identifier
      "label": "Note store",                // optional, ≤ 120 chars
      "settings": {"seed": ["a"]},          // optional, JSON data, ≤ 16384 bytes
      "requires": ["other-member-id"]       // optional, ids that must start first
    }
  ],
  "layout": {                                // optional, keyed by member id
    "store": {"slot": "main", "order": 1, "lazy": false}
  },
  "ownership": {                             // optional, asset path -> member id
    "/assets/shared.css": "store"
  }
}
```

### Shapes

| Field | Rule |
| --- | --- |
| member `id`, document `id` | `^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$` — 2 to 64 characters |
| `capability` | `^[a-z0-9][a-z0-9._-]{1,63}$` |
| `name` | 1-120 characters, no control characters |
| asset / route path | starts `/`, ≤ 256 chars, no `\`, no control character, no `..` or `.` segment, no empty segment |

### Bounds

`MAX_MEMBERS` 64 · settings ≤ 16 384 bytes serialised · settings nesting ≤ 8
levels · `MAX_DOCUMENT_DEPTH` 32, the depth of any part of a mapping handed
straight to `parse` · `MAX_NESTING_DEPTH` 32, measured on JSON or YAML **text**
before a recursive parser sees it · `MAX_DOCUMENT_BYTES` 256 000, measured on
the encoded input **before** parsing.

A mapping that contains itself is refused as `DocumentInvalid` naming the field:
no reader could have produced it, and a cycle has no canonical form.

### Rules a JSON schema cannot state

1. Ids are one namespace, shared with `layout` and `ownership`. A duplicate is
   refused at the second occurrence.
2. Every `requires` entry names a declared member. Self-reference and repeats
   are refused.
3. `requires` forms a DAG. A cycle is refused with the cycle written out
   (`aaa -> bbb -> ccc -> aaa`).
4. Every `layout` key and every `ownership` value names a declared member.
5. Unknown keys are refused, never ignored. A key that would name code —
   `entry`, `entrypoint`, `module`, `import`, `callable`, `factory`, `plugin`,
   `class`, `exec`, `eval`, `command`, `shell` — is refused with the reason:
   capabilities are resolved by the caller's allowlist, and nothing in this
   skill imports anything.
6. A credential-shaped key (`api_key`, `secret`, `password`, `client_secret`,
   `connection_string`, `sas_token`, `access_token`, `private_key`,
   `credential`) may hold **only** a value that names a location, a blank
   string, or `null`. A literal string of 8 or more characters is refused as
   `CredentialShaped`; values naming a location — `${…}`, `env:…`, `<…>`,
   `keyvault…`, `placeholder`, `example`, `unset`, `none`, `null` — pass. Any
   **non-string** value (list, object, number, boolean) is refused too, because
   wrapping a pasted secret in a list is otherwise a one-character bypass of the
   whole scan. This is a backstop for a mistake, **not** a proof of absence: a
   secret under a key the pattern does not match, or split across two fields,
   is not detectable here.
7. Numbers must be finite. `NaN` and `Infinity` are refused in both the parser
   and the JSON reader.

### Immutability

`parse` retains nothing it was given: settings are deep-copied and frozen
(`Mapping` becomes read-only, `list` becomes `tuple`), so mutating the input
mapping afterwards cannot change the document, and assigning through
`member.settings` raises `TypeError`. `member.settings_copy()` and `plain(value)`
return mutable deep copies the caller owns.

---

## 2. Encoding

| Function | Behaviour |
| --- | --- |
| `canonical_json(document) -> bytes` | UTF-8, `sort_keys=True`, separators `(",", ":")`, no ASCII escaping, one trailing newline |
| `from_json(data) -> Document` | size-checked, depth-checked on the text, `NaN`/`Infinity` refused, then `parse` |
| `to_yaml(document) -> str` | `yaml.safe_dump`, sorted keys, block style, **round trip verified before it returns** |
| `from_yaml(text) -> Document` | size-checked, depth-checked, then a strict loader, then `parse` |
| `to_mapping(document) -> dict` | plain JSON-ready mapping; empty optional blocks are omitted so a save is not a diff |

**Canonical identity.** For any document `d` — every document the validators in
§1 admit, not merely an ASCII one:

```
canonical_json(from_json(canonical_json(d))) == canonical_json(d)
canonical_json(from_yaml(to_yaml(d)))        == canonical_json(d)
```

Two documents that differ only in key order or in the absence of empty optional
blocks produce identical bytes.

The YAML half is **enforced by the writer**, not assumed. `to_yaml` emits the
readable form (`allow_unicode=True`), reads it back, and compares canonical
bytes; if the document contains a string that form loses — U+0085 is the one
that does, since `safe_dump` writes it raw and the loader folds it to a space —
it re-emits fully escaped and verifies again. A document that cannot be written
in a form that reads back identical raises `DocumentInvalid`, rather than being
written and silently corrupted. NEL, LS/PS, tab, CR, LF, NBSP and non-BMP
characters all round-trip, in `name`, `description` and nested `settings`.

**Depth.** JSON and YAML text nesting deeper than `MAX_NESTING_DEPTH` is refused
as `DocumentInvalid` before the parser recurses. `RecursionError` is never the
caller's error: every parse failure is a `DocumentInvalid` with a `.field`.

**The strict YAML loader** refuses, each as `DocumentInvalid("<yaml>", …)`:
duplicate keys in one mapping (`safe_load` keeps the last one silently), anchors
and aliases (an expansion vector, and a reader cannot see the value), unhashable
keys, any tag `SafeLoader` will not build, and an empty document.

**Version handling** is explicit. A missing, non-integer, or unsupported
`schemaVersion` raises `UnsupportedVersion`, carrying `found` and `supported`,
and saying whether the value predates this build or came from a newer release.
`bool` is not accepted as an integer.

---

## 3. Composition

```python
compose(document: Document, *, resolve: Callable[[str, Member], Contribution | None]) -> Composition
```

The single adoption boundary. `resolve` is the caller's allowlist: it returns a
`Contribution` for a capability it allows, `None` (or raises `KeyError` /
`LookupError`) for one it does not. Any other exception from the resolver is the
caller's and propagates unchanged. `allowlist({...})` builds the common form
from a literal `{capability: factory}` mapping.

**Lookup and construction are distinguished.** A `KeyError` or `LookupError`
raised *inside* a factory that `allowlist` did allow is re-raised as
`CapabilityFactoryFailed`, carrying `.cause`, `.member` and `.capability` — not
as `CapabilityNotAllowed`. The capability is allowed; the factory is what
failed, and pointing the reader at the allowlist would be a misdiagnosis. A
hand-written resolver that raises `KeyError` itself still means “not allowed”,
which is the documented compatibility for the resolver form the caller owns.

A composition is a **projection** of the document it was built from. It keeps
that document (`composition.document`), derives placement from its `layout`, and
provides no way to add or reorder members. There is no second file to edit.

### Neutral contribution types

```python
Contribution(routes=(), assets=(), startup=None, shutdown=None, metadata={})
Route(method, path, handler)     # handler: Request -> Response
Asset(path, body: bytes, media_type)
Request(method, path, params, headers, body)
Response(status=200, body=b"", media_type=…, headers={})
```

`METHODS` is the closed set `GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS`.
`METADATA_KEYS` is the closed set `("title", "description")`; any other metadata
key raises `UnknownMetadata`, and a non-string value raises `CompositionError`.
`ComposedMember` exposes `id`, `capability`, `placement`, `contribution` and
`title`.

Handlers and lifecycle hooks are **synchronous**. One that returns an awaitable
raises `CompositionError` naming the member: an un-awaited coroutine is
scheduled by nobody and would silently never run.

### Route templates

`route_template_error(template) -> str` states the whole template language, and
the matcher and the conflict check are both defined by it:

- every path rule in §1 applies (leading `/`, no `..`, no control characters, ≤
  256 characters);
- a segment is **either** a literal **or** exactly one `{name}` spanning the
  whole segment. `/a/{p}c` and `/a/x{p}` are refused, rather than being read as
  a literal by the matcher and as a parameter by the conflict check;
- `name` matches `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, and a template may not declare
  one name twice;
- at most `MAX_ROUTE_PARAMS` (16) parameters.

### Ownership

- **Routes.** Keyed by `(method, path with parameter names erased)`. `/items/{id}`
  and `/items/{key}` are the same route. A second claimant raises `RouteConflict`
  naming both members. Different methods on one path are fine.
- **Overlapping routes.** Two templates of one method *overlap* when some path
  matches both. The more specific one wins, compared **segment by segment**:
  a literal is more specific than a parameter, and one template wins only when
  it is at least as specific in every segment. `/items/new` beats `/items/{id}`
  by that rule, in either declaration order. `/{a}/y` and `/x/{b}` both match
  `/x/y` and neither dominates, so the pair is refused as `RouteConflict` with a
  witness path in the message — there is no declaration-order fallback.
- **Assets.** Keyed by path. A second claimant raises `AssetConflict` **even when
  the bytes are identical** — there is no first-wins fallback — unless the
  document's `ownership` names one of the two contenders. An `ownership` entry
  for a path nobody ships, or naming a member that does not ship it, raises
  `CompositionError`. An asset is served before any route is matched, so an
  asset path that **any** `GET`/`HEAD` route template would match raises
  `CompositionError`: `/files/a.txt` under a route `GET /files/{name}` is a
  shadow, and the test is the matcher rather than a string comparison.

### Placement

`composition.placement()` returns `(member id, Placement)` sorted by `order`
then id. `Placement(slot, order, lazy)` is metadata for whatever shell reads it.
This skill acts on none of it, ships no UI, and does not treat a slot as an
isolation or trust boundary.

---

## 4. Lifecycle

| Call | Behaviour |
| --- | --- |
| `startup()` | runs each member's `startup` in dependency order; returns the order |
| `startup()` again | `CompositionError` — it is not re-entrant |
| a member raises | already-started members are shut down in reverse order, then `StartupFailed(member, cause, rolled_back, rollback_failures, left_behind)` |
| every rollback succeeded, and the failing hook cleaned up after itself | the composition is left cleanly not-started and **may** be started again |
| a rollback raises | recorded in `rollback_failures`, never swallowed, **and latched**: the composition is unsafe |
| the failing hook raises `PartialStartup(detail)` | recorded in `left_behind` and **latched**: the hook has declared it kept resources |
| `shutdown()` | reverse dependency order, every hook runs even if an earlier one raised; failures are collected and raised as `ShutdownFailed` |
| a shutdown hook raises | **latched**, exactly as a failed rollback is: that member may still hold its port |
| `shutdown()` again | no-op returning `()` — exactly-once |
| `shutdown()` before `startup()` | no-op returning `()` |
| `KeyboardInterrupt` / `SystemExit` in any hook | never converted into `StartupFailed` or `ShutdownFailed`: the remaining cleanup still runs, the state is still latched, and the original exception is re-raised |
| `with composition:` | `startup` on entry, `shutdown` on exit |

### Hook obligations

A `startup` hook is a **transaction**. It either finishes, or it releases what
it had already built before raising. The composition rolls back *other* members;
it cannot reach inside a half-finished hook, and it does not pretend to.

A hook that genuinely cannot unwind — a child process that would not die, a lock
whose token it no longer holds — raises `PartialStartup(detail)` instead of a
bare exception. The composition then latches the unsafe state naming that member
and carries `detail` in `StartupFailed.left_behind`. The alternative is a leaked
resource nobody records, which is the one outcome worth refusing to produce.

An interrupted hook is treated the same way, because it neither finished nor
reached its own cleanup.

### The unsafe state

A member this composition could not stop means it does **not know** whether that
member is stopped: a port may still be bound, a handle still open. Starting again
would start it a second time, so it is refused. Three sources, one meaning — a
failed rollback, a failed `shutdown()`, and a startup hook that declared it kept
resources.

| Call | Behaviour |
| --- | --- |
| `unsafe_state()` | `((member id, error), …)` for every member that could not be stopped; `()` when clean |
| `startup()` while unsafe | `CompositionError` naming the members that would be started twice |
| `availability()` while unsafe | `False` |
| `readiness()` while unsafe | `(False, "unsafe: stop failed for […]")` |
| `clear_unsafe_state(resolved=[…])` | the one recovery route: the caller names **every** member it released by hand; a list that does not match exactly is refused, as is a call when nothing is latched |

There is no automatic retry and no restore. Only an operator can know whether
the resource was actually freed, so only an operator can say so.

Otherwise `availability()` answers `True` as soon as the application is
assembled — before startup, and after a clean shutdown. `readiness()` returns
`(False, "not started")` until every member has started, then `(True, "")`. They
are deliberately different questions: an availability probe that waits for
readiness makes a slow member look like a dead process.

### Concurrency

The lifecycle is **serialised by the caller**. Nothing here takes a lock, and
thread safety is not claimed: concurrent `startup`, `shutdown` and
`clear_unsafe_state` calls on one composition are the caller's to prevent.
`dispatch` holds no composition state and is re-entrant to the extent the
handlers behind it are.

---

## 5. Dispatch

```python
composition.dispatch(method, path, *, headers=None, body=b"", elide_head=True) -> Response
```

**The running window.** `dispatch` serves only between a successful `startup()`
and `shutdown()`. Outside it every request — routed, unrouted, asset or not —
is `503` carrying the readiness reason. A handler run after shutdown runs
against resources its own shutdown hook already released, and leaving that to
the host means every host has to solve it.

More specific routes are matched before less specific ones (§3). Unknown path →
`404`. Known path under another method → `405` with an `Allow` header. `GET`/
`HEAD` on an asset path returns its bytes.

**`HEAD`.** Served wherever `GET` is: if no `HEAD` route is declared for a path,
the `GET` handler answers it. Every `HEAD` response — `200`, `404`, `405`, `503`
alike — has an empty body and a `Content-Length` stating what `GET` would have
returned. An explicitly declared `HEAD` route supersedes the fallback. `Allow`
includes `HEAD` whenever `GET` is available.

`elide_head=False` returns that response **before** the body is dropped, and is
for transports only. A transport has to measure the bytes it is not going to
send; recovering the count from a header it did not write is how a handler ends
up framing the message. The ASGI adapter passes it, and is the only caller that
should.

**A handler returns a `Response`.** Anything else raises `CompositionError`
naming the owning member; an awaitable says so specifically.

**`dispatch` authenticates nobody and authorises nothing.** A caller with a trust
boundary checks it before calling.

### 5.1 The ASGI adapter, and what the host still owes

```python
asgi_app(composition, *, max_request_bytes=DEFAULT_MAX_REQUEST_BYTES) -> ASGI3 app
```

Covers `lifespan` (a failed startup is reported as `lifespan.startup.failed` and
is terminal, so the coroutine returns) and `http`. It adds no authorisation.
Websockets, streaming request bodies and server-sent events are out of scope;
any other `scope["type"]` raises `NotImplementedError`.

What the adapter guarantees, because only a transport can:

| Concern | Behaviour |
| --- | --- |
| request size | `max_request_bytes` (default `DEFAULT_MAX_REQUEST_BYTES`, 1 048 576) caps the buffered body, whether declared in `content-length` or streamed without one. Over it → `413` **before** dispatch, and the handler never sees the bytes. Accounting is a running total, not repeated concatenation. `HEAD` is held to the same limit. A non-integer, non-positive or boolean value raises `ValueError` at construction; there is no unbounded setting |
| disconnect | `http.disconnect` ends the request with **nothing sent** |
| malformed input | any message that is not `http.request` → `400`; a body chunk that is not bytes → `400` |
| header names | lowercased; RFC 9110 tokens only; a repeated field is refused rather than merged |
| header values | must be `str`; control characters (CR and LF included) and characters above U+00FF are refused as `ResponseInvalid` — a CRLF in a header value is response splitting. Nothing is coerced: a non-`str` value is refused, because coercing it would pick an encoding on the handler's behalf |
| response shape | `status` must be an `int` (a `bool` is not one) in `100`–`599`; `body` must be `bytes`. Anything else is `ResponseInvalid` before a byte is encoded |
| `content-type` | set by the adapter from `media_type`; a handler that also sends it is refused |
| `content-length` | **measured from the body**, and emitted exactly once. A handler may state it — an asset route does — but only as a claim that is checked: a non-numeric value, or a numeric one disagreeing with the byte count, is `ResponseInvalid`. It is never honoured over the bytes, because a client that believes it either truncates the body or waits for bytes nobody will send |
| hop-by-hop headers | `connection`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailer`, `transfer-encoding` and `upgrade` are refused. They are connection-scoped and belong to the server; a transfer coding beside a content length is two disagreeing statements about message length, and this adapter never streams |
| `1xx`, `204`, `304` | framed as having no body: a non-empty `body` is refused, no `content-length` is emitted, and a handler that states one is refused rather than overruled |
| `HEAD` | no body message content, whatever the handler returned, at every status. The length is measured **before** the body is dropped (`dispatch(..., elide_head=False)`), never recovered from a header |

What the **host** still owes, in full — none of it is done here:

- TLS termination;
- authentication and authorisation, including for static assets, which are
  served before any route is matched and so cannot be guarded per route;
- request-path normalisation. The ASGI `path` is already percent-decoded, so
  `%2e%2e%2f` arrives as `..` and lands in a parameter value; `dispatch`
  validates *declared* paths, never inbound ones;
- cache-control and `Vary` policy;
- concurrency limits, timeouts, keep-alive and connection lifetime;
- access logging, tracing and rate limiting;
- serialising lifecycle calls (§4, *Concurrency*).

---

## 6. Errors

Every parse-time failure is a `DocumentInvalid` carrying `.field` — the path a
person edits — and `.detail`. `UnsupportedVersion` and `CredentialShaped` are
subclasses. Every assembly, lifecycle or wire failure is a `CompositionError`:
`CapabilityNotAllowed`, `CapabilityFactoryFailed`, `RouteConflict`,
`AssetConflict`, `UnknownMetadata`, `StartupFailed`, `ShutdownFailed`,
`PartialStartup`, `ResponseInvalid`. `PartialStartup` is the one a **caller's
hook** raises rather than one this package raises (§4, *Hook obligations*).

`KeyboardInterrupt` and `SystemExit` are not in either family and are never
wrapped into one.

## 7. Public surface

`Asset` · `AssetConflict` · `CapabilityFactoryFailed` · `CapabilityNotAllowed` ·
`ComposedMember` · `Composition` · `CompositionError` · `Contribution` ·
`CredentialShaped` · `DEFAULT_MAX_REQUEST_BYTES` · `Document` ·
`DocumentInvalid` · `KIND` · `MAX_DOCUMENT_BYTES` · `MAX_DOCUMENT_DEPTH` ·
`MAX_NESTING_DEPTH` · `MAX_ROUTE_PARAMS` · `METADATA_KEYS` · `METHODS` ·
`Member` · `PartialStartup` · `Placement` · `Request` · `Response` ·
`ResponseInvalid` · `Route` ·
`RouteConflict` · `SCHEMA_VERSION` · `SUPPORTED_SCHEMA_VERSIONS` ·
`ShutdownFailed` · `StartupFailed` · `UnknownMetadata` · `UnsupportedVersion` ·
`allowlist` · `asgi_app` · `canonical_json` · `compose` · `from_json` ·
`from_yaml` · `parse` · `plain` · `route_template_error` · `to_mapping` ·
`to_yaml`.

On `Composition`: `member_ids`, `route_table`, `asset_table`, `placement()`,
`availability()`, `readiness()`, `unsafe_state()`, `clear_unsafe_state()`,
`startup()`, `shutdown()`, `dispatch()`, and the context-manager protocol.

`appcompose.demo` (the two example capabilities) is illustration, not mechanism.
Nothing in `appcompose.compose` imports it and deleting it leaves the skill
working.
