"""protokoll.csv im Belegordner: was wann geholt wurde.

Verhindert Doppelte und ist später die Grundlage für den Upload (Version 2).
Enthält keine Namen von Gästen oder Kunden — nur Datum, Nummern und Ablageort.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from belegabruf.quellen.basis import Beleg

SPALTEN = [
    "zeitpunkt",
    "quelle",
    "konto",
    "art",
    "schluessel",
    "rechnungsdatum",
    "buchungscode",
    "rechnungsnummer",
    "datei",
    "ziele",
]


class Protokoll:
    def __init__(self, datei: Path):
        self.datei = datei
        self._zeilen: dict[tuple[str, str, str], dict] = {}
        if datei.exists():
            with datei.open(newline="", encoding="utf-8") as f:
                for zeile in csv.DictReader(f, delimiter=";"):
                    self._zeilen[(zeile["quelle"], zeile["konto"], zeile["schluessel"])] = zeile

    def eintrag(self, quelle: str, konto: str, schluessel: str) -> dict | None:
        return self._zeilen.get((quelle, konto, schluessel))

    def bekannt(self, quelle: str, konto: str, schluessel: str) -> bool:
        """Bekannt = im Protokoll und (falls lokal abgelegt) die Datei gibt es noch.

        Wer eine Datei löscht, bekommt sie beim nächsten Lauf neu.
        """
        zeile = self.eintrag(quelle, konto, schluessel)
        if zeile is None:
            return False
        datei = zeile.get("datei") or ""
        if datei and not (self.datei.parent / datei).exists():
            return False
        return True

    def anzahl(self, quelle: str, konto: str, art: str) -> int:
        return sum(
            1 for (q, k, _), z in self._zeilen.items()
            if q == quelle and k == konto and z.get("art") == art
        )

    def eintragen(self, beleg: Beleg, datei: Path | None, ziele: list[str]) -> None:
        relativ = ""
        if datei is not None:
            try:
                relativ = datei.relative_to(self.datei.parent).as_posix()
            except ValueError:
                relativ = str(datei)
        zeile = {
            "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
            "quelle": beleg.quelle,
            "konto": beleg.konto,
            "art": beleg.art,
            "schluessel": beleg.schluessel,
            "rechnungsdatum": beleg.rechnungsdatum.isoformat() if beleg.rechnungsdatum else "",
            "buchungscode": beleg.buchungscode,
            "rechnungsnummer": beleg.rechnungsnummer,
            "datei": relativ,
            "ziele": ",".join(ziele),
        }
        neu_anlegen = not self.datei.exists()
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        with self.datei.open("a", newline="", encoding="utf-8") as f:
            schreiber = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";")
            if neu_anlegen:
                schreiber.writeheader()
            schreiber.writerow(zeile)
        self._zeilen[(beleg.quelle, beleg.konto, beleg.schluessel)] = zeile
