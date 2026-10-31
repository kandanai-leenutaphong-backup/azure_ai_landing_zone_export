import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from investigation_notebook import InvestigationNotebook, NotebookError, load_schema, validate_note
from selftest import note_body


class NotebookAPI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "notebook-data"
        self.notebook = InvestigationNotebook(self.root)

    def draft(self, body=None):
        self.notebook.drafts_dir.mkdir(parents=True, exist_ok=True)
        path = self.notebook.drafts_dir / "candidate.json"
        path.write_text(json.dumps(body or note_body()), encoding="utf-8")
        return path

    def test_constructor_and_schema_do_not_create_state(self):
        schema = load_schema()
        self.assertIn("system", schema["properties"])
        self.assertFalse(self.root.exists())
        schema.clear()
        self.assertIn("properties", load_schema())

    def test_publication_survives_a_new_instance(self):
        source = self.draft()
        path, published = self.notebook.publish(source)
        validate_note(published, published=True)
        restarted = InvestigationNotebook(self.root)
        self.assertEqual(restarted.show(published["id"]), {**published, "category": "uncategorized"})
        self.assertEqual(len(restarted.search("copied mechanism", 8)), 1)
        self.assertTrue(path.is_file())
        self.assertFalse(source.exists())

    def test_duplicate_refusal_keeps_draft_and_published_bytes(self):
        path, published = self.notebook.publish(self.draft())
        before = path.read_bytes()
        source = self.draft()
        with self.assertRaises(NotebookError):
            self.notebook.publish(source)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(source.exists())
        self.assertEqual(self.notebook.show(published["id"]), {**published, "category": "uncategorized"})

    def test_sensitive_content_refuses_without_echo_or_removal(self):
        body = note_body()
        value = "Bearer " + "X" * 32
        body["summary"] = value
        source = self.draft(body)
        with self.assertRaises(NotebookError) as caught:
            self.notebook.publish(source)
        self.assertNotIn(value, str(caught.exception))
        self.assertTrue(source.exists())
        self.assertFalse(self.notebook.notes_dir.exists())

    def test_status_noop_refuses_without_mutation(self):
        path, published = self.notebook.publish(self.draft())
        before = path.read_bytes()
        with self.assertRaises(NotebookError):
            self.notebook.status(published["id"], "active", "No change")
        self.assertEqual(path.read_bytes(), before)

    def test_corruption_is_reported_not_deleted(self):
        path, published = self.notebook.publish(self.draft())
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(NotebookError):
            self.notebook.show(published["id"])
        self.assertEqual(path.read_text(encoding="utf-8"), "{}")

    def test_cli_requires_explicit_root(self):
        result = subprocess.run(
            [sys.executable, "-I", "-m", "investigation_notebook", "stats"],
            cwd=self.directory.name, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--root", result.stderr)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()