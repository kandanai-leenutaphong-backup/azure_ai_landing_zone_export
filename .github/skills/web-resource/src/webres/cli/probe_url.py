#!/usr/bin/env python3
"""Probe URLs for reachability without downloading their bodies.

    python3 probe_url.py --url https://example.com/big.tar.gz --subject attack-telemetry-datasets \
        --out research/probes --catalogue research/manifest.json

    python3 probe_url.py --urls targets.txt --subject attack-telemetry-datasets --out research/probes

Answers "does this download link still resolve, how large is it, and does it
redirect to a login" without pulling the payload. HEAD is tried first; servers
that refuse HEAD are retried with a one-byte ranged GET. Results are written as
a single JSON artefact and catalogued like any other acquisition.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from webres import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    AcquisitionError,
    Catalogue,
    Provenance,
    now_iso,
    open_public,
    robots_allows,
    sha256_bytes,
    slugify,
    throttle,
    validate_url,
)

# Statuses that mean "this server dislikes HEAD", not "this resource is absent".
_HEAD_UNSUPPORTED = {405, 501}


def _request(url: str, method: str, timeout: int, extra: dict[str, str] | None = None, *, obey_robots: bool = True) -> dict[str, object]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Language": "en"}
    headers.update(extra or {})
    request = urllib.request.Request(url, headers=headers, method=method)
    with open_public(request, timeout=timeout, obey_robots=obey_robots) as response:
        if method == "GET":
            response.read(1)
        return {
            "status": response.status,
            "final_url": response.url,
            "content_type": response.headers.get("Content-Type", ""),
            "content_length": response.headers.get("Content-Length", ""),
            "content_range": response.headers.get("Content-Range", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
            "method": method,
        }


def probe(url: str, *, timeout: int = DEFAULT_TIMEOUT, obey_robots: bool = True) -> dict[str, object]:
    """Return a reachability record for ``url``. Never raises for HTTP failure."""
    record: dict[str, object] = {"url": url, "checked_at": now_iso()}
    try:
        parsed = validate_url(url)
    except AcquisitionError as exc:
        return {**record, "outcome": "refused", "detail": str(exc)}

    for method, extra in (("HEAD", None), ("GET", {"Range": "bytes=0-0"})):
        try:
            result = _request(url, method, timeout, extra, obey_robots=obey_robots)
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in _HEAD_UNSUPPORTED:
                continue
            return {
                **record,
                "outcome": "http-error",
                "status": exc.code,
                "detail": exc.reason if isinstance(exc.reason, str) else str(exc.reason),
                "method": method,
            }
        except AcquisitionError as exc:
            return {**record, "outcome": "refused", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - DNS, TLS, and timeouts are all "did not resolve"
            if method == "HEAD":
                continue
            return {**record, "outcome": "unreachable", "detail": f"{type(exc).__name__}: {exc}"}
        else:
            redirected = result["final_url"] != url
            return {**record, "outcome": "ok", "redirected": redirected, **result}

    return {**record, "outcome": "unreachable", "detail": "HEAD and ranged GET both failed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", action="append", default=[], help="a URL to probe; repeatable")
    source.add_argument("--urls", type=Path, help="file of URLs, one per line, # comments allowed")
    parser.add_argument("--out", type=Path, required=True, help="directory to write the results artefact into")
    parser.add_argument("--name", default="", help="artefact stem; defaults to the subject")
    parser.add_argument("--catalogue", type=Path, help="manifest JSON to record provenance in")
    parser.add_argument("--subject", default="uncategorised", help="subject tag for the catalogue")
    parser.add_argument("--ignore-robots", action="store_true", help="skip the robots.txt check; use only with permission")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    urls = list(args.url)
    if args.urls:
        urls += [
            line.strip()
            for line in args.urls.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not urls:
        print("no URLs supplied", file=sys.stderr)
        return 2

    results = []
    unreached = 0
    for url in urls:
        record = probe(url, timeout=args.timeout, obey_robots=not args.ignore_robots)
        results.append(record)
        outcome = str(record.get("outcome"))
        status = record.get("status", "-")
        size = record.get("content_length") or record.get("content_range") or ""
        if outcome != "ok":
            unreached += 1
        print(f"  {outcome:<18} {str(status):<5} {str(size):<16} {url}")
        if record.get("redirected"):
            print(f"                     -> {record.get('final_url')}")

    args.out = args.out.resolve()
    args.catalogue = (args.catalogue or args.out / "manifest.json").resolve()
    Catalogue(args.catalogue).key_for(args.out / "probe.json")
    args.out.mkdir(parents=True, exist_ok=True)
    stem = slugify(args.name or args.subject)
    target = args.out / f"{stem}-probe.json"
    payload = json.dumps({"generated": now_iso(), "count": len(results), "results": results}, indent=2) + "\n"
    target.write_text(payload, encoding="utf-8")

    if args.catalogue:
        catalogue = Catalogue(args.catalogue)
        root = args.catalogue.parent
        provenance = Provenance(
            source_url="(multiple; see results)",
            retrieved_at=now_iso(),
            status=200,
            content_type="application/json",
            sha256=sha256_bytes(payload.encode("utf-8")),
            bytes=len(payload.encode("utf-8")),
            title=f"URL reachability probe: {args.subject}",
            publisher="harness web-resource toolkit",
            subject=args.subject,
            function="url-probe",
            notes=f"{len(results) - unreached}/{len(results)} reachable",
        )
        provenance.artefact = catalogue.key_for(target)
        catalogue.record(provenance)
        catalogue.save()
        print(f"catalogued {len(catalogue.entries)} artefact(s) -> {args.catalogue}")

    print(f"{len(results) - unreached}/{len(results)} reachable -> {target}")
    return 1 if unreached else 0


if __name__ == "__main__":
    sys.exit(main())
