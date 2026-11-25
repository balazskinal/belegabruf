"""Ziel "sevdesk": Belege als Entwurf nach sevDesk hochladen.

**Regel: Dieses Programm ruft bei sevDesk nur auf, was zum Hochladen nötig ist.**
Es liest, ändert oder löscht dort nichts. Erlaubt sind genau diese Aufrufe
(siehe ``ERLAUBT``); jeder andere wird verweigert, bevor er das Netz erreicht:

    POST /Voucher/Factory/uploadTempFile   PDF hochladen (Zwischenablage bei sevDesk)
    POST /Voucher/Factory/saveVoucher      Entwurf anlegen, PDF anhängen
    GET  /SevClient                        nur bei "Einrichten": ist der Schlüssel gültig?

Eingetragen wird nur, was das Programm ohnehin weiß: Belegdatum, Rechnungsnummer
(als Belegnummer), Lieferant als Text "Airbnb", Steuerregel aus den Einstellungen,
Status Entwurf (50), Ausgabe. **Betrag und Konto bleiben leer** — die ergänzt man in
sevDesk. Gebucht wird nichts.

Der API-Schlüssel liegt im Passwortspeicher des Betriebssystems (Bibliothek
``keyring``) und erscheint nie in Ausgaben, Dateien oder Protokollen.
"""

from __future__ import annotations

import json
import secrets
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date

BASIS = "https://my.sevdesk.de/api/v1"
ZEITLIMIT = 60

ERLAUBT = {
    ("POST", "/Voucher/Factory/uploadTempFile"),
    ("POST", "/Voucher/Factory/saveVoucher"),
    ("GET", "/SevClient"),
}

STATUS_ENTWURF = 50
LIEFERANT = {"airbnb": "Airbnb"}


class NichtErlaubt(Exception):
    """Ein Aufruf, der nicht zum Hochladen gehört."""


class SchluesselFehlt(Exception):
    """Im Passwortspeicher liegt kein Schlüssel unter dem eingestellten Eintrag."""


@dataclass
class Antwort:
    status: int
    daten: dict


class Uebertragungsfehler(Exception):
    """sevDesk war nicht erreichbar oder hat nicht geantwortet.

    ``vielleicht_angekommen``: Die Anfrage ging raus, aber die Antwort fehlt. Dann ist
    unklar, ob sevDesk den Entwurf angelegt hat — so ein Beleg wird nicht noch einmal
    geschickt, sonst gäbe es ihn womöglich doppelt."""

    def __init__(self, text: str, vielleicht_angekommen: bool):
        super().__init__(text)
        self.vielleicht_angekommen = vielleicht_angekommen


# ── Schlüssel ────────────────────────────────────────────────────────────────


def schluessel_lesen(dienst: str, konto: str) -> str:
    import keyring

    wert = keyring.get_password(dienst, konto)
    if not wert:
        raise SchluesselFehlt(
            f"Im Passwortspeicher liegt kein sevDesk-Schlüssel unter „{dienst}/{konto}“. "
            "Doppelklick auf „Einrichten“ und den Schlüssel eingeben."
        )
    return wert.strip()


def schluessel_speichern(dienst: str, konto: str, wert: str) -> None:
    import keyring

    keyring.set_password(dienst, konto, wert.strip())


def schluessel_loeschen(dienst: str, konto: str) -> bool:
    import keyring
    from keyring.errors import PasswordDeleteError

    try:
        keyring.delete_password(dienst, konto)
        return True
    except PasswordDeleteError:
        return False


def schluessel_vorhanden(dienst: str, konto: str) -> bool:
    try:
        schluessel_lesen(dienst, konto)
        return True
    except SchluesselFehlt:
        return False


# ── Verbindung ───────────────────────────────────────────────────────────────


def _multipart(feld: str, dateiname: str, inhalt: bytes) -> tuple[bytes, str]:
    grenze = "belegabruf" + secrets.token_hex(12)
    kopf = (
        f"--{grenze}\r\n"
        f'Content-Disposition: form-data; name="{feld}"; filename="{dateiname}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    return kopf + inhalt + f"\r\n--{grenze}--\r\n".encode(), f"multipart/form-data; boundary={grenze}"


class Verbindung:
    """Alle Aufrufe an sevDesk laufen hier durch — und nur die erlaubten."""

    def __init__(self, schluessel: str, oeffnen=None):
        self._schluessel = schluessel
        self._oeffnen = oeffnen or urllib.request.urlopen

    def __repr__(self) -> str:  # nie den Schlüssel zeigen, auch nicht in Fehlerberichten
        return "Verbindung(sevDesk)"

    def _sauber(self, text: str) -> str:
        return text.replace(self._schluessel, "***") if self._schluessel else text

    def aufrufen(self, methode: str, pfad: str, *, json_daten: dict | None = None,
                 datei: tuple[str, bytes] | None = None) -> Antwort:
        if (methode, pfad) not in ERLAUBT:
            raise NichtErlaubt(f"{methode} {pfad} gehört nicht zum Hochladen und wird nicht ausgeführt.")
        kopf = {"Authorization": self._schluessel, "Accept": "application/json",
                "User-Agent": "belegabruf"}
        rumpf = None
        if datei is not None:
            rumpf, kopf["Content-Type"] = _multipart("file", *datei)
        elif json_daten is not None:
            rumpf = json.dumps(json_daten).encode("utf-8")
            kopf["Content-Type"] = "application/json"
        anfrage = urllib.request.Request(BASIS + pfad, data=rumpf, headers=kopf, method=methode)
        try:
            with self._oeffnen(anfrage, timeout=ZEITLIMIT) as antwort:
                return Antwort(antwort.status, _json(antwort.read()))
        except urllib.error.HTTPError as fehler:
            return Antwort(fehler.code, _json(fehler.read()))
        except (TimeoutError, socket.timeout) as fehler:
            raise Uebertragungsfehler(
                "sevDesk hat nicht rechtzeitig geantwortet.", vielleicht_angekommen=True) from fehler
        except urllib.error.URLError as fehler:
            grund = fehler.reason
            if isinstance(grund, (TimeoutError, socket.timeout)):
                raise Uebertragungsfehler(
                    "sevDesk hat nicht rechtzeitig geantwortet.", vielleicht_angekommen=True) from fehler
            raise Uebertragungsfehler(
                f"sevDesk ist nicht erreichbar (kein Internet?): {self._sauber(str(grund))}",
                vielleicht_angekommen=False) from fehler
        except (ConnectionError, OSError) as fehler:
            # Verbindung mittendrin abgebrochen: Die Anfrage kann schon angekommen sein.
            raise Uebertragungsfehler(
                f"Die Verbindung zu sevDesk ist abgebrochen: {self._sauber(str(fehler))}",
                vielleicht_angekommen=True) from fehler

    def fehlertext(self, antwort: Antwort) -> str:
        """Die Meldung von sevDesk im Klartext — ohne Schlüssel."""
        fehler = antwort.daten.get("error") if isinstance(antwort.daten, dict) else None
        text = ""
        if isinstance(fehler, dict):
            text = str(fehler.get("message") or "")
        elif fehler:
            text = str(fehler)
        if not text and isinstance(antwort.daten, dict):
            text = str(antwort.daten.get("message") or "")
        if antwort.status == 401:
            vorne = "sevDesk lehnt den API-Schlüssel ab (falsch oder abgelaufen)."
            return f"{vorne} Meldung von sevDesk: {self._sauber(text)}" if text else vorne
        text = self._sauber(text) or "keine Meldung"
        return f"sevDesk meldet Fehler {antwort.status}: {text}"


def _json(rumpf: bytes) -> dict:
    try:
        daten = json.loads(rumpf.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {"objects": daten}


# ── Hochladen ────────────────────────────────────────────────────────────────


class Abgelehnt(Exception):
    """sevDesk hat geantwortet und abgelehnt — der Entwurf wurde sicher nicht angelegt."""

    def __init__(self, text: str, schluessel_falsch: bool = False):
        super().__init__(text)
        self.schluessel_falsch = schluessel_falsch


def entwurf(quelle: str, rechnungsdatum: date | None, rechnungsnummer: str, steuerregel: str,
            gutschrift: bool, temp_datei: str) -> dict:
    """Der Rumpf für saveVoucher: nur, was das Programm weiß; ohne Positionen."""
    beleg = {
        "objectName": "Voucher",
        "mapAll": True,
        "status": STATUS_ENTWURF,
        "creditDebit": "C",  # Ausgabe
        "voucherType": "VOU",  # normaler Beleg
        "supplier": None,
        "supplierName": LIEFERANT.get(quelle, quelle.capitalize()),
        "description": f"{rechnungsnummer} (Gutschrift)" if gutschrift else rechnungsnummer,
        "taxRule": {"id": str(steuerregel), "objectName": "TaxRule"},
    }
    if rechnungsdatum is not None:
        beleg["voucherDate"] = rechnungsdatum.strftime("%d.%m.%Y")
    return {"voucher": beleg, "voucherPosSave": [], "voucherPosDelete": None, "filename": temp_datei}


class SevDesk:
    """Lädt einzelne Belege hoch. Kennt das Protokoll nicht — das macht ablauf.py."""

    name = "sevdesk"

    def __init__(self, verbindung: Verbindung, steuerregel: str):
        self.verbindung = verbindung
        self.steuerregel = steuerregel

    def hochladen(self, *, quelle: str, dateiname: str, inhalt: bytes, rechnungsdatum: date | None,
                  rechnungsnummer: str, gutschrift: bool, vor_entwurf=lambda: None) -> None:
        """Legt einen Entwurf an. Wirft ``Abgelehnt`` (sicher nicht angelegt) oder
        ``Uebertragungsfehler`` (``vielleicht_angekommen`` sagt, ob es unklar ist).

        ``vor_entwurf`` wird direkt vor dem Anlegen aufgerufen. Dort merkt sich das
        Programm „unklar“ — bricht der Rechner mittendrin ab, wird der Beleg so nicht
        ein zweites Mal geschickt."""
        # Schritt 1: Datei hochladen. Scheitert das, ist in sevDesk noch kein Beleg entstanden.
        try:
            antwort = self.verbindung.aufrufen(
                "POST", "/Voucher/Factory/uploadTempFile", datei=(dateiname, inhalt))
        except Uebertragungsfehler as fehler:
            raise Uebertragungsfehler(str(fehler), vielleicht_angekommen=False) from fehler
        if antwort.status >= 400:
            raise Abgelehnt(self.verbindung.fehlertext(antwort), schluessel_falsch=antwort.status == 401)
        objekte = antwort.daten.get("objects") or {}
        temp_datei = objekte.get("filename") if isinstance(objekte, dict) else None
        if not temp_datei:
            raise Abgelehnt("sevDesk hat die Datei angenommen, aber keinen Dateinamen zurückgegeben.")

        # Schritt 2: Entwurf anlegen.
        rumpf = entwurf(quelle, rechnungsdatum, rechnungsnummer, self.steuerregel, gutschrift, temp_datei)
        vor_entwurf()
        antwort = self.verbindung.aufrufen("POST", "/Voucher/Factory/saveVoucher", json_daten=rumpf)
        if 400 <= antwort.status < 500:
            raise Abgelehnt(self.verbindung.fehlertext(antwort), schluessel_falsch=antwort.status == 401)
        if antwort.status >= 500:
            # Serverfehler: sevDesk kann den Entwurf trotzdem angelegt haben.
            raise Uebertragungsfehler(self.verbindung.fehlertext(antwort), vielleicht_angekommen=True)


def schluessel_pruefen(verbindung: Verbindung) -> str | None:
    """Nur für "Einrichten": None, wenn der Schlüssel gilt, sonst eine Meldung."""
    try:
        antwort = verbindung.aufrufen("GET", "/SevClient")
    except Uebertragungsfehler as fehler:
        return str(fehler)
    if antwort.status == 200:
        return None
    return verbindung.fehlertext(antwort)
