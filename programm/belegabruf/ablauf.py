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
from belegabruf.ziele import mail
from belegabruf.ziele.basis import Abgelehnt, Lieferziel, Sendung, Unklar

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


# ── Lieferziele (Mail je Empfänger; später weitere) ──────────────────────────


def lieferziel_namen(einst: Einstellungen) -> list[str]:
    """Die eingeschalteten Lieferziele, wie sie im Protokoll heißen."""
    namen: list[str] = []
    if einst.mail_an:
        for adresse in einst.mail.empfaenger:
            name = mail.ziel_name(adresse)
            if name not in namen:
                namen.append(name)
    return namen


def lieferziele_erstellen(einst: Einstellungen) -> list[Lieferziel]:
    """Baut die Lieferziele. Liest dazu das Passwort aus dem Passwortspeicher."""
    ziele: list[Lieferziel] = []
    if einst.mail_an and einst.mail.empfaenger:
        postausgang = mail.Postausgang(einst.mail, mail.passwort_lesen(*einst.mail.dienst_und_konto))
        gesehen = set()
        for adresse in einst.mail.empfaenger:
            if mail.ziel_name(adresse) not in gesehen:
                gesehen.add(mail.ziel_name(adresse))
                ziele.append(mail.MailZiel(postausgang, adresse))
    return ziele


def _anzeige(name: str) -> str:
    return f"Mail an {name.removeprefix('mail:')}" if name.startswith("mail:") else name


def _sendung(protokoll: Protokoll, schluessel: str) -> Sendung | None:
    zeile = protokoll.eintrag(schluessel) or {}
    datei = protokoll.lokale_datei(schluessel)
    if datei is None or not datei.exists():
        return None
    try:
        datum = date.fromisoformat(zeile.get("rechnungsdatum") or "")
    except ValueError:
        datum = None
    return Sendung(
        quelle=zeile.get("quelle") or protokoll.quelle, schluessel=schluessel,
        rechnungsnummer=zeile.get("rechnungsnummer") or "", rechnungsdatum=datum,
        gutschrift="_Gutschrift" in datei.name, dateiname=datei.name, inhalt=datei.read_bytes(),
    )


def liefern(einst: Einstellungen, protokoll: Protokoll, erg: Ergebnis, melden: Melden,
            markiert: dict[str, int] | None = None, ziele: list[Lieferziel] | None = None) -> None:
    """Schickt an jedes Lieferziel, was ihm laut Protokoll noch fehlt — neue
    Rechnungen und solche, bei denen es letztes Mal nicht geklappt hat. Nie doppelt:
    Direkt vor dem Senden steht „unklar“ im Protokoll, erst danach „geliefert“."""
    namen = lieferziel_namen(einst)
    for name in namen:
        erg.lieferungen[name] = {"anzeige": _anzeige(name), "geliefert": 0, "offen": 0, "fehler": "",
                                 "unklar": [], "schon_markiert": (markiert or {}).get(name, 0)}
    if not namen or not any(protokoll.offen_fuer(n) for n in namen):
        return
    if ziele is None:
        try:
            ziele = lieferziele_erstellen(einst)
        except mail.PasswortFehlt as fehler:
            ziele, grund = [], str(fehler)
        except Exception as fehler:  # noqa: BLE001 - Passwortspeicher gesperrt o. Ä.
            ziele, grund = [], (f"Der Passwortspeicher ließ sich nicht lesen ({type(fehler).__name__}). "
                                "Beim nächsten Start noch einmal versuchen.")
        if not ziele:
            for name in namen:
                erg.lieferungen[name]["fehler"] = grund
                erg.lieferungen[name]["offen"] = len(protokoll.offen_fuer(name))
            return

    alle_anhalten = False
    ohne_datei: set[str] = set()
    try:
        for ziel in ziele:
            stand = erg.lieferungen[ziel.name]
            offen = protokoll.offen_fuer(ziel.name)
            if alle_anhalten or not offen:
                continue
            melden(f"{len(offen)} Rechnung(en): {ziel.anzeigename} …")
            for schluessel in offen:
                sendung = _sendung(protokoll, schluessel)
                if sendung is None:
                    ohne_datei.add(schluessel)
                    continue
                try:
                    ziel.senden(sendung, lambda: protokoll.als_unklar(schluessel, ziel.name))
                except Abgelehnt as fehler:
                    protokoll.als_offen(schluessel, ziel.name)  # sicher nicht angekommen
                    stand["fehler"] = f"Rechnung {sendung.rechnungsnummer}: {fehler}"
                    alle_anhalten = fehler.alle_anhalten
                    break
                except Unklar as fehler:
                    stand["unklar"].append(sendung.rechnungsnummer)
                    stand["fehler"] = f"Rechnung {sendung.rechnungsnummer}: {fehler}"
                    alle_anhalten = True  # Verbindung ist weg; nächster Lauf
                    break
                protokoll.als_geliefert(schluessel, ziel.name)
                stand["geliefert"] += 1
    finally:
        for ziel in ziele:
            try:
                ziel.schliessen()
            except Exception:  # noqa: BLE001
                pass
    for name in namen:
        erg.lieferungen[name]["offen"] = len(protokoll.offen_fuer(name))
    if ohne_datei:
        erg.hinweise.append(
            f"{len(ohne_datei)} Rechnung(en) sind noch nicht überall angekommen, liegen aber nicht mehr im "
            "Belegordner. E → „Fehlende Dateien neu holen“, dann werden sie verschickt."
        )


def abrufen(einst: Einstellungen, konto: Konto, melden: Melden, nachholen: bool = False) -> Ergebnis:
    """Holt die Belege eines Kontos. Stürzt nie ab, sondern meldet im Ergebnis.

    nachholen=True: zusätzlich alles neu holen, was im Protokoll steht, aber im
    Belegordner fehlt (Menüpunkt „Fehlende Dateien neu holen“).
    """
    uebernahme(einst)
    protokoll = protokoll_fuer(einst, konto)
    # Erst die Schalter abgleichen: Beim allerersten Einschalten eines Ziels gilt alles
    # bis jetzt Geholte als geliefert — bevor dieser Lauf Neues holt.
    markiert = protokoll.ziele_abgleichen(lieferziel_namen(einst))
    try:
        # Lokale Ziele (Ordner) beim Abruf; Lieferziele (Mail) schicken danach, was fehlt.
        ziele = [ziel_verzeichnis.erstellen(name, einst.belegordner)
                 for name in einst.ziele if name not in ziel_verzeichnis.LIEFERZIELE]
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
            # Was schon verschickt ist, bleibt so — auch wenn die Datei neu geholt wird.
            protokoll.eintragen(beleg, lokal, [z.name for z in ziele]
                                + protokoll.bisherige_lieferungen(beleg.schluessel))
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
    try:
        liefern(einst, protokoll, ergebnis, melden, markiert)
    except Exception as fehler:  # noqa: BLE001 - nie abstürzen, immer melden
        for name, stand in ergebnis.lieferungen.items():
            stand["fehler"] = stand["fehler"] or f"Versand abgebrochen ({type(fehler).__name__})."
            stand["offen"] = len(protokoll.offen_fuer(name))
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
        for stand in erg.lieferungen.values():
            name = stand["anzeige"]
            if stand["schon_markiert"]:
                zeilen.append(f"  {name}: neu eingeschaltet — {stand['schon_markiert']} schon geholte "
                              "Rechnung(en) gelten als verschickt und gehen nicht raus")
            teile = []
            if stand["geliefert"]:
                teile.append(f"{stand['geliefert']} verschickt")
            if stand["offen"]:
                teile.append(f"{stand['offen']} noch nicht verschickt (liegen im Belegordner, "
                             "der nächste Lauf versucht es erneut)")
            if teile:
                zeilen.append(f"  {name}: " + ", ".join(teile))
            elif not stand["unklar"]:
                zeilen.append(f"  {name}: nichts Neues zu verschicken")
            if stand["fehler"]:
                zeilen.append(f"  ! {name}: {stand['fehler']}")
            for nummer in stand["unklar"]:
                zeilen.append(
                    f"  ! {name}: Bei Rechnung {nummer} kam nach dem Senden keine Antwort. Ob die Mail "
                    "angekommen ist, ist unklar — bitte beim Empfänger nachsehen und sie notfalls von Hand "
                    "schicken. (Das Programm schickt sie nicht noch einmal, damit sie nicht doppelt ankommt.)")
        for abw in erg.abweichungen:
            zeilen.append(f"  ! {abw}")
        for hinweis in erg.hinweise:
            zeilen.append(f"  · {hinweis}")
        if erg.fehler:
            zeilen.append(f"  Fehler: {erg.fehler}")
    zeilen.append("")
    zeilen.append(f"Belegordner: {belegordner}")
    return "\n".join(zeilen)
