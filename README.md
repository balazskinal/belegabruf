# Belegabruf

Holt Rechnungen, die es nur im eingeloggten Konto eines Anbieters gibt, per Doppelklick auf den
eigenen Rechner. **Version 1 kann Airbnb:** die Rechnungen über die Airbnb-Servicegebühren für
Gastgeber, jede Buchung als eigenes PDF.

**Das ist kein Dienst — jeder betreibt seine eigene Kopie.** Niemand außer dir sieht deine
Anmeldung oder deine Belege. Es gibt keinen Server, kein Konto bei uns, keinen Support-Vertrag.

| | |
|---|---|
| macOS | getestet |
| Windows | **ungetestet** — gleicher Ablauf, wir suchen noch jemanden, der es ausprobiert |

---

## Was das Programm macht

1. Du doppelklickst **„Belege holen“**.
2. Es prüft, ob du bei Airbnb noch angemeldet bist. Wenn nicht, öffnet sich ein Browserfenster
   und **du** meldest dich ganz normal an (auch mit Zwei-Faktor). Dein Passwort steht nirgends.
3. Danach holt es alles allein und unsichtbar, in ruhigem, menschlichem Tempo:
   - die **Monatsübersichten** der letzten 12 Monate → Ordner `airbnb/kontrolle/`
   - jede **Einzelrechnung** daraus → `airbnb/<Jahr>/<Rechnungsdatum>_<Buchungscode>_<Rechnungsnummer>.pdf`
4. Am Ende steht eine Zusammenfassung: wie viele neu, wie viele schon da, und ob die Anzahl zu den
   Monatsübersichten passt.

Was schon da ist, wird nicht noch einmal geholt (das merkt sich die Datei `protokoll.csv` im
Belegordner). Gastnamen kommen nirgends vor — weder in Dateinamen noch im Protokoll.

**Wichtig:** Airbnb zeigt nur die **letzten 12 Monate**. Was älter ist, ist weg. Am besten einmal
im Monat laufen lassen. Liegt der letzte Lauf über zwei Monate zurück, warnt das Programm beim Start.

---

## Einrichten (einmalig, ca. 5 Minuten)

Du brauchst eine Internetverbindung. Installiert wird nur in deinem Benutzerkonto, keine
Administratorrechte nötig.

1. **Herunterladen:** Auf der Seite [Neueste Version](https://github.com/balazskinal/belegabruf/releases/latest)
   die Datei `belegabruf-v….zip` laden.
2. **Auspacken:** Doppelklick auf die ZIP-Datei. Den entstandenen Ordner `belegabruf-v…` an einen
   Ort legen, wo er bleiben darf (z. B. in deinen Dokumenten-Ordner).
3. **„Einrichten“ doppelklicken** — auf dem Mac `Einrichten.command`, unter Windows `Einrichten.cmd`.

   **Beim ersten Mal fragt dein Rechner einmal nach, ob du das wirklich öffnen willst.** Das ist
   normal bei Programmen, die nicht aus einem App-Store kommen:
   - **Mac:** Es kommt die Meldung, die Datei könne nicht geöffnet werden. Dann
     *Systemeinstellungen → Datenschutz & Sicherheit* öffnen, ganz nach unten scrollen und bei
     „Einrichten.command wurde blockiert“ auf **„Trotzdem öffnen“** klicken. Bei „Belege holen.command“
     kommt die gleiche Frage beim ersten Start noch einmal.
   - **Windows:** Es erscheint „Der Computer wurde durch Windows geschützt“. Auf **„Weitere
     Informationen“** und dann **„Trotzdem ausführen“** klicken.
4. Ein schwarzes Fenster geht auf und lädt alles Nötige (ein Hilfsprogramm namens *uv*, Python und
   einen eigenen Browser). Das dauert beim ersten Mal ein paar Minuten.
5. Dann kommen ein paar Fragen. **Enter übernimmt jeweils den Vorschlag in [Klammern].**
   - Welche Anbieter (zurzeit nur Airbnb)
   - Ein Name für dein Konto — nur für dich, z. B. „privat“. Hast du mehrere Airbnb-Konten
     (z. B. einen Zugang als Co-Gastgeber), kannst du mehrere eintragen; jedes bekommt seine eigene Anmeldung.
   - Der Belegordner (Vorschlag: `Dokumente/Belege`)
6. Zum Schluss öffnet sich das Airbnb-Anmeldefenster. Melde dich an. Fertig.

## Benutzen

Doppelklick auf **„Belege holen“** (`Belege holen.command` bzw. `Belege holen.cmd`).

- **Enter** = los
- **E** = Einstellungen ändern (die Fragen von oben noch einmal)
- **Q** = beenden

Während des Abrufs musst du nichts tun und kannst den Rechner normal weiterbenutzen.

**Läuft die Anmeldung mittendrin ab** (Airbnb verlangt manchmal schnell eine neue Anmeldung),
meldet das Programm das in der Zusammenfassung. Beim nächsten Start kommt das Anmeldefenster, und
der Rest wird nachgeholt.

**Eine Datei noch einmal holen:** einfach die PDF-Datei löschen — beim nächsten Lauf kommt sie neu.

## Wo was liegt

| Was | Wo |
|---|---|
| Deine Belege | der Belegordner, den du beim Einrichten angegeben hast |
| Einstellungen | Mac: `~/Library/Application Support/belegabruf/einstellungen.toml` · Windows: `%APPDATA%\belegabruf\einstellungen.toml` |
| Anmeldungen (Browserprofile) | im selben Ordner unter `profile/` |

Die Einstellungsdatei ist eine Textdatei mit Erklärungen und lässt sich mit jedem Texteditor
ändern. Ein Konto lässt sich dort mit `aktiv = "nein"` vorübergehend ausschalten.

Der Ordner `profile/` enthält deine eingeloggten Sitzungen — **wie ein offener Browser, in dem du
angemeldet bist.** Gib ihn nicht weiter und leg ihn nicht in eine Cloud-Freigabe. Zum Abmelden
reicht es, ihn zu löschen.

## Neue Version installieren (Update)

Beim Start steht ein Hinweis, wenn es eine neuere Version gibt. Dann:

1. Den **alten Programmordner löschen.**
2. Die neue ZIP-Datei von [Neueste Version](https://github.com/balazskinal/belegabruf/releases/latest) laden und auspacken.
3. „Einrichten“ doppelklicken (lädt eventuell neue Bausteine; deine Antworten bleiben als Vorschlag stehen).

Einstellungen, Anmeldungen und Belege bleiben dabei erhalten — sie liegen nicht im Programmordner.
Ein automatisches Selbst-Update gibt es bewusst nicht.

## Rechtliches

- Das Programm ruft **deine eigenen Rechnungen aus deinem eigenen Konto** ab, so wie du es von Hand
  im Browser tun würdest, und in einem ähnlich ruhigen Tempo. Ob das zu den Nutzungsbedingungen des
  Anbieters passt, **prüft jeder selbst.**
- Fragen zu Aufbewahrungspflichten und Buchhaltung klärst du am besten mit deinem Steuerberater.
- Lizenz: MIT (siehe [LICENSE](LICENSE)). Keine Gewähr.

---

## Für Neugierige und Entwickler

### Kommandozeile

Im Programmordner (mit installiertem [uv](https://docs.astral.sh/uv/)):

```bash
uv run belege                                   # wie Doppelklick
uv run belege einrichten
uv run belege pruefen --json                    # sind die Konten angemeldet?
uv run belege anmelden --quelle airbnb --konto privat
uv run belege holen --quelle airbnb --json      # unbeaufsichtigt, öffnet nie ein Fenster
```

`belege holen` gibt mit `--json` ein maschinenlesbares Ergebnis aus (Fortschritt geht nach stderr).
Exit-Code: 0 = alles gut, 2 = Anmeldung nötig oder abgelaufen, 1 = Fehler. So lassen sich die
Bausteine später auch aus einer Automatisierung (z. B. n8n) aufrufen.

### Aufbau

```
belegabruf/
  cli.py            Kommandozeile und Ablauf beim Doppelklick
  ablauf.py         Gerüst: prüfen, anmelden lassen, holen, abliefern
  quellen/          ein Baustein je Anbieter (Version 1: airbnb.py)
    basis.py        die feste Schnittstelle für Bausteine
  ziele/            wohin Belege geliefert werden (Version 1: ordner.py)
  protokoll.py      protokoll.csv — verhindert Doppelte
  pruefung.py       nie eine Anmelde-, 404- oder leere Seite als Beleg speichern
```

Ein **Baustein (Quelle)** kann genau drei Dinge: `sitzung_pruefen()`, `anmelden_lassen()` und
`belege_holen()`. Er speichert nichts selbst, sondern übergibt jeden Beleg an die **Ziele**. Das
Ziel „ordner“ legt Dateien ab; weitere Ziele (z. B. Upload an eine Buchhaltungssoftware) kommen als
eigene Datei in `ziele/` dazu, ohne dass sich die Quellen ändern.

Tests: `uv run --group dev pytest`

### Neue Bausteine beitragen

Neue Bausteine (z. B. für einen weiteren Anbieter) bitte als **Pull Request**. Gemergt wird **nur
vom Maintainer**. Ein Baustein arbeitet mit den angemeldeten Sitzungen der Nutzer — deshalb wird
jeder fremde Beitrag vor einem Release vollständig geprüft. Regeln für Bausteine:

- kein Passwort, kein Token im Code; angemeldet wird immer vom Menschen im sichtbaren Fenster
- menschliches Tempo (`browser.pause()` zwischen Abrufen)
- Inhalt prüfen, bevor etwas als Beleg gilt (`pruefung.py`)
- keine personenbezogenen Daten Dritter (z. B. Gastnamen) in Dateinamen, Protokoll oder Ausgabe

### Neue Version veröffentlichen (Maintainer)

Version in `pyproject.toml` erhöhen, committen, dann Tag setzen und pushen:

```bash
git tag v1.0.1
```

```bash
git push origin v1.0.1
```

Die GitHub Action baut das ZIP und hängt es an das Release.

## Offen

- **Windows:** noch von niemandem getestet (Abnahmepunkt 5). Wer es ausprobiert, bitte Rückmeldung.
- Weitere Bausteine und das Ziel „Upload an die Buchhaltung“ folgen in späteren Versionen.
