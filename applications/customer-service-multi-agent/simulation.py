"""Callable simulation service. Authoritative tools precede model completion."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
import threading
import time
import math
import uuid
from datetime import datetime, timezone
from dataclasses import replace
from pydantic import StrictBool, Field
from scenarios import SCENARIOS
from simulation_schema import StrictResult
from evaluation import SpecializedJudges
from settings import ROLES


class Triage(StrictResult):
    category: str


class Policy(StrictResult):
    action: str


class Resolution(StrictResult):
    message: str = Field(min_length=1, max_length=1000)
    action: str
    receipt_id: str
    completed: StrictBool


class Store:
    def __init__(self, path):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.interrupted = []
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, owner TEXT, data TEXT)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS ledger (run_id TEXT PRIMARY KEY, data TEXT)")
        with self.lock, self.connection:
            for run_id, data in self.connection.execute("SELECT id,data FROM runs").fetchall():
                row = json.loads(data)
                if row["status"] in ("queued", "running"):
                    row.update(status="failed", error_code="worker_interrupted", goal_index=None)
                    self.connection.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(row), run_id))
                    self.interrupted.append(row)

    def save(self, owner, row):
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?)",
                                    (row["id"], owner, json.dumps(row)))

    def get(self, owner, run_id):
        with self.lock:
            row = self.connection.execute("SELECT data FROM runs WHERE id=? AND owner=?", (run_id, owner)).fetchone()
            return json.loads(row[0]) if row else None

    def rows(self, owner):
        with self.lock:
            return [json.loads(r[0]) for r in self.connection.execute(
                "SELECT data FROM runs WHERE owner=?", (owner,)).fetchall()]

    def operate(self, run_id, scenario, requested):
        if requested != scenario.action:
            raise ValueError("Policy action rejected")
        with self.lock, self.connection:
            existing = self.connection.execute("SELECT data FROM ledger WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                return json.loads(existing[0])
            receipt = {"receipt_id": "SIM-" + run_id, "action": scenario.action, "simulation": True,
                       "amount_sgd": 49 if scenario.id == "duplicate-charge" else None,
                       "real_transaction": False, "state": "recorded"}
            self.connection.execute("INSERT INTO ledger VALUES (?,?)", (run_id, json.dumps(receipt)))
        return self.read_ledger(run_id)

    def read_ledger(self, run_id):
        with self.lock:
            row = self.connection.execute("SELECT data FROM ledger WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise ValueError("Missing tool readback")
            return json.loads(row[0])

    def close(self):
        self.connection.close()


class SimulationService:
    def __init__(self, store, agents, telemetry, pins):
        self.store, self.agents, self.telemetry, self.pins = store, agents, telemetry, pins
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="synthetic")
        self.busy = threading.Lock()
        for row in store.interrupted:
            scenario = SCENARIOS.get(row.get("scenario_id"))
            if scenario:
                self._snapshot(row, scenario)

    def _snapshot(self, row, scenario, context=None):
        """Content-free lifecycle snapshot, durable only after platform log ingestion."""
        judge = row.get("judge")
        with self.telemetry.event(
            "simulation.snapshot", hashlib.sha256(row["id"].encode()).hexdigest(),
            scenario.customer_tier, journey_type=scenario.category, run_id=row["id"], context=context,
        ) as event:
            event.update(status=row["status"], error_code=row.get("error_code"), metrics={
                "schema_version": 1, "scenario_id": scenario.id,
                "attempts": 1, "workflow_completed": row["status"] == "completed",
                "task_completed": bool(row["status"] == "completed" and judge and all(judge["criteria"])),
                "error": row["status"] == "failed",
                "scored": judge is not None and row["status"] == "completed",
                "goal_index": row.get("goal_index"), "coherence": judge["coherence"] if judge else None,
                "judge_scores": {key: value["score"] for key, value in judge["specialized"].items()} if judge else None,
                "human_review_required": judge["human_review_required"] if judge else None,
                "agent_samples": [
                    {key: s.get(key) for key in ("agent", "latency_ms", "error", "correct",
                                                "input_token_count", "output_token_count")}
                    for s in row.get("agent_samples", [])
                ],
                "calibration_status": "calibration_not_established", "release_ready": False,
                "resolution_rate": None, "reopen_rate": None,
            })

    def submit(self, owner, scenario_id, context=None, consensus=False, customer_request=None):
        scenario = SCENARIOS[scenario_id]
        if customer_request is not None:
            if not isinstance(customer_request, str) or not 1 <= len(customer_request.strip()) <= 2000:
                raise ValueError("Synthetic request override must contain 1..2000 characters")
            # Only language changes. Policy/category/action/criteria stay immutable.
            scenario = replace(scenario, request=customer_request)
        if not self.busy.acquire(blocking=False):
            raise BlockingIOError("One simulation already running")
        row = {"id": str(uuid.uuid4()), "scenario_id": scenario.id, "status": "queued",
               "journey_type": scenario.category, "agent_samples": [], "consensus": consensus,
               "request_variant": customer_request is not None,
               "created_at": datetime.now(timezone.utc).isoformat(), "simulation": True,
               "goal_index": None, "judge": None, "ledger": None, "error_code": None,
               "agent_pins": self.pins,
               "resolution_rate": None, "reopen_rate": None,
               "retention": "SQLite replica-local, non-durable"}
        try:
            self.store.save(owner, row)
            self._snapshot(row, scenario, context)
            self.executor.submit(self._run, owner, row, scenario, context)
        except Exception:
            self.busy.release()
            raise
        return dict(row)

    def _call(self, role, payload, schema, session, scenario, row):
        sample = {"agent": role, "latency_ms": None, "error": False, "correct": None,
                  "input_token_count": None, "output_token_count": None}
        row["agent_samples"].append(sample)
        start = time.perf_counter()
        try:
            with self.telemetry.event(role, session, scenario.customer_tier, self.pins[role],
                                      journey_type=scenario.category, run_id=row["id"]) as event:
                text, usage = self.agents.call(role, payload)
                event.update({k: usage.get(k) for k in ("input_token_count", "output_token_count")})
                sample.update({k: usage.get(k) for k in ("input_token_count", "output_token_count")})
                return self._parse(text, schema)
        except Exception:
            sample["error"] = True
            raise
        finally:
            sample["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)

    @staticmethod
    def _parse(text, schema):
            # JSON duplicate fields and non-standard NaN constants also fail closed.
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("Duplicate JSON key")
                out[key] = value
            return out
        parsed = json.loads(text, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON constant")))
        return schema.model_validate(parsed).model_dump()

    def _decision(self, role, correct, row, scenario, session):
        row["agent_samples"][-1]["correct"] = correct
        with self.telemetry.event("decision.validate", session, scenario.customer_tier, self.pins[role],
                                  journey_type=scenario.category, run_id=row["id"]) as event:
            event.update(correctness=correct, decision_code=role + "_contract",
                         status="ok" if correct else "rejected",
                         error_code=None if correct else "authoritative_mismatch")

    def _run(self, owner, row, scenario, context):
        session = hashlib.sha256(row["id"].encode()).hexdigest()
        run_context = context
        try:
            with self.telemetry.event("simulation", session, scenario.customer_tier, context=context,
                                      journey_type=scenario.category, run_id=row["id"]):
                from opentelemetry import trace
                from opentelemetry import context as otel_context
                run_context = otel_context.get_current()
                row["trace_id"] = f"{trace.get_current_span().get_span_context().trace_id:032x}"
                row["session_id"] = session
                row["status"] = "running"
                self.store.save(owner, row)
                payload = {"scenario": scenario.public()}
                triage = self._call("triage", payload, Triage, session, scenario, row)
                self._decision("triage", triage["category"] == scenario.category, row, scenario, session)
                if triage["category"] != scenario.category:
                    raise ValueError("Wrong triage category")
                policy = self._call("policy", {**payload, "triage": triage}, Policy, session, scenario, row)
                self._decision("policy", policy["action"] == scenario.action, row, scenario, session)
                with self.telemetry.event("tool.execute", session, scenario.customer_tier,
                                          journey_type=scenario.category, run_id=row["id"]):
                    self.store.operate(row["id"], scenario, policy["action"])
                with self.telemetry.event("tool.readback", session, scenario.customer_tier,
                                          journey_type=scenario.category, run_id=row["id"]):
                    ledger = self.store.read_ledger(row["id"])
                row["ledger"] = ledger
                resolution = self._call("resolution", {**payload, "triage": triage, "ledger": ledger},
                                        Resolution, session, scenario, row)
                resolution_correct = (
                    resolution["action"] == ledger["action"] and resolution["receipt_id"] == ledger["receipt_id"]
                    and resolution["completed"] is True)
                self._decision("resolution", resolution_correct, row, scenario, session)
                if (resolution["action"] != ledger["action"] or resolution["receipt_id"] != ledger["receipt_id"]
                        or resolution["completed"] is not True):
                    raise ValueError("Unsupported action completion")
                row["components"] = {"triage": triage, "policy": policy, "resolution": resolution}
                judges = SpecializedJudges(lambda role, body, schema: self._call(
                    role, body, schema, session, scenario, row))
                judge = judges.evaluate({
                    "full_transcript": {"request": scenario.request, **row["components"]},
                    "ground_truth": SCENARIOS[scenario.id].public(), "actual_final_state": ledger,
                }, consensus=row["consensus"])
                row["judge"] = judge
                row["goal_index"] = sum(w for w, passed in zip((3, 4, 3), judge["criteria"]) if passed)
                row["status"] = "completed"
                row["criteria"] = list(scenario.criteria)
                row["agent_pins"] = self.pins
                row["evaluation_scope"] = {
                    "component": "triage, policy, resolution and four specialized native prompt judges",
                    "memory": "single-run handoff context only; no cross-session memory evaluated",
                    "knowledge": "immutable supplied policy; no retrieval or RAG ranks",
                    "tool": "deterministic simulation action plus SQLite readback",
                    "prompt": "version-pinned definitions; no optimizer experiment",
                }
        except Exception:
            row.update(status="failed", error_code="simulation_failed", goal_index=None, judge=None)
            # Reconcile action independently: judge failure never erases a recorded synthetic operation.
            try:
                row["ledger"] = self.store.read_ledger(row["id"])
            except ValueError:
                pass
        finally:
            try:
                self.store.save(owner, row)
                self._snapshot(row, scenario, run_context)
            finally:
                self.busy.release()

    def metrics(self, owner, journey_type=None):
        return aggregate(self.store.rows(owner), journey_type)

    def close(self):
        self.executor.shutdown(wait=True)
        self.agents.close()
        self.store.close()


def aggregate(rows, journey_type=None):
    """Ratios use raw samples, never averages of per-journey averages."""
    def overall(group):
        scored = [r for r in group if r["status"] == "completed" and r.get("judge") is not None]
        completed = sum(all(r["judge"]["criteria"]) for r in scored)
        return {
            "attempts": len(group), "task_completed": completed,
            "workflow_completed": sum(r["status"] == "completed" for r in group),
            "errors": sum(r["status"] == "failed" for r in group),
            "pending": sum(r["status"] in ("queued", "running") for r in group),
            "task_completion_rate": completed / len(group) if group else None,
            "scored_count": len(scored), "unscored_count": len(group) - len(scored),
            "average_goal_achievement": sum(r["goal_index"] for r in scored) / len(scored) if scored else None,
            "journey_coherence": sum(r["judge"]["coherence"] for r in scored) / len(scored) if scored else None,
            "resolution_rate": None, "reopen_rate": None, "business_impact": None,
        }
    groups = {s.category: [] for s in SCENARIOS.values()}
    for row in rows:
        groups[row["journey_type"]].append(row)
    selected = groups[journey_type] if journey_type else rows
    agents = {}
    for role in ROLES:
        samples = [s for r in selected for s in r.get("agent_samples", []) if s["agent"] == role]
        evaluated = [s for s in samples if s["correct"] is not None]
        times = sorted(s["latency_ms"] for s in samples if s["latency_ms"] is not None)
        errors = sum(s["error"] for s in samples)
        agents[role] = {
            "attempts": len(samples), "errors": errors,
            "error_rate": errors / len(samples) if samples else None,
            "evaluated_count": len(evaluated), "unevaluated_count": len(samples) - len(evaluated),
            "correct_count": sum(s["correct"] is True for s in evaluated),
            "specialized_task_accuracy": sum(s["correct"] is True for s in evaluated) / len(evaluated) if evaluated else None,
            "accuracy_scope": {"triage": "exact authoritative category",
                               "policy": "exact authoritative requested action",
                               "resolution": "ledger receipt/action/completed consistency only, not prose quality",
                               }.get(role, "unavailable: no independent judge ground-truth labels"),
            "latency_sample_count": len(times),
            "mean_latency_ms": sum(times) / len(times) if times else None,
            "p95_latency_ms": times[math.ceil(.95 * len(times)) - 1] if times else None,
        }
        for key in ("input_token_count", "output_token_count"):
            known = [s[key] for s in samples if s[key] is not None]
            agents[role][key] = sum(known) if known else None
            agents[role][key + "_known_samples"] = len(known)
    return {"simulation": True, "system": overall(rows),
            "journeys": {k: overall(v) for k, v in groups.items()},
            "selected_journey": journey_type, "agents": agents,
            "demo_targets": {"task_completion_rate": .9, "average_goal_achievement": 8.5, "journey_coherence": 9},
            "business_metrics_note": "Unknown until actual user feedback. Simulation scores are not business impact.",
            "denominator_note": "Completion: all attempts including pending/failed. Goals/coherence: scored only, unscored shown. Agent accuracy: explicit correctness labels only. p95: nearest rank.",
            "retention": "SQLite replica-local, non-durable"}
