"""Rebuild against the remote tip and publish with an explicit, retryable lease."""

import argparse
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from . import migrate_history, sync_history as sync
else:
    import migrate_history
    import sync_history as sync


def publish(root, *, offline=False, migrate=False, attempts=5):
    root = Path(root).resolve()
    branch = sync.text(root, "symbolic-ref", "--short", "HEAD")
    if branch not in ("main", "test"):
        raise ValueError("Publishing is restricted to main or test")
    if sync.text(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Commit or stash local changes before publishing")
    ref = f"refs/heads/{branch}"
    for attempt in range(attempts):
        sync.git(root, "fetch", "--no-tags", "origin", ref)
        expected = sync.text(root, "rev-parse", "FETCH_HEAD")
        with tempfile.TemporaryDirectory(prefix="leetsync-publish-") as directory:
            work = Path(directory) / "repo"
            sync.git(root, "clone", "--no-hardlinks", "--no-checkout", str(root), str(work))
            sync.git(work, "checkout", "-B", branch, expected)
            for key in ("user.name", "user.email"):
                sync.git(work, "config", key, sync.text(root, "config", key))
            if migrate:
                migrate_history.migrate(work, offline=offline)
            final = sync.synchronize(work, offline=offline)
            sync.git(root, "fetch", "--no-tags", str(work), final)
        try:
            sync.git(root, "push", f"--force-with-lease={ref}:{expected}", "origin", f"{final}:{ref}")
            print(f"Published {branch}: {final} (attempt {attempt + 1})")
            return final
        except subprocess.CalledProcessError:
            sync.git(root, "fetch", "--no-tags", "origin", ref)
            if sync.text(root, "rev-parse", "FETCH_HEAD") == expected:
                raise  # Authentication, permissions, hooks, etc. are not races.
            print(f"Remote {branch} changed; rebuilding from its latest tip")
    raise ValueError(f"Remote kept changing during {attempts} publish attempts; rerun synchronization")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--migrate-history", action="store_true")
    args = parser.parse_args()
    try:
        publish(Path(__file__).resolve().parents[1], offline=args.offline, migrate=args.migrate_history)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sync.organizer.report_error("History publication failed", error)
        raise SystemExit(1)
