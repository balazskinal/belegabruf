# Belegabruf

Holt Rechnungen, die es nur im eingeloggten Konto eines Anbieters gibt, per Doppelklick auf den
eigenen Rechner. Es kann:

- **Airbnb:** die Rechnungen über die Airbnb-Servicegebühren für Gastgeber, jede Buchung als eigenes PDF.
- **Skool:** die Rechnungen für bezahlte Mitgliedschaften in Skool-Communities (siehe [Skool](#skool)).
- **Xentra:** die Rechnungen für das Xentra-Abonnement und Provisionen (siehe [Xentra](#xentra)).

**Das ist kein Dienst — jeder betreibt seine eigene Kopie.** Niemand außer dir sieht deine
Anmeldung oder deine Belege. Es gibt keinen Server, kein Konto bei uns, keinen Support-Vertrag.

| | |
|---|---|
| macOS | getestet |
| Windows | **ungetestet** — gleicher Ablauf, wir suchen noch jemanden, der es ausprobiert |

---

## Was das Programm macht

1. Du doppelklickst **„Belege holen“** (im Ordner `Start Mac` bzw. `Start Windows`).
2. Es prüft, ob du bei Airbnb noch angemeldet bist. Wenn nicht, öffnet sich ein Browserfenster
   und **du** meldest dich ganz normal an (auch mit Zwei-Faktor). Dein Passwort steht nirgends.
3. Danach holt es alles allein und unsichtbar, in ruhigem, menschlichem Tempo:
   - die **Monatsübersichten** der letzten 12 Monate → Ordner `airbnb/kontrolle/`
   - jede **Einzelrechnung** daraus → `airbnb/<Jahr>/<Rechnungsdatum>_<Buchungscode>_<Rechnungsnummer>.pdf`
4. Am Ende steht eine Zusammenfassung: wie viele neu, wie viele schon da, und ob die Anzahl zu den
   Monatsübersichten passt.

Was einmal geholt wurde, wird nicht noch einmal geholt — **auch wenn du die Datei aus dem
Belegordner löschst oder verschiebst.** Das merkt sich ein **Protokoll** bei den Einstellungen (nicht
im Belegordner). Den Belegordner darfst du also jederzeit leeren oder an die Buchhaltung bzw. den
Steuerberater weiterreichen, ohne dass alles wiederkommt. Gastnamen kommen nirgends vor — weder in
Dateinamen noch im Protokoll.

**Wichtig:** Airbnb zeigt nur die **letzten 12 Monate**. Was älter ist, ist weg. Am besten einmal
im Monat laufen lassen. Liegt der letzte Lauf über zwei Monate zurück, warnt das Programm beim Start.

---

## Was im Ordner liegt

```
belegabruf-v…/
  Start Mac/          ← nur das hier benutzen, wenn du einen Mac hast
    Einrichten.command
    Belege holen.command
  Start Windows/      ← nur das hier benutzen, wenn du Windows hast
    Einrichten.cmd
    Belege holen.cmd
  programm/           ← das eigentliche Programm, hier musst du nichts anfassen
  README.md           ← diese Anleitung
  LICENSE
```

Du brauchst nur den Start-Ordner für dein System. Den Ordner `programm` nicht verschieben oder
umbenennen — die Startdateien suchen ihn direkt daneben.

## Einrichten (einmalig, ca. 5 Minuten)

Du brauchst eine Internetverbindung. Installiert wird nur in deinem Benutzerkonto, keine
Administratorrechte nötig.

1. **Herunterladen:** Auf der Seite [Neueste Version](https://github.com/balazskinal/belegabruf/releases/latest)
   die Datei `belegabruf-v….zip` laden.
2. **Auspacken:** Doppelklick auf die ZIP-Datei. Den entstandenen Ordner `belegabruf-v…` an einen
   Ort legen, wo er bleiben darf (z. B. in deinen Dokumenten-Ordner).
3. **„Einrichten“ doppelklicken** — auf dem Mac `Start Mac/Einrichten.command`, unter Windows
   `Start Windows/Einrichten.cmd`.

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
   - Welche Anbieter (Airbnb, Skool, Xentra)
   - Ein Name für dein Konto — nur für dich, z. B. „privat“. Hast du mehrere Airbnb-Konten
     (z. B. einen Zugang als Co-Gastgeber), kannst du mehrere eintragen; jedes bekommt seine eigene Anmeldung.
   - Der Belegordner (Vorschlag: `Dokumente/Belege`)
6. Zum Schluss öffnet sich das Airbnb-Anmeldefenster. Melde dich an. Fertig.

## Skool

Skool zeigt die Rechnungen unter *Einstellungen → Zahlungsverlauf*, je Zahlung eine Rechnung. Einen
PDF-Knopf gibt es dort nicht: Das Programm öffnet jede Rechnung im (unsichtbaren) Browser, prüft, dass
Überschrift und Gesamtbetrag da sind, und speichert sie selbst als PDF:
`skool/<Jahr>/<Datum>_<Community>_<Rechnungs-ID>.pdf`. Bist du Mitglied in mehreren bezahlten
Communities, kommen alle mit; die Community steht im Dateinamen. Am Ende vergleicht es, ob so viele
Rechnungen geholt sind, wie der Zahlungsverlauf nennt. Das PDF kommt immer im **hellen Design**
heraus (gut zum Drucken und für die Texterkennung), auch wenn dein Skool-Konto auf Dunkel steht — das
gilt nur für den Ausdruck, deine Einstellung bei Skool bleibt, wie sie ist.

Das Programm **liest nur und lädt herunter**. Es klickt bei Skool nichts an — weder
Zahlungsmethoden noch Kündigung.

**Anmeldung mit Google:** Wer sich bei Skool sonst „Mit Google“ anmeldet, wird im Anmeldefenster des
Programms womöglich von Google blockiert („Dieser Browser oder diese App ist möglicherweise nicht
sicher“). Dann bei Skool mit **E-Mail und Passwort** anmelden. Hast du noch kein Skool-Passwort,
leg vorher in deinem normalen Browser eins fest (bei der Skool-Anmeldung über „Passwort vergessen“).
## Xentra

Xentra zeigt die Rechnungen unter *Abrechnung → Rechnungen*: Datum, Beschreibung, Betrag, Status und
ein Knopf „PDF herunterladen“. Das Programm drückt diesen Knopf für jede Zeile — wie du es mit der
Maus tun würdest —, lädt das PDF und speichert es als
`xentra/<Jahr>/<Datum>_xentra_<Rechnungsnummer>.pdf`. Die Beschreibung kommt absichtlich nicht in den
Dateinamen (bei Provisionen stehen dort Gastnamen). Am Ende vergleicht es, ob so viele Rechnungen
vorliegen, wie die Liste zeigt.

Das Programm **liest nur und lädt herunter**. Angeklickt werden nur der Reiter „Rechnungen“ und die
Knöpfe „PDF herunterladen“ — nichts an Abo, Zahlungsmethode oder Einstellungen. Damit es merkt, was
schon geholt ist, drückt es bei jedem Lauf alle Download-Knöpfe einmal; geladen und gespeichert wird
aber nur, was neu ist.

## Benutzen

Doppelklick auf **„Belege holen“**: auf dem Mac `Start Mac/Belege holen.command`, unter Windows
`Start Windows/Belege holen.cmd`.

- **Enter** = los
- **E** = Einstellungen:
  - **1** = Einstellungen ändern (die Fragen von oben noch einmal)
  - **2** = Fehlende Dateien neu holen (siehe unten)
- **Q** = beenden

Während des Abrufs musst du nichts tun und kannst den Rechner normal weiterbenutzen.

**Läuft die Anmeldung mittendrin ab** (Airbnb verlangt manchmal schnell eine neue Anmeldung),
meldet das Programm das in der Zusammenfassung. Beim nächsten Start kommt das Anmeldefenster, und
der Rest wird nachgeholt.

**Eine Datei noch einmal holen:** Einfach löschen reicht nicht — das Protokoll weiß, dass sie schon
geholt wurde. Stattdessen beim Start **E** und dann **2 „Fehlende Dateien neu holen“** wählen. Dann
kommt alles wieder, was im Protokoll steht, aber im Belegordner fehlt — soweit Airbnb es noch anbietet
(die letzten 12 Monate).

## Wo was liegt

| Was | Wo |
|---|---|
| Deine Belege | der Belegordner, den du beim Einrichten angegeben hast |
| Einstellungen | Mac: `~/Library/Application Support/belegabruf/einstellungen.toml` · Windows: `%APPDATA%\belegabruf\einstellungen.toml` |
| Anmeldungen (Browserprofile) | im selben Ordner unter `profile/` — **darf man jederzeit löschen** |
| Protokolle (was schon geholt ist) | im selben Ordner unter `protokolle/<anbieter>/<konto>.csv` — **nie löschen** |

Die Einstellungsdatei ist eine Textdatei mit Erklärungen und lässt sich mit jedem Texteditor
ändern. Ein Konto lässt sich dort mit `aktiv = "nein"` vorübergehend ausschalten.

Der Ordner `profile/` enthält deine eingeloggten Sitzungen — **wie ein offener Browser, in dem du
angemeldet bist.** Gib ihn nicht weiter und leg ihn nicht in eine Cloud-Freigabe. Zum Abmelden
reicht es, ihn zu löschen; beim nächsten Start kommt dann das Anmeldefenster.

Der Ordner `protokolle/` dagegen **bitte nie löschen.** Darin steht, was schon geholt wurde. Ohne
ihn holt das Programm beim nächsten Lauf alle 12 Monate noch einmal — und wer die Belege schon
weitergegeben hat, hätte sie dann doppelt in der Buchhaltung.

**Umstieg von Version 1.0:** Dort lag das Protokoll als `protokoll.csv` im Belegordner. Beim ersten
Start von Version 1.1 wird es automatisch übernommen und danach in `protokoll.csv.uebernommen`
umbenannt (nicht gelöscht). Danach kannst du die alte Datei wegwerfen.

## Neue Version installieren (Update)

Beim Start steht ein Hinweis, wenn es eine neuere Version gibt. Dann:

1. Den **alten Ordner `belegabruf-v…` komplett löschen** (mit Start-Ordnern und `programm`).
2. Die neue ZIP-Datei von [Neueste Version](https://github.com/balazskinal/belegabruf/releases/latest) laden und auspacken.
3. „Einrichten“ doppelklicken (lädt eventuell neue Bausteine; deine Antworten bleiben als Vorschlag stehen).

Einstellungen, Anmeldungen, Protokolle und Belege bleiben dabei erhalten — sie liegen nicht im
Programmordner.
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

Im Ordner `programm` (mit installiertem [uv](https://docs.astral.sh/uv/)):

```bash
uv run belege                                   # wie Doppelklick
uv run belege einrichten
uv run belege pruefen --json                    # sind die Konten angemeldet?
uv run belege anmelden --quelle airbnb --konto privat
uv run belege holen --quelle airbnb --json      # unbeaufsichtigt, öffnet nie ein Fenster
uv run belege holen --fehlende                  # dazu Fehlendes neu holen
```

`belege holen` gibt mit `--json` ein maschinenlesbares Ergebnis aus (Fortschritt geht nach stderr).
Exit-Code: 0 = alles gut, 2 = Anmeldung nötig oder abgelaufen, 1 = Fehler. So lassen sich die
Bausteine später auch aus einer Automatisierung (z. B. n8n) aufrufen.

### Aufbau

```
Start Mac/, Start Windows/   Startdateien (wechseln nach programm/ und rufen "belege" auf)
programm/
  pyproject.toml, uv.lock    Abhängigkeiten (Python, Playwright, PyMuPDF)
  tests/
  belegabruf/
    cli.py            Kommandozeile und Ablauf beim Doppelklick
    ablauf.py         Gerüst: prüfen, anmelden lassen, holen, abliefern
    quellen/          ein Baustein je Anbieter: airbnb.py, skool.py, xentra.py
      basis.py        die feste Schnittstelle für Bausteine
    ziele/            wohin Belege geliefert werden (Version 1: ordner.py)
    protokoll.py      Protokoll je Anbieter und Konto — entscheidet, was schon geholt ist
    pruefung.py       nie eine Anmelde-, 404- oder leere Seite als Beleg speichern
```

Ein **Baustein (Quelle)** kann genau drei Dinge: `sitzung_pruefen()`, `anmelden_lassen()` und
`belege_holen()`. Er speichert nichts selbst, sondern übergibt jeden Beleg an die **Ziele**. Das
Ziel „ordner“ legt Dateien ab; weitere Ziele (z. B. Upload an eine Buchhaltungssoftware) kommen als
eigene Datei in `ziele/` dazu, ohne dass sich die Quellen ändern.

Tests (im Ordner `programm`): `uv run --group dev pytest`

### Neue Bausteine beitragen

Neue Bausteine (z. B. für einen weiteren Anbieter) bitte als **Pull Request**. Gemergt wird **nur
vom Maintainer**. Ein Baustein arbeitet mit den angemeldeten Sitzungen der Nutzer — deshalb wird
jeder fremde Beitrag vor einem Release vollständig geprüft. Regeln für Bausteine:

- kein Passwort, kein Token im Code; angemeldet wird immer vom Menschen im sichtbaren Fenster
- menschliches Tempo (`browser.pause()` zwischen Abrufen)
- Inhalt prüfen, bevor etwas als Beleg gilt (`pruefung.py`)
- keine personenbezogenen Daten Dritter (z. B. Gastnamen) in Dateinamen, Protokoll oder Ausgabe

### Neue Version veröffentlichen (Maintainer)

Version in `programm/pyproject.toml` erhöhen, committen, dann Tag setzen und pushen:

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
