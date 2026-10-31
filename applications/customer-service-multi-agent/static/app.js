"use strict";
// Tokens and conversation binding live in memory. Redirect state uses sessionStorage.
// MSAL compatibility cookies are removed before leaving this origin.
// No tokens enter cookies/storage. Nothing uses localStorage.
let client = null, authConfig = null, account = null, generation = 0, signingIn = false;
let conversationId = null, chatEpoch = 0, chatBusy = false, chatUncertain = false;
let submissionPending = false;
let chatPolling = null, chatDeadlineTimer = null, chatController = null;
const attemptKey = "service-chat:login-pending", logoutKey = "service-chat:logged-out";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const $ = id => document.getElementById(id);
function node(tag, text, cls) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}
function controls() {
  $("chat-message").disabled = !account;
  $("chat-send").disabled = !account || chatBusy || chatUncertain;
  $("chat-check").disabled = !account || chatBusy;
  $("chat-form").setAttribute("aria-busy", String(chatBusy));
}
function chatError(message) {
  $("chat-error").textContent = message;
  $("chat-error").hidden = !message;
}
function stopChat() {
  clearTimeout(chatPolling); clearTimeout(chatDeadlineTimer);
  chatPolling = null; chatDeadlineTimer = null;
  chatController?.abort(); chatController = null;
  chatBusy = false;
}
function clearApp() {
  generation++; chatEpoch++; stopChat(); account = null;
  conversationId = null; chatUncertain = false; submissionPending = false;
  $("chat-transcript").replaceChildren(node("p", "Your conversation will appear here.", "empty"));
  $("chat-message").value = ""; $("chat-message").removeAttribute("aria-invalid");
  $("chat-check").hidden = true; chatError(""); controls();
}
function clearAuthCookies() {
  for (const cookie of document.cookie.split(";")) {
    const name = cookie.trim().split("=")[0];
    if (decodeURIComponent(name).startsWith("msal.")) {
      document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    }
  }
}
function clearTemporaryAuth() {
  clearAuthCookies();
  for (const key of Object.keys(sessionStorage)) {
    if (key.startsWith("msal.")) sessionStorage.removeItem(key);
  }
  sessionStorage.removeItem(attemptKey);
}
function cleanCallback() {
  if (location.pathname === "/auth/callback") history.replaceState(null, "", "/");
}
async function authFailure(message) {
  clearApp();
  client?.setActiveAccount(null);
  try { await client?.clearCache(); } catch { /* Memory is discarded on next navigation. */ }
  try { clearTemporaryAuth(); } catch { /* Storage failure is reported below, never bypassed. */ }
  cleanCallback();
  $("auth-status").textContent = message;
  $("chat-status").textContent = "Not connected. No messages will be sent.";
  $("auth-retry").textContent = "Retry Microsoft sign-in";
  $("auth-retry").hidden = false;
  $("auth-retry").disabled = false;
  $("logout").disabled = !authConfig;
}
function authErrorMessage(error) {
  if (["access_denied", "consent_required"].includes(error.errorCode))
    return "Microsoft sign-in denied or permission not granted. Check account access, then retry deliberately.";
  if (["user_cancelled", "user_canceled"].includes(error.errorCode))
    return "Microsoft sign-in cancelled. Retry when ready.";
  return "Microsoft sign-in could not complete. The redirect may have expired or been interrupted. Retry deliberately.";
}
async function beginLogin() {
  if (!client || !authConfig || signingIn) return;
  signingIn = true;
  $("auth-retry").hidden = true;
  $("auth-status").textContent = "Redirecting to Microsoft sign-in…";
  try {
    sessionStorage.removeItem(logoutKey);
    sessionStorage.setItem(attemptKey, "1");
    await client.loginRedirect({scopes: [authConfig.scope]});
  } catch (error) {
    await authFailure(authErrorMessage(error));
  } finally { signingIn = false; }
}
/** @typedef {{tenant_id: string, client_id: string, scope: string, redirect_path: string}} AuthConfig */
async function prepareAuth() {
  if (location.protocol !== "https:" && !["127.0.0.1", "localhost", "[::1]"].includes(location.hostname)) {
    await authFailure("HTTPS required for Microsoft sign-in."); return;
  }
  try {
    const response = await fetch("/auth/config", {cache: "no-store", credentials: "omit"});
    if (!response.ok) {
      await authFailure(response.status === 503
        ? "Microsoft sign-in is not configured (503). Contact the application operator."
        : `Microsoft sign-in configuration unavailable (${response.status}). Retry deliberately.`);
      return;
    }
    const config = /** @type {AuthConfig} */ (await response.json());
    if (!uuid.test(config.tenant_id) || !uuid.test(config.client_id)
      || config.scope !== "api://b2d8ec71-c3b4-4005-a492-08b9bdab3414/access_as_user"
      || config.redirect_path !== "/auth/callback") throw new Error("invalid_configuration");
    authConfig = config;
    class CookieFreeNavigationClient extends window.msal.NavigationClient {
      async navigateExternal(url, options) {
        // SessionStorage retains PKCE state. Auth cookies trigger the hub WAF on return.
        clearAuthCookies();
        return super.navigateExternal(url, options);
      }
    }
    client = new window.msal.PublicClientApplication({
      auth: {clientId: config.client_id, authority: `https://login.microsoftonline.com/${config.tenant_id}`,
        redirectUri: location.origin + config.redirect_path, navigateToLoginRequestUrl: false},
      cache: {cacheLocation: window.msal.BrowserCacheLocation.MemoryStorage,
        temporaryCacheLocation: window.msal.BrowserCacheLocation.SessionStorage,
        // MSAL 4.30 requires auth-state cookies to permit redirect with a memory token cache.
        storeAuthStateInCookie: true, secureCookies: location.protocol === "https:"},
      system: {navigationClient: new CookieFreeNavigationClient(),
        loggerOptions: {piiLoggingEnabled: false, loggerCallback: () => {}}}
    });
    await client.initialize();
    // Always consume redirect before reading guards or deciding whether to sign in.
    const result = await client.handleRedirectPromise();
    const pending = sessionStorage.getItem(attemptKey);
    const loggedOut = sessionStorage.getItem(logoutKey);
    const callback = location.pathname === "/auth/callback";
    clearTemporaryAuth(); cleanCallback();
    $("logout").disabled = false;
    if (loggedOut) {
      await client.clearCache();
      $("auth-status").textContent = "Logged out. Refresh keeps this tab logged out.";
      $("chat-status").textContent = "Conversation cleared.";
      $("auth-retry").textContent = "Continue with Microsoft";
      $("auth-retry").hidden = false;
      return;
    }
    if (result) {
      if (!result.account || !result.accessToken) throw new Error("missing_access_token");
      account = result.account;
      client.setActiveAccount(account);
      $("auth-status").textContent = "Connected with Microsoft.";
      $("chat-status").textContent = "Send a synthetic customer issue.";
      controls();
      return;
    }
    if (pending || callback) {
      await authFailure("Microsoft sign-in was interrupted or cancelled. Retry deliberately."); return;
    }
    await beginLogin();
  } catch (error) {
    await authFailure(authConfig ? authErrorMessage(error)
      : "Microsoft sign-in configuration unavailable or invalid. Retry deliberately or contact the operator.");
  }
}
$("auth-retry").addEventListener("click", () => {
  if (client && authConfig) beginLogin();
  else { $("auth-retry").hidden = true; prepareAuth(); }
});
$("logout").addEventListener("click", async () => {
  if (!authConfig) return;
  clearApp(); signingIn = false;
  $("logout").disabled = true; $("auth-retry").hidden = true;
  $("auth-status").textContent = "Logged out. Clearing Microsoft session…";
  $("chat-status").textContent = "Conversation cleared.";
  client?.setActiveAccount(null);
  try {
    sessionStorage.setItem(logoutKey, "1");
    await client?.clearCache();
    clearTemporaryAuth();
    // Exact registered callback, not origin or an unregistered query-string variant.
    const endpoint = new URL(`https://login.microsoftonline.com/${authConfig.tenant_id}/oauth2/v2.0/logout`);
    endpoint.searchParams.set("client_id", authConfig.client_id);
    endpoint.searchParams.set("post_logout_redirect_uri", location.origin + authConfig.redirect_path);
    location.assign(endpoint.href);
  } catch {
    $("auth-status").textContent = "Logged out locally. Microsoft logout could not complete. Close this tab to finish clearing memory.";
  }
});
function staleSession() { return Object.assign(new Error("Session changed."), {stale: true}); }
async function api(path, options = {}) {
  const session = generation;
  if (!account) throw staleSession();
  let result;
  try {
    result = await client.acquireTokenSilent({account, scopes: [authConfig.scope]});
    if (session !== generation) throw staleSession();
    if (!result.accessToken) throw new Error("missing_access_token");
  } catch (error) {
    if (session === generation) await authFailure("Microsoft session expired or API permission refused. Retry sign-in deliberately.");
    throw staleSession();
  }
  const response = await fetch(path, {...options, headers: {
    "Authorization": `Bearer ${result.accessToken}`, "Content-Type": "application/json"
  }});
  if (session !== generation) throw staleSession();
  if (response.status === 401 || response.status === 403) {
    await authFailure(`Access refused (${response.status}). Your account needs API permission and application approval.`);
    throw staleSession();
  }
  if (!response.ok) throw Object.assign(new Error("Request refused."), {status: response.status});
  if (options.method === "POST" && response.status !== 202) throw new Error("Unconfirmed submission.");
  return response.json();
}
/** @typedef {{role: 'user'|'assistant', content: string}} ChatMessage */
/** @typedef {{conversation_id: string, status: 'queued'|'running'|'completed'|'failed', messages: ChatMessage[], error_code: string|null}} ChatSnapshot */
function parseChatSnapshot(row) {
  if (!row || row.conversation_id !== conversationId
    || !["queued", "running", "completed", "failed"].includes(row.status)
    || !Array.isArray(row.messages) || !row.messages.every(m => m
      && ["user", "assistant"].includes(m.role) && typeof m.content === "string")
    || !(row.error_code === null || typeof row.error_code === "string")) throw new Error("Invalid conversation status.");
  return /** @type {ChatSnapshot} */ (row);
}
function chatBubble(message) {
  const bubble = node("div", null, `chat-bubble ${message.role}`);
  bubble.append(node("strong", message.role === "user" ? "You" : "Service agent"), node("p", message.content));
  return bubble;
}
function scrollChat() { $("chat-transcript").scrollTop = $("chat-transcript").scrollHeight; }
function chatCurrent(epoch, session) { return epoch === chatEpoch && session === generation && !!account; }
function startChatWait(epoch, session) {
  chatBusy = true; chatUncertain = false; chatController = new AbortController();
  $("chat-check").hidden = true; controls();
  chatDeadlineTimer = setTimeout(() => {
    if (!chatCurrent(epoch, session)) return;
    chatEpoch++; stopChat(); chatUncertain = true;
    $("chat-check").hidden = !conversationId || submissionPending;
    $("chat-status").textContent = "Status unknown after 4 minutes. Your message was not resent.";
    chatError(conversationId && !submissionPending ? "Check this conversation's status. Sending is blocked until its outcome is known."
      : "Submission outcome unknown. Do not resend. Logout clears local state but does not cancel submitted work.");
    controls();
  }, 240000);
}
function chatFailure(error, submission = false) {
  stopChat();
  chatUncertain = !submission || ![400, 422, 429, 503].includes(error.status);
  if (error.status === 404) { conversationId = null; chatUncertain = true; }
  // A completed old snapshot cannot prove that an uncertain POST was accepted.
  // Without a confirmed turn ID, even an existing conversation cannot unlock send.
  $("chat-check").hidden = submission || !(conversationId && chatUncertain);
  $("chat-status").textContent = "No successful outcome confirmed. Conversation history preserved.";
  chatError(error.status === 503 ? "Hosted agent unavailable: not deployed or configured. No successful response confirmed."
    : error.status === 429 ? "Busy: another agent operation is active. Nothing was automatically retried."
    : error.status === 404 ? "Conversation unavailable or not owned by this session. Binding cleared; sending blocked. No other conversation will be searched."
    : error.status === 400 || error.status === 422 ? "Message refused. Use 1–2000 characters of synthetic details."
    : conversationId && !submission ? "Status or submission outcome unknown. Do not resend. Check this conversation's status."
    : "Submission outcome unknown. Do not resend. Logout clears local state but does not cancel submitted work.");
  controls();
}
async function readChat(epoch, session) {
  try {
    const row = parseChatSnapshot(await api(`/api/chat/conversations/${encodeURIComponent(conversationId)}`,
      {signal: chatController.signal}));
    if (!chatCurrent(epoch, session)) return;
    $("chat-transcript").replaceChildren(...row.messages.map(chatBubble)); scrollChat();
    if (row.status === "queued" || row.status === "running") {
      $("chat-status").textContent = row.status === "queued" ? "Queued. Waiting for the service agent…" : "Thinking… Service agent is working.";
      chatPolling = setTimeout(() => readChat(epoch, session), 2000); return;
    }
    stopChat(); chatUncertain = false;
    $("chat-status").textContent = row.status === "completed"
      ? "Agent reply received. Advice only; no refunds or orders executed."
      : "Conversation turn failed. No success claimed. History preserved.";
    chatError(row.status === "failed" ? "The hosted agent could not complete this turn. No successful action is implied." : "");
    controls();
  } catch (error) { if (chatCurrent(epoch, session)) chatFailure(error); }
}
$("chat-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!account || chatBusy || chatUncertain) return;
  const message = $("chat-message").value.trim();
  if (!message || message.length > 2000) {
    $("chat-message").setAttribute("aria-invalid", "true");
    chatError("Enter 1–2000 characters of synthetic details."); return;
  }
  $("chat-message").removeAttribute("aria-invalid"); chatError("");
  const epoch = ++chatEpoch, session = generation;
  submissionPending = true;
  startChatWait(epoch, session);
  $("chat-status").textContent = "Submitting synthetic message…";
  $("chat-transcript > .empty")?.remove();
  const bubble = chatBubble({role: "user", content: message});
  $("chat-transcript").append(bubble); scrollChat();
  try {
    const row = await api("/api/chat/messages", {method: "POST",
      body: JSON.stringify({message, conversation_id: conversationId}), signal: chatController.signal});
    if (!chatCurrent(epoch, session)) return;
    if (!row || !uuid.test(row.conversation_id) || !uuid.test(row.turn_id)
      || row.status !== "queued" || (conversationId && row.conversation_id !== conversationId)) throw new Error("Invalid submission response.");
    conversationId = row.conversation_id;
    submissionPending = false;
    if ($("chat-message").value.trim() === message) $("chat-message").value = "";
    readChat(epoch, session);
  } catch (error) {
    if (chatCurrent(epoch, session)) {
      if ([400, 422, 429, 503].includes(error.status)) bubble.remove();
      chatFailure(error, true);
    }
  }
});
$("chat-message").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault(); $("chat-form").requestSubmit();
  }
});
$("chat-check").addEventListener("click", () => {
  if (!conversationId || chatBusy || !account) return;
  chatError("");
  const epoch = ++chatEpoch, session = generation;
  submissionPending = false;
  startChatWait(epoch, session);
  $("chat-status").textContent = "Checking known conversation. Your message is not being resent.";
  readChat(epoch, session);
});
prepareAuth();
