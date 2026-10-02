# scripts/organizer.py
"""Organize LeetSync solutions and refresh the generated README table."""

import html
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
CATEGORY_MAP = {
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
        print("Brak zmian do zacommitowania.")
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
            raise ValueError(f"Niedozwolone dowiązanie: {current}")


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
            raise ValueError(f"Konflikt katalog/plik: {target}")
        for child in source.iterdir():
            validate_move(child, target / child.name)
    else:
        if not source.is_file():
            raise ValueError(f"Nieobsługiwany plik: {source}")
        if target.exists() and not target.is_file():
            raise ValueError(f"Konflikt plik/katalog: {target}")
        if source.name == "notes.md" and target.exists():
            raise ValueError(
                f"Obie lokalizacje zawierają notes.md: {source}, {target}. "
                "Połącz notatki ręcznie."
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
            raise ValueError(f"notes.md nie jest plikiem: {notes}")
        return
    name = task.name
    template = (
        f"# {name}\n"
        "- **Link:** \n"
        "- **Time Complexity:** O()\n"
        "- **Space Complexity:** O()\n"
        "- **Intuicja:** \n\n"
        "## Anki Fiszka\n"
        f"**Front:** Jak optymalnie rozwiązać {name}?\n"
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
            "W solutions/ pozostały nierozpoznane pliki lub dowiązania. "
            "Zachowano je; sprawdź ich strukturę."
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


def generate_table():
    sections = []
    for category in directories(ROOT):
        if category.name in {"solutions", "scripts"}:
            continue
        patterns = []
        for pattern in directories(category):
            tasks = sorted(
                (task for task in directories(pattern)
                 if TASK_PATTERN.fullmatch(task.name)),
                key=task_sort_key,
            )
            if not tasks:
                continue
            heading = html.escape(pattern.name.replace("_", " "))
            rows = [
                f"<details><summary><b>{heading}</b></summary>", "",
                "| Zadanie | Kod | Notatki |", "| --- | --- | --- |",
            ]
            for task in tasks:
                notes = task / "notes.md"
                notes_link = link(notes, "Notatki") if notes.is_file() else "—"
                rows.append(
                    f"| {markdown_label(task.name)} | {code_links(task)} "
                    f"| {notes_link} |"
                )
            rows.extend(["", "</details>"])
            patterns.append("\n".join(rows))
        if patterns:
            sections.append(
                f"### {markdown_label(category.name)}\n\n"
                + "\n\n".join(patterns)
            )
    return "\n\n".join(sections) or "_Brak rozwiązanych zadań._"


def main():
    try:
        check_path(SOLUTIONS)
        if not SOLUTIONS.exists():
            print("Brak folderu solutions/ — nic do zorganizowania.")
            return 0
        if not SOLUTIONS.is_dir():
            raise ValueError("solutions istnieje, ale nie jest katalogiem.")
        check_path(README)
        original = README.read_text(encoding="utf-8")
        if (original.count(START) != 1 or original.count(END) != 1
                or original.index(START) >= original.index(END)):
            raise ValueError(
                "README.md musi zawierać dokładnie jedną poprawnie "
                "uporządkowaną parę START_TABLE / END_TABLE."
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
                        "Brak wiadomości commitu w historii zadania; "
                        "najpierw zapisz rozwiązanie w Git."
                    )
                match = TASK_PATTERN.fullmatch(source.name)
                key = f"{int(match.group(1))}-{match.group(2)}"
                target = ROOT / CATEGORY_MAP.get(key, DEFAULT_CATEGORY) / source.name
                validate_move(source, target)
                move_tree(source, target)
                ensure_notes(target)
                commit_paths(message, source, target)
                completed += 1
                print(f"Zorganizowano: {target.relative_to(ROOT)}")
            except (OSError, UnicodeError, ValueError, shutil.Error,
                    subprocess.SubprocessError) as error:
                errors += 1
                report_error(f"Błąd zadania {source.name}", error)
        try:
            remove_empty_directories()
        except (OSError, ValueError) as error:
            errors += 1
            report_error("Nie usunięto całego solutions/", error)
        table = generate_table()
        updated = re.sub(
            TABLE_PATTERN, lambda _: f"{START}\n\n{table}\n\n{END}",
            original, flags=re.DOTALL,
        )
        if updated != original:
            README.write_text(updated, encoding="utf-8")
        commit_paths("Aktualizacja pliku README", README)
        print(f"Gotowe: {completed}/{len(tasks)} folderów; błędy: {errors}.")
        return 1 if errors else 0
    except (OSError, UnicodeError, ValueError, shutil.Error,
            subprocess.SubprocessError) as error:
        report_error("Błąd organizatora", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
