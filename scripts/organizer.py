# scripts/organizer.py
"""Organize LeetSync solutions and refresh the generated README table."""

import html
import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
SOLUTIONS = ROOT / "solutions"
README = ROOT / "README.md"
KNOWN_TASKS_CACHE = {
    "1-two-sum": "Algorithm/Arrays_and_Hashing",
    "49-group-anagrams": "Algorithm/Arrays_and_Hashing",
    "125-valid-palindrome": "Algorithm/Two_Pointers",
    "15-3sum": "Algorithm/Two_Pointers",
    "20-valid-parentheses": "Algorithm/Stack",
    "704-binary-search": "Algorithm/Binary_Search",
    "175-combine-two-tables": "Database/Joins",
    "183-customers-who-never-order": "Database/Joins",
    "2887-fill-missing-data": "Pandas/Data_Manipulation",
    "2888-reshape-data-concatenate": "Pandas/Data_Manipulation",
}
TAG_TO_FOLDER_MAP = {
    "Database": "Database/Joins",
    "Pandas": "Pandas/Data_Manipulation",
    "Hash Table": "Algorithm/Arrays_and_Hashing",
    "Two Pointers": "Algorithm/Two_Pointers",
    "Stack": "Algorithm/Stack",
    "Binary Search": "Algorithm/Binary_Search",
    "Sliding Window": "Algorithm/Sliding_Window",
    "Linked List": "Algorithm/Linked_List",
    "Dynamic Programming": "Algorithm/Dynamic_Programming",
    "Tree": "Algorithm/Trees",
    "Graph": "Algorithm/Graphs",
    "Heap (Priority Queue)": "Algorithm/Heap",
    "Backtracking": "Algorithm/Backtracking",
    "Array": "Algorithm/Arrays_and_Hashing",
}
LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
DEFAULT_CATEGORY = "Algorithm/Uncategorized"
TASK_PATTERN = re.compile(r"^(\d+)-(.+)$")
START = "<!-- START_TABLE -->"
END = "<!-- END_TABLE -->"
TABLE_PATTERN = re.escape(START) + r".*?" + re.escape(END)
CODE_EXTENSIONS = {
    ".py", ".sql", ".java", ".js", ".ts", ".cpp", ".cc", ".c",
    ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".dart", ".r", ".sh",
}


def get_problem_tags(title_slug):
    """Return LeetCode topic tags in API order; return [] on API failure."""
    query = """
    query ProblemTags($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            topicTags { name }
        }
    }
    """
    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json={
                "query": query,
                "operationName": "ProblemTags",
                "variables": {"titleSlug": title_slug},
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "LeetCode-Notebook-Organizer/1.0",
                "Referer": f"https://leetcode.com/problems/{quote(title_slug, safe='')}/",
            },
            timeout=(3.05, 10),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errors"):
            raise ValueError("Invalid response or GraphQL errors.")
        question = payload["data"]["question"]
        if question is None:
            return []
        tags = question["topicTags"]
        if not isinstance(tags, list):
            raise ValueError("topicTags is not a list.")
        return [
            tag["name"] for tag in tags
            if isinstance(tag, dict) and isinstance(tag.get("name"), str)
            and tag["name"].strip()
        ]
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        print(
            f"Could not fetch tags for {title_slug}: {error} "
            f"Using {DEFAULT_CATEGORY}.", file=sys.stderr,
        )
        return []


@lru_cache(maxsize=None)
def category_for_task(folder_name):
    """Resolve each task once per process, including uncategorized results."""
    match = TASK_PATTERN.fullmatch(folder_name)
    if not match:
        return DEFAULT_CATEGORY
    title_slug = match.group(2)
    key = f"{int(match.group(1))}-{title_slug}"
    if key in KNOWN_TASKS_CACHE:
        return KNOWN_TASKS_CACHE[key]
    for tag in get_problem_tags(title_slug):
        if tag in TAG_TO_FOLDER_MAP:
            return TAG_TO_FOLDER_MAP[tag]
    return DEFAULT_CATEGORY


def git(*args, check=True):
    return subprocess.run(
        ["git", "--literal-pathspecs", *args], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", check=check,
    )


def commit_paths(message, *paths):
    """Commit only these paths, leaving unrelated staged changes alone."""
    relative = [path.relative_to(ROOT).as_posix() for path in paths]
    git("add", "-A", "--", *relative)
    diff = git("diff", "--cached", "--quiet", "--", *relative, check=False)
    if diff.returncode == 0:
        print("No changes to commit.")
        return False
    if diff.returncode != 1:
        diff.check_returncode()
    # --only also excludes changes staged by an earlier failed task.
    result = git(
        "commit", "--only", "--cleanup=verbatim", "-m", message,
        "--", *relative,
    )
    print(result.stdout.strip())
    return True


def report_error(context, error):
    if isinstance(error, subprocess.CalledProcessError):
        detail = (error.stderr or error.stdout or str(error)).strip()
    else:
        detail = str(error)
    print(f"{context}: {detail}", file=sys.stderr)


def find_leetsync_commit(source):
    """Skip later restore/organizer commits when locating submission metadata."""
    revision = git(
        "log", "-1", "--format=%H", "--fixed-strings", "--grep=LeetSync",
        "--diff-filter=AM", "--", source.relative_to(ROOT).as_posix(),
    ).stdout.strip()
    if not revision:
        print(f"No LeetSync commit found for {source.name}; keeping the regular commit.")
        return None
    message = git("show", "-s", "--format=%B", revision).stdout.rstrip("\n")
    return revision, message


def commit_leetsync_origin(target, origin):
    """A real file change makes the extra commit visible in folder history."""
    revision, message = origin
    metadata = target / ".leetsync.json"
    check_path(metadata)
    data = {
        "source_commit": revision,
        "message": message,
        # Also changes when an identical solution is moved again.
        "organization_commit": git("rev-parse", "HEAD").stdout.strip(),
    }
    metadata.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    commit_paths(message, metadata)


def walk_error(error):
    raise error


def directories(path):
    return sorted(
        (child for child in path.iterdir()
         if child.is_dir() and not child.is_symlink()
         and not child.name.startswith(".")),
        key=lambda child: child.name.casefold(),
    )


def check_path(path):
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Symbolic links are not allowed: {current}")


def discover_tasks():
    tasks = []
    for base, dirs, _ in os.walk(SOLUTIONS, onerror=walk_error):
        remaining = []
        for name in sorted(dirs):
            path = Path(base) / name
            check_path(path)
            if TASK_PATTERN.fullmatch(name):
                tasks.append(path)
            else:
                remaining.append(name)
        dirs[:] = remaining
    return tasks


def validate_move(source, target):
    """Detect conflicts before moving any part of this task."""
    check_path(source)
    check_path(target)
    if source.is_dir():
        if target.exists() and not target.is_dir():
            raise ValueError(f"Directory/file conflict: {target}")
        for child in source.iterdir():
            validate_move(child, target / child.name)
    else:
        if not source.is_file():
            raise ValueError(f"Unsupported file: {source}")
        if target.exists() and not target.is_file():
            raise ValueError(f"File/directory conflict: {target}")
        if source.name == "notes.md" and target.exists():
            raise ValueError(
                f"Both locations contain notes.md: {source}, {target}. "
                "Merge the notes manually."
            )


def move_tree(source, target):
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    elif source.is_dir():
        for child in sorted(source.iterdir()):
            move_tree(child, target / child.name)
        source.rmdir()
    else:
        # Replace code from a previous submission; Git keeps its history.
        shutil.move(str(source), str(target))


def ensure_notes(task):
    notes = task / "notes.md"
    check_path(notes)
    if notes.exists():
        if not notes.is_file():
            raise ValueError(f"notes.md is not a file: {notes}")
        return
    name = task.name
    template = (
        f"# {name}\n"
        "- **Link:** \n"
        "- **Time Complexity:** O()\n"
        "- **Space Complexity:** O()\n"
        "- **Intuition:** \n\n"
        "## Anki Flashcard\n"
        f"**Front:** How can you solve {name} optimally?\n"
        "**Back:** \n"
    )
    with notes.open("x", encoding="utf-8") as handle:
        handle.write(template)


def remove_empty_directories():
    # Never recursively delete unrecognized files.
    for base, _, _ in os.walk(SOLUTIONS, topdown=False, onerror=walk_error):
        path = Path(base)
        if not path.is_symlink() and not any(path.iterdir()):
            path.rmdir()
    if SOLUTIONS.exists():
        raise ValueError(
            "Unrecognized files or symbolic links remain in solutions/. "
            "They have been preserved; check their structure."
        )


def markdown_label(value):
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", value)


def link(path, label):
    relative = path.relative_to(ROOT).as_posix()
    return f"[{markdown_label(label)}](./{quote(relative, safe='/')})"


def task_sort_key(task):
    return int(TASK_PATTERN.fullmatch(task.name).group(1)), task.name


def code_links(task):
    files = []
    for base, dirs, names in os.walk(task, onerror=walk_error):
        dirs[:] = sorted(
            name for name in dirs
            if not name.startswith(".")
            and not (Path(base) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(base) / name
            if (not path.is_symlink() and path.is_file()
                    and path.suffix.lower() in CODE_EXTENSIONS):
                files.append(path)
    return "<br>".join(
        link(path, path.relative_to(task).as_posix()) for path in sorted(files)
    ) or "—"


def submission_result(task):
    """Prefer recorded LeetSync metadata, falling back to path history."""
    message = ""
    metadata = task / ".leetsync.json"
    if metadata.is_file() and not metadata.is_symlink():
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("message"), str):
                message = data["message"]
        except (OSError, UnicodeError, ValueError) as error:
            report_error(f"Could not read submission metadata for {task.name}", error)
    if not message.strip():
        try:
            message = git(
                "log", "-1", "--format=%B", "--fixed-strings",
                "--grep=LeetSync", "--diff-filter=AM", "--",
                task.relative_to(ROOT).as_posix(), f"solutions/{task.name}",
            ).stdout
        except (OSError, UnicodeError, subprocess.SubprocessError) as error:
            report_error(f"Could not read submission history for {task.name}", error)
    message = re.sub(r" - LeetSync\s*$", "", message.strip())
    return "<br>".join(markdown_label(line) for line in message.splitlines()) or "—"


def generate_table():
    groups = {}
    for category in directories(ROOT):
        if category.name in {"solutions", "scripts"}:
            continue
        for pattern in directories(category):
            for task in directories(pattern):
                if TASK_PATTERN.fullmatch(task.name):
                    groups.setdefault((category.name, pattern.name), {})[task.name] = task

    # Pending submissions remain browsable before the organizer runs.
    if SOLUTIONS.is_dir():
        for task in discover_tasks():
            category, pattern = category_for_task(task.name).split("/")
            groups.setdefault((category, pattern), {})[task.name] = task

    sections = []
    for category in sorted({category for category, _ in groups}, key=str.casefold):
        patterns = []
        total = 0
        for (main_category, pattern), entries in sorted(groups.items()):
            if main_category != category:
                continue
            tasks = sorted(entries.values(), key=task_sort_key)
            total += len(tasks)
            heading = html.escape(pattern.replace("_", " "))
            label = "problem" if len(tasks) == 1 else "problems"
            rows = [
                f"<details><summary><b>{heading}</b> · {len(tasks)} {label}</summary>", "",
                "| Problem | Code | Notes | Time |", "| --- | --- | --- | --- |",
            ]
            for task in tasks:
                notes = task / "notes.md"
                notes_link = link(notes, "Notes") if notes.is_file() else "—"
                rows.append(
                    f"| {markdown_label(task.name)} | {code_links(task)} "
                    f"| {notes_link} | {submission_result(task)} |"
                )
            rows.extend(["", "</details>"])
            patterns.append("\n".join(rows))
        if patterns:
            label = "problem" if total == 1 else "problems"
            sections.append(
                f"<details>\n<summary><strong>{html.escape(category)}</strong>"
                f" · {total} {label}</summary>\n\n"
                + "\n\n".join(patterns)
                + "\n\n</details>"
            )
    return "\n\n".join(sections) or "_No solved problems yet._"


def main():
    try:
        check_path(SOLUTIONS)
        if not SOLUTIONS.exists():
            print("No solutions/ directory found — nothing to organize.")
            return 0
        if not SOLUTIONS.is_dir():
            raise ValueError("solutions exists but is not a directory.")
        check_path(README)
        original = README.read_text(encoding="utf-8")
        if (original.count(START) != 1 or original.count(END) != 1
                or original.index(START) >= original.index(END)):
            raise ValueError(
                "README.md must contain exactly one correctly ordered "
                "pair of START_TABLE / END_TABLE markers."
            )
        tasks = discover_tasks()
        errors = completed = 0
        for source in tasks:
            try:
                message = git(
                    "log", "-1", "--pretty=%B", "--",
                    source.relative_to(ROOT).as_posix(),
                ).stdout.rstrip("\n")
                if not message.strip():
                    raise ValueError(
                        "No commit message found in the problem's history; "
                        "commit the solution to Git first."
                    )
                origin = find_leetsync_commit(source)
                target = ROOT / category_for_task(source.name) / source.name
                validate_move(source, target)
                move_tree(source, target)
                ensure_notes(target)
                commit_paths(message, source, target)
                if origin is not None:
                    commit_leetsync_origin(target, origin)
                completed += 1
                print(f"Organized: {target.relative_to(ROOT)}")
            except (OSError, UnicodeError, ValueError, shutil.Error,
                    subprocess.SubprocessError) as error:
                errors += 1
                report_error(f"Error processing {source.name}", error)
        try:
            remove_empty_directories()
        except (OSError, ValueError) as error:
            errors += 1
            report_error("Could not completely remove solutions/", error)
        table = generate_table()
        updated = re.sub(
            TABLE_PATTERN, lambda _: f"{START}\n\n{table}\n\n{END}",
            original, flags=re.DOTALL,
        )
        if updated != original:
            README.write_text(updated, encoding="utf-8")
        commit_paths("Update README", README)
        print(f"Done: {completed}/{len(tasks)} directories; errors: {errors}.")
        return 1 if errors else 0
    except (OSError, UnicodeError, ValueError, shutil.Error,
            subprocess.SubprocessError) as error:
        report_error("Organizer error", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
