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
            yield kontext

    def pdf_laden(self, kontext, adresse):
        assert adresse.startswith("https://files.example.com/")
        inhalt = b"<html>abgelaufen</html>" if zustand["verhalten"] == "kein_pdf" else _pdf("Rechnung")
        return inhalt

    monkeypatch.setattr(browser, "profil_oeffnen", profil_mit_umleitung)
    monkeypatch.setattr(browser, "pause", lambda *a, **k: None)
    monkeypatch.setattr(xentra.Xentra, "_pdf_laden", pdf_laden)
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
