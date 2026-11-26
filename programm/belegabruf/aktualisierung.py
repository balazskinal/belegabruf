"""Hinweis auf eine neuere Version auf GitHub. Kein Selbst-Update.

Fragt kurz die GitHub-Seite mit den Veröffentlichungen ab. Klappt das nicht
(kein Internet, Repo privat), passiert einfach nichts.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

from belegabruf import GITHUB_REPO, __version__

NEUESTE_SEITE = f"https://github.com/{GITHUB_REPO}/releases/latest"

#: Einrichten und Update mit einer Zeile (ab 2.2.0): Was curl bzw. PowerShell lädt, bekommt
#: keine Quarantäne bzw. kein Mark-of-the-Web — keine Sicherheitsmeldung beim Start.
UPDATE_MAC = f"curl -fsSL https://github.com/{GITHUB_REPO}/releases/latest/download/installieren.sh | bash"
UPDATE_WINDOWS = f"irm https://github.com/{GITHUB_REPO}/releases/latest/download/installieren.ps1 | iex"


def update_zeile() -> str:
    """Die Update-Zeile für dieses System."""
    return UPDATE_WINDOWS if sys.platform == "win32" else UPDATE_MAC


def update_hinweis() -> str:
    """Wo die Zeile hinkommt — für Menschen."""
    return "in PowerShell" if sys.platform == "win32" else "im Programm „Terminal“"


def _als_tupel(text: str) -> tuple[int, ...]:
    return tuple(int(t) for t in re.findall(r"\d+", text)[:3])


def ist_neuer(kandidat: str, aktuell: str = __version__) -> bool:
    try:
        return _als_tupel(kandidat) > _als_tupel(aktuell)
    except ValueError:
        return False


def neuere_version(timeout: float = 3.0) -> str | None:
    """Gibt die neuere Versionsnummer zurück, sonst None."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    anfrage = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "belegabruf"}
    )
    try:
        # Bandit B310 trifft hier nicht: feste https-Adresse von GitHub (oben gebaut), keine file:-Adresse.
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:  # nosec B310
            daten = json.loads(antwort.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - offline oder privat: kein Hinweis
        return None
    tag = str(daten.get("tag_name") or "")
    return tag.lstrip("vV") if tag and ist_neuer(tag) else None
