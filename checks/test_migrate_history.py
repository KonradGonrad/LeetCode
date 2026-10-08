"""Migration preserves material history and feeds the live synchronizer."""

import contextlib
import io
import json
from unittest.mock import patch

from checks.test_sync_history import GitFixture
from scripts import migrate_history as migration, organizer, sync_history as sync


class MigrationTests(GitFixture):
    def test_folder_latest_commit_displays_its_best_leetsync_result(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        self.migrate()
        self.assertEqual(
            self.git("log", "-1", "--format=%s", "--", "solutions/Easy/1-example"),
            self.metadata()["message"],
        )

    def test_migration_metadata_does_not_hide_later_personal_notes(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        self.write("solutions/Easy/1-example/notes.ipynb", '{"personal": "explanation"}\n')
        self.commit("Explain approach")
        before = self.user_files()
        report = self.migrate()
        self.assertEqual(self.user_files(), before)
        self.assertEqual(self.git("log", "-1", "--format=%s", "--", "solutions/Easy/1-example"),
                         "Explain approach")
        self.assertFalse(self.metadata()["comparison_valid"])
        self.assertIn("Time: 8 ms", self.metadata()["message"])
        self.assertEqual(len(self.versions()), 1)

    def assert_folder_results(self, names):
        for name in names:
            with self.subTest(task=name):
                self.assertEqual(self.git("log", "-1", "--format=%s", "--", f"solutions/Easy/{name}"),
                                 self.metadata(name)["message"])

    def test_multiple_folders_keep_their_own_result_after_future_improvement(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        self.submit(3, name="2-other")
        self.organize()
        self.migrate()
        self.assert_folder_results(("1-example", "2-other"))
        count = self.git("rev-list", "--count", "HEAD")
        self.submit(6)
        self.run_sync()
        self.assert_folder_results(("1-example", "2-other"))
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), count)
        self.assertEqual(len(self.versions()), 2)
        self.submit(5)
        self.run_sync()
        self.assert_folder_results(("1-example", "2-other"))
        self.assertTrue(self.migrate()["already_migrated"])

    def test_existing_v1_migration_can_be_repaired_without_extra_commits(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        self.submit(3, name="2-other")
        self.organize()
        # Reproduce the old finalizer: all metadata belongs to one migration node.
        with patch.object(migration, "place_folder_results", return_value=({}, [])), \
                patch.object(migration, "mark_placement", side_effect=lambda root: (
                    sync.text(root, "rev-parse", "HEAD"), sync.text(root, "rev-parse", "HEAD"))):
            self.migrate()
        self.assertEqual(self.git("log", "-1", "--format=%s", "--", "solutions/Easy/1-example"),
                         "Migrate LeetSync history")
        count, tree = self.git("rev-list", "--count", "HEAD"), self.git("rev-parse", "HEAD^{tree}")
        report = self.migrate()
        self.assertTrue(report["repaired_folder_results"])
        self.assert_folder_results(("1-example", "2-other"))
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), count)
        self.assertEqual(self.git("rev-parse", "HEAD^{tree}"), tree)
        self.assertEqual(len(self.versions()), 2)
        self.assertTrue(self.migrate()["already_migrated"])

    def organize(self):
        with sync.at_root(self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(organizer.main(offline=True), 0)

    def repeat(self, ms, title="Example", memory=20):
        self.commit(f"Added README.md file for {title}")
        return self.commit(f"Time: {ms} ms | Memory: {memory} MB - LeetSync")

    def migrate(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return migration.migrate(self.root, offline=True, **kwargs)

    def user_files(self):
        tree = migration.History(self.root).tree(self.head())
        return {name: value for name, value in tree.items()
                if name != "README.md" and not name.startswith("assets/")
                and not name.endswith("/.leetsync.json")}

    def test_legacy_empty_results_best_time_and_organizer_copies(self):
        self.submit(12)
        for ms in (10, 15, 8, 11):
            self.repeat(ms)
        self.organize()
        before = self.user_files()
        original = self.head()
        report = self.migrate()
        self.assertEqual(report["collapsed_results"], 4)
        self.assertEqual(report["removed_organizer_commits"], 1)
        self.assertEqual(report["ambiguous_results"], [])
        self.assertEqual(len(self.versions()), 1)
        self.assertIn("Time: 8 ms", self.metadata()["message"])
        self.assertEqual(self.user_files(), before)
        self.assertEqual(self.git("rev-parse", f"refs/leetsync/backups/{original}"), original)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_code_changes_and_reverts_stay_separate(self):
        self.submit(12, "A\n")
        self.repeat(8)
        self.submit(15, "B\n")
        self.repeat(11)
        self.submit(20, "A\n")
        self.organize()
        report = self.migrate()
        self.assertEqual(report["versions_kept"], 3)
        self.assertEqual([line.split(" ms")[0] for line in self.versions()], ["Time: 20", "Time: 11", "Time: 8"])

    def test_manual_notes_and_folder_changes_preserve_boundaries(self):
        self.submit(12)
        self.organize()
        self.write("solutions/Easy/1-example/notes.ipynb", '{"personal": "reasoning"}')
        self.commit("My reasoning")
        self.submit(8)
        self.organize()
        self.write("solutions/Easy/1-example/helper.py", "helper\n")
        self.commit("Add helper")
        self.submit(7)
        self.organize()
        files = self.user_files()
        self.migrate()
        self.assertEqual(len(self.versions()), 3)
        self.assertIn("My reasoning", self.git("log", "--format=%s"))
        self.assertIn("Add helper", self.git("log", "--format=%s"))
        self.assertEqual(self.user_files(), files)

    def test_dry_run_and_repeat_migration_are_noops_on_checkout(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        before = self.head()
        self.write("uncommitted.txt", "keep this")
        with self.assertRaisesRegex(ValueError, "Commit or stash"):
            self.migrate()
        preview = self.migrate(dry_run=True)
        self.assertEqual(self.head(), before)
        self.assertEqual(preview["collapsed_results"], 1)
        self.assertEqual((self.root / "uncommitted.txt").read_text(), "keep this")
        (self.root / "uncommitted.txt").unlink()
        self.migrate()
        after = self.head()
        self.assertTrue(self.migrate()["already_migrated"])
        self.assertEqual(self.head(), after)

    def test_future_sync_uses_migrated_best_and_preserves_code_versions(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        self.migrate()
        count = self.git("rev-list", "--count", "HEAD")
        for ms in (10, 6, 9):
            self.submit(ms)
            self.run_sync()
            self.assertEqual(self.git("rev-list", "--count", "HEAD"), count)
        self.assertIn("Time: 6 ms", self.metadata()["message"])
        self.submit(20, "new implementation\n")
        self.run_sync()
        self.assertEqual(len(self.versions()), 2)

    def test_ambiguous_results_are_reported_and_retained(self):
        self.submit(12)
        ambiguous = self.commit("Time: 1 ms - LeetSync")
        self.organize()
        report = self.migrate()
        self.assertEqual(report["ambiguous_results"][0]["commit"], ambiguous)
        self.assertIn("Time: 1 ms - LeetSync", self.versions())
        self.assertIn("Time: 12 ms", self.metadata()["message"])

    def test_metadata_references_in_retained_snapshots_are_reachable(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        self.submit(15, name="2-other")
        self.organize()
        self.migrate()
        history = migration.History(self.root)
        for commit in self.git("rev-list", "HEAD").splitlines():
            for name, (_, blob) in history.tree(commit).items():
                if name.endswith("/.leetsync.json"):
                    metadata = json.loads(history.blob(blob))
                    for key in ("source_commit", "organization_commit"):
                        if metadata.get(key):
                            self.git("merge-base", "--is-ancestor", metadata[key], commit)

    def test_migration_keeps_unrelated_manual_empty_commit(self):
        self.submit(12)
        self.commit("Manual checkpoint")
        self.repeat(8)
        self.organize()
        self.migrate()
        self.assertIn("Manual checkpoint", self.git("log", "--format=%s"))

    def test_zero_tie_keeps_same_winning_memory(self):
        self.submit(2)
        self.repeat(0, memory=25)
        self.repeat(0, memory=10)
        self.organize()
        self.migrate()
        self.assertIn("Memory: 25 MB", self.metadata()["message"])

    def test_normalized_fingerprint_matches_live_comparison(self):
        self.submit(12)
        before = migration.History(self.root)
        expected = before.tasks(before.tree(self.head()))["1-example"]["fingerprint"]
        self.organize()
        with sync.at_root(self.root):
            actual = sync.fingerprint(sync.snapshot(self.root / "solutions/Easy/1-example"))
        self.assertEqual(actual, expected)

    def test_manual_code_revert_does_not_merge_separate_versions(self):
        self.submit(12, "A\n")
        self.organize()
        self.write("solutions/Easy/1-example/solution.py", "B\n")
        self.commit("Try B")
        self.write("solutions/Easy/1-example/solution.py", "A\n")
        self.commit("Return to A")
        self.submit(8, "A\n")
        self.organize()
        self.migrate()
        self.assertEqual(len(self.versions()), 2)
        self.assertIn("Try B", self.git("log", "--format=%s"))
        self.assertIn("Return to A", self.git("log", "--format=%s"))

    def test_signed_descendant_aborts_without_rewriting_checkout(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        raw = sync.git(self.root, "cat-file", "commit", self.head())
        headers, message = raw.split(b"\n\n", 1)
        signed = sync.git(self.root, "hash-object", "-t", "commit", "-w", "--stdin",
                          data=headers + b"\ngpgsig test-signature\n\n" + message).decode().strip()
        self.git("update-ref", "HEAD", signed, self.head())
        with self.assertRaisesRegex(ValueError, "signed historical commit"):
            self.migrate()
        self.assertEqual(self.head(), signed)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_unmeasured_manual_revert_remains_boundary_for_future_sync(self):
        self.submit(12)
        self.repeat(8)
        self.organize()
        note = self.root / "solutions/Easy/1-example/notes.ipynb"
        original = note.read_text()
        note.write_text('{"personal": "changed"}')
        self.commit("Change notes")
        note.write_text(original)
        self.commit("Restore notes")
        report = self.migrate()
        self.assertEqual(report["current_comparison_boundaries"], ["1-example"])
        self.submit(20)
        self.run_sync()
        self.assertEqual(len(self.versions()), 2)
        self.assertIn("Time: 8 ms", self.versions()[1])
        self.assertIn("Time: 20 ms", self.metadata()["message"])

    def test_main_branch_migration_and_future_sync(self):
        self.git("branch", "-m", "main")
        self.submit(12)
        self.repeat(8)
        self.organize()
        report = self.migrate()
        self.assertFalse(report["already_migrated"])
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")
        self.submit(15)
        self.run_sync()
        self.assertEqual(len(self.versions()), 1)
        self.assertIn("Time: 8 ms", self.metadata()["message"])
        self.assertTrue(self.migrate()["already_migrated"])

    def test_historical_merge_aborts_without_rewriting_checkout(self):
        self.git("checkout", "-qb", "side")
        self.write("side.txt", "side")
        self.commit("Side")
        self.git("checkout", "test")
        self.write("main.txt", "main")
        self.commit("Main")
        self.git("merge", "--no-ff", "side", "-m", "Merge")
        head = self.head()
        with self.assertRaisesRegex(ValueError, "Historical merges"):
            self.migrate()
        self.assertEqual(self.head(), head)
