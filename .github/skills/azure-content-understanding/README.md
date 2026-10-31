# Azure Content Understanding

Portable, native-SDK PDF layout extraction with Entra identity, explicit source
authorization and immutable result directories. [Canonical guide](GUIDE.md).

The official Microsoft client owns API serialization, token policies, polling and
native models. This recipe adds only input/target bounds, durable local evidence
and no-overwrite refusal. It is not another framework package or hosted Function.
The [skill entry](SKILL.md) is a thin
discovery pointer; implementation, tests, lock and evidence belong here.

## Setup

Offline setup requires Python 3.12, uv 0.9.30 and reviewed dependencies, not Azure
credentials. From the repository root, set `RECIPE_ROOT` as below. For a standalone
copy, set it to the absolute directory containing this README. Select a new caller-owned
`UV_PROJECT_ENVIRONMENT` outside the checkout; never reuse another worker's environment.

```bash
export RECIPE_ROOT="$PWD/.github/skills/azure-content-understanding"
export UV_PROJECT_ENVIRONMENT=/absolute/path/to/a/new/content-understanding-env
uv sync --locked --project "$RECIPE_ROOT/libraries"
uv run --locked --project "$RECIPE_ROOT/libraries" python -m unittest discover -s "$RECIPE_ROOT/tests" -v
```

The bundled [manifest](libraries/pyproject.toml) and [lock](libraries/uv.lock)
are a stand-alone uv project, not a machine-specific copy of another workspace.
Only Microsoft SDKs, their transport dependencies and Python's standard library
are needed. No editable import from another repository, dataset or testbed is used.
Setup may need a package source; tests use synthetic transports and make no Azure call.

## Local Operator

Live extraction separately requires an approved public-Azure Foundry endpoint, Entra
data-plane identity, input/processing boundary and paid-analysis budget. Nothing here
provisions resources. `prebuilt-layout` needs no language/embedding model deployment.

Set these non-secret values yourself from the approved task, not from PDF content:
`RECIPE_ROOT`, `CU_ENDPOINT`, `TENANT_ID`, `SOURCE_PDF`, `SOURCE_SHA256`, `RESULT_DIR`.
`SOURCE_SHA256` is the authorized file's lowercase SHA-256. `RESULT_DIR` must not exist.
Use your authorized Azure CLI login in the intended tenant; this recipe never
changes the shared CLI subscription or requests a credential value.

```bash
uv run --locked --project "$RECIPE_ROOT/libraries" python "$RECIPE_ROOT/scripts/extract.py" \
  --endpoint "$CU_ENDPOINT" \
  --identity cli --tenant-id "$TENANT_ID" \
  --input "$SOURCE_PDF" --input-sha256 "$SOURCE_SHA256" \
  --processing-location geography \
  --output "$RESULT_DIR" --allow-analysis
```

`--allow-analysis` records an already-made authorization decision; an agent may not
self-grant access merely by setting it. `geography` requests a processing boundary;
confirm the service's region/feature support and applicable data policy. No fallback
to `global` occurs. Choose `dataZone` or `global` explicitly only when authorized.

Azure-hosted callers use `--identity managed`, optionally `--client-id` for a
user-assigned identity, without `--tenant-id`. Prefer calling the async `extract`
function with a host-injected credential; the function does not close a borrowed
credential. The CLI owns and closes the credential it creates.

## Outputs And Failure

| File | Meaning |
| --- | --- |
| `request.json` | Source identity, approved target, versions and initial attempt metadata, written before submission |
| `operation.json` | Validated native operation ID and target, written before reading the initial response body |
| `native.json` | Complete last native operation envelope, including result/usage or failure where available |
| `sdk-result.json` | The successful native `AnalysisResult.as_dict()` serialization |
| `content.md` | Unmodified Markdown from native document content blocks, joined with two newlines |
| `receipt.json` | Success/failure/incomplete status, versions, source hash, pages, timing and output paths |

No original PDF is written into the output. Derived output still contains document
content and must be protected accordingly. Stdout prints a receipt path or bounded
failure category, not document text, tokens or SDK exception payloads.

Failures exit 2. `unconfirmed` means a request may have been accepted without a
retained operation ID; `incomplete` retains an operation but has no complete local
result. Check that operation through the native result API before authorizing a new
submission. This recipe neither retries POSTs nor resumes/cancels existing jobs.
It is not a crash-recoverable scheduler. [Detailed contract](CONTRACT.md).

## Limits And Evidence

PDF-only, 10,000,000-byte cap, 900-second maximum client deadline. New input requires
new authorization; no filesystem discovery, URL fetch, attachment traversal or
request-controlled endpoint is supported. Government/China endpoints, other formats,
custom analyzers and model-generated fields need separate work.

[Verification](VERIFICATION.md) distinguishes native SDK/live evidence from the
authenticated reference host. [Gotchas](GOTCHAS.md) records source/layout limitations
and the async capture correction. [Original documentation](references/README.md).
Recorded migration result: 12 duplicate skill paths physically removed; 14 canonical
tests passed. Those tests, setup and live extraction were not rerun for this documentation
revision. Historical host evidence does not establish current cloud liveness or grants.

Code is covered by [LICENSE](LICENSE); Microsoft and other dependencies retain
their own terms. No report PDFs or customer deployment identity are distributed.