"""Protokoll: was wann geholt wurde — je Anbieter und Konto eine Datei.

    <Datenordner>/protokolle/<anbieter>/<konto>.csv

**Das Protokoll entscheidet allein**, ob ein Beleg schon geholt ist. Was einmal
geholt wurde, kommt nicht wieder — auch wenn die Datei im Belegordner fehlt.
Den Belegordner darf man also leeren oder weiterreichen. Neu holen gibt es nur
auf Wunsch („Fehlende Dateien neu holen“).

Das Protokoll liegt im Datenordner (bei Einstellungen und Anmeldungen), nicht im
Belegordner und nicht im Programmordner — und nicht in ``profile/``, denn das
darf man löschen. Es ist auch die Grundlage für den späteren Upload.

Enthält keine Namen von Gästen oder Kunden — nur Datum, Nummern und Ablageort.

Spalte ``ziele``: wohin der Beleg geliefert ist, mit Komma getrennt.
    ordner          liegt im Belegordner
    sevdesk         vom Programm als Entwurf nach sevDesk hochgeladen
    sevdesk-schon   war schon vorher in sevDesk (beim Einschalten markiert, nie hochgeladen)
    sevdesk-unklar  Antwort von sevDesk blieb aus — wird nicht noch einmal geschickt
Fehlt alles mit "sevdesk", ist der Beleg **noch nicht hochgeladen**; der nächste Lauf
versucht es erneut. Jede Änderung ist eine neue Zeile, die spätere gilt.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from belegabruf import pfade
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
    "sevdesk_id",  # Beleg-ID in sevDesk, wenn das Programm ihn hochgeladen hat
]


def protokolldatei(quelle: str, konto: str) -> Path:
    return pfade.datenordner() / "protokolle" / pfade.kurzname(quelle) / f"{pfade.kurzname(konto)}.csv"


class Protokoll:
    """Protokoll eines Kontos. ``datei``-Angaben sind relativ zum Belegordner."""

    def __init__(self, quelle: str, konto: str, belegordner: Path, datei: Path | None = None):
        self.quelle = quelle
        self.konto = konto
        self.belegordner = belegordner
        self.datei = datei or protokolldatei(quelle, konto)
        self._zeilen: dict[str, dict] = {}
        if self.datei.exists():
            with self.datei.open(newline="", encoding="utf-8") as f:
                leser = csv.DictReader(f, delimiter=";")
                alle = list(leser)
                spalten = leser.fieldnames or []
            for zeile in alle:
                self._zeilen[zeile["schluessel"]] = zeile  # spätere Zeilen gewinnen
            if spalten != SPALTEN:
                self._spalten_umstellen(alle)

    def _spalten_umstellen(self, alle: list[dict]) -> None:
        """Ältere Datei mit weniger Spalten (z. B. aus 1.1): neu schreiben, alle Zeilen
        bleiben in derselben Reihenfolge. Erst Zwischendatei, dann ersetzen."""
        zwischen = self.datei.with_suffix(".csv.teil")
        with zwischen.open("w", newline="", encoding="utf-8") as f:
            schreiber = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";", extrasaction="ignore")
            schreiber.writeheader()
            for zeile in alle:
                schreiber.writerow({k: zeile.get(k) or "" for k in SPALTEN})
        zwischen.replace(self.datei)

    def eintrag(self, schluessel: str) -> dict | None:
        return self._zeilen.get(schluessel)

    def bekannt(self, schluessel: str) -> bool:
        """Schon geholt? Entscheidet allein das Protokoll, nicht der Ordner."""
        return schluessel in self._zeilen

    def lokale_datei(self, schluessel: str) -> Path | None:
        zeile = self.eintrag(schluessel)
        if not zeile or not zeile.get("datei"):
            return None
        return self.belegordner / zeile["datei"]

    def fehlt_lokal(self, schluessel: str) -> bool:
        """Geholt, aber die Datei liegt nicht mehr im Belegordner."""
        datei = self.lokale_datei(schluessel)
        return datei is not None and not datei.exists()

    def fehlende(self, art: str = "rechnung") -> list[str]:
        return [s for s, z in self._zeilen.items() if z.get("art") == art and self.fehlt_lokal(s)]

    def anzahl(self, art: str) -> int:
        return sum(1 for z in self._zeilen.values() if z.get("art") == art)

    # ── Ziele je Beleg (z. B. schon in sevDesk?) ─────────────────────────────

    def ziele_von(self, schluessel: str) -> list[str]:
        zeile = self.eintrag(schluessel)
        if not zeile:
            return []
        return [z for z in (zeile.get("ziele") or "").split(",") if z]

    def in_sevdesk(self, schluessel: str) -> bool:
        """Hochgeladen, schon vorher drin oder unklar — in allen Fällen nicht (noch einmal) schicken."""
        return any(z in SEVDESK_ERLEDIGT for z in self.ziele_von(schluessel))

    def ziel_ergaenzen(self, schluessel: str, ziel: str) -> None:
        zeile = self.eintrag(schluessel)
        if zeile is None or ziel in self.ziele_von(schluessel):
            return
        neu = dict(zeile)
        neu["zeitpunkt"] = datetime.now().isoformat(timespec="seconds")
        neu["ziele"] = ",".join(self.ziele_von(schluessel) + [ziel])
        self._anhaengen([neu])

    def hochgeladen(self, schluessel: str, beleg_id: str) -> None:
        """Upload geklappt: "unklar" weg, "sevdesk" dazu, Beleg-ID merken — eine Zeile."""
        zeile = self.eintrag(schluessel)
        if zeile is None:
            return
        neu = dict(zeile)
        neu["zeitpunkt"] = datetime.now().isoformat(timespec="seconds")
        neu["ziele"] = ",".join([z for z in self.ziele_von(schluessel) if z != "sevdesk-unklar"] + ["sevdesk"])
        neu["sevdesk_id"] = beleg_id
        self._anhaengen([neu])

    def ziel_entfernen(self, schluessel: str, ziel: str) -> None:
        zeile = self.eintrag(schluessel)
        if zeile is None or ziel not in self.ziele_von(schluessel):
            return
        neu = dict(zeile)
        neu["zeitpunkt"] = datetime.now().isoformat(timespec="seconds")
        neu["ziele"] = ",".join(z for z in self.ziele_von(schluessel) if z != ziel)
        self._anhaengen([neu])

    def upload_offen(self) -> list[str]:
        """Rechnungen, die noch nicht in sevDesk sind (älteste zuerst)."""
        offen = [s for s, z in self._zeilen.items() if z.get("art") == "rechnung" and not self.in_sevdesk(s)]
        return sorted(offen, key=lambda s: (self._zeilen[s].get("rechnungsdatum") or "", s))

    def sevdesk_war_an(self) -> bool:
        """Lief das Konto beim letzten Mal schon mit Ziel sevDesk? Steht im Protokoll
        selbst (Zeile ``einstellung:sevdesk``), damit es nie verloren geht."""
        zeile = self.eintrag(SEVDESK_SCHALTER)
        return bool(zeile) and zeile.get("ziele") == "an"

    def sevdesk_schalten(self, an: bool) -> None:
        if self.sevdesk_war_an() == an:
            return
        self._anhaengen([{
            "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
            "quelle": self.quelle, "konto": self.konto, "art": "einstellung",
            "schluessel": SEVDESK_SCHALTER, "ziele": "an" if an else "aus",
        }])

    def als_schon_in_sevdesk_markieren(self) -> int:
        """Beim Einschalten von sevDesk: Alles, was bis jetzt geholt ist, gilt als schon drin."""
        neu = []
        jetzt = datetime.now().isoformat(timespec="seconds")
        for schluessel in self.upload_offen():
            zeile = dict(self._zeilen[schluessel])
            zeile["zeitpunkt"] = jetzt
            zeile["ziele"] = ",".join(self.ziele_von(schluessel) + ["sevdesk-schon"])
            neu.append(zeile)
        if neu:
            self._anhaengen(neu)
        return len(neu)

    def _anhaengen(self, zeilen: list[dict]) -> None:
        neu_anlegen = not self.datei.exists()
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        with self.datei.open("a", newline="", encoding="utf-8") as f:
            schreiber = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";", extrasaction="ignore")
            if neu_anlegen:
                schreiber.writeheader()
            for zeile in zeilen:
                schreiber.writerow(zeile)
                self._zeilen[zeile["schluessel"]] = zeile

    def eintragen(self, beleg: Beleg, datei: Path | None, ziele: list[str]) -> None:
        relativ = ""
        if datei is not None:
            try:
                relativ = datei.relative_to(self.belegordner).as_posix()
            except ValueError:
                relativ = str(datei)
        self._anhaengen([{
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
        }])


SEVDESK_SCHALTER = "einstellung:sevdesk"
SEVDESK_ERLEDIGT = {"sevdesk", "sevdesk-schon", "sevdesk-unklar"}

ALTER_NAME = "protokoll.csv"
NACH_UEBERNAHME = "protokoll.csv.uebernommen"


def altes_protokoll_uebernehmen(belegordner: Path) -> int:
    """Einmalig: protokoll.csv aus Version 1 (im Belegordner) in die neuen Dateien
    je Anbieter und Konto übernehmen. Danach wird die alte Datei umbenannt, nicht
    gelöscht. Gibt die Zahl der übernommenen Einträge zurück (0 = nichts zu tun)."""
    alt = belegordner / ALTER_NAME
    if not alt.exists():
        return 0
    with alt.open(newline="", encoding="utf-8") as f:
        zeilen = list(csv.DictReader(f, delimiter=";"))
    gruppen: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for zeile in zeilen:
        if zeile.get("quelle") and zeile.get("konto") and zeile.get("schluessel"):
            gruppen[(zeile["quelle"], zeile["konto"])].append(zeile)
    anzahl = 0
    for (quelle, konto), liste in gruppen.items():
        protokoll = Protokoll(quelle, konto, belegordner)
        neu = [z for z in liste if not protokoll.bekannt(z["schluessel"])]
        if neu:
            protokoll._anhaengen(neu)
            anzahl += len(neu)
    ziel = belegordner / NACH_UEBERNAHME
    if ziel.exists():
        ziel = belegordner / f"{NACH_UEBERNAHME}-{datetime.now():%Y%m%d%H%M%S}"
    alt.rename(ziel)
    return anzahl
