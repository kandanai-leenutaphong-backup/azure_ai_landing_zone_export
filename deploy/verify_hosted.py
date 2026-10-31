"""Bounded synthetic native chat probe. No credential or message payload in receipts."""
from __future__ import annotations

import hashlib
import json
import sys

import httpx

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

from manage import APP, STATE, config
from hosted_agent import NAME, definition, verify_version


def verify() -> dict:
    settings = config("sea")
    pin = json.loads((STATE / "hosted-agent.json").read_text())
    if pin["name"] != NAME or pin["status"] != "active":
        raise RuntimeError("A verified active Hosted version is required before inference.")
    sys.path.insert(0, str(APP))
    from chat import HostedClient
    from settings import Settings
    from dataclasses import replace
    configured = replace(Settings.from_env(), credential_mode="azure_cli",
                         hosted_agent_name=pin["name"], hosted_agent_version=pin["version"])
    receipt_path = STATE / f"hosted-invocation-v{pin['version']}.json"
    existing = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if existing and any(existing.get(key) != pin[key] for key in ("name", "version", "source_sha256")):
        raise RuntimeError("Retained Hosted invocation receipt differs from the accepted source/version.")
    if existing and existing.get("status") != "completed":
        raise RuntimeError("Hosted invocation outcome is pending or unknown; reconcile it without resending messages.")
    receipt = existing or {
        "name": pin["name"], "version": pin["version"], "status": "pending",
        "source_sha256": pin["source_sha256"], "turns": [], "human_signin_verified": False,
    }
    if existing is None:
        receipt_path.write_text(json.dumps(receipt, indent=2))
    with AzureCliCredential(tenant_id=settings["TENANT_ID"]) as credential, AIProjectClient(
        endpoint=settings["FOUNDRY_PROJECT_ENDPOINT"], credential=credential,
        allow_preview=True, retry_total=0, connection_timeout=10, read_timeout=180,
    ) as project:
        verify_version(project, pin["version"], definition(settings["MODEL_DEPLOYMENT"]), pin["source_sha256"])
        client = HostedClient(configured)
        native = project.get_openai_client(agent_name=NAME, max_retries=0, timeout=180)
        previous = None
        try:
            with httpx.Client(trust_env=False, timeout=30) as anonymous:
                response = anonymous.post(str(native.base_url).rstrip("/") + "/responses",
                                          json={"input": "Synthetic access-denial probe"})
            if response.status_code not in (401, 403):
                raise RuntimeError("Anonymous native Hosted invocation was not refused.")
            if existing:
                for turn in receipt["turns"]:
                    saved = native.responses.retrieve(turn["response_id"])
                    if saved.status != "completed" or hashlib.sha256(saved.output_text.encode()).hexdigest() != turn["output_sha256"]:
                        raise RuntimeError("Previously completed stored Hosted response no longer matches its receipt.")
                readback = {**receipt, "anonymous_status": response.status_code, "new_inference_calls": 0}
                (STATE / "hosted-auth-readback.json").write_text(json.dumps(readback, indent=2) + "\n")
                return readback
            receipt["anonymous_status"] = response.status_code
            for index, message in enumerate((
                "My synthetic order SYN-101 headphones arrived damaged five days after delivery. What can I do?",
                "For that same synthetic order, is a refund already issued, and what is the next step?",
            ), 1):
                receipt["status"] = "invoking"
                receipt["pending_turn"] = index
                receipt_path.write_text(json.dumps(receipt, indent=2))
                result = client.respond(message, previous, {})
                response_id = result["response_id"]
                receipt["turns"].append({"turn": index, "response_id": response_id, "stored_readback": False})
                receipt_path.write_text(json.dumps(receipt, indent=2))
                saved = native.responses.retrieve(response_id)
                if saved.status != "completed" or saved.output_text != result["content"]:
                    raise RuntimeError("Native stored response differs from the completed hosted turn.")
                receipt["turns"][-1].update(
                    stored_readback=True, output_characters=len(saved.output_text),
                    output_sha256=hashlib.sha256(saved.output_text.encode()).hexdigest(),
                )
                previous = response_id
                receipt_path.write_text(json.dumps(receipt, indent=2))
        finally:
            native.close()
            client.close()
    receipt["status"] = "completed"
    receipt.pop("pending_turn", None)
    receipt_path.write_text(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
