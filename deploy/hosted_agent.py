"""Native source-code deployment. No registry grants, Docker or credential exports."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
import zipfile
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import CodeConfiguration, HostedAgentDefinition, ProtocolVersionRecord
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential

from manage import APP, OWNER, STATE

NAME = "cs-customer-service-chat"


def package_code(app: Path, destination: Path) -> str:
    sources = {
        "main.py": app / "hosted/main.py",
        "runtime.py": app / "hosted/runtime.py",
        "validation.py": app / "hosted/validation.py",
        "requirements.txt": app / "hosted/requirements.txt",
        "scenarios.py": app / "scenarios.py",
        "telemetry.py": app / "telemetry.py",
    }
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError("Refusing a symlinked hosted archive destination.")
    from publish import PROHIBITED
    payloads = {}
    for name, source in sources.items():
        if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent != app.parent):
            raise ValueError("Hosted source must not cross symlinks.")
        if not source.resolve().is_relative_to(app.resolve()):
            raise ValueError("Hosted source escapes the application.")
        payload = source.read_bytes()
        if PROHIBITED.search(payload):
            raise ValueError(f"Credential-shaped content blocks hosted packaging: {name}")
        payloads[name] = payload
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def definition(model: str) -> HostedAgentDefinition:
    return HostedAgentDefinition(
        cpu="0.5", memory="1Gi",
        code_configuration=CodeConfiguration(
            runtime="python_3_13", entry_point=["python", "main.py"],
            dependency_resolution="remote_build",
        ),
        protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")],
        environment_variables={"MODEL_DEPLOYMENT": model},
    )


def verify_version(project, version: str, expected: HostedAgentDefinition, source_sha256: str) -> dict:
    actual = project.agents.get_version(agent_name=NAME, agent_version=version)
    actual_definition = actual.definition.as_dict()
    expected_definition = expected.as_dict()
    for key in ("cpu", "memory", "environment_variables", "protocol_versions", "kind"):
        if actual_definition.get(key) != expected_definition.get(key):
            raise RuntimeError(f"Hosted version differs in protected field: {key}")
    for key in ("runtime", "entry_point", "dependency_resolution"):
        if actual_definition.get("code_configuration", {}).get(key) != expected_definition["code_configuration"][key]:
            raise RuntimeError(f"Hosted version differs in code configuration: {key}")
    if actual.metadata.get("owner") != OWNER or actual.metadata.get("source_sha256") != source_sha256:
        raise RuntimeError("Hosted version ownership or source metadata differs.")
    digest = hashlib.sha256()
    for chunk in project.agents.download_code(agent_name=NAME, agent_version=version):
        digest.update(chunk)
    if digest.hexdigest() != source_sha256:
        raise RuntimeError("Downloaded deployed source does not match the accepted archive.")
    return {
        "name": NAME, "version": version, "status": actual.status,
        "source_sha256": source_sha256, "downloaded_source_matches": True,
        "runtime": "python_3_13", "cpu": "0.5", "memory": "1Gi",
        "model": expected.environment_variables["MODEL_DEPLOYMENT"],
        "deployment": "native-source-code", "rbac_changed": False,
    }


def provision(settings: dict) -> dict:
    STATE.mkdir(exist_ok=True)
    if STATE.is_symlink():
        raise ValueError("Refusing a symlinked deployment state directory.")
    with tempfile.TemporaryDirectory(prefix="customer-service-hosted-") as directory:
        candidate = Path(directory) / "source.zip"
        source_sha256 = package_code(APP, candidate)
        archive = STATE / f"hosted-code-{source_sha256}.zip"
        if archive.is_symlink():
            raise ValueError("Refusing a symlinked hosted source archive.")
        if archive.exists():
            if hashlib.sha256(archive.read_bytes()).hexdigest() != source_sha256:
                raise RuntimeError("Retained hosted source archive is corrupt; preserve it for inspection.")
        else:
            with archive.open("xb") as saved:
                saved.write(candidate.read_bytes())
    desired = definition(settings["MODEL_DEPLOYMENT"])
    with AzureCliCredential(tenant_id=settings["TENANT_ID"]) as identity, AIProjectClient(
        endpoint=settings["FOUNDRY_PROJECT_ENDPOINT"], credential=identity,
        allow_preview=True, retry_total=0, connection_timeout=10, read_timeout=120,
    ) as project:
        try:
            versions = list(project.agents.list_versions(agent_name=NAME))
        except ResourceNotFoundError:
            versions = []
        if any(version.metadata.get("owner") != OWNER for version in versions):
            raise RuntimeError("Hosted agent namespace contains foreign versions; refusing adoption.")
        matches = [version for version in versions if version.metadata.get("source_sha256") == source_sha256]
        if len(matches) > 1:
            raise RuntimeError("Ambiguous matching hosted versions; inspect before promotion.")
        intent = STATE / "hosted-intent.json"
        if intent.is_symlink():
            raise ValueError("Refusing a symlinked hosted intent.")
        if matches:
            version = matches[0].version
        else:
            if intent.exists() and json.loads(intent.read_text()).get("outcome") == "unknown":
                raise RuntimeError("Previous hosted upload outcome is unknown. Reconcile versions before another write.")
            intent.write_text(json.dumps({"name": NAME, "source_sha256": source_sha256, "outcome": "unknown"}))
            with archive.open("rb") as source:
                created = project.agents.create_version_from_code(
                    agent_name=NAME, definition=desired, code=source, code_zip_sha256=source_sha256,
                    metadata={"owner": OWNER, "source_sha256": source_sha256, "framework": "microsoft-agent-framework"},
                    description="Synthetic read-only customer-service multi-agent chat",
                )
            version = created.version
            intent.write_text(json.dumps({"name": NAME, "version": version,
                                          "source_sha256": source_sha256, "outcome": "accepted"}))
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            current = project.agents.get_version(agent_name=NAME, agent_version=version)
            if current.status == "active":
                receipt = verify_version(project, version, desired, source_sha256)
                (STATE / "hosted-agent.json").write_text(json.dumps(receipt, indent=2) + "\n")
                return receipt
            if current.status == "failed":
                raise RuntimeError(f"Hosted agent {NAME}:{version} provisioning failed; retain it and inspect native logs.")
            time.sleep(5)
        raise TimeoutError(f"Hosted agent {NAME}:{version} is not active after 600 seconds. Reconcile; do not re-create.")
