from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from certificate import ensure_certificate

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "applications/customer-service-multi-agent"
STATE = ROOT / "deploy/.state"
API_VERSION = "2024-05-01"
OWNER = "customer-service-multi-agent"
CONFIG_KEYS = {
    "TENANT_ID", "HUB_SUBSCRIPTION_ID", "HUB_RESOURCE_GROUP", "APP_SUBSCRIPTION_ID",
    "APP_RESOURCE_GROUP", "APP_LOCATION", "APP_NAME", "CONTAINER_ENVIRONMENT", "REGISTRY",
    "IDENTITY_NAME", "AZURE_CLIENT_ID", "AUTH_CLIENT_ID", "FOUNDRY_SUBSCRIPTION_ID",
    "FOUNDRY_RESOURCE_GROUP", "FOUNDRY_ACCOUNT", "FOUNDRY_PROJECT", "FOUNDRY_PROJECT_ENDPOINT",
    "MODEL_DEPLOYMENT", "GATEWAY", "GATEWAY_PUBLIC_IP", "DNS_SUBSCRIPTION_ID",
    "DNS_RESOURCE_GROUP", "DNS_ZONE", "DNS_LABEL", "PUBLIC_HOST", "ACME_DIRECTORY",
    "GATEWAY_NSG", "HUB_FIREWALL_SOURCE_PREFIX",
    "LOG_ANALYTICS_WORKSPACE_ID",
}
OPTIONAL_CONFIG_KEYS = {"BROWSER_CLIENT_ID", "HOSTED_AGENT_NAME", "HOSTED_AGENT_VERSION",
                        "APP_INSIGHTS_NAME", "AGENT_VNET", "REPLAY_OPERATOR_OBJECT_IDS",
                        "FOUNDRY_COSMOS_ACCOUNT", "FOUNDRY_COSMOS_CONTAINER"}


def command(args: list[str], *, output: bool = False, env: dict | None = None) -> str:
    result = subprocess.run(args, text=True, capture_output=True, env=env)
    if output and result.stdout:
        print(result.stdout, end="", flush=True)
    if result.returncode:
        # Command arguments may include a credential file reference; never echo them.
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def az(*args: str):
    text = command(["az", *args, "--only-show-errors", "-o", "json"])
    return json.loads(text) if text else None


def config(environment: str) -> dict[str, str]:
    if environment != "sea":
        raise ValueError("Only the reviewed 'sea' environment is supported.")
    values = {}
    for line in (ROOT / "deploy/env/sea.env").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key not in CONFIG_KEYS | OPTIONAL_CONFIG_KEYS or key in values or not value.strip():
            raise ValueError(f"Unknown, repeated, or empty deployment field: {key}")
        values[key] = value
    if not CONFIG_KEYS.issubset(values):
        raise ValueError(f"Missing deployment fields: {sorted(CONFIG_KEYS - set(values))}")
    if values["APP_NAME"] != OWNER or values["PUBLIC_HOST"] != f"{values['DNS_LABEL']}.{values['DNS_ZONE']}":
        raise ValueError("App ownership or public DNS target differs from the reviewed scope.")
    if values["APP_LOCATION"] != "southeastasia" or ".services.ai.azure.com/api/projects/" not in values["FOUNDRY_PROJECT_ENDPOINT"]:
        raise ValueError("Expected SEA hosting and a private Foundry project endpoint.")
    return values


class Deployment:
    def __init__(self, settings: dict[str, str]):
        self.c = settings
        self.app_scope = ["--subscription", settings["APP_SUBSCRIPTION_ID"], "-g", settings["APP_RESOURCE_GROUP"]]
        self.hub_scope = ["--subscription", settings["HUB_SUBSCRIPTION_ID"], "-g", settings["HUB_RESOURCE_GROUP"]]
        self.dns_scope = [
            "--subscription", settings["DNS_SUBSCRIPTION_ID"], "-g", settings["DNS_RESOURCE_GROUP"],
            "-z", settings["DNS_ZONE"],
        ]
        self.gateway_id = (
            f"/subscriptions/{settings['HUB_SUBSCRIPTION_ID']}/resourceGroups/{settings['HUB_RESOURCE_GROUP']}"
            f"/providers/Microsoft.Network/applicationGateways/{settings['GATEWAY']}"
        )
        STATE.mkdir(exist_ok=True)

    def app(self) -> dict:
        return az("containerapp", "show", *self.app_scope, "-n", self.c["APP_NAME"])

    def browser_auth(self) -> None:
        from browser_auth import configure
        receipt = configure(self.c)
        (STATE / "browser-auth.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2), flush=True)

    def configure_local(self) -> None:
        from dotenv import dotenv_values

        app = self.app()
        if app.get("tags", {}).get("project") != OWNER:
            raise RuntimeError("Refusing local configuration from an app with different ownership.")
        deployed = {
            item["name"]: item["value"]
            for item in app["properties"]["template"]["containers"][0]["env"]
            if "value" in item
        }
        if deployed.get("TENANT_ID") != self.c["TENANT_ID"]:
            raise RuntimeError("Deployed app tenant differs from the reviewed target.")
        operator = az("ad", "signed-in-user", "show", "--query", "id")
        if operator not in [value.strip() for value in deployed.get("AUTH_ALLOWED_OBJECT_IDS", "").split(",")]:
            raise RuntimeError("Current Azure CLI user is not in the app allowlist. No access was granted.")
        local = {
            "AZURE_AUTH_MODE": "azure_cli", "APP_REVISION": "local",
            "SQLITE_PATH": "/tmp/customer-service-multi-agent-local.sqlite3",
        }
        names = dotenv_values(APP / ".env-template", interpolate=False)
        values = {}
        for name in names:
            value = local[name] if name in local else deployed.get(name)
            if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\0"):
                raise RuntimeError(f"Missing or invalid non-secret deployed configuration: {name}")
            values[name] = value
        destination = APP / ".env"
        if destination.is_symlink():
            raise RuntimeError("Refusing a symlinked local environment file.")
        if destination.exists():
            if dict(dotenv_values(destination, interpolate=False)) != values:
                raise RuntimeError("Existing .env differs; preserve and review it rather than overwriting local changes.")
            destination.chmod(0o600)
            print(f"Local environment already matches deployed configuration: {destination}", flush=True)
            return
        with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
            handle.write("# Local targets only. Tokens stay in Azure CLI/browser memory, never this file.\n")
            handle.writelines(f"{name}={value}\n" for name, value in values.items())
        print(f"Created private .env from deployed settings: {destination}. Azure CLI authentication; no tokens saved.", flush=True)

    def gateway(self) -> dict:
        return az(
            "rest", "--method", "get", "--url",
            f"https://management.azure.com{self.gateway_id}?api-version={API_VERSION}",
        )

    def preflight(self) -> None:
        for tool in ("az", "dig"):
            if not shutil.which(tool):
                raise RuntimeError(f"Required tool absent: {tool}. Install it before deployment.")
        account = az("account", "show", "--query", "{subscription:id,tenant:tenantId,cloud:environmentName}")
        if account != {
            "subscription": self.c["HUB_SUBSCRIPTION_ID"], "tenant": self.c["TENANT_ID"], "cloud": "AzureCloud",
        }:
            raise RuntimeError("Select AzureCloud and the configured tenant/hub subscription before deployment.")
        environment = az("containerapp", "env", "show", *self.app_scope, "-n", self.c["CONTAINER_ENVIRONMENT"])
        if not environment["properties"]["vnetConfiguration"]["internal"]:
            raise RuntimeError("Refusing a public Container Apps environment.")
        firewall_subnet = az(
            "network", "vnet", "subnet", "show", *self.hub_scope, "--vnet-name", "vnet-hub-2",
            "-n", "AzureFirewallSubnet", "--query", "addressPrefix",
        )
        if firewall_subnet != self.c["HUB_FIREWALL_SOURCE_PREFIX"]:
            raise RuntimeError("Firewall ingress source must equal the existing dedicated AzureFirewallSubnet.")
        foundry = az(
            "cognitiveservices", "account", "show", "--subscription", self.c["FOUNDRY_SUBSCRIPTION_ID"],
            "-g", self.c["FOUNDRY_RESOURCE_GROUP"], "-n", self.c["FOUNDRY_ACCOUNT"],
        )
        if foundry["location"].lower().replace(" ", "") != "westus3" or foundry["properties"]["publicNetworkAccess"] != "Disabled":
            raise RuntimeError("Expected an existing private West US 3 Foundry account.")
        existing = az("containerapp", "list", *self.app_scope, "--query", f"[?name=='{OWNER}'].{{name:name,tags:tags}}")
        if existing and existing[0].get("tags", {}).get("project") != OWNER:
            raise RuntimeError("Container App name already owned elsewhere; refusing adoption.")
        gateway = self.gateway()
        policy_id = gateway["properties"]["firewallPolicy"]["id"]
        policy = az("rest", "--method", "get", "--url", f"https://management.azure.com{policy_id}?api-version={API_VERSION}")
        if policy["properties"]["policySettings"]["mode"] != "Prevention" or policy["properties"]["policySettings"]["state"] != "Enabled":
            raise RuntimeError("Hub WAF must already be enabled in Prevention mode.")
        az("network", "dns", "zone", "show", "--subscription", self.c["DNS_SUBSCRIPTION_ID"], "-g", self.c["DNS_RESOURCE_GROUP"], "-n", self.c["DNS_ZONE"], "--query", "id")
        if not existing:
            operator = az("ad", "signed-in-user", "show", "--query", "id")
            if not operator:
                raise RuntimeError("A signed-in human is required to establish the initial project allowlist.")
        else:
            entries = self.app()["properties"]["template"]["containers"][0].get("env", [])
            if not any(entry["name"] == "AUTH_ALLOWED_OBJECT_IDS" and entry.get("value") for entry in entries):
                raise RuntimeError("Existing app has no explicit allowlist; refusing automated adoption.")
        print("Preflight: private SEA host, private West US 3 Foundry, existing WAF and DNS targets confirmed.", flush=True)

    def build(self) -> None:
        command([sys.executable, "-m", "pytest", "-q", str(APP), str(ROOT / "deploy")], output=True)
        inputs = ["Dockerfile", "requirements.txt", ".dockerignore"]
        inputs += sorted(str(p.relative_to(APP)) for p in APP.rglob("*.py") if "__pycache__" not in p.parts)
        inputs += sorted(str(p.relative_to(APP)) for p in (APP / "static").rglob("*") if p.is_file()) if (APP / "static").exists() else []
        digest = hashlib.sha256()
        for name in inputs:
            digest.update(name.encode() + b"\0" + (APP / name).read_bytes())
        tag = digest.hexdigest()[:20]
        repository = f"{OWNER}:{tag}"
        print(f"Building checked source {digest.hexdigest()}.", flush=True)
        az("acr", "build", "--subscription", self.c["APP_SUBSCRIPTION_ID"], "-r", self.c["REGISTRY"], "-t", repository, str(APP), "--no-logs")
        manifest = az(
            "acr", "repository", "show", "--subscription", self.c["APP_SUBSCRIPTION_ID"],
            "-n", self.c["REGISTRY"], "--image", repository,
        )
        image = f"{self.c['REGISTRY']}.azurecr.io/{OWNER}@{manifest['digest']}"
        (STATE / "image.json").write_text(json.dumps({"image": image, "source_sha256": digest.hexdigest(), "tag": tag}, indent=2))
        print(f"Accepted image: {image}", flush=True)

    def provision_agents(self) -> None:
        env = dict(os.environ, FOUNDRY_PROJECT_ENDPOINT=self.c["FOUNDRY_PROJECT_ENDPOINT"], MODEL_DEPLOYMENT=self.c["MODEL_DEPLOYMENT"])
        output = command([sys.executable, str(APP / "provision_agents.py"), "--apply"], output=True, env=env)
        receipt, _ = json.JSONDecoder().raw_decode(output)
        if receipt["project"] != self.c["FOUNDRY_PROJECT_ENDPOINT"]:
            raise RuntimeError("Provisioned agent project differs from the reviewed target.")
        (STATE / "agent-pins.json").write_text(json.dumps(receipt, indent=2))

    def provision_hosted(self) -> None:
        self.preflight()
        from hosted_agent import provision
        receipt = provision(self.c)
        self.c.update(HOSTED_AGENT_NAME=receipt["name"], HOSTED_AGENT_VERSION=receipt["version"])
        print(json.dumps(receipt, indent=2), flush=True)

    def release(self) -> None:
        self.preflight()
        if not self.c.get("BROWSER_CLIENT_ID"):
            raise RuntimeError("Run setup-browser-auth and commit the returned BROWSER_CLIENT_ID target before release.")
        hosted_name, hosted_version = self.c.get("HOSTED_AGENT_NAME", ""), self.c.get("HOSTED_AGENT_VERSION", "")
        if bool(hosted_name) != bool(hosted_version):
            raise RuntimeError("Hosted agent name and version must be configured together.")
        if hosted_name:
            if hosted_name != "cs-customer-service-chat" or not hosted_version.isdecimal() or int(hosted_version) < 1:
                raise RuntimeError("Expected the app-owned hosted chat agent and an explicit positive version.")
            receipt = json.loads((STATE / "hosted-agent.json").read_text())
            if receipt["name"] != hosted_name or receipt["version"] != hosted_version or receipt["status"] != "active":
                raise RuntimeError("Configured hosted agent differs from the verified active source receipt.")
        image = json.loads((STATE / "image.json").read_text())["image"]
        existing = az("containerapp", "list", *self.app_scope, "--query", f"[?name=='{OWNER}']")
        if existing:
            current_env = {
                e["name"]: e.get("value", "") for e in existing[0]["properties"]["template"]["containers"][0].get("env", [])
            }
            allowed = current_env.get("AUTH_ALLOWED_OBJECT_IDS")
            if not allowed:
                raise RuntimeError("Existing app has no explicit allowlist; refusing to replace its authentication.")
        else:
            allowed = az("ad", "signed-in-user", "show", "--query", "id")
        parameters = {
            "location": self.c["APP_LOCATION"], "appName": OWNER, "environmentName": self.c["CONTAINER_ENVIRONMENT"],
            "registryName": self.c["REGISTRY"], "identityName": self.c["IDENTITY_NAME"], "image": image,
            "tenantId": self.c["TENANT_ID"], "authClientId": self.c["AUTH_CLIENT_ID"], "allowedObjectIds": allowed,
            "managedIdentityClientId": self.c["AZURE_CLIENT_ID"], "projectEndpoint": self.c["FOUNDRY_PROJECT_ENDPOINT"],
            "modelDeployment": self.c["MODEL_DEPLOYMENT"],
            "agentVersions": json.dumps({
                key: pin["version"] for key, pin in json.loads((STATE / "agent-pins.json").read_text())["pins"].items()
            }),
            "hubFirewallSourcePrefix": self.c["HUB_FIREWALL_SOURCE_PREFIX"],
            "browserClientId": self.c["BROWSER_CLIENT_ID"],
            "hostedAgentName": hosted_name,
            "hostedAgentVersion": hosted_version,
            "appInsightsName": self.c.get("APP_INSIGHTS_NAME", ""),
            "replayOperatorObjectIds": self.c.get("REPLAY_OPERATOR_OBJECT_IDS", ""),
        }
        az(
            "deployment", "group", "create", *self.app_scope, "-n", OWNER,
            "--template-file", str(ROOT / "deploy/infra/customer-service.bicep"), "--parameters",
            *[f"{key}={value}" for key, value in parameters.items()], "--query", "properties.provisioningState",
        )
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            app = self.app()
            properties = app["properties"]
            if properties.get("latestReadyRevisionName") == properties.get("latestRevisionName") and properties.get("runningStatus") == "Running":
                actual_image = properties["template"]["containers"][0]["image"]
                if actual_image != image:
                    raise RuntimeError("Ready revision differs from accepted immutable image.")
                print(f"Ready: {properties['latestReadyRevisionName']} {actual_image}", flush=True)
                return
            time.sleep(5)
        raise TimeoutError("Accepted Container App revision did not become ready within 360 seconds.")

    def hosted_principal(self) -> str:
        from azure.ai.projects import AIProjectClient
        from azure.identity import AzureCliCredential
        with AzureCliCredential(tenant_id=self.c["TENANT_ID"]) as credential, AIProjectClient(
            endpoint=self.c["FOUNDRY_PROJECT_ENDPOINT"], credential=credential, allow_preview=True,
        ) as project:
            agent = project.agents.get(agent_name=self.c["HOSTED_AGENT_NAME"]).as_dict()
        principal = agent.get("instance_identity", {}).get("principal_id")
        if not principal:
            raise RuntimeError("Hosted agent exposes no instance identity to authorize.")
        return principal

    def observability(self) -> None:
        """Entra-only App Insights export for the SEA app and the West US 3 Hosted Agent."""
        self.preflight()
        name = self.c.get("APP_INSIGHTS_NAME")
        if not name or not self.c.get("AGENT_VNET") or not self.c.get("HOSTED_AGENT_NAME"):
            raise RuntimeError("Set APP_INSIGHTS_NAME, AGENT_VNET and HOSTED_AGENT_NAME before observability.")
        component = az("monitor", "app-insights", "component", "show", *self.app_scope, "-a", name,
                       "--query", "{tags:tags,ingest:publicNetworkAccessForIngestion}")
        if (component.get("tags") or {}).get("project") != OWNER:
            raise RuntimeError("Application Insights component is not tagged for this project; refusing adoption.")
        app_principal = az("identity", "show", *self.app_scope, "-n", self.c["IDENTITY_NAME"], "--query", "principalId")
        hosted_principal = self.hosted_principal()
        vnet = (f"/subscriptions/{self.c['FOUNDRY_SUBSCRIPTION_ID']}/resourceGroups/{self.c['FOUNDRY_RESOURCE_GROUP']}"
                f"/providers/Microsoft.Network/virtualNetworks/{self.c['AGENT_VNET']}")
        parameters = {
            "appInsightsName": name, "appPrincipalId": app_principal, "hostedPrincipalId": hosted_principal,
            "agentVnetId": vnet, "foundrySubscriptionId": self.c["FOUNDRY_SUBSCRIPTION_ID"],
            "foundryResourceGroup": self.c["FOUNDRY_RESOURCE_GROUP"], "foundryAccount": self.c["FOUNDRY_ACCOUNT"],
            "foundryProject": self.c["FOUNDRY_PROJECT"],
        }
        state = az(
            "deployment", "group", "create", *self.app_scope, "-n", f"{OWNER}-observability",
            "--template-file", str(ROOT / "deploy/infra/observability.bicep"), "--parameters",
            *[f"{key}={value}" for key, value in parameters.items()], "--query", "properties.provisioningState",
        )
        appi_id = (f"/subscriptions/{self.c['APP_SUBSCRIPTION_ID']}/resourceGroups/{self.c['APP_RESOURCE_GROUP']}"
                   f"/providers/Microsoft.Insights/components/{name}")
        roles = az("role", "assignment", "list", "--scope", appi_id,
                   "--role", "Monitoring Metrics Publisher", "--query", "[].principalId")
        links = [az("network", "private-dns", "link", "vnet", "show", *self.app_scope, "-z", zone,
                    "-n", "link-vnet-spoke-agent-wus3", "--query", "virtualNetwork.id")
                 for zone in ("privatelink.monitor.azure.com", "privatelink.oms.opinsights.azure.com",
                              "privatelink.ods.opinsights.azure.com", "privatelink.agentsvc.azure-automation.net")]
        project = (f"https://management.azure.com/subscriptions/{self.c['FOUNDRY_SUBSCRIPTION_ID']}/resourceGroups/"
                   f"{self.c['FOUNDRY_RESOURCE_GROUP']}/providers/Microsoft.CognitiveServices/accounts/"
                   f"{self.c['FOUNDRY_ACCOUNT']}/projects/{self.c['FOUNDRY_PROJECT']}")
        connection = az("rest", "-m", "get", "-u", f"{project}/connections/{name}?api-version=2025-04-01-preview",
                        "--query", "{category:properties.category,target:properties.target,auth:properties.authType}")
        result = {
            "deployment": state, "component": appi_id, "ingestion_public": component.get("ingest"),
            "publishers": {"app": app_principal in roles, "hosted": hosted_principal in roles},
            "agent_vnet_dns_links": all(link and link.lower() == vnet.lower() for link in links),
            "foundry_connection": connection,
        }
        if not all(result["publishers"].values()) or not result["agent_vnet_dns_links"] or \
                connection.get("category") != "AppInsights" or connection.get("target", "").lower() != appi_id.lower():
            raise RuntimeError(f"Observability readback differs: {json.dumps(result)}")
        (STATE / "observability.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)

    def certificate(self) -> Path:
        self.preflight()
        challenge_name = f"_acme-challenge.{self.c['DNS_LABEL']}"

        def add(value: str) -> None:
            az("network", "dns", "record-set", "txt", "add-record", *self.dns_scope, "-n", challenge_name, "-v", value, "--query", "name")

        def remove(value: str) -> None:
            az("network", "dns", "record-set", "txt", "remove-record", *self.dns_scope, "-n", challenge_name, "-v", value, "--keep-empty-record-set", "--query", "name")

        def visible(value: str) -> bool:
            return value in command(["dig", "+short", "TXT", f"{challenge_name}.{self.c['DNS_ZONE']}"])

        private_dir = Path.home() / ".local/share/customer-service-multi-agent/tls"
        return ensure_certificate(self.c["ACME_DIRECTORY"], self.c["PUBLIC_HOST"], private_dir, add, visible, remove)

    def start_gateway(self) -> None:
        self.preflight()
        gateway = self.gateway()
        if gateway["properties"]["operationalState"] == "Stopped":
            az("network", "application-gateway", "start", *self.hub_scope, "-n", self.c["GATEWAY"])
        if self.gateway()["properties"]["operationalState"] != "Running":
            raise RuntimeError("Hub gateway did not settle in Running state.")
        print("Existing hub WAF gateway is Running.", flush=True)

    def network(self) -> None:
        self.preflight()
        public_ip = az("network", "public-ip", "show", *self.hub_scope, "-n", self.c["GATEWAY_PUBLIC_IP"], "--query", "ipAddress")
        rule_name = "AllowCustomerServiceHttps"
        rules = az("network", "nsg", "rule", "list", *self.hub_scope, "--nsg-name", self.c["GATEWAY_NSG"])
        expected = {
            "priority": 105, "direction": "Inbound", "access": "Allow", "protocol": "Tcp",
            "sourceAddressPrefix": "Internet", "destinationAddressPrefix": "10.0.5.0/24",
            "sourcePortRange": "*", "destinationPortRange": "443",
        }
        for rule in rules:
            if rule["name"] == rule_name and any(rule.get(key) != value for key, value in expected.items()):
                prior = dict(expected, destinationAddressPrefix=public_ip)
                if all(rule.get(key) == value for key, value in prior.items()) and rule.get("description", "").startswith("customer-service-multi-agent:"):
                    az(
                        "network", "nsg", "rule", "update", *self.hub_scope, "--nsg-name", self.c["GATEWAY_NSG"],
                        "-n", rule_name, "--destination-address-prefixes", "10.0.5.0/24", "--query", "name",
                    )
                else:
                    raise RuntimeError("Named HTTPS NSG rule already exists with different settings; refusing adoption.")
            if rule["name"] != rule_name and rule["priority"] == 105 and rule["direction"] == "Inbound":
                raise RuntimeError("NSG priority 105 is already owned elsewhere.")
        if not any(rule["name"] == rule_name for rule in rules):
            az(
                "network", "nsg", "rule", "create", *self.hub_scope, "--nsg-name", self.c["GATEWAY_NSG"],
                "-n", rule_name, "--priority", "105", "--direction", "Inbound", "--access", "Allow",
                "--protocol", "Tcp", "--source-address-prefixes", "Internet", "--source-port-ranges", "*",
                "--destination-address-prefixes", "10.0.5.0/24", "--destination-port-ranges", "443",
                "--description", "customer-service-multi-agent: TLS to the existing hub WAF public frontend only.",
                "--query", "name",
            )
        actual = az("network", "nsg", "rule", "show", *self.hub_scope, "--nsg-name", self.c["GATEWAY_NSG"], "-n", rule_name)
        if any(actual.get(key) != value for key, value in expected.items()):
            raise RuntimeError("HTTPS NSG readback differs from the narrowly scoped approved rule.")
        print("HTTPS allowed only to the existing dedicated hub WAF subnet.", flush=True)

    def route(self) -> None:
        self.preflight()
        app = self.app()
        if app["properties"].get("latestReadyRevisionName") != app["properties"].get("latestRevisionName"):
            raise RuntimeError("Refusing to publish an unready app.")
        backend = app["properties"]["configuration"]["ingress"]["fqdn"]
        public_ip = az("network", "public-ip", "show", *self.hub_scope, "-n", self.c["GATEWAY_PUBLIC_IP"], "--query", "ipAddress")
        record = az("network", "dns", "record-set", "list", *self.dns_scope, "--query", f"[?name=='{self.c['DNS_LABEL']}' && type=='Microsoft.Network/dnszones/A']")
        if record and (
            record[0].get("metadata", {}).get("project") != OWNER
            or {item["ipv4Address"] for item in record[0].get("aRecords", [])} != {public_ip}
        ):
            raise RuntimeError("DNS record already exists with foreign ownership or address.")
        pfx = self.certificate()
        gateway = self.gateway()
        properties = gateway["properties"]
        before = json.loads(json.dumps(properties))
        gateway_url = f"https://management.azure.com{self.gateway_id}?api-version={API_VERSION}"

        def ref(kind: str, name: str) -> dict:
            return {"id": f"{self.gateway_id}/{kind}/{name}"}

        def upsert(collection: str, name: str, body: dict) -> None:
            items = properties.setdefault(collection, [])
            matches = [item for item in items if item["name"] == name]
            if len(matches) > 1:
                raise RuntimeError(f"Duplicate gateway component: {name}")
            items[:] = [item for item in items if item["name"] != name]
            items.append({"name": name, "properties": body})

        prefix = "customer-service"
        frontends = properties["frontendIPConfigurations"]
        public = [item for item in frontends if item["properties"].get("publicIPAddress", {}).get("id", "").lower().endswith("/" + self.c["GATEWAY_PUBLIC_IP"].lower())]
        if len(public) != 1:
            raise RuntimeError("Expected exactly the existing public gateway frontend.")
        reserved = {40, 41}
        for rule in properties["requestRoutingRules"]:
            if rule["properties"].get("priority") in reserved and not rule["name"].startswith(prefix):
                raise RuntimeError("Requested gateway routing priority already in use.")
        if any(item["properties"]["port"] == 443 and item["name"] != f"{prefix}-https" for item in properties["frontendPorts"]):
            raise RuntimeError("Existing HTTPS frontend needs explicit integration; refusing collision.")
        upsert("frontendPorts", f"{prefix}-https", {"port": 443})
        upsert("sslCertificates", f"{prefix}-tls", {"data": base64.b64encode(pfx.read_bytes()).decode(), "password": ""})
        upsert("backendAddressPools", prefix, {"backendAddresses": [{"fqdn": backend}]})
        upsert("probes", prefix, {
            "protocol": "Https", "host": backend, "path": "/healthz", "interval": 30, "timeout": 30,
            "unhealthyThreshold": 3, "match": {"statusCodes": ["200"]},
        })
        upsert("backendHttpSettingsCollection", prefix, {
            "port": 443, "protocol": "Https", "cookieBasedAffinity": "Disabled", "requestTimeout": 240,
            "pickHostNameFromBackendAddress": True, "probe": ref("probes", prefix),
        })
        upsert("httpListeners", f"{prefix}-https", {
            "frontendIPConfiguration": {"id": public[0]["id"]}, "frontendPort": ref("frontendPorts", f"{prefix}-https"),
            "protocol": "Https", "hostName": self.c["PUBLIC_HOST"], "requireServerNameIndication": True,
            "sslCertificate": ref("sslCertificates", f"{prefix}-tls"),
        })
        upsert("httpListeners", f"{prefix}-http", {
            "frontendIPConfiguration": {"id": public[0]["id"]}, "frontendPort": ref("frontendPorts", "httpPort"),
            "protocol": "Http", "hostName": self.c["PUBLIC_HOST"],
        })
        upsert("redirectConfigurations", prefix, {
            "redirectType": "Permanent", "targetListener": ref("httpListeners", f"{prefix}-https"),
            "includePath": True, "includeQueryString": True,
        })
        upsert("requestRoutingRules", f"{prefix}-https", {
            "ruleType": "Basic", "priority": 40, "httpListener": ref("httpListeners", f"{prefix}-https"),
            "backendAddressPool": ref("backendAddressPools", prefix), "backendHttpSettings": ref("backendHttpSettingsCollection", prefix),
        })
        upsert("requestRoutingRules", f"{prefix}-http", {
            "ruleType": "Basic", "priority": 41, "httpListener": ref("httpListeners", f"{prefix}-http"),
            "redirectConfiguration": ref("redirectConfigurations", prefix),
        })
        # Preserve all pre-existing components and scalar settings outside the named additive slice.
        for collection, items in before.items():
            if isinstance(items, list):
                retained = [item for item in items if isinstance(item, dict) and not item.get("name", "").startswith(prefix)]
                actual = properties.get(collection, [])
                if any(item not in actual for item in retained):
                    raise RuntimeError(f"Unexpected change to existing gateway collection: {collection}")
            elif properties.get(collection) != items:
                raise RuntimeError(f"Unexpected change to existing gateway setting: {collection}")
        payload = {"location": gateway["location"], "tags": gateway.get("tags", {}), "zones": gateway.get("zones", []), "properties": properties}
        with tempfile.TemporaryDirectory(prefix="customer-service-tls-") as directory:
            body = Path(directory) / "gateway.json"
            body.write_text(json.dumps(payload))
            body.chmod(0o600)
            az("rest", "--method", "put", "--url", gateway_url, "--headers", f"If-Match={gateway['etag']}", "--body", f"@{body}", "--query", "name")
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            current = self.gateway()
            state = current["properties"]["provisioningState"]
            if state == "Succeeded":
                break
            if state == "Failed":
                raise RuntimeError("Gateway update failed; existing route must be inspected before retry.")
            time.sleep(10)
        else:
            raise TimeoutError("Gateway update still pending; do not resubmit before status reconciliation.")
        if current["properties"]["operationalState"] == "Stopped":
            az("network", "application-gateway", "start", *self.hub_scope, "-n", self.c["GATEWAY"])
        if not record:
            az("network", "dns", "record-set", "a", "create", *self.dns_scope, "-n", self.c["DNS_LABEL"], "--ttl", "60", "--metadata", f"project={OWNER}", "--query", "name")
            az("network", "dns", "record-set", "a", "add-record", *self.dns_scope, "-n", self.c["DNS_LABEL"], "-a", public_ip, "--query", "name")
        print(f"Published https://{self.c['PUBLIC_HOST']} through the existing hub WAF.", flush=True)

    def verify_runtime_configuration(self, app: dict) -> dict:
        environment = {
            item["name"]: item.get("value", "")
            for item in app["properties"]["template"]["containers"][0].get("env", [])
        }
        expected = {
            "TENANT_ID": self.c["TENANT_ID"], "AUTH_CLIENT_ID": self.c["AUTH_CLIENT_ID"],
            "BROWSER_CLIENT_ID": self.c["BROWSER_CLIENT_ID"], "AZURE_CLIENT_ID": self.c["AZURE_CLIENT_ID"],
            "AZURE_AUTH_MODE": "managed_identity", "FOUNDRY_PROJECT_ENDPOINT": self.c["FOUNDRY_PROJECT_ENDPOINT"],
            "MODEL_DEPLOYMENT": self.c["MODEL_DEPLOYMENT"],
            "HOSTED_AGENT_NAME": self.c.get("HOSTED_AGENT_NAME", ""),
            "HOSTED_AGENT_VERSION": self.c.get("HOSTED_AGENT_VERSION", ""),
        }
        if any(environment.get(name, "") != value for name, value in expected.items()):
            raise RuntimeError("Deployed authentication, managed identity or Hosted target differs from configuration.")
        if not environment.get("AUTH_ALLOWED_OBJECT_IDS"):
            raise RuntimeError("Deployed user allowlist is missing.")
        identity = app.get("identity", {})
        expected_identity = (
            f"/subscriptions/{self.c['APP_SUBSCRIPTION_ID']}/resourceGroups/{self.c['APP_RESOURCE_GROUP']}"
            f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{self.c['IDENTITY_NAME']}"
        ).lower()
        actual_identities = {name.lower() for name in identity.get("userAssignedIdentities", {})}
        if identity.get("type") != "UserAssigned" or actual_identities != {expected_identity}:
            raise RuntimeError("Deployed workload identity differs from the approved existing identity.")
        return {"azure_auth_mode": environment["AZURE_AUTH_MODE"],
                "browser_client_id": environment["BROWSER_CLIENT_ID"],
                "hosted_chat_configured": bool(environment.get("HOSTED_AGENT_NAME"))}

    def verify(self) -> None:
        app = self.app()
        runtime_configuration = self.verify_runtime_configuration(app)
        gateway = self.gateway()
        ingress = app["properties"]["configuration"]["ingress"]
        if app["tags"].get("project") != OWNER or app["location"].lower().replace(" ", "") != "southeastasia":
            raise RuntimeError("App ownership or region differs.")
        allowed_sources = {rule["ipAddressRange"] for rule in ingress["ipSecurityRestrictions"] if rule["action"] == "Allow"}
        if ingress["allowInsecure"] or allowed_sources != {"10.0.5.0/24", self.c["HUB_FIREWALL_SOURCE_PREFIX"]}:
            raise RuntimeError("Private backend ingress protections differ.")
        if app["properties"].get("latestReadyRevisionName") != app["properties"].get("latestRevisionName"):
            raise RuntimeError("Latest revision is not the ready revision.")
        if gateway["properties"]["operationalState"] != "Running":
            raise RuntimeError("Hub WAF gateway is not running.")
        expected_image = json.loads((STATE / "image.json").read_text())["image"]
        if app["properties"]["template"]["containers"][0]["image"] != expected_image:
            raise RuntimeError("Deployed image does not match the checked immutable build.")
        base = f"https://{self.c['PUBLIC_HOST']}"
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            deadline = time.monotonic() + 240
            while True:
                response = client.get(base + "/healthz")
                if response.status_code == 200:
                    break
                if time.monotonic() >= deadline or response.status_code not in {502, 503, 504}:
                    raise RuntimeError(f"External health failed: HTTP {response.status_code}.")
                time.sleep(5)
            root = client.get(base + "/")
            if root.status_code != 200 or "customer" not in root.text.lower():
                raise RuntimeError("External UI did not serve the expected app.")
            anonymous = client.post(base + "/api/simulations", json={"scenario_id": "damaged-return"})
            if anonymous.status_code not in {401, 403}:
                raise RuntimeError(f"Anonymous model invocation was not refused: {anonymous.status_code}.")
            forged = client.post(
                base + "/api/simulations", json={"scenario_id": "damaged-return"},
                headers={"Authorization": "Bearer forged.invalid.token", "X-Entra-Object-Id": "forged"},
            )
            if forged.status_code not in {401, 403}:
                raise RuntimeError("Forged identity was not refused.")
            waf = client.get(base + "/healthz", params={"waf_probe": "<script>alert(1)</script>"})
            if waf.status_code != 403:
                raise RuntimeError(f"WAF prevention probe did not block: HTTP {waf.status_code}.")
            redirect = client.get(f"http://{self.c['PUBLIC_HOST']}/healthz")
            if redirect.status_code not in {301, 308} or redirect.headers.get("location") != base + "/healthz":
                raise RuntimeError("HTTP does not redirect to the correct protected HTTPS hostname.")
        result = {
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "url": base,
            "revision": app["properties"]["latestReadyRevisionName"], "image": expected_image,
            "gateway_state": "Running", "anonymous_status": anonymous.status_code,
            "forged_status": forged.status_code, "waf_probe_status": waf.status_code,
            "health_status": 200, "http_redirect_status": redirect.status_code,
            **runtime_configuration,
        }
        (STATE / "verification.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2), flush=True)

    def regression(self) -> None:
        gold = APP / "datasets/gold.json"
        output = STATE / "regression-report.json"
        if not gold.is_file():
            output.write_text(json.dumps({
                "overall_pass": False, "status": "blocked", "reason": "calibrated_gold_baseline_missing",
                "model_calls": 0, "production_promotion": False,
            }, indent=2))
            raise RuntimeError("No calibrated gold baseline. Supply genuine human calibration and explicitly accepted frozen gold; no model calls were made.")
        allowed_names = {
            "TENANT_ID", "AUTH_CLIENT_ID", "AUTH_ALLOWED_OBJECT_IDS", "AZURE_CLIENT_ID",
            "FOUNDRY_PROJECT_ENDPOINT", "MODEL_DEPLOYMENT", "APP_REVISION",
            "AGENT_TRIAGE_VERSION", "AGENT_POLICY_VERSION", "AGENT_RESOLUTION_VERSION",
            "AGENT_JUDGE_FACTUAL_ACCURACY_VERSION", "AGENT_JUDGE_TASK_COMPLETION_VERSION",
            "AGENT_JUDGE_TONE_VERSION", "AGENT_JUDGE_CONSISTENCY_VERSION",
        }
        entries = self.app()["properties"]["template"]["containers"][0]["env"]
        environment = dict(os.environ)
        environment.update({entry["name"]: entry["value"] for entry in entries if entry["name"] in allowed_names and "value" in entry})
        command([
            sys.executable, str(APP / "regression.py"), "run", "--gold", str(gold),
            "--dataset", str(APP / "datasets/synthetic-customer-issues.jsonl"),
            "--output", str(output), "--allow-model-calls",
        ], output=True, env=environment)


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated customer-service-multi-agent deployment. No shared-resource teardown.")
    parser.add_argument("-e", "--environment", default="sea", choices=["sea"])
    parser.add_argument("action", choices=["preflight", "setup-browser-auth", "vendor-msal", "configure-local", "build", "provision-agents", "provision-hosted", "verify-hosted", "verify-hosted-logs", "certificate", "start-gateway", "network", "release", "route", "verify", "verify-logs", "workbooks", "exercise", "browser-verify", "generate-dataset", "validate-dataset", "regression", "publish", "status", "deploy", "teardown", "observability", "replay"])
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--trace-id")
    parser.add_argument("--span-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.action == "replay":
        # Inherit stdio so replay's own message, not a wrapper traceback, reaches the operator.
        sys.exit(subprocess.run([sys.executable, str(ROOT / "deploy/replay.py"),
                                 *(["--trace-id", args.trace_id] if args.trace_id else []),
                                 *(["--span-id", args.span_id] if args.span_id else []),
                                 *(["--json"] if args.json else [])]).returncode)
    if args.action == "publish":
        if not args.destination:
            parser.error("publish requires --destination outside the original repository")
        publish_args = [sys.executable, str(ROOT / "deploy/publish.py"), "--destination", str(args.destination)]
        if args.push:
            publish_args.append("--push")
        if args.session_id:
            publish_args.extend(["--session-id", args.session_id])
        command(publish_args, output=True)
        return
    deployment = Deployment(config(args.environment))
    actions = {
        "preflight": deployment.preflight, "build": deployment.build,
        "setup-browser-auth": deployment.browser_auth,
        "vendor-msal": lambda: command([sys.executable, str(ROOT / "deploy/vendor_msal.py")], output=True),
        "configure-local": deployment.configure_local,
        "provision-agents": deployment.provision_agents, "release": deployment.release,
        "provision-hosted": deployment.provision_hosted,
        "verify-hosted": lambda: command([sys.executable, str(ROOT / "deploy/verify_hosted.py")], output=True),
        "verify-hosted-logs": lambda: command([sys.executable, str(ROOT / "deploy/verify_hosted_logs.py")], output=True),
        "certificate": lambda: print(deployment.certificate()),
        "start-gateway": deployment.start_gateway,
        "network": deployment.network,
        "observability": deployment.observability,
        "exercise": lambda: command([sys.executable, str(ROOT / "deploy/exercise.py")], output=True),
        "generate-dataset": lambda: command([sys.executable, str(ROOT / "deploy/generate_dataset.py")], output=True),
        "validate-dataset": lambda: command([sys.executable, str(ROOT / "deploy/validate_dataset.py")], output=True),
        "browser-verify": lambda: command([
            sys.executable, str(ROOT / "deploy/browser_verify.py"),
            *(["--hosted-agent-name", deployment.c["HOSTED_AGENT_NAME"],
               "--hosted-agent-version", deployment.c["HOSTED_AGENT_VERSION"]]
              if deployment.c.get("HOSTED_AGENT_NAME") and deployment.c.get("HOSTED_AGENT_VERSION") else []),
        ], output=True),
        "verify-logs": lambda: command([sys.executable, str(ROOT / "deploy/verify_logs.py")], output=True),
        "workbooks": lambda: command([sys.executable, str(ROOT / "deploy/workbooks.py")], output=True),
        "regression": deployment.regression,
        "route": deployment.route, "verify": deployment.verify,
        "status": lambda: print(json.dumps({
            "app": deployment.app()["properties"]["latestReadyRevisionName"],
            "gateway": deployment.gateway()["properties"]["operationalState"],
        }, indent=2)),
    }
    if args.action == "teardown":
        raise RuntimeError("Teardown is not authorized. Shared gateway, registry, environment, identity and Foundry resources must never be deleted by this application.")
    if args.action == "deploy":
        for step in ("preflight", "setup-browser-auth", "vendor-msal", "provision-agents", "provision-hosted", "build", "release", "network", "route", "verify"):
            actions[step]()
    else:
        actions[args.action]()


if __name__ == "__main__":
    main()
