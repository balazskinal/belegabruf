"""Übernahme verwaister Konten (2.1.1).

Anmeldung (Profil) und Protokoll eines Kontos hängen an seiner internen Kennung. Geht die
Kennung verloren, bekommt das Konto eine neue (bei einem Konto ohne Namen „standard“). Dann
läge daneben ein altes Profil und ein altes Protokoll, an dem kein Konto mehr hängt — und das
Programm würde still neu anmelden lassen und alles noch einmal holen. Das passiert, wenn:

(a) ein Konto entfernt und ohne Namen neu angelegt wird,
(b) die Einstellungsdatei gerade nicht lesbar war und neu eingerichtet wurde,
(c) beim Speichern die alte Datei nicht lesbar war (seit 2.1.1 abgelehnt, siehe aktionen),
(d) der Name in der Datei von Hand gelöscht wurde.

Regel (seit der Prüfung zu PR #20 enger):

* Übernommen wird nur bei einem Konto **ohne Namen** und ohne ``kennung`` in der Datei (also mit
  der Standard-Kennung) — genau der Fall, in dem die Kennung verloren gegangen sein kann. Ein
  Konto mit Namen oder mit ausdrücklicher ``kennung`` wird nie umgebogen.
* Es muss **genau ein** verwaistes Protokoll beim selben Anbieter geben (ohne Protokoll: genau
  ein verwaistes Profil). Verwaist heißt: Es gehört zu keinem Konto, und es wurde nicht beim
  Entfernen eines Kontos als „entfernt“ vermerkt (``zustand.entfernt``). Ein absichtlich
  entferntes Konto gibt seine Anmeldung also nie an ein neues weiter.
* Nicht eindeutig (mehrere Waisen): nicht raten, das Konto auslassen — mit dem Ausweg, ihm einen
  Namen zu geben.

Die übernommene Kennung steht danach im Konto; beim nächsten Speichern schreibt die Datei sie
als ``kennung`` fest. Was im übernommenen Protokoll steht, gilt als schon verarbeitet — es wird
nie deshalb verschickt (siehe ``ablauf._uebernahme_abschliessen``).
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


def _waisen(quelle: str, eigene: set[str], gefunden: dict[str, Path]) -> list[str]:
    """Kennungen (Kurzname) mit Profil bzw. Protokoll, aber ohne Konto und nicht entfernt."""
    from belegabruf import zustand

    entfernt = {s.split("/", 1)[1] for s in zustand.entfernt() if s.startswith(pfade.kurzname(quelle) + "/")}
    return sorted(set(gefunden) - eigene - entfernt)


def _kandidat(konten) -> object | None:
    """Das eine Konto, dessen Kennung verloren gegangen sein kann: ohne Namen, ohne kennung."""
    from belegabruf.einstellungen import STANDARD_KENNUNG

    ohne = [k for k in konten if not k.anzeigetitel.strip() and not k.kennung_aus_datei
            and k.name == STANDARD_KENNUNG]
    return ohne[0] if len(ohne) == 1 else None


def zuordnen(einst) -> None:
    """Setzt bei einem verwaisten Konto die Kennung (``Konto.name``) und ``uebernommen_von``
    bzw. ``auslassen_grund``. Ändert keine Datei."""
    for quelle in dict.fromkeys(k.quelle for k in einst.konten):
        konten = [k for k in einst.konten if k.quelle == quelle]
        konto = _kandidat(konten)
        if konto is None:
            continue
        eigene = {pfade.kurzname(k.name) for k in konten}
        protokolle, profile = _protokolle(quelle), _profile(quelle)
        kurz = pfade.kurzname(konto.name)
        if kurz in protokolle:
            continue  # hat ein eigenes Protokoll: nichts verloren
        waisen = _waisen(quelle, eigene, protokolle)
        if waisen:
            _entscheiden(konto, quelle, waisen, lambda w, p=protokolle: _kennung_aus_protokoll(p[w], w))
        elif kurz not in profile:
            _entscheiden(konto, quelle, _waisen(quelle, eigene, profile), lambda w: w)


def _entscheiden(konto, quelle: str, waisen: list[str], kennung) -> None:
    if len(waisen) == 1:
        konto.uebernommen_von = konto.name
        konto.name = kennung(waisen[0])
    elif waisen:
        _auslassen(konto, quelle, waisen)


def _auslassen(konto, quelle: str, waisen: list[str]) -> None:
    from belegabruf import quellen

    konto.auslassen_grund = (
        f"Bei {quellen.anzeigename(quelle)} liegen mehrere frühere Anmeldungen ohne Konto "
        f"({', '.join(waisen)}). Ob eine davon zu diesem Konto gehört, ist nicht eindeutig — deshalb wird es "
        "ausgelassen, damit nichts doppelt oder einem falschen Konto zugeordnet wird. Gib dem Konto in den "
        "Einstellungen einen Namen: Heißt es wie sein früheres Konto, nutzt es dessen Anmeldung wieder; "
        "mit einem neuen Namen fängt es neu an.")
