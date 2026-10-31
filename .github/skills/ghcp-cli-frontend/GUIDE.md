# GHCP CLI Frontend

Requested lookup name: `ghcp_cli_frontend`. Portable skill ID: `ghcp-cli-frontend`; the catalogue
accepts both and returns one canonical entry. Existing npm `copilot-terminal`, Python
`copilot_terminal`, and React `CopilotTerminal` APIs remain compatible.

One reusable capability: `copilot-terminal` React/xterm client and
`copilot_terminal.TerminalService` framework-independent Python PTY service. The browser
forwards terminal bytes to one interactive process per session. It does not emulate a model,
interpret prompts, or launch a new `copilot -p` process for each message.

## Choose The Right Surface

| Need | Use |
| --- | --- |
| Preserve native CLI interaction inside a React surface | This component and PTY service |
| Script a single non-interactive CLI request or consume JSONL | Native CLI prompt mode; a different adapter |
| Embed structured agent events rather than a terminal | Evaluate the official SDK/ACP contract separately |
| Public or shared multi-user terminal | Add real caller authentication, owner authorization and OS isolation first; not provided here |

## Integrate

1. Install `copilot-terminal-runtime` and `copilot-terminal` using [README.md](README.md).
   Import their public APIs; do not add a skill or source directory to `sys.path`.
2. Supply the absolute standalone `copilot` executable, an explicit command `PATH`, and a
   private workspace root outside repository/user-home ancestry. A VS Code shim may fail when
   `HOME` changes. Probe the actual binary, not its wrapper.
3. Read provider configuration at the host edge. Supply `ProviderConfig` and a server-side
   callback returning `(bearer_token, expiry_epoch_seconds)`. Keep model alias distinct from wire
   deployment. The host owns identity and scope; the runtime reads no service environment or Azure SDK.
4. Optionally supply `LaunchOptions` for initial interactive/plan/autopilot mode, bounded
   continuations, reasoning effort, session name, screen-reader and mouse settings. These are
   host-owned startup options, not a browser launch-argument API.
5. Mount `TerminalService.handle(action, headers, payload)` at an application-owned API prefix.
   Normalize header names, bound JSON request bodies and retain the same-origin guard. Always call
   `close()` on shutdown. Use the [local example](examples/serve.py) as an adapter, not a cloud gateway.
6. Render `CopilotTerminal` from the npm package. Its native command menu inserts inspection
   commands without pressing Enter. A host action may request `autopilot: true`: it confirms only
   the recognized limited-permission option and refuses unknown dialogs before submitting its task.
7. Add `source_loader` only when the host can authorize the selected source before reading it.
   Return `(relative_path, bytes)`; the runtime stages a read-only local copy and refuses changed
   copies, traversal and escaping symlinks. This is not an upload or arbitrary-file-read endpoint.
8. Use optional `workspace_initializer`, `operations`, `task_operations`, and prepared frontend
   `actions` for bounded host capabilities. Register no built-in route names, permission-changing
   routes or arbitrary commands. The separate task credential may call only its named task routes.
9. Pass host-approved `plugin_dirs` for native skills and agents; private CLI state does not inherit
   the outer profile. `allowed_executables` may approve exact initialized workspace helpers, never
   a pattern, outside path or blanket shell permission.

## Official-Docs Enrichment

The [feature map](references/official-cli-features.md) records official sources, tested CLI version,
implemented options, useful native commands and deliberate deferrals. Read it before widening scope.

- Plan/autopilot are workflow modes, not permission grants. The default stays interactive; autopilot
  defaults to five continuations. Limited permissions may deny autonomous work rather than prompt.
- `--no-ask-user`, `--allow-all*`, `--yolo`, remote steering and session export are not added.
- Reasoning/model token limits describe model behavior; they are not hard billing quotas.
- `/context`, `/usage`, `/env`, `/skills list`, `/mcp list`, `/session info` and `/help` are useful
  native inspection commands. `/compact`, reviews, research and autonomous work may invoke a model.
- Official custom providers include OpenAI-compatible, Azure and Anthropic routes. This host
  adapter deliberately supports HTTPS plus injected bearer credentials, not arbitrary headers,
  API-key entry in a browser or plaintext local-provider HTTP.

## Security And Lifetime

The HTTP boundary requires a loopback Host, matching HTTP Origin, JSON and `X-Copilot-Terminal: 1`.
After Start it also requires the session's unguessable control key. Wrong ownership returns 404;
cross-origin access returns 403. These are local anti-CSRF/ownership controls, **not user login**.
Never expose this host to a network by trusting forwarded Host headers.

Private `HOME`/`COPILOT_HOME`, disabled remote export, a restricted child environment and
`--secret-env-vars` keep the provider token off browser/child-tool interfaces; output redaction
also covers secrets split across reads. Do not log bodies, keys or child environments. A process
running as the same OS user is not a secret-isolation boundary; use a dedicated user/container.

Defaults: four active records, five-minute disconnected idle expiry, one-hour maximum process
lifetime shortened by token expiry, one million replay characters. Reload reconnects to the same
live process using sessionStorage. Stop revokes control and kills the process group; it retains
workspace files. Native `/resume` is a different operation and does not restore the host's key after Stop.

## Verify

```bash
"$PYTHON_ENV/bin/python" "$LIBRARY_ROOT/tests/selftest.py"
"$PYTHON_ENV/bin/python" "$LIBRARY_ROOT/tests/native_cli.py" --cli "$COPILOT_EXECUTABLE"
```

The selftest is standard-library-only. The optional native test uses CLI 1.0.83 with private
offline state and only native commands; `--plugin-dir "$HARNESS_PLUGIN_ROOT"` additionally checks
the harness workflow and agent dialogs. No model call or credential acquisition occurs.
The standalone browser example and [browser test](tests/browser.mjs) cover actual xterm/PTY,
prepared actions, read-back, reconnect, keyboard, responsive geometry and refusal paths. The
fixture is explicitly labelled, not passed off as Copilot. Setup and commands: [README.md](README.md).
The [native autopilot check](tests/autopilot.mjs) operates the real offline CLI and rejects an
unrecognized permission dialog before selecting permissions or sending the prepared action.

Linux is verified. Python PTY requires POSIX; Windows is unsupported and macOS is unverified.
Live model completion, provider-specific authentication, billing and cloud multi-user exposure
remain unverified until explicitly configured and authorized. No MCP server or deployment is installed.