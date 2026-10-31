# Foundry Agent Evaluation, Optimization, And Observability

> Historical research only. Statements about absent runtime and refresh commands describe
> the collection date, not the canonical library now present in this directory.

**114 official references: 112 acquired and hash-checked, two retained as link-only.**
Research assembled 2026-09-15; acquisition timestamps are 2026-09-14 UTC. Documentation
only: no library implementation, dependency installation, Azure deployment, or paid run.

**Time-sensitive:** Microsoft documents a September 30, 2026 migration of sensitive GenAI
trace values into `AppGenAIContent`. Custom queries, alerts, and dashboards may need
changes. See [OBSERVABILITY.md](OBSERVABILITY.md#time-sensitive-content-migration).

## Reading Order

| File | Knowledge Collected |
| --- | --- |
| [EVALUATIONS.md](EVALUATIONS.md) | Offline/cloud/production evaluation; turn versus conversation scope; agent, RAG, safety, rubric, and custom evaluators; datasets; result handling; red teaming; CI/CD |
| [OPTIMIZATION.md](OPTIMIZATION.md) | Agent Optimizer versus Prompt Optimizer; prompt/hosted targets; native SDK/CLI integration; candidate scores; cost semantics; SFT, DPO, RFT, and Agent Lightning |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Traces, OpenTelemetry, model/agent metrics, dashboards, feedback, continuous evaluation, Agent Insights, sampling, privacy, identity, and the content-table migration |
| [API_AND_OPERATIONS.md](API_AND_OPERATIONS.md) | Current versus classic SDKs, version drift, REST entry points, example defects, permissions, quotas, regions, networking, costs, and remaining live checks |
| [SOURCES.md](SOURCES.md) | Clickable official source index, grouped by topic with acquisition and source-family labels |
| [sources.txt](sources.txt) | One URL per line for repeatable acquisition |
| [acquisitions.json](acquisitions.json) | Source receipts, retrieval timestamps, HTTP status, content hashes, discovery evidence, and access refusals |

## Main Findings

- Agent Optimizer performs scored configuration search. Prompt Optimizer rewrites text;
  neither is model-weight training. Hosted optimization can include skills and tool descriptions.
- Native optimizer SDK operations exist beyond portal/CLI workflows, but their beta types
  and polling contracts changed across recent Projects SDK versions.
- Agent evaluation must inspect outcome and process separately. Tool coverage, input shape,
  score range, score direction, and turn/conversation support differ by evaluator.
- Model availability, agent-run completion, evaluator task success, and human satisfaction
  are different measurements. Preserve raw results, denominators, missing data, and errors.
- Optimizer estimates are not spending caps. Missing token measurements are unknown, not
  zero. Evaluation and optimization can invoke external tools with real side effects.
- Tracing is documented as GA for prompt/hosted agents, with other surfaces retaining
  preview labels. Ingestion identity, log reading, and protected-content reading are separate.
- Current Agent Insights samples require 2.7.0 while the acquired changelog marks that
  version unreleased. Supporting models in 2.6.0 do not prove end-to-end availability.
- Official sources contain discrepancies: red-teaming region lists disagree, one metric's
  export flag contradicts broad how-to prose, and a dashboard Python example fails syntax parsing.

Each finding is expanded and linked to its official evidence in the topic guides.

## Evidence And Limits

Discovery used Microsoft Learn's search API and current Foundry navigation, followed by
official Microsoft SDK/source references and relevant upstream standards. No ranked search
provider was configured; the DuckDuckGo Instant Answer fallback was not treated as one.
This is a broad, bounded collection, not a claim to include every historical or future page.

The acquisition tool respected robots policies, used per-host pacing, and recorded source
provenance. All **132 cached artifacts** passed catalogue existence/hash checks. The
metadata selects one acquired representation for each of 112 source targets; duplicates,
text derivatives, and discovery documents explain the different artifact count.

Two sources remain link-only: W3C Trace Context and Microsoft's REST-reference short-link.
Their hosts refused this fetcher through robots policy; no workaround was attempted.
The legacy `azure/ai-foundry/toc.json` returned 404; the current `azure/foundry/toc.json`
was acquired. The fetcher does not expose redirect chains; none are claimed as verified.

All publisher documents and SDK source bodies remain in an internal temporary cache, not
this repository. This directory contains original synthesis, links, and metadata. Hashes
identify acquired bytes, not publisher authenticity, runtime correctness, or redistribution
rights. UTC acquisition dates, document dates, and package release dates are distinct.

No evaluation accuracy, optimization gain, package compatibility, cloud permission,
telemetry ingestion, alert delivery, or bill was measured. The only code-reference execution
was syntax parsing without imports or model calls. Examples and recommendations are labeled;
preview access and tenant-specific behavior require separately authorized verification.

This folder is the durable research record. No notebook mechanism, workspace package, or
consumer migration was added. Root project-state documentation is unchanged because this
collection adds no runtime capability.

## Refresh Sources

From the repository root, acquire into a new temporary cache:

```bash
CACHE=$(mktemp -d /tmp/agentcraft-foundry-refresh.XXXXXX)
python3 .github/skills/web-resource/scripts/fetch-page/fetch_page.py \
  --urls .github/skills/agent-optimization/sources.txt \
  --subject foundry-agent-research \
  --out "$CACHE/pages" --catalogue "$CACHE/manifest.json" --text
```

The fetch command reports refusals and can exit nonzero while retaining successful
acquisitions. Verify those acquired artifacts separately:

```bash
python3 .github/skills/web-resource/scripts/catalogue/catalogue.py \
  --catalogue "$CACHE/manifest.json" --verify
```

Most existing Learn receipts use the publisher's `?accept=text/markdown` representation;
the plain target-list command above instead fetches the ordinary pages. Use each recorded
`acquisition_url` to request the same representation when comparing hashes. Reacquisition
can still return updated content. Review new evidence before revising findings, and do not
silently overwrite old verification claims or bypass a publisher refusal.