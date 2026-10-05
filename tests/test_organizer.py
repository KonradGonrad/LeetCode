"""Integration tests run in temporary Git repositories without network access."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
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
        self.write("scripts/tag_colors.json", (Path(organizer.__file__).parent / "tag_colors.json").read_text())
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
            return organizer.main(offline=True)

    def test_flat_solutions_notebooks_scoped_commits_and_idempotence(self):
        task, original = self.task()
        self.write("unrelated.txt", "keep staged")
        self.git("add", "unrelated.txt")
        self.assertEqual(self.run_organizer(), 0)
        task = self.root / "solutions/Easy/1-two-sum"
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
        self.assertIn("| ID | Problem | Time | Memory | Difficulty | Tags |", readme)
        self.assertIn("![Easy]", readme)
        self.assertIn("| 3 ms | 20 MB |", readme)
        self.assertIn("[💻]", readme)
        self.assertIn("[📝]", readme)
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
        target = self.root / "solutions/Easy/1-two-sum"
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
        task = self.root / "solutions/Easy/1-two-sum"
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
        rows = [line for line in table.splitlines() if line.startswith("| ") and line.split("|")[1].strip().isdigit()]
        self.assertEqual(len(rows), 10)
        self.assertIn("12-problem", rows[0])
        self.assertIn("3-problem", rows[-1])
        self.assertEqual(table.count("<details>"), 1)

    def test_new_submission_updates_result_but_keeps_notebook(self):
        task, old = self.task()
        self.assertEqual(self.run_organizer(), 0)
        task = self.root / "solutions/Easy/1-two-sum"
        before = (task / "notes.ipynb").read_bytes()
        self.write("solutions/1-two-sum/solution.py", "# faster\n")
        self.write("solutions/1-two-sum/README.md", "Difficulty: Easy")
        self.git("add", ".")
        self.git("commit", "-qm", "Time: 1 ms - LeetSync")
        new = self.git("rev-parse", "HEAD").strip()
        self.assertNotEqual(old, new)
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(organizer.submission(task)["source_commit"], new)
        self.assertEqual((task / "notes.ipynb").read_bytes(), before)
        self.assertIn("| 1 ms |", organizer.generate_table())

    def test_collision_preserves_both_directories(self):
        source, _ = self.task(prefix="Database")
        target, _ = self.task()
        (source / "notes.ipynb").write_text('{"personal": "first"}')
        (target / "notes.ipynb").write_text('{"personal": "second"}')
        self.assertEqual(self.run_organizer(), 1)
        self.assertTrue(source.is_dir())
        self.assertTrue((self.root / "solutions/Easy/1-two-sum").is_dir())

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
        second = self.git("log", "-1", "--format=%H", "--", "solutions/Easy/2-second").strip()
        self.assertNotIn("1-first", self.git("show", "--pretty=", "--name-only", second))
        self.assertIn("1-first", self.git("diff", "--cached", "--name-only"))

    def test_missing_difficulty_and_untracked_solution(self):
        task, _ = self.task()
        (task / "README.md").unlink()
        self.assertEqual(organizer.difficulty(task), "—")
        self.write("solutions/2-untracked/solution.py", "pass")
        self.assertEqual(self.run_organizer(), 1)
        self.assertFalse((self.root / "solutions/2-untracked/notes.ipynb").exists())

    def test_all_difficulty_destinations(self):
        for number, level in enumerate(("Easy", "Medium", "Hard", "Unknown"), start=1):
            task, _ = self.task(f"{number}-level")
            (task / "README.md").write_text(f"Difficulty: {level}")
            self.git("add", ".")
            self.git("commit", "-qm", "Update statement")
        self.assertEqual(self.run_organizer(), 0)
        for number, level in enumerate(("Easy", "Medium", "Hard", "Unknown"), start=1):
            self.assertTrue((self.root / f"solutions/{level}/{number}-level/notes.ipynb").exists())

    def test_difficulty_change_keeps_newer_submission_from_previous_path(self):
        self.task()
        self.assertEqual(self.run_organizer(), 0)
        task = self.root / "solutions/Easy/1-two-sum"
        (task / "solution.py").write_text("# newer version")
        self.git("add", ".")
        self.git("commit", "-qm", "Time: 1 ms - LeetSync")
        newest = self.git("rev-parse", "HEAD").strip()
        self.assertEqual(self.run_organizer(), 0)
        (task / "README.md").write_text("Difficulty: Hard")
        self.git("add", ".")
        self.git("commit", "-qm", "Correct difficulty")
        self.assertEqual(self.run_organizer(), 0)
        target = self.root / "solutions/Hard/1-two-sum"
        self.assertEqual(organizer.submission(target)["source_commit"], newest)
        self.assertIn("| 1 ms |", organizer.generate_table())

    def test_activity_counts_unique_problem_days_and_ignores_organization(self):
        self.task("1-first", day=1)
        self.task("2-second", day=1)
        self.write("solutions/1-first/solution.py", "# resubmission")
        self.git("add", ".")
        with patch.dict(os.environ, {"GIT_COMMITTER_DATE": "2025-01-01T14:00:00+00:00"}):
            self.git("commit", "-qm", "Time: 2 ms - LeetSync")
        self.write("solutions/1-first/solution.py", "# next local day")
        self.git("add", ".")
        with patch.dict(os.environ, {"GIT_COMMITTER_DATE": "2025-01-01T23:30:00+00:00"}):
            self.git("commit", "-qm", "Time: 1 ms - LeetSync")
        expected = {date(2025, 1, 1): 2, date(2025, 1, 2): 1}
        self.assertEqual(organizer.activity.daily_activity(organizer.git, organizer.CODE_EXTENSIONS), expected)
        self.assertEqual(self.run_organizer(), 0)
        self.assertEqual(organizer.activity.daily_activity(organizer.git, organizer.CODE_EXTENSIONS), expected)
        self.assertTrue((self.root / "assets/activity.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_tag_badges_and_performance_columns(self):
        self.task()
        organizer.fetch_tags.save_cache(self.root / "scripts/leetcode_cache.json", {
            "two-sum": {"status": "ok", "tags": ["Array", "Hash Table", "New & Tag"]},
        })
        self.assertEqual(self.run_organizer(), 0)
        table = organizer.generate_table()
        self.assertIn("![Array]", table)
        self.assertIn("![Hash Table]", table)
        badge = next((self.root / "assets/badges").glob("tag-array-*.svg"))
        self.assertIn('fill="#1f6feb"', badge.read_text())
        self.assertEqual(organizer.performance("Time: 0 ms (100.00%) | Memory: 19.3 MB (32.95%) - LeetSync"),
                         ["0 ms (100.00%)", "19.3 MB (32.95%)"])
        self.assertEqual(organizer.performance("Not a result"), ["—", "—"])


class TagCacheTests(unittest.TestCase):
    def test_success_empty_and_failure_are_cached_until_explicit_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "leetcode_cache.json"
            tasks = [Path("1-first"), Path("2-second"), Path("3-third")]
            with patch.object(organizer.fetch_tags, "fetch_tags", side_effect=[["Array"], [], OSError("offline")]) as fetch:
                with contextlib.redirect_stderr(io.StringIO()):
                    result = organizer.fetch_tags.update_cache(tasks, cache)
                self.assertEqual(fetch.call_count, 3)
            self.assertEqual(result["third"]["status"], "error")
            self.assertEqual(result["second"]["tags"], [])
            self.assertEqual(organizer.fetch_tags.load_cache(cache), result)
            with patch.object(organizer.fetch_tags, "fetch_tags") as fetch:
                organizer.fetch_tags.update_cache(tasks, cache)
            fetch.assert_not_called()
            with patch.object(organizer.fetch_tags, "fetch_tags", return_value=["String"]) as fetch:
                result = organizer.fetch_tags.update_cache(tasks, cache, retry_errors=True)
            fetch.assert_called_once_with("third")
            self.assertEqual(result["third"]["tags"], ["String"])

    def test_corrupt_cache_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "leetcode_cache.json"
            path.write_text("{broken")
            with self.assertRaises(ValueError):
                organizer.fetch_tags.update_cache([Path("1-task")], path)
            self.assertEqual(path.read_text(), "{broken")

    def test_graphql_response_validation(self):
        for payload, expected in [
            ({"data": {"question": {"topicTags": [{"name": "Array"}]}}}, ["Array"]),
            ({"data": {"question": {"topicTags": []}}}, []),
            ({"data": {"question": None}}, None),
            ({"errors": [{"message": "denied"}]}, None),
            ({"data": {"question": {"topicTags": "bad"}}}, None),
        ]:
            with self.subTest(payload=payload), patch.object(organizer.fetch_tags.urllib.request, "urlopen") as request:
                request.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
                if expected is None:
                    with self.assertRaises(ValueError):
                        organizer.fetch_tags.fetch_tags("two-sum")
                else:
                    self.assertEqual(organizer.fetch_tags.fetch_tags("two-sum"), expected)


if __name__ == "__main__":
    unittest.main()
