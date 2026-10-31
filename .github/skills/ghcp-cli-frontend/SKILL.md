---
name: ghcp-cli-frontend
description: "Use when embedding an interactive GitHub Copilot CLI terminal in React, building ghcp_cli_frontend, or integrating a trusted-local Python PTY with explicit provider credentials."
---

# Copilot Terminal

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
An embedded operator terminal is not part of the synthetic customer workflow. Do not expose
this trusted-local PTY through the hub WAF or borrow CLI credentials into the web app.
Bundled runtime/frontend source does not establish installed packages or Copilot access.

For an explicitly selected local integration, verify `copilot-terminal-runtime`: `copilot_terminal.TerminalService`, `ProviderConfig`,
`LaunchOptions`, `PtySession`; frontend `copilot-terminal`: `CopilotTerminal` and its public types.
Read the canonical [library guide](GUIDE.md) and
[installation and checks](README.md).

Requires Python 3.11+ on POSIX, React 19, and an operator-installed Copilot CLI for native use.
Host owns explicit configuration, private credential injection, authorization and retained state.
Trusted local operator only: no OS sandbox, public gateway or multi-user authentication supplied.
Installation grants no model access and starts no process. Native/live checks require separate authority.