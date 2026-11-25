"""Verzeichnis der Ziele (wohin Belege geliefert werden).

``ordner`` legt Dateien ab (immer dabei). **Lieferziele** wie ``mail`` schicken nach
dem Abruf weiter, was laut Protokoll noch fehlt (siehe ablauf.liefern) — sie stehen
deshalb nicht in ``ZIELE``. Quellen bleiben dabei unverändert.
"""

from __future__ import annotations

from pathlib import Path

from belegabruf.ziele.basis import Ziel
from belegabruf.ziele.ordner import Ordner

ZIELE: dict[str, type[Ziel]] = {
    "ordner": Ordner,
}

#: Ziele, die nach dem Abruf weiterschicken (eigene Dateien: mail.py, sevdesk.py).
LIEFERZIELE = {"mail", "sevdesk"}


def erstellen(name: str, belegordner: Path) -> Ziel:
    if name not in ZIELE:
        bekannt = ", ".join(sorted(ZIELE))
        raise KeyError(f"Unbekanntes Ziel '{name}'. Bekannt sind: {bekannt}")
    return ZIELE[name](belegordner)
