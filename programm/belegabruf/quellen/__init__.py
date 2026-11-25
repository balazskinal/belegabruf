"""Verzeichnis der Bausteine (Quellen).

Ein neuer Baustein ist eine neue Datei in diesem Ordner mit einer Klasse, die
von ``Quelle`` erbt, plus ein Eintrag in ``QUELLEN``.
"""

from __future__ import annotations

from belegabruf.quellen.basis import Quelle


def _airbnb():
    from belegabruf.quellen.airbnb import Airbnb

    return Airbnb


def _skool():
    from belegabruf.quellen.skool import Skool

    return Skool


def _xentra():
    from belegabruf.quellen.xentra import Xentra

    return Xentra


# Kurzname -> (Anzeigename, Lader). Geladen wird erst, wenn gebraucht.
QUELLEN = {
    "airbnb": ("Airbnb", _airbnb),
    "skool": ("Skool", _skool),
    "xentra": ("Xentra", _xentra),
}


def klasse(name: str) -> type[Quelle]:
    if name not in QUELLEN:
        bekannt = ", ".join(sorted(QUELLEN))
        raise KeyError(f"Unbekannte Quelle '{name}'. Bekannt sind: {bekannt}")
    return QUELLEN[name][1]()


def anzeigename(name: str) -> str:
    return QUELLEN.get(name, (name, None))[0]
