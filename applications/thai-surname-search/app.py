from __future__ import annotations

import json
import os
import textwrap
import time
from pathlib import Path

import pandas as pd
import pytds
import streamlit as st
import certifi
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from rapidfuzz import fuzz, process
from sql_search import BASELINE_SQL_FUZZY_QUERY, NATIVE_TOKEN_FUZZY_QUERY
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


def sql_connection() -> pytds.Connection:
    credential = azure_credential()
    return pytds.connect(
        server=os.environ["AZURE_SQL_SERVER"],
        database=os.environ["AZURE_SQL_DATABASE"],
        port=1433,
        login_timeout=10,
        timeout=15,
        cafile=certifi.where(),
        pooling=True,
        access_token_callable=lambda: credential.get_token(
            "https://database.windows.net/.default"
        ).token,
    )


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


def main() -> None:
    st.set_page_config(page_title="Thai People Search", layout="wide")
    st.title("Thai First Name, Last Name and Address Search")
    st.write(
        "Compare prefix and fuzzy search across CSV, Azure SQL, and Azure AI Search."
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


if __name__ == "__main__":
    main()
