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


#: Vorgabe für den Eintrag im Passwortspeicher des Betriebssystems: "Dienst/Konto".
STANDARD_SCHLUESSEL = "belegabruf/sevdesk"
#: Steuerregel des Entwurfs in sevDesk. Keine Vorgabe: Sie hängt von der eigenen
#: Buchhaltung ab und wird bei "Einrichten" gewählt (Nummer aus sevDesk).
STANDARD_STEUERREGEL = ""


@dataclass
class SevDeskEinstellung:
    """Ziel sevDesk. Hier steht nie der Schlüssel selbst, nur wo er im
    Passwortspeicher des Betriebssystems liegt (Schlüsselbund bzw.
    Anmeldeinformationsverwaltung)."""

    schluessel: str = STANDARD_SCHLUESSEL  # "Dienst/Konto"
    steuerregel: str = STANDARD_STEUERREGEL

    @property
    def dienst_und_konto(self) -> tuple[str, str]:
        dienst, _, konto = self.schluessel.partition("/")
        return dienst.strip(), konto.strip()


@dataclass
class Einstellungen:
    belegordner: Path
    konten: list[Konto]
    ziele: list[str] = field(default_factory=lambda: ["ordner"])
    sichtbar: bool = False  # Abruf im sichtbaren Fenster (nur zur Fehlersuche)
    sevdesk: SevDeskEinstellung = field(default_factory=SevDeskEinstellung)

    @property
    def sevdesk_an(self) -> bool:
        return "sevdesk" in self.ziele

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
    ziele = [str(z).strip().lower() for z in ziele]
    if "ordner" not in ziele:  # Der Belegordner ist immer dabei.
        ziele.insert(0, "ordner")
    roh_sevdesk = roh.get("sevdesk") or {}
    if not isinstance(roh_sevdesk, dict):
        raise EinstellungsFehler("[sevdesk] muss ein Abschnitt sein.")
    sevdesk = SevDeskEinstellung(
        schluessel=str(roh_sevdesk.get("schluessel") or STANDARD_SCHLUESSEL).strip(),
        steuerregel=str(roh_sevdesk.get("steuerregel") or STANDARD_STEUERREGEL).strip(),
    )
    if sevdesk.steuerregel and not sevdesk.steuerregel.isdigit():
        raise EinstellungsFehler(
            f"[sevdesk] steuerregel = \"{sevdesk.steuerregel}\" muss eine Nummer sein (z. B. \"14\").")
    dienst, konto = sevdesk.dienst_und_konto
    if not dienst or not konto:
        raise EinstellungsFehler(
            f"[sevdesk] schluessel = \"{sevdesk.schluessel}\" muss die Form \"Dienst/Konto\" haben.")
    return Einstellungen(
        belegordner=belegordner,
        konten=konten,
        ziele=ziele,
        sichtbar=_wahrheitswert(roh.get("sichtbar"), False),
        sevdesk=sevdesk,
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
        "# Der sevDesk-Schlüssel liegt im Passwortspeicher des Betriebssystems, nie hier.",
        "",
        "# Wohin die Belege gespeichert werden.",
        f"belegordner = {_toml_text(str(einst.belegordner))}",
        "",
        "# Wohin die Belege geliefert werden: \"ordner\" (der Belegordner oben, immer dabei)",
        "# und auf Wunsch \"sevdesk\" (Upload als Entwurf, siehe Abschnitt [sevdesk] unten).",
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
    zeilen += [
        "",
        "# Nur wichtig, wenn bei ziele \"sevdesk\" steht.",
        "# schluessel: wo der API-Schlüssel im Passwortspeicher liegt, als \"Dienst/Konto\"",
        "#   (nicht der Schlüssel selbst!). Eingeben oder austauschen über \"Einrichten\".",
        "# steuerregel: Nummer der Steuerregel in sevDesk, wird im Entwurf eingetragen (Pflicht).",
        "[sevdesk]",
        f"schluessel = {_toml_text(einst.sevdesk.schluessel)}",
        f"steuerregel = {_toml_text(einst.sevdesk.steuerregel)}",
    ]
    return "\n".join(zeilen) + "\n"


def speichern(einst: Einstellungen, datei: Path | None = None) -> Path:
    datei = datei or pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(als_text(einst), encoding="utf-8")
    return datei
