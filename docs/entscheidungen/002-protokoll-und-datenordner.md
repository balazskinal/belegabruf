# ADR-002: Das Protokoll entscheidet, und es liegt im Datenordner

- **Datum:** 24.11.2026
- **Status:** ✅ gilt · umgesetzt in Version 1.1.0

## Kontext

In Version 1.0 galt ein Beleg als erledigt, wenn er im Protokoll stand **und** die Datei noch im
Belegordner lag. Belege werden aber weitergereicht (Buchhaltung, Steuerberatung) und aus dem Ordner
geräumt. Dann kamen sie beim nächsten Lauf wieder — und mit einem Upload ins Buchhaltungsprogramm wären
daraus Doppelte geworden.

## Entscheidung

1. **Allein das Protokoll entscheidet**, ob ein Beleg schon geholt ist. Den Belegordner darf jeder leeren.
   Erneutes Holen nur auf Wunsch: „Fehlende Dateien neu holen“ (Einstellungsmenü bzw. `--fehlende`).
2. **Das Protokoll gehört zum Programm, nicht zu den Belegen.** Es liegt im **Datenordner** bei
   Einstellungen und Anmeldungen — nicht im Programmordner, der bei jedem Update gelöscht wird:
   - macOS: `~/Library/Application Support/belegabruf/`
   - Windows: `%APPDATA%\belegabruf\`
3. **Aufbau des Datenordners:**

   ```
   belegabruf/
     einstellungen.toml
     profile/                 Anmeldungen — dürfen jederzeit gelöscht werden
     protokolle/              nie löschen
       <anbieter>/<konto>.csv
   ```

4. **Nicht in `profile/`:** Ein Profil wird gelöscht, wenn eine Anmeldung klemmt; das Protokoll ginge mit.
5. Beim Umstieg von 1.0 übernimmt das Programm einmal ein altes `protokoll.csv` aus dem Belegordner.
6. Das Protokoll merkt sich je Beleg auch, **wohin er schon geliefert ist** (Spalte `ziele`), damit kein
   Ziel etwas doppelt bekommt (ADR-003).

## Folgen

README: `profile/` darf man löschen, `protokolle/` nie — sonst holt das Programm die verfügbaren Monate
erneut.
