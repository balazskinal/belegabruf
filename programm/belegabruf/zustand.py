"""Kleiner Merkzettel im Benutzerordner: wann welches Konto zuletzt erfolgreich lief."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from belegabruf import pfade

# Airbnb zeigt nur 12 Monate. Wer länger als zwei Monate nicht abruft, wird gewarnt.
WARNEN_NACH = timedelta(days=61)


def _laden() -> dict:
    datei = pfade.zustandsdatei()
    if not datei.exists():
        return {}
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _speichern(daten: dict) -> None:
    datei = pfade.zustandsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")


def _schluessel(quelle: str, konto: str) -> str:
    return f"{quelle}/{konto}"


def letzter_lauf(quelle: str, konto: str) -> datetime | None:
    wert = _laden().get("letzter_erfolg", {}).get(_schluessel(quelle, konto))
    if not wert:
        return None
    try:
        return datetime.fromisoformat(wert)
    except ValueError:
        return None


def lauf_merken(quelle: str, konto: str, zeitpunkt: datetime | None = None) -> None:
    daten = _laden()
    daten.setdefault("letzter_erfolg", {})[_schluessel(quelle, konto)] = (
        zeitpunkt or datetime.now()
    ).isoformat(timespec="seconds")
    _speichern(daten)


def angemeldet_merken(quelle: str, konto: str) -> None:
    """Dieses Konto war schon einmal angemeldet (unterscheidet „abgelaufen“ von „noch nie“)."""
    daten = _laden()
    daten.setdefault("je_angemeldet", {})[_schluessel(quelle, konto)] = datetime.now().isoformat(timespec="seconds")
    _speichern(daten)


def je_angemeldet(quelle: str, konto: str) -> bool:
    return (_schluessel(quelle, konto) in _laden().get("je_angemeldet", {})
            or letzter_lauf(quelle, konto) is not None)


def zu_lange_her(quelle: str, konto: str, jetzt: datetime | None = None) -> datetime | None:
    """Gibt das Datum des letzten Laufs zurück, wenn es über zwei Monate her ist."""
    zuletzt = letzter_lauf(quelle, konto)
    if zuletzt and (jetzt or datetime.now()) - zuletzt > WARNEN_NACH:
        return zuletzt
    return None
