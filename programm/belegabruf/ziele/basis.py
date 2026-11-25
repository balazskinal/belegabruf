"""Die feste Schnittstelle für ein Ziel."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from belegabruf.quellen.basis import Beleg


class Ziel(ABC):
    name: str = ""

    def __init__(self, belegordner: Path):
        self.belegordner = belegordner

    @abstractmethod
    def abliefern(self, beleg: Beleg) -> Path | None:
        """Liefert einen Beleg ab. Gibt den lokalen Ablageort zurück (oder None)."""

    def lokale_datei(self, beleg_quelle: str, art: str, jahr: int, dateiname: str) -> Path | None:
        """Wo dieses Ziel einen Beleg lokal ablegt (nur Ziele mit lokaler Ablage)."""
        return None


# ── Lieferziele: schicken einen schon abgelegten Beleg weiter (Mail, später API) ──


class Abgelehnt(Exception):
    """Die Gegenseite hat geantwortet und abgelehnt — sicher nicht angekommen.
    Der nächste Lauf versucht es erneut.

    ``alle_anhalten``: Das Problem betrifft alles (z. B. falsches Passwort), also in
    diesem Lauf nichts weiter versuchen. Sonst nur dieses Ziel anhalten."""

    def __init__(self, text: str, alle_anhalten: bool = False):
        super().__init__(text)
        self.alle_anhalten = alle_anhalten


class Unklar(Exception):
    """Gesendet, aber die Antwort blieb aus — vielleicht angekommen. Wird nicht
    noch einmal geschickt, sonst käme es womöglich doppelt."""


@dataclass
class Sendung:
    """Was ein Lieferziel über eine Rechnung weiß — nur Daten aus dem Protokoll."""

    quelle: str
    schluessel: str
    rechnungsnummer: str
    rechnungsdatum: date | None
    gutschrift: bool
    dateiname: str
    inhalt: bytes


class Lieferziel(ABC):
    #: Name im Protokoll, z. B. "mail:buchhaltung@example.com"
    name: str = ""
    #: Für Menschen, z. B. "Mail an buchhaltung@example.com"
    anzeigename: str = ""
    #: Ziele derselben Gruppe teilen sich einen Zugang (z. B. alle Mail-Empfänger)
    gruppe: str = ""

    @abstractmethod
    def senden(self, sendung: Sendung, vor_senden: Callable[[], None]) -> str | None:
        """Schickt eine Rechnung. ``vor_senden`` direkt vor dem Schritt aufrufen, nach
        dem sie angekommen sein könnte. Wirft ``Abgelehnt`` oder ``Unklar``. Gibt
        optional die Kennung beim Ziel zurück (z. B. die Beleg-ID in sevDesk)."""

    def schliessen(self) -> None:
        """Verbindungen am Ende des Laufs schließen."""
