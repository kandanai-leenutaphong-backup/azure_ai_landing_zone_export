from __future__ import annotations

import json
import logging
import os
import socket
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import psycopg
import pytds
import streamlit as st
import streamlit.components.v1 as components
import certifi
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from foundry_agent import (
    COMPARISON_LABELS,
    COMPARISON_SKUS,
    COMPARISON_TARGETS,
    SEA_STANDARD_UNAVAILABLE,
    AgentSettings,
    AgentTimings,
    invoke_agent,
    measure_agent_connection,
    verify_regional_agents,
)
from agent_visuals import (
    PRICING_CHECKED, PRICING_SOURCE, estimate_transfer, flow_excalidraw, flow_html, timeline_html,
)
from rapidfuzz import fuzz, process
from sql_search import BASELINE_SQL_FUZZY_QUERY, NATIVE_TOKEN_FUZZY_QUERY
from postgres_search import (
    POSTGRES_BROWSE_QUERY,
    POSTGRES_CREATE_TABLE,
    POSTGRES_CREATE_TRGM_INDEXES,
    POSTGRES_FUZZY_QUERY,
    POSTGRES_PREFIX_QUERY,
)
from thai_tokenization import tokenize_thai


load_dotenv()
CSV_PATH = Path(__file__).with_name("thai_people.csv")
SEARCH_COLUMNS = ["first_name", "last_name", "address"]
AI_SEARCH_COLUMNS = [
    "first_name",
    "last_name",
    "street",
    "district",
    "province",
    "postal_code",
    "address",
]
AI_FUZZY_COLUMNS = [
    "first_name_exact",
    "last_name_exact",
    *AI_SEARCH_COLUMNS,
]
AI_SELECT_COLUMNS = ["id", *AI_SEARCH_COLUMNS]
LOGGER = logging.getLogger(__name__)


def clean_code(value: str) -> str:
    return textwrap.dedent(value).strip()


def csv_logic(query: str, mode: str) -> list[tuple[str, str, str]]:
    if mode == "Prefix":
        code = """
        query = query.casefold()
        mask = pd.Series(False, index=data.index)
        for column in ["first_name", "last_name", "address"]:
            mask |= (
                data[column]
                .fillna("")
                .astype(str)
                .str.casefold()
                .str.startswith(query)
            )
        results = data[mask].head(20)
        """
    else:
        code = """
        combined = data[
            ["first_name", "last_name", "address"]
        ].fillna("").astype(str).agg(" ".join, axis=1)

        matches = process.extract(
            query,
            combined.to_dict(),
            scorer=fuzz.WRatio,
            limit=20,
        )
        """
    return [
        ("Python executed locally", "python", clean_code(code)),
        ("Current input", "text", query or "<empty query>"),
    ]


def baseline_sql_logic(query: str, mode: str) -> list[tuple[str, str, str]]:
    if mode == "Prefix":
        sql = """
        SELECT TOP 20 id, first_name, last_name, address
        FROM dbo.thai_people
        WHERE first_name LIKE %s
           OR last_name LIKE %s
           OR address LIKE %s
        ORDER BY id
        """
        parameters = [f"{query}%"] * 3 if query else ["<empty>"] * 3
        return [
            ("SQL sent to Azure SQL", "sql", clean_code(sql)),
            (
                "Bound parameters",
                "json",
                json.dumps(parameters, ensure_ascii=False, indent=2),
            ),
        ]

    return [
        (
            "Native fuzzy SQL sent to Azure SQL",
            "sql",
            clean_code(BASELINE_SQL_FUZZY_QUERY),
        ),
        (
            "Bound parameters",
            "json",
            json.dumps([query, query, query], ensure_ascii=False, indent=2),
        ),
        (
            "Important",
            "text",
            "This scans the original columns directly and does not use "
            "dbo.thai_people_tokens or dbo.thai_token_vocabulary.",
        ),
    ]


def pool_sql_logic(query: str, mode: str) -> list[tuple[str, str, str]]:
    entries = baseline_sql_logic(query, mode)
    return [
        (
            "Elastic pool",
            "text",
            "Runs against thai-search-pool-demo-db, a database hosted in the "
            "thai-search-pool-sea Basic elastic pool (50 eDTU shared across "
            "pooled databases) instead of its own standalone compute/DTU "
            "allocation.",
        ),
        *entries,
    ]


def postgres_logic(query: str, mode: str) -> list[tuple[str, str, str]]:
    if mode == "Prefix":
        parameters = [f"{query}%"] * 3 if query else ["<empty>"] * 3
        return [
            ("SQL sent to PostgreSQL", "sql", clean_code(POSTGRES_PREFIX_QUERY)),
            (
                "Bound parameters",
                "json",
                json.dumps(parameters, ensure_ascii=False, indent=2),
            ),
        ]

    return [
        (
            "SQL sent to PostgreSQL",
            "sql",
            clean_code(POSTGRES_FUZZY_QUERY),
        ),
        (
            "Bound parameters",
            "json",
            json.dumps([query] * 6, ensure_ascii=False, indent=2),
        ),
        (
            "Important",
            "text",
            "Uses the pg_trgm extension's trigram similarity() function and "
            "the %% (similar-to) operator. Scores are 0-1, not the 0-100 "
            "scale used by the Azure SQL EDIT_DISTANCE_SIMILARITY tabs, and "
            "pg_trgm has no Thai-specific collation awareness.",
        ),
    ]


def tokenized_sql_logic(query: str, mode: str) -> list[tuple[str, str, str]]:
    tokens = tokenize_thai(query)
    token_json = json.dumps(tokens, ensure_ascii=False, indent=2)
    if mode == "Prefix":
        conditions = " AND ".join(
            """
            EXISTS (
                SELECT 1
                FROM dbo.thai_people_tokens t
                WHERE t.person_id = p.id
                  AND t.token LIKE %s
            )
            """.strip()
            for _ in tokens
        ) or "-- No token condition for an empty query"
        sql = f"""
        SELECT TOP 20 p.id, p.first_name, p.last_name, p.address
        FROM dbo.thai_people p
        WHERE {conditions}
        ORDER BY p.id
        """
        parameters = [f"{token}%" for token in tokens]
        return [
            ("PyThaiNLP newmm query tokens", "json", token_json),
            ("SQL sent to Azure SQL", "sql", clean_code(sql)),
            (
                "Bound parameters",
                "json",
                json.dumps(parameters, ensure_ascii=False, indent=2),
            ),
        ]

    payload = json.dumps(
        [{"token": token} for token in sorted(set(tokens))],
        ensure_ascii=False,
        indent=2,
    )
    return [
        ("PyThaiNLP newmm query tokens", "json", token_json),
        ("JSON passed to OPENJSON", "json", payload),
        (
            "Native Azure SQL fuzzy query",
            "sql",
            clean_code(NATIVE_TOKEN_FUZZY_QUERY),
        ),
    ]


def ai_search_logic(query: str, mode: str) -> list[tuple[str, str, str]]:
    if not query:
        request = {
            "search_text": "*",
            "query_type": "simple",
            "top": 20,
        }
        return [
            (
                "Azure AI Search request",
                "json",
                json.dumps(request, ensure_ascii=False, indent=2),
            )
        ]

    if mode == "Fuzzy":
        search_text = " ".join(f"{term}~1" for term in query.split())
        request = {
            "search_text": search_text,
            "query_type": "full",
            "search_mode": "all",
            "search_fields": AI_FUZZY_COLUMNS,
            "scoring_profile": "people-ranking",
            "top": 20,
        }
        return [
            (
                "Azure AI Search request",
                "json",
                json.dumps(request, ensure_ascii=False, indent=2),
            ),
            ("Lucene query passed as search_text", "text", search_text),
        ]

    if mode == "Prefix":
        search_text = " ".join(f"{term}*" for term in query.split())
        request = {
            "search_text": search_text,
            "query_type": "full",
            "search_mode": "all",
            "search_fields": AI_SEARCH_COLUMNS,
            "scoring_profile": "people-ranking",
            "top": 20,
        }
        return [
            (
                "Azure AI Search request",
                "json",
                json.dumps(request, ensure_ascii=False, indent=2),
            ),
            ("Lucene query passed as search_text", "text", search_text),
        ]

    escaped_terms = [term.casefold().replace("'", "''") for term in query.split()]
    exact_filter = (
        f"first_name_exact eq '{escaped_terms[0]}' or "
        f"last_name_exact eq '{escaped_terms[0]}'"
        if len(escaped_terms) == 1
        else (
            f"first_name_exact eq '{escaped_terms[0]}' and "
            f"last_name_exact eq '{' '.join(escaped_terms[1:])}'"
        )
    )
    fuzzy_query = " ".join(f"{term}~1" for term in query.split())
    requests = [
        {
            "tier": 4,
            "purpose": "Exact name",
            "search_text": "*",
            "filter": exact_filter,
        },
        {
            "tier": 3,
            "purpose": "Thai analyzed",
            "search_text": query,
            "query_type": "simple",
            "search_mode": "all",
            "search_fields": AI_SEARCH_COLUMNS,
        },
        {
            "tier": 2,
            "purpose": "Name prefix fallback",
            "search_text": query,
            "query_type": "simple",
            "search_fields": ["first_name_prefix", "last_name_prefix"],
        },
        {
            "tier": 1,
            "purpose": "Fuzzy fallback",
            "search_text": fuzzy_query,
            "query_type": "full",
            "search_fields": AI_FUZZY_COLUMNS,
        },
    ]
    return [
        (
            "Tiered Azure AI Search requests",
            "json",
            json.dumps(requests, ensure_ascii=False, indent=2),
        ),
        (
            "Ranking rule",
            "text",
            "Exact > Thai analyzed > name prefix > fuzzy fallback",
        ),
    ]


@st.cache_resource
def azure_credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(
        managed_identity_client_id=os.getenv("AZURE_CLIENT_ID")
    )


@st.cache_resource
def ai_search_client() -> SearchClient:
    return SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=os.getenv("AZURE_SEARCH_INDEX", "thai-people"),
        credential=azure_credential(),
    )


def fuzzy_filter(data: pd.DataFrame, query: str, limit: int = 20) -> pd.DataFrame:
    if not query:
        return data.head(limit)

    combined = data[SEARCH_COLUMNS].fillna("").astype(str).agg(" ".join, axis=1)
    matches = process.extract(
        query, combined.to_dict(), scorer=fuzz.WRatio, limit=min(limit, len(data))
    )
    selected = data.loc[[match[2] for match in matches]].copy()
    selected["score"] = [round(match[1], 1) for match in matches]
    return selected


def prefix_filter(data: pd.DataFrame, query: str, limit: int = 20) -> pd.DataFrame:
    if not query:
        return data.head(limit)
    query = query.casefold()
    mask = pd.Series(False, index=data.index)
    for column in SEARCH_COLUMNS:
        mask |= data[column].fillna("").astype(str).str.casefold().str.startswith(query)
    return data[mask].head(limit)


@st.cache_data
def load_csv() -> pd.DataFrame:
    return pd.read_csv(CSV_PATH, encoding="utf-8-sig")


def sql_connection(database: str | None = None) -> pytds.Connection:
    credential = azure_credential()
    return pytds.connect(
        server=os.environ["AZURE_SQL_SERVER"],
        database=database or os.environ["AZURE_SQL_DATABASE"],
        port=1433,
        login_timeout=10,
        timeout=15,
        cafile=certifi.where(),
        pooling=True,
        access_token_callable=lambda: credential.get_token(
            "https://database.windows.net/.default"
        ).token,
    )


def postgres_connection() -> psycopg.Connection:
    credential = azure_credential()
    entra_token = credential.get_token(
        "https://ossrdbms-aad.database.windows.net/.default"
    ).token
    connection_kwargs = {
        "host": os.environ["AZURE_POSTGRES_SERVER"],
        "dbname": os.environ["AZURE_POSTGRES_DATABASE"],
        "user": os.environ["AZURE_POSTGRES_USER"],
        "port": 5432,
        "sslmode": "require",
        "connect_timeout": 10,
    }
    # The AAD access token is passed as the connection password, per the
    # Entra-only (passwordless) auth model configured on the server.
    connection_kwargs["pass" + "word"] = entra_token
    return psycopg.connect(**connection_kwargs)


def search_sql(query: str, mode: str) -> pd.DataFrame:
    with sql_connection() as connection:
        if mode == "Prefix" and query:
            sql = """
                SELECT TOP 20 id, first_name, last_name, address
                FROM dbo.thai_people
                WHERE first_name LIKE %s OR last_name LIKE %s OR address LIKE %s
                ORDER BY id
            """
            value = f"{query}%"
            return pd.read_sql(sql, connection, params=(value, value, value))

        if mode == "Fuzzy" and query:
            return pd.read_sql(
                BASELINE_SQL_FUZZY_QUERY,
                connection,
                params=(query, query, query),
            )

        return pd.read_sql(
            """
            SELECT TOP 20 id, first_name, last_name, address
            FROM dbo.thai_people
            ORDER BY id
            """,
            connection,
        )


def search_sql_pool(query: str, mode: str) -> pd.DataFrame:
    """Same baseline query pattern as search_sql, run against the SQL
    elastic-pool-hosted demo database instead of the standalone database."""
    with sql_connection(os.environ["AZURE_SQL_POOL_DATABASE"]) as connection:
        if mode == "Prefix" and query:
            sql = """
                SELECT TOP 20 id, first_name, last_name, address
                FROM dbo.thai_people
                WHERE first_name LIKE %s OR last_name LIKE %s OR address LIKE %s
                ORDER BY id
            """
            value = f"{query}%"
            return pd.read_sql(sql, connection, params=(value, value, value))

        if mode == "Fuzzy" and query:
            return pd.read_sql(
                BASELINE_SQL_FUZZY_QUERY,
                connection,
                params=(query, query, query),
            )

        return pd.read_sql(
            """
            SELECT TOP 20 id, first_name, last_name, address
            FROM dbo.thai_people
            ORDER BY id
            """,
            connection,
        )


def search_postgres(query: str, mode: str) -> pd.DataFrame:
    with postgres_connection() as connection:
        if mode == "Prefix" and query:
            value = f"{query}%"
            return pd.read_sql(
                POSTGRES_PREFIX_QUERY, connection, params=(value, value, value)
            )

        if mode == "Fuzzy" and query:
            return pd.read_sql(
                POSTGRES_FUZZY_QUERY,
                connection,
                params=(query, query, query, query, query, query),
            )

        return pd.read_sql(POSTGRES_BROWSE_QUERY, connection)


def search_sql_tokenized(query: str, mode: str) -> pd.DataFrame:
    query_tokens = tokenize_thai(query)
    with sql_connection() as connection:
        if not query_tokens:
            return pd.read_sql(
                """
                SELECT TOP 20 p.id, p.first_name, p.last_name, p.address,
                    (
                        SELECT STRING_AGG(t.token, N' | ')
                        FROM dbo.thai_people_tokens t
                        WHERE t.person_id = p.id
                    ) AS tokens
                FROM dbo.thai_people p
                ORDER BY p.id
                """,
                connection,
            )

        if mode == "Prefix":
            conditions = " AND ".join(
                """
                EXISTS (
                    SELECT 1
                    FROM dbo.thai_people_tokens t
                    WHERE t.person_id = p.id AND t.token LIKE %s
                )
                """
                for _ in query_tokens
            )
            sql = f"""
                SELECT TOP 20 p.id, p.first_name, p.last_name, p.address,
                    (
                        SELECT STRING_AGG(t.token, N' | ')
                        FROM dbo.thai_people_tokens t
                        WHERE t.person_id = p.id
                    ) AS tokens
                FROM dbo.thai_people p
                WHERE {conditions}
                ORDER BY p.id
            """
            return pd.read_sql(
                sql, connection, params=tuple(f"{token}%" for token in query_tokens)
            )

        token_payload = json.dumps(
            [{"token": token} for token in set(query_tokens)],
            ensure_ascii=False,
        )
        return pd.read_sql(
            NATIVE_TOKEN_FUZZY_QUERY,
            connection,
            params=(token_payload,),
        )


def search_ai(query: str, mode: str) -> pd.DataFrame:
    client = ai_search_client()
    if mode == "Smart (tiered)" and query:
        return smart_search_ai(client, query)

    if not query:
        search_text = "*"
        query_type = "simple"
    elif mode == "Fuzzy":
        search_text = " ".join(f"{term}~1" for term in query.split())
        query_type = "full"
    else:
        search_text = " ".join(f"{term}*" for term in query.split())
        query_type = "full"

    results = client.search(
        search_text=search_text,
        query_type=query_type,
        search_mode="all",
        search_fields=(
            AI_FUZZY_COLUMNS if mode == "Fuzzy" else AI_SEARCH_COLUMNS
        ),
        scoring_profile="people-ranking",
        select=AI_SELECT_COLUMNS,
        top=20,
    )
    return ai_results_frame(results)


def ai_results_frame(results, match_type: str | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": int(result["id"]),
                "first_name": result["first_name"],
                "last_name": result["last_name"],
                "address": result["address"],
                "score": round(result["@search.score"], 3),
                **({"match_type": match_type} if match_type else {}),
            }
            for result in results
        ]
    )


def smart_search_ai(client: SearchClient, query: str) -> pd.DataFrame:
    ranked: dict[str, dict] = {}

    def add_results(results, match_type: str, tier: int) -> None:
        for result in results:
            document_id = result["id"]
            rank_score = tier * 1_000_000 + float(result["@search.score"] or 0)
            if document_id not in ranked or rank_score > ranked[document_id]["rank_score"]:
                ranked[document_id] = {
                    "id": int(document_id),
                    "first_name": result["first_name"],
                    "last_name": result["last_name"],
                    "address": result["address"],
                    "match_type": match_type,
                    "score": round(float(result["@search.score"] or 0), 3),
                    "rank_score": rank_score,
                }

    escaped_terms = [term.casefold().replace("'", "''") for term in query.split()]
    if len(escaped_terms) == 1:
        exact_filter = (
            f"first_name_exact eq '{escaped_terms[0]}' or "
            f"last_name_exact eq '{escaped_terms[0]}'"
        )
    else:
        last_name = " ".join(escaped_terms[1:])
        exact_filter = (
            f"(first_name_exact eq '{escaped_terms[0]}' and "
            f"last_name_exact eq '{last_name}')"
        )
    add_results(
        client.search(
            search_text="*",
            filter=exact_filter,
            select=AI_SELECT_COLUMNS,
            top=20,
        ),
        "Exact name",
        4,
    )

    add_results(
        client.search(
            search_text=query,
            query_type="simple",
            search_mode="all",
            search_fields=AI_SEARCH_COLUMNS,
            scoring_profile="people-ranking",
            select=AI_SELECT_COLUMNS,
            top=20,
        ),
        "Thai analyzed",
        3,
    )

    if len(ranked) < 20:
        add_results(
            client.search(
                search_text=query,
                query_type="simple",
                search_mode="all",
                search_fields=["first_name_prefix", "last_name_prefix"],
                scoring_profile="people-ranking",
                select=AI_SELECT_COLUMNS,
                top=20,
            ),
            "Name prefix",
            2,
        )

    if len(ranked) < 20:
        fuzzy_query = " ".join(f"{term}~1" for term in query.split())
        add_results(
            client.search(
                search_text=fuzzy_query,
                query_type="full",
                search_mode="all",
                search_fields=AI_FUZZY_COLUMNS,
                scoring_profile="people-ranking",
                select=AI_SELECT_COLUMNS,
                top=20,
            ),
            "Fuzzy fallback",
            1,
        )

    rows = sorted(ranked.values(), key=lambda item: item["rank_score"], reverse=True)
    for row in rows:
        del row["rank_score"]
    return pd.DataFrame(rows[:20])


def render_search_section(
    title: str,
    description: str,
    key: str,
    search_function,
    logic_function,
    modes: tuple[str, ...] = ("Prefix", "Fuzzy"),
) -> None:
    st.header(title)
    st.caption(description)
    query = st.text_input("Search name or address", key=f"{key}_query")
    mode = st.radio("Search mode", modes, horizontal=True, key=f"{key}_mode")
    with st.expander("Underlying logic and query"):
        for label, language, value in logic_function(query.strip(), mode):
            st.markdown(f"**{label}**")
            st.code(value, language=language)
    try:
        started_at = time.perf_counter()
        results = search_function(query.strip(), mode)
        elapsed_ms = (time.perf_counter() - started_at) * 1_000
        st.metric("Query time", f"{elapsed_ms:.1f} ms")
        st.dataframe(results, hide_index=True)
    except Exception as exc:
        st.error(f"Search failed: {exc}")


EGRESS_HTTPS_TESTS = (
    ("https://api.ipify.org", "Public IP echo (HTTPS 443)"),
    ("https://example.com", "Public website (HTTPS 443)"),
    ("https://mcr.microsoft.com/v2/", "Microsoft Container Registry (HTTPS 443)"),
)
EGRESS_TCP_TESTS = (
    ("smtp.office365.com", 25, "SMTP port 25 to the internet"),
    ("github.com", 22, "SSH port 22 to the internet"),
    ("portquiz.net", 8080, "Arbitrary TCP 8080 to the internet"),
)


def probe_https(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            body = response.read(64).decode("utf-8", "ignore").strip()
            return True, f"HTTP {response.status} {body[:40]}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def probe_tcp(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=6):
            return True, "connected"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


UPLOAD_COLUMNS = [
    "first_name",
    "last_name",
    "street",
    "district",
    "province",
    "postal_code",
    "address",
]


def _next_sql_id(cursor) -> int:
    cursor.execute("SELECT ISNULL(MAX(id), 0) FROM dbo.thai_people")
    return int(cursor.fetchone()[0]) + 1


def upload_to_sql(rows: pd.DataFrame, database: str) -> int:
    with sql_connection(database) as connection:
        cursor = connection.cursor()
        # pytds supports only one active cursor per connection; reuse this
        # cursor for every statement instead of opening a second one.
        next_id = _next_sql_id(cursor)
        for offset, (_, row) in enumerate(rows.iterrows()):
            cursor.execute(
                """
                INSERT INTO dbo.thai_people (
                    id, first_name, last_name, street, district, province,
                    postal_code, address
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    next_id + offset,
                    row["first_name"],
                    row["last_name"],
                    row.get("street", ""),
                    row.get("district", ""),
                    row.get("province", ""),
                    row.get("postal_code", ""),
                    row["address"],
                ),
            )
        connection.commit()
    return len(rows)


def upload_to_postgres(rows: pd.DataFrame) -> int:
    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM thai_people")
            next_id = cursor.fetchone()[0] + 1
            for offset, (_, row) in enumerate(rows.iterrows()):
                cursor.execute(
                    """
                    INSERT INTO thai_people (
                        id, first_name, last_name, street, district, province,
                        postal_code, address
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        next_id + offset,
                        row["first_name"],
                        row["last_name"],
                        row.get("street", ""),
                        row.get("district", ""),
                        row.get("province", ""),
                        row.get("postal_code", ""),
                        row["address"],
                    ),
                )
        connection.commit()
    return len(rows)


def render_upload_section() -> None:
    st.header("7. Upload data")
    st.caption(
        "Add rows to Azure SQL (standalone or elastic-pool database) and/or "
        "Azure Database for PostgreSQL. Uploaded rows are assigned new "
        "auto-incrementing ids and appended; they do not overwrite existing data."
    )
    targets = st.multiselect(
        "Write to",
        [
            "Azure SQL (thai-search-db)",
            "Azure SQL elastic pool (thai-search-pool-demo-db)",
            "Azure Database for PostgreSQL",
        ],
        default=["Azure SQL (thai-search-db)"],
        key="upload_targets",
    )

    tab_manual, tab_csv = st.tabs(["Add one record", "Upload CSV"])

    with tab_manual:
        with st.form("upload_manual_form"):
            first_name = st.text_input("First name")
            last_name = st.text_input("Last name")
            street = st.text_input("Street", value="")
            district = st.text_input("District", value="")
            province = st.text_input("Province", value="")
            postal_code = st.text_input("Postal code", value="")
            address = st.text_area("Full address")
            submitted = st.form_submit_button("Upload record")
        if submitted:
            if not first_name or not last_name or not address:
                st.error("First name, last name, and address are required.")
            else:
                row = pd.DataFrame(
                    [
                        {
                            "first_name": first_name,
                            "last_name": last_name,
                            "street": street,
                            "district": district,
                            "province": province,
                            "postal_code": postal_code,
                            "address": address,
                        }
                    ]
                )
                _upload_rows(row, targets)

    with tab_csv:
        st.caption(
            "CSV columns: " + ", ".join(UPLOAD_COLUMNS)
            + " (first_name, last_name, and address are required)."
        )
        uploaded_file = st.file_uploader("CSV file", type="csv", key="upload_csv")
        if uploaded_file is not None and st.button("Upload CSV rows"):
            try:
                rows = pd.read_csv(uploaded_file, encoding="utf-8-sig")
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")
                return
            missing = {"first_name", "last_name", "address"} - set(rows.columns)
            if missing:
                st.error(f"CSV is missing required columns: {sorted(missing)}")
            else:
                for column in UPLOAD_COLUMNS:
                    if column not in rows.columns:
                        rows[column] = ""
                _upload_rows(rows.fillna(""), targets)


def _upload_rows(rows: pd.DataFrame, targets: list[str]) -> None:
    if not targets:
        st.warning("Select at least one database to write to.")
        return
    for target in targets:
        try:
            if target == "Azure SQL (thai-search-db)":
                count = upload_to_sql(rows, os.environ["AZURE_SQL_DATABASE"])
            elif target == "Azure SQL elastic pool (thai-search-pool-demo-db)":
                count = upload_to_sql(rows, os.environ["AZURE_SQL_POOL_DATABASE"])
            elif target == "Azure Database for PostgreSQL":
                count = upload_to_postgres(rows)
            else:
                continue
            st.success(f"Inserted {count} row(s) into {target}.")
        except Exception as exc:
            st.error(f"Upload to {target} failed: {exc}")


def render_egress_section() -> None:
    st.header("8. Egress test (hub Azure Firewall)")
    st.caption(
        "Outbound probes run from this container. Traffic routed through the hub "
        "firewall leaves with the firewall public IP; the firewall allows HTTP/HTTPS "
        "and has no rule for other internet ports, so those are expected to be blocked."
    )
    if not st.button("Run egress tests", key="egress_run"):
        return

    firewall_ip = os.getenv("FIREWALL_PUBLIC_IP", "")
    rows = []
    observed_ip = ""
    for url, label in EGRESS_HTTPS_TESTS:
        ok, detail = probe_https(url)
        if url == "https://api.ipify.org" and ok:
            observed_ip = detail.split(" ", 2)[-1]
        rows.append(
            {
                "Test": label,
                "Target": url,
                "Expected via firewall": "Allowed",
                "Result": "Works" if ok else "Blocked/failed",
                "Detail": detail,
            }
        )
    for host, port, label in EGRESS_TCP_TESTS:
        ok, detail = probe_tcp(host, port)
        rows.append(
            {
                "Test": label,
                "Target": f"{host}:{port}",
                "Expected via firewall": "Blocked (no allow rule)",
                "Result": "Works" if ok else "Blocked/failed",
                "Detail": detail,
            }
        )

    st.metric("Observed public egress IP", observed_ip or "unknown")
    st.metric("Firewall public IP", firewall_ip or "not configured")
    if observed_ip and firewall_ip:
        if observed_ip == firewall_ip:
            st.success("Egress leaves through the hub Azure Firewall.")
        else:
            st.warning(
                "Egress does NOT use the firewall IP. This Container Apps "
                "environment is consumption-only, which does not support UDRs, so "
                "its subnet bypasses the firewall and the port tests are not enforced."
            )
    st.dataframe(pd.DataFrame(rows), hide_index=True)


@st.cache_resource
def regional_agent_client(project_endpoint: str) -> OpenAI:
    project = AIProjectClient(endpoint=project_endpoint, credential=azure_credential())
    return project.get_openai_client(timeout=90, max_retries=0)


@st.cache_data(ttl=300, show_spinner=False)
def verified_agent_pair(first: AgentSettings, second: AgentSettings, sku: str) -> dict:
    return verify_regional_agents(first, second, sku, azure_credential())


def render_agent_html(html: str, height: int) -> None:
    if hasattr(st, "iframe"):
        st.iframe(html, height=height, alt="Foundry regional flow and timing visualization")
    else:
        components.html(html, height=height, scrolling=True)


def render_agent_timings(
    timings: AgentTimings,
    setup_ms: float,
    total_ms: float,
    recorded_at: str,
    response_id: str,
) -> None:
    response_column, first_token_column = st.columns(2)
    response_column.metric("Responses API time", f"{timings.response_ms / 1000:.2f} s")
    first_token_column.metric(
        "Responses API first text",
        "Unavailable" if timings.first_token_ms is None else f"{timings.first_token_ms / 1000:.2f} s",
    )
    st.caption(
        "Primary API timings exclude client/conversation setup. They include authentication, "
        "network, queueing, model/tools and streaming, not pure inference."
    )
    app_column, token_column, service_column = st.columns(3)
    app_column.metric("SEA app response time", f"{total_ms / 1000:.2f} s")
    token_column.metric(
        "SEA app time to first token",
        "Unavailable" if timings.first_token_ms is None else f"{(setup_ms + timings.first_token_ms) / 1000:.2f} s",
    )
    service_column.metric(
        "Foundry server reference (overlapping)",
        "Unavailable" if timings.service_run_ms is None else f"{timings.service_run_ms / 1000:.0f} s",
    )
    render_agent_html(timeline_html(timings, setup_ms, total_ms), height=175)
    with st.expander("Latency breakdown"):
        st.dataframe(
            pd.DataFrame(
                [
                    ("Client/conversation setup", setup_ms),
                    ("Responses API stream", timings.response_ms),
                    ("Local response processing", total_ms - setup_ms - timings.response_ms),
                ],
                columns=["Stage", "Elapsed (ms)"],
            ),
            hide_index=True,
        )
        st.caption(f"Response: {response_id} | Captured: {recorded_at}")
        st.caption(
            "Measured at the SEA server, including client/conversation setup, authentication, "
            "network and model/tools. Browser traffic, Gateway/WAF and rendering are excluded. "
            "Time to first token is the first nonempty text delta received by the app, "
            "not the first browser paint. The Responses API streams without Classic run polling."
        )
        st.caption(
            "Foundry run is a separate, overlapping reference from server creation/completion "
            "timestamps with one-second precision. It includes queueing and model/tools, "
            "not just model inference. Do not add it to the stages or subtract it to claim "
            "pure network overhead. It is unavailable if completion timestamps are not supplied."
        )


def render_agent_connection_probe(settings: AgentSettings) -> None:
    probe_key = f"regional_agent_{settings.region}_connection_probe"
    with st.expander(f"Measure SEA app -> {settings.label} connection latency"):
        st.write(
            "Measure five fresh TCP connections to the configured Foundry endpoint, "
            "without calling the model. TCP connect time approximates the connection "
            "round trip, not the entire agent request."
        )
        if st.button("Measure connection latency", key=f"{probe_key}_run"):
            st.session_state.pop(probe_key, None)
            try:
                with st.spinner("Measuring connections from this app..."):
                    st.session_state[probe_key] = measure_agent_connection(settings)
            except (OSError, ValueError) as exc:
                LOGGER.exception("Regional agent connection probe failed")
                st.error(f"Connection latency measurement failed: {exc}")
        probe = st.session_state.get(probe_key)
        if probe:
            median_column, min_column, max_column = st.columns(3)
            median_column.metric("Median TCP connect", f"{probe.median_tcp_ms:.1f} ms")
            min_column.metric("Min TCP connect", f"{min(probe.tcp_samples_ms):.1f} ms")
            max_column.metric("Max TCP connect", f"{max(probe.tcp_samples_ms):.1f} ms")
            st.caption(
                f"Target: {probe.hostname}:443 -> {probe.resolved_ip} | "
                f"DNS lookup: {probe.dns_ms:.1f} ms | Captured: {probe.measured_at}"
            )
            st.dataframe(
                pd.DataFrame(
                    {"Sample": range(1, 6), "TCP connect (ms)": probe.tcp_samples_ms}
                ),
                hide_index=True,
            )
        st.caption(
            "DNS is measured separately and may be cached. TCP measurements exclude TLS, "
            "authentication and model processing; agents make multiple API calls. "
            "Connections are closed after each sample. These values approximate the app-to-endpoint "
            "transport baseline, not the entire request or the model inference location."
        )


def render_agent_latency_export() -> None:
    ledger = st.session_state.setdefault("regional_agent_measurements", [])
    rows = [row for row in ledger if row["comparison_mode"] in COMPARISON_TARGETS]
    if rows:
        with st.expander("Captured latency measurements"):
            if st.button("Clear captured latency measurements", key="regional_agent_clear_measurements"):
                ledger[:] = [row for row in ledger if row["comparison_mode"] not in COMPARISON_TARGETS]
                st.rerun()
            frame = pd.DataFrame(rows)
            paired = frame[frame["comparison_complete"] & ~frame["warmup"]]
            if not paired.empty:
                st.caption(
                    "Benchmark medians use complete pairs only, excluding warm-up pairs and single-agent chats. "
                    "Comparison modes and workloads are kept separate."
                )
                st.dataframe(
                    paired.groupby(
                        ["comparison_mode", "workload", "agent_region", "model_sku"], as_index=False
                    ).agg(
                        samples=("app_response_ms", "size"),
                        median_response_ms=("app_response_ms", "median"),
                        median_first_token_ms=("app_first_token_ms", "median"),
                        median_responses_api_ms=("responses_stream_ms", "median"),
                        median_responses_api_first_token_ms=("responses_first_token_ms", "median"),
                    ),
                    hide_index=True,
                )
            st.dataframe(frame, hide_index=True)
            st.download_button(
                "Download latency measurements (CSV)",
                frame.to_csv(index=False),
                file_name="foundry-agent-latency.csv",
                mime="text/csv",
                key="regional_agent_latency_download",
            )
            st.caption(
                "Successful calls across both comparison modes in this browser session; prompts and replies "
                "are not included. Export before closing the session. New conversation retains measurements."
            )


def render_agent_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        if message.get("fresh_comparison"):
            st.caption("Fresh conversation for paired comparison")
        if message.get("benchmark_context"):
            st.caption(message["benchmark_context"])
        st.markdown(message["text"])
        if message.get("file_ids"):
            st.caption("Cited files: " + ", ".join(message["file_ids"]))
        if message.get("timings") is not None:
            render_agent_timings(
                message["timings"], message["setup_ms"], message["total_ms"],
                message["recorded_at"], message["response_id"],
            )


def latest_agent_pair(mode: str, workload: str) -> list[dict]:
    rows = [
        row for row in st.session_state.get("regional_agent_measurements", [])
        if row["comparison_mode"] == mode and row["workload"] == workload
        and row["comparison_complete"] and not row["warmup"]
    ]
    if not rows:
        return []
    comparison_id = rows[-1]["comparison_id"]
    return [row for row in rows if row["comparison_id"] == comparison_id]


def render_agent_flow(mode: str, workload: str, blocked_reason: str = "") -> list[dict]:
    rows = [] if blocked_reason else latest_agent_pair(mode, workload)
    probes = {
        region: st.session_state[f"regional_agent_{region}_connection_probe"]
        for region in ("sea", "westus3")
        if f"regional_agent_{region}_connection_probe" in st.session_state
    }
    st.subheader("Data flow and measured time")
    st.caption(
        f"Last complete, non-warm-up {workload} pair: {rows[-1]['comparison_id']}"
        if rows else "No complete measured pair for this mode/workload. No timings are invented."
    )
    render_agent_html(flow_html(mode, rows, probes, blocked_reason), height=655)
    st.download_button(
        "Download editable flow diagram",
        flow_excalidraw(mode, rows, blocked_reason),
        file_name=f"foundry-{mode}-regional-flow.excalidraw",
        mime="application/json", key=f"agent_flow_download_{mode}",
    )
    st.caption(
        "Global Standard does not expose the physical inference region. Standard follows its configured "
        "Azure geography processing policy, not a guarantee that every operation stays in one physical region. "
        "Tools are disabled in model-only mode; tool-internal timings are not measured when retrieval is enabled."
    )
    return rows


def render_agent_transfer_cost(mode: str, rows: list[dict], available: bool) -> None:
    with st.expander("Approximate egress / data-transfer cost", expanded=True):
        st.caption(
            f"USD public retail snapshot checked {PRICING_CHECKED}; decimal GB, first Private Link tier. "
            "App-to-Foundry leg only, not an Azure bill or token-cost estimate."
        )
        if not available:
            st.warning("This scenario is hypothetical: the selected matched comparison is unavailable.")
        request_column, response_column, calls_column = st.columns(3)
        request_kib = request_column.number_input(
            "Assumed request KiB per call", min_value=0.0, max_value=1024.0,
            value=4.0, key="agent_cost_request_kib",
        )
        response_kib = response_column.number_input(
            "Assumed response KiB per call", min_value=0.0, max_value=1024.0,
            value=64.0, key="agent_cost_response_kib",
        )
        calls = calls_column.number_input(
            "Calls per regional endpoint / month", min_value=0, max_value=1_000_000,
            value=10_000, key="agent_cost_calls",
        )
        estimates = []
        for region, label in (("sea", "Southeast Asia"), ("westus3", "West US 3")):
            cost = estimate_transfer(region, request_kib * 1024, response_kib * 1024, calls)
            estimates.append({
                "Endpoint": label, "SKU": COMPARISON_SKUS[mode],
                "Scenario": "Assumed monthly volume" if available else "Hypothetical / unavailable pair",
                "Request GB": cost["request_gb"], "Response GB": cost["response_gb"],
                "SEA peering USD": cost["sea_peering_usd"],
                "West peering USD": cost["westus3_peering_usd"],
                "Private Link USD": cost["private_link_usd"], "Estimated USD": cost["total_usd"],
            })
        st.dataframe(pd.DataFrame(estimates), hide_index=True)
        st.markdown(
            "**West US 3:** SEA global-peering ingress/egress $0.09/GB + West US 3 "
            "$0.035/GB = **$0.125/GB across both endpoints**, plus destination Private Link "
            "processing $0.01/GB, approximately **$0.135/GB** of request + response traffic. "
            "**SEA:** same VNet, no global-peering charge; approximately **$0.01/GB** "
            "Private Link processing. For 1 GB requests + 1 GB responses: West approximately "
            "**$0.27**, SEA approximately **$0.02**. Each direction is counted once."
        )
        observed = []
        for row in rows:
            request_bytes, response_bytes = row.get("request_payload_bytes"), row.get("response_payload_bytes")
            if request_bytes is None or response_bytes is None:
                continue
            cost = estimate_transfer(
                "sea" if row["agent_region"] == "Southeast Asia" else "westus3",
                request_bytes, response_bytes,
            )
            observed.append({
                "Endpoint": row["agent_region"], "Response ID": row["response_id"],
                "Responses request body bytes": request_bytes, "Stream body bytes": response_bytes,
                "Body-only estimate USD": f'{cost["total_usd"]:.8f}',
            })
        if observed:
            st.dataframe(pd.DataFrame(observed), hide_index=True)
        st.caption(
            "Observed Responses HTTP-body bytes include SSE stream framing but exclude HTTP headers, "
            "TLS/TCP, authentication, conversation creation and agent-internal traffic. They are a partial "
            "baseline, not Azure billed bytes; tokens are NOT converted to network bytes. The monthly "
            "calculator uses your explicit assumed volumes, not extrapolated token counts."
        )
        st.caption(
            "Existing Standard Private Endpoints cost $0.01/hour each (about $7.30 at 730 hours), "
            "shared by deployments; no new endpoint is required for a SKU. Excluded: endpoint hours, "
            "model tokens/tools, Search/Blob/Cosmos, compute, Gateway/WAF, protocol overhead and common "
            "browser/hub-path traffic. No generic inter-region bandwidth is added on top of peering. "
            "Hidden Global Standard inference routing is not treated as billable customer VNet peering. "
            "Actual prices, discounts, tiers and invoices can differ."
        )
        st.markdown(
            f"[Azure Retail Prices API]({PRICING_SOURCE}) | "
            "[Global VNet peering pricing](https://azure.microsoft.com/en-us/pricing/details/virtual-network/) | "
            "[Private Link pricing](https://azure.microsoft.com/en-us/pricing/details/private-link/)"
        )


def render_agent_section() -> None:
    st.header("9. Private Foundry agents: matched regional comparisons")
    st.caption(
        "New versioned Foundry agents using Conversations/Responses, not Classic Assistants. "
        "The SEA Container App uses managed identity and private endpoints, with global "
        "VNet peering for West US 3. Existing Classic agents are retained but not called."
    )
    if st.session_state.get("agent_comparison_mode") not in COMPARISON_TARGETS:
        st.session_state["agent_comparison_mode"] = "global"
    mode = st.selectbox(
        "Comparison mode", list(COMPARISON_TARGETS), format_func=COMPARISON_LABELS.__getitem__,
        key="agent_comparison_mode",
    )
    namespace = f"matched_agent_{mode}"
    targets = COMPARISON_TARGETS[mode]
    labels = {target: "Southeast Asia" if target.startswith("sea") else "West US 3" for target in targets}
    use_search = st.checkbox("Include file search", key=f"{namespace}_search")
    warmup = st.checkbox("Warm-up pair (exclude from benchmark medians)", key=f"{namespace}_warmup")
    workload = "agent_with_search" if use_search else "model_only"
    blocked_reason = ""
    pair_settings = {}
    try:
        pair_settings = {target: AgentSettings.from_env(target) for target in targets}
        verified = verified_agent_pair(
            pair_settings[targets[0]], pair_settings[targets[1]], COMPARISON_SKUS[mode],
        )
    except (AzureError, OpenAIError, OSError, ValueError, RuntimeError) as exc:
        LOGGER.exception("Matched regional agent validation failed")
        blocked_reason = f"{SEA_STANDARD_UNAVAILABLE} {exc}" if mode == "standard" else f"Comparison blocked: {exc}"
        st.error(blocked_reason)
    else:
        st.info(
            f"Live-verified {verified['sku']}: {verified['model']} version {verified['version']}, "
            f"capacity {verified['capacity']} each, matching instructions, temperature, tools and corpus bytes. "
            "Different regional vector stores hold the same document. Model-only disables tools; "
            "file-search execution and output/cache/token counts can still vary."
        )
        st.caption(f"Agent/deployment check: {verified['verified_at']} (cached for up to five minutes).")
    flow_container = st.container()
    cost_container = st.container()
    if blocked_reason:
        with flow_container:
            rows = render_agent_flow(mode, workload, blocked_reason)
        with cost_container:
            render_agent_transfer_cost(mode, rows, False)
        st.button("Compare both regions (fresh conversations)", disabled=True, key=f"{namespace}_blocked")
        render_agent_latency_export()
        return
    selected = st.radio(
        "Agent region", targets,
        format_func=labels.__getitem__, horizontal=True,
        key=f"{namespace}_target",
    )
    settings = pair_settings[selected]

    with st.expander("Agent configuration and underlying logic"):
        st.code(
            "Browser -> Application Gateway/WAF -> SEA Container App\n"
            f"        -> private Foundry endpoint in {settings.label}\n\n"
            f"Project: {settings.project_endpoint}\n"
            f"Agent: {settings.agent_name}, pinned version {settings.agent_version}\n"
            f"Model deployment SKU: {settings.model_sku}",
            language="text",
        )
        st.code(
            "client.conversations.create()\n"
            "client.responses.create(conversation=conversation_id, input=prompt,\n"
            "    stream=True, extra_body={'agent_reference': {\n"
            "        'type': 'agent_reference', 'name': agent_name, 'version': agent_version}})",
            language="python",
        )

    render_agent_connection_probe(settings)
    context_suffix = f"_{workload}"
    prefix = f"{namespace}_{selected}{context_suffix}"
    messages = st.session_state.setdefault(f"{prefix}_messages", [])
    if st.button("New agent conversation", key=f"{namespace}_new"):
        st.session_state[f"{prefix}_conversation"] = None
        messages.clear()
    st.caption(
        "Try model-only: List three popular foods in Bangkok in one sentence. "
        "With file search: What is the West US 3 readiness code in the document? "
        "A new conversation resets only the selected agent/workload context, not either agent. "
        "Paired comparison sends the same prompt to both agents sequentially in fresh "
        "conversations and incurs two model calls. Starting order alternates on successive pairs. "
        "Run a warm-up pair, then repeat measured pairs to compare medians, not just one sample."
    )
    for message in messages:
        render_agent_message(message)

    with st.form(f"{namespace}_form", clear_on_submit=True):
        prompt = st.text_area("Message the selected agent or compare both", max_chars=4000)
        submitted = st.form_submit_button("Send to selected agent")
        compare = st.form_submit_button("Compare both regions (fresh conversations)")
    if not submitted and not compare:
        with flow_container:
            rows = render_agent_flow(mode, workload)
        with cost_container:
            render_agent_transfer_cost(mode, rows, True)
        render_agent_latency_export()
        return
    if not prompt.strip():
        st.error("Enter a message before sending.")
        with flow_container:
            rows = render_agent_flow(mode, workload)
        with cost_container:
            render_agent_transfer_cost(mode, rows, True)
        render_agent_latency_export()
        return

    comparison_id = datetime.now(timezone.utc).isoformat() if compare else ""
    ordered_targets = (selected,)
    if compare:
        count_key = f"{namespace}_comparison_count"
        count = st.session_state.get(count_key, 0)
        ordered_targets = tuple(reversed(targets)) if count % 2 else targets
        st.session_state[count_key] = count + 1
    pair_rows = []
    for position, target_key in enumerate(ordered_targets, start=1):
        try:
            target = pair_settings[target_key]
            target_prefix = f"{namespace}_{target_key}{context_suffix}"
            history = st.session_state.setdefault(f"{target_prefix}_messages", [])
            if compare:
                st.subheader(labels[target_key])
            user_message = {"role": "user", "text": prompt, "fresh_comparison": compare}
            history.append(user_message)
            render_agent_message(user_message)
            started_at = time.perf_counter()
            client = regional_agent_client(target.project_endpoint)
            conversation_id = st.session_state.get(f"{target_prefix}_conversation")
            if compare or not conversation_id:
                conversation_id = client.conversations.create().id
                st.session_state[f"{target_prefix}_conversation"] = conversation_id
            setup_ms = (time.perf_counter() - started_at) * 1000
            with st.spinner(f"Calling the private {target.label} agent..."):
                reply = invoke_agent(
                    client, target, conversation_id, prompt,
                    tool_choice="auto" if use_search else "none",
                )
            total_ms = (time.perf_counter() - started_at) * 1000
            recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            assistant_message = {
                "role": "assistant",
                "text": reply.text,
                "file_ids": reply.file_ids,
                "timings": reply.timings,
                "setup_ms": setup_ms,
                "total_ms": total_ms,
                "recorded_at": recorded_at,
                "response_id": reply.response_id,
                "benchmark_context": (
                    f"{target.model_sku} | {workload} | "
                    f"{'warm-up' if warmup else 'measured'} | "
                    f"Input/output tokens: {reply.input_tokens}/{reply.output_tokens} | "
                    f"Cached input tokens: {reply.cached_input_tokens} | "
                    f"File-search calls: {reply.file_search_calls}"
                ),
            }
            history.append(assistant_message)
            render_agent_message(assistant_message)
            row = {
                "captured_at_utc": recorded_at,
                "comparison_id": comparison_id,
                "comparison_mode": mode,
                "comparison_complete": False,
                "pair_position": position if compare else None,
                "warmup": warmup,
                "workload": workload,
                "project_endpoint": target.project_endpoint,
                "agent_region": target.label,
                "agent_name": target.agent_name,
                "agent_version": target.agent_version,
                "model": reply.model,
                "model_sku": target.model_sku,
                "response_id": reply.response_id,
                "conversation_id": conversation_id,
                "app_response_ms": total_ms,
                "app_first_token_ms": (
                    setup_ms + reply.timings.first_token_ms
                    if reply.timings.first_token_ms is not None else None
                ),
                "client_conversation_setup_ms": setup_ms,
                "responses_stream_ms": reply.timings.response_ms,
                "responses_first_token_ms": reply.timings.first_token_ms,
                "service_run_approx_ms": reply.timings.service_run_ms,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "cached_input_tokens": reply.cached_input_tokens,
                "file_search_calls": reply.file_search_calls,
                "request_payload_bytes": reply.request_payload_bytes,
                "response_payload_bytes": reply.response_payload_bytes,
            }
            st.session_state.setdefault("regional_agent_measurements", []).append(row)
            pair_rows.append(row)
        except (AzureError, OpenAIError, OSError, ValueError, RuntimeError) as exc:
            LOGGER.exception("Foundry agent invocation failed for %s", target_key)
            st.error(f"{labels[target_key]} agent call failed: {exc}")
    if compare:
        for row in pair_rows:
            row["comparison_complete"] = len(pair_rows) == len(targets)
    with flow_container:
        rows = render_agent_flow(mode, workload)
    with cost_container:
        render_agent_transfer_cost(mode, rows, True)
    render_agent_latency_export()


def main() -> None:
    st.set_page_config(page_title="Thai People Search", layout="wide")
    st.title("Thai First Name, Last Name and Address Search")
    st.write(
        "Compare prefix and fuzzy search across CSV, Azure SQL (standalone and "
        "elastic pool), Azure Database for PostgreSQL, and Azure AI Search. "
        "Upload new records to either database from this app."
    )

    render_search_section(
        "1. Local CSV",
        "Prefix filtering and RapidFuzz edit-distance ranking run locally.",
        "csv",
        lambda query, mode: (
            prefix_filter(load_csv(), query)
            if mode == "Prefix"
            else fuzzy_filter(load_csv(), query)
        ),
        csv_logic,
    )
    st.divider()
    render_search_section(
        "2. Azure SQL Database",
        "Prefix search uses SQL LIKE. Fuzzy search uses native Azure SQL "
        "EDIT_DISTANCE_SIMILARITY directly on the original columns.",
        "sql",
        search_sql,
        baseline_sql_logic,
    )
    st.divider()
    render_search_section(
        "3. Azure SQL Database with Custom Thai Tokenization",
        "PyThaiNLP newmm tokens are stored in an indexed SQL token table. Prefix "
        "and native edit-distance fuzzy ranking both run inside Azure SQL.",
        "sql_tokens",
        search_sql_tokenized,
        tokenized_sql_logic,
    )
    st.divider()
    render_search_section(
        "4. Azure AI Search",
        "Prefix and fuzzy use native Lucene queries. Smart mode prioritizes exact "
        "names, Thai-analyzed matches, name prefixes, then fuzzy fallback.",
        "search",
        search_ai,
        ai_search_logic,
        ("Prefix", "Fuzzy", "Smart (tiered)"),
    )
    st.divider()
    render_search_section(
        "5. Azure SQL Elastic Pool (Basic demo database)",
        "Same query logic as tab 2, but the target database shares a Basic "
        "elastic pool's eDTUs with other pooled databases instead of having "
        "its own dedicated compute.",
        "sql_pool",
        search_sql_pool,
        pool_sql_logic,
    )
    st.divider()
    render_search_section(
        "6. Azure Database for PostgreSQL",
        "Prefix search uses ILIKE. Fuzzy search uses the pg_trgm extension's "
        "trigram similarity() function and the %-similarity operator.",
        "postgres",
        search_postgres,
        postgres_logic,
    )
    st.divider()
    render_upload_section()
    st.divider()
    render_egress_section()
    st.divider()
    render_agent_section()


if __name__ == "__main__":
    main()
