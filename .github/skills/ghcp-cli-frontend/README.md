# Copilot Terminal

Interactive Copilot CLI in React/xterm, backed by a private POSIX PTY. Skill lookup accepts
`ghcp_cli_frontend`; the portable directory/metadata use `ghcp-cli-frontend` because the Agent Skills
spec permits hyphens, not underscores. Package APIs remain `copilot-terminal` (npm),
`copilot-terminal-runtime` (Python distribution), `copilot_terminal` (Python import).

## Package And Integrate

Canonical owner: `.github/skills/ghcp-cli-frontend`. Set `LIBRARY_ROOT` to this directory and install
the Python distribution into an isolated environment. No skill source is loaded at runtime:

```bash
python3 -m venv "$PYTHON_ENV"
uv pip install --python "$PYTHON_ENV/bin/python" "$LIBRARY_ROOT"
```

Python 3.11+ on Linux/POSIX; runtime has no third-party Python dependencies. Install the host's
identity SDK separately. The frontend package exports ESM, declarations and CSS for a bundler
handling React 19. Build before packing or consuming a source-workspace package. React is a peer;
`@xterm/xterm`, `@xterm/addon-fit` and `lucide-react` are declared runtime dependencies.

```tsx
import { CopilotTerminal } from 'copilot-terminal'

<CopilotTerminal apiBase="/api/my-terminal" active={active} />
```

Optional `source={{ uid, path }}` enables host-authorized staging. `actions` supplies prepared
host workflows; `prepare` names a registered operation whose result owns the final prompt.
The native command menu only inserts text. Browser-selected executable/model/launch flags are refused.

```python
from copilot_terminal import LaunchOptions, ProviderConfig, TerminalService

terminal = TerminalService(
        cli=standalone_cli_path,
        provider=ProviderConfig(endpoint=model_endpoint, deployment=wire_deployment,
                                                        model_id=base_model_id, provider_type="openai", wire_api="responses"),
        workspace_root=private_workspace_root,
        token_provider=issue_token,
        path=explicit_command_path,
        launch=LaunchOptions(mode="plan", reasoning_effort="medium", session_name="Local review"),
)
```

The host supplies these values; this is an integration shape, not invented Azure configuration.
`issue_token()` returns a server-issued bearer token and expiry epoch. Use `openai` with a full
OpenAI-compatible endpoint or `azure` with its host URL; confirm the correct route with your
provider. Provider variants and token windows are tested as configuration, not live model access.
`mode="autopilot"` is explicit opt-in with default five continuations and an adapter cap of twenty.
Host actions with `autopilot: true` select only the recognized "Continue with limited permissions"
dialog option, confirm the transition, then submit the prepared prompt. Unknown dialogs refuse;
no blanket tool grant is added. Call `terminal.close()` during shutdown.

Optional `plugin_dirs=(approved_plugin_root,)` explicitly loads native plugins in the private CLI.
It does not inherit the outer agent's profile. `allowed_executables` may return exact executable
helpers within the initialized workspace; escaping, symlinked or pattern-shaped paths refuse.

## Standalone Example

Prerequisites: Python 3.11+, Node 20.19+ or 22.12+, npm. The actual CLI is needed only for native or
live-provider use. The example defaults to no mode: choose its clearly labelled fixture explicitly.
Set `EXAMPLE_ROOT` to a fresh external directory, such as one returned by `mktemp -d`:

```bash
mkdir -p "$EXAMPLE_ROOT"
cp -a "$LIBRARY_ROOT" "$EXAMPLE_ROOT/library"
uv pip install --python "$PYTHON_ENV/bin/python" "$EXAMPLE_ROOT/library"
npm ci --prefix "$EXAMPLE_ROOT/library"
npm run build --prefix "$EXAMPLE_ROOT/library"
npm run typecheck --prefix "$EXAMPLE_ROOT/library"
npm run lint --prefix "$EXAMPLE_ROOT/library"
GHCP_FRONTEND_BUILD_DIR="$EXAMPLE_ROOT/dist" npm run build:example --prefix "$EXAMPLE_ROOT/library"
"$PYTHON_ENV/bin/python" "$EXAMPLE_ROOT/library/examples/serve.py" --dist "$EXAMPLE_ROOT/dist" \
    --sessions "$EXAMPLE_ROOT/sessions" --port 8765 --fixture
```

Use a free port, or `--port 0` and read the printed URL. Session roots must be outside repository
and user-home ancestry. The fixture is a real PTY transport exercise, not a Copilot/model emulator.
It executes no shell commands or model calls. Stop the example with Ctrl+C to close its sessions.

For real use, replace `--fixture` with `--cli "$COPILOT_EXECUTABLE" --endpoint "$MODEL_ENDPOINT"
--deployment "$MODEL_DEPLOYMENT" --model-id "$BASE_MODEL_ID" --expires-at "$TOKEN_EXPIRY"`.
The example reads the host-provided `GHCP_FRONTEND_TOKEN` environment value or a name chosen by
`--token-env`; it never accepts a token on the command line or from a browser. Obtain credentials
through the host's approved flow. Do not paste secrets into chat, shell arguments, tests or logs.
Live prompts spend provider resources and need separate authorization.

## Verify

```bash
"$PYTHON_ENV/bin/python" "$LIBRARY_ROOT/tests/selftest.py"
"$PYTHON_ENV/bin/python" "$LIBRARY_ROOT/tests/native_cli.py" --cli "$COPILOT_EXECUTABLE"
```

Backend selftests cover twenty-two cases without a CLI or model. The native test additionally proved
CLI 1.0.83 startup, `/help`, `/session info`, resize, wrong-key refusal and process cleanup with
private offline state and a non-secret loopback test provider. Add `--plugin-dir "$HARNESS_PLUGIN_ROOT"`
to verify the harness workflow and agent dialogs. No live inference was run.

For the running fixture example, install Chromium into an external cache and run the browser gate:

```bash
PLAYWRIGHT_BROWSERS_PATH="$EXAMPLE_ROOT/browsers" \
    node "$EXAMPLE_ROOT/library/node_modules/@playwright/test/cli.js" install chromium
PLAYWRIGHT_BROWSERS_PATH="$EXAMPLE_ROOT/browsers" \
    node "$EXAMPLE_ROOT/library/tests/browser.mjs" --url "$EXAMPLE_URL" --out "$EXAMPLE_ROOT/evidence"
```

Browser acceptance operates command insertion, prepared actions, source read-back, reload,
interrupt, resize, Stop and matching refusals on desktop/mobile. It records screenshots and
geometry, not secrets. It proves UI/transport behavior, not a model answer.

To check the native limited-autopilot transition, replace the example's `--fixture` with
`--offline-cli "$COPILOT_EXECUTABLE"`, then run the same browser command with
`tests/autopilot.mjs`. This mode supplies an unreachable loopback provider, exposes only a native
`/session info` action, and checks both limited-permission completion and unknown-dialog refusal.
Native CLI/browser verification requires an explicitly supplied CLI and installed browser runtime;
it is separate from the offline Python acceptance gate.

## Boundaries

The host pre-trusts its freshly created private workspace and any explicitly supplied `extra_dirs`.
Additional directories also load trusted CLI skills/agents; they are not read-only sandboxes.
Normal interactive tool approvals remain. A loopback Host check is not multi-user authentication,
and private files/environment filtering are not OS process isolation. Do not mount this adapter
behind a public proxy or expose forwarded loopback headers as proof of identity.

Linux was verified; Windows PTY is unsupported and macOS is unverified. Native slash commands and
screen-readiness detection can change between CLI releases. Session reload restores a live process;
Stop does not implement durable resume, and retained files need host-owned cleanup.

API details: [CONTRACT.md](CONTRACT.md). Operational pitfalls: [GOTCHAS.md](GOTCHAS.md).
Official features and deferrals: [references/official-cli-features.md](references/official-cli-features.md).
Original package provenance: [PROVENANCE.md](PROVENANCE.md).
Integration procedure: [GUIDE.md](GUIDE.md). Installed Python guidance lives under
`share/copilot-terminal` in the environment prefix. Distribution includes typing metadata.

## Migration Verification

2026-09-16: installed Python 3.11 package passed all 22 offline PTY/ownership/refusal tests;
frontend ESM/declaration build and TypeScript 6 check passed with Node 20.20. Native Copilot,
live providers and terminal browser tests were not rerun in this migration. The original
skill runtime and package metadata are retired; no source-path import fallback remains.

Framework scope: F2 packaging/types and F3 host-owned authority are covered by these checks.
F4 retains the existing safe HTTP/exception contract; F5 uses explicit synchronous `close()`;
F6 retains session/time/output ceilings, not a shared run budget; F7 retains private host state
and bounded replay, not durable resume; F8 retains explicit callbacks and fixture coverage.
F1 discovery is in the [catalogue](../../../libraries/capabilities.json); the
[native-exception assessment](../harness-guide/framework/CONFORMANCE.md#native-exceptions-and-unverified-boundaries)
owns selected framework scope. Native CLI provider accounting is not a shared billing quota.