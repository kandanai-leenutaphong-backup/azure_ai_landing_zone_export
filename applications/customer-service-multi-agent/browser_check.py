"""Local Chrome proof. Test-only SDK interception, signed JWT, no cloud/inference."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import socket
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlparse

import uvicorn
from playwright.sync_api import sync_playwright
from app import create_app
from auth import EntraAuth
from telemetry import LOGGER
from test_app import TENANT, AUDIENCE, USER, FakeAgents, settings, signing, token


ROOT = Path(__file__).resolve().parent
SCOPE = f"api://{AUDIENCE}/access_as_user"
CLIENT = "722e2f80-ccb1-4ba0-93a5-d36514a955ae"
CID = "aaaaaaaa-1111-4444-8888-111111111111"
TID = "bbbbbbbb-2222-4444-8888-222222222222"
# This replacement exists only in Playwright's vendor-script route.
# The real vendored SDK remains unchanged and is never replaced on disk.
MSAL_STUB = r"""
window.__authTest = {events: [], silentMode: "success", cached: false, clears: 0};
window.msal = {
  BrowserCacheLocation: {MemoryStorage: "memoryStorage", SessionStorage: "sessionStorage"},
  NavigationClient: class {
    async navigateExternal(url) { location.assign(url); return true; }
  },
  PublicClientApplication: class {
    constructor(config) { window.__authTest.config = config; this.config = config; }
    async initialize() { window.__authTest.events.push("initialize"); }
    async handleRedirectPromise() {
      const test = window.__authTest;
      test.events.push("handleRedirectPromise");
      if (!this.config.cache.storeAuthStateInCookie) throw {errorCode:"in_mem_redirect_unavailable"};
      const returning = sessionStorage.getItem("msal.test.redirect");
      if (!returning) return null;
      if (returning === "denied") throw {errorCode:"access_denied", message:"PRIVATE ERROR"};
      if (returning === "cancelled") throw {errorCode:"user_cancelled", message:"PRIVATE ERROR"};
      if (returning === "interrupted") return null;
      test.cached = true;
      return {account:{homeAccountId:"test-account"}, accessToken:__ACCESS__};
    }
    async loginRedirect(request) {
      const test = window.__authTest;
      test.events.push("loginRedirect"); test.request = request;
      if (test.events.indexOf("handleRedirectPromise") < 0) throw Error("redirect handled too late");
      sessionStorage.setItem("msal.test.redirect", window.__testMode || "success");
      document.cookie = "msal.test.transient=TEST-ONLY; path=/; SameSite=Lax";
      const url = new URL(this.config.auth.authority + "/oauth2/v2.0/authorize");
      url.searchParams.set("client_id", this.config.auth.clientId);
      url.searchParams.set("redirect_uri", this.config.auth.redirectUri);
      await this.config.system.navigationClient.navigateExternal(url.href, {});
    }
    async acquireTokenSilent(request) {
      const test = window.__authTest;
      test.silentRequest = request;
      if (test.silentMode === "expired") throw {errorCode:"interaction_required",message:"PRIVATE ERROR"};
      if (test.silentMode === "pending") return new Promise(resolve => {
        test.finishSilent = () => {test.cached = true; resolve({accessToken:__ACCESS__});};
      });
      return {accessToken:__ACCESS__};
    }
    setActiveAccount(account) { window.__authTest.active = account; }
    async clearCache() { window.__authTest.cached = false; window.__authTest.clears++; }
  }
};
"""


def contains(page, selector, text):
    page.wait_for_function(
        "arg => document.querySelector(arg[0])?.textContent.includes(arg[1])", arg=[selector, text])


def luminance(color):
    values = [int(v) / 255 for v in re.findall(r"\d+", color)[:3]]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))


def check_real_auth(base_url, ipv6_localhost=False):
    """Real vendored SDK, no sign-in interaction. Stop before Microsoft authorization."""
    parsed = urlparse(base_url)
    assert parsed.scheme == "http" and parsed.hostname == "localhost"
    assert parsed.path in ("", "/") and not parsed.query and not parsed.fragment
    origin = base_url.rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", args=(
            ["--host-resolver-rules=MAP localhost [::1]"] if ipv6_localhost else []))
        context = browser.new_context()
        page = context.new_page()
        devtools = context.new_cdp_session(page)
        devtools.send("DOMStorage.enable")
        proof = {"authorize": None, "responses": [], "page_error_classes": [], "unexpected_requests": []}
        try:
            def capture_local_state():
                # CDP storage reads do not wait for a document navigation to settle.
                session = devtools.send("DOMStorage.getDOMStorageItems", {
                    "storageId": {"securityOrigin": origin, "isLocalStorage": False}})["entries"]
                local = devtools.send("DOMStorage.getDOMStorageItems", {
                    "storageId": {"securityOrigin": origin, "isLocalStorage": True}})["entries"]
                cookies = context.cookies(origin)
                entries = session + local + [[c["name"], c["value"]] for c in cookies]
                proof["storage"] = {
                    "session_names": [key for key, _ in session],
                    "local_names": [key for key, _ in local],
                    "cookie_names": [c["name"] for c in cookies],
                    "token_artifact_present": any(
                        re.search(r"access.?token|id.?token|refresh.?token", key, re.I)
                        or re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value)
                        for key, value in entries),
                }
                proof["cookie_metadata"] = [{"name": c["name"], "secure": c["secure"],
                                             "httpOnly": c["httpOnly"], "sameSite": c["sameSite"]}
                                            for c in cookies]

            def boundary(route):
                request = route.request
                url = urlparse(request.url)
                if url.hostname == "login.microsoftonline.com" and url.path.endswith("/authorize"):
                    params = parse_qs(url.query)
                    proof["authorize"] = {
                        "hostname": url.hostname, "path": url.path,
                        "pkce_s256": params.get("code_challenge_method") == ["S256"],
                        "pkce_challenge_present": len(params.get("code_challenge", [""])[0]) >= 43,
                        "response_type_code": params.get("response_type") == ["code"],
                        "registered_callback": params.get("redirect_uri") == [origin + "/auth/callback"],
                        "expected_client": params.get("client_id") == [CLIENT],
                    }
                    capture_local_state()
                    route.abort()  # No credentials, consent, token exchange or sign-in page.
                elif request.method != "GET" or url.hostname not in ("localhost", "login.microsoftonline.com") or url.path.startswith("/api/"):
                    proof["unexpected_requests"].append({
                        "hostname": url.hostname, "path": url.path, "method": request.method})
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", boundary)
            page.on("response", lambda response: proof["responses"].append({
                "hostname": urlparse(response.url).hostname, "path": urlparse(response.url).path,
                "status": response.status}))
            page.on("pageerror", lambda error: proof["page_error_classes"].append(error.name))
            page.goto(origin)
            deadline = time.monotonic() + 25
            while proof["authorize"] is None and time.monotonic() < deadline:
                page.wait_for_timeout(100)
                if page.locator("#auth-retry").is_visible():
                    break
            if proof["authorize"] is None:
                capture_local_state()
            assert proof["authorize"] and all(value for key, value in proof["authorize"].items()
                                             if key not in ("hostname", "path")), "authorize_not_verified"
            assert not proof["storage"]["local_names"], "local_storage_not_empty"
            assert not proof["storage"]["token_artifact_present"], "persistent_token_artifact"
            assert not proof["page_error_classes"] and not proof["unexpected_requests"], "unexpected_browser_event"
            proof["result"] = "PASS"
        except Exception as error:
            proof["result"] = "FAIL"
            proof["failure_class"] = type(error).__name__
            raise
        finally:
            print(json.dumps(proof, indent=2))
            browser.close()


def main():
    LOGGER.handlers.clear()
    LOGGER.addHandler(logging.NullHandler())
    private, keys = signing()
    # Artifacts are test output, never source fixtures or notebook publication.
    artifacts = Path(tempfile.mkdtemp(prefix="simple-chat-browser-"))
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(settings(directory + "/browser.sqlite"), agents=FakeAgents(),
                         auth=EntraAuth(TENANT, AUDIENCE, [USER], keys))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]))
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                if time.monotonic() > deadline:
                    raise AssertionError("Test server did not start")
                time.sleep(.01)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome")
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                errors, external, api_calls = [], [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: api_calls.append(request.url)
                        if "/api/" in request.url else None)
                config = {"tenant_id": TENANT, "client_id": CLIENT, "scope": SCOPE,
                          "redirect_path": "/auth/callback"}
                context.route("**/auth/config", lambda route: route.fulfill(json=config))
                context.route("**/static/vendor/msal-browser.min.js", lambda route: route.fulfill(
                    content_type="application/javascript",
                    body=MSAL_STUB.replace("__ACCESS__", json.dumps(token(private)))))

                def offline_microsoft(route):
                    external.append(route.request.url)
                    parsed = urlparse(route.request.url)
                    assert parsed.hostname == "login.microsoftonline.com"
                    params = parse_qs(parsed.query)
                    if parsed.path.endswith("/authorize"):
                        assert params["redirect_uri"] == [origin + "/auth/callback"]
                        assert not context.cookies(origin), "Auth cookies survived external navigation"
                        route.fulfill(status=302, headers={
                            "Location": origin + "/auth/callback?code=TEST-ONLY&state=TEST-ONLY"})
                    elif parsed.path.endswith("/logout"):
                        assert params["post_logout_redirect_uri"] == [origin + "/auth/callback"]
                        assert params["client_id"] == [CLIENT]
                        route.fulfill(status=302, headers={"Location": origin + "/auth/callback"})
                    else:
                        raise AssertionError("Unexpected cloud request: " + route.request.url)

                context.route("https://**/*", offline_microsoft)
                health = page.request.get(origin + "/healthz").json()
                assert health["revision"] == "test-artifact", health
                # Callback must serve the same real entry point, not a test replacement.
                callback = page.request.get(origin + "/auth/callback")
                assert callback.body() == (ROOT / "static/index.html").read_bytes()
                assert page.request.get(origin + "/api/scenarios").status == 401
                page.goto(origin)
                contains(page, "#auth-status", "Connected with Microsoft")
                assert len(external) == 1 and not api_calls
                assert page.url == origin + "/"
                assert page.evaluate("window.__authTest.events") == ["initialize", "handleRedirectPromise"]
                assert page.evaluate("""() => {
                  const c = window.__authTest.config;
                  return c.cache.cacheLocation === "memoryStorage"
                    && c.cache.temporaryCacheLocation === "sessionStorage"
                    && c.cache.storeAuthStateInCookie && !c.cache.secureCookies
                    && !c.auth.navigateToLoginRequestUrl
                    && c.auth.redirectUri === location.origin + "/auth/callback"
                    && !c.system.loggerOptions.piiLoggingEnabled;
                }""")
                assert page.evaluate("localStorage.length === 0 && sessionStorage.length === 0 && document.cookie === ''")
                assert page.locator("section").count() == 1
                assert page.get_by_role("button").all_text_contents() == ["Logout", "Send message"]
                assert page.locator("#auth-retry").is_hidden()
                assert page.locator("#chat-check").is_hidden()
                assert page.locator("#chat-message").get_attribute("maxlength") == "2000"
                assert page.locator("#chat-transcript").get_attribute("aria-live") == "polite"
                page.screenshot(path=str(artifacts / "desktop-empty.png"), full_page=True)
                state = {"mode": "complete", "messages": [], "posts": [], "gets": 0}
                reply = "Synthetic advice. <img src=x onerror=alert(1)> No order was changed."

                def endpoint(route):
                    request = route.request
                    assert request.headers.get("authorization", "").startswith("Bearer ")
                    mode = state["mode"]
                    if request.method == "POST":
                        body = request.post_data_json
                        assert set(body) == {"message", "conversation_id"}
                        assert body["conversation_id"] in (None, CID)
                        state["posts"].append(body)
                        if mode in (422, 429, 503, 500, 401, 403):
                            route.fulfill(status=mode, json={"detail": "PRIVATE ERROR"})
                            return
                        state["messages"].append({"role": "user", "content": body["message"]})
                        route.fulfill(status=202, json={"conversation_id": CID, "turn_id": TID, "status": "queued"})
                        return
                    state["gets"] += 1
                    assert request.url.endswith("/api/chat/conversations/" + CID)
                    if mode in ("missing", "get-error", "malformed"):
                        route.fulfill(status=404 if mode == "missing" else 500 if mode == "get-error" else 200,
                                      json={} if mode == "malformed" else {"detail": "PRIVATE ERROR"})
                        return
                    status = "queued" if mode == "queued" else "running" if mode == "pending" else "failed" if mode == "failed" else "completed"
                    if status == "completed" and state["messages"][-1]["role"] == "user":
                        state["messages"].append({"role": "assistant", "content": reply})
                    route.fulfill(json={"conversation_id": CID, "status": status, "messages": state["messages"],
                                        "error_code": "agent_failed" if status == "failed" else None})

                page.route("**/api/chat/**", endpoint)
                message, send = page.locator("#chat-message"), page.locator("#chat-send")

                def submit(text):
                    message.fill(text)
                    send.click()

                send.click()
                contains(page, "#chat-error", "1–2000")
                message.evaluate("e => {e.value = 'x'.repeat(2001);}")
                send.click()
                assert message.get_attribute("aria-invalid") == "true" and not state["posts"]
                message.fill("My fictional headphones arrived damaged.")
                message.press("Shift+Enter")
                assert message.input_value().endswith("\n")
                message.press("Enter")
                contains(page, "#chat-status", "Agent reply received")
                assert state["posts"][0]["conversation_id"] is None
                assert page.locator(".chat-bubble").count() == 2
                assert message.evaluate("e => e === document.activeElement")
                submit("What synthetic return details should I prepare?")
                contains(page, "#chat-status", "Agent reply received")
                assert state["posts"][-1]["conversation_id"] == CID
                assert page.locator(".chat-bubble").count() == 4
                assert page.locator("#chat-transcript img").count() == 0
                assert "<img" in page.locator("#chat-transcript").inner_text()
                assert page.evaluate("window.__authTest.silentRequest.scopes") == [SCOPE]
                message.focus()
                page.keyboard.press("Tab")
                assert send.evaluate("e => e === document.activeElement")
                focus = send.evaluate("""e => {const s=getComputedStyle(e); return {
                  style:s.outlineStyle,width:s.outlineWidth,color:s.color,background:s.backgroundColor};}""")
                assert focus["style"] == "solid" and focus["width"] == "3px", focus
                lighter, darker = sorted([luminance(focus["color"]), luminance(focus["background"])], reverse=True)
                contrast = (lighter + .05) / (darker + .05)
                assert contrast >= 4.5
                page.keyboard.press("Shift+Tab")
                assert message.evaluate("e => e === document.activeElement")
                page.locator("#logout").focus()
                page.keyboard.press("Tab")
                assert page.locator("#chat-transcript").evaluate("e => e === document.activeElement")
                page.keyboard.press("Tab")
                assert message.evaluate("e => e === document.activeElement")
                accessibility = page.locator("main").aria_snapshot()
                assert 'button "Logout"' in accessibility and 'log "Customer support conversation"' in accessibility
                assert 'textbox "Your synthetic customer message"' in accessibility

                def geometry():
                    return page.evaluate("""() => {
                      const box = selector => {const e=document.querySelector(selector),
                        r=e.getBoundingClientRect(),s=getComputedStyle(e);
                        return {x:r.x,y:r.y,width:r.width,height:r.height,
                          visible:r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight
                            &&s.visibility==="visible"&&s.display!=="none"};};
                      return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                        transcript:box("#chat-transcript"),composer:box("#chat-message"),
                        send:box("#chat-send"),logout:box("#logout")};
                    }""")

                desktop = geometry()
                assert desktop["scrollWidth"] == 1440
                page.screenshot(path=str(artifacts / "desktop-chat.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                mobile = geometry()
                assert mobile["scrollWidth"] == 390, mobile
                for target in ("transcript", "composer", "send", "logout"):
                    assert mobile[target]["visible"] and mobile[target]["height"] >= 44, mobile
                page.screenshot(path=str(artifacts / "mobile-chat.png"), full_page=True)
                # Explicit refusals never produce a reply, change binding or retry POST.
                for code, text in ((503, "Hosted agent unavailable"), (429, "Busy:"), (422, "Message refused")):
                    state["mode"] = code
                    before = len(state["posts"])
                    submit("Synthetic negative-path test.")
                    contains(page, "#chat-error", text)
                    assert send.is_enabled() and len(state["posts"]) == before + 1
                    assert page.locator(".chat-bubble").count() == 4
                    assert "PRIVATE ERROR" not in page.locator("body").inner_text()
                state["mode"] = "queued"
                submit("A fictional pending request.")
                contains(page, "#chat-status", "Queued.")
                assert send.is_disabled() and page.locator("#chat-form").get_attribute("aria-busy") == "true"
                state["mode"] = "pending"
                contains(page, "#chat-status", "Thinking")
                page.screenshot(path=str(artifacts / "mobile-pending.png"), full_page=True)
                state["mode"] = "failed"
                contains(page, "#chat-status", "Conversation turn failed")
                assert send.is_enabled() and page.locator(".chat-bubble").count() == 5
                # Known conversation can recover through GET only. Unknowns block duplicates.
                state["mode"] = "get-error"
                submit("A fictional status failure.")
                contains(page, "#chat-error", "outcome unknown")
                before = len(state["posts"])
                assert send.is_disabled() and page.locator("#chat-check").is_visible()
                state["mode"] = "complete"
                page.locator("#chat-check").click()
                contains(page, "#chat-status", "Agent reply received")
                assert send.is_enabled() and len(state["posts"]) == before
                state["mode"] = "malformed"
                submit("A fictional malformed status.")
                contains(page, "#chat-error", "outcome unknown")
                assert send.is_disabled()
                state["mode"] = "complete"
                page.locator("#chat-check").click()
                contains(page, "#chat-status", "Agent reply received")
                page.clock.install()
                state["mode"] = "pending"
                submit("A fictional long-running request.")
                contains(page, "#chat-status", "Thinking")
                before = len(state["posts"])
                page.clock.fast_forward(240001)
                contains(page, "#chat-status", "Status unknown after 4 minutes")
                assert send.is_disabled() and len(state["posts"]) == before
                page.clock.resume()
                state["mode"] = "missing"
                page.locator("#chat-check").click()
                contains(page, "#chat-error", "not owned by this session")
                assert send.is_disabled() and page.locator("#chat-check").is_hidden()
                # Logout callback and refresh must not silently restart Microsoft login.
                authorizes = len([url for url in external if "/authorize?" in url])
                page.evaluate("document.cookie = 'msal.test.leftover=TEST-ONLY; path=/; SameSite=Lax'")
                page.get_by_role("button", name="Logout", exact=True).click()
                contains(page, "#auth-status", "Logged out.")
                assert page.locator(".chat-bubble").count() == 0 and message.input_value() == ""
                assert message.is_disabled() and send.is_disabled()
                assert page.evaluate("""localStorage.length === 0 && sessionStorage.length === 1
                  && sessionStorage.getItem("service-chat:logged-out") === "1"
                  && document.cookie === "" && !window.__authTest.cached""")
                page.reload()
                contains(page, "#auth-status", "Logged out.")
                assert len([url for url in external if "/authorize?" in url]) == authorizes
                page.screenshot(path=str(artifacts / "mobile-logged-out.png"), full_page=True)
                page.get_by_role("button", name="Continue with Microsoft").click()
                contains(page, "#auth-status", "Connected with Microsoft")
                assert page.evaluate("sessionStorage.length === 0")
                # A fresh unknown POST must not offer a false GET recovery without an ID.
                state["mode"] = 500
                submit("A fictional unknown submission.")
                contains(page, "#chat-error", "Submission outcome unknown")
                before = len(state["posts"])
                assert send.is_disabled() and page.locator("#chat-check").is_hidden()
                message.press("Enter")
                assert len(state["posts"]) == before
                # Reconnect deliberately for session expiry and permission checks.
                def reconnect():
                    page.locator("#logout").click()
                    contains(page, "#auth-status", "Logged out.")
                    page.locator("#auth-retry").click()
                    contains(page, "#auth-status", "Connected with Microsoft")

                reconnect()
                state["mode"] = "complete"
                state["messages"] = []
                submit("An established fictional conversation.")
                contains(page, "#chat-status", "Agent reply received")
                state["mode"] = 500
                submit("An uncertain second submission.")
                contains(page, "#chat-error", "Submission outcome unknown")
                assert send.is_disabled() and page.locator("#chat-check").is_hidden()
                reconnect()
                page.evaluate("window.__authTest.silentMode = 'expired'")
                submit("A fictional expired session.")
                contains(page, "#auth-status", "session expired")
                assert page.locator(".chat-bubble").count() == 0 and send.is_disabled()
                assert page.locator("#auth-retry").is_visible()
                for code in (401, 403):
                    reconnect()
                    state["mode"] = code
                    submit("A fictional unauthorized request.")
                    contains(page, "#auth-status", f"Access refused ({code})")
                    assert send.is_disabled() and page.locator(".chat-bubble").count() == 0
                # A late token acquisition after Logout cannot submit or restore UI.
                reconnect()
                page.evaluate("window.__authTest.silentMode = 'pending'")
                submit("A fictional pending token acquisition.")
                page.wait_for_function("typeof window.__authTest.finishSilent === 'function'")
                before = len(state["posts"])
                page.locator("#logout").click()
                contains(page, "#auth-status", "Logged out.")
                assert len(state["posts"]) == before and page.locator(".chat-bubble").count() == 0
                assert not errors, errors
                assert not any("/api/metrics" in url or "/api/simulations" in url for url in api_calls)
                # Separate contexts prove redirect denial/cancellation and config errors.
                negative_checks = []
                for mode, expected in (("denied", "sign-in denied"), ("cancelled", "sign-in cancelled"),
                                       ("interrupted", "interrupted or cancelled")):
                    page.evaluate("sessionStorage.clear()")
                    context.add_init_script(f"window.__testMode = {json.dumps(mode)};")
                    count = len(external)
                    page.goto(origin)
                    contains(page, "#auth-status", expected)
                    assert len(external) == count + 1
                    assert page.locator("#auth-retry").is_visible() and send.is_disabled()
                    assert page.evaluate("sessionStorage.length === 0 && localStorage.length === 0")
                    assert "PRIVATE ERROR" not in page.locator("body").inner_text()
                    negative_checks.append(mode)
                context.route("**/auth/config", lambda route: route.fulfill(status=503, json={"detail": "PRIVATE ERROR"}))
                page.goto(origin)
                contains(page, "#auth-status", "not configured (503)")
                assert send.is_disabled()
                assert not errors, errors
                browser.close()
                print(json.dumps({
                    "result": "PASS", "artifacts": str(artifacts),
                    "app_sha256": hashlib.sha256((ROOT / "static/app.js").read_bytes()).hexdigest(),
                    "desktop": desktop, "mobile": mobile, "button_contrast": round(contrast, 2),
                    "focus": focus, "auth_negative_checks": negative_checks + ["config 503", "silent expiry", "401", "403"],
                    "checks": ["automatic redirect roundtrip", "callback index identity", "redirect before session decision",
                               "no token storage", "single panel", "two-turn binding", "keyboard/focus/accessibility",
                               "literal HTML", "empty/oversize", "503/429/422 no retry", "queued/running/failed",
                               "unknown GET recovery", "malformed status", "4-minute bound", "404 owner isolation",
                               "unknown POST blocks duplicates with/without binding",
                               "logout callback/refresh guard", "late silent logout"],
                    "page_errors": errors,
                }, indent=2))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            assert not thread.is_alive(), "Local server cleanup failed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-auth-base-url")
    parser.add_argument("--ipv6-localhost", action="store_true")
    args = parser.parse_args()
    if args.real_auth_base_url:
        check_real_auth(args.real_auth_base_url, args.ipv6_localhost)
    else:
        main()
