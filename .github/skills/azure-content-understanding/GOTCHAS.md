# Content Understanding Gotchas

## Analyzer Choice Is A Capability Choice

`prebuilt-layout` extracts native structure without language/embedding deployments.
`prebuilt-documentSearch`, generated fields and multimodal analysis have different
requirements. Do not create model capacity just because a generic quickstart does.
Pin the analyzer and GA API, verify the actual response, and test expanded scope.

## Async Response Capture

Azure Core's `raw_response_hook` is synchronous. Calling `.json()` on an unread
async SDK response can raise `ResponseNotReadError` after submission, before a
poller reaches the caller. An `async def` hook alone is not a fix: that hook is not
awaited by `CustomHookPolicy`.

The tested recipe uses an `AsyncHTTPPolicy`, saves the validated operation ID first,
then awaits `.read()` before JSON access. Tests reproduce unread-body refusal on
the actual SDK transport boundary. This protects native evidence without replacing
Microsoft's SDK. Never classify a capture exception as proof nothing was submitted.

## Preserve Native Structure

Markdown may contain HTML tables or image references. Keep native rows, cells,
`rowSpan`, word/page coordinates and content offsets beside the Markdown. One
logical row can span several physical rows. Stripping tags before storing evidence
or counting table strings is not a faithful structure comparison.

The Python SDK requests `codePoint` indexing. Use the response's declared string
encoding for spans; do not mix it with UTF-16 browser offsets or byte offsets.

## Diagram Labels Are Not Topology

In the report experiment, `Busbar 5B2` became `Bus bar 5B2`; a strict phrase probe
reported a miss even though the label remained. A compact device identifier was
also tokenized with an extra space. Neither occurrence establishes a missing
electrical branch, but both matter for exact identifier consumers. Preserve page
images/native locations and adjudicate against the source before forming an answer key.

## Timeout Is Not Rollback

POST has no automatic replay in this recipe. The SDK may have submitted a billable
job before a local timeout or capture failure. Keep `operation.json` when present;
otherwise retain an unknown outcome. A fresh invocation is a new analysis, not an
idempotent retry. A client deadline and lack of local output do not imply cancellation.

## Identity, Location And Cost

Local operator OAuth, Function incoming caller identity and Function workload
managed identity are different authorities. A successful native SDK call does not
prove an HTTP host authenticates callers. Never trade keys/anonymous access for a
passing test. Resource-scoped access and approved processing geography belong to
the host's target configuration. Report usage where returned; unknown price stays
unknown. Document analysis and retained hosting/network/storage can incur charges.