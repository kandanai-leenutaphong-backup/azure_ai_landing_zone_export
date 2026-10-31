"""Reconcile only app-owned definitions. No deployment, RBAC or registration writes."""
import argparse
import hashlib
import json
from native import definition, verify_definition
from settings import PROJECT, ROLES


def reconcile(project, apply=False):
    from azure.core.exceptions import ResourceNotFoundError
    result = {}
    # Preflight all names before creating anything.
    missing = []
    for role in ROLES:
        name = f"cs-sim-{role.replace('_', '-')}"
        expected_hash = hashlib.sha256(json.dumps(definition(role).as_dict(), sort_keys=True).encode()).hexdigest()
        try:
            project.agents.get(agent_name=name)
        except ResourceNotFoundError:
            missing.append((role, name, expected_hash))
            continue
        versions = list(project.agents.list_versions(agent_name=name))
        matches = []
        for version in versions:
            if (version.metadata or {}).get("owner") != "customer-service-multi-agent":
                raise RuntimeError(f"Unrelated existing agent name: {name}")
            verify_definition(version, role)
            if (version.metadata or {}).get("definition_sha256") != expected_hash:
                raise RuntimeError(f"Definition metadata mismatch: {name}")
            matches.append(version)
        if len(matches) != 1:
            raise RuntimeError(f"Ambiguous versions for {name}; explicit operator reconciliation required")
        result[role] = {"name": name, "version": matches[0].version}
    if missing and not apply:
        raise RuntimeError("Missing agents. Explicit --apply required to create app-owned definitions.")
    for role, name, digest in missing:
        created = project.agents.create_version(
            agent_name=name, definition=definition(role),
            metadata={"owner": "customer-service-multi-agent", "definition_sha256": digest},
        )
        readback = project.agents.get_version(agent_name=name, agent_version=created.version)
        verify_definition(readback, role)
        result[role] = {"name": name, "version": readback.version}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Explicitly create missing app-owned agents")
    args = parser.parse_args()
    from azure.identity import AzureCliCredential
    from azure.ai.projects import AIProjectClient
    with AzureCliCredential() as credential, AIProjectClient(
        endpoint=PROJECT, credential=credential, retry_total=0, connection_timeout=5, read_timeout=40,
    ) as project:
        from settings import MODEL
        deployment = project.deployments.get(name=MODEL)
        if deployment.sku.name != "Standard" or deployment.model_name != MODEL or not deployment.sku.capacity:
            raise RuntimeError("Existing regional Standard deployment required")
        pins = reconcile(project, args.apply)
        print(json.dumps({"project": PROJECT, "pins": pins}, indent=2))
        for role, pin in pins.items():
            print(f"AGENT_{role.upper()}_VERSION={pin['version']}")


if __name__ == "__main__":
    main()
