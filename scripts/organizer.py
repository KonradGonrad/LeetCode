"""Organize solutions by difficulty and publish results, tags, and activity."""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

if __package__:
    from . import activity, fetch_tags
else:
    import activity
    import fetch_tags

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
    
    # Usunięto ścieżki z diff, aby sprawdzić cały stage
    diff = git("diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        return False
    if diff.returncode != 1:
        diff.check_returncode()
        
    # Usunięto flagę --only oraz ścieżki z polecenia commit
    result = git("commit", "--cleanup=verbatim", "-m", message)
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
    saved_revision = saved.get("source_commit")
    if saved_revision and saved_revision != revision:
        if not isinstance(saved_revision, str) or not re.fullmatch(r"[0-9a-f]{40,64}", saved_revision):
            raise ValueError(f"Invalid saved source commit for {task.name}")
        # A difficulty change may hide newer code commits under a former path.
        ancestor = git("merge-base", "--is-ancestor", revision, saved_revision, check=False)
        if ancestor.returncode == 0:
            revision = saved_revision
        elif ancestor.returncode != 1:
            ancestor.check_returncode()
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
    level = difficulty(source)
    target = SOLUTIONS / (level if level != "—" else "Unknown") / source.name
    check_path(target)
    if source != target:
        if target.exists():
            previous = submission(target)
            if previous and previous["submitted_at"] > origin["submitted_at"]:
                raise ValueError(f"Destination contains a newer solution: {target}")
            validate_merge(source, target)
        for path in source.rglob("*"):
            check_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        move_tree(source, target)
    ensure_notebook(target)
    metadata = target / ".leetsync.json"
    check_path(metadata)
    data = origin.copy()
    # Restore the folder's LeetSync message after a manual bulk migration commit.
    last = git("log", "-1", "--format=%H%x00%B", "--", target.relative_to(ROOT).as_posix()).stdout
    if last and last.split("\0", 1)[1].rstrip("\n") != origin["message"]:
        data["organization_commit"] = last.split("\0", 1)[0]
    elif metadata.exists():
        previous = json.loads(metadata.read_text(encoding="utf-8"))
        if previous.get("source_commit") == origin["source_commit"] and previous.get("organization_commit"):
            data["organization_commit"] = previous["organization_commit"]
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if not metadata.exists() or metadata.read_text(encoding="utf-8") != content:
        metadata.write_text(content, encoding="utf-8")
    return target


def validate_merge(source, target):
    check_path(source)
    check_path(target)
    if not target.exists():
        return
    if source.is_dir() and target.is_dir():
        for child in source.iterdir():
            validate_merge(child, target / child.name)
    elif source.is_file() and target.is_file():
        if (source.suffix == ".ipynb" or source.name == "notes.md") and source.read_bytes() != target.read_bytes():
            raise ValueError(f"Conflicting personal notes; merge manually: {source}, {target}")
    else:
        raise ValueError(f"File/directory conflict: {target}")


def move_tree(source, target):
    if source.is_dir() and target.exists():
        for child in sorted(source.iterdir()):
            move_tree(child, target / child.name)
        source.rmdir()
    else:
        shutil.move(str(source), str(target))


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


def problem_title(task):
    path = task / "README.md"
    if path.is_file():
        match = re.search(r"<h[12]\b[^>]*>(.*?)</h[12]>", path.read_text(encoding="utf-8"), re.S | re.I)
        if match:
            title = html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
            return re.sub(r"^\d+\.\s*", "", title)
    return task.name.split("-", 1)[1].replace("-", " ").title()


def performance(message):
    message = re.sub(r"\s*- LeetSync\s*$", "", message)
    values = []
    for field in ("Time", "Memory"):
        match = re.search(rf"\b{field}:\s*([^|\n]+)", message)
        values.append(markdown_label(match.group(1).strip()) if match else "—")
    return values


def badge(label, color, kind="tag"):
    if not re.fullmatch(r"[0-9a-fA-F]{6}", color):
        raise ValueError(f"Invalid badge color: {color}")
    name = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    digest = hashlib.sha256(label.encode()).hexdigest()[:8]
    path = ROOT / "assets/badges" / f"{kind}-{name}-{digest}.svg"
    check_path(path)
    width = max(44, len(label) * 7 + 18)
    rgb = [int(color[n:n+2], 16) for n in (0, 2, 4)]
    foreground = "#111827" if sum(c*w for c, w in zip(rgb, (.299, .587, .114))) > 150 else "#ffffff"
    content = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="22" role="img" aria-label="{html.escape(label)}">'
        f'<rect width="{width}" height="22" rx="5" fill="#{color}"/>'
        f'<text x="{width/2}" y="15" text-anchor="middle" fill="{foreground}" '
        f'font-family="DejaVu Sans Mono,monospace" font-size="11">{html.escape(label)}</text></svg>\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != content:
        path.write_text(content, encoding="utf-8")
    return f"![{markdown_label(label)}](./{path.relative_to(ROOT).as_posix()})"


def collect_entries():
    entries = []
    order = {sha: index for index, sha in enumerate(git("rev-list", "HEAD").stdout.splitlines())}
    for task in discover_tasks():
        if task.is_relative_to(SOLUTIONS):
            info = submission(task)
            if info:
                entries.append((task, info))
    entries.sort(key=lambda item: (
        -item[1]["submitted_at"],
        order.get(item[1]["source_commit"], len(order)),
        item[0].name,
    ))
    return entries


def generate_table(entries=None):
    """Generate only problem rows; README owns the table header and layout."""
    if entries is None:
        entries = collect_entries()
    cache = fetch_tags.load_cache(ROOT / "scripts/leetcode_cache.json")
    colors = json.loads((ROOT / "scripts/tag_colors.json").read_text(encoding="utf-8"))
    rows = []
    for task, info in entries[:10]:
        icons = [link(path, "💻") for path in code_files(task)]
        notes = task / "notes.ipynb"
        if notes.is_file() and not notes.is_symlink():
            icons.append(link(notes, "📝"))
        runtime, memory = performance(info["message"])
        level = difficulty(task)
        level_badge = badge(level, colors["difficulty"][level], "difficulty") if level != "—" else "—"
        identifier, slug = task.name.split("-", 1)
        tags = cache.get(slug, {}).get("tags", [])
        tag_badges = []
        for tag in tags:
            palette = colors["palette"]
            fallback = palette[int(hashlib.sha256(tag.encode()).hexdigest()[:8], 16) % len(palette)]
            tag_badges.append(badge(tag, colors["tags"].get(tag, fallback)))
        rows.append(
            f"| {int(identifier)} | {link(task, problem_title(task))} {' '.join(icons)} "
            f"| {runtime} | {memory} | {level_badge} | {' '.join(tag_badges) or '—'} |"
        )
    return "\n".join(rows)


def table_template(text):
    """Validate the editable README template before changing repository files."""
    if (text.count(START) != 1 or text.count(END) != 1
            or text.index(START) >= text.index(END)):
        raise ValueError("README.md must contain one ordered START_TABLE / END_TABLE pair.")
    section = text.split(START, 1)[1].split(END, 1)[0]
    header = re.match(
        r"\s*\|[^\n]+\|\n\|(?:[ \t]*:?-+:?[ \t]*\|){6}[ \t]*\n", section,
    )
    if not header:
        raise ValueError("The README table markers must enclose a six-column Markdown header and its rows.")
    return header.group()


def update_readme(entries=None):
    check_path(README)
    original = README.read_text(encoding="utf-8")
    header = table_template(original)
    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        lambda _: f"{START}{header}{generate_table(entries)}\n\n{END}",
        original, flags=re.DOTALL,
    )
    if updated != original:
        README.write_text(updated, encoding="utf-8")


def main(*, commit=True, offline=False):
    errors = 0
    try:
        # Validate the marker pair before changing any solution files.
        check_path(README)
        text = README.read_text(encoding="utf-8")
        table_template(text)
        for source in discover_tasks():
            try:
                origin = submission(source)
                if not origin:
                    raise ValueError("Commit the solution to Git before running the organizer.")
                target = prepare_task(source, origin)
                if commit:
                    commit_paths(origin["message"], source, target)
                print(f"Prepared: {target.relative_to(ROOT)}")
            except (OSError, ValueError, subprocess.SubprocessError, shutil.Error) as error:
                errors += 1
                report_error(f"Error processing {source.name}", error)
        remove_empty_legacy_directories()
        cache_path = ROOT / "scripts/leetcode_cache.json"
        check_path(cache_path)
        if not offline:
            fetch_tags.update_cache(discover_tasks(), cache_path)
        entries = collect_entries()
        heatmap = ROOT / "assets/heatmap.svg"
        check_path(heatmap)
        activity.write_heatmap(entries, heatmap)
        update_readme(entries)
        if commit:
            paths = [README, ROOT / "assets"]
            if cache_path.exists():
                paths.append(cache_path)
            commit_paths("Update README", *paths)
    except (OSError, ValueError, subprocess.SubprocessError, shutil.Error) as error:
        errors += 1
        report_error("Organizer error", error)
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-commit", action="store_true", help="Prepare files without creating Git commits")
    parser.add_argument("--offline", action="store_true", help="Use cached tags without API calls")
    args = parser.parse_args()
    sys.exit(main(commit=not args.no_commit, offline=args.offline))
