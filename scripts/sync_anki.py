# scripts/sync_anki.py
"""Synchronize repository notes to a running local AnkiConnect instance."""

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANKI_URL = "http://localhost:8765"
DECK_NAME = "LeetCode"
FALLBACK_MODEL = "LeetCode Basic"
TITLE_RE = re.compile(r"\A#[ \t]+([^\r\n]+)")
CARD_RE = re.compile(
    r"^\*\*Front:\*\*[ \t]*(?P<front>[^\r\n]*)"
    r"\r?\n[ \t\r\n]*"
    r"^\*\*Back:\*\*[ \t]*(?P<back>.*)\Z",
    re.MULTILINE | re.DOTALL,
)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class AnkiError(RuntimeError):
    pass


def invoke_anki(action, **params):
    payload = {"action": action, "version": 6, "params": params}
    api_key = os.environ.get("ANKICONNECT_API_KEY")
    if api_key:
        payload["key"] = api_key
    request = urllib.request.Request(
        ANKI_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with OPENER.open(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise AnkiError(f"HTTP {error.code} podczas {action}") from error
    except (urllib.error.URLError, OSError) as error:
        raise ConnectionError(
            "Uruchom Anki i zainstaluj AnkiConnect"
        ) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise AnkiError("AnkiConnect zwrócił niepoprawny JSON.") from error
    if (not isinstance(result, dict)
            or "error" not in result or "result" not in result):
        raise AnkiError("Niepoprawna struktura odpowiedzi AnkiConnect.")
    if result["error"] is not None:
        raise AnkiError(f"{action}: {result['error']}")
    return result["result"]


def walk_error(error):
    raise error


def iter_notes():
    for base, dirs, files in os.walk(
        ROOT, followlinks=False, onerror=walk_error
    ):
        dirs[:] = sorted(
            name for name in dirs
            if not name.startswith(".")
            and name not in {"venv", "node_modules", "__pycache__"}
            and not (Path(base) / name).is_symlink()
        )
        if "notes.md" in files:
            path = Path(base) / "notes.md"
            if not path.is_symlink():
                yield path


def parse_notes(path):
    text = path.read_text(encoding="utf-8-sig")
    title_match = TITLE_RE.search(text)
    card_match = CARD_RE.search(text)
    if not title_match or not card_match:
        return None
    title = title_match.group(1).strip()
    front = card_match.group("front").strip()
    back = card_match.group("back").strip()
    if not title or not front or not back:
        return None
    return title, front, back


def to_anki_html(text):
    return html.escape(text, quote=False).replace("\n", "<br>")


def front_query(front):
    escaped = html.escape(front, quote=False)
    escaped = re.sub(r'([\\*"_])', r'\\\1', escaped)
    return f'"deck:{DECK_NAME}" "Front:{escaped}"'


def select_model():
    models = invoke_anki("modelNames")
    if not isinstance(models, list):
        raise AnkiError("modelNames nie zwróciło listy.")
    for name in ("Basic", FALLBACK_MODEL):
        if name in models:
            fields = invoke_anki("modelFieldNames", modelName=name)
            if isinstance(fields, list) and set(fields) == {"Front", "Back"}:
                return name
            if name == FALLBACK_MODEL:
                raise AnkiError(f"Model {FALLBACK_MODEL} ma niezgodne pola.")
    invoke_anki(
        "createModel", modelName=FALLBACK_MODEL,
        inOrderFields=["Front", "Back"],
        css=(".card { font-family: Arial; font-size: 20px; "
             "text-align: left; white-space: pre-wrap; }"),
        isCloze=False,
        cardTemplates=[{
            "Name": "Card 1", "Front": "{{Front}}",
            "Back": '{{FrontSide}}<hr id="answer">{{Back}}',
        }],
    )
    return FALLBACK_MODEL


def read_back(ids):
    notes = invoke_anki("notesInfo", notes=ids)
    try:
        if not isinstance(notes, list) or len(notes) != 1:
            raise ValueError("Oczekiwano jednej notatki.")
        value = notes[0]["fields"]["Back"]["value"]
        if not isinstance(value, str):
            raise ValueError("Back nie jest tekstem.")
        return value
    except (KeyError, TypeError, ValueError) as error:
        raise AnkiError("Nie udało się odczytać pola Back fiszki.") from error


def sync_card(model_name, front, back):
    ids = invoke_anki("findNotes", query=front_query(front))
    if not isinstance(ids, list):
        raise AnkiError("findNotes nie zwróciło listy.")
    expected_back = to_anki_html(back)
    if not ids:
        note_id = invoke_anki(
            "addNote",
            note={
                "deckName": DECK_NAME, "modelName": model_name,
                "fields": {"Front": to_anki_html(front), "Back": expected_back},
                "options": {"allowDuplicate": False, "duplicateScope": "deck"},
                "tags": ["leetcode"],
            },
        )
        if not isinstance(note_id, int):
            raise AnkiError("Anki nie potwierdziło dodania notatki.")
        return "dodane"
    if len(ids) != 1:
        raise AnkiError(
            f"Znaleziono {len(ids)} fiszek z tym Front. Usuń duplikaty w Anki."
        )
    if read_back(ids) == expected_back:
        return "bez_zmian"
    invoke_anki(
        "updateNoteFields", note={"id": ids[0], "fields": {"Back": expected_back}}
    )
    if read_back(ids) != expected_back:
        raise AnkiError(
            "Nie potwierdzono zapisu. Zamknij edycję fiszki w Anki "
            "i spróbuj ponownie."
        )
    return "zaktualizowane"


def main():
    counts = dict.fromkeys(
        ["dodane", "zaktualizowane", "bez_zmian", "pominięte", "błędy"], 0
    )
    seen_fronts = set()
    try:
        invoke_anki("createDeck", deck=DECK_NAME)
        model_name = select_model()
        for path in iter_notes():
            try:
                parsed = parse_notes(path)
                if parsed is None:
                    counts["pominięte"] += 1
                    print(f"Pominięto niewypełnioną notatkę: {path}")
                    continue
                title, front, back = parsed
                if front in seen_fronts:
                    raise ValueError("Pytanie Front powtarza się w repozytorium.")
                seen_fronts.add(front)
                status = sync_card(model_name, front, back)
                counts[status] += 1
                print(f"{status}: {title}")
            except ConnectionError:
                raise
            except (OSError, UnicodeError, ValueError, AnkiError) as error:
                counts["błędy"] += 1
                print(f"Błąd {path}: {error}", file=sys.stderr)
    except ConnectionError as error:
        counts["błędy"] += 1
        print(str(error), file=sys.stderr)
    except (OSError, AnkiError) as error:
        counts["błędy"] += 1
        print(f"Błąd synchronizacji: {error}", file=sys.stderr)
    finally:
        print("\nPodsumowanie synchronizacji:")
        for label, count in counts.items():
            print(f"  {label.replace('_', ' ').capitalize()}: {count}")
    return 1 if counts["błędy"] else 0


if __name__ == "__main__":
    sys.exit(main())
