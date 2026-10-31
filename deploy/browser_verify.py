"""Real automatic Microsoft redirect plus separately labeled protected chat acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from azure.identity import AzureCliCredential
from playwright.sync_api import sync_playwright

from manage import STATE, Deployment, config

SDK_PATH = "/static/vendor/msal-browser.min.js"
CLI_SDK = r"""
window.__cliVerifier = {cache: __ACCESS__, active: true};
const testAccount = {homeAccountId:"cli-verification-only",localAccountId:"cli-user"};
window.msal = {
  BrowserCacheLocation: {MemoryStorage:"memoryStorage",SessionStorage:"sessionStorage"},
  NavigationClient: class {
    async navigateExternal(url) {location.assign(url);return true;}
  },
  InteractionRequiredAuthError: class extends Error {},
  PublicClientApplication: class {
    constructor(config) {
      if(config.cache.cacheLocation !== "memoryStorage" ||
         config.cache.temporaryCacheLocation !== "sessionStorage" ||
         config.cache.storeAuthStateInCookie !== true ||
         config.cache.secureCookies !== (location.protocol === "https:"))
        throw Error("Unexpected token or temporary cache policy");
    }
    async initialize() {}
    async handleRedirectPromise() {
      return {account:testAccount,accessToken:window.__cliVerifier.cache};
    }
    getAllAccounts() {return window.__cliVerifier.active ? [testAccount] : [];}
    getActiveAccount() {return window.__cliVerifier.active ? testAccount : null;}
    setActiveAccount(account) {window.__cliVerifier.active=!!account;}
    async acquireTokenSilent() {return {account:testAccount,accessToken:window.__cliVerifier.cache};}
    async loginRedirect() {throw Error("Unexpected login redirect in authenticated test context");}
    async acquireTokenRedirect() {throw Error("Unexpected token redirect in authenticated test context");}
    async clearCache() {window.__cliVerifier.cache=null;window.__cliVerifier.active=false;}
    async logoutRedirect() {
      window.__cliVerifier.cache=null;window.__cliVerifier.active=false;
    }
  }
};
"""


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def poll(client, path):
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        response = client.get(path, timeout=30)
        require(response.status_code == 200, "Owned chat readback refused; retain accepted ID, never resend.")
        row = response.json()
        if row["status"] in {"completed", "failed"}:
            return row
        require(row["status"] in {"queued", "running"}, "Invalid chat lifecycle state.")
        time.sleep(2)
    raise TimeoutError("Chat outcome unknown; reconcile accepted ID with GET only.")


def actual_redirect(browser, base, settings, directory, *, ipv6_localhost=False, progress=lambda stage: None):
    with browser.new_context(viewport={"width": 1440, "height": 1000}) as context:
        page = context.new_page()
        writes = []
        errors = []
        page.on("pageerror", lambda _: errors.append("pageerror"))
        context.on("request", lambda r: writes.append(True)
                   if urlsplit(r.url).path.startswith("/api/") and r.method != "GET" else None)
        # Chrome's host-resolver override does not affect Playwright's separate API client.
        request_base = "http://[::1]:8080" if ipv6_localhost else base
        progress("reading_official_sdk")
        with httpx.Client(trust_env=False, timeout=15) as metadata:
            sdk = metadata.get(request_base + SDK_PATH)
        require(sdk.status_code == 200, "Official vendored MSAL unavailable.")
        progress("checking_callback_document")
        with httpx.Client(trust_env=False, timeout=15) as metadata:
            callback = metadata.get(request_base + "/auth/callback")
        require(callback.status_code == 200 and b"/static/app.js" in callback.content,
                "Redirect callback does not load the same authentication application.")
        require("script-src 'self'" in callback.headers.get("content-security-policy", "")
                and "'unsafe-inline'" not in callback.headers.get("content-security-policy", ""),
                "Authentication callback lost strict script policy.")

        def authorize(request):
            url = urlsplit(request.url)
            return url.hostname == "login.microsoftonline.com" and url.path.endswith("/oauth2/v2.0/authorize")

        # Keep the initiating document available for storage checks, without entering credentials.
        context.route("https://login.microsoftonline.com/**/oauth2/v2.0/authorize*",
                      lambda route: route.fulfill(status=204, body=""))
        progress("awaiting_automatic_authorize_redirect")
        with context.expect_event("request", predicate=authorize, timeout=60000) as observed:
            page.goto(base, wait_until="domcontentloaded")
        request = urlsplit(observed.value.url)
        values = parse_qs(request.query)
        scope = f"api://{settings['AUTH_CLIENT_ID']}/access_as_user"
        require(request.path == f"/{settings['TENANT_ID']}/oauth2/v2.0/authorize", "Wrong sign-in tenant.")
        require(values.get("client_id") == [settings["BROWSER_CLIENT_ID"]], "Wrong browser client.")
        require(values.get("redirect_uri") == [base + "/auth/callback"], "Wrong callback origin.")
        require(scope in values.get("scope", [""])[0].split(), "Delegated API scope missing.")
        require(values.get("response_type") == ["code"] and values.get("code_challenge_method") == ["S256"],
                "Automatic sign-in does not use authorization code with PKCE.")
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", values.get("code_challenge", [""])[0])),
                "Invalid PKCE challenge.")
        storage = page.evaluate(r"""() => {
          const entries = Object.entries(sessionStorage);
          const token = /access.?token|id.?token|refresh.?token/i;
          const jwt = /[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}/;
          return {
            local_entries: localStorage.length,
            session_entries: entries.length,
            session_token_artifacts: entries.filter(([key,value]) =>
              token.test(key) || /"(access_token|id_token|refresh_token)"\s*:/.test(value) ||
              jwt.test(value)).length
          };
        }""")
        cookies = context.cookies(base)
        with httpx.Client(trust_env=False, timeout=30) as metadata:
            cookie_callback = metadata.get(request_base + "/auth/callback",
                                           cookies={item["name"]: item["value"] for item in cookies})
        progress(f"callback_http_{cookie_callback.status_code}_with_{len(cookies)}_auth_cookies")
        require(cookie_callback.status_code == 200,
                "Gateway refused callback with actual SDK authentication cookies.")
        require(storage["local_entries"] == 0 and storage["session_token_artifacts"] == 0,
                "Automatic redirect persisted token-shaped browser storage.")
        require(not cookies, "MSAL authentication cookies would be sent through WAF on callback.")
        require(storage["session_entries"] > 0, "Redirect lost tab-scoped PKCE state.")
        denial = urlencode({"error": "access_denied", "state": values["state"][0]})
        callback_response = page.goto(base + "/auth/callback#" + denial, wait_until="networkidle")
        require(callback_response.status == 200, "Browser callback blocked at gateway.")
        page.wait_for_function("""() => document.getElementById("auth-status").textContent.includes(
          "Microsoft sign-in denied or permission not granted.")""")
        require(page.evaluate("() => sessionStorage.length === 0 && localStorage.length === 0")
                and not context.cookies(base), "Handled callback retained temporary authentication state.")
        require(not writes and not errors, "Automatic sign-in caused API writes or JavaScript errors.")
        # Microsoft page may contain user/tenant data; never screenshot it.
        return {
            "status": "passed", "automatic_redirect": True, "actual_sdk": True,
            "sdk_sha256": hashlib.sha256(sdk.content).hexdigest(), "pkce_s256": True,
            "tenant_id": settings["TENANT_ID"], "client_id": settings["BROWSER_CLIENT_ID"],
            "redirect_uri": base + "/auth/callback", "interactive_human_signin_verified": False,
            "api_writes": 0, "javascript_errors": len(errors),
            "authorization_navigation_intercepted_204": True,
            "storage": storage, "transient_cookie_count": len(cookies),
            "cookie_policy_verified": True,
            "callback_status": callback_response.status,
            "actual_sdk_denied_callback_handled": True,
        }


def protected_chat(browser, base, settings, receipt, save, directory):
    with AzureCliCredential(tenant_id=settings["TENANT_ID"]) as identity:
        access = identity.get_token(f"api://{settings['AUTH_CLIENT_ID']}/.default").token
    with browser.new_context(viewport={"width": 1440, "height": 1000}) as context:
        sdk = CLI_SDK.replace("__ACCESS__", json.dumps(access))
        context.route(base + SDK_PATH, lambda route: route.fulfill(content_type="application/javascript", body=sdk))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda _: errors.append("pageerror"))
        with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {access}"},
                          timeout=30, trust_env=False) as client:
            require(context.request.get(base + "/api/chat/conversations/" + str(uuid.uuid4())).status == 401,
                    "Anonymous conversation lookup not refused.")
            page.goto(base, wait_until="networkidle")
            page.locator("#chat-message").wait_for(state="visible")
            page.wait_for_function("() => !document.getElementById('chat-message').disabled")
            require(page.get_by_role("button", name="Sign in with Microsoft", exact=True).count() == 0,
                    "Manual sign-in button remains on the normal chat surface.")
            require(page.locator("#scenarios, #system-metrics, #journey-filter, #chat-new").count() == 0,
                    "Removed dashboard or new-conversation controls remain.")
            receipt.update(auth_mode="intercepted_sdk_existing_cli_user", real_sso_verified=False)
            conversation = None
            for index, message in enumerate((
                "My synthetic order SYN-101 headphones arrived damaged five days after delivery. What can I do?",
                "For the same synthetic order, is a refund already issued and what happens next?",
            ), 1):
                page.locator("#chat-message").fill(message)
                with page.expect_response(lambda r: r.request.method == "POST"
                                          and urlsplit(r.url).path == "/api/chat/messages") as accepted:
                    page.locator("#chat-send").click()
                response = accepted.value
                require(response.status == 202, f"Chat submission refused HTTP {response.status}; no retry.")
                queued = response.json()
                require(conversation in {None, queued["conversation_id"]}, "Follow-up changed conversation.")
                conversation = queued["conversation_id"]
                receipt["conversation_id"] = conversation
                receipt["turns"].append({"turn": index, "turn_id": queued["turn_id"], "status": "queued"})
                save()
                row = poll(client, f"/api/chat/conversations/{conversation}")
                receipt["turns"][-1].update(status=row["status"], trace_id=row.get("trace_id"))
                save()
                require(row["status"] == "completed", "Hosted chat failed; no successful response claimed.")
                require(len(row["messages"]) == index * 2, "Stored conversation history incomplete.")
                page.wait_for_function("(n) => document.querySelectorAll('.chat-bubble').length === n",
                                       arg=index * 2)
                require(page.locator(".chat-bubble p").all_text_contents()
                        == [m["content"] for m in row["messages"]], "UI differs from stored history.")
                page.wait_for_function("() => !document.getElementById('chat-send').disabled")
                receipt["turns"][-1]["history_matches_ui"] = True
                save()
            geometry = []
            for width, height, name in ((1440, 1000, "desktop"), (390, 844, "mobile")):
                page.set_viewport_size({"width": width, "height": height})
                measured = page.evaluate("""() => ({
                  width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,
                  minimumButtonHeight:Math.min(...[...document.querySelectorAll('button')]
                    .filter(e=>e.getBoundingClientRect().height>0).map(e=>e.getBoundingClientRect().height))
                })""")
                require(measured["width"] >= measured["scrollWidth"] and measured["minimumButtonHeight"] >= 44,
                        "Minimal chat responsive geometry failed.")
                page.screenshot(path=str(directory / f"chat-{name}.png"), full_page=True)
                geometry.append({"viewport": name, **measured})
            require(page.evaluate("() => localStorage.length") == 0, "Tokens persisted in localStorage.")
            # A 204 keeps the cleared app document inspectable; no Microsoft session is claimed logged out.
            context.route("https://login.microsoftonline.com/**/oauth2/v2.0/logout*",
                          lambda route: route.fulfill(status=204, body=""))
            with context.expect_event("request", predicate=lambda r:
                                      urlsplit(r.url).hostname == "login.microsoftonline.com"
                                      and urlsplit(r.url).path.endswith("/oauth2/v2.0/logout")) as logout:
                page.get_by_role("button", name="Logout", exact=True).click()
            end_session = urlsplit(logout.value.url)
            require(end_session.path == f"/{settings['TENANT_ID']}/oauth2/v2.0/logout"
                    and parse_qs(end_session.query).get("post_logout_redirect_uri") == [base + "/auth/callback"]
                    and parse_qs(end_session.query).get("client_id") == [settings["BROWSER_CLIENT_ID"]],
                    "Logout did not target the exact tenant and registered callback.")
            page.wait_for_function("() => !window.__cliVerifier.cache && !window.__cliVerifier.active")
            require(page.locator(".chat-bubble").count() == 0, "Logout retained conversation text.")
            require(not errors, "Chat browser JavaScript error.")
            receipt.update(status="passed", geometry=geometry, logout_cleared=True,
                           microsoft_logout_request_verified=True, microsoft_logout_intercepted_204=True,
                           javascript_errors=0,
                           automatic_post_retries=0, messages_logged=False)


def verify(*, auth_only=False, base_url=None, ipv6_localhost=False,
           hosted_agent_name=None, hosted_agent_version=None):
    settings = config("sea")
    base = (base_url or f"https://{settings['PUBLIC_HOST']}").rstrip("/")
    require(base in {f"https://{settings['PUBLIC_HOST']}", "http://localhost:8080"}, "Unreviewed verification origin.")
    if not auth_only:
        require(hosted_agent_name == settings.get("HOSTED_AGENT_NAME")
                and hosted_agent_version == settings.get("HOSTED_AGENT_VERSION"), "Hosted target pin differs.")
        require(bool(hosted_agent_name and hosted_agent_version), "Hosted target must be configured.")
        Deployment(settings).verify_runtime_configuration(Deployment(settings).app())
    directory = STATE / "screenshots" / "simple-chat"
    directory.mkdir(parents=True, exist_ok=True)
    destination = STATE / f"chat-browser-{uuid.uuid4()}.json"
    receipt = {"url": base, "status": "started", "turns": [],
               "hosted_name": hosted_agent_name, "hosted_version": hosted_agent_version,
               "interactive_human_signin_verified": False}

    def save():
        destination.write_text(json.dumps(receipt, indent=2) + "\n")

    def progress(stage):
        receipt["stage"] = stage
        save()

    save()
    try:
        with sync_playwright() as playwright:
            args = ["--host-resolver-rules=MAP localhost [::1]"] if ipv6_localhost else []
            browser = playwright.chromium.launch(channel="chrome", headless=True, args=args)
            try:
                receipt["actual_auth"] = actual_redirect(browser, base, settings, directory,
                                                        ipv6_localhost=ipv6_localhost, progress=progress)
                save()
                if auth_only:
                    receipt["status"] = "passed"
                else:
                    protected_chat(browser, base, settings, receipt, save, directory)
            finally:
                browser.close()
    except Exception as error:
        receipt.update(status="failed", failure_type=type(error).__name__,
                       reconciliation="Retain accepted IDs; GET only, no POST retries.")
        save()
        raise RuntimeError(f"Chat browser verification failed; retained nonsecret receipt: {destination}") from None
    save()
    if not auth_only:
        (STATE / "chat-browser-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-only", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--ipv6-localhost", action="store_true")
    parser.add_argument("--hosted-agent-name", default=os.getenv("HOSTED_AGENT_NAME"))
    parser.add_argument("--hosted-agent-version", default=os.getenv("HOSTED_AGENT_VERSION"))
    print(json.dumps(verify(**vars(parser.parse_args())), indent=2))
