"""Die feste Schnittstelle für jeden Baustein (eine Quelle = eine Datei in quellen/).

Jede Quelle kann genau drei Dinge:

1. ``sitzung_pruefen()``   — ist das Konto noch angemeldet? (unsichtbar)
2. ``anmelden_lassen()``   — sichtbares Fenster öffnen, der Mensch meldet sich an
3. ``belege_holen()``      — alle neuen Belege holen und abliefern (unsichtbar)

Eine Quelle speichert nichts selbst. Sie übergibt jeden Beleg an ``abliefern``;
wohin er geht (Ordner, später sevDesk), entscheiden die Ziele.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from belegabruf.einstellungen import Konto


class SitzungAbgelaufen(Exception):
    """Mitten im Abruf ist die Anmeldung abgelaufen."""


@dataclass
class Beleg:
    """Ein geholter Beleg, fertig zum Abliefern."""

    quelle: str
    konto: str
    art: str  # "rechnung" (der eigentliche Beleg) oder "kontrolle" (z. B. Monatsübersicht)
    schluessel: str  # eindeutig je Quelle und Konto, verhindert Doppelte
    dateiname: str
    inhalt: bytes
    jahr: int
    rechnungsdatum: date | None = None
    rechnungsnummer: str = ""
    buchungscode: str = ""
    betrag: str = ""  # wie im Beleg, z. B. "12,34 EUR" (für später, Upload)


@dataclass
class Ergebnis:
    """Was ein Abruf für ein Konto gebracht hat. Enthält nie Inhalte aus den Belegen
    außer Datum, Rechnungsnummer und Buchungscode."""

    quelle: str
    konto: str
    status: str = "ok"  # ok | unvollstaendig | anmeldung_noetig | abgelaufen | fehler
    neu: int = 0
    schon_da: int = 0
    kontrolle_neu: int = 0
    erwartet: int | None = None  # so viele Einzelrechnungen nennen die Übersichten
    vorhanden: int | None = None  # so viele liegen jetzt vor
    abweichungen: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    fehler: str = ""
    neue_dateien: list[str] = field(default_factory=list)
    # Ziel sevDesk (nur wenn eingeschaltet)
    sevdesk: bool = False
    hochgeladen: int = 0  # in diesem Lauf als Entwurf hochgeladen
    nicht_hochgeladen: int = 0  # warten noch, der nächste Lauf versucht es erneut
    upload_fehler: str = ""  # Meldung von sevDesk im Klartext (nie mit Schlüssel)
    upload_unklar: list[str] = field(default_factory=list)  # Rechnungsnummern: Antwort blieb aus
    als_schon_markiert: int = 0  # beim Einschalten als „schon in sevDesk“ markiert

    def als_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Umgebung:
    """Was das Gerüst einer Quelle beim Abruf mitgibt."""

    bekannt: Callable[[str], bool]  # Schlüssel schon abgeliefert?
    abliefern: Callable[[Beleg], list[str]]  # liefert ab, gibt Ablageorte zurück
    vorhandene_datei: Callable[[str], Path | None]  # lokale Kopie eines Belegs (Schlüssel)
    melden: Callable[[str], None]  # Fortschritt für den Menschen
    sichtbar: bool = False


class Quelle(ABC):
    """Basisklasse für einen Baustein."""

    #: Kurzname, wie er in der Einstellungsdatei steht (z. B. "airbnb").
    name: str = ""
    #: Name für Menschen (z. B. "Airbnb").
    anzeigename: str = ""

    def __init__(self, konto: Konto, profil: Path):
        self.konto = konto
        self.profil = profil

    @abstractmethod
    def sitzung_pruefen(self) -> bool:
        """True, wenn das Konto angemeldet ist. Öffnet kein sichtbares Fenster."""

    @abstractmethod
    def anmelden_lassen(self, melden: Callable[[str], None]) -> bool:
        """Öffnet ein sichtbares Fenster, wartet auf den Menschen. True bei Erfolg."""

    @abstractmethod
    def belege_holen(self, umgebung: Umgebung) -> Ergebnis:
        """Holt alle noch nicht bekannten Belege und gibt sie an umgebung.abliefern."""
