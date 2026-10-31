"""Publish a project decision, progress event or settled result from a JSON object on stdin."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from validate import StrictLoader, validate

RECORD_SCHEMA = json.loads(Path(__file__).with_name("record.schema.json").read_text())
RECORD_VALIDATOR = Draft202012Validator(RECORD_SCHEMA, format_checker=FormatChecker())


def contained(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Archive path escapes root")
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Symlinked archive paths are refused")
    return path


def references(root: Path, items):
    for item in items:
        path = contained(root, item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Referenced evidence digest mismatch")


def verify(root: Path) -> list[str]:
    verified = []
    for path in sorted((root / "records/v2").glob("*/record.json")):
        path = contained(root, str(path.relative_to(root)))
        record = json.loads(path.read_text())
        RECORD_VALIDATOR.validate(record)
        if record["project_id"] != root.name:
            raise ValueError("Wrong project in archived record")
        references(root, record["record_refs"])
        references(path.parent, record["artifacts"])
        snapshot = contained(path.parent, record["constitution"]["snapshot"])
        if hashlib.sha256(snapshot.read_bytes()).hexdigest() != record["constitution"]["sha256"]:
            raise ValueError("Archived constitution digest mismatch")
        for artifact in record["artifacts"]:
            if contained(path.parent, artifact["path"]).stat().st_size != artifact["bytes"]:
                raise ValueError("Archived artifact size mismatch")
        verified.append(str(path))
    return verified


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Invalid record or relationship ID")
    return value


def publish(root: Path, record: dict, *, snapshots=(), snapshot_root: Path | None = None) -> Path:
    if not isinstance(record, dict):
        raise ValueError("Expected one JSON object")
    json.dumps(record, allow_nan=False)
    record = dict(record)
    reserved = {"schema_version", "project_id", "constitution", "recorded_at", "artifacts"}
    if reserved.intersection(record):
        raise ValueError("Recorder owns version, project, constitution and recording timestamp")
    if not isinstance(record.get("actor"), str) or not record["actor"].strip() or not isinstance(record.get("evidence"), list):
        raise ValueError("Actor and evidence references are required")
    record_id = identifier(record.get("id"))
    kind = record.get("record_type")
    required = {
        "decision": {"observation", "hypothesis", "decision", "changed_levers", "rationale", "approval",
                     "expected_outcome", "acceptance_refs", "authority_source", "supersedes"},
        "event": {"sequence", "phase", "status", "decision_ids"},
        "result": {"status", "decision_ids", "metrics", "verdict", "limitations", "next_decision", "settlement"},
        "checkpoint": {"status", "decision_ids", "changes", "metrics", "coverage", "reversion", "rationale", "supersedes"},
    }
    if kind not in required or not required[kind].issubset(record):
        raise ValueError("Unknown record type or missing type-specific fields")
    constitution_path = root / "constitution/constitution.yaml"
    if any(path.is_symlink() for path in (constitution_path, *constitution_path.parents)):
        raise ValueError("Symlinked project paths are refused")
    constitution_bytes = constitution_path.read_bytes()
    document = yaml.load(constitution_bytes, Loader=StrictLoader)
    project_id = identifier(document["project_id"])
    if root.absolute().parts[-2:] != ("agentcraft_projects", project_id):
        raise ValueError("Expected agentcraft_projects/<project-id> root")
    project_record = kind in {"decision", "checkpoint"} and record.get("run_id") is None
    if not project_record and validate(constitution_path):
        raise ValueError("Progress and results require a valid ready constitution")
    stage = record.setdefault("stage", "optimization")
    if stage not in {"data-understanding", "optimization"}:
        raise ValueError("Unknown execution stage")
    if not project_record:
        if document["status"] == "exploring" and stage != "data-understanding":
            raise ValueError("Exploring constitutions permit only data-understanding records")
        if stage == "data-understanding":
            if document["schema_version"] != 2 or "data_understanding" not in document:
                raise ValueError("Data-understanding scope must be declared")
            if record.setdefault("evidence_class", "exploratory") != "exploratory":
                raise ValueError("Data-understanding evidence must remain exploratory")
            if kind == "result" and record["verdict"] not in {"inconclusive", "blocked"}:
                raise ValueError("Exploration cannot claim comparative improvement")
    for field in ("series_id", "run_id", "parent_run_id", "iteration"):
        record.setdefault(field, None)
    if record["run_id"] is None:
        if not project_record or any(record[field] is not None for field in ("series_id", "parent_run_id", "iteration")):
            raise ValueError("Only project decisions/checkpoints may omit run context")
    else:
        identifier(record["run_id"])
        identifier(record["series_id"])
        if record["parent_run_id"] is not None:
            identifier(record["parent_run_id"])
        if type(record["iteration"]) is not int or record["iteration"] < 1:
            raise ValueError("A run requires a positive iteration number")
    if kind == "event":
        sequence = record["sequence"]
        if type(sequence) is not int or sequence < 1:
            raise ValueError("A progress event requires a positive sequence")
        legacy_events = root / "results" / record["run_id"] / "events"
        if list(legacy_events.glob(f"{sequence:06d}-*.json")):
            raise ValueError("Progress sequence already exists")
    if (root / "decisions" / f"{record_id}.json").exists():
        raise FileExistsError("Legacy decision ID already exists")
    if kind == "result" and (root / "results" / record["run_id"] / "run.json").exists():
        raise FileExistsError("Legacy settled run already exists")
    archive_root = contained(root, "records/v2")
    for existing_path in archive_root.glob("*/record.json"):
        existing_path = contained(root, str(existing_path.relative_to(root)))
        existing = json.loads(existing_path.read_text())
        if existing["id"] == record_id:
            raise FileExistsError("Record ID already exists")
        if record["run_id"] and existing["run_id"] == record["run_id"]:
            if kind == "result" and existing["record_type"] == "result":
                raise FileExistsError("Settled run already exists")
            if kind == "event" and existing["record_type"] == "event" and existing["sequence"] == record["sequence"]:
                raise ValueError("Progress sequence already exists")
    captured = {"artifacts/constitution.yaml": constitution_bytes}
    artifacts = []
    snapshot_root = snapshot_root or root
    for index, relative in enumerate(snapshots):
        source = contained(snapshot_root, relative)
        if any(part in {".git", "data", "reference_project", "node_modules", ".runtime"} for part in Path(relative).parts):
            raise ValueError("Bulk or restricted snapshot path refused")
        if source.name.startswith(".env") or re.search(r"secret|credential|token|id_rsa|id_ed25519|\.(pem|key)$", source.name, re.I):
            raise ValueError("Secret-shaped snapshot path refused")
        if source.stat().st_size > 2 * 1024**2:
            raise ValueError("Snapshot exceeds 2 MiB; reference external evidence instead")
        payload = source.read_bytes()
        payload.decode("utf-8")
        if re.search(rb"(?m)^[ \t]*-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----[ \t]*\r?$", payload) or b"\x00" in payload:
            raise ValueError("Private key or binary snapshot refused")
        relative_output = f"artifacts/{index:04d}-{source.name}"
        captured[relative_output] = payload
        artifacts.append({"path": relative_output, "source_path": relative,
                          "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
    if sum(map(len, captured.values())) > 16 * 1024**2:
        raise ValueError("Snapshot bundle exceeds 16 MiB")
    recorded_at = datetime.now(timezone.utc)
    bundle_name = recorded_at.strftime("%Y%m%dT%H%M%S%fZ") + "-" + record_id
    bundle = contained(root, "records/v2/" + bundle_name)
    destination = bundle / "record.json"
    record.setdefault("occurred_at", None)
    record.setdefault("record_refs", [])
    record.update(schema_version=2, project_id=project_id,
                  recorded_at=recorded_at.isoformat(), artifacts=artifacts,
                  constitution={"revision": document["revision"], "path": "constitution/constitution.yaml",
                                "sha256": hashlib.sha256(constitution_bytes).hexdigest(),
                                "snapshot": "artifacts/constitution.yaml"})
    RECORD_VALIDATOR.validate(record)
    references(root, record["record_refs"])
    payload = (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    archive_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(dir=archive_root, prefix=".pending-"))
    try:
        for relative, content in {**captured, "record.json": payload}.items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if target.read_bytes() != content:
                raise ValueError("Artifact read-back mismatch")
        if bundle.exists():
            raise FileExistsError("Archive destination exists")
        temporary.rename(bundle)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    if destination.read_bytes() != payload:
        raise ValueError("Record read-back mismatch")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path)
    parser.add_argument("--snapshot", action="append", default=[])
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify:
            print(json.dumps({"status": "verified", "records": verify(args.project_root),
                      "scope": "v2 schema, snapshots and explicit reference hashes; not semantic acceptance or total capture"}))
            return
        content = sys.stdin.read(65537)
        if len(content.encode()) > 65536:
            raise ValueError("Record exceeds 64 KiB")
        record = json.loads(content)
        destination = publish(args.project_root, record, snapshots=args.snapshot, snapshot_root=args.snapshot_root)
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, ValidationError) as error:
        parser.exit(2, f"Record refused: {type(error).__name__}; source records retained\n")
    print(json.dumps({"status": "saved", "path": str(destination),
                      "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()