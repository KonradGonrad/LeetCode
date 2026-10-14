"""Race real Git pushes against a local bare remote."""

from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from checks.test_sync_history import GitFixture
from scripts import publish_history as publisher, sync_history as sync


class PublishTests(GitFixture):
    def setUp(self):
        super().setUp()
        self.remote_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.remote_temp.cleanup)
        self.remote = Path(self.remote_temp.name) / "remote.git"
        self.git("init", "--bare", str(self.remote))
        self.git("remote", "add", "origin", str(self.remote))
        self.submit(415)
        self.git("push", "origin", "test")

    def test_race_rebuilds_and_keeps_concurrent_upload(self):
        original = sync.synchronize
        calls = []

        def synchronize(work, **kwargs):
            result = original(work, **kwargs)
            calls.append(result)
            if len(calls) == 1:
                self.commit("Added README.md file for Example")
                self.commit("Time: 414 ms - LeetSync")
                self.git("push", "origin", "test")
            return result

        with patch.object(sync, "synchronize", side_effect=synchronize):
            final = publisher.publish(self.root, offline=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sync.text(self.remote, "rev-parse", "test"), final)
        versions = sync.text(self.remote, "log", "test", "--format=%s", "--grep=- LeetSync").splitlines()
        self.assertEqual(versions, ["Time: 414 ms - LeetSync"])

    def test_non_race_failure_is_not_retried(self):
        original = sync.git
        pushes = []

        def git(root, *args, **kwargs):
            if args[0] == "push":
                pushes.append(args)
                raise subprocess.CalledProcessError(1, args, stderr=b"permission denied")
            return original(root, *args, **kwargs)

        with patch.object(sync, "git", side_effect=git):
            with self.assertRaises(subprocess.CalledProcessError):
                publisher.publish(self.root, offline=True)
        self.assertEqual(len(pushes), 1)

    def test_repeated_races_stop_without_overwriting_remote(self):
        original = sync.synchronize

        def synchronize(work, **kwargs):
            result = original(work, **kwargs)
            self.commit("Concurrent manual update")
            self.git("push", "origin", "test")
            return result

        with patch.object(sync, "synchronize", side_effect=synchronize):
            with self.assertRaisesRegex(ValueError, "2 publish attempts"):
                publisher.publish(self.root, offline=True, attempts=2)
        self.assertEqual(sync.text(self.remote, "rev-parse", "test"), self.head())
