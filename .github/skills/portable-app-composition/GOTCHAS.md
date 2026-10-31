# GOTCHAS

Numbered so code and documents can cite them. Symptom first, because that is
what you have when you arrive here. Every entry below was hit while building or
testing this skill, not imagined.

## G1 — A credential allowlist containing `""` silently disables the whole scan

**Symptom.** `parse()` accepts `{"api_key": "9f2c1d5b7a3e"}` without raising
`CredentialShaped`, and every other credential test passes too — because none of
them fail.

**Cause.** The scan skips a value when any allowed token appears in it:
`any(token in value for token in ALLOWED)`. An empty string is *in* every string,
so one stray `""` in the tuple makes the check always skip.

**Fix.** Never put an empty string in a substring allowlist. The empty-value case
belongs in the length guard (`len(value) >= 8`), not in the token list. See
`_CREDENTIAL_ALLOWED` in `appcompose/document.py`.

## G2 — `mappingproxy` raises `TypeError` on assignment but has no `__setitem__`

**Symptom.** A test written as `expect(TypeError, lambda: settings.__setitem__("k", 1))`
fails with `AttributeError: 'mappingproxy' object has no attribute '__setitem__'`.

**Cause.** `types.MappingProxyType` implements the mapping protocol at C level
without exposing `__setitem__`. The statement `proxy["k"] = 1` raises
`TypeError`; the attribute lookup raises `AttributeError`.

**Fix.** Test immutability with a real assignment statement inside a small
function, never through the dunder.

## G3 — `yaml.safe_load` accepts duplicate keys and aliases

**Symptom.** A document has `name:` twice and the program uses the second one
without a word. Or a 200-byte file exhausts memory on load.

**Cause.** `safe_load` blocks arbitrary object construction and nothing else.
Duplicate keys are last-wins by design; anchors and aliases expand
multiplicatively (the "billion laughs" shape).

**Fix.** Load configuration with a loader that refuses both, as
`_StrictLoader` in `appcompose/serialisation.py` does. Refusing aliases outright
is what makes the expansion impossible; a size cap alone does not, because the
input is small.

## G4 — `schemaVersion: true` passes an `isinstance(v, int)` check

**Symptom.** A boolean, or the YAML values `yes` / `on`, are accepted as a
version and compared as `1`.

**Cause.** `bool` is a subclass of `int` in Python.

**Fix.** Check `isinstance(value, bool)` first and reject. Applied to
`schemaVersion`, to `layout.*.order`, and to `settings.limit` in the demo
capability.

## G5 — `/items/{id}` and `/items/{key}` look like different routes

**Symptom.** Two members compose cleanly, then one of them never receives a
request in production.

**Cause.** A conflict check that compares path strings sees two different
strings. A router matching by segment shape sees one route.

**Fix.** Erase parameter names before comparing (`_shape` in
`appcompose/compose.py`), so the conflict is refused at compose time with both
member ids named.

## G6 — Identical asset bytes are still a conflict

**Symptom.** Two members ship the same stylesheet, and you expect a composition
to notice the bytes match and move on.

**Cause.** "Same bytes today" is not ownership. The next version of one member
changes the file, and the winner is decided by iteration order — the hardest
class of bug to see, because nothing failed.

**Fix.** `AssetConflict` unless the document's `ownership` names one of the two
contenders. There is deliberately no first-wins fallback.

## G7 — The credential scan is a backstop, not a proof

**Symptom.** A document passes validation, so somebody concludes it contains no
secret.

**Cause.** The scan matches a fixed set of key names with literal string values.
A secret under the key `token_material`, or one split across two fields, is not
matched.

**Fix.** Treat a pass as "no obvious mistake", never as evidence. Secrets are
kept out by where they are stored, not by a regular expression.

## G8 — An ASGI `lifespan` coroutine does not return after startup

**Symptom.** A test helper that feeds one `lifespan.startup` message and awaits
the app crashes with `IndexError: pop from empty list`, or hangs.

**Cause.** The lifespan protocol is one long-lived coroutine per process: after
replying `startup.complete` it loops and waits for `shutdown`. It only returns
after shutdown — or, here, after a failed startup, which is terminal.

**Fix.** Drive it as a task with a queue for both messages, as
`LifespanSession` in `examples/asgi_headless_app.py` does. Do not model it as a
request/response pair.

## G9 — ASGI header names must be lowercase

**Symptom.** A response carries `Content-Length`, and a client reading
`headers["content-length"]` gets a `KeyError`.

**Cause.** ASGI specifies lowercase header names on the wire. Servers are not
required to normalise what an application sends.

**Fix.** Lowercase on the way out, in `appcompose/asgi.py`. The `Response`
object itself keeps whatever case the handler used, so the adapter is the single
place that knows the wire rule.

## G10 — A conformance gate runs `tests/selftest.py` without `PYTHONPATH`

**Symptom.** `python3 tests/selftest.py` works in your shell and fails with
`ModuleNotFoundError: No module named 'appcompose'` under the gate.

**Cause.** The upstream validator executes the selftest with the box as the
working directory and does not add it to `PYTHONPATH`. The current directory is
not on `sys.path` for a script run by path.

**Fix.** Every entry script inserts its own parent directory:
`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`. Do it in
examples, scripts and tests alike — one of them will be run in a way you did not
plan for.

## G11 — A one-character id is refused

**Symptom.** `members[0].id: 'a' does not match ^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$`
on a document that looks obviously fine.

**Cause.** The pattern is a leading character plus 1 to 63 more, so the minimum
length is two. Single letters are a poor id in a namespace shared with `layout`
and `ownership`, and the rule is deliberate — but the message reads as a typo.

**Fix.** Use ids of two characters or more.

## G12 — Removing a member renumbers every field path after it

**Symptom.** `document.without("store")` raises
`members[0].requires[0]: names 'store'…` when `store` was at index 0 and the
consumer was at index 1.

**Cause.** `without()` re-validates the *resulting* document, so field paths are
positions in the document you would now edit — not in the one you started with.

**Fix.** Read the path against the new document. This is the useful behaviour:
the path points at the line you have to fix.

## G13 — A second `shutdown()` returns `()` rather than raising

**Symptom.** Code that treats a non-empty return as "we stopped things" thinks
nothing happened on the second call.

**Cause.** Shutdown is exactly-once by contract: the second call is a no-op, as
is a call before `startup()`. Raising there would turn correct defensive cleanup
— a `finally` block plus a context manager — into an error path.

**Fix.** Treat `()` as "nothing left to stop", not as failure. Check
`readiness()` if you need the state.

## G14 — `dispatch` authorises nothing

**Symptom.** A route that should be protected answers anyone.

**Cause.** By design. `Composition.dispatch` is a router; it authenticates
nobody, and a layout slot is metadata for a shell rather than an isolation
boundary.

**Fix.** Check your trust boundary before calling `dispatch`, or in a wrapper
around `asgi_app(...)`. `examples/refusals.py` ends with the smallest honest
version of that. Note that assets are served *before* any route is matched, so
the guard has to wrap the whole call, not a route.

## G15 — `yaml.safe_dump(allow_unicode=True)` loses U+0085

**Symptom.** A description containing NEL (U+0085) comes back with a space where
it was, and a round trip that is byte-identical for every ASCII document fails
for that one.

**Cause.** The emitter writes NEL raw, and the loader treats it as a line break
and folds it to a space. U+2028, U+2029, tab, CR, LF and NBSP all survive; NEL
is the single hole, and `name`'s own pattern (`[^\x00-\x1f]`) admits it.

**Fix.** Do not trust a serialiser's round trip — verify it. `to_yaml` reads its
own output back and compares canonical bytes, re-emitting with
`allow_unicode=False` when the readable form loses something, and refusing if
neither form survives. A round-trip test built only from ASCII samples proves
nothing about the universal claim it is written under.

## G16 — Restarting after a *failed* rollback starts a member twice

**Symptom.** `startup()` fails, its rollback also fails, you fix the cause, call
`startup()` again, and the first member is started a second time while the first
instance is still holding a port.

**Cause.** A rollback failure was recorded and then ignored: the composition was
left in the same "not running" state as a clean rollback, so a retry looked
safe. It was not — nothing knows whether those members stopped.

**Fix.** The failure latches. `unsafe_state()` is non-empty, `availability()` is
`False`, and `startup()` refuses naming the members. Recovery is
`clear_unsafe_state(resolved=[...])`, which requires naming every latched
member, because only an operator can know the port was freed.

## G17 — A static asset silently shadows a parameterised route

**Symptom.** `GET /files/a.txt` returns bytes nobody expected, while
`GET /files/b.txt` reaches the handler. Both look right in the route table.

**Cause.** Assets are served before routing, and a collision check that only
compared *literal* route paths never saw that `/files/{name}` matches
`/files/a.txt`.

**Fix.** Run the collision check through the matcher, not through string
equality — the same function that dispatches. `_collect_assets` does.

## G18 — `/a/{p}c` is read two different ways in one program

**Symptom.** Two obviously different paths, `/a/{p}c` and `/a/{q}c`, are refused
as a `RouteConflict` on `/a/{}c`.

**Cause.** The matcher required a segment to *end* with `}` after the name and
so read `{p}c` as a literal; the conflict check's regex erased `{p}` and read it
as a parameter. Two components disagreeing about what a parameter is.

**Fix.** State the template language in one place (`route_template_error`) and
refuse anything outside it. A segment is either a literal or exactly one
`{name}`; mixing them is now a compose-time refusal with the reason.

## G19 — `/{a}/y` and `/x/{b}` are routed by declaration order

**Symptom.** `GET /x/y` reaches one member. Somebody reorders the members, or a
dict iterates differently, and it reaches the other. Nothing failed.

**Cause.** A tiebreak that counts `{` characters cannot order two templates with
the same number of parameters in different positions. They cross: neither is
more specific.

**Fix.** Compare specificity segment by segment and require one template to
dominate in *every* segment. `/items/new` over `/items/{id}` is a rule;
`/{a}/y` versus `/x/{b}` is a coin toss, so it is refused with a witness path in
the message.

## G20 — `RecursionError` is not a `DocumentInvalid`

**Symptom.** A caller that catches `DocumentInvalid` and prints `.field` gets an
uncaught `RecursionError` from a 12 KB input, far under `MAX_DOCUMENT_BYTES`.

**Cause.** `json.loads` and `yaml.load` recurse per nesting level, and a size cap
does not bound depth. A mapping handed straight to `parse` skips both parsers
and hits the validator's own recursion instead.

**Fix.** Bound depth explicitly: on the text before parsing
(`MAX_NESTING_DEPTH`), and while walking a mapping (`MAX_DOCUMENT_DEPTH`), with
cycle detection for a mapping that contains itself. Catching `RecursionError` is
the backstop, not the mechanism.

## G21 — A credential scan that only reads strings

**Symptom.** `{"api_key": ["AbCdEf0123456789"]}` parses clean while
`{"api_key": "AbCdEf0123456789"}` is refused.

**Cause.** The scan matched the key, then tested `isinstance(value, str)` before
looking at it. A list, a dict or a number under the same key skipped the check
entirely — a one-character bypass.

**Fix.** Decide on the *key*, then constrain what the value may be: a reference
string, a blank string, or null. Everything else is refused. It is still a
backstop (G7) — a secret under `token_material` is not detectable at all.

## G22 — A CRLF in a response header is response splitting

**Symptom.** A handler returns `headers={"X-Note": value}` where `value` came
from a request, and the wire carries two headers.

**Cause.** The neutral `Response` is in-process data; nothing validated it on
the way to the transport, and ASGI servers do not all check.

**Fix.** The adapter validates every name and value and raises `ResponseInvalid`
rather than framing it. The same pass lowercases names, refuses a repeated field
(two `content-length` values is smuggling written down), and settles
`Content-Length` itself. A handler is trusted for meaning, never for framing.

## G23 — An `async def` hook is never awaited

**Symptom.** A member's `startup` is an `async def`, composition starts cleanly,
and the store is never opened. Python may or may not print
"coroutine was never awaited", depending on when it is collected.

**Cause.** Calling a coroutine function returns a coroutine object and runs
nothing. A synchronous lifecycle that ignores the return value swallows it.

**Fix.** Refuse it. Hooks and handlers that return an awaitable raise
`CompositionError` naming the member. The lifecycle here is synchronous and
serialised by the caller; wrap the await in the adapter you own.


## G24 — A handler-supplied `Content-Length` used to be believed

**Symptom.** A handler returns `Response(body=b"abc",
headers={"Content-Length": "1"})`. The adapter emits `content-length: 1` and a
three-byte body. Curl prints `abc` and reports success; a keep-alive client
reads one byte, treats `bc` as the start of the next response, and the
connection desynchronises.

**Cause.** `_wire_headers` accepted any *numeric* handler value and only fell
back to `len(response.body)` when none was supplied. Validating the digits
proved the header was a number, not that it was the truth. The module docstring
said the adapter owns the framing; the code let the handler own it.

**Fix.** Measure. `Content-Length` is computed from `len(response.body)`, and a
handler value is treated as a claim to check: a disagreement is
`ResponseInvalid`, never a preference. Nothing above the transport is trusted
with message length.

## G25 — `HEAD` loses the bytes it has to state the length of

**Symptom.** The obvious repair for G24 — "just use `len(response.body)`" —
makes every `HEAD` respond `Content-Length: 0`, because `dispatch` already
dropped the body.

**Cause.** Two owners for one number. `dispatch` elides the body for `HEAD`
(correctly: a `HEAD` body is a protocol violation at any status), and by the
time the adapter measures, there is nothing left to measure. Recovering the
count from the header `dispatch` wrote just reintroduces G24 through a longer
path.

**Fix.** Measure before the strip. The adapter calls
`dispatch(..., elide_head=False)`, takes `len(response.body)` while the bytes
are still there, and drops them itself. In-process callers keep the default and
see the familiar elided response.

## G26 — `Transfer-Encoding` from a handler, beside a `Content-Length`

**Symptom.** A handler sets `Transfer-Encoding: chunked` to stream. The adapter
does not stream, so the body is sent whole, with both fields on the wire.

**Cause.** Two disagreeing statements about message length. RFC 9110 makes
`Transfer-Encoding` win, so a proxy reads the body as chunk headers — the exact
shape of request smuggling.

**Fix.** Every hop-by-hop field is refused: `connection`, `keep-alive`,
`proxy-authenticate`, `proxy-authorization`, `te`, `trailer`,
`transfer-encoding`, `upgrade`. They are connection-scoped and belong to the
server.

## G27 — `204` and `304` are framed as having no body at all

**Symptom.** A handler returns `Response(status=204, body=b"deleted")`, or
states `Content-Length: 0` on a `304`. h11 raises, or the server silently drops
what was sent.

**Cause.** RFC 9110 gives `1xx`, `204` and `304` no body, and a server frames
them that way regardless of what the application supplied.

**Fix.** The adapter holds them to it: a non-empty body is `ResponseInvalid`, no
`content-length` is emitted, and a handler that states one is refused rather
than quietly overruled. `tests/loopback_check.py` reads the resulting bytes off
a real socket, because "the adapter emitted the right ASGI messages" and "a
client received the right bytes" are different claims.

## G28 — A failed `shutdown()` left the composition startable

**Symptom.** An app starts, a member's stop hook raises, `ShutdownFailed` is
handled and logged, and a supervisor calls `startup()` again. The member that
would not stop is now running twice.

**Cause.** `shutdown` set `_running = False` and cleared `_started` before
raising. The latch existed, but only a *rollback* failure set it — the same bug
as the earlier rollback one, reached through the other door.

**Fix.** Any member this composition could not stop latches it, whichever call
failed. `availability()` goes `False`, `startup()` refuses naming the member,
and `clear_unsafe_state(resolved=[...])` is the only way back.

## G29 — Ctrl-C during startup came back as `StartupFailed`

**Symptom.** A slow startup is interrupted. The caller's `except
StartupFailed:` branch catches it, logs "startup failed", and carries on. The
process does not exit.

**Cause.** `except BaseException` wrapped everything, including
`KeyboardInterrupt` and `SystemExit`. An interrupt that a caller has to catch a
domain error to observe is not an interrupt.

**Fix.** Roll back, record the state, then re-raise the original. The
interrupted member is latched too: its hook neither finished nor reached its own
cleanup, so what it holds is unknown, and unknown is latched rather than
forgotten.

## G30 — A startup hook that cannot unwind itself

**Symptom.** A hook spawns a child process, then fails. Rollback runs for every
*other* member, the composition reports a clean failure, and the child is still
running.

**Cause.** The composition rolls back members it started. It cannot reach inside
a half-finished hook, and a hook that raises a bare exception is claiming, by
default, that it cleaned up after itself.

**Fix.** Make the obligation explicit. A `startup` hook is a transaction; one
that genuinely cannot unwind raises `PartialStartup(detail)`, which latches the
unsafe state naming that member and carries `detail` in
`StartupFailed.left_behind`. A leaked resource that is recorded can be dealt
with; one that is not, cannot.

## G31 — A copied box is not an importable one

**Symptom.** `cp -r portable-app-composition vendor/` succeeds, and
`from appcompose import compose` from the consumer's own root raises
`ModuleNotFoundError` with `PYTHONPATH` clear.

**Cause.** Copying puts files on disk; it puts nothing on `sys.path`. The usual
fix — a `sys.path.insert` at the top of the consumer's entry point — is exactly
the kind of positional fragility this skill exists to remove, and it breaks the
moment the copy moves.

**Fix.** `pyproject.toml`, and a plain non-editable
`python -m pip install ./vendor/portable-app-composition`. Only `appcompose`
and `appcompose.demo` are installed, including CLI modules and demo data; `tests/` and `examples/` stay
in the copy, so nothing ships a top-level `tests` package into somebody else's
site-packages.

## G32 - Immutable mapping defaults can still fail on Python 3.11

**Symptom.** Importing the package on Python 3.11 raises a dataclass `ValueError` about a
mutable `mappingproxy` default, before any document is read.

**Cause.** Python 3.11 treats an unhashable field default as mutable. Its mapping proxy is
unhashable even when wrapping an empty immutable view; the source baseline ran on a newer Python.

**Fix.** Construct each empty mapping proxy through `field(default_factory=...)`. The resulting
values remain immutable and independent. The locked MCP and copied-out native tests run on
Python 3.11 and catch an import-time regression; changing the document format is unnecessary.
