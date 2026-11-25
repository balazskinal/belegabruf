# ADR-005: Bedienoberfläche im Browserfenster statt Terminal

- **Datum:** 25.11.2026
- **Status:** ✅ Richtung gilt · 📋 eingeplant als **Version 2.0.0** · drei Punkte offen (unten)

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

## Offen (vor dem Bau klären)

1. **Terminalfenster:** klein bzw. minimiert mit Hinweis „nicht schließen“, oder versteckt (Beenden nur
   über die Bedienseite)?
2. **Terminal-Menü** neben der Oberfläche behalten (Fehlersuche) oder entfernen?
3. **Sprache:** nur Deutsch oder Deutsch/Englisch?

## Folgen

Windows-Test ist Pflicht, bevor 2.0.0 veröffentlicht wird.
