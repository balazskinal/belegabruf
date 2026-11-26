"""Übernahme verwaister Konten (2.1.1).

Anmeldung (Profil) und Protokoll eines Kontos hängen an seiner internen Kennung. Geht die
Kennung verloren, bekommt das Konto eine neue (bei einem Konto ohne Namen „standard“). Dann
läge daneben ein altes Profil und ein altes Protokoll, an dem kein Konto mehr hängt — und das
Programm würde still neu anmelden lassen und alles noch einmal holen. Das passiert, wenn:

(a) ein Konto entfernt und ohne Namen neu angelegt wird,
(b) die Einstellungsdatei gerade nicht lesbar war und neu eingerichtet wurde,
(c) beim Speichern die alte Datei nicht lesbar war (seit 2.1.1 abgelehnt, siehe aktionen),
(d) der Name in der Datei von Hand gelöscht wurde.

Regel: Hat ein Konto unter seiner Kennung **kein Protokoll**, und gibt es beim selben Anbieter
**genau ein** verwaistes Protokoll (das zu keinem anderen Konto gehört), übernimmt es dessen
Kennung — und damit Protokoll und Profil. Gibt es kein verwaistes Protokoll, aber genau ein
verwaistes Profil und das Konto hat weder Protokoll noch Profil, wird das Profil übernommen.
Ist es nicht eindeutig (mehrere Waisen oder mehrere Konten ohne Protokoll), wird nicht geraten:
Diese Konten werden ausgelassen, mit einer Meldung, was zu tun ist.

Die übernommene Kennung steht danach im Konto; beim nächsten Speichern schreibt die Datei sie
als ``kennung`` fest. Was im übernommenen Protokoll steht, gilt als schon verarbeitet — es wird
nie deshalb verschickt (siehe ``ablauf.abrufen``).
"""

from __future__ import annotations

import csv
from pathlib import Path

from belegabruf import pfade


def _protokolle(quelle: str) -> dict[str, Path]:
    """Kurzname der Kennung → Protokolldatei, für einen Anbieter."""
    ordner = pfade.datenordner() / "protokolle" / pfade.kurzname(quelle)
    return {p.stem: p for p in ordner.glob("*.csv")} if ordner.is_dir() else {}


def _profile(quelle: str) -> dict[str, Path]:
    """Kurzname der Kennung → Profilordner, für einen Anbieter."""
    ordner = pfade.datenordner() / "profile"
    vorne = pfade.kurzname(quelle) + "-"
    if not ordner.is_dir():
        return {}
    return {p.name[len(vorne):]: p for p in ordner.iterdir() if p.is_dir() and p.name.startswith(vorne)}


def _kennung_aus_protokoll(datei: Path, ersatz: str) -> str:
    """Die Kennung, wie sie im Protokoll steht (Spalte „konto“), sonst der Dateiname."""
    try:
        with datei.open(newline="", encoding="utf-8") as f:
            for zeile in csv.DictReader(f, delimiter=";"):
                konto = (zeile.get("konto") or "").strip()
                if konto and pfade.kurzname(konto) == ersatz:
                    return konto
    except (OSError, csv.Error, UnicodeDecodeError):
        pass
    return ersatz


def zuordnen(einst) -> None:
    """Setzt bei verwaisten Konten die Kennung (``Konto.name``) und ``uebernommen_von`` bzw.
    ``auslassen_grund``. Ändert keine Datei."""
    from belegabruf import quellen

    for quelle in dict.fromkeys(k.quelle for k in einst.konten):
        konten = [k for k in einst.konten if k.quelle == quelle]
        eigene = {pfade.kurzname(k.name) for k in konten}
        protokolle, profile = _protokolle(quelle), _profile(quelle)
        waisen_protokoll = sorted(set(protokolle) - eigene)
        waisen_profil = sorted(set(profile) - eigene)
        ohne_protokoll = [k for k in konten if pfade.kurzname(k.name) not in protokolle]
        anbieter = quellen.anzeigename(quelle)

        if waisen_protokoll and not ohne_protokoll:
            # Schon früher neu angefangen (vor 2.1.1): nicht mehr automatisch zu lösen, nur sagen.
            for k in konten:
                alt = ", ".join(waisen_protokoll)
                k.hinweis = (f"Es gibt bei {anbieter} ein früheres Protokoll ohne Konto ({alt}). "
                             "Wurden Belege doppelt geholt (Dateien mit „-2“), stammt es von einem früheren Konto.")
        if waisen_protokoll and ohne_protokoll:
            if len(waisen_protokoll) == 1 and len(ohne_protokoll) == 1:
                kurz = waisen_protokoll[0]
                _uebernehmen(ohne_protokoll[0], _kennung_aus_protokoll(protokolle[kurz], kurz))
            else:
                _auslassen(ohne_protokoll, anbieter, waisen_protokoll, "Protokolle")
            continue
        ohne_alles = [k for k in ohne_protokoll if pfade.kurzname(k.name) not in profile]
        if waisen_profil and ohne_alles:
            if len(waisen_profil) == 1 and len(ohne_alles) == 1:
                _uebernehmen(ohne_alles[0], waisen_profil[0])
            else:
                _auslassen(ohne_alles, anbieter, waisen_profil, "Anmeldungen")


def _uebernehmen(konto, kennung: str) -> None:
    konto.uebernommen_von = konto.name
    konto.name = kennung


def _auslassen(konten, anbieter: str, waisen: list[str], was: str) -> None:
    satz = (f"Bei {anbieter} gibt es {len(waisen)} frühere {was} ohne Konto ({', '.join(waisen)}), aber nicht "
            "eindeutig, welches Konto dazugehört. Damit nichts doppelt geholt wird, wird dieses Konto ausgelassen. "
            "Bitte in der Einstellungsdatei beim Konto die richtige Zeile kennung = \"…\" eintragen "
            f"(einer der Namen in Klammern).")
    for k in konten:
        k.auslassen_grund = satz
