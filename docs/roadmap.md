# Roadmap

Stand: 26.11.2026. Begründungen stehen in den [Entscheidungen](entscheidungen/README.md).

## Veröffentlicht

- **1.0.0** — Airbnb-Einzelrechnungen per Doppelklick in einen lokalen Ordner (ADR-001)
- **1.1.0** — Das Protokoll entscheidet, liegt im Datenordner (ADR-002)
- **1.2.0** — Quellen Xentra (Abo- und Provisionsrechnungen aus „Abrechnung → Rechnungen“) und Skool
  (Rechnungen aus dem Zahlungsverlauf, immer als helles PDF). Beide gegen echte Konten durchgespielt.
- **1.3.0** — Ziel Mail: jede neue Rechnung per Mail an eine oder mehrere Belegadressen, über das
  eigene Postfach; Passwort im Passwortspeicher (ADR-003, ADR-004)
- **2.0.0** — Bedienoberfläche im Browserfenster (ADR-005): Einrichten, Anmelden und Belege holen
  ohne Terminal; ein Starter je System; Zeitraum „Belege ab“ je Konto; Ablage nach Jahr/Monat;
  Mailanbieter als Auswahl. Auf dem Mac durchgespielt, Windows noch offen (#11).

## Geplant

Die Planung steht in den [Meilensteinen](https://github.com/balazskinal/belegabruf/milestones);
je Vorhaben ein Issue. Die Termine sind Ziele, keine Zusagen.

| Version | Inhalt | Ziel |
|---|---|---|
| [2.0.1](https://github.com/balazskinal/belegabruf/milestone/2) | Windows-Test (#11) | 15.12.2026 |
| [2.1.0](https://github.com/balazskinal/belegabruf/milestone/3) | Ziel sevDesk über die API (#12, PR #3) | 23.12.2026 |
| [2.2.0](https://github.com/balazskinal/belegabruf/milestone/4) | Quelle Booking.com (#13) | 31.01.2027 |
| [2.3.0](https://github.com/balazskinal/belegabruf/milestone/5) | Ziel Lexware Office (#14) | 28.02.2027 |
| [Später](https://github.com/balazskinal/belegabruf/milestone/1) | n8n-Weg mit `--json` (#15) | — |

**Weitere Quellen:** Vorschläge willkommen, als Issue oder Pull Request. Gesucht sind Anbieter, die
keine Rechnung per Mail schicken.
