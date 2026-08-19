from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytds
import certifi
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes._generated.models import (
    CustomAnalyzer,
    EdgeNGramTokenFilterV2,
)
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    ScoringProfile,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    TextWeights,
)
from dotenv import load_dotenv
from sql_search import BASELINE_SQL_FUZZY_QUERY, NATIVE_TOKEN_FUZZY_QUERY
from thai_tokenization import tokenize_thai


ROOT = Path(__file__).parent
BATCH_SIZE = 1_000
SQL_BATCH_SIZE = 5_000


def az(*args: str) -> str:
    command = ["az", *args, "--only-show-errors", "-o", "json"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def load_rows() -> list[dict[str, str]]:
    with (ROOT / "thai_people.csv").open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def azure_credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(
        managed_identity_client_id=os.getenv("AZURE_CLIENT_ID")
    )


def sql_connection() -> pytds.Connection:
    credential = azure_credential()
    return pytds.connect(
        server=os.environ["AZURE_SQL_SERVER"],
        database=os.environ["AZURE_SQL_DATABASE"],
        port=1433,
        login_timeout=30,
        timeout=180,
        cafile=certifi.where(),
        access_token_callable=lambda: credential.get_token(
            "https://database.windows.net/.default"
        ).token,
    )


def load_sql(rows: list[dict[str, str]]) -> None:
    with sql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            IF OBJECT_ID('dbo.thai_people', 'U') IS NULL
            CREATE TABLE dbo.thai_people (
                id INT NOT NULL PRIMARY KEY,
                first_name NVARCHAR(100) NOT NULL,
                last_name NVARCHAR(100) NOT NULL,
                street NVARCHAR(150) NOT NULL,
                district NVARCHAR(150) NOT NULL,
                province NVARCHAR(150) NOT NULL,
                postal_code NVARCHAR(10) NOT NULL,
                address NVARCHAR(500) NOT NULL
            )
            """
        )
        cursor.execute(
            """
            IF COL_LENGTH('dbo.thai_people', 'street') IS NULL
                ALTER TABLE dbo.thai_people ADD street NVARCHAR(150) NULL;
            IF COL_LENGTH('dbo.thai_people', 'district') IS NULL
                ALTER TABLE dbo.thai_people ADD district NVARCHAR(150) NULL;
            IF COL_LENGTH('dbo.thai_people', 'province') IS NULL
                ALTER TABLE dbo.thai_people ADD province NVARCHAR(150) NULL;
            IF COL_LENGTH('dbo.thai_people', 'postal_code') IS NULL
                ALTER TABLE dbo.thai_people ADD postal_code NVARCHAR(10) NULL;
            """
        )
        cursor.execute(
            """
            IF OBJECT_ID('dbo.thai_people_tokens', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.thai_people_tokens (
                    person_id INT NOT NULL,
                    field_name NVARCHAR(20) NOT NULL,
                    token NVARCHAR(100) NOT NULL,
                    CONSTRAINT PK_thai_people_tokens
                        PRIMARY KEY (person_id, field_name, token),
                    CONSTRAINT FK_thai_people_tokens_person
                        FOREIGN KEY (person_id) REFERENCES dbo.thai_people(id)
                );
                CREATE INDEX IX_thai_people_tokens_lookup
                    ON dbo.thai_people_tokens (token, field_name)
                    INCLUDE (person_id);
            END
            """
        )
        cursor.execute(
            """
            IF OBJECT_ID('dbo.thai_token_vocabulary', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.thai_token_vocabulary (
                    token NVARCHAR(100) NOT NULL PRIMARY KEY,
                    token_length AS CONVERT(SMALLINT, LEN(token)) PERSISTED
                );
                CREATE INDEX IX_thai_token_vocabulary_length
                    ON dbo.thai_token_vocabulary (token_length, token);
            END

            IF NOT EXISTS (SELECT 1 FROM dbo.thai_token_vocabulary)
                INSERT INTO dbo.thai_token_vocabulary (token)
                SELECT DISTINCT token
                FROM dbo.thai_people_tokens;
            """
        )
        cursor.execute(
            """
            IF COL_LENGTH('dbo.thai_people_tokens', 'token_length') IS NULL
                ALTER TABLE dbo.thai_people_tokens
                ADD token_length AS CONVERT(SMALLINT, LEN(token)) PERSISTED;

            IF NOT EXISTS (
                SELECT 1
                FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.thai_people_tokens')
                    AND name = 'IX_thai_people_tokens_length'
            )
                CREATE INDEX IX_thai_people_tokens_length
                    ON dbo.thai_people_tokens (token_length, token)
                    INCLUDE (person_id, field_name);
            """
        )
        cursor.execute(
            """
            IF OBJECT_ID('dbo.thai_search_metadata', 'U') IS NULL
            CREATE TABLE dbo.thai_search_metadata (
                metadata_key NVARCHAR(100) NOT NULL PRIMARY KEY,
                metadata_value NVARCHAR(200) NOT NULL
            )
            """
        )
        dataset_hash = hashlib.sha256(
            json.dumps(
                rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        cursor.execute(
            """
            SELECT metadata_value
            FROM dbo.thai_search_metadata
            WHERE metadata_key = N'dataset_hash'
            """
        )
        hash_row = cursor.fetchone()
        if hash_row and hash_row[0] == dataset_hash:
            connection.commit()
            return

        if not hash_row:
            cursor.execute("SELECT COUNT(*) FROM dbo.thai_people")
            existing_people = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM dbo.thai_people_tokens")
            existing_tokens = cursor.fetchone()[0]
            if existing_people == len(rows) and existing_tokens > len(rows):
                cursor.execute(
                    """
                    INSERT INTO dbo.thai_search_metadata (
                        metadata_key, metadata_value
                    )
                    VALUES (N'dataset_hash', %s)
                    """,
                    (dataset_hash,),
                )
                connection.commit()
                return

        cursor.execute("DELETE FROM dbo.thai_people_tokens")
        cursor.execute("DELETE FROM dbo.thai_token_vocabulary")
        cursor.execute("DELETE FROM dbo.thai_people")
        person_documents = [
            {**row, "id": int(row["id"])}
            for row in rows
        ]
        for offset in range(0, len(person_documents), SQL_BATCH_SIZE):
            payload = json.dumps(
                person_documents[offset : offset + SQL_BATCH_SIZE],
                ensure_ascii=False,
            )
            cursor.execute(
                """
                INSERT INTO dbo.thai_people (
                    id, first_name, last_name, street, district, province,
                    postal_code, address
                )
                SELECT
                    id, first_name, last_name, street, district, province,
                    postal_code, address
                FROM OPENJSON(%s)
                WITH (
                    id INT '$.id',
                    first_name NVARCHAR(100) '$.first_name',
                    last_name NVARCHAR(100) '$.last_name',
                    street NVARCHAR(150) '$.street',
                    district NVARCHAR(150) '$.district',
                    province NVARCHAR(150) '$.province',
                    postal_code NVARCHAR(10) '$.postal_code',
                    address NVARCHAR(500) '$.address'
                )
                """,
                (payload,),
            )
        token_values = []
        token_fields = [
            "first_name",
            "last_name",
            "street",
            "district",
            "province",
            "postal_code",
            "address",
        ]
        for row in rows:
            for field_name in token_fields:
                for token in set(tokenize_thai(row[field_name])):
                    token_values.append(
                        {
                            "person_id": int(row["id"]),
                            "field_name": field_name,
                            "token": token,
                        }
                    )
        for offset in range(0, len(token_values), SQL_BATCH_SIZE):
            payload = json.dumps(
                token_values[offset : offset + SQL_BATCH_SIZE], ensure_ascii=False
            )
            cursor.execute(
                """
                INSERT INTO dbo.thai_people_tokens (person_id, field_name, token)
                SELECT person_id, field_name, token
                FROM OPENJSON(%s)
                WITH (
                    person_id INT '$.person_id',
                    field_name NVARCHAR(20) '$.field_name',
                    token NVARCHAR(100) '$.token'
                )
                """,
                (payload,),
            )
        cursor.execute(
            """
            INSERT INTO dbo.thai_token_vocabulary (token)
            SELECT DISTINCT token
            FROM dbo.thai_people_tokens
            """
        )
        cursor.execute(
            """
            MERGE dbo.thai_search_metadata AS target
            USING (
                SELECT N'dataset_hash' AS metadata_key, %s AS metadata_value
            ) AS source
            ON target.metadata_key = source.metadata_key
            WHEN MATCHED THEN
                UPDATE SET metadata_value = source.metadata_value
            WHEN NOT MATCHED THEN
                INSERT (metadata_key, metadata_value)
                VALUES (source.metadata_key, source.metadata_value);
            """,
            (dataset_hash,),
        )
        connection.commit()


def load_search(rows: list[dict[str, str]]) -> None:
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.getenv("AZURE_SEARCH_INDEX", "thai-people")
    credential = azure_credential()
    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(
            name="first_name",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            sortable=True,
            analyzer_name="th.lucene",
        ),
        SearchField(
            name="last_name",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            sortable=True,
            analyzer_name="th.lucene",
        ),
        SearchField(
            name="first_name_exact",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            analyzer_name="keyword",
        ),
        SearchField(
            name="last_name_exact",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            analyzer_name="keyword",
        ),
        SearchField(
            name="first_name_prefix",
            type=SearchFieldDataType.String,
            searchable=True,
            index_analyzer_name="name_edge_analyzer",
            search_analyzer_name="keyword",
        ),
        SearchField(
            name="last_name_prefix",
            type=SearchFieldDataType.String,
            searchable=True,
            index_analyzer_name="name_edge_analyzer",
            search_analyzer_name="keyword",
        ),
        SearchField(
            name="street",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            analyzer_name="th.lucene",
        ),
        SearchField(
            name="district",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            facetable=True,
            analyzer_name="th.lucene",
        ),
        SearchField(
            name="province",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            facetable=True,
            analyzer_name="th.lucene",
        ),
        SearchField(
            name="postal_code",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            analyzer_name="keyword",
        ),
        SearchField(
            name="address",
            type=SearchFieldDataType.String,
            searchable=True,
            analyzer_name="th.lucene",
        ),
    ]
    index = SearchIndex(
        name=index_name,
        fields=fields,
        analyzers=[
            CustomAnalyzer(
                name="name_edge_analyzer",
                tokenizer="standard_v2",
                token_filters=["lowercase", "name_edge_filter"],
            )
        ],
        token_filters=[
            EdgeNGramTokenFilterV2(
                name="name_edge_filter", min_gram=1, max_gram=30
            )
        ],
        scoring_profiles=[
            ScoringProfile(
                name="people-ranking",
                text_weights=TextWeights(
                    weights={
                        "first_name_exact": 10,
                        "last_name_exact": 10,
                        "first_name": 5,
                        "last_name": 5,
                        "district": 3,
                        "province": 3,
                        "street": 2,
                        "postal_code": 2,
                        "address": 1,
                    }
                ),
            )
        ],
        default_scoring_profile="people-ranking",
    )
    required_fields = {field.name for field in fields}
    try:
        existing_index = index_client.get_index(index_name)
        existing_fields = {field.name for field in existing_index.fields}
        if not required_fields.issubset(existing_fields):
            index_client.delete_index(index_name)
            index_client.create_index(index)
        else:
            index_client.create_or_update_index(index, allow_index_downtime=True)
    except ResourceNotFoundError:
        index_client.create_index(index)

    search_client = SearchClient(endpoint, index_name, credential)
    documents = [
        {
            **row,
            "first_name_exact": row["first_name"].casefold(),
            "last_name_exact": row["last_name"].casefold(),
            "first_name_prefix": row["first_name"],
            "last_name_prefix": row["last_name"],
        }
        for row in rows
    ]
    failure_count = 0
    for offset in range(0, len(documents), BATCH_SIZE):
        result = search_client.upload_documents(
            documents[offset : offset + BATCH_SIZE]
        )
        failure_count += sum(not item.succeeded for item in result)
    if failure_count:
        raise RuntimeError(f"Failed to upload {failure_count} search documents")


def verify_sql(rows_expected: int) -> tuple[int, int, int]:
    with sql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.thai_people")
        sql_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dbo.thai_people_tokens")
        token_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dbo.thai_token_vocabulary")
        vocabulary_count = cursor.fetchone()[0]
    if sql_count != rows_expected:
        raise RuntimeError(f"Expected {rows_expected}; SQL has {sql_count}")
    if token_count <= rows_expected:
        raise RuntimeError(
            f"Expected more than {rows_expected} SQL tokens; found {token_count}"
        )
    if vocabulary_count == 0:
        raise RuntimeError("SQL token vocabulary is empty")
    return sql_count, token_count, vocabulary_count


def verify_search(rows_expected: int) -> int:
    search_client = SearchClient(
        os.environ["AZURE_SEARCH_ENDPOINT"],
        os.getenv("AZURE_SEARCH_INDEX", "thai-people"),
        azure_credential(),
    )
    search_count = 0
    for _ in range(12):
        search_count = search_client.get_document_count()
        if search_count == rows_expected:
            break
        time.sleep(5)
    if search_count != rows_expected:
        raise RuntimeError(f"Expected {rows_expected}; Search has {search_count}")
    return search_count


def check_sql_fuzzy_capability() -> dict[str, int]:
    with sql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT compatibility_level
            FROM sys.databases
            WHERE name = DB_NAME()
            """
        )
        compatibility_level = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT EDIT_DISTANCE_SIMILARITY(
                CAST(N'กิตติกร' AS NVARCHAR(100)) COLLATE Thai_100_CI_AI,
                CAST(N'กิตติกล' AS NVARCHAR(100)) COLLATE Thai_100_CI_AI
            )
            """
        )
        similarity = cursor.fetchone()[0]
        token_payload = json.dumps(
            [{"token": "กิตติ"}, {"token": "กล"}], ensure_ascii=False
        )
        started_at = time.perf_counter()
        cursor.execute(NATIVE_TOKEN_FUZZY_QUERY, (token_payload,))
        native_result = cursor.fetchone()
        query_time_ms = round((time.perf_counter() - started_at) * 1_000)
        if native_result is None:
            raise RuntimeError("Native SQL fuzzy query returned no Thai result")
    return {
        "compatibility_level": compatibility_level,
        "edit_distance_similarity": similarity,
        "native_query_score": int(native_result[4]),
        "native_query_time_ms": query_time_ms,
    }


def check_baseline_fuzzy_query() -> dict[str, int | str]:
    query = "กิตติกล"
    with sql_connection() as connection:
        cursor = connection.cursor()
        started_at = time.perf_counter()
        cursor.execute(
            BASELINE_SQL_FUZZY_QUERY,
            (query, query, query),
        )
        result = cursor.fetchone()
        query_time_ms = round((time.perf_counter() - started_at) * 1_000)
    if result is None:
        raise RuntimeError("Baseline SQL fuzzy query returned no result")
    return {
        "id": result[0],
        "first_name": result[1],
        "score": result[4],
        "query_time_ms": query_time_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=[
            "sql",
            "search",
            "all",
            "verify",
            "sql-capabilities",
            "baseline-fuzzy",
        ],
        default="all",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    if args.target == "sql-capabilities":
        print(json.dumps(check_sql_fuzzy_capability(), ensure_ascii=False))
        return
    if args.target == "baseline-fuzzy":
        print(json.dumps(check_baseline_fuzzy_query(), ensure_ascii=False))
        return

    rows = load_rows()
    if args.target in {"sql", "all"}:
        load_sql(rows)
    if args.target in {"search", "all"}:
        load_search(rows)
    counts = {}
    if args.target in {"sql", "all", "verify"}:
        sql_count, token_count, vocabulary_count = verify_sql(len(rows))
        counts["sql_count"] = sql_count
        counts["sql_token_count"] = token_count
        counts["sql_vocabulary_count"] = vocabulary_count
    if args.target in {"search", "all", "verify"}:
        counts["search_count"] = verify_search(len(rows))
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
