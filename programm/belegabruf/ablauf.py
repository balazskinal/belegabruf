"""Das Gerüst: Konten prüfen, Anmeldungen einsammeln, Belege holen, abliefern."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from belegabruf import pfade, quellen, zustand
from belegabruf import ziele as ziel_verzeichnis
from belegabruf.browser import BrowserFehlt, ProfilBelegt
from belegabruf.einstellungen import Einstellungen, Konto
from belegabruf.protokoll import Protokoll, altes_protokoll_uebernehmen
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung

Melden = Callable[[str], None]


def quelle_fuer(konto: Konto) -> Quelle:
    klasse = quellen.klasse(konto.quelle)
    return klasse(konto, pfade.profilordner(konto.quelle, konto.name))


def protokoll_fuer(einst: Einstellungen, konto: Konto) -> Protokoll:
    return Protokoll(konto.quelle, konto.name, einst.belegordner)


def uebernahme(einst: Einstellungen) -> int:
    """Einmalig das protokoll.csv aus Version 1 übernehmen (siehe protokoll.py)."""
    return altes_protokoll_uebernehmen(einst.belegordner)


def fehlende_dateien(einst: Einstellungen, konto: Konto) -> int:
    """Wie viele geholte Einzelrechnungen fehlen im Belegordner?"""
    return len(protokoll_fuer(einst, konto).fehlende("rechnung"))


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


def abrufen(einst: Einstellungen, konto: Konto, melden: Melden, nachholen: bool = False) -> Ergebnis:
    """Holt die Belege eines Kontos. Stürzt nie ab, sondern meldet im Ergebnis.

    nachholen=True: zusätzlich alles neu holen, was im Protokoll steht, aber im
    Belegordner fehlt (Menüpunkt „Fehlende Dateien neu holen“).
    """
    uebernahme(einst)
    protokoll = protokoll_fuer(einst, konto)
    try:
        ziele = [ziel_verzeichnis.erstellen(name, einst.belegordner) for name in einst.ziele]
        quelle = quelle_fuer(konto)
    except KeyError as fehler:
        return Ergebnis(konto.quelle, konto.name, status="fehler", fehler=str(fehler).strip("'\""))

    def bekannt(schluessel: str) -> bool:
        if nachholen and schluessel.startswith("rechnung:") and protokoll.fehlt_lokal(schluessel):
            return False
        return protokoll.bekannt(schluessel)

    def vorhandene_datei(schluessel: str) -> Path | None:
        datei = protokoll.lokale_datei(schluessel)
        return datei if datei is not None and datei.exists() else None

    def abliefern(beleg: Beleg) -> list[str]:
        lokal: Path | None = None
        for ziel in ziele:
            ort = ziel.abliefern(beleg)
            if ort is not None and lokal is None:
                lokal = ort
        if protokoll.eintrag(beleg.schluessel) is None or beleg.art == "rechnung":
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
    if ergebnis.status in {"ok", "unvollstaendig"}:
        zustand.lauf_merken(konto.quelle, konto.name)
    fehlen = len(protokoll.fehlende("rechnung"))
    if fehlen:
        ergebnis.hinweise.append(
            f"{fehlen} schon geholte Rechnung(en) liegen nicht mehr im Belegordner. Das ist in Ordnung, "
            "wenn du sie weitergegeben hast. Sonst: E → „Fehlende Dateien neu holen“."
        )
    return ergebnis


STATUS_TEXT = {
    "ok": "fertig",
    "anmeldung_noetig": "nicht angemeldet — beim nächsten Start anmelden",
    "abgelaufen": "Anmeldung mittendrin abgelaufen — der nächste Lauf holt den Rest nach",
    "unvollstaendig": "nicht alles geholt — einfach später noch einmal starten, der Rest wird nachgeholt",
    "fehler": "Fehler",
    "uebersprungen": "übersprungen",
}


def zusammenfassung(ergebnisse: list[Ergebnis], belegordner: Path) -> str:
    zeilen = ["", "Zusammenfassung", "───────────────"]
    for erg in ergebnisse:
        name = f"{quellen.anzeigename(erg.quelle)} ({erg.konto})"
        zeilen.append(f"{name}: {STATUS_TEXT.get(erg.status, erg.status)}")
        if erg.status in {"ok", "abgelaufen", "unvollstaendig"} or erg.neu or erg.schon_da:
            zeilen.append(f"  {erg.neu} neu, {erg.schon_da} schon vorhanden")
            if erg.kontrolle_neu:
                zeilen.append(f"  {erg.kontrolle_neu} Monatsübersicht(en) neu (Ordner kontrolle)")
            if erg.erwartet is not None and erg.vorhanden is not None:
                passt = "✓ passt" if erg.erwartet == erg.vorhanden else "✗ ABWEICHUNG"
                uebersicht = "Monatsübersichten nennen" if erg.quelle == "airbnb" else "Übersicht nennt"
                zeilen.append(
                    f"  Kontrolle: {uebersicht} {erg.erwartet} Rechnungen, "
                    f"davon geholt: {erg.vorhanden} — {passt}"
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
