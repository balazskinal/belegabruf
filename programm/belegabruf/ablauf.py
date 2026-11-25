"""Das Gerüst: Konten prüfen, Anmeldungen einsammeln, Belege holen, abliefern."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from belegabruf import pfade, quellen, zustand
from belegabruf import ziele as ziel_verzeichnis
from belegabruf.browser import BrowserFehlt, ProfilBelegt
from belegabruf.einstellungen import Einstellungen, Konto
from belegabruf.protokoll import Protokoll, altes_protokoll_uebernehmen
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung
from belegabruf.ziele import sevdesk

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


def sevdesk_vorbereiten(einst: Einstellungen, protokoll: Protokoll) -> int:
    """Ziel sevDesk ein- oder ausgeschaltet? Beim Einschalten gilt alles, was bis
    jetzt geholt ist, als schon in sevDesk (wurde von Hand hochgeladen). Gibt die
    Zahl der so markierten Rechnungen zurück."""
    if not einst.sevdesk_an:
        protokoll.sevdesk_schalten(False)
        return 0
    if protokoll.sevdesk_war_an():
        return 0
    anzahl = protokoll.als_schon_in_sevdesk_markieren()
    protokoll.sevdesk_schalten(True)
    return anzahl


def hochladen(einst: Einstellungen, protokoll: Protokoll, erg: Ergebnis, melden: Melden,
              verbindung: sevdesk.Verbindung | None = None) -> None:
    """Lädt alle Rechnungen hoch, die noch nicht in sevDesk sind — neue und solche,
    bei denen es letztes Mal nicht geklappt hat. Hält beim ersten Fehler an: Was
    übrig bleibt, versucht der nächste Lauf."""
    erg.sevdesk = True
    offen = protokoll.upload_offen()
    if not offen:
        return
    if verbindung is None:
        try:
            verbindung = sevdesk.Verbindung(sevdesk.schluessel_lesen(*einst.sevdesk.dienst_und_konto))
        except sevdesk.SchluesselFehlt as fehler:
            erg.upload_fehler = str(fehler)
            erg.nicht_hochgeladen = len(offen)
            return
        except Exception as fehler:  # noqa: BLE001 - Passwortspeicher gesperrt o. Ä.
            erg.upload_fehler = (f"Der Passwortspeicher ließ sich nicht lesen ({type(fehler).__name__}). "
                                 "Beim nächsten Start noch einmal versuchen.")
            erg.nicht_hochgeladen = len(offen)
            return
    try:
        ziel = sevdesk.SevDesk(verbindung, einst.sevdesk.steuerregel)
    except sevdesk.SteuerregelFehlt as fehler:
        erg.upload_fehler = str(fehler)
        erg.nicht_hochgeladen = len(offen)
        return
    ohne_datei = 0
    melden(f"{len(offen)} Rechnung(en) werden nach sevDesk hochgeladen …")
    for schluessel in offen:
        zeile = protokoll.eintrag(schluessel) or {}
        datei = protokoll.lokale_datei(schluessel)
        if datei is None or not datei.exists():
            ohne_datei += 1
            continue
        nummer = zeile.get("rechnungsnummer") or ""
        try:
            datum = date.fromisoformat(zeile.get("rechnungsdatum") or "")
        except ValueError:
            datum = None
        try:
            beleg_id = ziel.hochladen(
                quelle=zeile.get("quelle") or protokoll.quelle, dateiname=datei.name,
                inhalt=datei.read_bytes(), rechnungsdatum=datum, rechnungsnummer=nummer,
                gutschrift="_Gutschrift" in datei.name,
                vor_entwurf=lambda: protokoll.ziel_ergaenzen(schluessel, "sevdesk-unklar"),
            )
        except sevdesk.Abgelehnt as fehler:
            protokoll.ziel_entfernen(schluessel, "sevdesk-unklar")  # sicher nicht angelegt
            erg.upload_fehler = f"Rechnung {nummer}: {fehler}"
            break
        except sevdesk.Uebertragungsfehler as fehler:
            if fehler.vielleicht_angekommen:
                erg.upload_unklar.append(nummer)
            else:
                protokoll.ziel_entfernen(schluessel, "sevdesk-unklar")
            erg.upload_fehler = f"Rechnung {nummer}: {fehler}"
            break
        protokoll.hochgeladen(schluessel, beleg_id)
        erg.hochgeladen += 1
    erg.nicht_hochgeladen = len(protokoll.upload_offen())
    if ohne_datei:
        erg.hinweise.append(
            f"{ohne_datei} Rechnung(en) sind noch nicht in sevDesk, liegen aber nicht mehr im Belegordner. "
            "E → „Fehlende Dateien neu holen“, dann werden sie hochgeladen."
        )


def abrufen(einst: Einstellungen, konto: Konto, melden: Melden, nachholen: bool = False) -> Ergebnis:
    """Holt die Belege eines Kontos. Stürzt nie ab, sondern meldet im Ergebnis.

    nachholen=True: zusätzlich alles neu holen, was im Protokoll steht, aber im
    Belegordner fehlt (Menüpunkt „Fehlende Dateien neu holen“).
    """
    uebernahme(einst)
    protokoll = protokoll_fuer(einst, konto)
    markiert = sevdesk_vorbereiten(einst, protokoll)
    try:
        # Lokale Ziele (Ordner) beim Abruf; sevDesk lädt danach hoch, was noch fehlt.
        ziele = [ziel_verzeichnis.erstellen(name, einst.belegordner)
                 for name in einst.ziele if name != "sevdesk"]
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
            # Schon in sevDesk? Das bleibt so, auch wenn die Datei neu geholt wird — nie doppelt.
            bisher = [z for z in protokoll.ziele_von(beleg.schluessel) if z.startswith("sevdesk")]
            protokoll.eintragen(beleg, lokal, [z.name for z in ziele] + bisher)
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
    if einst.sevdesk_an:
        ergebnis.als_schon_markiert = markiert
        try:
            hochladen(einst, protokoll, ergebnis, melden)
        except Exception as fehler:  # noqa: BLE001 - nie abstürzen, immer melden
            ergebnis.upload_fehler = f"Hochladen abgebrochen ({type(fehler).__name__})."
            ergebnis.nicht_hochgeladen = len(protokoll.upload_offen())
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
                zeilen.append(
                    f"  Kontrolle: Monatsübersichten nennen {erg.erwartet} Rechnungen, "
                    f"davon geholt: {erg.vorhanden} — {passt}"
                )
        if erg.sevdesk:
            if erg.als_schon_markiert:
                zeilen.append(f"  sevDesk eingeschaltet: {erg.als_schon_markiert} schon geholte Rechnung(en) "
                              "gelten als schon in sevDesk und werden nicht hochgeladen.")
            if erg.hochgeladen:
                zeilen.append(f"  sevDesk: {erg.hochgeladen} als Entwurf hochgeladen "
                              "(Betrag und Konto dort ergänzen)")
            if erg.nicht_hochgeladen:
                zeilen.append(f"  sevDesk: {erg.nicht_hochgeladen} noch nicht hochgeladen — liegen im Belegordner, "
                              "der nächste Lauf versucht es erneut")
            if not erg.hochgeladen and not erg.nicht_hochgeladen and not erg.upload_unklar:
                zeilen.append("  sevDesk: nichts Neues hochzuladen")
            if erg.upload_fehler:
                zeilen.append(f"  ! sevDesk: {erg.upload_fehler}")
            for nummer in erg.upload_unklar:
                zeilen.append(
                    f"  ! sevDesk: Bei Rechnung {nummer} kam keine Antwort. Ob der Entwurf angelegt ist, ist unklar — "
                    "bitte in sevDesk nachsehen. Fehlt er, von Hand hochladen. (Das Programm schickt ihn nicht "
                    "noch einmal, damit er nicht doppelt ankommt.)")
        for abw in erg.abweichungen:
            zeilen.append(f"  ! {abw}")
        for hinweis in erg.hinweise:
            zeilen.append(f"  · {hinweis}")
        if erg.fehler:
            zeilen.append(f"  Fehler: {erg.fehler}")
    zeilen.append("")
    zeilen.append(f"Belegordner: {belegordner}")
    return "\n".join(zeilen)
