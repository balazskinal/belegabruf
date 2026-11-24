"""Einstellungsdatei lesen und schreiben (TOML, mit Erklärungen als Kommentar)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from belegabruf import pfade

JA = {"ja", "j", "yes", "y", "true", "1", "an", "ein"}
NEIN = {"nein", "n", "no", "false", "0", "aus"}


class EinstellungsFehler(Exception):
    """Die Einstellungsdatei fehlt oder ist nicht lesbar."""


def _wahrheitswert(wert: object, standard: bool = True) -> bool:
    if isinstance(wert, bool):
        return wert
    if wert is None:
        return standard
    text = str(wert).strip().lower()
    if text in JA:
        return True
    if text in NEIN:
        return False
    raise EinstellungsFehler(f"'{wert}' ist weder ja noch nein.")


@dataclass
class Konto:
    quelle: str
    name: str
    aktiv: bool = True
    optionen: dict = field(default_factory=dict)

    @property
    def bezeichnung(self) -> str:
        return f"{self.quelle} ({self.name})"


@dataclass
class Einstellungen:
    belegordner: Path
    konten: list[Konto]
    ziele: list[str] = field(default_factory=lambda: ["ordner"])
    sichtbar: bool = False  # Abruf im sichtbaren Fenster (nur zur Fehlersuche)

    def aktive_konten(self, quelle: str | None = None, konto: str | None = None) -> list[Konto]:
        return [
            k for k in self.konten
            if k.aktiv
            and (quelle is None or k.quelle == quelle)
            and (konto is None or k.name == konto)
        ]


def laden(datei: Path | None = None) -> Einstellungen:
    datei = datei or pfade.einstellungsdatei()
    if not datei.exists():
        raise EinstellungsFehler(f"Noch nicht eingerichtet (keine Datei {datei}).")
    try:
        roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as fehler:
        raise EinstellungsFehler(f"Die Einstellungsdatei {datei} ist fehlerhaft: {fehler}") from fehler

    belegordner = Path(str(roh.get("belegordner") or pfade.standard_belegordner())).expanduser()
    konten = []
    for eintrag in roh.get("konto", []):
        if not eintrag.get("quelle") or not eintrag.get("name"):
            raise EinstellungsFehler("Jedes [[konto]] braucht 'quelle' und 'name'.")
        optionen = {k: v for k, v in eintrag.items() if k not in {"quelle", "name", "aktiv"}}
        konten.append(
            Konto(
                quelle=str(eintrag["quelle"]).strip().lower(),
                name=str(eintrag["name"]).strip(),
                aktiv=_wahrheitswert(eintrag.get("aktiv"), True),
                optionen=optionen,
            )
        )
    ziele = roh.get("ziele") or ["ordner"]
    if isinstance(ziele, str):
        ziele = [ziele]
    return Einstellungen(
        belegordner=belegordner,
        konten=konten,
        ziele=[str(z).strip().lower() for z in ziele],
        sichtbar=_wahrheitswert(roh.get("sichtbar"), False),
    )


def _toml_text(wert: str) -> str:
    return '"' + wert.replace("\\", "\\\\").replace('"', '\\"') + '"'


def als_text(einst: Einstellungen) -> str:
    zeilen = [
        "# Einstellungen für Belegabruf",
        "#",
        "# Du kannst diese Datei mit jedem Texteditor ändern oder einfach noch einmal",
        "# \"Einrichten\" doppelklicken. Zeilen mit # am Anfang sind nur Erklärungen.",
        "# Hier stehen keine Passwörter — angemeldet wird immer im Browserfenster.",
        "",
        "# Wohin die Belege gespeichert werden.",
        f"belegordner = {_toml_text(str(einst.belegordner))}",
        "",
        "# Wohin die Belege geliefert werden. Version 1 kennt nur \"ordner\"",
        "# (der Belegordner oben). Später kommt \"sevdesk\" dazu.",
        "ziele = [" + ", ".join(_toml_text(z) for z in einst.ziele) + "]",
        "",
        "# Abruf im sichtbaren Browserfenster? Nur zur Fehlersuche: \"ja\".",
        f"sichtbar = {_toml_text('ja' if einst.sichtbar else 'nein')}",
        "",
        "# Ein Block [[konto]] je Konto. Mehrere Konten bei derselben Quelle sind",
        "# erlaubt (z. B. ein eigenes und ein Co-Gastgeber-Konto) — jedes bekommt",
        "# seine eigene Anmeldung. Mit aktiv = \"nein\" wird ein Konto übersprungen.",
    ]
    for konto in einst.konten:
        zeilen += [
            "",
            "[[konto]]",
            f"quelle = {_toml_text(konto.quelle)}",
            f"name = {_toml_text(konto.name)}",
            f"aktiv = {_toml_text('ja' if konto.aktiv else 'nein')}",
        ]
        for schluessel, wert in konto.optionen.items():
            zeilen.append(f"{schluessel} = {_toml_text(str(wert))}")
    return "\n".join(zeilen) + "\n"


def speichern(einst: Einstellungen, datei: Path | None = None) -> Path:
    datei = datei or pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(als_text(einst), encoding="utf-8")
    return datei
