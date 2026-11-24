"""Das Gerüst: Konten prüfen, Anmeldungen einsammeln, Belege holen, abliefern."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from belegabruf import pfade, quellen, zustand
from belegabruf import ziele as ziel_verzeichnis
from belegabruf.browser import BrowserFehlt, ProfilBelegt
from belegabruf.einstellungen import Einstellungen, Konto
from belegabruf.protokoll import Protokoll
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung

Melden = Callable[[str], None]


def quelle_fuer(konto: Konto) -> Quelle:
    klasse = quellen.klasse(konto.quelle)
    return klasse(konto, pfade.profilordner(konto.quelle, konto.name))


def protokoll_fuer(einst: Einstellungen) -> Protokoll:
    return Protokoll(einst.belegordner / "protokoll.csv")


def sitzung_pruefen(konto: Konto) -> str:
    """'angemeldet', 'abgemeldet' oder eine Fehlermeldung."""
    try:
        return "angemeldet" if quelle_fuer(konto).sitzung_pruefen() else "abgemeldet"
    except (BrowserFehlt, ProfilBelegt) as fehler:
        return str(fehler)
    except Exception as fehler:  # noqa: BLE001
        return f"Prüfung fehlgeschlagen: {fehler}"


def anmelden(konto: Konto, melden: Melden) -> bool:
    try:
        return quelle_fuer(konto).anmelden_lassen(melden)
    except (BrowserFehlt, ProfilBelegt) as fehler:
        melden(f"  {fehler}")
        return False


def abrufen(einst: Einstellungen, konto: Konto, melden: Melden, protokoll: Protokoll | None = None) -> Ergebnis:
    """Holt die Belege eines Kontos. Stürzt nie ab, sondern meldet im Ergebnis."""
    protokoll = protokoll or protokoll_fuer(einst)
    try:
        ziele = [ziel_verzeichnis.erstellen(name, einst.belegordner) for name in einst.ziele]
        quelle = quelle_fuer(konto)
    except KeyError as fehler:
        return Ergebnis(konto.quelle, konto.name, status="fehler", fehler=str(fehler).strip("'\""))

    def bekannt(schluessel: str) -> bool:
        return protokoll.bekannt(konto.quelle, konto.name, schluessel)

    def vorhandene_datei(schluessel: str) -> Path | None:
        zeile = protokoll.eintrag(konto.quelle, konto.name, schluessel)
        if not zeile or not zeile.get("datei"):
            return None
        datei = einst.belegordner / zeile["datei"]
        return datei if datei.exists() else None

    def abliefern(beleg: Beleg) -> list[str]:
        lokal: Path | None = None
        for ziel in ziele:
            ort = ziel.abliefern(beleg)
            if ort is not None and lokal is None:
                lokal = ort
        if protokoll.eintrag(beleg.quelle, beleg.konto, beleg.schluessel) is None or beleg.art == "rechnung":
            protokoll.eintragen(beleg, lokal, [z.name for z in ziele])
        return [str(lokal)] if lokal else []

    umgebung = Umgebung(
        bekannt=bekannt,
        abliefern=abliefern,
        vorhandene_datei=vorhandene_datei,
        melden=melden,
        sichtbar=einst.sichtbar,
    )
    try:
        ergebnis = quelle.belege_holen(umgebung)
    except SitzungAbgelaufen:
        ergebnis = Ergebnis(konto.quelle, konto.name, status="abgelaufen")
    except (BrowserFehlt, ProfilBelegt) as fehler:
        ergebnis = Ergebnis(konto.quelle, konto.name, status="fehler", fehler=str(fehler))
    except Exception as fehler:  # noqa: BLE001 - nie abstürzen, immer melden
        ergebnis = Ergebnis(konto.quelle, konto.name, status="fehler", fehler=f"{type(fehler).__name__}: {str(fehler).splitlines()[0][:200]}")
    if ergebnis.status == "ok":
        zustand.lauf_merken(konto.quelle, konto.name)
    return ergebnis


STATUS_TEXT = {
    "ok": "fertig",
    "anmeldung_noetig": "nicht angemeldet — beim nächsten Start anmelden",
    "abgelaufen": "Anmeldung mittendrin abgelaufen — der nächste Lauf holt den Rest nach",
    "fehler": "Fehler",
    "uebersprungen": "übersprungen",
}


def zusammenfassung(ergebnisse: list[Ergebnis], belegordner: Path) -> str:
    zeilen = ["", "Zusammenfassung", "───────────────"]
    for erg in ergebnisse:
        name = f"{quellen.anzeigename(erg.quelle)} ({erg.konto})"
        zeilen.append(f"{name}: {STATUS_TEXT.get(erg.status, erg.status)}")
        if erg.status in {"ok", "abgelaufen"} or erg.neu or erg.schon_da:
            zeilen.append(f"  {erg.neu} neu, {erg.schon_da} schon vorhanden")
            if erg.kontrolle_neu:
                zeilen.append(f"  {erg.kontrolle_neu} Monatsübersicht(en) neu (Ordner kontrolle)")
            if erg.erwartet is not None and erg.vorhanden is not None:
                passt = "✓ passt" if erg.erwartet == erg.vorhanden else "✗ ABWEICHUNG"
                zeilen.append(
                    f"  Kontrolle: Monatsübersichten nennen {erg.erwartet} Rechnungen, "
                    f"im Ordner liegen {erg.vorhanden} — {passt}"
                )
        for abw in erg.abweichungen:
            zeilen.append(f"  ! {abw}")
        for hinweis in erg.hinweise:
            zeilen.append(f"  · {hinweis}")
        if erg.fehler:
            zeilen.append(f"  Fehler: {erg.fehler}")
    zeilen.append("")
    zeilen.append(f"Belegordner: {belegordner}")
    return "\n".join(zeilen)
