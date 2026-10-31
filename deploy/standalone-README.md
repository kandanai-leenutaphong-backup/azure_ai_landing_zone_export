# Customer service multi-agent on Azure

Synthetic customer support workbench at
<https://customer-service-multi-agent.azuremew-domain.org>.

SEA private Azure Container Apps orchestrates three native service agents and
four specialized judges in private West US 3 Microsoft Foundry. Existing hub
Application Gateway WAF protects the new HTTPS hostname. Tenant-scoped Entra
tokens, delegated scope and an explicit project allowlist protect model calls.
Managed identity handles outgoing Azure access.

**Sign in with Microsoft**, not a pasted API token. A dedicated tenant-only,
secretless SPA uses official vendored MSAL and PKCE; the API independently enforces its
existing user allowlist. Completed interactive human sign-in/MFA remains unverified.
The conversational UI/API and three-role Microsoft Agent Framework hosted runtime are
implemented, but native Hosted deployment is blocked by the disconnected operator VPN.
Chat explicitly returns 503 until an active, source-verified Hosted version is configured;
it never falls back to local agents. Existing synthetic simulations remain available.

| Capability | Owner |
| --- | --- |
| API, browser, deterministic tools, correlated logs, three-tier scorecards | [`applications/customer-service-multi-agent`](applications/customer-service-multi-agent/README.md) |
| Owner-isolated conversations and native Framework host | Application `chat.py` and `hosted/`; live Hosted deployment pending private connectivity |
| Twenty LLM-generated synthetic cases and frozen annotations | [`datasets`](applications/customer-service-multi-agent/datasets/README.md) |
| Specialized judges, consensus, calibration, regression and drift | [`regression contract`](applications/customer-service-multi-agent/REGRESSION.md) |
| SEA release, DNS/TLS, hub WAF and verification | [`deploy/deploy.sh`](deploy/README.md) |
| GitHub Actions quality/deployment gates | [workflow](.github/workflows/customer-service.yml) |

Run focused checks and validate the frozen cohort:

```bash
python3 -m pytest -q applications/customer-service-multi-agent deploy
bash deploy/deploy.sh -e sea validate-dataset
```

For local development, `bash deploy/deploy.sh -e sea configure-local` creates
the app's private `.env` from deployed non-secret settings using your existing
authorized Azure CLI login. The app loads it automatically; `.env-template`
documents the variables. See the application README for local startup.

Use the deployment runbook for prerequisites and commands. No real orders or
payments are modified. UI tokens remain in tab memory. This is a **working
synthetic demonstration, not a calibrated production-quality claim**.

## CI/CD

Push/PR checks run offline tests, cohort drift/integrity checks and UI syntax.
Manual live evaluation requires a pre-provisioned private-network self-hosted
runner with labels `self-hosted, linux, azure-vnet`, the optional evaluation SDK,
the configured managed identity available to native inference, and separately
configured Azure OIDC federation for control-plane operations. Required repository/environment
variables: `AZURE_DEPLOY_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_HUB_SUBSCRIPTION_ID`. Configure GitHub `evaluation` and `production`
environments and their appropriate approval/branch protections.

No runner, Azure role grant, federation or client secret is provisioned by this
repository. GitHub-hosted runners cannot reach the private Foundry endpoint.
Live dispatch is opt-in and billable. Production release depends on evaluation,
never only on a green build.

The gold baseline is deliberately absent. Genuine 50-100 human-labeled examples
must establish each specialized judge's kappa above 0.7 before explicit baseline
promotion. Candidate gates fail closed on missing calibration, missing cases,
invalid provenance, canary failure or regression beyond 2 percentage points
completion, 0.3 goal points, 0.5 coherence points, or 5 percentage points for any
journey. Business-agent/model versions may change; frozen evaluation judges
and cohort preserve comparability.

## Known limits

- Replica-local SQLite and live UI metrics can disappear on scale-to-zero or
  restart. Content-free correlated metric snapshots persist in existing
  Log Analytics; the UI does not query historical telemetry.
- Same-model prompt variants are not independent model consensus.
  Four specialized judges run ordinarily; consensus is an explicit option.
- Synthetic follow-ups are generated context, not a full customer simulator.
  Real customer resolution/reopen rates remain unknown.
- Native SDK batch execution, calibrated gold promotion and live CI/CD remain
  blocked until the stated external prerequisites exist.
- Sampling/drift comparison utilities are present; no automatic production
  sampling or scheduled drift monitor is installed.
- TLS certificate renewal is operator-owned; rerun `route` at least monthly.
  No automatic certificate-renewal schedule is installed.

This repository is an allowlisted export of the application and its deployment
owner. It does not include unrelated landing-zone applications, credentials,
local databases, token files or private certificate material.
