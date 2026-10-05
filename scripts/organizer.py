"""Keep solutions flat, preserve LeetSync results, and publish recent notebooks."""

import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOLUTIONS = ROOT / "solutions"
README = ROOT / "README.md"
START = "<!-- START_TABLE -->"
END = "<!-- END_TABLE -->"
TASK_PATTERN = re.compile(r"^\d+-.+$")
CODE_EXTENSIONS = {
    ".py", ".sql", ".java", ".js", ".ts", ".cpp", ".cc", ".c", ".h",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".dart", ".r", ".sh",
}


def git(*args, check=True):
    return subprocess.run(
        ["git", "--literal-pathspecs", *args], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", check=check,
    )


def report_error(context, error):
    detail = (error.stderr or error.stdout) if isinstance(error, subprocess.CalledProcessError) else str(error)
    print(f"{context}: {detail or error}", file=sys.stderr)


def check_path(path):
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Symbolic links are not allowed: {current}")


def commit_paths(message, *paths):
    relative = list(dict.fromkeys(path.relative_to(ROOT).as_posix() for path in paths))
    git("add", "-A", "--", *relative)
    diff = git("diff", "--cached", "--quiet", "--", *relative, check=False)
    if diff.returncode == 0:
        return False
    if diff.returncode != 1:
        diff.check_returncode()
    result = git("commit", "--only", "--cleanup=verbatim", "-m", message, "--", *relative)
    print(result.stdout.strip())
    return True


def walk_error(error):
    raise error


def discover_tasks():
    # Former category roots are supported only for migration into solutions/.
    tasks = []
    for name in ("solutions", "Algorithm", "Database", "Pandas"):
        root = ROOT / name
        check_path(root)
        if not root.exists():
            continue
        if not root.is_dir():
            raise ValueError(f"Expected a directory: {root}")
        for base, dirs, _ in os.walk(root, onerror=walk_error):
            remaining = []
            for name in sorted(dirs):
                path = Path(base) / name
                check_path(path)
                if TASK_PATTERN.fullmatch(name):
                    tasks.append(path)
                elif not name.startswith("."):
                    remaining.append(name)
            dirs[:] = remaining
    return tasks


def code_files(task):
    return sorted(
        path for path in task.rglob("*")
        if path.is_file() and not path.is_symlink()
        and not any(part.startswith(".") for part in path.relative_to(task).parts)
        and path.suffix.lower() in CODE_EXTENSIONS
    )


def submission(task):
    """Read solution history, excluding notebook and metadata-only commits."""
    metadata = task / ".leetsync.json"
    check_path(metadata)
    saved = json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
    if not isinstance(saved, dict):
        raise ValueError(f"Invalid submission metadata: {metadata}")
    paths = []
    for path in code_files(task):
        paths.extend([
            path.relative_to(ROOT).as_posix(),
            (Path("solutions") / task.name / path.relative_to(task)).as_posix(),
        ])
    if not paths:
        return None
    revision = git(
        "log", "-1", "--format=%H", "--fixed-strings", "--grep=LeetSync",
        "--diff-filter=AM", "--", *paths,
    ).stdout.strip()
    metadata_commit = git(
        "log", "-1", "--format=%H", "--", metadata.relative_to(ROOT).as_posix()
    ).stdout.strip() if saved else ""
    # A migration commit can touch both code and metadata. Retain its source date.
    if saved.get("source_commit") and (
        not revision or revision == metadata_commit
        or revision == saved.get("organization_commit")
    ):
        revision = saved["source_commit"]
    if not revision:
        revision = git("log", "-1", "--format=%H", "--diff-filter=AM", "--", *paths).stdout.strip()
    if not revision:
        return None
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ValueError(f"Invalid source commit for {task.name}")
    timestamp, message = git("show", "-s", "--format=%ct%x00%B", revision).stdout.split("\0", 1)
    return {
        "source_commit": revision,
        "message": message.rstrip("\n"),
        "submitted_at": int(timestamp),
    }


def notebook_data(task):
    legacy = task / "notes.md"
    check_path(legacy)
    slug = task.name.split("-", 1)[1]
    text = legacy.read_text(encoding="utf-8") if legacy.exists() else (
        f"# {task.name}\n\n"
        f"[Problem on LeetCode](https://leetcode.com/problems/{slug}/)\n\n"
        "## Approach\n\nWrite your reasoning here.\n\n"
        "## Complexity\n\n- Time: \n- Space: \n"
    )
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)},
            {"cell_type": "code", "execution_count": None, "metadata": {},
             "outputs": [], "source": []},
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }


def ensure_notebook(task):
    notes = task / "notes.ipynb"
    check_path(notes)
    if notes.exists():
        if not notes.is_file():
            raise ValueError(f"Notebook is not a file: {notes}")
        return
    data = notebook_data(task)
    with notes.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    # Content has been preserved verbatim in the notebook's Markdown cell.
    legacy = task / "notes.md"
    if legacy.exists():
        legacy.unlink()


def prepare_task(source, origin):
    target = SOLUTIONS / source.name
    check_path(target)
    if source != target:
        if target.exists():
            raise ValueError(f"Destination already exists; merge manually: {target}")
        for path in source.rglob("*"):
            check_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    ensure_notebook(target)
    metadata = target / ".leetsync.json"
    check_path(metadata)
    content = json.dumps(origin, ensure_ascii=False, indent=2) + "\n"
    if not metadata.exists() or metadata.read_text(encoding="utf-8") != content:
        metadata.write_text(content, encoding="utf-8")
    return target


def remove_empty_legacy_directories():
    for name in ("Algorithm", "Database", "Pandas"):
        root = ROOT / name
        if root.is_dir():
            for base, _, _ in os.walk(root, topdown=False, onerror=walk_error):
                path = Path(base)
                if not path.is_symlink() and not any(path.iterdir()):
                    path.rmdir()


def markdown_label(value):
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", value)


def link(path, label):
    return f"[{markdown_label(label)}](./{quote(path.relative_to(ROOT).as_posix(), safe='/')})"


def difficulty(task):
    path = task / "README.md"
    check_path(path)
    if not path.is_file():
        return "—"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Difficulty\s*[:\-]\s*(Easy|Medium|Hard)\b", text, re.IGNORECASE)
    return match.group(1).capitalize() if match else "—"


def generate_table():
    entries = []
    order = {sha: index for index, sha in enumerate(git("rev-list", "HEAD").stdout.splitlines())}
    if SOLUTIONS.is_dir():
        for task in SOLUTIONS.iterdir():
            if task.is_dir() and not task.is_symlink() and TASK_PATTERN.fullmatch(task.name):
                info = submission(task)
                if info:
                    entries.append((task, info))
    entries.sort(key=lambda item: (
        -item[1]["submitted_at"],
        order.get(item[1]["source_commit"], len(order)),
        item[0].name,
    ))
    rows = [
        "<details>",
        "<summary><strong>Latest 10 solved problems</strong></summary>",
        "",
        "| Problem | Code | Notes | Time | Difficulty |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task, info in entries[:10]:
        code = "<br>".join(link(path, path.name) for path in code_files(task)) or "—"
        notes = task / "notes.ipynb"
        note_link = link(notes, "Notebook") if notes.is_file() and not notes.is_symlink() else "—"
        message = info["message"]
        result = re.sub(r" - LeetSync\s*$", "", message) if re.search(r"\bTime:", message) else ""
        result = "<br>".join(markdown_label(line) for line in result.splitlines()) or "—"
        rows.append(
            f"| {link(task, task.name)} | {code} | {note_link} | {result} | {difficulty(task)} |"
        )
    rows.extend(["", "</details>"])
    return "\n".join(rows)


def update_readme():
    check_path(README)
    original = README.read_text(encoding="utf-8")
    if (original.count(START) != 1 or original.count(END) != 1
            or original.index(START) >= original.index(END)):
        raise ValueError("README.md must contain one ordered START_TABLE / END_TABLE pair.")
    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        lambda _: f"{START}\n\n{generate_table()}\n\n{END}",
        original, flags=re.DOTALL,
    )
    if updated != original:
        README.write_text(updated, encoding="utf-8")


def main():
    errors = 0
    try:
        # Validate the marker pair before changing any solution files.
        check_path(README)
        text = README.read_text(encoding="utf-8")
        if (text.count(START) != 1 or text.count(END) != 1
                or text.index(START) >= text.index(END)):
            raise ValueError("README.md must contain one ordered START_TABLE / END_TABLE pair.")
        for source in discover_tasks():
            try:
                origin = submission(source)
                if not origin:
                    raise ValueError("Commit the solution to Git before running the organizer.")
                target = prepare_task(source, origin)
                commit_paths(origin["message"], source, target)
                print(f"Prepared: {target.relative_to(ROOT)}")
            except (OSError, ValueError, subprocess.SubprocessError, shutil.Error) as error:
                errors += 1
                report_error(f"Error processing {source.name}", error)
        remove_empty_legacy_directories()
        update_readme()
        commit_paths("Update README", README)
    except (OSError, ValueError, subprocess.SubprocessError, shutil.Error) as error:
        errors += 1
        report_error("Organizer error", error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
