from __future__ import annotations

from copy import deepcopy

from manage import OWNER, az

NAME = "customer-service-multi-agent-web"
GRAPH = "https://graph.microsoft.com/v1.0"


def normalized_api(api: dict) -> dict:
    result = deepcopy(api)
    result["preAuthorizedApplications"] = sorted([
        {**entry, "delegatedPermissionIds": sorted(entry["delegatedPermissionIds"])}
        for entry in result.get("preAuthorizedApplications") or []
    ], key=lambda entry: entry["appId"])
    return result


def configure(settings: dict) -> dict:
    account = az("account", "show", "--query", "{tenant:tenantId,cloud:environmentName}")
    if account != {"tenant": settings["TENANT_ID"], "cloud": "AzureCloud"}:
        raise RuntimeError("Select the configured tenant in AzureCloud before changing browser authentication.")
    api = az("ad", "app", "show", "--id", settings["AUTH_CLIENT_ID"])
    scopes = [scope for scope in api["api"]["oauth2PermissionScopes"]
              if scope["value"] == "access_as_user" and scope["isEnabled"]]
    if len(scopes) != 1 or api["signInAudience"] != "AzureADMyOrg":
        raise RuntimeError("Existing tenant-only API delegated scope does not match the approved contract.")
    scope_id = scopes[0]["id"]
    redirects = [f"https://{settings['PUBLIC_HOST']}/auth/callback", "http://localhost:8080/auth/callback"]
    access = [{"resourceAppId": settings["AUTH_CLIENT_ID"],
               "resourceAccess": [{"id": scope_id, "type": "Scope"}]}]
    existing = az("ad", "app", "list", "--display-name", NAME)
    existing = [app for app in existing if app["displayName"] == NAME]
    if len(existing) > 1:
        raise RuntimeError("Multiple browser registrations have the same name; reconcile before creating another.")
    if existing:
        browser = existing[0]
        if OWNER not in browser.get("tags", []):
            raise RuntimeError("Existing browser registration belongs to another owner.")
        if (browser["signInAudience"] != "AzureADMyOrg" or
                set(browser["spa"]["redirectUris"]) != set(redirects) or
                browser["requiredResourceAccess"] != access or
                browser.get("passwordCredentials") or browser.get("keyCredentials")):
            raise RuntimeError("Existing browser registration differs from the approved secretless SPA configuration.")
    else:
        import json
        browser = az("rest", "--method", "post", "--url", f"{GRAPH}/applications", "--body", json.dumps({
            "displayName": NAME, "signInAudience": "AzureADMyOrg",
            "tags": [OWNER], "spa": {"redirectUris": redirects},
            "requiredResourceAccess": access, "isFallbackPublicClient": False,
        }))
    principals = az("ad", "sp", "list", "--filter", f"appId eq '{browser['appId']}'")
    if len(principals) > 1:
        raise RuntimeError("Ambiguous browser service principal.")
    if not principals:
        az("ad", "sp", "create", "--id", browser["appId"])
    original = deepcopy(api["api"])
    current = original.get("preAuthorizedApplications") or []
    matching = [entry for entry in current if entry["appId"] == browser["appId"]]
    if matching and matching != [{"appId": browser["appId"], "delegatedPermissionIds": [scope_id]}]:
        raise RuntimeError("Existing client preauthorization has an unexpected permission set.")
    expected = deepcopy(original)
    if not matching:
        import json
        expected["preAuthorizedApplications"] = current + [
            {"appId": browser["appId"], "delegatedPermissionIds": [scope_id]},
        ]
        az("rest", "--method", "patch", "--url", f"{GRAPH}/applications/{api['id']}",
           "--body", json.dumps({"api": expected}))
    confirmed_api = az("ad", "app", "show", "--id", settings["AUTH_CLIENT_ID"])
    confirmed_browser = az("ad", "app", "show", "--id", browser["appId"])
    if normalized_api(confirmed_api["api"]) != normalized_api(expected) or confirmed_api["identifierUris"] != api["identifierUris"]:
        raise RuntimeError("API preauthorization readback differs; existing permission contract must be preserved.")
    if (set(confirmed_browser["spa"]["redirectUris"]) != set(redirects) or
            confirmed_browser["requiredResourceAccess"] != access or
            confirmed_browser["signInAudience"] != "AzureADMyOrg" or
            confirmed_browser.get("passwordCredentials") or confirmed_browser.get("keyCredentials")):
        raise RuntimeError("Browser registration readback did not preserve secretless tenant-only configuration.")
    return {
        "client_id": browser["appId"], "object_id": browser["id"],
        "tenant_id": settings["TENANT_ID"], "redirect_uris": redirects,
        "api_client_id": settings["AUTH_CLIENT_ID"], "delegated_scope": "access_as_user",
        "client_secrets": False, "foundry_rbac_changed": False,
    }
