import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repository_inspection import filesystem as inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cleanup-skill-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()

    def file(self, name, content=b"data"):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_counts_hidden_files_empty_groups_and_nested_git_without_root_git(self):
        self.file("src/main.py", b"code")
        self.file("src/nested/data.json", b"{}")
        self.file(".hidden", b"x")
        self.file("vendor/.git/HEAD", b"ref")
        self.file(".git/objects/ignored", b"not counted")
        (self.root / ".cache/empty").mkdir(parents=True)
        report = inventory.scan(self.root, group_depth=2)
        self.assertTrue(report["complete"])
        self.assertEqual(report["totals"], {"files": 4, "logical_bytes": 10,
                                           "directories": 6, "symlinks": 0, "special_files": 0})
        groups = {item["path"]: item for item in report["groups"]}
        self.assertEqual(groups["src"]["logical_bytes"], 6)
        self.assertEqual(groups[".cache/empty"]["files"], 0)
        self.assertEqual(report["excluded_entries"], 1)

    @unittest.skipUnless(hasattr(os, "symlink"), "Host does not support symbolic links")
    def test_never_follows_symlinked_files_or_directories(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "payload").write_bytes(b"do not traverse")
        (self.root / "file-link").symlink_to(outside / "payload")
        (self.root / "directory-link").symlink_to(outside, target_is_directory=True)
        report = inventory.scan(self.root)
        self.assertEqual(report["totals"]["files"], 0)
        self.assertEqual(report["totals"]["symlinks"], 2)

    @unittest.skipUnless(hasattr(os, "link"), "Host does not support hard links")
    def test_hardlinks_are_logical_entries_not_claimed_allocated_bytes(self):
        original = self.file("original", b"abc")
        os.link(original, self.root / "copy")
        report = inventory.scan(self.root)
        self.assertEqual(report["totals"]["logical_bytes"], 6)
        self.assertEqual(report["totals"]["files"], 2)

    def test_exclusion_skips_whole_subtree(self):
        self.file("raw/resource/payload")
        self.file("source/main.py")
        report = inventory.scan(self.root, exclude=("raw",))
        self.assertEqual(report["totals"]["files"], 1)
        self.assertEqual(report["scope"]["excluded_patterns"], [".git", "raw"])

    def test_unreadable_directory_is_incomplete_not_zero_success(self):
        (self.root / "denied").mkdir()
        real_scandir = os.scandir

        def guarded(path):
            if Path(path).name == "denied":
                raise PermissionError(13, "fixture refusal")
            return real_scandir(path)

        with patch.object(inventory.os, "scandir", side_effect=guarded):
            report = inventory.scan(self.root)
        self.assertFalse(report["complete"])
        self.assertEqual(report["error_count"], 1)
        with self.assertRaisesRegex(ValueError, "complete inventories"):
            inventory.compare(report, report)

    def test_compare_records_net_additions_and_refuses_scope_changes(self):
        self.file("source", b"data")
        before = inventory.scan(self.root)
        self.file("generated", b"new")
        after = inventory.scan(self.root)
        result = inventory.compare(before, after)
        self.assertEqual(result["net_removed"]["files"], -1)
        self.assertEqual(result["file_reduction_percent"], -100)
        changed = copy.deepcopy(after)
        changed["scope"]["excluded_patterns"].append("generated")
        with self.assertRaisesRegex(ValueError, "identical roots and counting scope"):
            inventory.compare(before, changed)

    def test_output_is_external_and_never_overwrites(self):
        report = inventory.scan(self.root)
        with self.assertRaisesRegex(ValueError, "outside"):
            inventory.write_report(report, self.root / "report.json")
        target = self.base / "receipt.json"
        with contextlib.redirect_stdout(io.StringIO()):
            inventory.write_report(report, target)
        self.assertEqual(json.loads(target.read_text()), report)
        with self.assertRaises(FileExistsError):
            inventory.write_report(report, target)

    def test_cli_scan_and_compare_and_invalid_root(self):
        self.file("source", b"x")
        report = self.base / "before.json"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(inventory.main(["scan", str(self.root), "--output", str(report)]), 0)
            self.assertEqual(inventory.main(["compare", str(report), str(report)]), 0)
            self.assertEqual(inventory.main(["scan", str(self.base / "absent")]), 2)
        self.assertEqual((self.root / "source").read_bytes(), b"x")


if __name__ == "__main__":
    unittest.main()