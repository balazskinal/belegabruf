# Roadmap

Stand: 25.11.2026. Begründungen stehen in den [Entscheidungen](entscheidungen/README.md).

## Veröffentlicht

- **1.0.0** — Airbnb-Einzelrechnungen per Doppelklick in einen lokalen Ordner (ADR-001)
- **1.1.0** — Das Protokoll entscheidet, liegt im Datenordner (ADR-002)
- **1.2.0** — Quellen Xentra (Abo- und Provisionsrechnungen aus „Abrechnung → Rechnungen“) und Skool
  (Rechnungen aus dem Zahlungsverlauf, immer als helles PDF). Beide gegen echte Konten durchgespielt.

## In Arbeit

- [ ] **1.3.0 — Ziel Mail:** jede neue Rechnung per Mail an eine oder mehrere Belegadressen, vom
      eigenen Postfach (ADR-004)
- [ ] **1.4.0 — Ziel sevDesk über die API:** Entwurf mit PDF, Datum, Rechnungsnummer (ADR-004)

## Danach: 2.0.0 — Bedienoberfläche im Browserfenster (ADR-005)

**Fertig heißt:**
1. Doppelklick öffnet ein Browserfenster mit der Bedienseite; niemand tippt im Terminal.
2. Ersteinrichtung komplett über die Seite, Zugangsdaten in den Passwortspeicher.
3. Je Konto „Anmelden“ öffnet einen Tab; die Seite zeigt danach „angemeldet“.
4. „Belege holen“ zeigt Fortschritt und dieselbe Zusammenfassung wie das CLI.
5. Kein Geheimnis auf der Seite, in Server-Antworten oder Logs (Test vorhanden).
6. Der lokale Server ist nur mit Schlüssel von `127.0.0.1` erreichbar (Test vorhanden).
7. Auf einem Mac und einem Windows-Rechner nach Anleitung durchgespielt.

**Schritte:**
- [ ] Offene Punkte aus ADR-005 klären (Terminalfenster, Terminal-Menü, Sprache)
- [ ] Gerüst: lokaler Server mit Schlüssel, Bedienseite als erster Tab, Startdateien öffnen das Fenster
- [ ] Einrichten als Formular inkl. Zugangsdaten
- [ ] Anmelden je Konto mit Zustandsanzeige
- [ ] Belege holen mit Fortschritt und Zusammenfassung
- [ ] Alle Szenarien durchspielen, Windows-Test, veröffentlichen

## Später / Ideen

- **Lexware Office** über die API, sobald jemand mit echtem Konto testen kann
- **Weitere Quellen** — Vorschläge willkommen (Issue oder Pull Request): Welche Anbieter schicken keine
  Rechnung per Mail?
- **Windows-Test** durch jemanden, der es nach Anleitung ausprobiert
- **n8n-Variante** mit denselben Bausteinen (CLI mit `--json`)
