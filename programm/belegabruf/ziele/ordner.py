"""Ziel "ordner": Belege in den lokalen Belegordner legen.

Aufbau:
    <Belegordner>/<quelle>/<Jahr>/<Dateiname>.pdf      die eigentlichen Rechnungen
    <Belegordner>/<quelle>/kontrolle/<Dateiname>.pdf   Übersichten zur Kontrolle
"""

from __future__ import annotations

import os
from pathlib import Path

from belegabruf.quellen.basis import Beleg
from belegabruf.ziele.basis import Ziel


class Ordner(Ziel):
    name = "ordner"

    def lokale_datei(self, beleg_quelle: str, art: str, jahr: int, dateiname: str) -> Path:
        unterordner = "kontrolle" if art == "kontrolle" else str(jahr)
        return self.belegordner / beleg_quelle / unterordner / dateiname

    def abliefern(self, beleg: Beleg) -> Path:
        ziel = self.lokale_datei(beleg.quelle, beleg.art, beleg.jahr, beleg.dateiname)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if beleg.art != "kontrolle":
            # Nie einen anderen Beleg überschreiben: gleicher Name → -2, -3, …
            stamm, nr = ziel.stem, 2
            while ziel.exists() and ziel.read_bytes() != beleg.inhalt:
                ziel = ziel.with_name(f"{stamm}-{nr}{ziel.suffix}")
                nr += 1
        # Erst in eine Zwischendatei schreiben, dann umbenennen: so liegt nie eine
        # halbe Datei im Ordner, falls der Rechner mittendrin ausgeht.
        zwischen = ziel.with_suffix(ziel.suffix + ".teil")
        zwischen.write_bytes(beleg.inhalt)
        os.replace(zwischen, ziel)
        return ziel
