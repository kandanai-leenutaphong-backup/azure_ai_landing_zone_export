# Terminal Gotchas

- G1: A VS Code shim may resolve Copilot using the original home. Pass the actual standalone
  executable and test it with a private home; the migration verified CLI 1.0.83.
- G2: `--no-custom-instructions` is not a promise that no skills/plugins are discovered. Keep
  private workspaces outside repository/home ancestry. `--add-dir` also trusts configuration.
- G3: Model alias and deployment are different. Azure provider type expects a host URL; an
  OpenAI-compatible route may need its full path. Check the provider, not a guessed resource name.
- G4: Autopilot is not `--allow-all` and not `--no-ask-user`. With limited permissions it can deny
  steps that need approval. Continuation and token-window bounds are not provider spending caps.
- G5: Native Help opens a panel. Dismiss it and wait for the CLI footer before another command.
  A startup banner is not input readiness; TUI patterns are version-sensitive.
- G6: Sending prompt and Enter in one chunk may paste a newline. Prepared actions send them
  separately; the command menu deliberately never auto-submits.
- G7: React reload reconnects to the live PTY, not a newly resumed CLI. Stop revokes the control
  key; native `/resume` cannot restore that key after the host ends the session.
- G8: A private workspace and 0400 staged file are not an OS sandbox. The same user can change
  permissions or inspect other same-user processes. Use real isolation for untrusted work.
- G9: Never log request bodies, sessionStorage keys or provider environments. The redactor handles
  split output but cannot sanitize downstream host callbacks or logs that bypass it.
- G10: Default tests do not call a model. Fixture screenshots prove transport/UI; native help proves
  CLI startup. Neither proves live provider auth, token refresh or a completed inference.