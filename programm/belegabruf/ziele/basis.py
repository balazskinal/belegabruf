"""Die feste Schnittstelle für ein Ziel."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

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
