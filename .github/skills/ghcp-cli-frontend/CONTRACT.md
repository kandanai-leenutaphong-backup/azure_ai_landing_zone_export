# Terminal Contract

## Ownership

The frontend owns xterm rendering, input forwarding, viewport resize, live-session reconnect and
local controls. The Python runtime owns one PTY process per session, bounded output, secret
redaction and lifetime. The application owns model/caller identity, scopes, storage, source
authorization, launch configuration and its HTTP adapter. No application or Azure SDK is imported.

## Python API

Public exports: `ProviderConfig`, `LaunchOptions`, `PtySession`, `TerminalService`.
`ProviderConfig` retains positional endpoint/deployment/model ID; keyword provider type, wire API,
prompt/output token windows add documented configuration. HTTPS endpoints and injected bearer
credentials are required. No provider headers, browser token input or arbitrary child environment.

`LaunchOptions.arguments()` maps only typed host choices to CLI flags. Interactive is default;
plan/autopilot are explicit choices. Autopilot continuation count is 0..20, default 5. Reasoning
effort follows the tested CLI enum; session name is bounded printable text. This is startup policy,
not enforcement against commands an authorized local operator later enters inside the CLI.

`TerminalService.handle(action, headers, payload)` returns `(status, JSON object)`. Adapters lowercase
header names, limit body size and bind to loopback. All actions require matching HTTP Origin/Host,
JSON and `X-Copilot-Terminal: 1`. After creation, session ID and control key must match; never put
them in URLs or logs. Permission mismatch deliberately returns 404 rather than exposing existence.

| Action | Input Beyond Ownership | Result |
| --- | --- | --- |
| `info` | None | Actual CLI version, availability, deployment and host startup summary; no token request |
| `start` | Optional `columns`, `rows` only | 201 with control key, session ID, workspace, expiry and startup summary |
| `output` | Nonnegative cursor | Bounded long-poll text, next cursor, gap/reset flag, running state and exit code |
| `input` | Terminal text, at most 64 KiB UTF-8 | Native bytes forwarded; no shell interpolation by the host |
| `resize` | 20..400 columns, 5..200 rows | PTY resize |
| `source` | Host-defined source selection | Authorized bytes staged under private workspace, relative path returned |
| `stop` | None | Control revoked; process group terminated; files retained |
| Registered operation | Host-defined bounded payload | Host-owned result after session-key validation |

`source_loader` must authorize before reading. Runtime validates its returned relative path and
read-only copy integrity, not a storage scope it cannot know. `workspace_initializer` and registered
callbacks are trusted code. Never register built-in names as custom/task operations. Task-only
credentials are private per-session files (0600), redacted in output, and must never authorize
terminal control, arbitrary file access or another session. Consumer callbacks need their own
positive/negative tests; original showcase route behavior is not bundled.

## Frontend API

`plugin_dirs` on the service is an explicit host-approved tuple of native plugin roots, forwarded
as `--plugin-dir`; the private profile inherits no outer client plugins. `allowed_executables`
optionally names literal executable workspace files for narrow shell preapproval; escaping symlinks
and pattern paths refuse. An action's `autopilot` option selects only verified limited permissions
in the native dialog and refuses unknown states before submitting. No blanket approval is added.

`CopilotTerminal` accepts `apiBase`, `active`, optional `source`, and optional `actions`.
`TerminalAction` retains `id`, `label`, `title`, `prompt`, `stage`, `prepare` and `onPrepared`.
Prepared actions intentionally submit a host-supplied prompt once readiness is detected. The fixed
native inspection menu only inserts text; the operator reviews/submits it. The terminal owns slash
commands, tool approvals, shell mode and control sequences. No fake chat rendering is substituted.

## Refusals And Limits

Origin/header refusal: 403. Unknown or wrong-key sessions: 404. Invalid sizes, payloads, launch
override or source paths: 400. Credential/start failures: 503 without exception secrets. The local
example validates body size before JSON parsing and exposes no cloud login or anonymous network route.

The provider credential lives in the process environment, not browser JSON. CLI secret-env filtering
and PTY redaction protect interfaces, not against a hostile process with the same OS identity.
Default lifetime is at most an hour and expires before the provider token; tokens do not refresh
inside an existing process. Idle expiry closes disconnected sessions. Bounded replay may signal a
gap. Stop/shutdown invalidate live ownership; on-disk session files are retained, not silently deleted.