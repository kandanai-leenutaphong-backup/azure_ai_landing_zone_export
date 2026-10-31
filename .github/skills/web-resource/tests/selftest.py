#!/usr/bin/env python3
"""Offline contract tests for the installed web-resource library.

Runs without network access. Gates the guarantees that make acquisition safe and
the holdings verifiable.

    python3 tests/selftest.py
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
import tempfile
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

LIBRARY_ROOT = Path(__file__).resolve().parent.parent

import webres
from webres import (
    AcquisitionError,
    Catalogue,
    Provenance,
    extract_title,
    sha256_bytes,
    slugify,
    validate_url,
)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{': ' + detail if detail and not condition else ''}")


# --------------------------------------------------------------- URL refusal

REFUSE = [
    ("file:///etc/passwd", "non-web scheme"),
    ("ftp://example.com/x", "non-web scheme"),
    ("javascript:alert(1)", "non-web scheme"),
    ("https://user:pass@example.com/", "embedded credentials"),
    ("https://127.0.0.1/admin", "loopback"),
    ("https://localhost:8765/", "loopback"),
    ("https://10.0.0.1/internal", "private range"),
    ("https://192.168.1.1/", "private range"),
    ("https://169.254.169.254/latest/meta-data/", "link-local metadata endpoint"),
    ("https://", "no host"),
]
def fixture_dns(host, port, **kwargs):
    try:
        address = str(ipaddress.ip_address(host))
    except ValueError:
        address = "127.0.0.1" if host == "localhost" else "8.8.8.8"
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 443))]

with patch.object(socket, "getaddrinfo", side_effect=fixture_dns):
    for url, why in REFUSE:
        try:
            validate_url(url)
            check(f"refuse {why}", False, f"accepted {url}")
        except AcquisitionError:
            check(f"refuse {why}", True)

    for url in ("https://learn.microsoft.com/en-us/azure/", "http://example.com/a?b=c#d"):
        try:
            validate_url(url)
            check(f"accept {url[:38]}", True)
        except AcquisitionError as exc:
            check(f"accept {url[:38]}", False, str(exc))


# ------------------------------------------------------------------- helpers

check("slug lowercases and hyphenates", slugify("Investigate Incidents!") == "investigate-incidents")
check("slug strips repeats", slugify("a---b") == "a-b")
check("slug never empty", slugify("!!!") == "untitled")
check("slug bounded", len(slugify("x" * 500)) <= 60)
check("title extracted", extract_title("<html><title> Hello  World </title>") == "Hello World")
check("title absent is empty", extract_title("<html><body>x</body></html>") == "")
check("hash is stable", sha256_bytes(b"abc") == sha256_bytes(b"abc"))
check("hash discriminates", sha256_bytes(b"abc") != sha256_bytes(b"abd"))


# ----------------------------------------------------------------- catalogue

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    manifest = root / "manifest.json"
    artefact = root / "shots" / "example.png"
    artefact.parent.mkdir(parents=True)
    artefact.write_bytes(b"PNGDATA")

    cat = Catalogue(manifest)
    entry = Provenance(
        source_url="https://example.com/docs",
        retrieved_at="2026-08-31T00:00:00Z",
        status=200,
        content_type="image/png",
        sha256=sha256_bytes(b"PNGDATA"),
        bytes=7,
        subject="soc-dashboards",
        function="screenshot",
        artefact="shots/example.png",
    )
    cat.record(entry)
    cat.save()
    check("catalogue writes", manifest.exists())

    document = json.loads(manifest.read_text())
    check("manifest counts entries", document["count"] == 1, str(document.get("count")))
    check("manifest states usage", "internal reference only" in document["usage"].lower())
    check("entry keeps source url", document["entries"][0]["source_url"] == "https://example.com/docs")

    reloaded = Catalogue(manifest)
    check("catalogue round-trips", len(reloaded.entries) == 1)
    reloaded.record(entry)
    check("re-record replaces not appends", len(reloaded.entries) == 1)

    entry2 = Provenance(
        source_url="", retrieved_at="2026-08-31T00:00:00Z", status=0,
        content_type="image/png", sha256="x", bytes=1,
        subject="observability", function="screenshot", artefact="shots/missing.png",
    )
    reloaded.record(entry2)
    dropped = reloaded.drop_missing(root)
    check("prune drops missing artefacts", dropped == ["shots/missing.png"], str(dropped))
    check("prune keeps present artefacts", "shots/example.png" in reloaded.entries)

    grouped = Catalogue(manifest).by_subject()
    check("grouping by subject works", list(grouped) == ["soc-dashboards"], str(list(grouped)))

    try:
        Catalogue(manifest).record(Provenance(
            source_url="https://x.test/", retrieved_at="", status=200,
            content_type="text/html", sha256="x", bytes=1,
        ))
        check("catalogue demands an artefact path", False, "accepted an entry with no artefact")
    except AcquisitionError:
        check("catalogue demands an artefact path", True)

check("adopted provenance is honest", Provenance(
    source_url="", retrieved_at="", status=0, content_type="", sha256="", bytes=0,
).source_url == "", "adoption must not invent a source URL")


# -------------------------------------------------------------- skill layout

for folder in ("fetch-page", "capture-screenshot", "catalogue"):
    path = LIBRARY_ROOT / "scripts" / folder
    check(f"{folder} exists", path.is_dir())
    check(f"{folder} has a README", (path / "README.md").is_file())
    command = import_module(f"webres.cli.{folder.replace('-', '_')}")
    check(f"{folder} has an installed entry point", callable(command.main))

check("library has canonical guide", (LIBRARY_ROOT / "GUIDE.md").is_file())
check("installed shared library present", Path(webres.__file__).is_file())

collections = [p for p in (LIBRARY_ROOT / "collections").iterdir() if p.is_dir()]
check("at least one collection", len(collections) >= 1)
for collection in collections:
    check(f"collection {collection.name} has a README", (collection / "README.md").is_file())
    targets = collection / "targets.json"
    check(f"collection {collection.name} has targets", targets.is_file())
    if targets.is_file():
        payload = json.loads(targets.read_text())
        check(f"{collection.name} targets are a list", isinstance(payload, list) and bool(payload))
        keys_ok = all({"url", "name", "subject"} <= set(t) for t in payload)
        check(f"{collection.name} targets carry url, name, subject", keys_ok)
        urls_ok = all(t["url"].startswith("https://") for t in payload)
        check(f"{collection.name} targets are https", urls_ok)


# ------------------------------------------------------------------- conduct

guide_text = (LIBRARY_ROOT / "GUIDE.md").read_text(encoding="utf-8").lower()
for phrase, label in (
    ("robots.txt", "robots policy stated"),
    ("rate limit", "rate limiting stated"),
    ("paywall", "access-control policy stated"),
    ("internal reference only", "ownership policy stated"),
):
    check(label, phrase in guide_text)

library_text = Path(webres.__file__).read_text(encoding="utf-8")
check("politeness floor is enforced in code", "MIN_INTERVAL_SECONDS" in library_text)
check("user agent does not impersonate", "Mozilla" not in library_text)


for line in FAILED:
    print(f"FAIL {line}")
print(f"{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed")
sys.exit(1 if FAILED else 0)
