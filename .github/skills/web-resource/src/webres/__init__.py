"""Shared machinery for web resource acquisition.

Every acquisition adapter goes through here so that politeness, provenance, and
cataloguing are properties of the toolkit rather than things each script
remembers to do.

Guarantees:

* **robots.txt is consulted** before any fetch, and a disallow is fatal.
* **Per-host rate limiting** with a configurable floor between requests.
* **Provenance is recorded** for every artefact: source URL, retrieval time,
  content hash, status, and the fact that third-party material is held for
  internal reference only.
* **Only public HTTP(S)** is reachable. Credentialed URLs, non-web schemes, and
  private address literals are refused before a socket opens.

Standard library only.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Identifies the toolkit honestly rather than impersonating a browser.
USER_AGENT = "harness-web-resource/1.0 (public reference acquisition)"

# Floor between requests to one host. Politeness, not throughput.
MIN_INTERVAL_SECONDS = 2.0

DEFAULT_TIMEOUT = 30
MAX_RESPONSE_BYTES = 16 * 1024 * 1024

_last_request: dict[str, float] = {}
_robots_cache: dict[object, Any] = {}
_crawl_delays: dict[str, float] = {}
_rate_lock = threading.Lock()


class AcquisitionError(RuntimeError):
    """A fetch was refused, blocked, or failed."""


class RobotsDisallowed(AcquisitionError):
    """robots.txt forbids this path for our user agent."""


# --------------------------------------------------------------------- guards


def public_addresses(host: str, port: int = 443) -> list[str]:
    """Resolve once and reject the whole answer if any address is not public unicast."""
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, ValueError) as exc:
        raise AcquisitionError("host could not be resolved safely") from exc
    addresses = []
    for info in answers:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise AcquisitionError("refusing private or non-unicast address")
        addresses.append(str(address))
    if not addresses:
        raise AcquisitionError("host resolved to no public addresses")
    return addresses


def validate_url(url: str) -> urllib.parse.ParseResult:
    """Return the parsed URL if it is safe to request, else raise.

    Refuses non-web schemes, embedded credentials, and private address space, so
    the toolkit cannot be pointed at internal services.
    """
    if not isinstance(url, str) or not url or len(url) > 8192 or any(character.isspace() for character in url):
        raise AcquisitionError("invalid URL")
    try:
        parsed = urllib.parse.urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise AcquisitionError("invalid URL host or port") from exc
    if parsed.scheme not in {"http", "https"}:
        raise AcquisitionError(f"refusing non-web scheme {parsed.scheme!r}: {url}")
    if not parsed.hostname:
        raise AcquisitionError(f"URL has no host: {url}")
    if parsed.username is not None or parsed.password is not None:
        raise AcquisitionError("refusing URL carrying credentials")
    public_addresses(parsed.hostname, port or (443 if parsed.scheme == "https" else 80))
    return parsed


class PublicHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        if self._tunnel_host:
            raise AcquisitionError("proxy tunnels are not supported")
        addresses = public_addresses(self.host, self.port)
        self.sock = socket.create_connection((addresses[0], self.port), self.timeout, self.source_address)


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self) -> None:
        PublicHTTPConnection.connect(self)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, request):
        return self.do_open(PublicHTTPConnection, request)


class PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(PublicHTTPSConnection, request, context=self._context)


class GuardedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, obey_robots: bool = True, deadline: float | None = None,
                 robots_parser: Callable[[str], Any] | None = None) -> None:
        self.obey_robots = obey_robots
        self.deadline = deadline
        self.robots_parser = robots_parser

    def redirect_request(self, request, response, code, message, headers, new_url):
        parsed = validate_url(new_url)
        if self.obey_robots and not robots_allows(new_url, deadline=self.deadline, robots_parser=self.robots_parser):
            raise RobotsDisallowed("redirect target is disallowed by robots.txt")
        throttle(parsed.hostname, deadline=self.deadline)
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("acquisition deadline exceeded")
            request.timeout = min(request.timeout, remaining)
        return super().redirect_request(request, response, code, message, headers, new_url)


def open_public(request, *, timeout: float = DEFAULT_TIMEOUT, obey_robots: bool = True,
                deadline: float | None = None, robots_parser: Callable[[str], Any] | None = None):
    if deadline is not None and deadline <= time.monotonic():
        raise TimeoutError("acquisition deadline exceeded")
    if isinstance(request, str):
        request = urllib.request.Request(request, headers={"User-Agent": USER_AGENT})
    parsed = validate_url(request.full_url)
    if request.get_method() not in {"GET", "HEAD"}:
        raise AcquisitionError("only GET and HEAD acquisition is supported")
    if not 0 < timeout <= 120:
        raise AcquisitionError("timeout must be between 0 and 120 seconds")
    if obey_robots and not robots_allows(request.full_url, deadline=deadline, robots_parser=robots_parser):
        raise RobotsDisallowed("robots.txt disallows acquisition")
    throttle(parsed.hostname, deadline=deadline)
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("acquisition deadline exceeded")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicHTTPHandler(),
                                        PublicHTTPSHandler(), GuardedRedirects(obey_robots, deadline, robots_parser))
    return opener.open(request, timeout=timeout)


def read_bounded(response) -> bytes:
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise AcquisitionError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
    return payload


def robots_allows(url: str, *, user_agent: str = USER_AGENT, deadline: float | None = None,
                  robots_parser: Callable[[str], Any] | None = None) -> bool:
    """Consult robots.txt; missing permits, denied or unreachable refuses."""
    parsed = validate_url(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    cache_key = (origin, robots_parser) if robots_parser is not None else origin
    if cache_key not in _robots_cache:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        try:
            request = urllib.request.Request(f"{origin}/robots.txt", headers={"User-Agent": user_agent})
            with open_public(request, timeout=15, obey_robots=False, deadline=deadline) as response:
                text = read_bounded(response).decode("utf-8", errors="replace")
                if robots_parser is not None:
                    parser = robots_parser(text)
                else:
                    parser.parse(text.splitlines())
            _robots_cache[cache_key] = parser
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 410}:
                return False
            _robots_cache[cache_key] = None
        except (OSError, AcquisitionError):
            return False
    parser = _robots_cache[cache_key]
    if parser is not None:
        delay = parser.crawl_delay(user_agent) or 0
        rate = parser.request_rate(user_agent)
        if rate is not None and rate.requests > 0:
            delay = max(delay, rate.seconds / rate.requests)
        _crawl_delays[parsed.hostname] = max(_crawl_delays.get(parsed.hostname, 0), delay)
    return True if parser is None else parser.can_fetch(user_agent, url)


def throttle(host: str, minimum: float = MIN_INTERVAL_SECONDS, *, deadline: float | None = None) -> None:
    """Sleep so that consecutive requests to ``host`` are at least ``minimum`` apart."""
    with _rate_lock:
        minimum = max(MIN_INTERVAL_SECONDS, _crawl_delays.get(host, 0), minimum)
        now = time.monotonic()
        previous = _last_request.get(host)
        scheduled = max(now, previous + minimum) if previous is not None else now
        if deadline is not None and scheduled >= deadline:
            raise TimeoutError("per-host request delay exceeds acquisition deadline")
        _last_request[host] = scheduled
        wait = scheduled - now
    if wait > 0:
        time.sleep(wait)


# --------------------------------------------------------------------- fetch


@dataclass(slots=True)
class Provenance:
    """Where an artefact came from and what it is."""

    source_url: str
    retrieved_at: str
    status: int
    content_type: str
    sha256: str
    bytes: int
    title: str = ""
    publisher: str = ""
    subject: str = ""
    function: str = ""
    artefact: str = ""
    # Third-party pages and images remain owned by their publishers.
    usage: str = "internal reference only; third-party content remains the property of its publisher"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def extract_title(html: str) -> str:
    match = _TITLE.search(html)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()[:200]


def fetch(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    obey_robots: bool = True,
    accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
) -> tuple[bytes, Provenance]:
    """Fetch ``url`` politely, returning its bytes and a provenance record."""
    parsed = validate_url(url)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "en"},
    )
    try:
        with open_public(request, timeout=timeout, obey_robots=obey_robots) as response:
            payload = read_bounded(response)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise AcquisitionError(f"HTTP {exc.code} for {url}") from exc
    except AcquisitionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AcquisitionError(f"fetch failed for {url}: {exc}") from exc

    title = ""
    if "html" in content_type.lower():
        title = extract_title(payload.decode("utf-8", errors="replace"))

    return payload, Provenance(
        source_url=url,
        retrieved_at=now_iso(),
        status=status,
        content_type=content_type,
        sha256=sha256_bytes(payload),
        bytes=len(payload),
        title=title,
        publisher=parsed.netloc,
    )


# ----------------------------------------------------------------- catalogue


def slugify(value: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "untitled"


class Catalogue:
    """A manifest of acquired artefacts, keyed by artefact path.

    Re-recording the same artefact replaces its entry rather than appending, so
    the manifest stays a statement of current holdings.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.entries: dict[str, dict[str, object]] = {}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(loaded.get("entries"), list):
                raise AcquisitionError("invalid provenance catalogue")
            for entry in loaded["entries"]:
                if not isinstance(entry, dict) or not isinstance(entry.get("artefact"), str):
                    raise AcquisitionError("invalid provenance entry")
                self.artefact_path(entry["artefact"])
                if entry["artefact"] in self.entries:
                    raise AcquisitionError("duplicate provenance entry")
                self.entries[entry["artefact"]] = entry

    def artefact_path(self, key: str) -> Path:
        relative = Path(key)
        if not key or relative.is_absolute() or ".." in relative.parts or "\\" in key:
            raise AcquisitionError("artefact path must stay beneath the catalogue directory")
        resolved = (self.path.parent / relative).resolve()
        if not resolved.is_relative_to(self.path.parent):
            raise AcquisitionError("artefact symlink escapes the catalogue directory")
        return resolved

    def key_for(self, path: Path) -> str:
        try:
            key = path.resolve().relative_to(self.path.parent).as_posix()
        except ValueError as exc:
            raise AcquisitionError("output must stay beneath the catalogue directory") from exc
        self.artefact_path(key)
        return key

    def record(self, provenance: Provenance) -> None:
        if not provenance.artefact:
            raise AcquisitionError("provenance needs an artefact path before it can be catalogued")
        self.artefact_path(provenance.artefact)
        self.entries[provenance.artefact] = provenance.to_dict()

    def drop_missing(self, root: Path) -> list[str]:
        """Remove entries whose artefact no longer exists. Returns the dropped keys."""
        if root.resolve() != self.path.parent:
            raise AcquisitionError("prune root must equal the catalogue directory")
        gone = [key for key in self.entries if not self.artefact_path(key).exists()]
        for key in gone:
            del self.entries[key]
        return gone

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "generated": now_iso(),
            "count": len(self.entries),
            "usage": "Third-party material held for internal reference only. Do not redistribute.",
            "entries": sorted(self.entries.values(), key=lambda e: (e.get("subject", ""), e.get("artefact", ""))),
        }
        self.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def by_subject(self) -> dict[str, list[dict[str, object]]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for entry in self.entries.values():
            grouped.setdefault(str(entry.get("subject", "uncategorised")), []).append(entry)
        return grouped
