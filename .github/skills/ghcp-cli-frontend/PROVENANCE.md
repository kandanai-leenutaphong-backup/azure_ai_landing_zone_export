# Provenance

This package owns the React terminal adapter and Python PTY service distributed here. It does not
bundle the GitHub Copilot CLI executable, require a private source repository or select a cloud
host. The operator installs and authenticates the CLI separately under its applicable terms.

The npm/Python/React APIs, PTY process lifecycle, private environment, split-secret redactor,
source staging, prepared host callbacks and session transport have library-boundary coverage and
a standalone browser fixture. No customer credentials, corpus or generated UI output is included.

Enrichment is grounded in official GitHub docs and help shipped with Copilot CLI 1.0.83:
host-owned launch modes, bounded continuations, reasoning/session/accessibility options, typed BYOK
settings, remote-export disabling and native command insertion. Sources and feature decisions are
in [references/official-cli-features.md](references/official-cli-features.md).

`ghcp_cli_frontend` is the requested catalogue alias; `ghcp-cli-frontend` is the portable skill
identifier required by Agent Skills naming. Existing package identifiers remain to avoid breaking
consumer imports. All third-party runtime dependencies remain package-manager dependencies.