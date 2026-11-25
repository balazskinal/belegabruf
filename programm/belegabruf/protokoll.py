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

**Lieferziele** (z. B. ``mail:buchhaltung@example.com``) stehen in der Spalte ``ziele``,
mit Komma getrennt, als Zustand je Rechnung:

    <ziel>          geliefert (z. B. Mail verschickt)
    <ziel>:schon    galt beim allerersten Einschalten des Ziels als schon geliefert
    <ziel>:unklar   Antwort blieb aus — wird nicht noch einmal geschickt
    (nichts)        noch offen; der nächste Lauf versucht es erneut

``ordner`` heißt: liegt im Belegordner. Ob ein Ziel an ist, steht als Zeile
``einstellung:<ziel>`` (an/aus) im Protokoll selbst. Nur beim allerersten Einschalten
eines Ziels gilt alles schon Geholte als geliefert; beim Wiedereinschalten nicht.
Jede Änderung ist eine neue Zeile, die spätere gilt.
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
                for zeile in csv.DictReader(f, delimiter=";"):
                    self._zeilen[zeile["schluessel"]] = zeile  # spätere Zeilen gewinnen

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

    # ── Lieferziele (Mail, später weitere) ───────────────────────────────────

    def ziele_von(self, schluessel: str) -> list[str]:
        zeile = self.eintrag(schluessel)
        if not zeile:
            return []
        return [z for z in (zeile.get("ziele") or "").split(",") if z]

    def zustand(self, schluessel: str, ziel: str) -> str:
        """'geliefert', 'schon', 'unklar' oder 'offen'."""
        vorhanden = set(self.ziele_von(schluessel))
        if ziel in vorhanden:
            return "geliefert"
        if f"{ziel}:schon" in vorhanden:
            return "schon"
        if f"{ziel}:unklar" in vorhanden:
            return "unklar"
        return "offen"

    def _ziele_setzen(self, schluessel: str, ziele: list[str], **extra: str) -> None:
        zeile = self.eintrag(schluessel)
        if zeile is None or ziele == self.ziele_von(schluessel):
            return
        neu = dict(zeile)
        neu.update(extra)
        neu["zeitpunkt"] = datetime.now().isoformat(timespec="seconds")
        neu["ziele"] = ",".join(ziele)
        self._anhaengen([neu])

    def _ohne(self, schluessel: str, ziel: str) -> list[str]:
        """Alle Ziele dieser Rechnung ohne die Einträge zu ``ziel``."""
        return [z for z in self.ziele_von(schluessel)
                if z not in {ziel, f"{ziel}:schon", f"{ziel}:unklar"}]

    def als_unklar(self, schluessel: str, ziel: str) -> None:
        """Direkt vor dem Senden: Bricht es jetzt ab, wird nicht noch einmal geschickt."""
        self._ziele_setzen(schluessel, self._ohne(schluessel, ziel) + [f"{ziel}:unklar"])

    def als_offen(self, schluessel: str, ziel: str) -> None:
        """Sicher nicht angekommen (abgelehnt): der nächste Lauf versucht es erneut."""
        self._ziele_setzen(schluessel, self._ohne(schluessel, ziel))

    def als_geliefert(self, schluessel: str, ziel: str) -> None:
        self._ziele_setzen(schluessel, self._ohne(schluessel, ziel) + [ziel])

    def offen_fuer(self, ziel: str) -> list[str]:
        """Rechnungen, die an dieses Ziel noch nicht geliefert sind (älteste zuerst)."""
        offen = [s for s, z in self._zeilen.items()
                 if z.get("art") == "rechnung" and self.zustand(s, ziel) == "offen"]
        return sorted(offen, key=lambda s: (self._zeilen[s].get("rechnungsdatum") or "", s))

    def bisherige_lieferungen(self, schluessel: str) -> list[str]:
        """Zustände aller Lieferziele (alles außer „ordner“) — bleiben beim Neuholen erhalten."""
        return [z for z in self.ziele_von(schluessel) if z != "ordner"]

    # Schalter je Ziel

    @staticmethod
    def _schalter(ziel: str) -> str:
        return f"einstellung:{ziel}"

    def je_eingeschaltet(self, ziel: str) -> bool:
        """Stand je eine Schalterzeile für dieses Ziel im Protokoll?"""
        return self.eintrag(self._schalter(ziel)) is not None

    def ist_an(self, ziel: str) -> bool:
        zeile = self.eintrag(self._schalter(ziel))
        return bool(zeile) and zeile.get("ziele") == "an"

    def eingeschaltete_ziele(self) -> list[str]:
        return [s.removeprefix("einstellung:") for s, z in self._zeilen.items()
                if z.get("art") == "einstellung" and z.get("ziele") == "an"]

    def schalten(self, ziel: str, an: bool) -> None:
        if self.ist_an(ziel) == an or (not an and not self.je_eingeschaltet(ziel)):
            return
        self._anhaengen([{
            "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
            "quelle": self.quelle, "konto": self.konto, "art": "einstellung",
            "schluessel": self._schalter(ziel), "ziele": "an" if an else "aus",
        }])

    def als_schon_markieren(self, ziel: str) -> int:
        """Alles bis jetzt Geholte gilt für dieses Ziel als schon geliefert."""
        jetzt = datetime.now().isoformat(timespec="seconds")
        neu = []
        for schluessel in self.offen_fuer(ziel):
            zeile = dict(self._zeilen[schluessel])
            zeile["zeitpunkt"] = jetzt
            zeile["ziele"] = ",".join(self.ziele_von(schluessel) + [f"{ziel}:schon"])
            neu.append(zeile)
        if neu:
            self._anhaengen(neu)
        return len(neu)

    def ziele_abgleichen(self, aktive: list[str]) -> dict[str, int]:
        """Schalter an die Einstellungen anpassen. Ziele, die zum allerersten Mal an
        sind, markieren den Bestand als schon geliefert. Gibt je so markiertem Ziel die
        Anzahl zurück."""
        markiert = {}
        for ziel in aktive:
            if not self.je_eingeschaltet(ziel):
                markiert[ziel] = self.als_schon_markieren(ziel)
            self.schalten(ziel, True)
        for ziel in self.eingeschaltete_ziele():
            if ziel not in aktive:
                self.schalten(ziel, False)
        return markiert

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
