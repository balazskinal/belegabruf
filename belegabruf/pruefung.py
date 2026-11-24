"""Inhaltsprüfung: Nur echte Belege werden gespeichert.

Ohne diese Prüfung landen Anmeldeseiten, 404-Seiten oder leere Seiten als
"Rechnung" im Ordner — das ist der wichtigste Stolperstein beim Abruf.
"""

from __future__ import annotations

import re

import pymupdf

ANMELDE_MERKMALE = (
    "einloggen", "log in", "anmelden", "passwort", "password", "registrieren", "sign up",
)
FEHLER_MERKMALE = (
    "404", "seite nicht gefunden", "page not found", "wir können die seite", "we can't seem to find",
    "nicht gefunden", "something went wrong", "etwas ist schiefgelaufen",
)


def ist_pdf(inhalt: bytes) -> bool:
    return inhalt[:5] == b"%PDF-"


def pdf_text(inhalt: bytes) -> str:
    if not ist_pdf(inhalt):
        return ""
    try:
        with pymupdf.open(stream=inhalt, filetype="pdf") as dok:
            return "\n".join(seite.get_text() for seite in dok)
    except Exception:  # noqa: BLE001 - kaputtes PDF
        return ""


def seite_ist_beleg(text: str, pflicht: list[str]) -> str | None:
    """Prüft einen Seiten- oder PDF-Text. Gibt None zurück, wenn alles passt,
    sonst den Grund, warum es kein Beleg ist."""
    sauber = re.sub(r"-\s+", "-", " ".join(text.split()))  # umgebrochene Nummern zusammenfügen
    if len(sauber) < 80:
        return "leere Seite"
    fehlend = [p for p in pflicht if p and p not in sauber]
    if fehlend:
        klein = sauber.lower()
        if any(m in klein for m in FEHLER_MERKMALE):
            return "Fehlerseite (z. B. 404)"
        if any(m in klein for m in ANMELDE_MERKMALE):
            return "Anmeldeseite"
        return "erwartete Angaben fehlen"
    return None
