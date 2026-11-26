"""Ziel "ordner": Belege in den lokalen Belegordner legen.

Aufbau (Einstellung ``ablage``):
    <Belegordner>/<quelle>/<JJJJ>/<Dateiname>.pdf       die Rechnungen, ablage = "jahr" (Standard)
    <Belegordner>/<quelle>/<JJJJ>/<MM>/<Dateiname>.pdf  die Rechnungen, ablage = "monat"
    <Belegordner>/<quelle>/kontrolle/<Dateiname>.pdf    Übersichten zur Kontrolle (immer hier)

Maßgeblich für Jahr und Monat ist das Rechnungsdatum. Fehlt es, gilt das Jahr des Belegs;
der Monatsordner ist dann der heutige, wenn es das laufende Jahr ist, sonst gibt es keinen.
Ob ein Beleg schon geholt ist, entscheidet allein das Protokoll (Schlüssel), nicht der Pfad: Wer die Ablage umstellt,
bekommt nichts doppelt, und bereits abgelegte Belege bleiben, wo sie sind.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from belegabruf.quellen.basis import Beleg
from belegabruf.ziele.basis import Ziel


class Ordner(Ziel):
    name = "ordner"

    def lokale_datei(self, beleg_quelle: str, art: str, jahr: int, dateiname: str,
                     monat: int | None = None) -> Path:
        if art == "kontrolle":
            return self.belegordner / beleg_quelle / "kontrolle" / dateiname
        ordner = self.belegordner / beleg_quelle / str(jahr)
        if self.ablage == "monat":
            if monat is None and jahr == date.today().year:
                monat = date.today().month  # ohne Datum: die Quellen meinen dann „jetzt“
            if monat is not None:  # ohne Datum aus einem früheren Jahr: kein geratener Monat
                ordner = ordner / f"{monat:02d}"
        return ordner / dateiname

    def abliefern(self, beleg: Beleg) -> Path:
        datum = beleg.rechnungsdatum
        ziel = self.lokale_datei(beleg.quelle, beleg.art, datum.year if datum else beleg.jahr, beleg.dateiname,
                                 monat=datum.month if datum else None)
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
