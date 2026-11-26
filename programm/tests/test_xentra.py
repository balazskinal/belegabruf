"""Baustein Xentra — mit einer nachgebauten Seite, nie gegen das echte Xentra.

Alle Daten sind erfunden. Die Beschreibungen enthalten absichtlich einen
erfundenen Namen, um zu prüfen, dass er nirgends ankommt.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date

import pymupdf
import pytest

from belegabruf import browser, pfade
from belegabruf.einstellungen import Konto
from belegabruf.quellen import xentra
from belegabruf.quellen.basis import Umgebung

ERFUNDENER_NAME = "Erika Musterfrau"


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


# ── Lesen ────────────────────────────────────────────────────────────────────


def test_datum_lesen():
    assert xentra.datum_lesen("05.08.2026") == date(2026, 8, 5)
    assert xentra.datum_lesen("am 5.8.2026 bezahlt") == date(2026, 8, 5)
    assert xentra.datum_lesen("31.02.2026") is None
    assert xentra.datum_lesen("") is None


@pytest.mark.parametrize("rumpf, erwartet", [
    ('{"invoice_id": "INV-0042"}', "INV-0042"),
    ('{"invoiceId": "123"}', "123"),
    ('{"data": {"invoice": {"id": "abc_9"}}}', "abc_9"),
    ('{"customer_id": "c1", "invoice_id": "77"}', "77"),
    ('{"invoice_id": 88}', "88"),
    ('{"invoice_id": "../../etc"}', ""),
    ("kein json", ""),
    (None, ""),
])
def test_rechnungs_id_aus_anfrage(rumpf, erwartet):
    assert xentra.rechnungs_id_aus_anfrage(rumpf) == erwartet


def test_pdf_adresse_aus_antwort():
    assert xentra.pdf_adresse_aus_antwort('{"download": {"download_url": "https://files.example.com/a.pdf?sig=1"}}') \
        == "https://files.example.com/a.pdf?sig=1"
    assert xentra.pdf_adresse_aus_antwort('{"url": "http://unsicher.example.com/a.pdf"}') == ""
    assert xentra.pdf_adresse_aus_antwort("{}") == ""
    # gezielt das Feld download_url, nicht die erstbeste Adresse
    assert xentra.pdf_adresse_aus_antwort(
        '{"logo": "https://andere.example.com/logo.png", "download_url": "https://files.example.com/b.pdf"}') \
        == "https://files.example.com/b.pdf"
    assert xentra.pdf_adresse_aus_antwort('{"hinweis": "https://andere.example.com/x"}') == ""


class _Antwort:
    def __init__(self, inhalt: bytes, laenge: str | None = None):
        import io

        self._strom = io.BytesIO(inhalt)
        self.headers = {"Content-Length": laenge} if laenge else {}

    def read(self, n=-1):
        return self._strom.read(n)

    def read1(self, n=-1):
        return self._strom.read1(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FalscherOeffner:
    """Statt Netz: merkt sich die Anfragen und liefert ein PDF."""

    def __init__(self):
        self.anfragen = []
        self.inhalt = _pdf("Rechnung")
        self.laenge = None

    def open(self, anfrage, timeout=None):
        self.anfragen.append(anfrage)
        return _Antwort(self.inhalt, self.laenge)


def test_pdf_herunterladen_ohne_cookies_nur_https(monkeypatch):
    o = FalscherOeffner()
    monkeypatch.setattr(xentra, "_oeffner", o)
    assert xentra.pdf_herunterladen("https://files.example.com/a.pdf?sig=1").startswith(b"%PDF")
    kopf = {k.lower() for k in o.anfragen[0].header_items() for k in [k[0]]}
    assert "cookie" not in kopf and "authorization" not in kopf
    with pytest.raises(RuntimeError, match="nicht https"):
        xentra.pdf_herunterladen("http://files.example.com/a.pdf")
    assert len(o.anfragen) == 1


def test_oeffner_hat_keinen_cookie_speicher():
    import urllib.request

    assert not any(isinstance(h, urllib.request.HTTPCookieProcessor) for h in xentra._oeffner.handlers)


def test_weiterleitung_nur_https():
    import io
    import urllib.error
    import urllib.request

    h = xentra._NurHttps()
    anfrage = urllib.request.Request("https://files.example.com/a.pdf")
    assert h.max_redirections == 3
    assert h.redirect_request(anfrage, io.BytesIO(), 302, "Found", {}, "https://cdn.example.com/a.pdf") is not None
    with pytest.raises(urllib.error.HTTPError):
        h.redirect_request(anfrage, io.BytesIO(), 302, "Found", {}, "http://cdn.example.com/a.pdf")


def test_pdf_hoechstens_20_mb(monkeypatch):
    from belegabruf import pruefung

    o = FalscherOeffner()
    monkeypatch.setattr(xentra, "_oeffner", o)
    o.laenge = str(pruefung.MAX_PDF_BYTES + 1)
    with pytest.raises(xentra.PdfZuGross):
        xentra.pdf_herunterladen("https://files.example.com/a.pdf")
    o.laenge = None
    o.inhalt = b"%PDF-" + b"0" * pruefung.MAX_PDF_BYTES
    with pytest.raises(xentra.PdfZuGross):
        xentra.pdf_herunterladen("https://files.example.com/a.pdf")


def test_fehlermeldung_nennt_keine_adresse(monkeypatch):
    import urllib.error

    class Kaputt:
        def open(self, anfrage, timeout=None):
            raise urllib.error.HTTPError(anfrage.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(xentra, "_oeffner", Kaputt())
    with pytest.raises(RuntimeError) as info:
        xentra.pdf_herunterladen("https://geheim.example.com/a.pdf?sig=abc")
    assert "403" in str(info.value) and "geheim" not in str(info.value) and "sig" not in str(info.value)


def _pdf(text: str = "Rechnung") -> bytes:
    dok = pymupdf.open()
    dok.new_page().insert_text((50, 100), text)
    inhalt = dok.tobytes()
    dok.close()
    return inhalt


def test_pdf_pruefen():
    assert xentra.pdf_pruefen(_pdf()) is None
    assert xentra.pdf_pruefen(b"") == "leere Datei"
    assert xentra.pdf_pruefen(b"<html>Login</html>") == "kein PDF"
    assert xentra.pdf_pruefen(b"%PDF-1.7 kaputt") == "PDF nicht lesbar"


def test_dateiname_ohne_beschreibung():
    assert xentra.dateiname(date(2026, 8, 5), "INV-0042") == "2026-08-05_xentra_INV-0042.pdf"
    assert xentra.dateiname(None, "a/b") == "ohne-datum_xentra_ab.pdf"


def test_quelle_bekannt():
    from belegabruf import quellen

    assert quellen.klasse("xentra") is xentra.Xentra


# ── Ganzer Ablauf im echten (unsichtbaren) Browser mit nachgebauter Seite ────

ZEILEN = [  # (datum, beschreibung, betrag, id)
    ("05.10.2026", "Xentra Pro / Host Domain", "12,97 €", "INV-0003"),
    ("12.09.2026", f"Provision Produkt: Buchung {ERFUNDENER_NAME}", "4,20 €", "INV-0002"),
    ("05.09.2026", "Xentra Pro / Host Domain", "12,97 €", "INV-0001"),
]


def _tabelle(sichtbar: bool) -> str:
    zeilen = "".join(
        f"<tr><td>{d}</td><td>{b}</td><td>{betrag}</td><td>Bezahlt</td>"
        f"<td><button aria-label='PDF herunterladen' onclick=\"laden('{i}')\">⬇</button></td></tr>"
        for d, b, betrag, i in ZEILEN)
    stil = "" if sichtbar else " style='display:none'"
    return f"<table{stil}><tr><th>Datum</th><th>Beschreibung</th><th>Betrag</th><th>Status</th><th>PDF</th></tr>{zeilen}</table>"


SEITE = f"""<!doctype html><html><body>
<div role="tablist"><button role="tab">Abonnement</button>
<button role="tab" onclick="document.getElementById('r').style.display='block'">Rechnungen</button></div>
<button onclick="document.title='ABO GEKUENDIGT'">Abo kündigen</button>
<div id="r" style="display:none"><h3>Abonnement-Rechnungen</h3>{_tabelle(False)}{_tabelle(True)}</div>
<script>
async function laden(id) {{
  const w = window.open('about:blank');
  const r = await fetch('https://api.myxentra.com/functions/v1/chargebee-invoice-download',
    {{method: 'POST', headers: {{'content-type': 'application/json'}}, body: JSON.stringify({{invoice_id: id}})}});
  const d = await r.json();
  if (d.download && w) w.location = d.download.download_url;
}}
</script></body></html>"""


def _chromium_da() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(channel="chromium", headless=True).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def falsches_xentra(monkeypatch):
    if not _chromium_da():
        pytest.skip("Chromium nicht installiert")
    zustand = {"verhalten": "ok", "aufrufe": [], "downloads": []}
    original = browser.profil_oeffnen

    def app(route):
        url = route.request.url
        zustand["aufrufe"].append(url)
        if zustand["verhalten"] == "abgemeldet" and "/login" not in url:
            return route.fulfill(status=302, headers={"Location": "https://app.myxentra.com/login"})
        if "/login" in url:
            return route.fulfill(content_type="text/html; charset=utf-8", body="<html><body>Anmelden <input type=password></body></html>")
        if url.rstrip("/").endswith("/billing"):
            return route.fulfill(content_type="text/html; charset=utf-8", body=SEITE)
        return route.fulfill(status=404, body="404")

    def api(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers={"access-control-allow-origin": "*",
                                                      "access-control-allow-headers": "content-type"})
        kennung = json.loads(route.request.post_data)["invoice_id"]
        zustand["downloads"].append(kennung)
        if zustand["verhalten"] == "fehler" and kennung == "INV-0002":
            return route.fulfill(status=500, headers={"access-control-allow-origin": "*"}, body="{}")
        return route.fulfill(
            content_type="application/json", headers={"access-control-allow-origin": "*"},
            body=json.dumps({"download": {"download_url": f"https://files.example.com/{kennung}.pdf?sig=x"}}))

    def dateien(route):
        return route.fulfill(content_type="application/pdf", body=_pdf("Rechnung"))

    @contextmanager
    def profil_mit_umleitung(profil, sichtbar):
        with original(profil, sichtbar=False) as kontext:
            kontext.route("https://app.myxentra.com/**", app)
            kontext.route("https://api.myxentra.com/**", api)
            kontext.route("https://files.example.com/**", dateien)
            # Das Profil hat Cookies, auch für den Datei-Host — die dürfen nie mitgehen.
            kontext.add_cookies([{"name": "sitzung", "value": "geheim", "domain": "files.example.com", "path": "/"},
                                 {"name": "sitzung", "value": "geheim", "domain": "app.myxentra.com", "path": "/"}])
            yield kontext

    class Oeffner(FalscherOeffner):
        def open(self, anfrage, timeout=None):
            assert anfrage.full_url.startswith("https://files.example.com/")
            if zustand["verhalten"] == "kein_pdf":
                self.inhalt = b"<html>abgelaufen</html>"
            if zustand["verhalten"] == "zu_gross":
                self.laenge = str(30 * 1024 * 1024)
            return super().open(anfrage, timeout)

    oeffner = Oeffner()
    zustand["oeffner"] = oeffner
    monkeypatch.setattr(browser, "profil_oeffnen", profil_mit_umleitung)
    monkeypatch.setattr(browser, "pause", lambda *a, **k: None)
    monkeypatch.setattr(xentra, "_oeffner", oeffner)
    return zustand


def _umgebung(bekannt: set[str], abgeliefert: list, meldungen: list):
    def abliefern(beleg):
        abgeliefert.append(beleg)
        bekannt.add(beleg.schluessel)
        return [beleg.dateiname]

    return Umgebung(bekannt=lambda s: s in bekannt, abliefern=abliefern,
                    vorhandene_datei=lambda s: None, melden=meldungen.append)


def test_ablauf_holt_sichtbare_rechnungen(tmp_path, falsches_xentra):
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is True
    bekannt, abgeliefert, meldungen = set(), [], []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, meldungen))
    assert erg.status == "ok" and erg.neu == 3 and erg.erwartet == 3 and erg.vorhanden == 3
    assert [b.dateiname for b in abgeliefert] == [
        "2026-10-05_xentra_INV-0003.pdf", "2026-09-12_xentra_INV-0002.pdf", "2026-09-05_xentra_INV-0001.pdf"]
    assert [b.betrag for b in abgeliefert] == ["12,97 €", "4,20 €", "12,97 €"]
    assert abgeliefert[0].schluessel == "rechnung:INV-0003" and abgeliefert[0].rechnungsdatum == date(2026, 10, 5)
    # Nur die sichtbare Tabelle: jede Rechnung genau einmal angefragt
    assert falsches_xentra["downloads"] == ["INV-0003", "INV-0002", "INV-0001"]
    # Die Beschreibung (mit Namen) kommt nirgends an
    sichtbar_fuer_mensch = " ".join(meldungen + erg.abweichungen + erg.hinweise)
    assert ERFUNDENER_NAME not in sichtbar_fuer_mensch
    assert not any(ERFUNDENER_NAME in str(v) for b in abgeliefert for k, v in vars(b).items() if k != "inhalt")
    assert not any("Musterfrau" in str(v) for v in erg.als_dict().values())

    # PDF ohne Cookies geladen
    anfragen = falsches_xentra["oeffner"].anfragen
    assert len(anfragen) == 3
    assert all("cookie" not in {k.lower() for k, _ in a.header_items()} for a in anfragen)
    # Nur die Abrechnungsseite aufgerufen — nichts an Abo oder Einstellungen
    assert all(u.rstrip("/").endswith("/billing") for u in falsches_xentra["aufrufe"])

    # Zweiter Lauf: nichts Neues, nichts gespeichert
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, meldungen))
    assert erg.neu == 0 and erg.schon_da == 3 and erg.vorhanden == 3 and len(abgeliefert) == 3


def test_fehler_bei_einer_rechnung(tmp_path, falsches_xentra):
    falsches_xentra["verhalten"] = "fehler"
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    bekannt, abgeliefert = set(), []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, []))
    assert erg.status == "unvollstaendig" and erg.neu == 2 and erg.vorhanden == 2 and erg.erwartet == 3
    assert any("12.09.2026" in a and "500" in a for a in erg.abweichungen)
    falsches_xentra["verhalten"] = "ok"
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, []))
    assert erg.neu == 1 and erg.status == "ok"


def test_kein_pdf_wird_nicht_gespeichert(tmp_path, falsches_xentra):
    falsches_xentra["verhalten"] = "kein_pdf"
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    erg = quelle.belege_holen(_umgebung(set(), (abgeliefert := []), []))
    assert erg.neu == 0 and abgeliefert == [] and erg.status == "unvollstaendig"
    assert all("kein PDF" in a for a in erg.abweichungen)


def test_abgemeldet(tmp_path, falsches_xentra):
    falsches_xentra["verhalten"] = "abgemeldet"
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is False
    erg = quelle.belege_holen(_umgebung(set(), [], []))
    assert erg.status == "abgelaufen" and erg.neu == 0


def test_zu_grosses_pdf_wird_nicht_gespeichert(tmp_path, falsches_xentra):
    falsches_xentra["verhalten"] = "zu_gross"
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    abgeliefert = []
    erg = quelle.belege_holen(_umgebung(set(), abgeliefert, []))
    assert abgeliefert == [] and erg.status == "unvollstaendig"
    assert all("größer als 20 MB" in a for a in erg.abweichungen) and len(erg.abweichungen) == 3
    assert not any("files.example.com" in a for a in erg.abweichungen)  # kein Host in der Zusammenfassung


# ── Abgebrochene, langsame und kaputte Downloads (echter lokaler Server) ──────


@contextmanager
def _lokaler_server(antworten):
    """Ein winziger HTTP-Server auf 127.0.0.1, der rohe Bytes schickt (auch kaputte)."""
    import socket
    import threading

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(5)
    stop = threading.Event()

    def laufen():
        s.settimeout(0.2)
        while not stop.is_set():
            try:
                verbindung, _ = s.accept()
            except OSError:
                continue
            with verbindung:
                verbindung.recv(65536)
                try:
                    antworten(verbindung)
                except OSError:
                    pass

    faden = threading.Thread(target=laufen, daemon=True)
    faden.start()
    try:
        yield f"http://127.0.0.1:{s.getsockname()[1]}/rechnung.pdf?token=geheim"
    finally:
        stop.set()
        faden.join(2)
        s.close()


@pytest.fixture
def lokal(monkeypatch):
    """Echter urllib-Zugang, aber http://127.0.0.1 ausnahmsweise erlaubt (nur im Test)."""
    monkeypatch.setattr(xentra, "_adresse_erlaubt", lambda a: a.startswith("http://127.0.0.1:"))


def test_lokal_vollstaendig(lokal):
    pdf = _pdf("Rechnung")

    def antworten(v):
        v.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\nContent-Length: %d\r\n"
                  b"Connection: close\r\n\r\n" % len(pdf) + pdf)

    with _lokaler_server(antworten) as adresse:
        assert xentra.pdf_herunterladen(adresse) == pdf


def test_abgebrochener_download_mit_laenge(lokal):
    pdf = _pdf("Rechnung")
    assert xentra.pdf_pruefen(pdf[: int(len(pdf) * 0.9)]) is None  # PyMuPDF nähme das gekürzte PDF an

    def antworten(v):
        v.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(pdf)
                  + pdf[: int(len(pdf) * 0.9)])  # dann Verbindung zu

    with _lokaler_server(antworten) as adresse, pytest.raises(xentra.DownloadUnvollstaendig) as info:
        xentra.pdf_herunterladen(adresse)
    assert "abgebrochen" in str(info.value) and "geheim" not in str(info.value)


def test_abgebrochener_download_chunked(lokal):
    pdf = _pdf("Rechnung")

    def antworten(v):
        teil = pdf[: len(pdf) // 3]
        v.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
                  + b"%x\r\n" % len(pdf) + teil)  # Stück kündigt mehr an, als kommt

    with _lokaler_server(antworten) as adresse, pytest.raises(xentra.DownloadUnvollstaendig):
        xentra.pdf_herunterladen(adresse)


def test_troepfelnder_server_gesamtfrist(lokal, monkeypatch):
    import time

    monkeypatch.setattr(xentra, "GESAMTFRIST_S", 1)
    assert xentra._STUECK >= 64 * 1024  # bewusst nicht verkleinert: genau das soll der Test prüfen

    def antworten(v):
        v.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n")
        for _ in range(20):
            v.sendall(b"%")
            time.sleep(0.2)

    with _lokaler_server(antworten) as adresse:
        start = time.monotonic()
        with pytest.raises(xentra.DownloadUnvollstaendig, match="länger als 1 Sekunden"):
            xentra.pdf_herunterladen(adresse)
        assert time.monotonic() - start < 3


def test_kaputte_adresse_nennt_keinen_token():
    with pytest.raises(RuntimeError) as info:
        xentra.pdf_herunterladen("https://files.example.com/a b.pdf?token=geheim123")
    text = str(info.value)
    assert "geheim123" not in text and "files.example.com" not in text
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_abgebrochener_download_wird_nicht_gespeichert(tmp_path, falsches_xentra, monkeypatch):
    def unvollstaendig(adresse):
        raise xentra.DownloadUnvollstaendig("Download abgebrochen (10 von 100 Bytes)")

    monkeypatch.setattr(xentra, "pdf_herunterladen", unvollstaendig)
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    abgeliefert = []
    erg = quelle.belege_holen(_umgebung(set(), abgeliefert, []))
    assert abgeliefert == [] and erg.status == "unvollstaendig" and len(erg.abweichungen) == 3
    assert all("abgebrochen" in a and "nicht gespeichert" in a for a in erg.abweichungen)


def test_zeitraum_filtert_vor_dem_anklicken(tmp_path, falsches_xentra):
    quelle = xentra.Xentra(Konto("xentra", "test"), tmp_path / "profil")
    bekannt, abgeliefert, meldungen = set(), [], []
    umgebung = _umgebung(bekannt, abgeliefert, meldungen)
    umgebung.ab = date(2026, 9, 10)
    erg = quelle.belege_holen(umgebung)
    assert erg.neu == 2 and erg.uebersprungen == 1 and erg.erwartet == 2
    assert falsches_xentra["downloads"] == ["INV-0003", "INV-0002"]  # INV-0001 nie angeklickt
    assert "rechnung:INV-0001" not in bekannt
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, meldungen))
    assert erg.neu == 1 and erg.schon_da == 2 and falsches_xentra["downloads"][-1] == "INV-0001"
