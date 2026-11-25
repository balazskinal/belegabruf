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
   `Start Windows/`.
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

Die übrigen Anmerkungen (Haken „Belege holen“, Einrichtung ohne Headless Shell, Rückmeldung am
Speichern-Knopf, Absender vorbelegt, Port springt mit der Verschlüsselung) ändern keine Entscheidung.

## Folgen

Windows-Test ist Pflicht, bevor 2.0.0 veröffentlicht wird.
