"""Exercise real Git history in isolated repositories, without network access."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import organizer, sync_history as sync


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        env.start()
        self.addCleanup(env.stop)
        self.git("init", "-q", "-b", "test")
        self.git("config", "user.name", "Tester")
        self.git("config", "user.email", "test@example.com")
        self.write("README.md", "<!-- START_TABLE -->\n"
                   "| ID | Problem | Time | Memory | Difficulty | Tags |\n"
                   "| --- | --- | --- | --- | --- | --- |\n<!-- END_TABLE -->\n")
        self.write("scripts/tag_colors.json", (Path(organizer.__file__).parent / "tag_colors.json").read_text())
        self.write(sync.CONFIG, '{"schema": 1}\n')
        self.commit("Enable compaction")
        self.base = self.head()

    def git(self, *args):
        return sync.text(self.root, *args)

    def head(self):
        return self.git("rev-parse", "HEAD")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "--allow-empty", "-qm", message)
        return self.head()

    def submit(self, ms, code="pass\n", name="1-example", prefix="solutions", extra=None):
        folder = f"{prefix}/{name}"
        self.write(f"{folder}/solution.py", code)
        self.write(f"{folder}/README.md", "Difficulty: Easy\n")
        if extra:
            self.write(f"{folder}/{extra}", "extra\n")
        return self.commit(f"Time: {ms} ms (50.00%) | Memory: 20 MB (40.00%) - LeetSync")

    def run_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return sync.synchronize(self.root, offline=True)

    def versions(self):
        return self.git("log", "--format=%s", "--grep=- LeetSync").splitlines()

    def metadata(self, name="1-example"):
        return json.loads((self.root / f"solutions/Easy/{name}/.leetsync.json").read_text())


class SyncHistoryTests(GitFixture):
    def test_main_branch_compacts_results_and_preserves_branch(self):
        self.git("branch", "-m", "main")
        for ms in (12, 8, 15):
            self.submit(ms)
            self.run_sync()
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(len(self.versions()), 1)
        self.assertIn("Time: 8 ms", self.metadata()["message"])

    def test_identical_submissions_keep_only_best_and_are_idempotent(self):
        for ms in (12, 10, 15, 8, 11):
            self.submit(ms)
            self.run_sync()
        self.assertEqual(len(self.versions()), 1)
        self.assertEqual(self.git("rev-list", "--count", f"{self.base}..HEAD"), "1")
        self.assertIn("Time: 8 ms", self.versions()[0])
        self.assertIn("Time: 8 ms", self.metadata()["message"])
        self.assertNotIn("history", self.metadata())
        self.assertIn("| 8 ms (50.00%) |", (self.root / "README.md").read_text())
        head = self.head()
        self.assertEqual(self.run_sync(), head)
        self.submit(8)
        self.assertEqual(self.run_sync(), head)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_changed_code_creates_version_even_when_slower_and_revert_is_new(self):
        for ms, code in ((8, "A\n"), (15, "B\n"), (11, "B\n"), (20, "A\n")):
            self.submit(ms, code)
            self.run_sync()
        self.assertEqual([v.split(" ms")[0] for v in self.versions()], ["Time: 20", "Time: 11", "Time: 8"])

    def test_interleaved_tasks_keep_other_history_and_notes(self):
        self.submit(12)
        self.run_sync()
        self.submit(3, name="2-other")
        self.run_sync()
        notes = "solutions/Easy/2-other/notes.ipynb"
        self.write(notes, '{"personal": "keep me"}\n')
        self.commit("Write personal notes")
        self.submit(8)
        self.run_sync()
        self.assertEqual(len(self.versions()), 2)
        self.assertIn("Write personal notes", self.git("log", "--format=%s"))
        self.assertEqual((self.root / notes).read_text(), '{"personal": "keep me"}\n')
        with sync.at_root(self.root):
            for task in organizer.discover_tasks():
                info = organizer.submission(task)
                self.git("merge-base", "--is-ancestor", info["source_commit"], "HEAD")

    def test_queued_submissions_do_not_lose_intermediate_code_versions(self):
        self.submit(12, "A\n")
        self.run_sync()
        self.submit(8, "A\n")
        self.submit(15, "B\n")
        self.submit(20, "C\n")
        self.run_sync()
        self.submit(11, "C\n")
        self.run_sync()
        self.assertEqual([v.split(" ms")[0] for v in self.versions()], ["Time: 11", "Time: 15", "Time: 8"])
        self.assertEqual((self.root / "solutions/Easy/1-example/solution.py").read_text(), "C\n")

    def test_added_renamed_and_deleted_files_preserve_versions(self):
        self.submit(12)
        self.run_sync()
        self.submit(8, extra="helper.py")
        self.run_sync()
        folder = self.root / "solutions/Easy/1-example"
        (folder / "helper.py").rename(folder / "utility.py")
        self.commit("Time: 7 ms - LeetSync")
        self.run_sync()
        (folder / "utility.py").unlink()
        self.commit("Time: 6 ms - LeetSync")
        self.run_sync()
        self.assertEqual(len(self.versions()), 4)
        self.assertFalse((folder / "utility.py").exists())

    def test_manual_task_change_is_a_version_boundary(self):
        self.submit(12)
        self.run_sync()
        self.write("solutions/Easy/1-example/notes.ipynb", '{"notes": "mine"}')
        self.commit("Notes")
        self.run_sync()
        self.submit(8)
        self.run_sync()
        self.assertEqual(len(self.versions()), 2)
        self.assertIn("Notes", self.git("log", "--format=%s"))

    def test_queued_raw_deletion_reaches_normalized_folder(self):
        self.submit(12, extra="helper.py")
        (self.root / "solutions/1-example/helper.py").unlink()
        self.commit("Time: 8 ms - LeetSync")
        self.run_sync()
        self.assertEqual(len(self.versions()), 2)
        self.assertFalse((self.root / "solutions/Easy/1-example/helper.py").exists())

    def test_empty_manual_commit_does_not_restore_raw_directories(self):
        self.submit(12)
        self.commit("Empty manual checkpoint")
        self.run_sync()
        self.assertFalse((self.root / "solutions/1-example").exists())
        self.assertTrue((self.root / "solutions/Easy/1-example/solution.py").exists())
        self.assertIn("Empty manual checkpoint", self.git("log", "--format=%s"))

    def test_zero_runtime_and_memory_are_kept_from_same_submission(self):
        self.submit(2)
        self.run_sync()
        self.submit(0)
        self.run_sync()
        self.submit(0)
        self.git("commit", "--amend", "-qm", "Time: 0 ms (99.00%) | Memory: 1 MB - LeetSync")
        self.run_sync()
        self.assertEqual(len(self.versions()), 1)
        self.assertIn("Memory: 20 MB", self.metadata()["message"])

    def test_merge_after_checkpoint_is_rejected_without_changes(self):
        self.git("checkout", "-qb", "side")
        self.write("side.txt", "side")
        self.commit("Side")
        self.git("checkout", "test")
        self.write("main.txt", "main")
        self.commit("Main")
        self.git("merge", "--no-ff", "side", "-m", "Merge")
        head = self.head()
        with self.assertRaisesRegex(ValueError, "Merge commits"):
            self.run_sync()
        self.assertEqual(self.head(), head)

    def test_existing_organized_baseline_is_used_and_metadata_remapped(self):
        self.submit(12)
        with sync.at_root(self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(organizer.main(offline=True), 0)
        # Moving the activation file's commit establishes the already organized baseline.
        self.write(sync.CONFIG, '{"schema": 1}\n\n')
        self.commit("Activate after organization")
        count = len(self.versions())
        self.submit(8)
        self.run_sync()
        self.assertEqual(len(self.versions()), count)
        with sync.at_root(self.root):
            info = organizer.submission(self.root / "solutions/Easy/1-example")
        self.assertIn("Time: 8 ms", info["message"])
        self.git("merge-base", "--is-ancestor", info["source_commit"], "HEAD")

    def test_failure_does_not_change_real_checkout(self):
        self.submit(12)
        self.run_sync()
        self.submit(8)
        self.write("solutions/1-example/notes.ipynb", '{"conflict": true}')
        self.commit("Time: 8 ms - LeetSync")
        head, tree = self.head(), self.git("rev-parse", "HEAD^{tree}")
        with self.assertRaisesRegex(ValueError, "Conflicting personal notes"):
            self.run_sync()
        self.assertEqual(self.head(), head)
        self.assertEqual(self.git("rev-parse", "HEAD^{tree}"), tree)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_dirty_checkout_and_wrong_branch_are_rejected(self):
        self.write("local.txt", "uncommitted")
        with self.assertRaisesRegex(ValueError, "Commit or stash"):
            self.run_sync()
        self.commit("Local file")
        self.git("checkout", "-qb", "other")
        with self.assertRaisesRegex(ValueError, "test branch"):
            self.run_sync()

    def test_ambiguous_empty_result_does_not_guess_the_task(self):
        self.commit("Time: 8 ms - LeetSync")
        head = self.head()
        with self.assertRaisesRegex(ValueError, "Cannot identify"):
            self.run_sync()
        self.assertEqual(self.head(), head)

    def test_explicit_readme_pair_identifies_queued_empty_result(self):
        self.submit(12)
        self.commit("Added README.md file for Example")
        self.commit("Time: 8 ms | Memory: 19 MB - LeetSync")
        self.run_sync()
        self.assertEqual(len(self.versions()), 1)
        self.assertIn("Time: 8 ms", self.metadata()["message"])
        self.assertEqual(self.git("rev-list", "--count", f"{self.base}..HEAD"), "1")

    def test_explicit_lease_refuses_concurrent_remote_submission(self):
        remote = self.root / "remote.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "origin", "test")
        expected = self.head()
        self.commit("Concurrent update")
        self.git("push", "origin", "test")
        with self.assertRaises(subprocess.CalledProcessError):
            self.git("push", f"--force-with-lease=refs/heads/test:{expected}", "origin", f"{expected}:refs/heads/test")
        self.assertEqual(sync.text(remote, "rev-parse", "refs/heads/test"), self.head())


if __name__ == "__main__":
    unittest.main()
