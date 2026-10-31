"""White-box tests for the optimizer's private evidence reader.

The point under test is that a hostile or careless SQL string cannot write, cannot reach the
label database, cannot reach SQLite's own catalogue, and cannot run forever.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_optimization import (
    LocalQueryError,
    QueryDenied,
    QueryTimeout,
    SQLiteReader,
)


@pytest.fixture()
def source_db(tmp_path: Path) -> Path:
    path = tmp_path / "source.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE cases (case_id TEXT PRIMARY KEY, org_id TEXT, split TEXT);
        CREATE TABLE evidence (case_id TEXT, category TEXT, entity_type TEXT);
        CREATE TABLE training_profile (feature TEXT, value TEXT, support INTEGER);
        CREATE TABLE labels (case_id TEXT PRIMARY KEY, incident_grade TEXT);
        """
    )
    connection.executemany(
        "INSERT INTO cases VALUES (?, ?, ?)",
        [(f"case{index:02d}", str(index), "development") for index in range(10)],
    )
    connection.executemany(
        "INSERT INTO evidence VALUES (?, ?, ?)",
        [(f"case{index // 3:02d}", "InitialAccess", "Ip") for index in range(30)],
    )
    connection.execute("INSERT INTO training_profile VALUES ('category', 'InitialAccess', 7)")
    connection.execute("INSERT INTO labels VALUES ('case00', 'TruePositive')")
    connection.commit()
    connection.close()
    return path


def test_select_returns_columns_and_rows(source_db: Path) -> None:
    result = SQLiteReader(source_db).query("SELECT case_id, org_id FROM cases ORDER BY case_id")
    assert result["columns"] == ["case_id", "org_id"]
    assert result["rows"][0] == ["case00", "0"]
    assert result["truncated"] is False
    assert result["elapsed_ms"] >= 0.0


def test_named_parameters_are_bound_not_interpolated(source_db: Path) -> None:
    result = SQLiteReader(source_db).query(
        "SELECT count(*) FROM evidence WHERE case_id = :case_id",
        {"case_id": "case00"},
    )
    assert result["rows"] == [[3]]


def test_max_rows_truncates_and_reports_it(source_db: Path) -> None:
    result = SQLiteReader(source_db).query("SELECT case_id FROM cases", max_rows=4)
    assert len(result["rows"]) == 4
    assert result["truncated"] is True


def test_max_rows_exactly_at_the_bound_is_not_truncated(source_db: Path) -> None:
    result = SQLiteReader(source_db).query("SELECT case_id FROM cases", max_rows=10)
    assert len(result["rows"]) == 10
    assert result["truncated"] is False


def test_aggregate_and_join_across_permitted_tables(source_db: Path) -> None:
    result = SQLiteReader(source_db).query(
        """
        SELECT c.split, count(DISTINCT e.case_id) AS cases
        FROM cases c JOIN evidence e ON e.case_id = c.case_id
        GROUP BY c.split
        """
    )
    assert result["rows"] == [["development", 10]]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO cases VALUES ('x', 'y', 'z')",
        "UPDATE cases SET org_id = '9'",
        "DELETE FROM evidence",
        "DROP TABLE evidence",
        "CREATE TABLE sneak (a TEXT)",
        "ALTER TABLE cases ADD COLUMN extra TEXT",
        "CREATE INDEX ix ON evidence(case_id)",
    ],
)
def test_writes_and_ddl_are_denied(source_db: Path, sql: str) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query(sql)


def test_no_write_reaches_the_file(source_db: Path) -> None:
    before = source_db.stat().st_mtime_ns
    with pytest.raises(LocalQueryError):
        SQLiteReader(source_db).query("INSERT INTO cases VALUES ('x', 'y', 'z')")
    connection = sqlite3.connect(source_db)
    remaining = connection.execute("SELECT count(*) FROM cases").fetchone()[0]
    connection.close()
    assert remaining == 10
    assert source_db.stat().st_mtime_ns == before


def test_pragma_is_denied(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("PRAGMA table_info(evidence)")


def test_attach_is_denied(source_db: Path, tmp_path: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query(
            f"ATTACH DATABASE '{tmp_path / 'other.sqlite'}' AS other"
        )


def test_load_extension_is_denied(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT load_extension('/tmp/evil.so')")


def test_unlisted_function_is_denied(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT randomblob(16)")


def test_label_table_is_denied_directly(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT incident_grade FROM labels")


def test_label_table_is_denied_without_a_column_read(source_db: Path) -> None:
    # count(*) reads no column, so the table must be refused on the table read alone.
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT count(*) FROM labels")


def test_unlisted_table_is_denied_without_a_column_read(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT count(*) FROM cases", tables={"evidence"})


def test_label_table_is_denied_inside_a_nested_select(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query(
            "SELECT case_id FROM cases WHERE case_id IN (SELECT case_id FROM labels)"
        )


def test_label_table_is_denied_inside_a_cte(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query(
            "WITH leak AS (SELECT case_id FROM labels) SELECT * FROM leak"
        )


def test_system_catalogue_is_denied(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT name FROM sqlite_master")


def test_tables_argument_narrows_the_readable_set(source_db: Path) -> None:
    reader = SQLiteReader(source_db)
    allowed = reader.query(
        "SELECT count(*) FROM evidence", tables={"evidence", "training_profile"}
    )
    assert allowed["rows"] == [[30]]
    with pytest.raises(QueryDenied):
        reader.query("SELECT count(*) FROM cases", tables={"evidence", "training_profile"})


def test_tables_argument_cannot_widen_to_labels(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT * FROM labels", tables={"labels"})


def test_construction_policy_is_copied_and_requests_only_narrow(source_db: Path) -> None:
    policy = {"evidence"}
    reader = SQLiteReader(source_db, allowed_tables=policy)
    policy.add("cases")
    assert reader.query("SELECT count(*) FROM evidence")["rows"] == [[30]]
    with pytest.raises(QueryDenied):
        reader.query("SELECT count(*) FROM cases", tables={"cases"})
    with pytest.raises(QueryDenied):
        reader.query("SELECT count(*) FROM cases")


def test_trusted_construction_supports_domain_neutral_tables(source_db: Path) -> None:
    with sqlite3.connect(source_db) as connection:
        connection.execute("CREATE TABLE observations (value INTEGER)")
        connection.execute("INSERT INTO observations VALUES (7)")
    reader = SQLiteReader(source_db, allowed_tables={"observations"})
    assert reader.query("SELECT value FROM observations")["rows"] == [[7]]
    with pytest.raises(QueryDenied):
        reader.query("SELECT * FROM labels", tables={"observations", "labels"})


@pytest.mark.parametrize("table", ["labels", "LaBeLs", "sqlite_master", "SQLITE_SCHEMA"])
def test_construction_policy_cannot_expose_labels_or_catalogue(source_db: Path, table: str) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db, allowed_tables={table})


@pytest.mark.parametrize("policy", [[], [""], [None], "evidence"])
def test_construction_policy_requires_explicit_table_names(source_db: Path, policy) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db, allowed_tables=policy)


def test_multiple_statements_are_refused(source_db: Path) -> None:
    with pytest.raises(QueryDenied, match="multiple statements"):
        SQLiteReader(source_db).query("SELECT 1 FROM cases; DROP TABLE cases")


def test_trailing_semicolon_is_accepted(source_db: Path) -> None:
    result = SQLiteReader(source_db).query("SELECT count(*) FROM cases;")
    assert result["rows"] == [[10]]


def test_semicolon_inside_a_literal_is_not_a_separator(source_db: Path) -> None:
    result = SQLiteReader(source_db).query("SELECT count(*) FROM cases WHERE org_id = 'a;b'")
    assert result["rows"] == [[0]]


def test_empty_statement_is_refused(source_db: Path) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("   ")


@pytest.mark.parametrize("kwargs", [{"max_rows": 0}, {"max_rows": True}, {"max_rows": 1.5},
                                    {"timeout_seconds": 0}, {"timeout_seconds": True},
                                    {"timeout_seconds": float("nan")}, {"timeout_seconds": float("inf")}])
def test_invalid_bounds_are_refused(source_db: Path, kwargs: dict) -> None:
    with pytest.raises(QueryDenied):
        SQLiteReader(source_db).query("SELECT 1 FROM cases", **kwargs)


def test_database_uri_preserves_reserved_path_characters(source_db: Path) -> None:
    renamed = source_db.with_name("evidence?#.sqlite")
    source_db.rename(renamed)
    assert SQLiteReader(renamed).query("SELECT count(*) FROM evidence")["rows"] == [[30]]


def test_missing_database_is_reported(tmp_path: Path) -> None:
    with pytest.raises(LocalQueryError):
        SQLiteReader(tmp_path / "absent.sqlite").query("SELECT 1 FROM cases")


def test_syntax_error_is_a_local_query_error(source_db: Path) -> None:
    with pytest.raises(LocalQueryError):
        SQLiteReader(source_db).query("SELECT FROM WHERE cases")


def test_deadline_aborts_a_runaway_query(source_db: Path) -> None:
    with pytest.raises(QueryTimeout):
        SQLiteReader(source_db).query(
            """
            WITH RECURSIVE burn(n) AS (
                SELECT 1 UNION ALL SELECT n + 1 FROM burn WHERE n < 200000000
            )
            SELECT count(*) FROM burn
            """,
            timeout_seconds=0.25,
        )
