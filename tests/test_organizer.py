"""Integration tests run in temporary Git repositories without network access."""

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
        env = patch.dict(os.environ, {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        })
        env.start()
        self.addCleanup(env.stop)
        settings = patch.multiple(
            organizer, ROOT=self.root, SOLUTIONS=self.root / "solutions",
            README=self.root / "README.md",
        )
        settings.start()
        self.addCleanup(settings.stop)
        self.git("init", "-q")
        self.git("config", "user.name", "Test Bot")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.write("README.md", "Intro\n<!-- START_TABLE -->\n<!-- END_TABLE -->\nFooter\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial")

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

    def task(self, name="1-two-sum", prefix="solutions", message="Time: 3 ms | Memory: 20 MB - LeetSync", day=1):
        task = self.root / prefix / name
        self.write(f"{prefix}/{name}/solution.py", f"# {name}\n")
        self.write(f"{prefix}/{name}/README.md", "<img alt='Difficulty: Easy' />")
        self.git("add", "--", str(task))
        date = f"2025-01-{day:02d}T12:00:00+00:00"
        with patch.dict(os.environ, {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}):
            self.git("commit", "-qm", message)
        return task, self.git("rev-parse", "HEAD").strip()

    def run_organizer(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return organizer.main()

    def test_flat_solutions_notebooks_scoped_commits_and_idempotence(self):
        task, original = self.task()
        self.write("unrelated.txt", "keep staged")
        self.git("add", "unrelated.txt")
        self.assertEqual(self.run_organizer(), 0)
        notebook = json.loads((task / "notes.ipynb").read_text())
        self.assertEqual(notebook["nbformat"], 4)
        self.assertEqual([cell["cell_type"] for cell in notebook["cells"]], ["markdown", "code"])
        self.assertEqual(notebook["cells"][1]["outputs"], [])
        self.assertEqual(organizer.submission(task)["source_commit"], original)
        self.assertEqual(self.git("log", "-1", "--pretty=%B", "--", "solutions/1-two-sum").strip(),
                         "Time: 3 ms | Memory: 20 MB - LeetSync")
        self.assertEqual(self.git("diff", "--cached", "--name-only").strip(), "unrelated.txt")
        readme = (self.root / "README.md").read_text()
        self.assertIn("notes.ipynb", readme)
        self.assertIn("| Problem | Code | Notes | Time | Difficulty |", readme)
        self.assertIn("| Easy |", readme)
        self.assertIn("Time: 3 ms \\| Memory: 20 MB", readme)
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_legacy_migration_preserves_code_markdown_and_original_date(self):
        task, original = self.task(prefix="Algorithm/Arrays_and_Hashing")
        legacy = "My reasoning\n\nUnicode: ąę\n"
        self.write("Algorithm/Arrays_and_Hashing/1-two-sum/notes.md", legacy)
        self.git("add", ".")
        self.git("commit", "-qm", "Write notes")
        self.assertEqual(self.run_organizer(), 0)
        target = self.root / "solutions/1-two-sum"
        self.assertFalse(task.exists())
        self.assertFalse((self.root / "Algorithm").exists())
        self.assertEqual((target / "solution.py").read_text(), "# 1-two-sum\n")
        notebook = json.loads((target / "notes.ipynb").read_text())
        self.assertEqual("".join(notebook["cells"][0]["source"]), legacy)
        self.assertFalse((target / "notes.md").exists())
        self.assertEqual(organizer.submission(target)["source_commit"], original)
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_existing_notebook_never_overwritten_and_notes_do_not_change_recency(self):
        task, original = self.task()
        self.assertEqual(self.run_organizer(), 0)
        notebook = task / "notes.ipynb"
        content = json.loads(notebook.read_text())
        content["cells"][1]["source"] = ["print('my solution')\n"]
        notebook.write_text(json.dumps(content))
        self.git("add", ".")
        self.git("commit", "-qm", "Edit notebook")
        before = notebook.read_bytes()
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(notebook.read_bytes(), before)
        self.assertEqual(organizer.submission(task)["source_commit"], original)

    def test_only_latest_ten_solutions_in_readme(self):
        for number in range(1, 13):
            self.task(f"{number}-problem", day=number)
        self.assertEqual(self.run_organizer(), 0)
        table = organizer.generate_table()
        rows = [line for line in table.splitlines() if line.startswith("| [")]
        self.assertEqual(len(rows), 10)
        self.assertIn("12-problem", rows[0])
        self.assertIn("3-problem", rows[-1])
        self.assertEqual(table.count("<details>"), 1)

    def test_new_submission_updates_result_but_keeps_notebook(self):
        task, old = self.task()
        self.assertEqual(self.run_organizer(), 0)
        before = (task / "notes.ipynb").read_bytes()
        self.write("solutions/1-two-sum/solution.py", "# faster\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Time: 1 ms - LeetSync")
        new = self.git("rev-parse", "HEAD").strip()
        self.assertNotEqual(old, new)
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(organizer.submission(task)["source_commit"], new)
        self.assertEqual((task / "notes.ipynb").read_bytes(), before)
        self.assertIn("Time: 1 ms", organizer.generate_table())

    def test_collision_preserves_both_directories(self):
        source, _ = self.task(prefix="Database")
        target, _ = self.task()
        self.assertEqual(self.run_organizer(), 1)
        self.assertTrue(source.is_dir())
        self.assertTrue(target.is_dir())

    def test_failure_does_not_contaminate_next_task_commit(self):
        self.task("1-first", message="First - LeetSync")
        self.task("2-second", message="Second - LeetSync")
        original_git = organizer.git
        def fail_first(*args, **kwargs):
            if args[0] == "commit" and "First - LeetSync" in args:
                raise subprocess.CalledProcessError(1, args, stderr="hook rejected")
            return original_git(*args, **kwargs)
        with patch.object(organizer, "git", side_effect=fail_first):
            self.assertEqual(self.run_organizer(), 1)
        second = self.git("log", "-1", "--format=%H", "--", "solutions/2-second").strip()
        self.assertNotIn("1-first", self.git("show", "--pretty=", "--name-only", second))
        self.assertIn("1-first", self.git("diff", "--cached", "--name-only"))

    def test_missing_difficulty_and_untracked_solution(self):
        task, _ = self.task()
        (task / "README.md").unlink()
        self.assertEqual(organizer.difficulty(task), "—")
        self.write("solutions/2-untracked/solution.py", "pass")
        self.assertEqual(self.run_organizer(), 1)
        self.assertFalse((self.root / "solutions/2-untracked/notes.ipynb").exists())


if __name__ == "__main__":
    unittest.main()
