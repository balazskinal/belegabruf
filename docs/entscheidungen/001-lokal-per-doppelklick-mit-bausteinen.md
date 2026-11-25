# ADR-001: Lokal per Doppelklick, nachbaubar, mit Bausteinen

- **Datum:** 24.11.2026
- **Status:** ✅ gilt · umgesetzt ab Version 1.0.0

## Kontext

Viele Rechnungen gibt es nur im eingeloggten Konto eines Portals, ohne Schnittstelle und ohne Versand
per Mail. Bei Airbnb betrifft das die Rechnungen über die Servicegebühren; Airbnb zeigt außerdem nur die
**letzten 12 Monate**. Wer sie für die Buchhaltung braucht, lädt sie regelmäßig einzeln herunter.

Unter Gastgebern war das ein häufig genanntes Ärgernis. Ziel: ein Werkzeug, das jeder für sich selbst
betreibt und nachbauen kann.

## Entscheidung

1. **Nachbaubar für alle, kein Dienst.** Niemand betreibt das Werkzeug für andere, niemand hält fremde
   Sitzungen. Jeder betreibt seine eigene Kopie.
2. **Läuft lokal auf dem eigenen Rechner**, ohne Server. **Mac und Windows mit demselben Code** (Python,
   Playwright, `uv`); nur die Startdateien (`Start Mac/`, `Start Windows/`) unterscheiden sich.
3. **Start per Doppelklick, kein Zeitplan.** Ablauf: alle Konten prüfen → **erst alle Anmeldefenster**
   (angemeldet wird immer vom Menschen, kein Passwort im Code) → dann Abruf unbeaufsichtigt und
   nacheinander → Zusammenfassung. Läuft eine Sitzung mittendrin ab, wird das gemeldet und beim nächsten
   Lauf nachgeholt. Warnung, wenn der letzte Lauf lange zurückliegt (12-Monats-Grenze bei Airbnb).
4. **Einzelrechnungen sind der Kern.** Übersichten (z. B. Airbnbs Monats-PDF) dienen nur der Kontrolle,
   ob alles geholt ist. Eine Anmelde-, 404- oder leere Seite wird nie als Rechnung gespeichert.
5. **Bausteine.** Jede Quelle ist eine Datei mit denselben drei Fähigkeiten: Sitzung prüfen, anmelden
   lassen, Belege holen. **Mehrere Konten je Quelle** sind möglich. Es läuft nur, was eingetragen und
   eingeschaltet ist.
6. **Abholen und Abliefern getrennt.** Quellen holen, **Ziele** liefern ab (Ordner, später Mail und
   Buchhaltungsprogramme, siehe ADR-003). Die Bausteine sind über die Kommandozeile mit JSON-Ausgabe
   aufrufbar, damit ein späterer Umzug auf n8n sie unverändert übernehmen kann.
7. **Ablage ohne Namen von Gästen oder Kunden** im Dateinamen, z. B.
   `<Belegordner>/airbnb/<Jahr>/<Rechnungsdatum>_<Buchungscode>_<Rechnungsnummer>.pdf`; Übersichten unter
   `kontrolle/`.
8. **Einrichtung fragt beim ersten Start ab** (Anbieter, Konten, Belegordner, Ziele) und schreibt eine
   kommentierte Einstellungsdatei. Ändern durch erneutes „Einrichten“ oder in der Datei.
9. **Eigenes öffentliches Repo**, MIT-Lizenz. Auslieferung über **GitHub Releases**: ein ZIP je Version,
   gebaut von einer GitHub Action. Keine Installationsdatei (ohne Signatur warnen beide Systeme zu laut).
10. **Update:** alten Programmordner löschen, neues ZIP auspacken. **Kein Selbst-Update** — beim Start nur
    ein Hinweis auf eine neuere Version.
11. **Neue Bausteine per Pull Request**, gemergt vom Betreuer des Repos nach vollständiger Prüfung: Ein
    Baustein arbeitet mit den angemeldeten Sitzungen der Nutzer.

## Verworfen

- **n8n mit Playwright auf einem Server:** für andere kaum nachbaubar; Anmeldung von einer Server-Adresse
  scheitert an Bot-Erkennung und Zwei-Faktor. Bleibt ein Weg für später, mit denselben Bausteinen.
- **Nur ein KI-Skill:** läuft nicht ohne KI-Zugang und kostet je Lauf.
- **Ein Dienst für andere:** Auftragsverarbeitung, Haftung, Support, fremde Konten.
- **Namen von Gästen im Dateinamen:** Datenschutz.
- **Ein-Klick-Selbst-Update:** fehleranfällig, besonders unter Windows.

## Folgen

- README: Abruf der eigenen Rechnungen aus dem eigenen Konto in menschlichem Tempo; die
  Nutzungsbedingungen der Portale prüft jeder selbst.
- Windows gilt als ungetestet, bis jemand es nach Anleitung durchgespielt hat.
