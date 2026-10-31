# Native Layout Recipe Contract

## Owner And Dependencies

This skill owns an executable recipe, not a new public cloud client library.
`scripts/extract.py` composes the supported async Microsoft
`ContentUnderstandingClient`, `AsyncHTTPPolicy` and Azure Identity credentials.
`libraries/pyproject.toml` and `libraries/uv.lock` own its isolated environment.
No import or runtime path depends on a testbed, repository catalogue or other skill.

## Input And Authority

`extract` is an async keyword-only function. Host supplies endpoint, borrowed
credential, local source `Path`, expected SHA-256, new output `Path`, explicit
`allow_analysis`, processing location and optional timeout/transport for tests.

- Import and help do not connect, acquire credentials or submit documents.
- Without authorization, execution refuses before credential use or output creation.
- Source must be a regular non-symlink file, start with `%PDF-`, match the declared
  lowercase SHA-256 and fit 10,000,000 bytes. No OCR/readability guarantee follows
  from magic bytes; the service can still refuse a malformed/encrypted document.
- Endpoint is HTTPS on `<resource>.services.ai.azure.com`, without path, query,
  user information, fragment or custom port. Public Azure only. Trusting/configuring
  that endpoint and data boundary is the host's decision, not the PDF's.
- API `2025-11-01` and analyzer `prebuilt-layout` are fixed. Operation-Location must
  stay on the exact configured resource and native result path/version.
- Processing location is one of `geography`, `dataZone`, `global`; CLI requires it.
  Service/regional support is not inferred, and no fallback broadens it.
- The source hash binds submitted bytes. This is not user authentication or Azure
  RBAC. Incoming caller authorization and document rights remain host-owned.

## Native Execution

Binary bytes go to `begin_analyze_binary` with `application/pdf`. SDK poller owns
long-running completion. Azure Core retry count is zero to avoid automatic POST
replay. Connection/read timeouts are 15/90 seconds; the whole async operation has
an explicit positive deadline no greater than 900 seconds. Deadline cancellation
stops local waiting and closes the owned client, not the remote Azure job.

A small async pipeline policy validates/persists the operation ID, awaits each
response body, and retains the native JSON. It does not alter response data,
implement HTTP authentication or replace SDK polling/serialization.

## Result And Integrity

The function returns the receipt dictionary on successful extraction. Success
requires a completed native envelope, matching analyzer/API, nonempty document
blocks, nonempty Markdown and observed positive integer page numbers. Each result
retains all native contents; no truncation-to-fit or pair filtering occurs.

Output directory creation is exclusive; existing paths/symlinks are refused.
All written files have fixed names and use exclusive creation. The result envelope
is read back and compared, and output presence is checked. Prior directories and
source bytes are never overwritten. This is ordinary local persistence, not a
power-loss durability or transactional-filesystem guarantee.

`native.json` preserves the service envelope. `sdk-result.json` preserves the SDK
model serialization. `content.md` preserves returned Markdown; concatenating
multiple native document blocks inserts exactly two newlines. Tables, figures,
spans and usage remain native facts, not normalized into an invented schema.

## Errors And Recovery

Local refusal raises `Refusal` before remote effects when possible. Once submission
begins, failures raise `ExtractionFailed` after retaining a bounded receipt and
available native evidence. Error summaries contain exception type, not arbitrary
SDK messages. Native artifacts can contain service failure details or document
content; they are private operator evidence, not safe log output.

- `failed`: rejected operation or unusable returned result, not a claim of no bill.
- `incomplete`: accepted/known operation or transport timeout with retained ID.
- `unconfirmed`: submission outcome cannot be established and no ID was retained.

No automatic retry, cancellation, resume, source-upload endpoint, role grant or
resource lifecycle is provided. Preserve the output directory and use the native
result API with the recorded operation before making any new submission decision.

## Non-Claims

No universal accuracy, complete diagram interpretation, calibrated confidence,
cost ceiling, durable background queue, caller auth, hosted deployment or MCP
service is supplied. A host may use the recipe behind independently verified
authentication/authorization and durable storage; those are separate contracts.