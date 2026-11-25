"""Ziel sevDesk — nur gegen eine Attrappe, nie gegen ein echtes sevDesk.

Alle Daten sind erfunden. Der "Schlüssel" ist ein Platzhalter.
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest

from belegabruf import ablauf, einstellungen, pfade
from belegabruf.einstellungen import Einstellungen, Konto, SevDeskEinstellung
from belegabruf.protokoll import Protokoll
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle
from belegabruf.ziele import sevdesk

PLATZHALTER = "test-schluessel-0000"


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    return tmp_path / "daten"


class _Antwort(io.BytesIO):
    def __init__(self, status: int, daten: dict):
        super().__init__(json.dumps(daten).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Attrappe:
    """Spielt sevDesk. Merkt sich jeden Aufruf (ohne Kopfzeilen)."""

    def __init__(self):
        self.aufrufe: list[tuple[str, str]] = []
        self.entwuerfe: list[dict] = []
        self.kopfzeilen: list[dict] = []
        self.verhalten = "ok"  # ok | 401 | ablehnen | kein_netz | zeitueberschreitung | 500

    def __call__(self, anfrage, timeout=None):
        pfad = anfrage.full_url.removeprefix(sevdesk.BASIS)
        self.aufrufe.append((anfrage.get_method(), pfad))
        self.kopfzeilen.append(dict(anfrage.header_items()))
        if self.verhalten == "kein_netz":
            raise urllib.error.URLError(OSError("Name or service not known"))
        if self.verhalten == "401":
            raise urllib.error.HTTPError(anfrage.full_url, 401, "Unauthorized", {},
                                         io.BytesIO(b'{"error":{"message":"Authentication required"}}'))
        if pfad.endswith("uploadTempFile"):
            assert b"%PDF" in anfrage.data
            return _Antwort(201, {"objects": {"filename": f"temp{len(self.aufrufe)}.pdf"}})
        if pfad.endswith("saveVoucher"):
            if self.verhalten == "ablehnen":
                raise urllib.error.HTTPError(
                    anfrage.full_url, 422, "Unprocessable", {},
                    io.BytesIO(b'{"error":{"message":"voucherPos must not be empty"}}'))
            if self.verhalten == "zeitueberschreitung":
                raise TimeoutError("timed out")
            if self.verhalten == "500":
                raise urllib.error.HTTPError(anfrage.full_url, 500, "Server Error", {}, io.BytesIO(b"{}"))
            self.entwuerfe.append(json.loads(anfrage.data))
            return _Antwort(201, {"objects": {"voucher": {"id": str(900 + len(self.entwuerfe))}}})
        if pfad == "/SevClient":
            return _Antwort(200, {"objects": [{"id": "1"}]})
        raise AssertionError(f"Unerwarteter Aufruf {pfad}")


def _pdf(text: str) -> bytes:
    import pymupdf

    dok = pymupdf.open()
    dok.new_page().insert_text((50, 100), text)
    inhalt = dok.tobytes()
    dok.close()
    return inhalt


def _einst(tmp_path: Path, an: bool = True) -> Einstellungen:
    return Einstellungen(
        belegordner=tmp_path / "Belege",
        konten=[Konto("airbnb", "privat")],
        ziele=["ordner", "sevdesk"] if an else ["ordner"],
        sevdesk=SevDeskEinstellung(steuerregel="14"),
    )


class Falsch(Quelle):
    """Quelle ohne Browser: liefert vorgegebene Rechnungen."""

    name = "airbnb"
    anzeigename = "Airbnb"
    rechnungen: list[tuple[str, str, str]] = []  # (kennung, datum, nummer)

    def sitzung_pruefen(self):
        return True

    def anmelden_lassen(self, melden):
        return True

    def belege_holen(self, umgebung):
        erg = Ergebnis(self.name, self.konto.name)
        for kennung, datum, nummer in self.rechnungen:
            schluessel = f"rechnung:{kennung}"
            if umgebung.bekannt(schluessel):
                erg.schon_da += 1
                continue
            gutschrift = kennung.startswith("g")
            umgebung.abliefern(Beleg(
                quelle="airbnb", konto=self.konto.name, art="rechnung", schluessel=schluessel,
                dateiname=f"{datum}_HMX_{nummer}{'_Gutschrift' if gutschrift else ''}.pdf",
                inhalt=_pdf(nummer), jahr=int(datum[:4]),
                rechnungsdatum=date.fromisoformat(datum), rechnungsnummer=nummer,
            ))
            erg.neu += 1
        return erg


@pytest.fixture
def attrappe(monkeypatch):
    a = Attrappe()
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Falsch(konto, Path("/gibt-es-nicht")))
    monkeypatch.setattr(sevdesk, "schluessel_lesen", lambda dienst, konto: PLATZHALTER)
    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", a)
    monkeypatch.setattr(ablauf.zustand, "lauf_merken", lambda *a: None)
    return a


def _lauf(einst, nachholen=False) -> Ergebnis:
    return ablauf.abrufen(einst, einst.konten[0], lambda t: None, nachholen=nachholen)


def _protokoll(einst) -> Protokoll:
    return Protokoll("airbnb", "privat", einst.belegordner)


# ── Erlaubte Aufrufe ─────────────────────────────────────────────────────────


def test_nur_upload_aufrufe_erlaubt():
    verbindung = sevdesk.Verbindung(PLATZHALTER, oeffnen=lambda *a, **k: pytest.fail("darf nicht raus"))
    for methode, pfad in [("GET", "/Voucher"), ("DELETE", "/Voucher/1"), ("PUT", "/Voucher/1"),
                          ("GET", "/Contact"), ("POST", "/Voucher/1/bookAmount"),
                          ("GET", "/SevClient/1"), ("POST", "/SevClient")]:
        with pytest.raises(sevdesk.NichtErlaubt):
            verbindung.aufrufen(methode, pfad)
    assert sevdesk.ERLAUBT == {
        ("POST", "/Voucher/Factory/uploadTempFile"),
        ("POST", "/Voucher/Factory/saveVoucher"),
        ("GET", "/SevClient"),
    }


def test_schluessel_nie_in_ausgabe():
    verbindung = sevdesk.Verbindung(PLATZHALTER)
    assert PLATZHALTER not in repr(verbindung)
    antwort = sevdesk.Antwort(400, {"error": {"message": f"token {PLATZHALTER} invalid"}})
    assert PLATZHALTER not in verbindung.fehlertext(antwort)


# ── Abnahme-Szenarien ────────────────────────────────────────────────────────


def test_alter_bestand_wird_nicht_hochgeladen(tmp_path, attrappe):
    einst = _einst(tmp_path, an=False)
    Falsch.rechnungen = [("a1", "2026-10-01", "AIUC-1"), ("a2", "2026-10-02", "AIUC-2")]
    _lauf(einst)  # Version 1.x ohne sevDesk
    assert attrappe.aufrufe == []

    einst = _einst(tmp_path, an=True)
    Falsch.rechnungen += [("a3", "2026-11-20", "AIUC-3")]
    erg = _lauf(einst)
    assert erg.als_schon_markiert == 2
    assert erg.hochgeladen == 1
    assert [e["voucher"]["description"] for e in attrappe.entwuerfe] == ["AIUC-3"]
    p = _protokoll(einst)
    assert "sevdesk-schon" in p.ziele_von("rechnung:a1")
    assert "sevdesk" in p.ziele_von("rechnung:a3")


def test_entwurf_enthaelt_nur_bekanntes(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-9"), ("g1", "2026-11-04", "AIUC-9")]
    _lauf(einst)  # erster Lauf: nichts vorher → beide neu nach dem Einschalten
    assert attrappe.aufrufe == [
        ("POST", "/Voucher/Factory/uploadTempFile"), ("POST", "/Voucher/Factory/saveVoucher"),
        ("POST", "/Voucher/Factory/uploadTempFile"), ("POST", "/Voucher/Factory/saveVoucher"),
    ]
    rechnung, gutschrift = attrappe.entwuerfe
    v = rechnung["voucher"]
    assert v["status"] == 50 and v["creditDebit"] == "C" and v["voucherType"] == "VOU"
    assert v["supplierName"] == "Airbnb" and "supplier" not in v
    assert v["voucherDate"] == "03.11.2026" and v["description"] == "AIUC-9"
    assert v["taxRule"] == {"id": "14", "objectName": "TaxRule"}
    assert set(rechnung) == {"voucher", "filename"}  # wie in der echten Probe: keine Positionen
    assert rechnung["filename"].startswith("temp")
    assert not any(k in v for k in ("sumGross", "sumNet", "sumTax"))  # kein Betrag
    assert gutschrift["voucher"]["description"] == "AIUC-9 (Gutschrift)"
    assert all(k["Authorization"] == PLATZHALTER for k in attrappe.kopfzeilen)
    p = _protokoll(einst)
    assert p.eintrag("rechnung:a1")["sevdesk_id"] == "901"
    assert p.ziele_von("rechnung:a1") == ["ordner", "sevdesk"]


def test_zweiter_lauf_laedt_nichts_doppelt(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    assert _lauf(einst).hochgeladen == 1
    erg = _lauf(einst)
    assert erg.hochgeladen == 0 and erg.nicht_hochgeladen == 0
    assert len(attrappe.entwuerfe) == 1


def test_fehlende_datei_neu_holen_laedt_nicht_doppelt(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(einst)
    datei = _protokoll(einst).lokale_datei("rechnung:a1")
    datei.unlink()
    _lauf(einst, nachholen=True)
    assert datei.exists()
    assert len(attrappe.entwuerfe) == 1
    assert "sevdesk" in _protokoll(einst).ziele_von("rechnung:a1")


def test_falscher_schluessel_verstaendlich_nichts_verloren(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1"), ("a2", "2026-11-04", "AIUC-2")]
    attrappe.verhalten = "401"
    erg = _lauf(einst)
    assert erg.hochgeladen == 0 and erg.nicht_hochgeladen == 2
    assert "lehnt den API-Schlüssel ab" in erg.upload_fehler
    assert PLATZHALTER not in erg.upload_fehler
    assert len(attrappe.aufrufe) == 1  # hält beim ersten Fehler an
    p = _protokoll(einst)
    assert p.upload_offen() == ["rechnung:a1", "rechnung:a2"]
    assert p.lokale_datei("rechnung:a1").exists()
    text = ablauf.zusammenfassung([erg], einst.belegordner)
    assert "noch nicht hochgeladen" in text and PLATZHALTER not in text

    attrappe.verhalten = "ok"  # Schlüssel ausgetauscht → nächster Lauf holt es nach
    erg = _lauf(einst)
    assert erg.hochgeladen == 2 and erg.nicht_hochgeladen == 0


def test_sevdesk_lehnt_entwurf_ab(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    attrappe.verhalten = "ablehnen"
    erg = _lauf(einst)
    assert "voucherPos must not be empty" in erg.upload_fehler
    assert "422" in erg.upload_fehler
    assert _protokoll(einst).upload_offen() == ["rechnung:a1"]


def test_kein_netz_naechster_lauf_versucht_erneut(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    attrappe.verhalten = "kein_netz"
    erg = _lauf(einst)
    assert "nicht erreichbar" in erg.upload_fehler and erg.nicht_hochgeladen == 1
    attrappe.verhalten = "ok"
    assert _lauf(einst).hochgeladen == 1


@pytest.mark.parametrize("verhalten", ["zeitueberschreitung", "500"])
def test_antwort_bleibt_aus_wird_nicht_wiederholt(tmp_path, attrappe, verhalten):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    attrappe.verhalten = verhalten
    erg = _lauf(einst)
    assert erg.upload_unklar == ["AIUC-1"]
    assert "nachsehen" in ablauf.zusammenfassung([erg], einst.belegordner)
    attrappe.verhalten = "ok"
    vorher = len(attrappe.aufrufe)
    erg = _lauf(einst)
    assert len(attrappe.aufrufe) == vorher  # nicht noch einmal geschickt
    assert erg.nicht_hochgeladen == 0


def test_absturz_waehrend_entwurf_wird_nicht_wiederholt(tmp_path, attrappe, monkeypatch):
    """Rechner geht aus, nachdem saveVoucher losgeschickt wurde."""
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]

    def absturz(anfrage, timeout=None):
        if anfrage.full_url.endswith("saveVoucher"):
            raise KeyboardInterrupt
        return attrappe(anfrage, timeout)

    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", absturz)
    with pytest.raises(KeyboardInterrupt):
        _lauf(einst)
    assert "sevdesk-unklar" in _protokoll(einst).ziele_von("rechnung:a1")
    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", attrappe)
    _lauf(einst)
    assert attrappe.entwuerfe == []


def test_schluessel_fehlt(tmp_path, attrappe, monkeypatch):
    def fehlt(dienst, konto):
        raise sevdesk.SchluesselFehlt("kein Schlüssel")

    monkeypatch.setattr(sevdesk, "schluessel_lesen", fehlt)
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(einst)
    assert erg.upload_fehler == "kein Schlüssel" and erg.nicht_hochgeladen == 1
    assert attrappe.aufrufe == []


def test_aus_und_wieder_an_markiert_nichts(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(einst)
    Falsch.rechnungen += [("a2", "2026-11-05", "AIUC-2")]
    _lauf(_einst(tmp_path, an=False))  # ausgeschaltet: a2 kommt nur in den Ordner
    assert len(attrappe.entwuerfe) == 1
    erg = _lauf(einst)  # wieder an: nichts markiert, a2 wird hochgeladen
    assert erg.als_schon_markiert == 0 and erg.hochgeladen == 1
    assert [e["voucher"]["description"] for e in attrappe.entwuerfe] == ["AIUC-1", "AIUC-2"]


def test_aus_und_wieder_an_laedt_gescheiterte_hoch(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    attrappe.verhalten = "401"
    assert _lauf(einst).nicht_hochgeladen == 1  # gescheitert
    _lauf(_einst(tmp_path, an=False))
    _lauf(_einst(tmp_path, an=False))  # mehrmals aus ändert nichts
    attrappe.verhalten = "ok"
    erg = _lauf(einst)
    assert erg.als_schon_markiert == 0 and erg.hochgeladen == 1
    assert "sevdesk" in _protokoll(einst).ziele_von("rechnung:a1")


def test_erstes_einschalten_nach_langer_zeit_aus(tmp_path, attrappe):
    """Nie eingeschaltet, lange nur Ordner: das erste Einschalten markiert alles."""
    Falsch.rechnungen = [("a1", "2026-10-01", "AIUC-1")]
    _lauf(_einst(tmp_path, an=False))
    _lauf(_einst(tmp_path, an=False))
    erg = _lauf(_einst(tmp_path))
    assert erg.als_schon_markiert == 1 and attrappe.entwuerfe == []


def test_datei_fehlt_vor_upload(tmp_path, attrappe):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    attrappe.verhalten = "kein_netz"
    _lauf(einst)
    _protokoll(einst).lokale_datei("rechnung:a1").unlink()
    attrappe.verhalten = "ok"
    erg = _lauf(einst)
    assert erg.hochgeladen == 0 and erg.nicht_hochgeladen == 1
    assert any("Fehlende Dateien neu holen" in h for h in erg.hinweise)


# ── Einstellungen ────────────────────────────────────────────────────────────


def test_einstellungen_mit_sevdesk_hin_und_zurueck(tmp_path):
    einst = Einstellungen(
        belegordner=tmp_path / "B", konten=[Konto("airbnb", "privat")], ziele=["ordner", "sevdesk"],
        sevdesk=SevDeskEinstellung(schluessel="sevdesk-api/jemand"),
    )
    datei = einstellungen.speichern(einst, tmp_path / "e.toml")
    text = datei.read_text(encoding="utf-8")
    assert "sevdesk-api/jemand" in text
    geladen = einstellungen.laden(datei)
    assert geladen.sevdesk_an
    assert geladen.sevdesk.dienst_und_konto == ("sevdesk-api", "jemand")
    assert geladen.sevdesk.steuerregel == ""  # keine Vorgabe


def test_ordner_ist_immer_dabei(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('ziele = ["sevdesk"]\n', encoding="utf-8")
    assert einstellungen.laden(datei).ziele == ["ordner", "sevdesk"]


def test_alte_einstellungsdatei_ohne_sevdesk(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('belegordner = "/x"\nziele = ["ordner"]\n', encoding="utf-8")
    geladen = einstellungen.laden(datei)
    assert not geladen.sevdesk_an
    assert geladen.sevdesk.schluessel == "belegabruf/sevdesk"


def test_falscher_eintrag_wird_gemeldet(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('[sevdesk]\nschluessel = "ohne-schraegstrich"\n', encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler):
        einstellungen.laden(datei)


def test_schluessel_pruefen(attrappe):
    v = sevdesk.Verbindung(PLATZHALTER)
    assert sevdesk.schluessel_pruefen(v) is None
    attrappe.verhalten = "401"
    assert "lehnt den API-Schlüssel ab" in sevdesk.schluessel_pruefen(v)


# ── Einrichten (Eingaben gespielt, Passwortspeicher als Attrappe) ────────────


class _Speicher:
    def __init__(self):
        self.daten = {}

    def get_password(self, dienst, konto):
        return self.daten.get((dienst, konto))

    def set_password(self, dienst, konto, wert):
        self.daten[(dienst, konto)] = wert

    def delete_password(self, dienst, konto):
        self.daten.pop((dienst, konto))


def _einrichten(monkeypatch, tmp_path, antworten, verdeckt=""):
    import builtins
    import getpass

    import keyring

    from belegabruf import einrichtung

    speicher = getattr(_einrichten, "speicher", None) or _Speicher()
    _einrichten.speicher = speicher
    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, name, getattr(speicher, name))
    eingaben = iter(antworten)
    monkeypatch.setattr(builtins, "input", lambda text="": next(eingaben))
    monkeypatch.setattr(getpass, "getpass", lambda text="": verdeckt)
    monkeypatch.setattr(pfade, "standard_belegordner", lambda: tmp_path / "Belege")
    return einrichtung.einrichten(), speicher


def test_einrichten_mit_neuem_schluessel(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    a = Attrappe()
    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", a)
    _einrichten.speicher = None
    # Anbieter, Kontoname, noch ein Konto?, Belegordner, sevDesk?, Eintrag, Steuerregel (erst falsch)
    einst, speicher = _einrichten(monkeypatch, tmp_path, ["", "", "n", "", "j", "", "x", "14"],
                                  verdeckt=PLATZHALTER)
    assert einst.sevdesk.steuerregel == "14"
    assert einst.sevdesk_an and einst.sevdesk.schluessel == "belegabruf/sevdesk"
    assert speicher.daten[("belegabruf", "sevdesk")] == PLATZHALTER
    assert a.aufrufe == [("GET", "/SevClient")]
    ausgabe = capsys.readouterr().out
    assert "Der Schlüssel funktioniert" in ausgabe and PLATZHALTER not in ausgabe
    text = pfade.einstellungsdatei().read_text(encoding="utf-8")
    assert PLATZHALTER not in text and 'schluessel = "belegabruf/sevdesk"' in text


def test_einrichten_mit_vorhandenem_eintrag(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    a = Attrappe()
    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", a)
    speicher = _Speicher()
    speicher.daten[("sevdesk-api", "jemand")] = PLATZHALTER
    _einrichten.speicher = speicher
    # …, sevDesk?, Eintrag, Steuerregel, Austauschen?
    einst, _ = _einrichten(monkeypatch, tmp_path, ["", "", "n", "", "j", "sevdesk-api/jemand", "14", "n"])
    assert einst.sevdesk.schluessel == "sevdesk-api/jemand"
    assert speicher.daten == {("sevdesk-api", "jemand"): PLATZHALTER}  # nichts überschrieben
    assert "Der Schlüssel funktioniert" in capsys.readouterr().out


def test_ohne_steuerregel_wird_nichts_hochgeladen(tmp_path, attrappe):
    einst = _einst(tmp_path)
    einst.sevdesk = SevDeskEinstellung(steuerregel="")
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(einst)
    assert "keine Steuerregel" in erg.upload_fehler and erg.nicht_hochgeladen == 1
    assert attrappe.aufrufe == []


def test_steuerregel_muss_nummer_sein(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('[sevdesk]\nsteuerregel = "Reverse Charge"\n', encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler):
        einstellungen.laden(datei)


def test_protokoll_aus_1_1_bekommt_neue_spalte(tmp_path):
    from belegabruf import protokoll as protokoll_modul

    datei = protokoll_modul.protokolldatei("airbnb", "privat")
    datei.parent.mkdir(parents=True)
    alte_spalten = [s for s in protokoll_modul.SPALTEN if s != "sevdesk_id"]
    datei.write_text(
        ";".join(alte_spalten) + "\n"
        "2026-11-01T10:00:00;airbnb;privat;rechnung;rechnung:a1;2026-10-01;HMX;AIUC-1;airbnb/2026/x.pdf;ordner\n"
        "2026-11-01T10:00:01;airbnb;privat;kontrolle;monat:2026-10;;;;airbnb/kontrolle/m.pdf;ordner\n",
        encoding="utf-8")
    p = Protokoll("airbnb", "privat", tmp_path / "Belege")
    assert datei.read_text(encoding="utf-8").splitlines()[0].endswith(";ziele;sevdesk_id")
    assert p.eintrag("rechnung:a1")["rechnungsnummer"] == "AIUC-1"
    p.hochgeladen("rechnung:a1", "77")
    neu = Protokoll("airbnb", "privat", tmp_path / "Belege")
    assert neu.eintrag("rechnung:a1")["sevdesk_id"] == "77"
    assert neu.eintrag("monat:2026-10")["datei"] == "airbnb/kontrolle/m.pdf"
    assert neu.anzahl("rechnung") == 1


def test_einrichten_ohne_steuerregel_bleibt_sevdesk_aus(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    a = Attrappe()
    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", a)
    _einrichten.speicher = _Speicher()
    # …, sevDesk?, Eintrag, Steuerregel leer
    einst, speicher = _einrichten(monkeypatch, tmp_path, ["", "", "n", "", "j", "", ""], verdeckt=PLATZHALTER)
    assert not einst.sevdesk_an
    assert speicher.daten == {} and a.aufrufe == []  # kein Schlüssel abgefragt, nichts gesendet
    assert "AUSGESCHALTET" in capsys.readouterr().out
    assert not einstellungen.laden().sevdesk_an
