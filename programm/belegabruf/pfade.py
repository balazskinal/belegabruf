"""Wo Einstellungen, Sitzungen und Belege liegen.

Einstellungen und Browser-Sitzungen liegen immer im Benutzerordner des Systems,
nie im Programmordner: Wer das Programm aktualisiert (Ordner löschen, neues ZIP
auspacken), verliert dadurch weder Einstellungen noch Anmeldungen.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def starter() -> str:
    """Wie der Starter für dieses System heißt (liegt oben im ausgepackten Ordner)."""
    return "Belegabruf Windows" if sys.platform == "win32" else "Belegabruf Mac"


def datenordner() -> Path:
    """Ordner für Einstellungen, Zustand und Browserprofile."""
    ueberschrieben = os.environ.get("BELEGABRUF_DATEN")
    if ueberschrieben:
        return Path(ueberschrieben).expanduser()
    if sys.platform == "win32":
        basis = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(basis) / "belegabruf"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "belegabruf"
    basis = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(basis) / "belegabruf"


def einstellungsdatei() -> Path:
    return datenordner() / "einstellungen.toml"


def zustandsdatei() -> Path:
    return datenordner() / "zustand.json"


def kurzname(text: str) -> str:
    """Macht aus einem Kontonamen einen sicheren Ordnernamen."""
    ersetzt = (
        text.strip().lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    ersetzt = re.sub(r"[^a-z0-9]+", "-", ersetzt).strip("-")
    return ersetzt or "konto"


def anzeigepfad(pfad: Path | str) -> str:
    """Ein Pfad für Meldungen: der Benutzerordner als „~“ (kein Benutzername im Bildschirmfoto)."""
    text = str(pfad)
    heim = str(Path.home())
    return "~" + text[len(heim):] if text == heim or text.startswith(heim + os.sep) else text


def profilordner(quelle: str, konto: str) -> Path:
    """Eigenes, dauerhaftes Browserprofil je Konto."""
    return datenordner() / "profile" / f"{kurzname(quelle)}-{kurzname(konto)}"


def standard_belegordner() -> Path:
    """Dokumente/Belege — unter Windows und macOS heißt der Ordner intern 'Documents'."""
    return Path.home() / "Documents" / "Belege"
