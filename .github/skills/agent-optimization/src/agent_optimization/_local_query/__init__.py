"""Read-only SQL access to a local SQLite file, enforced by SQLite's own authorizer."""

from .reader import (
    ALLOWED_FUNCTIONS,
    DEFAULT_ALLOWED_TABLES,
    LocalQueryError,
    QueryDenied,
    QueryTimeout,
    SQLiteReader,
)

__all__ = [
    "SQLiteReader",
    "LocalQueryError",
    "QueryDenied",
    "QueryTimeout",
    "DEFAULT_ALLOWED_TABLES",
    "ALLOWED_FUNCTIONS",
]
