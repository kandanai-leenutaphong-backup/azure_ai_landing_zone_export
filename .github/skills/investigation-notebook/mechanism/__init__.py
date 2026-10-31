"""Public API for an explicitly located investigation notebook."""

from .notebook import (
    InvestigationNotebook,
    NotebookError,
    SCHEMA_VERSION,
    load_schema,
    main,
    scan_sensitive,
    validate_note,
)

__version__ = "0.1.0"
__all__ = [
    "InvestigationNotebook",
    "NotebookError",
    "SCHEMA_VERSION",
    "load_schema",
    "main",
    "scan_sensitive",
    "validate_note",
]