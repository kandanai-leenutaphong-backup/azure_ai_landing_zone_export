"""Read-only SQLite query surface.

The security boundary is SQLite's own authorizer callback, not string inspection of the SQL:
the connection is opened `mode=ro`, every authorizer action other than an approved read is
refused, and the statement is aborted from a progress handler once its deadline passes.
"""

from __future__ import annotations

import sqlite3
import time
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "SQLiteReader",
    "LocalQueryError",
    "QueryDenied",
    "QueryTimeout",
    "DEFAULT_ALLOWED_TABLES",
    "ALLOWED_FUNCTIONS",
]


class LocalQueryError(Exception):
    """Base class for every refusal this module raises."""


class QueryDenied(LocalQueryError):
    """The statement was refused before or during execution."""


class QueryTimeout(LocalQueryError):
    """The statement exceeded its deadline and was aborted."""


DEFAULT_ALLOWED_TABLES = frozenset({"evidence", "cases", "training_profile"})

# Never readable through this surface, whatever the caller passes as `tables`.
_FORBIDDEN_TABLES = frozenset({"labels"})

ALLOWED_FUNCTIONS = frozenset(
    {
        "abs", "avg", "cast", "char", "coalesce", "count", "date", "datetime",
        "format", "group_concat", "hex", "ifnull", "iif", "instr", "julianday",
        "length", "like", "lower", "ltrim", "max", "min", "nullif", "printf",
        "quote", "replace", "round", "rtrim", "sign", "strftime", "substr",
        "substring", "sum", "total", "trim", "typeof", "unicode", "unixepoch",
        "upper",
    }
)

# Authorizer actions that a read-only query legitimately needs. Everything else is denied,
# which covers INSERT/UPDATE/DELETE/DROP/CREATE/ALTER, PRAGMA, ATTACH, DETACH,
# TRANSACTION and load_extension without enumerating them.
_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
)


def _split_points(sql: str) -> int:
    """Count statement separators outside string literals, identifiers and comments."""
    count = 0
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        if char in ("'", '"', "`"):
            closing = char
            index += 1
            while index < length:
                if sql[index] == closing:
                    if index + 1 < length and sql[index + 1] == closing:
                        index += 2
                        continue
                    break
                index += 1
        elif char == "[":
            while index < length and sql[index] != "]":
                index += 1
        elif char == "-" and sql.startswith("--", index):
            while index < length and sql[index] != "\n":
                index += 1
        elif char == "/" and sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            index = length if end == -1 else end + 1
        elif char == ";":
            count += 1
        index += 1
    return count


class SQLiteReader:
    """Answers read-only SQL against one SQLite file.

    The caller supplies the path; nothing here reads the environment.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        allowed_tables: Iterable[str] = DEFAULT_ALLOWED_TABLES,
    ) -> None:
        self._path = Path(path)
        if isinstance(allowed_tables, (str, bytes)):
            raise QueryDenied("allowed_tables must be a collection of table names")
        names = tuple(allowed_tables)
        if not names or any(not isinstance(name, str) or not name for name in names):
            raise QueryDenied("allowed_tables must contain nonempty table names")
        self._allowed_tables = frozenset(name.lower() for name in names)
        if any(
            name in _FORBIDDEN_TABLES or name.startswith("sqlite_")
            for name in self._allowed_tables
        ):
            raise QueryDenied("labels and SQLite catalogue tables are never readable")

    @property
    def path(self) -> Path:
        return self._path

    def query(
        self,
        sql: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        max_rows: int = 200,
        timeout_seconds: float = 5.0,
        tables: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(sql, str) or not sql.strip():
            raise QueryDenied("empty statement")
        if type(max_rows) is not int or max_rows < 1:
            raise QueryDenied("max_rows must be at least 1")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise QueryDenied("timeout_seconds must be finite and positive")

        trimmed = sql.strip().rstrip(";").strip()
        if _split_points(trimmed) > 0:
            raise QueryDenied("multiple statements are not permitted")
        if not trimmed:
            raise QueryDenied("empty statement")

        if tables is None:
            allowed = set(self._allowed_tables)
        else:
            requested = {str(name).lower() for name in tables}
            unknown = requested - self._allowed_tables
            if unknown:
                raise QueryDenied(f"table not readable: {sorted(unknown)[0]}")
            allowed = requested
        allowed -= _FORBIDDEN_TABLES
        if not allowed:
            raise QueryDenied("no readable table selected")

        if not self._path.exists():
            raise LocalQueryError(f"database not found: {self._path}")

        uri = self._path.resolve().as_uri() + "?mode=ro"
        # A read of a real table and a read of a CTE alias reach the authorizer with the same
        # arguments, so the catalogue is what tells them apart. Read it before the authorizer
        # is installed; afterwards sqlite_master is itself unreadable.
        catalogue = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
        try:
            known_objects = {
                str(row[0]).lower()
                for row in catalogue.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
        finally:
            catalogue.close()

        denials: list[str] = []

        def authorizer(action: int, arg1, arg2, dbname, trigger) -> int:
            if action not in _ALLOWED_ACTIONS:
                denials.append(f"operation not permitted (action {action})")
                return sqlite3.SQLITE_DENY
            if dbname not in (None, "main"):
                denials.append(f"database not readable: {dbname}")
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION:
                name = (arg2 or "").lower()
                if name not in ALLOWED_FUNCTIONS:
                    denials.append(f"function not permitted: {arg2}")
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
                return sqlite3.SQLITE_OK
            name = (arg1 or "").lower()
            if name.startswith("sqlite_") or name in _FORBIDDEN_TABLES:
                denials.append(f"table not readable: {arg1}")
                return sqlite3.SQLITE_DENY
            if name in known_objects and name not in allowed:
                denials.append(f"table not readable: {arg1}")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        started = time.monotonic()
        deadline = started + timeout_seconds
        connection = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
        try:
            connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
            connection.set_authorizer(authorizer)
            try:
                cursor = connection.execute(trimmed, dict(parameters or {}))
                fetched = cursor.fetchmany(max_rows + 1)
            except sqlite3.OperationalError as error:
                if denials:
                    raise QueryDenied(denials[0]) from error
                if time.monotonic() > deadline or "interrupted" in str(error).lower():
                    raise QueryTimeout(
                        f"query exceeded {timeout_seconds:g}s deadline"
                    ) from error
                raise LocalQueryError(str(error)) from error
            except sqlite3.DatabaseError as error:
                if denials:
                    raise QueryDenied(denials[0]) from error
                raise LocalQueryError(str(error)) from error
            columns = [description[0] for description in (cursor.description or [])]
            truncated = len(fetched) > max_rows
            rows = [list(row) for row in fetched[:max_rows]]
        finally:
            connection.set_authorizer(None)
            connection.set_progress_handler(None, 0)
            connection.close()

        return {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "elapsed_ms": round((time.monotonic() - started) * 1000.0, 3),
        }
