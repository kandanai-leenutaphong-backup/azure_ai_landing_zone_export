from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx
from azure.identity import AzureCliCredential

from manage import STATE, config


def run(scenario_id: str, output: Path) -> dict:
    settings = config("sea")
    with AzureCliCredential(tenant_id=settings["TENANT_ID"]) as credential:
        token = credential.get_token(f"api://{settings['AUTH_CLIENT_ID']}/.default")
    base = f"https://{settings['PUBLIC_HOST']}"
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token.token}"}, timeout=60) as client:
        scenarios = client.get("/api/scenarios").raise_for_status().json()
        selected = [row["id"] for row in scenarios["scenarios"]] if scenario_id == "all" else [scenario_id]
        observed = []
        for fixture_id in selected:
            accepted = client.post("/api/simulations", json={"scenario_id": fixture_id}).raise_for_status()
            if accepted.status_code != 202:
                raise RuntimeError("Simulation was not accepted asynchronously.")
            location = accepted.headers["Location"]
            deadline = time.monotonic() + 420
            while True:
                result = client.get(location).raise_for_status().json()
                if result["status"] in {"completed", "failed"}:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Simulation {result['id']} did not settle in 420 seconds; poll before resubmission.")
                time.sleep(3)
            observed.append(result)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"results": observed}, indent=2))
            if result["status"] != "completed":
                raise RuntimeError(f"Simulation failed: {json.dumps({k: result.get(k) for k in ('id', 'error_code', 'status')})}. Evidence: {output}")
            if result.get("ledger", {}).get("real_transaction") is not False:
                raise RuntimeError("Authoritative simulation ledger did not confirm synthetic-only action.")
            reread = client.get(location).raise_for_status().json()
            if reread != result:
                raise RuntimeError("Terminal simulation readback changed unexpectedly.")
            print(json.dumps({
                "id": result["id"], "scenario_id": fixture_id, "status": result["status"],
                "goal_index": result.get("goal_index"), "trace_id": result.get("trace_id"),
                "ledger": result.get("ledger"),
            }), flush=True)
        metrics = client.get("/api/metrics").raise_for_status().json()
        output.write_text(json.dumps({"results": observed, "metrics": metrics, "scenario_catalog": scenarios}, indent=2))
        return {"runs": len(observed), "evidence": str(output)}


def main():
    parser = argparse.ArgumentParser(description="Bounded, authenticated synthetic customer journey through the real WAF. Billable model and judge calls.")
    parser.add_argument("--scenario", default="damaged-return")
    parser.add_argument("--output", type=Path, default=STATE / "smoke.json")
    args = parser.parse_args()
    print(json.dumps(run(args.scenario, args.output)))


if __name__ == "__main__":
    main()
