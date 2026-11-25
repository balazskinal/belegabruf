# Belegabruf

Holt Rechnungen, die es nur im eingeloggten Konto eines Anbieters gibt, per Doppelklick auf den
eigenen Rechner. **Es kann Airbnb:** die Rechnungen über die Airbnb-Servicegebühren für
Gastgeber, jede Buchung als eigenes PDF. **Seit Version 2** lädt es neue Rechnungen auf Wunsch
zusätzlich als Entwurf nach **sevDesk** hoch.

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

5. Ist **sevDesk** eingeschaltet, lädt es jede neue Rechnung dort als **Entwurf** hoch (siehe
   [Upload nach sevDesk](#upload-nach-sevdesk)). Die Datei bleibt trotzdem im Belegordner.

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
   - Welche Anbieter (zurzeit nur Airbnb)
   - Ein Name für dein Konto — nur für dich, z. B. „privat“. Hast du mehrere Airbnb-Konten
     (z. B. einen Zugang als Co-Gastgeber), kannst du mehrere eintragen; jedes bekommt seine eigene Anmeldung.
   - Der Belegordner (Vorschlag: `Dokumente/Belege`)
   - Ob die Rechnungen auch nach sevDesk sollen — dann fragt es nach dem API-Schlüssel (siehe unten)
6. Zum Schluss öffnet sich das Airbnb-Anmeldefenster. Melde dich an. Fertig.

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

## Upload nach sevDesk

Auf Wunsch lädt das Programm jede **neu geholte** Rechnung als **Entwurf** nach sevDesk hoch. Du
findest sie dort bei den Belegen als offenen Entwurf, mit dem PDF im Anhang.

**Was im Entwurf steht:** nur, was das Programm ohnehin weiß — Belegdatum, Rechnungsnummer (als
Belegnummer), Lieferant „Airbnb“ und die Steuerregel. **Betrag und Konto bleiben leer — die
ergänzt du in sevDesk**; sevDesk liest dabei nichts aus dem PDF aus. Gebucht wird nichts. Gutschriften
kommen genauso an, mit „(Gutschrift)“ hinter der Belegnummer.

**Einschalten:** „Einrichten“ doppelklicken und bei „Nach sevDesk hochladen?“ mit **j** antworten.
Dann fragt es nach der **Steuerregel**: sevDesk verlangt für jeden Entwurf eine, und welche passt,
hängt von deiner Buchhaltung ab. Deshalb gibt es keinen Vorschlag. Die Nummer findest du z. B. in der
Vorlage deines Lieferanten Airbnb in sevDesk; im Zweifel frag deine Steuerberatung. Danach fragt es
nach dem **API-Schlüssel** (in sevDesk unter *Einstellungen → Benutzer → API-Token*).
Beim Einfügen sieht man nichts — das ist Absicht. Der Schlüssel kommt in den **Passwortspeicher
deines Rechners** (Mac: Schlüsselbund, Windows: Anmeldeinformationsverwaltung) und **nie in eine
Datei**. In den Einstellungen steht nur, unter welchem Eintrag er liegt (Vorschlag:
`belegabruf/sevdesk`). Hast du schon einen Eintrag, kannst du den angeben. Austauschen oder löschen
ebenfalls über „Einrichten“. Auf dem Mac fragt der Schlüsselbund beim ersten Mal, ob das Programm den
Eintrag lesen darf — dort **„Immer erlauben“** wählen (nach einem Update kann die Frage wiederkommen).

**Alter Bestand:** Beim Einschalten gilt alles, was bis dahin geholt ist, als **schon in sevDesk**
und wird nicht hochgeladen. Hochgeladen wird nur, was danach neu dazukommt.

**Nie doppelt:** Das Protokoll merkt sich, was hochgeladen ist (mit der Beleg-ID aus sevDesk). Klappt ein Upload nicht (kein
Internet, falscher Schlüssel, sevDesk lehnt ab), bleibt der Beleg im Belegordner, die Zusammenfassung
zeigt die Meldung von sevDesk, und der **nächste Lauf versucht es erneut**. Kommt von sevDesk gar
keine Antwort, ist unklar, ob der Entwurf angelegt wurde. Dann schickt das Programm ihn **nicht** noch
einmal und sagt dir, welche Rechnung du in sevDesk nachsehen sollst.

**Was das Programm bei sevDesk darf:** Ein sevDesk-API-Schlüssel hat alle Rechte deines Benutzers —
einschränken lässt er sich nicht. Deshalb ruft das Programm **ausschließlich das Hochladen** auf:
Datei hochladen (`/Voucher/Factory/uploadTempFile`) und Entwurf anlegen
(`/Voucher/Factory/saveVoucher`); beim Einrichten einmal `/SevClient`, um den Schlüssel zu prüfen.
Es liest, ändert oder löscht sonst nichts. Jeder andere Aufruf wird im Programm verweigert, bevor er
das Netz erreicht (`programm/belegabruf/ziele/sevdesk.py`, Liste `ERLAUBT`).

## Wo was liegt

| Was | Wo |
|---|---|
| Deine Belege | der Belegordner, den du beim Einrichten angegeben hast |
| Einstellungen | Mac: `~/Library/Application Support/belegabruf/einstellungen.toml` · Windows: `%APPDATA%\belegabruf\einstellungen.toml` |
| Anmeldungen (Browserprofile) | im selben Ordner unter `profile/` — **darf man jederzeit löschen** |
| Protokolle (was schon geholt und hochgeladen ist) | im selben Ordner unter `protokolle/<anbieter>/<konto>.csv` — **nie löschen** |
| sevDesk-Schlüssel | im Passwortspeicher des Betriebssystems, nie in einer Datei |

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
Exit-Code: 0 = alles gut, 2 = Anmeldung nötig oder abgelaufen, nicht alles geholt oder nicht alles
nach sevDesk hochgeladen (später noch einmal), 1 = Fehler. So lassen sich die
Bausteine später auch aus einer Automatisierung (z. B. n8n) aufrufen.

### Aufbau

```
Start Mac/, Start Windows/   Startdateien (wechseln nach programm/ und rufen "belege" auf)
programm/
  pyproject.toml, uv.lock    Abhängigkeiten (Python, Playwright, PyMuPDF, keyring)
  tests/
  belegabruf/
    cli.py            Kommandozeile und Ablauf beim Doppelklick
    ablauf.py         Gerüst: prüfen, anmelden lassen, holen, abliefern
    quellen/          ein Baustein je Anbieter (Version 1: airbnb.py)
      basis.py        die feste Schnittstelle für Bausteine
    ziele/            wohin Belege geliefert werden: ordner.py, sevdesk.py
    protokoll.py      Protokoll je Anbieter und Konto — entscheidet, was schon geholt ist
    pruefung.py       nie eine Anmelde-, 404- oder leere Seite als Beleg speichern
```

Ein **Baustein (Quelle)** kann genau drei Dinge: `sitzung_pruefen()`, `anmelden_lassen()` und
`belege_holen()`. Er speichert nichts selbst, sondern übergibt jeden Beleg an die **Ziele**. Das
Ziel „ordner“ legt Dateien ab und ist immer dabei. Das Ziel „sevdesk“ lädt danach hoch, was laut
Protokoll noch nicht in sevDesk ist. Weitere Ziele (z. B. Lexware Office) kommen als eigene Datei in
`ziele/` dazu, ohne dass sich die Quellen ändern. Ziele mit API-Schlüssel lesen ihn nur über
`keyring` und rufen nur die Aufrufe zum Hochladen auf.

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
- **sevDesk:** Ein Entwurf ohne Betrag und Konto wird über die API angenommen (einmal mit einer
  echten Rechnung geprüft; dokumentiert ist es nicht). Eine automatische Belegerkennung wie beim
  Mail-Eingang gibt es über die API nicht.
- Weitere Bausteine und Ziele (z. B. Lexware Office) folgen in späteren Versionen.
