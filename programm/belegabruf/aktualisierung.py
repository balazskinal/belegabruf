"""Hinweis auf eine neuere Version auf GitHub. Kein Selbst-Update.

Fragt kurz die GitHub-Seite mit den Veröffentlichungen ab. Klappt das nicht
(kein Internet, Repo privat), passiert einfach nichts.
"""

from __future__ import annotations

import json
import re
import urllib.request

from belegabruf import GITHUB_REPO, __version__

NEUESTE_SEITE = f"https://github.com/{GITHUB_REPO}/releases/latest"


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
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - offline oder privat: kein Hinweis
        return None
    tag = str(daten.get("tag_name") or "")
    return tag.lstrip("vV") if tag and ist_neuer(tag) else None
