"""Normalize new LeetSync submissions and retain one commit per solution version.

All planning, normalization and history rewriting happens in a temporary clone.
The original checkout is updated only after the complete operation succeeds.
"""

import argparse
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Older revisions track Python bytecode; importing helpers must not dirty them.
sys.dont_write_bytecode = True

if __package__:
    from . import organizer
else:
    import organizer

CONFIG = ".leetsync-history.json"
CHECKPOINT = "LeetSync-Checkpoint: 1"
VERSION = "LeetSync-Version: "
RESULT = re.compile(r"^Time:\s*(\d+(?:\.\d+)?)\s*(ms|s)\b[^\n]* - LeetSync$")


def git(root, *args, data=None, env=None):
    return subprocess.run(
        ["git", "--literal-pathspecs", *args], cwd=root, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        env={**os.environ, **(env or {})},
    ).stdout


def text(root, *args):
    return git(root, *args).decode("utf-8").strip()


@contextmanager
def at_root(root):
    previous = organizer.ROOT, organizer.SOLUTIONS, organizer.README
    organizer.ROOT, organizer.SOLUTIONS, organizer.README = root, root / "solutions", root / "README.md"
    try:
        yield
    finally:
        organizer.ROOT, organizer.SOLUTIONS, organizer.README = previous


def runtime(message):
    match = RESULT.fullmatch(message.splitlines()[0]) if message else None
    return Decimal(match[1]) * (1000 if match[2] == "s" else 1) if match else None


def task_root(path):
    parts = Path(path).parts
    if not parts or parts[0] not in ("solutions", "Algorithm", "Database", "Pandas"):
        return None
    for index, part in enumerate(parts[1:], 1):
        if organizer.TASK_PATTERN.fullmatch(part):
            return Path(*parts[:index + 1])
    return None


def task_roots_at(root, revision):
    paths = git(root, "ls-tree", "-r", "--name-only", "-z", revision).split(b"\0")
    return {folder for path in paths if path
            if (folder := task_root(path.decode("utf-8"))) is not None}


def readme_identity(root, revision):
    """Identify an explicit LeetSync README helper by its unique problem title."""
    message = text(root, "show", "-s", "--format=%s", revision)
    match = re.fullmatch(r"Added README\.md file for (.+)", message)
    if not match:
        return None
    def label(value):
        return re.sub(r"[^a-z0-9]", "", html.unescape(value).casefold())
    expected = label(match[1])
    candidates = set()
    for folder in task_roots_at(root, revision):
        titles = [folder.name.split("-", 1)[1]]
        entry = git(root, "ls-tree", revision, "--", (folder / "README.md").as_posix())
        if entry:
            content = git(root, "show", f"{revision}:{folder}/README.md").decode("utf-8")
            heading = re.search(r"<h[12]\b[^>]*>(.*?)</h[12]>", content, re.S | re.I)
            if heading:
                title = html.unescape(re.sub(r"<[^>]+>", "", heading[1])).strip()
                titles.append(re.sub(r"^\d+\.\s*", "", title))
        if any(label(title) == expected for title in titles):
            candidates.add(folder.name)
    return next(iter(candidates)) if len(candidates) == 1 else None


def empty_submission_folder(root, revision):
    parents = text(root, "show", "-s", "--format=%P", revision).split()
    name = readme_identity(root, parents[0]) if len(parents) == 1 else None
    if name is None:
        return None
    folders = [folder for folder in task_roots_at(root, revision) if folder.name == name]
    # Multiple aliases with conflicting contents require explicit changed paths.
    return folders[0] if len(folders) == 1 else None


def snapshot(task):
    """Compare normalized paths, bytes and modes, including personal notebooks."""
    files = []
    for path in sorted(task.rglob("*")):
        organizer.check_path(path)
        if path.is_file() and path.name != ".leetsync.json":
            files.append((path.relative_to(organizer.ROOT).as_posix(),
                          bool(path.stat().st_mode & 0o111), path.read_bytes()))
    return files


def fingerprint(files):
    values = [(name, executable, hashlib.sha256(content).hexdigest())
              for name, executable, content in files]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def write_metadata(task, info):
    path = task / ".leetsync.json"
    organizer.check_path(path)
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def changed_paths(root, commit):
    return [p.decode("utf-8") for p in git(
        root, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", "-z", commit,
    ).split(b"\0") if p]


def apply_paths(root, commit, paths):
    """Apply exact changed blobs, even when normalization removed the raw path."""
    if not paths:
        return
    entries = {}
    for entry in git(root, "ls-tree", "-r", "-z", commit, "--", *paths).split(b"\0"):
        if entry:
            header, name = entry.split(b"\t", 1)
            mode, kind, blob = header.decode().split()
            if kind != "blob" or mode not in ("100644", "100755"):
                raise ValueError("Symlinks and submodules require manual processing")
            entries[name.decode("utf-8")] = (mode, blob)
    for name in paths:
        path = root / name
        organizer.check_path(path)
        if name not in entries and path.is_file():
            path.unlink()
    for name, (mode, blob) in entries.items():
        path = root / name
        organizer.check_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git(root, "cat-file", "blob", blob))
        path.chmod(0o755 if mode == "100755" else 0o644)


def make_commit(root, message, original=None, allow_empty=False):
    git(root, "add", "-A")
    tree = text(root, "write-tree")
    parent = text(root, "rev-parse", "HEAD")
    if not allow_empty and tree == text(root, "rev-parse", "HEAD^{tree}"):
        return parent
    env = {}
    if original:
        fields = git(root, "show", "-s", "--format=%an%x00%ae%x00%aI%x00%cI", original).decode().strip().split("\0")
        env = dict(zip(("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"), fields))
    new = git(root, "commit-tree", tree, "-p", parent, data=(message.rstrip() + "\n").encode(), env=env).decode().strip()
    git(root, "update-ref", "HEAD", new, parent)
    return new


def rewrite_messages(root, replacements):
    """Preserve trees and commit headers; rewrite parent links in topological order."""
    mapping = {}
    if not replacements:
        return mapping
    head = text(root, "rev-parse", "HEAD")
    for old in text(root, "rev-list", "--reverse", "--topo-order", head).splitlines():
        raw = git(root, "cat-file", "commit", old)
        headers, message = raw.split(b"\n\n", 1)
        lines = headers.split(b"\n")
        updated = []
        for line in lines:
            if line.startswith(b"parent "):
                parent = line[7:].decode()
                line = b"parent " + mapping.get(parent, parent).encode()
            updated.append(line)
        if old in replacements:
            # Keep version/checkpoint trailers on commits managed by this script.
            trailers = [line for line in message.decode().splitlines()
                        if line.startswith((VERSION, "LeetSync-Folder-Results: ")) or line == CHECKPOINT]
            message = (replacements[old].rstrip() + ("\n\n" + "\n".join(trailers) if trailers else "") + "\n").encode()
        rebuilt = b"\n".join(updated) + b"\n\n" + message
        if rebuilt != raw:
            if any(line.startswith((b"gpgsig ", b"mergetag ")) for line in lines):
                raise ValueError("Cannot rewrite signed history automatically")
            mapping[old] = git(root, "hash-object", "-t", "commit", "-w", "--stdin", data=rebuilt).decode().strip()
    git(root, "update-ref", "HEAD", mapping.get(head, head), head)
    return mapping


def checkpoint(root):
    config_commit = text(root, "log", "-1", "--format=%H", "--", CONFIG)
    if not config_commit:
        raise ValueError(f"Commit {CONFIG} before running the synchronizer")
    for commit in text(root, "rev-list", "--first-parent", "HEAD").splitlines():
        message = text(root, "show", "-s", "--format=%B", commit)
        if CHECKPOINT in message.splitlines() or commit == config_commit:
            return commit
    raise ValueError("No synchronization checkpoint found")


def process(root, base, pending, offline):
    git(root, "checkout", "--detach", base)
    records = {}
    replacements = {}
    for task in organizer.discover_tasks():
        if task.parent.name not in ("Easy", "Medium", "Hard", "Unknown") or task.parent.parent != root / "solutions":
            raise ValueError("Organize existing folders before enabling history compaction")
        info = organizer.submission(task)
        if info:
            stored = json.loads((task / ".leetsync.json").read_text())
            files = snapshot(task)
            stored.setdefault("fingerprint", fingerprint(files))
            write_metadata(task, stored)
            records[task.name] = {"anchor": info["source_commit"], "info": stored,
                                  "files": files,
                                  "eligible": stored.get("comparison_valid", True)
                                  and stored["fingerprint"] == fingerprint(files)}
    for original in pending:
        headers = git(root, "cat-file", "commit", original).split(b"\n\n", 1)[0]
        if any(line.startswith((b"gpgsig ", b"mergetag ")) for line in headers.splitlines()):
            raise ValueError("Cannot replay signed commits automatically")
        paths = changed_paths(root, original)
        message = text(root, "show", "-s", "--format=%B", original)
        elapsed = runtime(message)
        roots = {task_root(path) for path in paths}
        if elapsed is None:
            if message.splitlines() and message.splitlines()[0].endswith("- LeetSync"):
                raise ValueError(f"Unrecognized LeetSync runtime in {original}")
            if not paths and readme_identity(root, original) is not None:
                continue
            apply_paths(root, original, paths)
            for folder in roots - {None}:
                if folder.name in records:
                    records[folder.name]["eligible"] = False
                    metadata = root / folder / ".leetsync.json"
                    if metadata.is_file():
                        stored = json.loads(metadata.read_text())
                        stored["comparison_valid"] = False
                        write_metadata(metadata.parent, stored)
            make_commit(root, message, original, allow_empty=True)
            continue
        if not paths:
            folder = empty_submission_folder(root, original)
            roots = {folder} if folder is not None else set()
        if len(roots) != 1 or None in roots:
            raise ValueError(f"Cannot identify one task for LeetSync commit {original}")
        folder = roots.pop()
        if any(Path(path).name == ".leetsync.json" for path in paths):
            raise ValueError("Incoming LeetSync commits must not modify generated metadata")
        apply_paths(root, original, paths)
        # A queued submission may modify only one file in a raw directory that
        # was removed by processing its predecessor. Restore its complete input.
        apply_paths(root, original, [folder.as_posix()])
        source = root / folder
        if not source.is_dir() or not organizer.code_files(source):
            raise ValueError(f"Missing solution files in {original}")
        level = organizer.difficulty(source)
        target = root / "solutions" / (level if level != "—" else "Unknown") / source.name
        organizer.check_path(target)
        if source != target:
            organizer.validate_merge(source, target)
            # Explicit deletions in queued raw uploads refer to the normalized
            # directory after the previous upload has already been moved.
            for name in paths:
                if not git(root, "ls-tree", original, "--", name):
                    deleted = target / Path(name).relative_to(folder)
                    organizer.check_path(deleted)
                    if deleted.is_file():
                        deleted.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            organizer.move_tree(source, target)
        organizer.ensure_notebook(target)
        files = snapshot(target)
        previous = records.get(target.name)
        if previous and previous["eligible"] and files == previous["files"] and runtime(previous["info"]["message"]) is not None:
            if elapsed < runtime(previous["info"]["message"]):
                previous["info"]["message"] = message
                replacements[previous["anchor"]] = message
            write_metadata(target, previous["info"])
            print(f"Collapsed {target.name}: best {runtime(previous['info']['message'])} ms")
        else:
            info = {"version_id": original, "message": message,
                    "fingerprint": fingerprint(files),
                    "submitted_at": int(text(root, "show", "-s", "--format=%ct", original))}
            write_metadata(target, info)
            anchor = make_commit(root, message + "\n\n" + VERSION + original, original)
            records[target.name] = {"anchor": anchor, "info": info, "files": files, "eligible": True}
            print(f"Kept new version: {target.name}")
    mapping = rewrite_messages(root, replacements)
    # Old metadata can refer to ancestors whose IDs changed with their parents.
    for task in organizer.discover_tasks():
        if task.parent.parent != root / "solutions" or task.parent.name not in ("Easy", "Medium", "Hard", "Unknown"):
            raise ValueError("Manual commits introduced an unorganized task directory")
        path = task / ".leetsync.json"
        if path.exists():
            info = json.loads(path.read_text())
            for key in ("source_commit", "organization_commit"):
                if info.get(key) in mapping:
                    info[key] = mapping[info[key]]
            write_metadata(task, info)
    organizer.remove_empty_legacy_directories()
    cache = root / "scripts/leetcode_cache.json"
    if not offline:
        organizer.fetch_tags.update_cache(organizer.discover_tasks(), cache)
    entries = organizer.collect_entries()
    organizer.activity.write_heatmap(entries, root / "assets/heatmap.svg")
    organizer.update_readme(entries)
    # Include generated files in the current managed commit. A better runtime
    # must not replace LeetSync duplicates with a growing list of README commits.
    final = text(root, "rev-parse", "HEAD")
    raw = git(root, "cat-file", "commit", final)
    headers, message = raw.split(b"\n\n", 1)
    managed = any(line == CHECKPOINT or line.startswith(VERSION) for line in message.decode().splitlines())
    if managed:
        git(root, "add", "-A")
        tree = text(root, "write-tree")
        lines = [b"tree " + tree.encode() if line.startswith(b"tree ") else line
                 for line in headers.splitlines()]
        if CHECKPOINT not in message.decode().splitlines():
            message = message.rstrip() + b"\n\n" + CHECKPOINT.encode() + b"\n"
        new = git(root, "hash-object", "-t", "commit", "-w", "--stdin",
                  data=b"\n".join(lines) + b"\n\n" + message).decode().strip()
        git(root, "update-ref", "HEAD", new, final)
    else:
        make_commit(root, "Update README\n\n" + CHECKPOINT, allow_empty=True)
    # Updating A's metadata inside B's final commit would make GitHub show B's
    # timing for folder A. Keep each folder's generated write with its own result.
    if __package__:
        from . import migrate_history
    else:
        import migrate_history
    placed, _ = migrate_history.place_folder_results(root)
    if placed:
        migrate_history.mark_placement(root)
    return text(root, "rev-parse", "HEAD")


def synchronize(root, *, offline=False):
    root = Path(root).resolve()
    branch = text(root, "symbolic-ref", "--short", "HEAD")
    if branch not in ("main", "test"):
        raise ValueError("History compaction is restricted to the main or test branch")
    if text(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Commit or stash local changes before compacting history")
    config = json.loads((root / CONFIG).read_text())
    if config != {"schema": 1}:
        raise ValueError("Unsupported history configuration")
    head = text(root, "rev-parse", "HEAD")
    base = checkpoint(root)
    pending = text(root, "rev-list", "--reverse", f"{base}..{head}").splitlines()
    if not pending:
        print("No new submissions to process")
        return head
    if text(root, "rev-list", "--merges", f"{base}..{head}"):
        raise ValueError("Merge commits after the checkpoint require manual processing")
    with tempfile.TemporaryDirectory(prefix="leetsync-") as directory:
        work = Path(directory) / "repo"
        git(root, "clone", "--no-hardlinks", "--no-checkout", str(root), str(work))
        for key in ("user.name", "user.email"):
            git(work, "config", key, text(root, "config", key))
        with at_root(work):
            organizer.table_template(git(work, "show", f"{head}:README.md").decode())
            final = process(work, base, pending, offline)
        if text(root, "rev-parse", "HEAD") != head or text(root, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("Checkout changed during synchronization; no history updated")
        git(root, "fetch", "--no-tags", str(work), final)
        git(root, "update-ref", f"refs/leetsync/backups/{head}", head)
        git(root, "reset", "--keep", final)
    print(f"Synchronized {branch}: {head[:12]} -> {final[:12]}")
    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use cached tags")
    parser.add_argument("--migrate-history", action="store_true", help="Migrate historical submissions once")
    parser.add_argument("--dry-run", action="store_true", help="Preview historical migration without changing the checkout")
    parser.add_argument("--report", type=Path, help="Write a historical migration report as JSON")
    args = parser.parse_args()
    if (args.dry_run or args.report) and not args.migrate_history:
        parser.error("--dry-run and --report require --migrate-history")
    try:
        root = Path(__file__).resolve().parents[1]
        if args.migrate_history:
            if __package__:
                from . import migrate_history
            else:
                import migrate_history
            report = migrate_history.migrate(root, offline=args.offline, dry_run=args.dry_run)
            if args.report:
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if report["already_migrated"]:
                print("Historical migration already completed")
            else:
                print(f"{'Preview' if args.dry_run else 'Migrated'}: {report['commits_before']} -> {report['commits_after']} commits; "
                      f"{report['versions_kept']} solution versions; {len(report['ambiguous_results'])} ambiguous results preserved")
        else:
            synchronize(root, offline=args.offline)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        organizer.report_error("History synchronization failed", error)
        raise SystemExit(1)
