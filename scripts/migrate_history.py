"""One-time, conservative migration of historical LeetSync result commits."""

from collections import defaultdict
import json
from pathlib import Path
import re
import tempfile

if __package__:
    from . import organizer, sync_history as sync
else:
    import organizer
    import sync_history as sync

MIGRATION = "LeetSync-Migration: 1"
PLACEMENT = "LeetSync-Folder-Results: 1"


class History:
    """Read original Git objects; never execute scripts from historical commits."""

    def __init__(self, root):
        self.root = root
        self.blobs = {}
        self.trees = {}
        self.raw_commits = {}
        self.normalized = {}

    def blob(self, sha):
        if sha not in self.blobs:
            self.blobs[sha] = sync.git(self.root, "cat-file", "blob", sha)
        return self.blobs[sha]

    def store(self, content):
        sha = sync.git(self.root, "hash-object", "-w", "--stdin", data=content).decode().strip()
        self.blobs[sha] = content
        return sha

    def commit(self, sha):
        if sha not in self.raw_commits:
            self.raw_commits[sha] = sync.git(self.root, "cat-file", "commit", sha)
        return self.raw_commits[sha]

    def tree(self, sha):
        tree_id = self.commit(sha).splitlines()[0].split()[1].decode()
        if tree_id not in self.trees:
            entries = {}
            for entry in sync.git(self.root, "ls-tree", "-r", "-z", tree_id).split(b"\0"):
                if entry:
                    header, name = entry.split(b"\t", 1)
                    mode, _, blob = header.decode().split()
                    entries[name.decode()] = (mode, blob)
            self.trees[tree_id] = entries
        return self.trees[tree_id]

    def tasks(self, tree):
        grouped = defaultdict(dict)
        for name, entry in tree.items():
            folder = sync.task_root(name)
            if folder is not None:
                grouped[folder][Path(name).relative_to(folder).as_posix()] = entry
        aliases = defaultdict(list)
        for folder, files in grouped.items():
            aliases[folder.name].append((folder, files))
        result = {}
        for name, folders in aliases.items():
            key = tuple(sorted((str(folder), tuple(sorted(files.items()))) for folder, files in folders))
            if key in self.normalized:
                result[name] = self.normalized[key]
                continue
            merged = {}
            raw = [folder for folder, _ in folders
                   if folder.parent not in [Path("solutions") / level for level in ("Easy", "Medium", "Hard", "Unknown")]]
            if len(raw) > 1:
                raise ValueError(f"Ambiguous historical input folders for {name}: {raw}")
            # As in the live organizer, an incoming upload overlays the existing
            # canonical folder, while existing notebooks remain in place.
            for folder, files in sorted(folders, key=lambda item: (item[0] in raw, str(item[0]))):
                for filename, entry in files.items():
                    if filename == ".leetsync.json":
                        continue
                    if filename in merged and (filename.endswith(".ipynb") or filename == "notes.md") and merged[filename] != entry:
                        raise ValueError(f"Conflicting historical personal notes for {name}")
                    if entry[0] not in ("100644", "100755"):
                        raise ValueError(f"Unsupported historical file mode in {name}/{filename}")
                    merged[filename] = entry
            statement = self.blob(merged["README.md"][1]).decode() if "README.md" in merged else ""
            difficulty = re.search(r"Difficulty\s*[:\-]\s*(Easy|Medium|Hard)\b", statement, re.I)
            level = difficulty[1].capitalize() if difficulty else "Unknown"
            has_code = any(Path(filename).suffix.lower() in organizer.CODE_EXTENSIONS for filename in merged)
            if has_code and "notes.ipynb" not in merged:
                legacy = merged.pop("notes.md", None)
                content = self.blob(legacy[1]).decode() if legacy else None
                notebook = organizer.notebook_from_text(name, content)
                blob = self.store((json.dumps(notebook, ensure_ascii=False, indent=2) + "\n").encode())
                merged["notes.ipynb"] = ("100644", blob)
            files = [(f"solutions/{level}/{name}/{filename}", mode == "100755", self.blob(blob))
                     for filename, (mode, blob) in sorted(merged.items())]
            value = {"fingerprint": sync.fingerprint(files), "has_code": has_code}
            self.normalized[key] = value
            result[name] = value
        return result


def analyze(history, commits):
    records, groups, aliases, replacements, drops = {}, [], {}, {}, set()
    report = {"collapsed_results": 0, "removed_organizer_commits": 0,
              "removed_readme_helpers": 0, "ambiguous_results": []}
    previous_tree, previous_tasks = {}, {}
    for index, sha in enumerate(commits):
        tree = history.tree(sha)
        tasks = history.tasks(tree)
        message = history.commit(sha).split(b"\n\n", 1)[1].decode().strip()
        paths = {path for path in previous_tree.keys() | tree.keys()
                 if previous_tree.get(path) != tree.get(path)}
        roots = {sync.task_root(path) for path in paths}
        names = {folder.name for folder in roots if folder is not None}
        elapsed = sync.runtime(message)
        if message.startswith("Added README.md file for "):
            helper = sync.readme_identity(history.root, sha)
            if helper and not paths and index:
                drops.add(sha)
                report["removed_readme_helpers"] += 1
        managed = any(line.startswith(sync.VERSION) for line in message.splitlines())
        outside = [path for path in paths if sync.task_root(path) is None]
        allowed_generated = all(path == "README.md" or path.startswith("assets/")
                                or path == "scripts/leetcode_cache.json" for path in outside)
        name = next(iter(names)) if len(names) == 1 and (not outside or managed and allowed_generated) else None
        if elapsed is not None and not paths:
            folder = sync.empty_submission_folder(history.root, sha)
            name = folder.name if folder is not None else None
        organized = False
        if name and elapsed is not None and not managed:
            for path in paths:
                if path.endswith("/.leetsync.json") and path in tree:
                    metadata = json.loads(history.blob(tree[path][1]))
                    if not isinstance(metadata, dict):
                        raise ValueError(f"Invalid historical metadata: {path} in {sha}")
                    source = metadata.get("source_commit")
                    if source in aliases:
                        organized = True
        if organized:
            # These messages copy a submission's old timing; they are not runs.
            if tasks == previous_tasks and not outside and index:
                drops.add(sha)
                report["removed_organizer_commits"] += 1
            else:
                replacements[sha] = f"Organize {name}"
        elif elapsed is not None and name and tasks.get(name, {}).get("has_code"):
            current = tasks[name]["fingerprint"]
            prior = records.get(name)
            if prior and prior["eligible"] and prior["fingerprint"] == current:
                # Removing a result must not remove a real normalized transition.
                if tasks != previous_tasks:
                    raise ValueError(f"Unexpected material change in duplicate {sha}")
                if elapsed < sync.runtime(prior["message"]):
                    prior["message"] = message.split("\n\n", 1)[0]
                aliases[sha] = prior
                drops.add(sha)
                report["collapsed_results"] += 1
            else:
                version = next((line[len(sync.VERSION):] for line in message.splitlines()
                                if line.startswith(sync.VERSION)), sha)
                prior = {"anchor": sha, "version_id": version, "name": name,
                         "message": message.split("\n\n", 1)[0],
                         "submitted_at": int(sync.text(history.root, "show", "-s", "--format=%ct", sha)),
                         "fingerprint": current, "eligible": True}
                records[name] = prior
                groups.append(prior)
                aliases[sha] = prior
        else:
            if elapsed is not None:
                report["ambiguous_results"].append({"commit": sha, "reason": "No unambiguous task identity"})
            # A manual edit remains a boundary even if a later edit restores A.
            for changed in previous_tasks.keys() | tasks.keys():
                if previous_tasks.get(changed) != tasks.get(changed) and changed in records:
                    records[changed]["eligible"] = False
        if organized:
            for changed in previous_tasks.keys() | tasks.keys():
                if previous_tasks.get(changed) != tasks.get(changed) and changed in records:
                    records[changed]["eligible"] = False
        previous_tree, previous_tasks = tree, tasks
    for group in groups:
        replacements[group["anchor"]] = group["message"] + "\n\n" + sync.VERSION + group["version_id"]
    return records, groups, aliases, replacements, drops, report


def rewrite(history, commits, aliases, replacements, drops, index_path):
    mapping = {}
    env = {"GIT_INDEX_FILE": str(index_path)}
    for sha in commits:
        raw = history.commit(sha)
        headers, message = raw.split(b"\n\n", 1)
        lines = headers.splitlines()
        parents = [line[7:].decode() for line in lines if line.startswith(b"parent ")]
        if sha in drops:
            if not parents:
                raise ValueError("Cannot remove the root commit")
            mapping[sha] = mapping[parents[0]]
            continue
        # Rewrite metadata references in every retained snapshot, not just HEAD.
        edits = []
        for path, (mode, blob) in history.tree(sha).items():
            if not path.endswith("/.leetsync.json") or sync.task_root(path) is None:
                continue
            original = history.blob(blob)
            info = json.loads(original)
            if not isinstance(info, dict):
                raise ValueError(f"Invalid historical metadata: {path} in {sha}")
            group = aliases.get(info.get("source_commit"))
            for key in ("source_commit", "organization_commit"):
                old = info.get(key)
                if old in aliases and key == "source_commit":
                    old = aliases[old]["anchor"]
                if old in mapping:
                    info[key] = mapping[old]
            if group:
                info["message"] = group["message"]
                info["submitted_at"] = group["submitted_at"]
            content = (json.dumps(info, ensure_ascii=False, indent=2) + "\n").encode()
            if content != original:
                edits.append(f"{mode} {history.store(content)}\t{path}\0".encode())
        if edits:
            sync.git(history.root, "read-tree", sha, env=env)
            sync.git(history.root, "update-index", "-z", "--index-info", data=b"".join(edits), env=env)
            tree = sync.git(history.root, "write-tree", env=env).strip()
            lines[0] = b"tree " + tree
        lines = [b"parent " + mapping[line[7:].decode()].encode() if line.startswith(b"parent ") else line
                 for line in lines]
        if sha in replacements:
            message = (replacements[sha].rstrip() + "\n").encode()
        updated = b"\n".join(lines) + b"\n\n" + message
        if updated != raw and any(line.startswith((b"gpgsig ", b"mergetag ")) for line in lines):
            raise ValueError(f"Cannot rewrite signed historical commit {sha}")
        mapping[sha] = sync.git(
            history.root, "hash-object", "-t", "commit", "-w", "--stdin", data=updated,
        ).decode().strip()
    return mapping


def place_unmeasured_metadata(root):
    """Keep generated metadata with the last real edit of an unmeasured task.

    A later notebook/code edit must remain the folder's visible commit. Rewriting
    only metadata in that commit and its descendants preserves every user tree
    and does not invent a benchmark for the edited files.
    """
    head = sync.text(root, "rev-parse", "HEAD")
    history = History(root)
    commits = sync.text(root, "rev-list", "--reverse", head).splitlines()
    positions = {sha: index for index, sha in enumerate(commits)}
    targets = {}
    for task in organizer.discover_tasks():
        path = task / ".leetsync.json"
        if not path.exists():
            continue
        info = json.loads(path.read_text())
        if info.get("version_id") and info.get("fingerprint") == sync.fingerprint(sync.snapshot(task)):
            continue
        relative = task.relative_to(root).as_posix()
        folder_commits = sync.text(root, "log", "--format=%H", "--", relative).splitlines()
        material = next((sha for sha in folder_commits if any(
            sync.task_root(name) == task.relative_to(root) and name != f"{relative}/.leetsync.json"
            for name in sync.changed_paths(root, sha))), None)
        if material is None:
            raise ValueError(f"Cannot find the last real edit for {task.name}")
        if folder_commits[0] != material:
            targets[f"{relative}/.leetsync.json"] = (positions[material], info)
    if not targets:
        return {}
    mapping = {}
    env = {"GIT_INDEX_FILE": str(root.parent / "unmeasured-metadata.index")}
    for index, sha in enumerate(commits):
        raw = history.commit(sha)
        headers, message = raw.split(b"\n\n", 1)
        lines = headers.splitlines()
        tree = history.tree(sha)
        edits = []
        names = {name for name in tree if name.endswith("/.leetsync.json") and sync.task_root(name)}
        names.update(name for name, (start, _) in targets.items() if index >= start)
        for name in sorted(names):
            original = history.blob(tree[name][1]) if name in tree else None
            if name in targets and index >= targets[name][0]:
                info = dict(targets[name][1])
                # This legacy bookkeeping field can point beyond the real edit.
                info.pop("organization_commit", None)
            else:
                info = json.loads(original)
            for key in ("source_commit", "organization_commit"):
                if info.get(key) in mapping:
                    info[key] = mapping[info[key]]
            content = (json.dumps(info, ensure_ascii=False, indent=2) + "\n").encode()
            if content != original:
                mode = tree[name][0] if name in tree else history.tree(head)[name][0]
                edits.append(f"{mode} {history.store(content)}\t{name}\0".encode())
        if edits:
            sync.git(root, "read-tree", sha, env=env)
            sync.git(root, "update-index", "-z", "--index-info", data=b"".join(edits), env=env)
            lines[0] = b"tree " + sync.git(root, "write-tree", env=env).strip()
        lines = [b"parent " + mapping[line[7:].decode()].encode() if line.startswith(b"parent ") else line
                 for line in lines]
        updated = b"\n".join(lines) + b"\n\n" + message
        if updated != raw and any(line.startswith((b"gpgsig ", b"mergetag ")) for line in lines):
            raise ValueError(f"Cannot rewrite signed historical commit {sha}")
        mapping[sha] = sync.git(root, "hash-object", "-t", "commit", "-w", "--stdin", data=updated).decode().strip()
    final = mapping[head]
    if any(name and not name.endswith(b"/.leetsync.json")
           for name in sync.git(root, "diff", "--name-only", "-z", head, final).split(b"\0")):
        raise ValueError("Unmeasured metadata placement changed a user file")
    sync.git(root, "checkout", "--detach", final)
    return mapping


def place_folder_results(root):
    if sync.text(root, "rev-list", "--merges", "HEAD"):
        raise ValueError("Folder result placement requires linear history")
    earlier = place_unmeasured_metadata(root)
    later, skipped = _place_measured_folder_results(root)
    return {**later, **{old: later.get(new, new) for old, new in earlier.items()}}, skipped


def _place_measured_folder_results(root):
    """Relocate current result commits to own their final per-folder metadata.

    Retained commits keep their user-file trees. A result can move only when its
    material task snapshot is also present in the next retained commit. This
    avoids losing a transient implementation while keeping one result per version.
    """
    head = sync.text(root, "rev-parse", "HEAD")
    history = History(root)
    commits = sync.text(root, "rev-list", "--reverse", head).splitlines()
    if sync.text(root, "rev-list", "--merges", head):
        raise ValueError("Folder result placement requires linear history")
    positions = {sha: index for index, sha in enumerate(commits)}
    moved, skipped = {}, []
    for task in organizer.discover_tasks():
        path = task / ".leetsync.json"
        if not path.exists():
            continue
        info = json.loads(path.read_text())
        version = info.get("version_id")
        if not version:
            continue
        relative = task.relative_to(root).as_posix()
        latest = sync.text(root, "log", "-1", "--format=%H", "--", relative)
        anchor = organizer.submission(task)["source_commit"]
        if latest == anchor:
            continue
        if info.get("fingerprint") != sync.fingerprint(sync.snapshot(task)):
            skipped.append({"task": task.name, "reason": "Current files differ from the measured version"})
            continue
        # Never relabel or move a subsequent manual code/notebook edit. The
        # reported bug is a generated metadata write masking a measured result.
        last_paths = sync.changed_paths(root, latest)
        relevant = [name for name in last_paths if sync.task_root(name) == task.relative_to(root)]
        if any(name != f"{relative}/.leetsync.json" for name in relevant):
            skipped.append({"task": task.name, "reason": "Latest folder commit contains real file changes"})
            continue
        if not positions[anchor]:
            raise ValueError("Cannot relocate a root result commit")
        if anchor in moved:
            raise ValueError("A result commit cannot own multiple task versions")
        moved[anchor] = {"task": task.name, "path": f"{relative}/.leetsync.json", "info": info}
    if not moved:
        return {}, skipped
    # Prove that deleting each old result node cannot delete a material state.
    for anchor, record in moved.items():
        following = next((sha for sha in commits[positions[anchor] + 1:] if sha not in moved), None)
        before = history.tasks(history.tree(anchor))
        if following is None or before.get(record["task"]) != history.tasks(history.tree(following)).get(record["task"]):
            raise ValueError(f"Cannot relocate unique historical snapshot for {record['task']}")
        parent = commits[positions[anchor] - 1]
        previous = history.tasks(history.tree(parent))
        changed_tasks = {name for name in previous.keys() | before.keys() if previous.get(name) != before.get(name)}
        if changed_tasks - {record["task"]}:
            raise ValueError(f"Result also changes another task: {anchor}")
        for name in sync.changed_paths(root, anchor):
            if sync.task_root(name) is None and not (name == "README.md" or name.startswith("assets/")
                                                    or name == "scripts/leetcode_cache.json"):
                raise ValueError(f"Result also changes an unrelated file: {anchor}")
    versions = {record["info"]["version_id"] for record in moved.values()}
    mapping = {}
    env = {"GIT_INDEX_FILE": str(root.parent / "folder-results.index")}
    for sha in commits:
        raw = history.commit(sha)
        headers, message = raw.split(b"\n\n", 1)
        lines = headers.splitlines()
        parent = next((line[7:].decode() for line in lines if line.startswith(b"parent ")), None)
        if sha in moved:
            mapping[sha] = mapping[parent]
            continue
        edits = []
        for name, (mode, blob) in history.tree(sha).items():
            if not name.endswith("/.leetsync.json") or sync.task_root(name) is None:
                continue
            original = history.blob(blob)
            info = json.loads(original)
            # Metadata for a relocated version is introduced with that version's
            # new node, never left with a dangling SHA or a later generic writer.
            if info.get("version_id") in versions or info.get("source_commit") in moved:
                edits.append(f"0 {'0' * len(blob)}\t{name}\0".encode())
                continue
            for key in ("source_commit", "organization_commit"):
                if info.get(key) in mapping:
                    info[key] = mapping[info[key]]
            content = (json.dumps(info, ensure_ascii=False, indent=2) + "\n").encode()
            if content != original:
                edits.append(f"{mode} {history.store(content)}\t{name}\0".encode())
        if edits:
            sync.git(root, "read-tree", sha, env=env)
            sync.git(root, "update-index", "-z", "--index-info", data=b"".join(edits), env=env)
            lines[0] = b"tree " + sync.git(root, "write-tree", env=env).strip()
        lines = [b"parent " + mapping[line[7:].decode()].encode() if line.startswith(b"parent ") else line
                 for line in lines]
        updated = b"\n".join(lines) + b"\n\n" + message
        if updated != raw and any(line.startswith((b"gpgsig ", b"mergetag ")) for line in lines):
            raise ValueError(f"Cannot rewrite signed historical commit {sha}")
        mapping[sha] = sync.git(root, "hash-object", "-t", "commit", "-w", "--stdin", data=updated).decode().strip()
    tip = mapping[head]
    sync.git(root, "read-tree", tip, env=env)
    for anchor in sorted(moved, key=positions.get):
        record = moved[anchor]
        info = dict(record["info"])
        # Stable version IDs replace obsolete references to relocated nodes.
        info.pop("source_commit", None)
        info.pop("organization_commit", None)
        blob = history.store((json.dumps(info, ensure_ascii=False, indent=2) + "\n").encode())
        mode = history.tree(head)[record["path"]][0]
        sync.git(root, "update-index", "--add", "--cacheinfo", f"{mode},{blob},{record['path']}", env=env)
        tree = sync.git(root, "write-tree", env=env).strip()
        headers = history.commit(anchor).split(b"\n\n", 1)[0].splitlines()
        if any(line.startswith((b"gpgsig ", b"mergetag ")) for line in headers):
            raise ValueError(f"Cannot relocate signed result {anchor}")
        headers = [b"tree " + tree if line.startswith(b"tree ") else
                   b"parent " + tip.encode() if line.startswith(b"parent ") else line for line in headers]
        message = info["message"].rstrip() + "\n\n" + sync.VERSION + info["version_id"] + "\n"
        tip = sync.git(root, "hash-object", "-t", "commit", "-w", "--stdin",
                       data=b"\n".join(headers) + b"\n\n" + message.encode()).decode().strip()
        mapping[anchor] = tip
    # Moving nodes is count-neutral; only metadata may differ at the final tree.
    for name in sync.git(root, "diff", "--name-only", "-z", head, tip).split(b"\0"):
        if name and not name.endswith(b"/.leetsync.json"):
            raise ValueError(f"Folder result placement changed a user file: {name.decode()}")
    sync.git(root, "checkout", "--detach", tip)
    return mapping, skipped


def mark_placement(root):
    """Put the checkpoint on the last result without touching any file trees."""
    head = sync.text(root, "rev-parse", "HEAD")
    raw = sync.git(root, "cat-file", "commit", head)
    headers, message = raw.split(b"\n\n", 1)
    for marker in (PLACEMENT, sync.CHECKPOINT):
        if marker not in message.decode().splitlines():
            message = message.rstrip() + b"\n\n" + marker.encode() + b"\n"
    if any(line.startswith((b"gpgsig ", b"mergetag ")) for line in headers.splitlines()):
        raise ValueError("Cannot mark a signed commit as the placement checkpoint")
    new = sync.git(root, "hash-object", "-t", "commit", "-w", "--stdin",
                   data=headers + b"\n\n" + message).decode().strip()
    sync.git(root, "update-ref", "HEAD", new, head)
    return head, new


def repair_placement(root, head):
    sync.git(root, "checkout", "--detach", head)
    before = int(sync.text(root, "rev-list", "--count", head))
    _, skipped = place_folder_results(root)
    _, final = mark_placement(root)
    return {"original_head": head, "new_head": final, "commits_before": before,
            "commits_after": int(sync.text(root, "rev-list", "--count", final)),
            "versions_kept": len(sync.text(root, "log", "--format=%H", "--fixed-strings",
                                          f"--grep={sync.VERSION}").splitlines()),
            "already_migrated": False, "repaired_folder_results": True,
            "folder_results_skipped": skipped, "ambiguous_results": []}


def build(root, head, offline):
    commits = sync.text(root, "rev-list", "--reverse", head).splitlines()
    history = History(root)
    records, groups, aliases, replacements, drops, report = analyze(history, commits)
    mapping = rewrite(history, commits, aliases, replacements, drops, root.parent / "migration.index")
    sync.git(root, "checkout", "--detach", mapping[head])
    final_tasks = history.tasks(history.tree(head))
    for task in organizer.discover_tasks():
        if task.parent.parent != root / "solutions" or task.parent.name not in ("Easy", "Medium", "Hard", "Unknown"):
            raise ValueError("Organize the current checkout before migrating history")
        group = records.get(task.name)
        if group:
            info = {key: group[key] for key in ("version_id", "message", "submitted_at", "fingerprint")}
            if not group["eligible"] or group["fingerprint"] != final_tasks[task.name]["fingerprint"]:
                info["comparison_valid"] = False
            sync.write_metadata(task, info)
        elif (task / ".leetsync.json").exists():
            info = json.loads((task / ".leetsync.json").read_text())
            info["comparison_valid"] = False
            sync.write_metadata(task, info)
    if not offline:
        organizer.fetch_tags.update_cache(organizer.discover_tasks(), root / "scripts/leetcode_cache.json")
    entries = organizer.collect_entries()
    organizer.activity.write_heatmap(entries, root / "assets/heatmap.svg")
    organizer.update_readme(entries)
    sync.make_commit(root, "Migrate LeetSync history\n\n" + MIGRATION + "\n" + sync.CHECKPOINT, allow_empty=True)
    placed, skipped = place_folder_results(root)
    previous_tip, final = mark_placement(root)
    mapping = {old: placed.get(new, new) for old, new in mapping.items()}
    mapping = {old: final if new == previous_tip else new for old, new in mapping.items()}
    changed = sync.git(root, "diff", "--name-only", "-z", head, final).split(b"\0")
    for item in changed:
        path = item.decode()
        if path and not (path == "README.md" or path.startswith("assets/")
                         or path == "scripts/leetcode_cache.json" or path.endswith("/.leetsync.json")):
            raise ValueError(f"Migration unexpectedly changed a user file: {path}")
    report.update({"original_head": head, "new_head": final, "commits_before": len(commits),
                   "commits_after": int(sync.text(root, "rev-list", "--count", final)),
                   "versions_kept": len(groups), "already_migrated": False,
                   "folder_results_skipped": skipped,
                   "current_comparison_boundaries": sorted(name for name, group in records.items()
                       if name in final_tasks and (not group["eligible"]
                           or group["fingerprint"] != final_tasks[name]["fingerprint"])),
                   "versions": [{"task": group["name"], "message": group["message"],
                                 "commit": mapping[group["anchor"]]} for group in groups]})
    return report


def migrate(root, *, offline=False, dry_run=False):
    root = Path(root).resolve()
    if sync.text(root, "symbolic-ref", "--short", "HEAD") not in ("main", "test"):
        raise ValueError("History migration is restricted to the main or test branch")
    if not dry_run and sync.text(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Commit or stash local changes before migrating history")
    if not dry_run and (not sync.text(root, "ls-files", "--", sync.CONFIG)
                        or json.loads((root / sync.CONFIG).read_text()) != {"schema": 1}):
        raise ValueError(f"Commit the supported {sync.CONFIG} configuration before migration")
    if sync.text(root, "rev-parse", "--is-shallow-repository") == "true":
        raise ValueError("Fetch the full history before migrating")
    head = sync.text(root, "rev-parse", "HEAD")
    markers = sync.text(root, "log", "--format=%H", "--fixed-strings", f"--grep={MIGRATION}").splitlines()
    migrated = any(MIGRATION in sync.text(root, "show", "-s", "--format=%B", sha).splitlines() for sha in markers)
    placements = sync.text(root, "log", "--format=%H", "--fixed-strings", f"--grep={PLACEMENT}").splitlines()
    placed = any(PLACEMENT in sync.text(root, "show", "-s", "--format=%B", sha).splitlines() for sha in placements)
    if migrated and placed:
        return {"original_head": head, "new_head": head, "already_migrated": True}
    if sync.text(root, "rev-list", "--merges", head):
        raise ValueError("Historical merges require manual migration")
    with tempfile.TemporaryDirectory(prefix="leetsync-migration-") as directory:
        work = Path(directory) / "repo"
        sync.git(root, "clone", "--no-hardlinks", "--no-checkout", str(root), str(work))
        for key in ("user.name", "user.email"):
            sync.git(work, "config", key, sync.text(root, "config", key))
        with sync.at_root(work):
            report = repair_placement(work, head) if migrated else build(work, head, offline)
        if not dry_run:
            if sync.text(root, "rev-parse", "HEAD") != head or sync.text(root, "status", "--porcelain", "--untracked-files=all"):
                raise ValueError("Checkout changed during migration; no history updated")
            sync.git(root, "fetch", "--no-tags", str(work), report["new_head"])
            sync.git(root, "update-ref", f"refs/leetsync/backups/{head}", head)
            sync.git(root, "reset", "--keep", report["new_head"])
    report["dry_run"] = dry_run
    return report
