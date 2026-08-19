# Thai Search Comparison

This Streamlit app compares Thai first-name, last-name, and address searches
across a local CSV, Azure SQL Database, and Azure AI Search.

## Deployed app

https://thai-search-app-eastus2.wittypond-f54803a5.eastus2.azurecontainerapps.io

The previous Sweden Central URL was retired during the East US 2 migration and
returns 404.

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

Azure SQL is hosted in `rg-vm-vnet-test`. East US 2 and East US were closed to
new SQL logical-server creation during deployment, so the database uses
Central US with an S2 service objective. Its private endpoint and the
Streamlit app are in East US 2. The SQL private DNS zone is linked to
`vnet-1`, `vnet-2`, and `vnet-hub-2`.

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
