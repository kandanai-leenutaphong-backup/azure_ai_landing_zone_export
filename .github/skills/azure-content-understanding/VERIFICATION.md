# Verification

## Portable Recipe

2026-09-16, Linux, Python 3.12.3, uv 0.9.30. Native SDK 1.1.0, Azure Core 1.41.0,
Azure Identity 1.25.2, aiohttp 3.14.3; transitive versions are in the bundled lock.
GA API `2025-11-01`, `prebuilt-layout`, explicit `processing_location=geography`.

Fourteen offline checks pass through the real SDK with a synthetic lower HTTP
transport, not a mocked `begin_analyze_binary` method:

- Native binary request/API/content type, poll completion and full envelope capture.
- Exact authorized source hash, PDF magic/byte cap, non-symlink local input.
- Permission before credentials/output; exact resource and polling-target confinement.
- Existing output refusal; native failure/empty success preserved as failure.
- Bounded async timeout retains operation ID and closes client transport.
- Unread-body fixture reproduces real async response behavior; exception summaries
  do not copy provider messages into receipts/logs.

Run:

```bash
uv run --locked --project "$SKILL_ROOT/libraries" python -m unittest discover -s "$SKILL_ROOT/tests" -v
```

## Live Native SDK

Two operator-authorized born-digital PDF reports were submitted through this exact
recipe with Azure CLI Entra identity to an existing CU resource, without new grants
or resources. Both returned complete envelopes and persisted output read back equal.

| Source | Pages | Native Tables | Markdown Bytes | Client Seconds | Reported Usage |
| --- | ---: | ---: | ---: | ---: | --- |
| Yallourn incident report | 7 | 5 | 21,579 | 8.915079 | 7 documentPagesStandard |
| Murray incident report | 6 | 3 | 14,480 | 8.789323 | 6 documentPagesStandard |

These are measured single runs, not a latency ranking or global accuracy claim.
Source PDFs and private endpoint/operation receipts stay with the host experiment;
they are not distribution inputs. Actual dollar cost is unknown.

Both native SDK outputs also passed the existing source-reviewed 32 narrative
and six native table-row probes. Murray retains the known `Bus bar` spacing
difference. Diagram topology remains unverified; phrase matches alone do not prove it.

One earlier native submission failed during response capture before its operation
ID was retained. Its remote outcome/cost remains unknown. The original receipt and
correction remain in the host record. The async-policy fix was tested before two
new deliberate submissions; no silent retry or erased failure is claimed.

## Reference Host

Separately, an Entra-protected Azure Function using native CU REST operations was
tested against the same reports. The retained native results pass 32 source-based
narrative probes and six native row-association probes. The CU-only Function release
has three bindings: extraction, status and health; retired alternative routes refuse.
Its 52 offline checks and live authorization/persisted-result checks pass.

That host's identity, deployment, storage and durable-job implementation is not
bundled or reimplemented here. Its permissions and customer inputs are not inherited
by installing a skill. The portable recipe's managed-identity option is present;
these direct-SDK live runs used Azure CLI identity, not hosted SDK execution.

## Remaining Limits

No broad PDF corpus, scanned-document accuracy benchmark, cross-region support,
diagram topology, generative analyzer, other formats, load benchmark, government
cloud, browser sign-in or exact billing measurement was run. Local persistence is
not proof of power-loss durability. Offline authorization flags are not Azure RBAC.

## Copy-Out And Discovery

The skill was copied outside the checkout without its environment/cache, installed
with its own `uv sync --locked --project libraries`, and tested through the copied
script and tests. CLI help also passed. No repository imports, PDF fixtures, cloud
configuration or live calls were required. All portable local documentation links
resolved and the copied MIT notice matched the source notice.

The native catalogue contains one `azure-content-understanding` entry; capability
count is 29. Client-specific automatic skill refresh and MCP discovery are not
claimed; this skill registers no MCP server.