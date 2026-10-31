import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from test_constitution import discovery_fixture, fixture


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("project_records", ROOT / "record.py")
recorder = importlib.util.module_from_spec(SPEC)
with patch.dict(sys.modules, {"validate": sys.modules[fixture.__module__].checker}):
    SPEC.loader.exec_module(recorder)


def decision():
    return {"record_type": "decision", "id": "scope-agreement", "actor": "test-reviewer", "evidence": [],
            "observation": "Test fixture", "hypothesis": None, "decision": "Use a bounded fixture",
            "changed_levers": [], "rationale": "Test only", "approval": "fixture-only",
            "expected_outcome": "Readable record", "acceptance_refs": [], "authority_source": "test",
            "supersedes": None}


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "agentcraft_projects/grid-test"
        self.constitution = self.root / "constitution/constitution.yaml"
        self.constitution.parent.mkdir(parents=True)
        self.constitution.write_text(yaml.safe_dump(fixture()))

    def test_decision_readback_and_duplicate_refusal(self):
        path = recorder.publish(self.root, decision())
        original = path.read_bytes()
        saved = json.loads(original)
        self.assertIsNone(saved["run_id"])
        self.assertEqual(saved["constitution"]["sha256"], hashlib.sha256(self.constitution.read_bytes()).hexdigest())
        with self.assertRaises(FileExistsError):
            recorder.publish(self.root, decision())
        self.assertEqual(path.read_bytes(), original)

    def test_draft_allows_decisions_not_events(self):
        document = fixture()
        document["status"] = "draft"
        self.constitution.write_text(yaml.safe_dump(document))
        recorder.publish(self.root, decision())
        with self.assertRaisesRegex(ValueError, "ready constitution"):
            recorder.publish(self.root, self.event())
        with self.assertRaisesRegex(ValueError, "ready constitution"):
            recorder.publish(self.root, {**decision(), "run_id": "run-1", "series_id": "series-1", "iteration": 1})

    def event(self):
        return {"record_type": "event", "id": "start", "actor": "fixture", "evidence": [],
                "run_id": "run-1", "series_id": "series-1", "iteration": 1, "sequence": 1,
                "phase": "build", "status": "started", "decision_ids": ["scope-agreement"]}

    def test_event_sequence_and_result_path(self):
        event = self.event()
        event_path = recorder.publish(self.root, event)
        self.assertEqual(event_path.name, "record.json")
        self.assertTrue(event_path.parent.name.endswith("-start"))
        with self.assertRaisesRegex(ValueError, "sequence already"):
            recorder.publish(self.root, {**event, "id": "another"})
        result = {key: value for key, value in event.items() if key not in {"sequence", "phase"}}
        result.update(record_type="result", id="result", status="blocked", metrics=[], verdict="blocked",
                      limitations=["fixture"], next_decision=None, settlement="fixture has no workers")
        self.assertTrue(recorder.publish(self.root, result).is_relative_to(self.root / "records/v2"))

    def test_invalid_ids_reserved_fields_and_symlinks_refuse(self):
        for update in ({"id": "../escape"}, {"recorded_at": "invented"}, {"iteration": 1}, {"rationale": float("nan")}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                recorder.publish(self.root, {**decision(), **update})
        (self.root / "records").symlink_to(self.root)
        with self.assertRaises(ValueError):
            recorder.publish(self.root, decision())

    def test_discovery_records_cannot_claim_optimization(self):
        self.constitution.write_text(yaml.safe_dump(discovery_fixture()))
        event = {**self.event(), "stage": "data-understanding", "phase": "profile"}
        path = recorder.publish(self.root, event)
        self.assertEqual(json.loads(path.read_text())["evidence_class"], "exploratory")
        with self.assertRaisesRegex(ValueError, "only data-understanding"):
            recorder.publish(self.root, self.event())
        result = {key: value for key, value in event.items() if key not in {"sequence", "phase"}}
        result.update(record_type="result", id="result", status="completed", metrics=[], verdict="improved",
                      limitations=[], next_decision=None, settlement="no workers")
        with self.assertRaisesRegex(ValueError, "comparative improvement"):
            recorder.publish(self.root, result)
        result["verdict"] = "inconclusive"
        recorder.publish(self.root, result)

    def test_snapshot_survives_source_change_and_verifies(self):
        source = self.root / "candidate.txt"
        source.write_text("before\n")
        path = recorder.publish(self.root, decision(), snapshots=["candidate.txt"])
        record = json.loads(path.read_text())
        self.assertEqual(record["schema_version"], 2)
        snapshot = path.parent / record["artifacts"][0]["path"]
        self.assertEqual(snapshot.read_text(), "before\n")
        source.write_text("after\n")
        self.constitution.write_text("status: draft\n")
        self.assertEqual(recorder.verify(self.root), [str(path)])
        snapshot.write_text("tampered\n")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            recorder.verify(self.root)

    def test_evidence_reference_and_secret_snapshot_refusal(self):
        evidence = self.root / "observed.json"
        evidence.write_text('{"measured": 1}\n')
        reference = {"path": "observed.json", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(), "relation": "outcome"}
        path = recorder.publish(self.root, {**decision(), "record_refs": [reference]})
        self.assertEqual(recorder.verify(self.root), [str(path)])
        evidence.write_text("changed")
        with self.assertRaises(ValueError):
            recorder.verify(self.root)
        with self.assertRaises(ValueError):
            recorder.publish(self.root, {**decision(), "id": "bad-reference", "record_refs": [reference]})
        (self.root / ".env").write_text("not a secret")
        with self.assertRaises(ValueError):
            recorder.publish(self.root, {**decision(), "id": "unsafe"}, snapshots=[".env"])

    def test_checkpoint_schema_and_legacy_evidence_preserved(self):
        checkpoint = {"record_type": "checkpoint", "id": "adoption", "actor": "archivist", "stage": "data-understanding",
                      "evidence": [], "decision_ids": [], "changes": [], "metrics": [], "status": "retrospective",
                      "coverage": {"status": "partial", "observed": ["existing files"], "gaps": ["before-state unavailable"]},
                      "reversion": {"status": "not_verified", "plan": "Retain current bytes; no restore executed"},
                      "rationale": "Adopt existing evidence without inventing history", "supersedes": None}
        legacy = self.root / "results/prior/run.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"id":"prior"}\n')
        prior_bytes = legacy.read_bytes()
        recorder.publish(self.root, checkpoint)
        self.assertEqual(legacy.read_bytes(), prior_bytes)
        recorder.RECORD_VALIDATOR.check_schema(recorder.RECORD_SCHEMA)

    def test_private_key_header_refusal_without_source_false_positive(self):
        source = self.root / "detector.py"
        source.write_text('pattern = b"PRIVATE KEY-----"\n')
        recorder.publish(self.root, decision(), snapshots=["detector.py"])
        source.write_text("-----BEGIN PRIVATE KEY-----\nfixture-not-a-real-key\n-----END PRIVATE KEY-----\n")
        with self.assertRaisesRegex(ValueError, "Private key"):
            recorder.publish(self.root, {**decision(), "id": "private-key"}, snapshots=["detector.py"])


if __name__ == "__main__":
    unittest.main()