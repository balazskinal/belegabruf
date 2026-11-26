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

## Nachtrag (26.11.2026, 2.1.1): Übernahme verwaister Konten

Profil und Protokoll hängen an der internen Kennung eines Kontos (seit 2.0: Name, ohne Namen
„standard“, sonst `kennung` in der Datei). Geht die Kennung verloren — Konto entfernt und neu angelegt,
Einstellungsdatei beim Einrichten nicht lesbar, Name von Hand gelöscht —, entstand bisher still ein
neues, leeres Protokoll; alles wurde noch einmal geholt (bei „Erster Versand: auch“ auch verschickt).

Seit 2.1.1 (`waisen.py`): Hat ein Konto **ohne Namen** (Standard-Kennung, ohne `kennung` in der Datei)
kein Protokoll unter seiner Kennung, und gibt es beim selben Anbieter **genau ein** Protokoll (bzw. ohne
Protokoll genau ein Profil), das zu keinem Konto gehört und nicht als entfernt vermerkt ist, übernimmt
das Konto dessen Kennung; beim nächsten Speichern steht sie als `kennung` in der Datei. Konten mit Namen
oder ausdrücklicher `kennung` werden nie umgebogen; wer ein Konto in den Einstellungen entfernt, dessen
Profil und Protokoll werden als entfernt vermerkt (`entfernt` im Merkzettel) und nie weitergegeben. Der
Inhalt des übernommenen Protokolls gilt als verarbeitet: Für jedes Lieferziel, das darin noch nie an
war, wird er einmalig als „schon geliefert“ markiert (`einstellung:uebernahme` im Protokoll); war ein
Ziel schon an, bleibt Offenes (gescheiterter Versand) offen. Ist es nicht
eindeutig, wird nicht geraten — das Konto wird ausgelassen, mit Meldung. Über eine unlesbare
Einstellungsdatei wird nicht mehr gespeichert.

