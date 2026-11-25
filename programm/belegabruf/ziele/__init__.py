"""Verzeichnis der Ziele (wohin Belege geliefert werden).

``ordner`` legt Dateien ab (immer dabei). ``sevdesk`` (Upload als Entwurf per API,
siehe sevdesk.py) läuft nach dem Abruf über das Protokoll und steht deshalb nicht in
dieser Liste — Quellen bleiben dabei unverändert.
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
