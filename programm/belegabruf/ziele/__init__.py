"""Verzeichnis der Ziele (wohin Belege geliefert werden).

Version 1: nur ``ordner``. Version 2 bringt ``sevdesk`` (Upload per API) als
weitere Datei in diesem Ordner — Quellen und Gerüst bleiben dabei unverändert.
"""

from __future__ import annotations

from pathlib import Path

from belegabruf.ziele.basis import Ziel
from belegabruf.ziele.ordner import Ordner

ZIELE: dict[str, type[Ziel]] = {
    "ordner": Ordner,
}


def erstellen(name: str, belegordner: Path) -> Ziel:
    if name not in ZIELE:
        bekannt = ", ".join(sorted(ZIELE))
        raise KeyError(f"Unbekanntes Ziel '{name}'. Bekannt sind: {bekannt}")
    return ZIELE[name](belegordner)
