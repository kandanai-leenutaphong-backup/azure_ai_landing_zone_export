"""appcompose — a human-authored document, composed into a running application.

One import, one call site:

    from appcompose import allowlist, compose, from_yaml

    document = from_yaml(text)
    app = compose(document, resolve=allowlist({"notes.store": build_notes}))

Everything else in this namespace is the vocabulary those two lines use: the
document types, the neutral contribution types, and the refusals.
"""

from __future__ import annotations

from appcompose.asgi import DEFAULT_MAX_REQUEST_BYTES, asgi_app
from appcompose.compose import (
    Asset,
    ComposedMember,
    Composition,
    Contribution,
    MAX_ROUTE_PARAMS,
    METADATA_KEYS,
    METHODS,
    Request,
    Response,
    Route,
    allowlist,
    compose,
    route_template_error,
)
from appcompose.document import (
    KIND,
    MAX_DOCUMENT_DEPTH,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    Document,
    Member,
    Placement,
    parse,
    plain,
    to_mapping,
)
from appcompose.errors import (
    AssetConflict,
    CapabilityFactoryFailed,
    CapabilityNotAllowed,
    CompositionError,
    CredentialShaped,
    DocumentInvalid,
    PartialStartup,
    ResponseInvalid,
    RouteConflict,
    ShutdownFailed,
    StartupFailed,
    UnknownMetadata,
    UnsupportedVersion,
)
from appcompose.serialisation import (
    MAX_DOCUMENT_BYTES,
    MAX_NESTING_DEPTH,
    canonical_json,
    from_json,
    from_yaml,
    to_yaml,
)

__version__ = "1.1.0"

__all__ = [
    "Asset",
    "AssetConflict",
    "CapabilityFactoryFailed",
    "CapabilityNotAllowed",
    "ComposedMember",
    "Composition",
    "CompositionError",
    "Contribution",
    "CredentialShaped",
    "DEFAULT_MAX_REQUEST_BYTES",
    "Document",
    "DocumentInvalid",
    "KIND",
    "MAX_DOCUMENT_BYTES",
    "MAX_DOCUMENT_DEPTH",
    "MAX_NESTING_DEPTH",
    "MAX_ROUTE_PARAMS",
    "METADATA_KEYS",
    "METHODS",
    "Member",
    "PartialStartup",
    "Placement",
    "Request",
    "Response",
    "ResponseInvalid",
    "Route",
    "RouteConflict",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "ShutdownFailed",
    "StartupFailed",
    "UnknownMetadata",
    "UnsupportedVersion",
    "allowlist",
    "asgi_app",
    "canonical_json",
    "compose",
    "from_json",
    "from_yaml",
    "parse",
    "plain",
    "route_template_error",
    "to_mapping",
    "to_yaml",
]
