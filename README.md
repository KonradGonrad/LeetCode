<div align="center">
  
  <h1>LeetCode Summary</h1>
  
  <img src="https://leetcard.jacoblin.cool/KonradGonradLeetCode?theme=dark" alt="LeetCode Stats" />

</div>

<!-- START_TABLE -->
<!-- END_TABLE -->

## Automatyzacja

Push zmian w `solutions/**` na `main` uruchamia organizator i aktualizację tabeli.
Lokalnie organizator można uruchomić poleceniem `python3 scripts/organizer.py`.

## Fiszki Anki

Uzupełnij pola `**Front:**` i `**Back:**` w plikach `notes.md`.
Puste fiszki są pomijane. Treść Markdown jest wyświetlana jako tekst.

- Synchronizacja: uruchom Anki z dodatkiem AnkiConnect, następnie
  `python3 scripts/sync_anki.py`. Kierunek synchronizacji to `notes.md` → Anki;
  odpowiedzi zmienione w Anki zostaną zastąpione treścią z repozytorium.
- Eksport alternatywny: zainstaluj `python3 -m pip install -r requirements.txt`
  i uruchom `python3 scripts/generate_anki.py`. Powstanie `LeetCode_Deck.apkg`.

Synchronizacja używa talii `LeetCode`, a eksport talii `LeetCode Algorithms`.
Są to alternatywne sposoby pracy, z osobnymi fiszkami. Pytanie identyfikuje
fiszkę: zmiana pola Front tworzy nową fiszkę; zmiana Back aktualizuje istniejącą.
