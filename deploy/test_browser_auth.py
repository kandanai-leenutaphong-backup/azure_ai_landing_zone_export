from copy import deepcopy

import pytest

import browser_auth
import manage


def test_registration_reuse_preserves_api_contract_despite_provider_list_order(monkeypatch):
    settings = manage.config("sea")
    scope_id = "scope-id"
    new_client = "browser-id"
    api = {"id": "api-object", "identifierUris": ["api://existing"], "signInAudience": "AzureADMyOrg",
           "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [
               {"id": scope_id, "value": "access_as_user", "isEnabled": True},
           ], "preAuthorizedApplications": [{"appId": "old-client", "delegatedPermissionIds": [scope_id]}]}}
    browser = {"id": "browser-object", "appId": new_client, "displayName": browser_auth.NAME,
               "tags": [manage.OWNER], "signInAudience": "AzureADMyOrg",
               "spa": {"redirectUris": [f"https://{settings['PUBLIC_HOST']}/auth/callback", "http://localhost:8080/auth/callback"]},
               "requiredResourceAccess": [{"resourceAppId": settings["AUTH_CLIENT_ID"],
                                          "resourceAccess": [{"id": scope_id, "type": "Scope"}]}]}
    state = deepcopy(api)
    writes = []

    def call(*args):
        if args[:2] == ("account", "show"):
            return {"tenant": settings["TENANT_ID"], "cloud": "AzureCloud"}
        if args[:3] == ("ad", "app", "show"):
            return deepcopy(state if args[args.index("--id") + 1] == settings["AUTH_CLIENT_ID"] else browser)
        if args[:3] == ("ad", "app", "list"):
            return [deepcopy(browser)]
        if args[:3] == ("ad", "sp", "list"):
            return [{"appId": new_client}]
        if args[:3] == ("rest", "--method", "patch"):
            import json
            writes.append(args)
            state["api"] = json.loads(args[args.index("--body") + 1])["api"]
            state["api"]["preAuthorizedApplications"].reverse()
            return None
        pytest.fail(f"Unexpected mutation or lookup: {args[:3]}")

    monkeypatch.setattr(browser_auth, "az", call)
    assert browser_auth.configure(settings)["client_id"] == new_client
    assert len(writes) == 1
    assert len(state["api"]["preAuthorizedApplications"]) == 2
    assert state["api"]["oauth2PermissionScopes"] == api["api"]["oauth2PermissionScopes"]
    browser_auth.configure(settings)
    assert len(writes) == 1
