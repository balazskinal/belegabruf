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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from belegabruf.einstellungen import Konto


class SitzungAbgelaufen(Exception):
    """Mitten im Abruf ist die Anmeldung abgelaufen."""


@dataclass
class Beleg:
    """Ein geholter Beleg, fertig zum Abliefern."""

    quelle: str
    konto: str
    # "rechnung" (der eigentliche Beleg, geht an Lieferziele wie Mail), "kontrolle" (z. B.
    # Monatsübersicht bei Airbnb) oder eine weitere Dokumentart, die nur abgelegt wird
    # (z. B. "auszahlung" bei Booking.com). Nur "rechnung" wird verschickt.
    art: str
    schluessel: str  # eindeutig je Quelle und Konto, verhindert Doppelte
    dateiname: str
    inhalt: bytes
    jahr: int
    rechnungsdatum: date | None = None
    rechnungsnummer: str = ""
    buchungscode: str = ""
    betrag: str = ""  # wie im Beleg, z. B. "12,34 EUR" (für später, Upload)
    # Eigener Ordner unter dem Anbieter, z. B. "Rechnungen" → <quelle>/Rechnungen/<JJJJ>/…
    # Leer = wie bisher direkt <quelle>/<JJJJ>/…
    unterordner: str = ""


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
    # Lieferziele (z. B. Mail je Empfänger): Name im Protokoll → Stand dieses Laufs mit
    # anzeige, geliefert, offen, fehler (Klartext, nie mit Passwort), unklar
    # (Rechnungsnummern), schon_markiert (beim allerersten Einschalten).
    lieferungen: dict[str, dict] = field(default_factory=dict)
    anzeige: str = ""  # „Airbnb“ bzw. „Airbnb (Privat)“; leer = aus quelle und konto
    # Zeitraum: Belege vor diesem Datum (ISO, leer = alle) wurden nicht geholt und nicht vermerkt.
    ab: str = ""
    uebersprungen: int = 0  # so viele Rechnungen lagen vor dem Zeitraum
    erstlauf_abgelegt: int = 0  # erster Lauf eines neuen Kontos: abgelegt, nicht verschickt

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
    ab: date | None = None  # Zeitraum: nur Belege ab diesem Rechnungsdatum (None = alle)

    def zu_alt(self, datum: date | None) -> bool:
        """Liegt der Beleg vor dem Zeitraum? Ohne erkanntes Datum: nein (lieber holen)."""
        return self.ab is not None and datum is not None and datum < self.ab


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
