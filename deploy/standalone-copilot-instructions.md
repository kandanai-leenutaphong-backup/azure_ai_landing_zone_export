# Customer service multi-agent

Application owner: `applications/customer-service-multi-agent/`.
Deployment owner: `deploy/deploy.sh`; read `deploy/README.md` before cloud work.
Evaluation owner: the application's `evaluation.py`, `evaluate_cli.py` and
`regression.py`; read `REGRESSION.md` before changing scores or gates.
Dataset owner: `datasets/manifest.json` and frozen JSONL. Never overwrite gold
or manufacture human labels. Read the root README for verified scope and limits.

Use the existing private SEA Container Apps environment, hub WAF and private
West US 3 Foundry project. Do not provision another landing zone or move
inference to another region/SKU. Cloud writes, inference, identity grants and
teardown each need appropriate explicit scope. No secret retrieval, credentials
in source, authentication bypass or broad role grants.

Reuse the native Foundry agent/evaluation clients and existing application
service. APIs and browser call the same authoritative workflow. Real orders,
payments and customer data are outside this synthetic demo.

Browser authentication uses the dedicated tenant-only secretless SPA, vendored MSAL
and PKCE. Managed identity authenticates outbound CApp calls, never incoming humans.
Only the approved browser registration/preauthorization is in scope; preserve the
existing API contract, CLI client and user allowlist. Chat source uses Microsoft Agent
Framework in a native source-deployed Hosted Agent, not a prompt-agent fallback.
Missing private connectivity or active version pins blocks chat; do not invent pins,
enable public Foundry access or grant roles to hide a prerequisite failure.

Preserve all required structured telemetry fields and privacy allowlists.
Scorecards drill from system to journey to per-agent metrics. Business outcomes
remain unknown without real feedback. Replica-local SQLite is not durable
production persistence. Four specialized judge scores are provisional until
genuine human calibration establishes agreement.

Use `uv` with an existing Python interpreter for declared packages. Do not
create or activate environments, install unrelated tooling or use bare pip.
Keep edits surgical, preserve unrelated changes, and run the smallest covering
checks. Cloud configuration requires exact readback. A green offline test is not
a native batch, production deployment or calibrated gold-baseline pass.
