# Thai Search Comparison

This Streamlit app compares Thai first-name, last-name, and address searches
across a local CSV, Azure SQL Database, and Azure AI Search.

## Deployed app

The current landing-zone deployment runs `thai-surname-search` in
`rg-ai-dev-sea` on the internal `capps-env-sea` environment. Its existing public
Application Gateway/WAF DNS entry is:

http://thai-search-sea-ozewfizfnaft4.southeastasia.cloudapp.azure.com

The gateway must be running for the public DNS entry to serve the app. It was
verified Running on 2026-10-15; the agent changes did not start or stop it.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 generate_data.py
streamlit run app.py
```

Copy `.env.example` to `.env` and provide the Azure connection values before
using the Azure-backed sections. Azure SQL uses Microsoft Entra-only
authentication through the identity signed in with `az login`.

The subscription governance policy disables Azure SQL public endpoints. The
deployed Container App therefore connects to SQL through a private endpoint.

The SEA landing-zone deployment uses
`sql-thai-search-sea-ozewfizfnaft4.database.windows.net` and
`search-foundry-seaozewfizfnaft4.search.windows.net` through private networking.

## Azure SQL vs Azure Database for PostgreSQL: why both

The app showcases two managed relational databases side by side so the
tradeoffs are visible in one place, not as a recommendation to run both for
this workload in production:

| | Azure SQL Database | Azure Database for PostgreSQL |
| --- | --- | --- |
| Engine | Microsoft SQL Server, T-SQL | Open-source PostgreSQL, standard SQL + extensions |
| Why it's here | Native `EDIT_DISTANCE_SIMILARITY` and Thai collations (`Thai_100_CI_AI`) give in-database fuzzy ranking with no extension | `pg_trgm` trigram similarity is the open-source equivalent; no Thai-specific collation, so scores are coarser |
| Licensing/cost model | DTU-based (Basic/Standard/Premium) or vCore; per-database or pooled | vCore-based only (Burstable/General Purpose/Memory Optimized) |
| Ecosystem fit | Best when the rest of the stack is Microsoft (SSIS, Fabric, Synapse, Power BI native connectors) | Best when the rest of the stack is open-source/cloud-portable (avoids SQL Server licensing, easy to self-host or move to another cloud) |
| Extensibility | T-SQL, CLR, limited extension model | Rich extension ecosystem (`pg_trgm`, `postgis`, `pgvector`, JSON/JSONB, custom types) |
| This app's usage | Tabs 2, 3, 5 (standalone DB, tokenized DB, elastic-pool demo DB) | Tab 6 (fuzzy search via `pg_trgm`) |

Both connect over Microsoft Entra-only authentication (no SQL/Postgres
passwords are ever created) and both sit behind private endpoints in
`snet-pe`, so neither is reachable from the public internet.

## Elastic pool showcase (and its real cost)

`thai-search-pool-sea` is a **Basic elastic pool (50 eDTU)** hosting a second
demo database, `thai-search-pool-demo-db` (tab 5), alongside the standalone
`thai-search-db` (tab 2) on the same logical server. It demonstrates sharing
compute/storage budget across multiple databases that each have unpredictable,
non-overlapping usage spikes — a single pool absorbs bursts from many small
databases more cheaply than giving each one its own peak-sized SKU.

**Honest cost tradeoff:** 50 eDTU is the lowest Basic pool floor Azure offers,
at roughly **$75-80/month** (East/Southeast Asia retail pricing, subject to
change). Two standalone Basic (5 DTU) databases, like `thai-search-db` and a
hypothetical second one, cost roughly **$4.90/month each (~$9.80/month total)**.
For exactly two small, low-traffic demo databases, a pool is **not** the
cheapest option — it is included here purely to showcase the elastic pool
capability itself, as asked. Elastic pools pay off once you have many (eight
or more, by common rule of thumb) small databases whose individual peak-SKU
cost would exceed the pool floor.

## Uploading data (Option 7)

Tab 7 lets you add rows directly from the running app, to any combination of:

- Azure SQL (`thai-search-db`)
- The SQL elastic-pool demo database (`thai-search-pool-demo-db`)
- Azure Database for PostgreSQL (`thai-search-pg-db`)

Use the single-record form or upload a CSV with
`first_name, last_name, street, district, province, postal_code, address`
columns (`first_name`, `last_name`, and `address` are required). New rows get
freshly assigned ids and are appended; existing rows are never overwritten.

## Provisioning and mock data (operator steps)

The SQL and PostgreSQL servers both have public network access disabled, so
these steps must run from inside the VNet (VPN/P2S, a jumpbox, or a
Container Apps Job in the same environment) — not from an unconnected machine:

1. **Bootstrap database permissions** for the `uami-container-apps` managed
   identity (one-time per database):
   ```bash
   python3 scripts/bootstrap-thai-sql.py \
     --server sql-thai-search-sea-<suffix>.database.windows.net \
     --database thai-search-db \
     --identity-name uami-container-apps \
     --identity-client-id <uami-container-apps clientId>

   python3 scripts/bootstrap-thai-sql.py \
     --server sql-thai-search-sea-<suffix>.database.windows.net \
     --database thai-search-pool-demo-db \
     --identity-name uami-container-apps \
     --identity-client-id <uami-container-apps clientId>

   az postgres flexible-server parameter set \
     --resource-group rg-ai-dev-sea \
     --server-name pg-thai-search-sea-<suffix> \
     --name azure.extensions --value PG_TRGM

   python3 scripts/bootstrap-thai-postgres.py \
     --server pg-thai-search-sea-<suffix>.postgres.database.azure.com \
     --database thai-search-pg-db \
     --admin-login <Entra admin UPN> \
     --identity-name uami-container-apps \
     --identity-principal-id <uami-container-apps principalId>
   ```
   `scripts/deploy-apps.sh` runs all of the above automatically when the
   Postgres server and pool database exist.

2. **Load mock data.** The container image's startup command already runs
   `python azure_setup.py --target all`, which loads the same
   `thai_people.csv` dataset into `thai-search-db` (with tokenization),
   `thai-search-pool-demo-db` (plain table, for the pool showcase),
   `thai-search-pg-db` (with `pg_trgm` trigram indexes), and Azure AI Search.
   Loads are idempotent (a dataset hash/row-count check skips reloading
   unchanged data). To (re)run it manually against one target:
   ```bash
   python3 azure_setup.py --target sql-pool
   python3 azure_setup.py --target postgres
   python3 azure_setup.py --target verify
   ```

## Option 6: Matched regional Foundry comparisons

Only two comparison choices are shown:

| Mode | West US 3 | SEA | Availability checked 2026-10-15 |
| --- | --- | --- | --- |
| **Global Standard: West US 3 vs SEA** (default) | `sku-global-latency-agent:1`, `gpt-4.1-mini-global` | `regional-latency-agent:1`, `gpt-4.1-mini` | Working; both GlobalStandard |
| **Standard: SEA vs West US 3** | `regional-latency-agent:1`, `gpt-4.1-mini` | No Standard chat deployment | Blocked, explicitly disabled |

Both Global deployments use `gpt-4.1-mini` version `2025-04-14`, capacity 10,
the same instructions, temperature `0`, output limit and document bytes.
The West agents share a store; SEA holds the same document in a separate store.
The app reads actual pinned agent definitions and model-deployment metadata
before allowing calls, comparing SKU, base model/version/publisher, capacity,
settings, tools and corpus hash. Checks are cached for up to five minutes.
Labels alone cannot turn a mismatched deployment into a valid comparison.

SEA's account and regional model catalogs offer **Standard only for
text-embedding-3-large**, not a Standard chat model. The app does not silently
substitute Global Standard, an embedding model, or a different region.
`AZURE_SEA_STANDARD_AGENT_NAME` and `_VERSION` remain unset. If future service
availability changes, explicitly deploy a matching Standard chat model and
new agent before configuring this target; live metadata validation still applies.
The provisioning script deliberately exposes only the three supported targets.

The former mixed-SKU regional mode and same-West/different-SKU mode are no longer
offered. Existing models, agents, files and vector stores are retained.
[`foundry_agent.py`](foundry_agent.py) uses **new versioned Foundry agents** with
Conversations and streaming Responses, never Classic Assistants polling.
The private projects are:

- West: `foundry-agent-wus3jbm3vfsrmekbg` / `agent-project`.
- SEA: `foundry-agent-vnet-seaxlpu` / `agent-vnet-projectxlpu`.

**Compare both regions (fresh conversations)** sends the same prompt sequentially
to both agents, with fresh conversations and alternating starting order. It
incurs two calls. Model-only is default (`tool_choice=none`); unexpected search
execution rejects the result. **Include file search** enables the full agent
workload. Actual tool/cache/input/output-token counts are captured because
identical configuration does not guarantee identical execution or output length.
Use an initial **Warm-up pair**, then repeat measured pairs. Medians include
complete non-warm-up pairs only, grouped by mode/workload/region/SKU.
Single chats, partial failures and warm-ups remain exported but do not enter
medians or the diagram's last measured pair. Histories are isolated by mode,
target, workload and browser session.

### Visual data flow and additive timings

The in-app themed diagram, implemented in [`agent_visuals.py`](agent_visuals.py),
shows browser -> hub Application Gateway/WAF -> SEA Container App, branching to:

- SEA Foundry through the same VNet's private endpoint.
- West US 3 Foundry through **direct global VNet peering**, not hub/Firewall transit.

It shows endpoint API/first-text/full-app timings from the last complete
non-warm-up pair for the current mode/workload, plus optional separate TCP
probe medians. Browser/Gateway/rendering and service-internal model/tool hops
are explicitly unmeasured. Global Standard's actual inference region is
**not exposed**; endpoint region is not inference location. Standard follows
its Azure geography processing policy, not a strict physical-region guarantee.
The unavailable SEA Standard path has no invented timings.
An editable `.excalidraw` download preserves the diagram source.

Primary **Responses API time / first text** exclude client/conversation setup,
but include authentication, transport, queueing, model/tools and streaming.
Full **SEA app response time / time to first token** include setup.
The visible additive timeline is:

```text
setup + API wait until first text + API remaining stream + local processing = app total
```

If first text is unavailable, the API interval remains unsplit.
**Foundry server reference (overlapping)** uses coarse one-second server
timestamps. It is neither an extra stage nor pure inference; never subtract it
from app time to claim network latency.
**Measure connection latency** measures five fresh TCP connections, separately
from DNS, without a model call. It excludes TLS, authentication and service work.
CSV exports timings, pair metadata, model/SKU, token/cache/tool counts and
Responses request/stream-body byte counters, but no prompt/reply content.
Resetting a conversation does not delete agents or measurements.

### Approximate data-transfer cost

The UI includes an explicit request/response KiB and monthly-calls calculator.
Rates are USD public retail checked **2026-10-15**, decimal GB:

| App-to-Foundry endpoint | Global peering across both ends | Destination Private Link processing | Approximate variable total |
| --- | --- | --- | --- |
| SEA, same VNet | $0 | $0.01/GB | $0.01/GB |
| West US 3 | SEA $0.09 + West $0.035 = $0.125/GB | $0.01/GB | $0.135/GB |

Apply each rate once to **request bytes + response bytes**. For 1 GB requests
plus 1 GB responses, West is approximately **$0.27**, SEA **$0.02**. Do not add
generic inter-region bandwidth on top of the same peering transfer.
Standard-mode estimates remain hypothetical while its SEA agent is unavailable.

Observed Responses HTTP-body sizes include SSE framing but omit HTTP headers,
TLS/TCP, auth/conversation calls and service-internal traffic. The displayed
body-only cost is a partial baseline, **not Azure billed-byte telemetry**.
Token counts are not used to infer app network bytes. Monthly scenarios use
explicit assumed volumes and stay within the first 1 PB/direction pricing tier.
Existing Standard Private Endpoints are $0.01/hour each, approximately
$7.30/730-hour month, and are shared across model deployments. No new endpoint
is added for a SKU. Estimates exclude endpoint hours, model tokens/tools,
Search/Blob/Cosmos, compute, Gateway/WAF, protocol overhead and common
browser/hub-path traffic. Hidden Global inference routing is not invented as
billable customer VNet peering.

Sources: [Azure Retail Prices API](https://prices.azure.com/api/retail/prices),
[VNet peering pricing](https://azure.microsoft.com/en-us/pricing/details/virtual-network/),
[Private Link pricing](https://azure.microsoft.com/en-us/pricing/details/private-link/).
Rates/discounts and actual invoices can differ.

Configure the supported targets with `AZURE_AGENT_*` (West Standard),
`AZURE_GLOBAL_AGENT_*` (West GlobalStandard) and `AZURE_SEA_AGENT_*`
(SEA GlobalStandard), as in `.env.example`. The existing managed identity has
project-scoped **Foundry User** on both projects. No keys/secrets are added.
The app never creates/deletes agents, files or stores. Prompts are limited to
4000 characters and output to 1000 tokens; reads and stream elapsed checks use
a 90-second limit. Closing a failed/timed-out stream does not claim server-side
cancellation. Failures are logged and surfaced, not successful measurements.

Try: **What is the West US 3 readiness code in the document?**

The `regionalAgent*`, `seaAgent*`, and `thaiSurnameAppImageTag` main Bicep parameters
persist the configuration without changing other apps' images. The
`globalAgentName` and `globalAgentVersion` parameters add the Global Standard
agent at the existing `regionalAgentProjectEndpoint`. The regional
spoke accepts `callerPrincipalId` for project-scoped RBAC. For an existing project,
apply the same assignment without redeploying its capability host:

```bash
az deployment group create \
  --subscription 6bacd437-5d04-4afd-850e-51bdc4041496 \
  --resource-group rg-ai-dev-wus3 \
  --name sea-containerapp-agent-invoker \
  --template-file bicep/modules/foundry-agent-invoker-access.bicep \
  --parameters accountName=foundry-agent-wus3jbm3vfsrmekbg \
               projectName=agent-project \
               principalId=66173777-740f-49b0-a5c0-6080f29367b3
```

For SEA, use the workload subscription/resource group, account
`foundry-agent-vnet-seaxlpu`, and project `agent-vnet-projectxlpu` instead.
Its added mini deployment is reproducible with:

```bash
az deployment group create \
  --subscription d88c020a-2180-43da-91a2-f6cc01f25946 \
  --resource-group rg-ai-dev-sea \
  --template-file bicep/modules/cognitive-deployment.bicep \
  --parameters accountName=foundry-agent-vnet-seaxlpu \
               deploymentName=gpt-4.1-mini modelName=gpt-4.1-mini \
               modelVersion=2025-04-14 skuName=GlobalStandard capacity=10
```

After installing requirements and configuring the environment, the explicit
provisioning script creates the agents and their independent file-search
resources. It reuses an existing matching configured version and rejects a
different definition rather than overwriting it. It never deletes resources:

```bash
python3 applications/thai-surname-search/provision_agents.py --region westus3
python3 applications/thai-surname-search/provision_agents.py --region sea
```

To reproduce the West Global target used by the matched regional comparison, verify that West US 3 has
available GlobalStandard quota/capacity for the matching model version. Deploy
only the additional model, not the whole landing zone:

```bash
az deployment group create \
  --subscription 6bacd437-5d04-4afd-850e-51bdc4041496 \
  --resource-group rg-ai-dev-wus3 \
  --name agent-sku-comparison \
  --template-file bicep/agent-sku-comparison.bicep \
  --parameters accountName=foundry-agent-wus3jbm3vfsrmekbg capacity=10

python3 applications/thai-surname-search/provision_agents.py --target westus3_global
```

The model template copies the existing Standard model/version, content policy,
and upgrade policy. Match the Standard capacity explicitly; equal quota is not
reserved compute or guaranteed equal load. The provisioning script retains all
existing agents/files/stores and refuses to reuse a Global Standard agent whose
definition differs, including a different knowledge-store reference.

See Microsoft's [new-agent migration guide](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate)
for the Conversations/Responses API.

From the repository root, run the targeted unit tests with:

```bash
python3 -m unittest discover -s applications/thai-surname-search -p 'test_*agent*.py' -v
```

## Search behavior

- CSV: local prefix filtering and RapidFuzz fuzzy ranking.
- Azure SQL: native `LIKE 'prefix%'`; fuzzy ranking uses
  `EDIT_DISTANCE_SIMILARITY` directly on the original name and address columns.
- Azure SQL with Custom Thai Tokenization: PyThaiNLP `newmm` tokens are stored
  in an indexed child table. SQL performs token-prefix matching and native
  `EDIT_DISTANCE_SIMILARITY` ranking against a distinct, length-indexed token
  vocabulary. The app caches Azure credentials and enables TDS connection
  pooling to reduce per-query setup time.
- Azure AI Search: native Lucene prefix (`*`), fuzzy (`~1`), and Smart
  tiered search. Smart mode ranks exact names first, then Thai-analyzed
  matches, edge-ngram name prefixes, and fuzzy fallback results.

The 10,000-row dataset contains unique name pairs and addresses with separate
street, district, province, and postal-code fields for field-aware ranking.

## Code map by UI option

The four UI sections are registered in
[`main()`](app.py#L331-L373). Each section passes its search function to the
shared [`render_search_section()`](app.py#L310-L328) UI helper.

### Option 1: Local CSV

This option reads `thai_people.csv` into a cached Pandas DataFrame. It does not
query either Azure service.

| Mode | Implementation | What it does |
| --- | --- | --- |
| Prefix | [`prefix_filter()`](app.py#L68-L77) | Applies `startswith(query)` to `first_name`, `last_name`, and `address`. |
| Fuzzy | [`fuzzy_filter()`](app.py#L55-L65) | Combines the three fields and ranks every row with RapidFuzz `WRatio`. |
| CSV loading | [`load_csv()`](app.py#L79-L82) | Loads and caches the local CSV file. |

The Option 1 UI wiring is in [app.py](app.py#L338-L347).

### Option 2: Azure SQL Database

Both modes enter [`search_sql()`](app.py#L99-L115).

| Mode | Query location | What runs |
| --- | --- | --- |
| Prefix | [Inline SQL](app.py#L102-L110) | SQL executes `LIKE query%` against the beginning of the three original columns. |
| Fuzzy | [Table read and RapidFuzz call](app.py#L112-L115) | SQL returns all people, then Python calls `fuzzy_filter()`. This mode does not perform fuzzy scoring inside SQL. |

The Option 2 UI wiring is in [app.py](app.py#L349-L355).

### Option 3: Azure SQL with Thai tokenization

This option enters [`search_sql_tokenized()`](app.py#L118-L166). The search
query is tokenized first by [`tokenize_thai()`](thai_tokenization.py#L8-L18),
which uses PyThaiNLP `newmm`.

| Mode | Query location | What runs |
| --- | --- | --- |
| Prefix | [Token-prefix SQL](app.py#L135-L159) | Uses a correlated `EXISTS` lookup where `t.person_id = p.id` and `t.token LIKE query_token%`. One condition is generated for every query token. |
| Fuzzy | [`NATIVE_TOKEN_FUZZY_QUERY`](sql_search.py#L1-L62) | Uses SQL `EDIT_DISTANCE_SIMILARITY`, maps matching tokens back to people, requires every query token to match, averages token scores, and returns the top 20. |

The supporting SQL schema is created by [`load_sql()`](azure_setup.py#L67-L288):

- [`thai_people_tokens` table](azure_setup.py#L101-L114)
- [`IX_thai_people_tokens_lookup` index](azure_setup.py#L110-L112)
- [Token generation and insertion](azure_setup.py#L200-L234)

The Option 3 UI wiring is in [app.py](app.py#L357-L363).

### Option 4: Azure AI Search

This option enters [`search_ai()`](app.py#L173-L202). The actual Azure SDK
request is the [`client.search()` call](app.py#L188-L199).

| Mode | Query construction | What runs |
| --- | --- | --- |
| Prefix | [Prefix construction](app.py#L184-L186) | Adds `*` to each query term and sends a full Lucene query. |
| Fuzzy | [Fuzzy construction](app.py#L181-L183) | Adds `~1` to each term and sends a full Lucene query. |
| Smart (tiered) | [`smart_search_ai()`](app.py#L218-L306) | Runs exact-name, Thai-analyzed, name-prefix, and fuzzy-fallback searches in descending priority. |

The Azure AI Search index is defined in
[`load_search()`](azure_setup.py#L292-L430). Its searchable Thai fields use the
`th.lucene` analyzer, beginning with
[`first_name`](azure_setup.py#L299-L306). The Option 4 UI wiring is in
[app.py](app.py#L365-L373).

## Query flow summary

```text
Option 1  CSV -> Pandas -> prefix_filter / RapidFuzz
Option 2  Azure SQL thai_people -> SQL LIKE / Python RapidFuzz
Option 3  query -> PyThaiNLP -> thai_people_tokens -> SQL prefix/edit distance
Option 4  query -> Azure AI Search -> th.lucene/Lucene -> ranked documents
```
