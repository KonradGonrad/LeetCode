"""Integration checks using disposable Git repositories, never the real index."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import organizer


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.git("init", "-q")
        self.git("config", "user.name", "Test Bot")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.write("README.md", "Before\n<!-- START_TABLE -->\n<!-- END_TABLE -->\nAfter\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial")
        self.original_git = organizer.git
        self.settings = patch.multiple(
            organizer, ROOT=self.root, SOLUTIONS=self.root / "solutions",
            README=self.root / "README.md",
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def task(self, name, message):
        self.write(f"solutions/{name}/solution.py", f"# {name}\n")
        self.git("add", "solutions")
        self.git("commit", "-qm", message)

    def run_organizer(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return organizer.main()

    def test_separate_messages_paths_and_unrelated_staging(self):
        first = "Time: 0 ms\n\nMemory: 18 MB\nUnicode characters: ąę"
        second = 'Time: 5 ms; "quoted" $(not-a-command)'
        self.task("1-two-sum", first)
        self.task("125-valid-palindrome", second)
        before = self.git("rev-parse", "HEAD").strip()
        self.write("unrelated.txt", "leave staged")
        self.git("add", "unrelated.txt")
        self.assertEqual(self.run_organizer(), 0)
        commits = self.git("rev-list", "--reverse", f"{before}..HEAD").splitlines()
        self.assertEqual(len(commits), 3)
        messages = [self.git("log", "-1", "--pretty=%B", sha).rstrip("\n") for sha in commits]
        self.assertEqual(messages, [first, second, "Update README"])
        for sha, name, category in zip(commits[:2], ["1-two-sum", "125-valid-palindrome"], ["Arrays_and_Hashing", "Two_Pointers"]):
            paths = set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", sha).splitlines())
            self.assertEqual(paths, {
                f"solutions/{name}/solution.py",
                f"Algorithm/{category}/{name}/solution.py",
                f"Algorithm/{category}/{name}/notes.md",
            })
        self.assertEqual(self.git("show", "--pretty=", "--name-only", "HEAD").strip(), "README.md")
        self.assertEqual(self.git("diff", "--cached", "--name-only").strip(), "unrelated.txt")
        self.assertFalse((self.root / "solutions").exists())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(organizer.commit_paths("no-op", self.root / "README.md"))
        self.assertEqual(len(self.git("rev-list", f"{before}..HEAD").splitlines()), 3)

    def test_commit_failure_does_not_contaminate_next_task_or_readme(self):
        self.task("1-two-sum", "First task")
        self.task("125-valid-palindrome", "Second task")
        before = self.git("rev-parse", "HEAD").strip()

        def fail_first_commit(*args, **kwargs):
            if args[0] == "commit" and "First task" in args:
                raise subprocess.CalledProcessError(1, args, output="", stderr="hook rejected")
            return self.original_git(*args, **kwargs)

        with patch.object(organizer, "git", side_effect=fail_first_commit):
            self.assertEqual(self.run_organizer(), 1)
        commits = self.git("rev-list", "--reverse", f"{before}..HEAD").splitlines()
        self.assertEqual(len(commits), 2)
        self.assertEqual(self.git("log", "-1", "--pretty=%B", commits[0]).strip(), "Second task")
        self.assertNotIn("1-two-sum", self.git("show", "--pretty=", "--name-only", commits[0]))
        self.assertEqual(self.git("show", "--pretty=", "--name-only", "HEAD").strip(), "README.md")
        self.assertIn("1-two-sum", self.git("diff", "--cached", "--name-only"))

    def test_untracked_task_is_preserved_and_other_tasks_continue(self):
        self.task("125-valid-palindrome", "Tracked")
        path = self.write("solutions/1-two-sum/solution.py", "untracked")
        self.assertEqual(self.run_organizer(), 1)
        self.assertTrue(path.exists())
        self.assertTrue((self.root / "Algorithm/Two_Pointers/125-valid-palindrome/solution.py").exists())
        self.assertEqual(self.git("log", "-1", "--pretty=%B").strip(), "Update README")

    def test_restored_task_gets_original_leetsync_message_on_destination(self):
        message = "Time: 3 ms (53.54%) | Memory: 20.6 MB (19.09%) - LeetSync"
        self.task("1-two-sum", message)
        original = self.git("rev-parse", "HEAD").strip()
        self.git("rm", "-r", "solutions/1-two-sum")
        self.git("commit", "-qm", "Automatic organization")
        self.git("restore", f"--source={original}", "--", "solutions/1-two-sum")
        self.git("add", "solutions")
        self.git("commit", "-qm", "Restore solutions directory from main")
        before = self.git("rev-parse", "HEAD").strip()
        self.assertEqual(self.run_organizer(), 0)
        target = "Algorithm/Arrays_and_Hashing/1-two-sum"
        self.assertEqual(self.git("log", "-1", "--pretty=%B", "--", target).strip(), message)
        commits = self.git("rev-list", "--reverse", f"{before}..HEAD").splitlines()
        self.assertEqual(len(commits), 3)
        self.assertEqual(
            self.git("show", "--pretty=", "--name-only", commits[1]).strip(),
            f"{target}/.leetsync.json",
        )
        metadata = json.loads((self.root / target / ".leetsync.json").read_text())
        self.assertEqual(metadata["source_commit"], original)
        self.assertEqual(metadata["message"], message)
        self.assertEqual(metadata["organization_commit"], commits[0])
        # A later bulk restore of identical code still gets a folder commit.
        self.git("restore", f"--source={original}", "--", "solutions/1-two-sum")
        self.git("add", "solutions")
        self.git("commit", "-qm", "Restore solutions again")
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(self.git("log", "-1", "--pretty=%B", "--", target).strip(), message)
        self.assertEqual(
            json.loads((self.root / target / ".leetsync.json").read_text())["source_commit"],
            original,
        )


if __name__ == "__main__":
    unittest.main()
