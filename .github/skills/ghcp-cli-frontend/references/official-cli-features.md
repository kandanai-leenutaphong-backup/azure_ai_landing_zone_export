# Official CLI Features

Checked 2026-09-09 against GitHub's documentation and the installed **GitHub Copilot CLI 1.0.83**.
Documentation evolves independently; recheck `copilot --help`, `copilot help commands` and
`copilot help providers` for a different binary. No model request is needed for those checks.

Sources:

- [CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [Autopilot](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot)
- [Bring your own key](https://docs.github.com/en/copilot/concepts/models/bring-your-own-key)
- [Local sandbox policy](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/understanding-local-sandboxing)
- [Agent Skills specification](https://agentskills.io/specification)

[official-sources.json](official-sources.json) is a repeatable target list for a public-web acquisition
tool. Only source metadata and these paraphrased decisions ship; full downloaded GitHub text is
not bundled. Network pages are evidence, not permission to run their example commands.

## Implemented Enrichment

| Official Feature | Integration | Acceptance And Limit |
| --- | --- | --- |
| `--mode interactive\|plan\|autopilot` | Typed host `LaunchOptions.mode`; interactive default | Unit tests inspect argv and refusals; only interactive native startup exercised |
| `--max-autopilot-continues` | Host integer 0..20; default 5 | CLI docs default is 5; adapter cap is our policy, not a GitHub quota |
| `--reasoning-effort` | Optional tested CLI enum | Configuration tested; model may not support every level |
| `--name` | Optional bounded host session name | No command/control characters or browser option injection |
| `--screen-reader`, `--no-mouse` | Host accessibility choices; xterm screen-reader support retained | Backend argv verified; actual desktop/mobile DOM and geometry inspected |
| `--secret-env-vars` | Provider bearer value excluded from CLI tools; additional PTY redaction | Split-secret and private-env tests; not OS-user isolation |
| `--no-remote-export`, `--no-remote` | Both are always on at startup | Native CLI accepts the flags; no implicit session sharing |
| OpenAI-compatible/Azure/Anthropic BYOK | Typed provider type, wire API, model alias and deployment | HTTPS + injected bearer only; no live provider calls in acceptance |
| Provider prompt/output token windows | Optional positive integers passed as documented variables | Model context limits, not a billing budget |
| Native help/context/usage/env/session/skills/MCP inspection | Fixed menu inserts supported commands | Operator submits; browser fixture exercises menu and native PTY test exercises Help/Session |

Mode is not permission. Official autopilot documentation says it can continue autonomously until
completion, interruption or its continuation bound. Without full permissions, operations needing
approval may be denied. This skill neither selects full permission for the operator nor adds
`--no-ask-user`; the two are distinct from mode and from one another.

## Useful Native Workflows

The terminal already preserves native CLI behavior; avoid implementing a second agent around it.

| Workflow | Native Surface | Host Decision |
| --- | --- | --- |
| Inspect loaded environment | `/env`, `/skills list`, `/mcp list`, `/list-dirs` | Read the result; installation presence is not a running-service claim |
| Manage context | `/context`, `/compact [focus]` | Context inspection is read-only; compaction can invoke a model |
| Inspect usage/session | `/usage`, `/session info` | Usage is observation; CLI credits are not a hard BYOK billing limit |
| Change model/reasoning | `/model`, host startup options | Confirm provider supports the model; wire deployment stays separate |
| Plan before implementation | `/plan`, plan startup | A plan may use inference; it is not permission for edits or deployment |
| Review and research | `/review`, `/security-review`, `/research`, `/rubber-duck` | Model/tool activity and source exposure need task authority |
| Queue or steer work | Ctrl+Enter/Ctrl+Q and normal native input | Keyboard delivery may differ in browser terminals; no automatic submission loop |
| Multiple conversations | `/resume`, `/fork`, `/rename`, native session commands | Host credentials still authorize only this live terminal process |
| Skills/custom agents/plugins | Native discovery, `/agent`, `/plugin`, explicit `--plugin-dir`/`--add-dir` | Host-reviewed trusted code only; `--add-dir` also loads configuration |
| Local file context | Native `@` references after host staging | Host validates source scope before download; staging does not grant broader storage access |

## Not Silently Enabled

| Feature | Why It Is Deferred Or Excluded |
| --- | --- |
| Arbitrary startup argv, `--allow-all*`, `--yolo`, automatic approvals | Converts a terminal embedding into an unbounded execution service |
| Remote steering/export, gist/link sharing, PR creation/merge | Exports session material or mutates GitHub; requires separate caller/auth/data policy |
| ACP/SDK structured agent interface | Different transport/contract from a PTY; evaluate independently, not by parsing terminal output |
| Prompt mode JSONL, usage output files | Useful for a separate batch adapter; do not replace this one-session interactive runtime |
| Extra MCP servers, hooks, LSP, plugins, custom agents | Run or load trusted code; operator must review commands, credentials and scope before wiring |
| Native sandbox | Officially preview; platform-dependent. Configure and read back `/sandbox policy` before claiming it exists |
| HTTP localhost providers or browser API-key/header entry | Official CLI supports broader setups; this adapter deliberately keeps HTTPS and server-issued bearer credentials |
| Hard cost ceiling | Continuation count, token windows and CLI usage UI do not enforce a provider-account budget |
| Durable reconnect after host restart/Stop | Requires persisted ownership and credential renewal; only live process reconnect is implemented |
| Model completion in default tests | Needs explicit provider configuration, credentials and spending authorization |

## Provider Details

Help shipped with CLI 1.0.83 documents `COPILOT_PROVIDER_BASE_URL` as the BYOK selector,
`COPILOT_PROVIDER_TYPE` as `openai`, `azure` or `anthropic`, `COPILOT_PROVIDER_WIRE_API` as
`completions` or `responses`, and distinct `COPILOT_PROVIDER_MODEL_ID` versus
`COPILOT_PROVIDER_WIRE_MODEL`. It also documents bearer-over-API-key precedence and token-window
variables. This skill sends only the selected bearer path, avoiding credential/header precedence
ambiguity. Azure host URLs and OpenAI-compatible full routes are not interchangeable.

Local BYOK does not require GitHub model routing/login; it still requires the provider's own
authorization and can incur provider cost. The native smoke test uses a non-secret loopback target
with `COPILOT_OFFLINE=true`, issues no prompt, and never validates a live model endpoint.

Official local sandbox docs distinguish OS-enforced subprocess policies from software checks for
built-in file operations, and exclude remote MCP processes from local enforcement. Our private
workspace does not configure that sandbox. This limitation must survive any deployment handoff.