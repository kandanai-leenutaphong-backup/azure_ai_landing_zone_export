from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manage


def gateway():
    return {
        "location": "southeastasia", "tags": {"existing": "keep"}, "etag": 'W/"original"',
        "properties": {
            "provisioningState": "Succeeded", "operationalState": "Running",
            "firewallPolicy": {"id": "/existing-waf"},
            "frontendIPConfigurations": [{
                "name": "publicFrontend", "id": "/public",
                "properties": {"publicIPAddress": {"id": "/publicIPAddresses/agw-thai-search-sea-pip"}},
            }],
            "frontendPorts": [{"name": "httpPort", "properties": {"port": 80}}],
            "httpListeners": [{"name": "publicHttpListener", "properties": {"protocol": "Http"}}],
            "backendAddressPools": [{"name": "thaiSurnameBackend", "properties": {"backendAddresses": [{"fqdn": "old.internal"}]}}],
            "requestRoutingRules": [{"name": "thaiSurnameRule", "properties": {"priority": 100}}],
        },
    }


def app(ready=True):
    return {"properties": {
        "latestReadyRevisionName": "app--1",
        "latestRevisionName": "app--1" if ready else "app--2",
        "configuration": {"ingress": {"fqdn": "new.internal"}},
    }}


def test_additive_route_preserves_existing_gateway_and_conditional_write():
    settings = manage.config("sea")
    original = gateway()
    calls = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pfx = root / "certificate.pfx"
        pfx.write_bytes(b"synthetic-test-certificate")
        with patch.object(manage, "STATE", root), patch.object(manage.Deployment, "preflight"), \
                patch.object(manage.Deployment, "app", return_value=app()), \
                patch.object(manage.Deployment, "gateway", side_effect=lambda: copy.deepcopy(original)), \
                patch.object(manage.Deployment, "certificate", return_value=pfx):
            deployment = manage.Deployment(settings)

            def fake_az(*args):
                calls.append(args)
                if args[:3] == ("rest", "--method", "put"):
                    assert args[args.index("--headers") + 1] == 'If-Match=W/"original"'
                    payload = json.loads(Path(args[args.index("--body") + 1][1:]).read_text())
                    for collection in ("frontendIPConfigurations", "httpListeners", "backendAddressPools", "requestRoutingRules"):
                        assert original["properties"][collection][0] in payload["properties"][collection]
                    rules = payload["properties"]["requestRoutingRules"]
                    assert {rule["properties"]["priority"] for rule in rules} == {40, 41, 100}
                    assert payload["properties"]["firewallPolicy"] == {"id": "/existing-waf"}
                    assert payload["tags"] == {"existing": "keep"}
                    return OWNER
                if args[:3] == ("network", "public-ip", "show"):
                    return "203.0.113.8"
                if args[:4] == ("network", "dns", "record-set", "list"):
                    return []
                return None

            OWNER = "customer-service-multi-agent"
            with patch.object(manage, "az", side_effect=fake_az):
                deployment.route()
    assert any(call[:3] == ("rest", "--method", "put") for call in calls)
    assert not any("delete" in call for call in calls)


@pytest.mark.parametrize("failure", ["unready", "priority", "foreign-dns"])
def test_route_refuses_unsafe_adoption(failure):
    original = gateway()
    if failure == "priority":
        original["properties"]["requestRoutingRules"].append({"name": "foreign", "properties": {"priority": 40}})
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pfx = root / "certificate.pfx"
        pfx.write_bytes(b"test")
        with patch.object(manage, "STATE", root), patch.object(manage.Deployment, "preflight"), \
                patch.object(manage.Deployment, "app", return_value=app(failure != "unready")), \
                patch.object(manage.Deployment, "gateway", side_effect=lambda: copy.deepcopy(original)), \
                patch.object(manage.Deployment, "certificate", return_value=pfx):
            deployment = manage.Deployment(manage.config("sea"))
            calls = []

            def fake_az(*args):
                calls.append(args)
                if args[:3] == ("network", "public-ip", "show"):
                    return "203.0.113.8"
                if args[:4] == ("network", "dns", "record-set", "list"):
                    return [{"metadata": {}, "aRecords": [{"ipv4Address": "203.0.113.8"}]}] if failure == "foreign-dns" else []
                return None

            with patch.object(manage, "az", side_effect=fake_az), pytest.raises(RuntimeError):
                deployment.route()
            if failure == "unready":
                assert not calls
            assert not any(call[:3] == ("rest", "--method", "put") for call in calls)
            assert not any(call[:5] == ("network", "dns", "record-set", "a", "add-record") for call in calls)


def test_preflight_refuses_wrong_tenant_before_target_mutation():
    with tempfile.TemporaryDirectory() as temporary, patch.object(manage, "STATE", Path(temporary)):
        deployment = manage.Deployment(manage.config("sea"))
        with patch.object(manage, "az", return_value={"subscription": "foreign", "tenant": "foreign", "cloud": "AzureCloud"}) as cli:
            with pytest.raises(RuntimeError, match="configured tenant"):
                deployment.preflight()
            assert cli.call_count == 1


def test_runtime_readback_checks_browser_user_and_workload_identity_configuration(tmp_path):
    settings = manage.config("sea")
    settings.pop("HOSTED_AGENT_NAME", None)
    settings.pop("HOSTED_AGENT_VERSION", None)
    identity = (
        f"/subscriptions/{settings['APP_SUBSCRIPTION_ID']}/resourceGroups/{settings['APP_RESOURCE_GROUP']}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{settings['IDENTITY_NAME']}"
    )
    values = {
        name: settings[name] for name in (
            "TENANT_ID", "AUTH_CLIENT_ID", "BROWSER_CLIENT_ID", "AZURE_CLIENT_ID",
            "FOUNDRY_PROJECT_ENDPOINT", "MODEL_DEPLOYMENT",
        )
    }
    values.update(AZURE_AUTH_MODE="managed_identity", AUTH_ALLOWED_OBJECT_IDS="existing-allowlist")
    actual = {"identity": {"type": "UserAssigned", "userAssignedIdentities": {identity: {}}},
              "properties": {"template": {"containers": [{"env": [
                  {"name": name, "value": value} for name, value in values.items()
              ]}]}}}
    with patch.object(manage, "STATE", tmp_path):
        deployment = manage.Deployment(settings)
        assert deployment.verify_runtime_configuration(actual)["hosted_chat_configured"] is False
        for name, value in (("BROWSER_CLIENT_ID", "wrong-client"), ("AZURE_AUTH_MODE", "azure_cli"),
                            ("AUTH_ALLOWED_OBJECT_IDS", ""), ("HOSTED_AGENT_NAME", "foreign-agent")):
            changed = copy.deepcopy(actual)
            changed["properties"]["template"]["containers"][0]["env"].append({"name": name, "value": value})
            with pytest.raises(RuntimeError):
                deployment.verify_runtime_configuration(changed)


def test_missing_gold_blocks_before_control_plane_or_inference(tmp_path):
    with patch.object(manage, "STATE", tmp_path), patch.object(manage, "APP", tmp_path / "app"):
        deployment = manage.Deployment(manage.config("sea"))
        with patch.object(deployment, "app") as read_app, patch.object(manage, "command") as inference:
            with pytest.raises(RuntimeError, match="No calibrated gold"):
                deployment.regression()
        read_app.assert_not_called()
        inference.assert_not_called()
        assert json.loads((tmp_path / "regression-report.json").read_text())["model_calls"] == 0


@pytest.mark.parametrize("authorized", [True, False])
def test_configure_local_creates_private_file_without_expanding_access(tmp_path, authorized):
    settings = manage.config("sea")
    application = tmp_path / "app"
    application.mkdir()
    (application / ".env-template").write_text(
        "TENANT_ID=\nAUTH_ALLOWED_OBJECT_IDS=\nAZURE_AUTH_MODE=azure_cli\n"
    )
    deployed = {"tags": {"project": manage.OWNER}, "properties": {"template": {"containers": [{"env": [
        {"name": "TENANT_ID", "value": settings["TENANT_ID"]},
        {"name": "AUTH_ALLOWED_OBJECT_IDS", "value": "existing-owner"},
    ]}]}}}
    with patch.object(manage, "APP", application), patch.object(manage, "STATE", tmp_path), \
            patch.object(manage.Deployment, "app", return_value=deployed), \
            patch.object(manage, "az", return_value="existing-owner" if authorized else "unlisted-user"):
        deployment = manage.Deployment(settings)
        destination = application / ".env"
        if authorized:
            deployment.configure_local()
            original = destination.read_text()
            assert "AZURE_AUTH_MODE=azure_cli" in original
            assert destination.stat().st_mode & 0o777 == 0o600
            deployment.configure_local()
            assert destination.read_text() == original
            destination.write_text("CUSTOM_SETTING=preserve\n")
            with pytest.raises(RuntimeError, match="preserve and review"):
                deployment.configure_local()
            assert destination.read_text() == "CUSTOM_SETTING=preserve\n"
        else:
            with pytest.raises(RuntimeError, match="not in the app allowlist"):
                deployment.configure_local()
            assert not destination.exists()


@pytest.mark.parametrize("has_allowlist", [True, False])
def test_existing_app_preflight_preserves_allowlist_without_human_graph_lookup(tmp_path, has_allowlist):
    settings = manage.config("sea")
    calls = []

    def read(*args):
        calls.append(args)
        if args[:2] == ("account", "show"):
            return {"subscription": settings["HUB_SUBSCRIPTION_ID"], "tenant": settings["TENANT_ID"], "cloud": "AzureCloud"}
        if args[:3] == ("containerapp", "env", "show"):
            return {"properties": {"vnetConfiguration": {"internal": True}}}
        if args[:3] == ("network", "vnet", "subnet"):
            return settings["HUB_FIREWALL_SOURCE_PREFIX"]
        if args[:3] == ("cognitiveservices", "account", "show"):
            return {"location": "westus3", "properties": {"publicNetworkAccess": "Disabled"}}
        if args[:2] == ("containerapp", "list"):
            return [{"name": manage.OWNER, "tags": {"project": manage.OWNER}}]
        if args[:3] == ("rest", "--method", "get"):
            return {"properties": {"policySettings": {"mode": "Prevention", "state": "Enabled"}}}
        if args[:2] == ("containerapp", "show"):
            return {"properties": {"template": {"containers": [{"env": [{
                "name": "AUTH_ALLOWED_OBJECT_IDS", "value": "existing-owner" if has_allowlist else "",
            }]}]}}}
        if args[:2] == ("ad", "signed-in-user"):
            pytest.fail("Existing app deployment must not require a human Graph identity.")
        return None

    with patch.object(manage, "STATE", tmp_path), patch.object(manage, "az", side_effect=read), \
            patch.object(manage.Deployment, "gateway", return_value=gateway()), patch.object(manage.shutil, "which", return_value="/existing/tool"):
        deployment = manage.Deployment(settings)
        if has_allowlist:
            deployment.preflight()
        else:
            with pytest.raises(RuntimeError, match="explicit allowlist"):
                deployment.preflight()
