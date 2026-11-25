# ADR-005: Bedienoberfläche im Browserfenster statt Terminal

- **Datum:** 25.11.2026
- **Status:** ✅ gilt · 🚧 gebaut als **Version 2.0.0** (PR offen) · offene Punkte entschieden 25.11.2026

## Kontext

Das Programm startet per Doppelklick, läuft aber im Terminal: Einrichten ist ein Frage-Antwort-Dialog,
die Zusammenfassung ist Terminaltext. Für viele Nutzer ist das die größte Hürde. Für die Anmeldungen
bringt das Programm ohnehin ein eigenes Chromium mit (Playwright, eigenes Profil je Konto).

## Entscheidung

1. **Die Bedienung zieht ins Browserfenster, das das Programm schon hat.** Doppelklick öffnet das
   Playwright-Chromium; der erste Tab ist die Bedienseite. Nicht der Standardbrowser des Nutzers.
2. **Inhalt:** Einstellungen als Formular (Belegordner, Konten, Ziele, Mailserver, Steuerregel) · je
   Konto „Anmelden“ mit Zustand · „Belege holen“ mit Fortschritt · Zusammenfassung als Liste · Hinweis auf
   neue Version.
3. **Anmeldungen als neuer Tab im selben Fenster**, mit dem Profil des Kontos wie bisher.
4. **Zugangsdaten** werden in ein verdecktes Feld getippt und gehen direkt in den Passwortspeicher
   (ADR-003). Sie erscheinen nie auf der Seite, in Antworten des lokalen Servers oder in Logs.
5. **Nur lokal:** Der Server der Bedienseite lauscht nur auf `127.0.0.1`, auf einem freien Port, mit
   einem Zufallsschlüssel in der Adresse; Anfragen ohne Schlüssel oder mit fremdem `Host`-Kopf werden
   abgelehnt.
6. **Das CLI bleibt darunter.** Die Oberfläche ruft dieselben Bausteine auf; `--json` bleibt.
7. Weiter **kein Dienst**, kein Hosting, keine Konten.

## Verworfen

- **Standardbrowser des Nutzers:** Die Anmeldungen bräuchten trotzdem das zweite Fenster.
- **Eigene Fenster-Oberfläche (Tkinter o. Ä.):** auf dem Mac unzuverlässig, doppelte Pflege.
- **Signierte App:** würde das Terminal ganz beseitigen, kostet aber Entwicklerkonten und Pflege.

## Entschieden 25.11.2026 (Balazs)

1. **Terminalfenster:** bleibt offen, klein bzw. minimiert, mit dem gut sichtbaren Satz „Nicht schließen,
   solange Belegabruf läuft“. Es wird nicht versteckt.
2. **Terminal-Menü bleibt.** Die Startdatei „Belege holen“ öffnet künftig die Oberfläche; das bisherige
   Menü gibt es weiter über eine eigene Startdatei „Belegabruf (Terminal)“ in `Start Mac/` und
   `Start Windows/` (seit Nachtrag 8–10: ein Starter „Belegabruf“, das Menü unter `Fehlersuche/`).
3. **Sprache:** nur Deutsch.
4. **Versionen:** Die Oberfläche wird **2.0.0**; der sevDesk-API-Weg (PR #3) kommt später als **2.1.0**.

## Nachtrag 25.11.2026: Anmeldung im eigenen Fenster statt als Tab

Punkt 3 der Entscheidung („Anmeldungen als neuer Tab im selben Fenster“) lässt sich so nicht bauen: Die
Anmeldung eines Kontos lebt in dessen **dauerhaftem Browserprofil**, und jedes dauerhafte Profil ist bei
Chromium eine **eigene Browser-Instanz** — ein Tab im Fenster der Bedienseite kann dieses Profil nicht
benutzen. Deshalb öffnet „Anmelden“ je Konto ein **eigenes Fenster** mit dem Profil des Kontos, wie bisher.
Die Bedienseite zeigt den Zustand und erkennt die Anmeldung von selbst. Abruf und Prüfen laufen wie bisher
unsichtbar im Hintergrund. Die Bedienseite selbst läuft als App-Fenster (ohne Adressleiste) mit einem
eigenen, leeren Profil (`profile/_bedienseite`).

## Nachtrag 25.11.2026: Anmerkungen aus der Neuinstallation (Balazs)

Balazs hat 2.0.0 als komplette Neuinstallation getestet. Drei Anmerkungen ändern Entscheidungen bzw.
die Datenhaltung:

1. **Kontoname optional.** Ein Konto braucht nur den Anbieter. Ein Name ist erst Pflicht, wenn es beim
   selben Anbieter ein zweites Konto gibt (Datei, Oberfläche und Terminal-Einrichtung prüfen gleich).
   Dafür trennt das Programm **Kennung** und **Name**: An der Kennung hängen Browserprofil (Anmeldung),
   Protokoll und Zustand; der Name ist nur Anzeige. Ein Konto ohne Namen hat die Kennung `standard` und
   heißt in der Anzeige nur „Airbnb“. Bei bisherigen Konten mit Namen sind Kennung und Name gleich —
   Profil- und Protokollpfade ändern sich nicht. Wird ein Konto umbenannt (z. B. das bisher namenlose,
   wenn ein zweites dazukommt), behält es seine Kennung; die Einstellungsdatei schreibt sie dann als
   `kennung = "…"` dazu. Sonst ginge mit dem Umbenennen die Anmeldung verloren und das Protokoll
   begänne von vorn (Rechnungen kämen doppelt).
2. **Zwei Reiter** statt einer langen Seite: „Belege holen“ (Konten mit Anmeldestatus, Anmelden/Prüfen,
   Holen mit Fortschritt, Zusammenfassung) und „Einstellungen“ (Belegordner, Konten, Mail, Passwort).
   Erster Start ohne Konten öffnet „Einstellungen“, sonst „Belege holen“. Wechsel jederzeit; während
   eines Vorgangs ist nur Speichern gesperrt. Ohne Framework, die CSP mit Nonce bleibt; Tastatur nach
   WAI-ARIA (Tabs mit Pfeiltasten, Pos1/Ende).
3. **Ablage nach Monat wählbar:** Einstellung `ablage = "jahr"` (Standard, wie bisher:
   `<anbieter>/<JJJJ>/`) oder `"monat"` (`<anbieter>/<JJJJ>/<MM>/`), maßgeblich ist das Rechnungsdatum;
   der Dateiname bleibt mit Datum vorne. Die Umstellung gilt nur für neue Belege — nichts wird
   verschoben. Der Duplikatschutz hängt weiter am Protokoll (Schlüssel), nicht am Pfad; das Protokoll
   speichert je Beleg den Pfad, unter dem er abgelegt wurde. Die **Airbnb-Monatsübersichten** bleiben in
   `airbnb/kontrolle/`: Sie heißen schon `<JJJJ-MM>_…`, sind Kontrollberichte und keine Belege, und ein
   Unterordner je Monat mit genau einer Datei brächte nichts.

Die übrigen Anmerkungen (Einrichtung ohne Headless Shell, Rückmeldung am Speichern-Knopf, Absender
vorbelegt, Port springt mit der Verschlüsselung) ändern keine Entscheidung.

### Nachtrag (Balazs, 25.11.2026)

4. **Haken je Konto im Reiter „Belege holen“** statt in den Einstellungen. „Belege holen“ holt nur
   angehakte Konten; ein Klick speichert den Haken sofort (als `aktiv`), ohne „Einstellungen speichern“.
   Ohne angehaktes Konto ist „Belege holen“ gesperrt, mit Hinweis. „Alle Anmeldungen prüfen“ prüft
   alle Konten. Das Einstellungsformular ändert den Haken nicht (sonst überschriebe ein älterer
   Formularstand einen eben gesetzten Haken).
5. **Zeitraum je Konto („Belege ab“), schon in 2.0.0:** `belege_ab = "alle"` (Vorgabe, auch für alte
   Dateien ohne den Schlüssel), `"letzter-monat"`, `"letzte-3-monate"`, `"letzte-12-monate"` oder ein
   Datum `"TT.MM.JJJJ"`. Relativ heißt ab dem 1. des Monats vor N Monaten, gerechnet am Tag des Laufs.
   Gefiltert wird beim Lesen der Rechnungsliste, also **vor** dem Download: Airbnb lädt
   Monatsübersichten von Monaten vor dem Zeitraum gar nicht und lässt ältere Zeilen aus; Skool öffnet
   ältere Rechnungen nicht; Xentra klickt ältere Zeilen nicht an. Übersprungenes kommt **nicht** ins
   Protokoll — wird der Zeitraum erweitert, holt der nächste Lauf es nach. Belege ohne erkanntes Datum
   werden geholt (lieber einmal zu viel als einer zu wenig). Die Zusammenfassung (auch CLI und `--json`)
   nennt „übersprungen (älter als Zeitraum)“; bei Airbnb zusätzlich, wie viele Monate nicht angesehen
   wurden (deren Rechnungen kennt das Programm dann nicht und kann sie nicht zählen).
6. **Mailanbieter als Auswahl:** GMX, WEB.DE, Gmail, Outlook.com, Microsoft 365, IONOS, STRATO,
   all-inkl.com, iCloud und „Anderer“. Die Auswahl füllt Server, Port und Verschlüsselung vor; die
   Felder bleiben änderbar, eine Handänderung springt auf „Anderer“. Gespeichert werden weiter nur
   `server`, `port`, `verschluesselung`; der Anbieter wird beim Laden erkannt. Die Werte stammen von den
   offiziellen Hilfeseiten (Stand 25.11.2026, Quellen als Kommentar in `seite.html`). Ehrlich vermerkt:
   **Outlook.com** verlangt OAuth2, die Anmeldung mit Passwort klappt dort voraussichtlich nicht;
   bei **Microsoft 365** muss der Admin SMTP AUTH erlauben, und Microsoft schaltet die
   Passwort-Anmeldung dafür Ende Dezember 2026 standardmäßig ab. OAuth2 baut das Programm nicht ein
   (bräuchte eine registrierte App beim Anbieter).
7. **Headless Shell ganz weg:** Alles startet Chromium mit `channel="chromium"`, auch die
   Versions-Probe; die Einrichtung lädt mit `--no-shell`. Geprüft mit der ganzen Testsuite in einem
   Browserordner ohne Shell. FFmpeg bleibt.

### Nachtrag (Balazs, 25.11.2026): ein Starter je System

8. **„Belegabruf“ ersetzt „Einrichten“ und „Belege holen“** (`Start Mac/Belegabruf.command`,
   `Start Windows/Belegabruf.cmd`). Beim Doppelklick, jeder Schritt nur, wenn nötig: uv fehlt → uv holen;
   `.venv` fehlt oder `uv.lock`/`pyproject.toml` ist neuer als der letzte Sync → `uv sync --no-dev`;
   Chromium für diese Playwright-Version fehlt → `playwright install --no-shell chromium`; dann die
   Bedienseite. Die Prüfung (`python -m belegabruf.startpruefung`) liest nur die `browsers.json` von
   Playwright und schaut nach dem fertig geladenen Browserordner — sie startet Playwright nicht. Klappt
   `uv sync` nicht, wird die halbe `.venv` weggeräumt; der nächste Doppelklick versucht es erneut.
   Erster Start und Update sind damit gleich: **ZIP auspacken, „Belegabruf“ doppelklicken.**
9. Was „Einrichten“ abgefragt hat (Belegordner, Konten, Mail, Passwort), geht im Reiter „Einstellungen“;
   der erste Start ohne Konten öffnet ihn. Neu dafür in der Seite: **„Passwort löschen“** (nur Einträge
   mit Dienst `belegabruf`, wie im Terminal). Nur im Terminal bleibt das Ändern des Eintrags im
   Passwortspeicher (`passwort_eintrag`) über `belege einrichten`.
10. **„Belegabruf (Terminal)“ bleibt**, liegt aber im Unterordner `Fehlersuche/`, damit oben nur ein
    Starter liegt. Er richtet nichts ein, sondern verweist auf „Belegabruf“, falls noch nichts da ist.

## Folgen

Windows-Test ist Pflicht, bevor 2.0.0 veröffentlicht wird.
