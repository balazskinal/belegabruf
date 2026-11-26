"""Inhaltsprüfung: Nur echte Belege werden gespeichert.

Ohne diese Prüfung landen Anmeldeseiten, 404-Seiten oder leere Seiten als
"Rechnung" im Ordner — das ist der wichtigste Stolperstein beim Abruf.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

import pymupdf

ANMELDE_MERKMALE = (
    "einloggen", "log in", "anmelden", "passwort", "password", "registrieren", "sign up",
)
FEHLER_MERKMALE = (
    "404", "seite nicht gefunden", "page not found", "wir können die seite", "we can't seem to find",
    "nicht gefunden", "something went wrong", "etwas ist schiefgelaufen",
)


#: Größer wird kein Beleg gespeichert (Schutz vor kaputten oder untergeschobenen Dateien).
MAX_PDF_BYTES = 20 * 1024 * 1024


def zu_gross(inhalt: bytes | None) -> bool:
    return inhalt is not None and len(inhalt) > MAX_PDF_BYTES


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


# ── Adressen: Belege nur vom Anbieter selbst ─────────────────────────────────


class FremdeAdresse(Exception):
    """Eine Belegadresse liegt nicht bei einem erlaubten Host. Die Meldung nennt nur den Host
    (nie Pfad oder Query — dort stehen Sitzungsschlüssel und befristete Signaturen)."""

    def __init__(self, url: str):
        self.herkunft = herkunft(url)
        super().__init__(f"Adresse nicht vom Anbieter ({self.herkunft}), nicht geholt")


def host_von(url: str) -> str:
    """Nur der Hostname einer Adresse, für Meldungen. „?“, wenn keiner zu erkennen ist."""
    try:
        return (urlsplit(str(url or "")).hostname or "?")[:80]
    except ValueError:
        return "?"


def herkunft(url: str) -> str:
    """Schema, Host und Port einer Adresse für Meldungen („http://admin.booking.com“,
    „https://andere.example:8443“) — nie Benutzerangaben, Pfad oder Query."""
    try:
        teile = urlsplit(str(url or ""))
        port = f":{teile.port}" if teile.port else ""
    except ValueError:
        return "?"
    return f"{teile.scheme or '?'}://{host_von(url)}{port}"[:100]


def adresse_erlaubt(url: str, hosts: Iterable[str], endungen: Iterable[str] = ()) -> bool:
    """True nur für ``https://<host>/…`` mit ``host`` genau aus ``hosts`` (oder, wenn ein Anbieter
    wechselnde Unterdomains nutzt, ``<etwas>.<endung>`` mit einer eng gefassten ``endung``).

    Abgelehnt werden: anderes Schema (auch http), Benutzerangaben (``user@host``), ein anderer
    Port als 443, Hosts mit Zeichen außerhalb von a–z, 0–9, Punkt und Bindestrich (z. B. ein
    Vollbreiten-„＠“) und alles, was sich nicht sauber lesen lässt."""
    try:
        teile = urlsplit(str(url or ""))
        port = teile.port
    except ValueError:
        return False
    if teile.scheme != "https" or "@" in teile.netloc or "＠" in teile.netloc:
        return False
    if teile.username is not None or teile.password is not None or port not in (None, 443):
        return False
    host = (teile.hostname or "").lower()
    if not re.fullmatch(r"[a-z0-9.-]+", host) or host.startswith(".") or host.endswith(".") or ".." in host:
        return False
    erlaubt = {h.lower() for h in hosts}
    return host in erlaubt or any(host.endswith("." + e.lower().lstrip(".")) for e in endungen)


def adresse_pruefen(url: str, hosts: Iterable[str], endungen: Iterable[str] = ()) -> str:
    """Wie ``adresse_erlaubt``, wirft aber ``FremdeAdresse``. Gibt die Adresse zurück."""
    if not adresse_erlaubt(url, hosts, endungen):
        raise FremdeAdresse(url)
    return url
