# scripts/generate_anki.py
"""Export notes as an Anki package without connecting to Anki."""

import sys

try:
    import genanki
except ImportError:
    genanki = None

if __package__:
    from .sync_anki import ROOT, iter_notes, parse_notes, to_anki_html
else:
    from sync_anki import ROOT, iter_notes, parse_notes, to_anki_html

MODEL_ID = 1867452301
DECK_ID = 1986543207


def main():
    if genanki is None:
        print(
            "genanki is not installed. Run: python -m pip install genanki",
            file=sys.stderr,
        )
        return 1
    try:
        model = genanki.Model(
            MODEL_ID, "LeetCode Algorithms Question Answer",
            fields=[{"name": "Question"}, {"name": "Answer"}],
            templates=[{
                "name": "Card 1", "qfmt": "{{Question}}",
                "afmt": '{{FrontSide}}<hr id="answer">{{Answer}}',
            }],
            css=(".card { font-family: Arial; font-size: 20px; "
                 "text-align: left; white-space: pre-wrap; }"),
        )
        my_deck = genanki.Deck(DECK_ID, "LeetCode Algorithms")
        seen_fronts = set()
        added = skipped = errors = 0
        for path in iter_notes():
            try:
                parsed = parse_notes(path)
                if parsed is None:
                    skipped += 1
                    continue
                _, front, back = parsed
                if front in seen_fronts:
                    raise ValueError("Duplicate Front question in the repository.")
                seen_fronts.add(front)
                note = genanki.Note(
                    model=model,
                    fields=[to_anki_html(front), to_anki_html(back)],
                    guid=genanki.guid_for("leetcode-algorithms-v1", front),
                    tags=["leetcode"],
                )
                my_deck.add_note(note)
                added += 1
            except (OSError, UnicodeError, ValueError) as error:
                errors += 1
                print(f"Error in {path}: {error}", file=sys.stderr)
        if errors:
            print(
                f"Export aborted: {errors} errors. "
                "The existing APKG file has not been changed.", file=sys.stderr,
            )
            return 1
        if not added:
            print(f"No completed flashcards found. Skipped: {skipped}.")
            return 0
        output = ROOT / "LeetCode_Deck.apkg"
        genanki.Package(my_deck).write_to_file(str(output))
        print(f"Saved: {output}")
        print(f"Flashcards: {added}; skipped templates: {skipped}.")
        return 0
    except Exception as error:
        print(f"APKG export error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
