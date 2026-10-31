#!/usr/bin/env python3
"""Capture full-page screenshots with provenance.

    python3 capture_screenshot.py --url https://example.com/docs --name example-docs \
        --subject soc-dashboards --out app/data/reference/screenshots \
        --catalogue app/data/reference/manifest.json

    python3 capture_screenshot.py --targets targets.json --out shots/ --catalogue manifest.json

Requires Playwright and a Chromium build. Neither is installed by this script;
if they are absent it says so and exits rather than reaching for the network.

A target file is JSON: [{"url": "...", "name": "...", "subject": "...",
"wait": "selector", "hide": ["css", ...], "notes": "..."}]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from webres import (
    AcquisitionError,
    Catalogue,
    Provenance,
    USER_AGENT,
    now_iso,
    open_public,
    read_bounded,
    robots_allows,
    sha256_bytes,
    slugify,
    throttle,
    validate_url,
)

# Common consent and chat overlays that otherwise dominate a reference capture.
DEFAULT_HIDE = [
    "#onetrust-consent-sdk",
    ".onetrust-pc-dark-filter",
    "#cookie-banner",
    "[id*='cookie-banner']",
    "[class*='cookie-consent']",
    "[aria-label*='cookie' i]",
    "#drift-widget-container",
    "[id*='intercom']",
]

def fulfill_public(route, *, obey_robots: bool, blocked: list[str]) -> None:
    try:
        request = urllib.request.Request(route.request.url, method=route.request.method,
                                         headers={"User-Agent": USER_AGENT})
        with open_public(request, obey_robots=obey_robots) as response:
            payload = read_bounded(response)
            headers = {key: value for key, value in response.headers.items()
                       if key.lower() not in {"content-length", "transfer-encoding", "connection", "set-cookie"}}
            route.fulfill(status=response.status, headers=headers, body=payload)
    except Exception as exc:
        blocked.append(f"{type(exc).__name__}: {exc}"[:160])
        route.abort()


def capture(targets: list[dict], *, obey_robots: bool = True, executable: str | None = None) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AcquisitionError("Install the declared browser extra and Chromium in an external runtime first") from exc
    results = []
    with sync_playwright() as toolkit:
        browser = toolkit.chromium.launch(**({"executable_path": executable} if executable else {}))
        try:
            for target in targets:
                context = browser.new_context(viewport={"width": target["width"], "height": target["height"]},
                                              device_scale_factor=2, user_agent=USER_AGENT,
                                              service_workers="block", accept_downloads=False)
                blocked = []
                context.route("**/*", lambda route: fulfill_public(route, obey_robots=obey_robots, blocked=blocked))
                context.route_web_socket("**/*", lambda connection: connection.close())
                try:
                    page = context.new_page()
                    response = page.goto(target["url"], wait_until="domcontentloaded", timeout=45000)
                    if response is None or response.status >= 400:
                        raise AcquisitionError("page did not return a successful response")
                    if target.get("wait"):
                        page.wait_for_selector(target["wait"], timeout=8000)
                    page.wait_for_load_state("load", timeout=15000)
                    title = page.title()
                    if any(phrase in title.lower() for phrase in ("404", "not found", "page doesn't exist")):
                        raise AcquisitionError("page title reports missing content")
                    hide = target.get("hide", []) + DEFAULT_HIDE
                    if hide:
                        page.add_style_tag(content="\n".join(f"{selector}{{display:none !important}}" for selector in hide))
                    page.screenshot(path=target["path"], full_page=target.get("fullPage", True), animations="disabled")
                    results.append({"name": target["name"], "ok": True, "title": title,
                                    "status": response.status, "blocked_requests": len(blocked)})
                except Exception as exc:
                    results.append({"name": target["name"], "ok": False, "error": str(exc)[:160],
                                    "blocked_requests": len(blocked)})
                finally:
                    context.close()
        finally:
            browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="single URL to capture")
    source.add_argument("--targets", type=Path, help="JSON file of capture targets")
    parser.add_argument("--name", help="artefact name for a single URL")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path)
    parser.add_argument("--subject", default="uncategorised")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--viewport-only", action="store_true", help="capture the viewport rather than the full page")
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--browser-executable", help="explicit existing Chromium executable; otherwise use Playwright's installed browser")
    args = parser.parse_args()

    if args.targets:
        targets = json.loads(args.targets.read_text(encoding="utf-8"))
    else:
        targets = [{"url": args.url, "name": args.name or slugify(args.url), "subject": args.subject}]

    args.out = args.out.resolve()
    args.catalogue = (args.catalogue or args.out / "manifest.json").resolve()
    catalogue = Catalogue(args.catalogue)
    catalogue.key_for(args.out / "capture.png")
    args.out.mkdir(parents=True, exist_ok=True)

    prepared, skipped = [], []
    for t in targets:
        url = t["url"]
        try:
            parsed = validate_url(url)
        except AcquisitionError as exc:
            print(f"  SKIP  {url}\n        {exc}")
            skipped.append(url)
            continue
        name = slugify(t.get("name") or url)
        t = dict(t)
        t["name"] = name
        t["path"] = str((args.out / f"{name}.png").resolve())
        t.setdefault("width", args.width)
        t.setdefault("height", args.height)
        t["fullPage"] = not args.viewport_only
        prepared.append(t)

    if not prepared:
        print("nothing to capture")
        return 1

    try:
        results = capture(prepared, obey_robots=not args.ignore_robots, executable=args.browser_executable)
    except Exception as exc:
        print(f"capture runtime unavailable: {exc}", file=sys.stderr)
        return 3
    failures = list(skipped)
    for target, result in zip(prepared, results):
        path = Path(target["path"])
        if not result.get("ok") or not path.exists():
            print(f"  FAIL  {target['name']}: {result.get('error', 'no file written')}")
            failures.append(target["name"])
            path.unlink(missing_ok=True)
            continue
        payload = path.read_bytes()
        provenance = Provenance(
            source_url=target["url"],
            retrieved_at=now_iso(),
            status=int(result.get("status") or 200),
            content_type="image/png",
            sha256=sha256_bytes(payload),
            bytes=len(payload),
            title=result.get("title", "")[:200],
            publisher=validate_url(target["url"]).netloc,
            subject=target.get("subject", args.subject),
            function="screenshot",
            notes=f"{target.get('notes', '')}; blocked requests: {result.get('blocked_requests', 0)}; robots override: {args.ignore_robots}",
        )
        provenance.artefact = catalogue.key_for(path)
        if catalogue:
            catalogue.record(provenance)
        print(f"  ok    {path.name}  {len(payload):,}B  {provenance.title[:56]}")

    if catalogue:
        catalogue.save()
        print(f"catalogued {len(catalogue.entries)} artefact(s) -> {args.catalogue}")

    print(f"{len(prepared) - (len(failures) - len(skipped))}/{len(targets)} captured")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
