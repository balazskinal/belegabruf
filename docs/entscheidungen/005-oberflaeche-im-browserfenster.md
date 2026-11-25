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

## Folgen

Windows-Test ist Pflicht, bevor 2.0.0 veröffentlicht wird.
