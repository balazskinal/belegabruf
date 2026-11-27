"""Baustein Booking.com — mit einem nachgebauten Extranet, nie gegen das echte Booking.com.

Alle Daten sind erfunden: Unterkunft, Sitzungsschlüssel, Rechnungs-, Buchungs- und
Auszahlungsnummern. Die Auszahlungs-CSV enthält absichtlich einen erfundenen Gastnamen,
um zu prüfen, dass er nirgends ankommt (außer in der unveränderten CSV-Datei selbst).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pymupdf
import pytest

from belegabruf import browser, pfade
from belegabruf.einstellungen import Konto
from belegabruf.quellen import booking
from belegabruf.quellen.basis import Umgebung

ERFUNDENER_NAME = "Erika Musterfrau"
HOTEL = "1234567"
ANDERES_HOTEL = "7654321"  # zweite, erfundene Unterkunft (Co-Hosting)
SES = "SES-GEHEIM-0815"
HEUTE = date(2026, 11, 26)


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    monkeypatch.setattr(booking, "heute", lambda: HEUTE)
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


# ── Lesen (ohne Browser) ─────────────────────────────────────────────────────


@pytest.mark.parametrize("text, erwartet", [
    ("3. Nov. 2026", date(2026, 11, 3)),
    ("Kommission 1111111111 3. Juli 2026 1 Juni - 30 Juni", date(2026, 7, 3)),
    ("26. Sept. 2026", date(2026, 9, 26)),
    ("1. März 2026", date(2026, 3, 1)),
    ("5. Mai 2026", date(2026, 5, 5)),
    ("2026-01-03", date(2026, 1, 3)),
    ("31. Feb. 2026", None),
    ("ohne Datum", None),
])
def test_datum_lesen(text, erwartet):
    assert booking.datum_lesen(text) == erwartet


def _csv(zeilen: list[tuple[str, str]], datum="19. Nov. 2026", nummer="PAYOUT0815TEST") -> bytes:
    kopf = ('Art,Buchungsnummer,Check-in,Checkout,"Name des Gastes","Dienstleister für Zahlungen",'
            'Buchungsstatus,Währung,Zahlungsstatus,Betrag,Kommission,"Servicegebühr für Zahlungen",Netto,'
            '"Datum der Auszahlung",Auszahlungsnummer')
    rumpf = [f'Buchung,{b},"{c}","{c}",{ERFUNDENER_NAME},"Booking.com B.V.",ok,EUR,by_booking,'
             f'100.00,-15.00,-1.50,83.50,"{datum}",{nummer}' for b, c in zeilen]
    return ("\r\n".join([kopf, *rumpf]) + "\r\n").encode("utf-8")


def test_auszahlung_lesen_ohne_namen():
    daten = booking.auszahlung_lesen(_csv([("9000000001", "12. Nov. 2026"), ("9000000002", "14. Nov. 2026")]))
    assert daten.buchungsnummern == ["9000000001", "9000000002"]
    assert daten.checkins == [date(2026, 11, 12), date(2026, 11, 14)]
    assert daten.datum == date(2026, 11, 19) and daten.nummer == "PAYOUT0815TEST"
    assert ERFUNDENER_NAME not in repr(daten)


def test_auszahlung_dateiname():
    eine = booking.auszahlung_lesen(_csv([("9000000001", "12. Nov. 2026")]))
    assert booking.auszahlung_dateiname(None, eine, "pdf") == "2026-11-19_auszahlung_9000000001_checkin-2026-11-12.pdf"
    viele = booking.auszahlung_lesen(_csv([(f"900000000{i}", f"1{i}. Nov. 2026") for i in range(1, 6)]))
    assert booking.auszahlung_dateiname(None, viele, "csv", hotel=HOTEL, mehrere=True) == (
        "2026-11-19_auszahlung_9000000001_9000000002_9000000003+2_checkin-2026-11-11_1234567.csv")
    leer = booking.AuszahlungsDaten()
    assert booking.auszahlung_dateiname(date(2026, 1, 2), leer, "pdf") == "2026-01-02_auszahlung_ohne-buchung.pdf"


def test_unterkuenfte_und_sauber():
    seite = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/home.html?hotel_id={HOTEL}&ses={SES}"
    links = [f"https://admin.booking.com/x?hotel_id=7654321&ses={SES}", f"https://admin.booking.com/y?hotel_id={HOTEL}"]
    assert booking.unterkuenfte(seite, links) == [HOTEL]  # fremde IDs in Links zählen nicht
    assert booking.unterkuenfte(seite, links, "7654321") == ["7654321"]
    assert booking.unterkuenfte(seite, links, f"{HOTEL}, 7654321") == [HOTEL, "7654321"]
    assert booking.unterkuenfte(seite, links, [HOTEL, 7654321]) == [HOTEL, "7654321"]  # TOML-Liste
    gruppe = f"https://admin.booking.com/hotel/hoteladmin/groups/home/index.html?ses={SES}"
    assert booking.unterkuenfte(gruppe, links) == ["7654321", HOTEL]
    assert booking.parameter(seite) == {"hotel_id": HOTEL, "ses": SES}
    assert SES not in booking.sauber(f"Timeout beim Laden von {seite} (ses={SES})")


def test_jahr_fehlt_im_menue_wird_still_uebersprungen():
    class Eintrag:
        def __init__(self, n):
            self.n = n

        def count(self):
            return self.n

    class Knopf:
        first = None

        def inner_text(self, timeout=None):
            return "2025"

        def click(self, timeout=None):
            pass

    class Seite:
        gedrueckt = []
        keyboard = type("K", (), {"press": lambda self, t: Seite.gedrueckt.append(t)})()

        def locator(self, _):
            k = Knopf()
            k.first = k
            return type("L", (), {"filter": lambda s, **kw: type("F", (), {"locator": lambda s2, _: k})()})()

        def wait_for_timeout(self, _):
            pass

        def get_by_role(self, rolle, name=None, exact=None):
            return Eintrag(0)

    assert booking.Booking.__new__(booking.Booking)._jahr_waehlen(Seite(), 2024) is False
    assert Seite.gedrueckt == ["Escape"]


def test_jahre_noetig():
    assert booking.jahre_noetig([2024, 2026, 2025], None) == [2026, 2025, 2024]
    assert booking.jahre_noetig([2024, 2026, 2025], date(2026, 1, 1)) == [2026]
    assert booking.jahre_noetig([2024, 2026, 2025], date(2026, 1, 1), vorlauf=1) == [2026, 2025]


def test_quelle_bekannt():
    from belegabruf import quellen

    assert quellen.anzeigename("booking") == "Booking.com"
    assert quellen.klasse("booking") is booking.Booking


# ── Ablage: eigene Unterordner je Dokumentart ────────────────────────────────


def _beleg(art, dateiname, datum, inhalt=b"%PDF-1.4 test"):
    from belegabruf.quellen.basis import Beleg

    return Beleg(quelle="booking", konto="standard", art=art, schluessel=f"{art}:{dateiname}",
                 dateiname=dateiname, inhalt=inhalt, jahr=datum.year, rechnungsdatum=datum,
                 unterordner=booking.UNTERORDNER[art])


@pytest.mark.parametrize("ablage, monat", [("jahr", ""), ("monat", "11")])
def test_ablage_je_art(tmp_path, ablage, monat):
    from belegabruf.ziele.ordner import Ordner

    ziel = Ordner(tmp_path, ablage=ablage)
    for art in ("rechnung", "auszahlungsuebersicht", "auszahlung"):
        ort = ziel.abliefern(_beleg(art, "x.pdf", date(2026, 11, 3)))
        erwartet = tmp_path / "booking" / booking.UNTERORDNER[art] / "2026"
        assert ort == (erwartet / monat / "x.pdf" if monat else erwartet / "x.pdf")


def test_nur_rechnungen_gehen_an_lieferziele(tmp_path):
    from belegabruf.protokoll import Protokoll

    p = Protokoll("booking", "standard", tmp_path)
    for art in ("rechnung", "auszahlungsuebersicht", "auszahlung"):
        b = _beleg(art, f"{art}.pdf", date(2026, 11, 3))
        p.eintragen(b, tmp_path / f"{art}.pdf", ["ordner"])
    assert p.offen_fuer("mail:beleg@example.com") == ["rechnung:rechnung.pdf"]


# ── Ablauf gegen ein nachgebautes Extranet ───────────────────────────────────


def _pdf(text: str) -> bytes:
    dok = pymupdf.open()
    dok.new_page().insert_text((50, 100), text)
    inhalt = dok.tobytes()
    dok.close()
    return inhalt


RECHNUNGEN = {  # Jahr im Filter → (invoice_name, Rechnungsdatum)
    2026: [("1000-1111111112", "3. Nov. 2026"), ("1000-1111111111", "3. Okt. 2026")],
    2025: [("1000-1111111110", "3. Jan. 2026"), ("1000-1111111109", "3. Dez. 2025")],
    2024: [("1000-1111111100", "3. Dez. 2024")],
}
UEBERSICHTEN = {2026: [11, 10], 2025: [12]}  # Jahr → Monate (11/2026 läuft noch)
AUSZAHLUNGEN = {  # Zeitraum → (uuid, Datum, Buchungen [(Nummer, Check-in)])
    "THIS_YEAR": [
        ("aaaaaaaa-0000-0000-0000-000000000003", "27. Nov. 2026", [("9000000009", "20. Nov. 2026")]),
        ("aaaaaaaa-0000-0000-0000-000000000002", "19. Nov. 2026",
         [("9000000001", "12. Nov. 2026"), ("9000000002", "14. Nov. 2026")]),
    ],
    "LAST_YEAR": [("aaaaaaaa-0000-0000-0000-000000000001", "18. Dez. 2025", [("9000000000", "10. Dez. 2025")])],
}
ALLE_AUSZAHLUNGEN = {u: (d, b) for liste in AUSZAHLUNGEN.values() for u, d, b in liste}


def _q(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _jahrfilter(name: str, jahre: list[int], aktuell: int, beim_klick: str) -> str:
    knoepfe = "".join(f"<li role='none'><button role='menuitem' onclick=\"{beim_klick}({j})\">{j}</button></li>"
                      for j in jahre)
    return (f"<div>Nach Jahr filtern<button id='{name}-jahr' aria-expanded='false' "
            f"onclick=\"document.getElementById('{name}-menue').style.display='block'\">{aktuell}</button>"
            f"<ul id='{name}-menue' style='display:none'>{knoepfe}</ul></div>")


FREMDER_LINK = ("https://andere.example/fresa/extranet/finance/invoices/get_document?"
                f"hotel_id={HOTEL}&ses={SES}&invoice_name=1000-2222222222")


def _rechnungsseite(jahr: int, ohne_filter: bool = False, mit_fremden: bool = False) -> str:
    fremd = "" if not mit_fremden else (f"<tr><td>Kommission</td><td>2222222222</td><td>3. Okt. {jahr}</td>"
             f"<td><a href='{FREMDER_LINK}'>PDF</a></td></tr>"
             f"<tr><td>Kommission</td><td>3333333333</td><td>3. Okt. {jahr}</td><td><a href='http://admin.booking.com"
             f"/fresa/extranet/finance/invoices/get_document?invoice_name=1000-3333333333'>PDF</a></td></tr>")
    zeilen = fremd + "".join(
        f"<tr><td>Kommission</td><td>{n.split('-')[1]}</td><td>{d}</td><td>Zeitraum</td>"
        f"<td><a target='_blank' href='/fresa/extranet/finance/invoices/get_document?hotel_id={HOTEL}"
        f"&lang=de&ses={SES}&invoice_name={n}'>PDF</a> | <a href='/kaputt?x=1'>Übersicht ansehen</a></td>"
        f"<td>Bezahlt</td><td>€ 12,34</td></tr>" for n, d in RECHNUNGEN.get(jahr, []))
    von_jahre = sorted(UEBERSICHTEN, reverse=True)
    return f"""<!doctype html><html><body>
<button onclick="document.title='ABGEMELDET'">Abmelden</button>
<div role="tablist">
  <button role="tab" id="t-an" onclick="zeige('an')"><span>Zahlungen an Booking.com</span></button>
  <button role="tab" id="t-von" onclick="zeige('von')"><span>Zahlungen von Booking.com</span></button>
</div>
<div id="an">{'' if ohne_filter else _jahrfilter('an', sorted(RECHNUNGEN, reverse=True), jahr, 'jahrAn')}
  <table>{zeilen}</table></div>
<div id="von" style="display:none">{_jahrfilter('von', von_jahre, von_jahre[0], 'jahrVon')}
  <table id="von-zeilen"></table></div>
<script>
const UEBERSICHTEN = {dict((str(k), v) for k, v in UEBERSICHTEN.items())};
function zeige(t) {{
  document.getElementById('an').style.display = t === 'an' ? 'block' : 'none';
  document.getElementById('von').style.display = t === 'von' ? 'block' : 'none';
  if (t === 'von') jahrVon({von_jahre[0]});
}}
function jahrAn(j) {{ location.href = location.pathname + location.search.replace(/&year=\\d+/, '') + '&year=' + j; }}
function jahrVon(j) {{
  document.getElementById('von-menue').style.display = 'none';
  document.getElementById('von-jahr').textContent = j;
  const t = document.getElementById('von-zeilen');
  t.textContent = '';
  for (const m of (UEBERSICHTEN[j] || [])) {{
    const tr = document.createElement('tr');
    const q = '?hotel_id={HOTEL}&lang=de&ses={SES}&year=' + j + '&month=' + m;
    tr.innerHTML = '<td>Auszahlungsübersicht</td><td>1. Dez. ' + j + '</td>'
      + '<td><a href="/fresa/payment/payout/monthlyStatementPDF' + q + '">PDF</a> | '
      + '<a href="/fresa/payment/payout/migrated/historyCSV' + q + '">CSV</a></td>';
    t.appendChild(tr);
  }}
}}
</script></body></html>"""


def _auszahlungsseite() -> str:
    daten = {z: [[u, d] for u, d, _ in liste] for z, liste in AUSZAHLUNGEN.items()}
    return f"""<!doctype html><html><body>
<select id="report-period-filter" onchange="zeige(this.value)">
  <option value="THIS_MONTH">Dieser Monat</option><option value="LAST_MONTH">Letzter Monat</option>
  <option value="THIS_YEAR" selected>Dieses Jahr</option><option value="LAST_YEAR">Letztes Jahr</option>
  <option value="CUSTOM_DATES">Individueller Zeitraum</option></select>
<table id="z"></table>
<script>
const D = {daten};
function zeige(z) {{
  const t = document.getElementById('z'); t.textContent = '';
  for (const [u, d] of (D[z] || [])) {{
    const tr = document.createElement('tr');
    const q = '?hotel_id={HOTEL}&lang=de&ses={SES}&payout_uuid=' + u;
    tr.innerHTML = '<td>' + d + '</td><td>Zeitraum</td><td>XyZ</td><td><a href="/fresa/payment/payout/payoutPDF'
      + q + '">PDF</a>/<a href="/fresa/payment/payout/migrated/payoutCSV' + q + '">CSV</a></td><td>Gesendet</td>';
    t.appendChild(tr);
  }}
}}
zeige('THIS_YEAR');
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
def falsches_booking(monkeypatch):
    if not _chromium_da():
        pytest.skip("Chromium nicht installiert")
    zustand = {"verhalten": "ok", "seiten": [], "dateien": []}
    original = browser.profil_oeffnen
    basis = "https://admin.booking.com"
    start = f"{basis}/hotel/hoteladmin/extranet_ng/manage/home.html?hotel_id={HOTEL}&lang=de&ses={SES}"

    def html(route, text):
        return route.fulfill(content_type="text/html; charset=utf-8", body=text)

    def extranet(route):
        url = route.request.url
        pfad = urlsplit(url).path
        # Weiterleitungen per Skript, nicht per 302: Playwright fängt die Folgeanfrage
        # einer 302 nicht ab — sie ginge sonst ans echte Booking.com.
        if zustand["verhalten"] == "abgemeldet":
            return html(route, "<script>location.replace('https://account.booking.com/sign-in')</script>")
        if pfad == "/":
            return html(route, f"<script>location.replace('{start}')</script>")
        if pfad.startswith("/fresa/"):
            q = _q(url)
            zustand["dateien"].append(pfad.rsplit("/", 1)[-1] + ":" + (q.get("invoice_name") or q.get(
                "payout_uuid") or f"{q.get('year')}-{q.get('month')}"))
            assert q.get("ses") == SES and q.get("hotel_id") == HOTEL
            if zustand["verhalten"] == "fehler" and q.get("invoice_name") == "1000-1111111111":
                return route.fulfill(status=500, body="Fehler")
            if pfad.endswith("CSV"):
                buchungen = ALLE_AUSZAHLUNGEN.get(q.get("payout_uuid", ""), (None, [("9000000099", "1. Okt. 2026")]))
                return route.fulfill(content_type="text/csv", body=_csv(buchungen[1], datum=buchungen[0] or ""))
            return route.fulfill(content_type="application/pdf", body=_pdf("Booking.com " + pfad))
        zustand["seiten"].append(pfad + ("?year=" + _q(url)["year"] if "year" in _q(url) else ""))
        if pfad.endswith("home.html") and zustand["verhalten"] == "zwei_faktor":
            # Extranet-Adresse mit ses, aber die Bestätigung ist noch offen: keine Unterkunft auf der Seite.
            return html(route, "<html><body><h1>Bestätigung</h1><p>Code eingeben</p>"
                               "<input name=code><button>Bestätigen</button></body></html>")
        if pfad.endswith("home.html"):  # mit einem Link auf eine fremde Unterkunft (wie im echten Extranet)
            return html(route, f"<html><body><a href='{start}'>Start</a>"
                               f"<a href='{basis}/x.html?hotel_id=7654321&ses={SES}'>Werbung</a></body></html>")
        if pfad.endswith("finance_invoices.html") and zustand["verhalten"] == "zwei_faktor_mittendrin":
            return html(route, "<html><body><h1>Bestätigung</h1><input name=code></body></html>")
        if pfad.endswith("finance_invoices.html") and zustand["verhalten"] == "kein_zugriff_403":
            # 403 ohne Menü: nur ein kurzer Text, kein Unterkunfts-Link, keine Finanzmerkmale.
            return route.fulfill(status=403, content_type="text/html; charset=utf-8",
                                 body="<html><body><h1>Forbidden</h1></body></html>")
        if pfad.endswith("finance_invoices.html") and zustand["verhalten"] == "403_mit_code":
            # 403, aber Booking.com fragt erneut nach einem Code: Bestätigung, kein Rechteproblem.
            return route.fulfill(status=403, content_type="text/html; charset=utf-8",
                                 body="<html><body><p>Bitte bestätigen</p><input name=code></body></html>")
        if pfad.endswith("finance_invoices.html") and zustand["verhalten"] == "403_sperre":
            # Sperrseite eines Netzwerkdienstes (erfundene Referenz).
            return route.fulfill(status=403, content_type="text/html; charset=utf-8",
                                 body="<html><body><h1>Access Denied</h1><p>You don't have permission to access "
                                      "this server.</p><p>Reference #18.0000000.0000000000.000000</p></body></html>")
        if pfad.endswith("payouts.html") and zustand["verhalten"] == "403_auszahlungen":
            return route.fulfill(status=403, content_type="text/html; charset=utf-8",
                                 body="<html><body><h1>Forbidden</h1></body></html>")
        if pfad.endswith("finance_invoices.html") and (
                zustand["verhalten"] == "kein_zugriff"
                or (zustand["verhalten"] == "kein_zugriff_teil" and _q(url).get("hotel_id") == ANDERES_HOTEL)):
            return html(route, f"<html><body><a href='{start}'>Start</a>"
                               "<p>Sie haben keinen Zugriff auf diese Seite.</p></body></html>")
        if pfad.endswith("finance_invoices.html"):
            return html(route, _rechnungsseite(int(_q(url).get("year") or 2026),
                                               ohne_filter=zustand["verhalten"] == "ohne_filter",
                                               mit_fremden=zustand["verhalten"] == "fremde_links"))
        if pfad.endswith("payouts.html"):
            if zustand["verhalten"] == "auszahlungen_kaputt":
                return route.abort()
            return html(route, _auszahlungsseite())
        return route.fulfill(status=404, body="404")

    def fremd(route):
        zustand["fremd"] = zustand.get("fremd", 0) + 1
        return route.fulfill(content_type="application/pdf", body=_pdf("untergeschoben"))

    def konto(route):
        return html(route, "<html><body>Anmelden <input type=password></body></html>")

    @contextmanager
    def profil_mit_umleitung(profil, sichtbar):
        with original(profil, sichtbar=False) as kontext:
            kontext.route("https://admin.booking.com/**", extranet)
            kontext.route("https://account.booking.com/**", konto)
            kontext.route("**://andere.example/**", fremd)
            yield kontext

    monkeypatch.setattr(browser, "profil_oeffnen", profil_mit_umleitung)
    monkeypatch.setattr(browser, "pause", lambda *a, **k: None)
    return zustand


def _umgebung(bekannt: set[str], abgeliefert: list, meldungen: list, ab: date | None = None):
    def abliefern(beleg):
        abgeliefert.append(beleg)
        bekannt.add(beleg.schluessel)
        return [beleg.dateiname]

    return Umgebung(bekannt=lambda s: s in bekannt, abliefern=abliefern,
                    vorhandene_datei=lambda s: None, melden=meldungen.append, ab=ab)


def test_ablauf_holt_drei_arten(tmp_path, falsches_booking):
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is True
    bekannt, abgeliefert, meldungen = set(), [], []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, meldungen))
    assert erg.status == "ok", erg.abweichungen

    je_art = {}
    for b in abgeliefert:
        je_art.setdefault(b.art, []).append(b)
    rechnungen = je_art["rechnung"]
    assert sorted(b.dateiname for b in rechnungen) == [
        "2024-12-03_booking_1111111100.pdf", "2025-12-03_booking_1111111109.pdf",
        "2026-01-03_booking_1111111110.pdf", "2026-10-03_booking_1111111111.pdf",
        "2026-11-03_booking_1111111112.pdf"]
    assert erg.neu == 5 and erg.erwartet == 5 and erg.vorhanden == 5
    assert rechnungen[0].schluessel.startswith(f"rechnung:{HOTEL}:") and rechnungen[0].rechnungsnummer
    assert all(b.unterordner == "Rechnungen (an Booking.com)" for b in rechnungen)

    # Auszahlungsübersichten: nur abgeschlossene Monate (11/2026 läuft noch), PDF und CSV
    assert sorted(b.dateiname for b in je_art["auszahlungsuebersicht"]) == [
        "2025-12_auszahlungsuebersicht.csv", "2025-12_auszahlungsuebersicht.pdf",
        "2026-10_auszahlungsuebersicht.csv", "2026-10_auszahlungsuebersicht.pdf"]

    # Auszahlungen: dieses und letztes Jahr, nicht die in der Zukunft
    assert sorted(b.dateiname for b in je_art["auszahlung"]) == [
        "2025-12-18_auszahlung_9000000000_checkin-2025-12-10.csv",
        "2025-12-18_auszahlung_9000000000_checkin-2025-12-10.pdf",
        "2026-11-19_auszahlung_9000000001_9000000002_checkin-2026-11-12.csv",
        "2026-11-19_auszahlung_9000000001_9000000002_checkin-2026-11-12.pdf"]
    assert not any("000000000003" in s for s in falsches_booking["dateien"])
    assert any("auszahlung" in h.lower() and "nicht verschickt" in h for h in erg.hinweise)

    # Kein Gastname und kein Sitzungsschlüssel in Dateinamen, Feldern, Meldungen oder Ergebnis
    for b in abgeliefert:
        felder = " ".join(str(v) for k, v in vars(b).items() if k != "inhalt")
        assert ERFUNDENER_NAME not in felder and SES not in felder
    menschlich = " ".join(meldungen + erg.abweichungen + erg.hinweise) + repr(erg.als_dict())
    assert ERFUNDENER_NAME not in menschlich and SES not in menschlich

    # Nur Finanzseiten aufgerufen (kein Klick auf „Abmelden“ o. Ä.)
    assert {s.split("?")[0].rsplit("/", 1)[-1] for s in falsches_booking["seiten"]} <= {
        "home.html", "finance_invoices.html", "payouts.html"}

    # Zweiter Lauf: nichts Neues
    vorher = len(abgeliefert)
    falsches_booking["dateien"].clear()
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, meldungen))
    assert erg.status == "ok" and erg.neu == 0 and erg.schon_da == 5 and len(abgeliefert) == vorher
    assert falsches_booking["dateien"] == []


def test_zeitraum_gilt_fuer_alle_arten(tmp_path, falsches_booking):
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    bekannt, abgeliefert = set(), []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, [], ab=date(2026, 1, 1)))
    assert erg.status == "ok"
    namen = sorted(b.dateiname for b in abgeliefert)
    assert [n for n in namen if "_booking_" in n] == [
        "2026-01-03_booking_1111111110.pdf", "2026-10-03_booking_1111111111.pdf",
        "2026-11-03_booking_1111111112.pdf"]  # die Dezember-Rechnung steht im Filter 2025
    assert not any(n.startswith("2025") for n in namen)
    assert erg.uebersprungen == 1  # Rechnung vom 03.12.2025
    # Jahr 2024 wird gar nicht erst aufgerufen, „Letztes Jahr“ bei Auszahlungen nicht gewählt
    assert not any("year=2024" in s for s in falsches_booking["seiten"])
    assert not any("000000000001" in s for s in falsches_booking["dateien"])


def test_abgemeldet(tmp_path, falsches_booking):
    falsches_booking["verhalten"] = "abgemeldet"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is False
    erg = quelle.belege_holen(_umgebung(set(), [], []))
    assert erg.status == "abgelaufen" and erg.neu == 0


def test_fehler_bei_einer_rechnung_ohne_adresse(tmp_path, falsches_booking):
    falsches_booking["verhalten"] = "fehler"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    bekannt, abgeliefert = set(), []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, []))
    assert erg.status == "unvollstaendig" and erg.neu == 4 and erg.erwartet == 5 and erg.vorhanden == 4
    meldung = next(a for a in erg.abweichungen if "1111111111" in a)
    assert "500" in meldung and SES not in meldung and "http" not in meldung
    falsches_booking["verhalten"] = "ok"
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert, []))
    assert erg.status == "ok" and erg.neu == 1


def test_in_der_oberflaeche_waehlbar(tmp_path):
    from belegabruf import einstellungen
    from belegabruf.oberflaeche.aktionen import Steuerung, einstellungen_aus_eingaben

    assert {"name": "booking", "anzeige": "Booking.com"} in Steuerung().zustand()["quellen"]
    einst = einstellungen_aus_eingaben({"belegordner": str(tmp_path / "B"),
                                        "konten": [{"quelle": "booking", "name": ""}]})
    assert [k.anzeige for k in einst.konten] == ["Booking.com"]
    assert einstellungen.aus_text(einstellungen.als_text(einst)).konten[0].quelle == "booking"


# ── Nachbesserung nach der Prüfung (M1, N1–N4) ───────────────────────────────


def test_links_nur_von_admin_booking_com():
    """M1: Nur https://admin.booking.com wird angenommen — fremde Hosts und http nie."""
    roh = [{"href": FREMDER_LINK, "datum": "3. Okt. 2026"},
           {"href": "http://admin.booking.com/fresa/extranet/finance/invoices/get_document?invoice_name=1000-3333333333"},
           {"href": "https://admin.booking.com.andere.example/get_document?invoice_name=1000-4444444444"},
           {"href": "https://admin.booking.com/fresa/extranet/finance/invoices/get_document?invoice_name=1000-1111111111"}]
    assert [r.nummer for r in booking.rechnungen_aus_links(roh)] == ["1111111111"]
    fremd = [{"href": "https://andere.example/fresa/payment/payout/payoutPDF?payout_uuid=aaaaaaaa-0000-0000-0000-000000000009"},
             {"href": "https://andere.example/fresa/payment/payout/monthlyStatementPDF?year=2026&month=1"}]
    assert booking.auszahlungen_aus_links(fremd) == [] and booking.uebersichten_aus_links(fremd) == []


def test_fremder_link_wird_nicht_geholt(tmp_path, falsches_booking):
    falsches_booking["verhalten"] = "fremde_links"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    abgeliefert = []
    erg = quelle.belege_holen(_umgebung(set(), abgeliefert, []))
    assert erg.status == "unvollstaendig" and erg.neu == 5
    assert sorted(a for a in erg.abweichungen if "nicht vom Anbieter" in a) == [
        "Adresse nicht vom Anbieter (http://admin.booking.com), nicht geholt.",
        "Adresse nicht vom Anbieter (https://andere.example), nicht geholt."]  # je Host einmal, ohne Pfad
    assert not any(SES in a or "invoice_name" in a for a in erg.abweichungen)
    assert not any(n in b.dateiname for b in abgeliefert for n in ("2222222222", "3333333333"))
    assert falsches_booking.get("fremd", 0) == 0


class _Seite:
    """Attrappe für _laden: gibt eine vorgegebene fetch-Antwort zurück (oder wirft)."""

    url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/x.html?ses={SES}"

    def __init__(self, antwort):
        self.antwort = antwort

    def evaluate(self, js, argumente):
        if isinstance(self.antwort, Exception):
            raise self.antwort
        return self.antwort


ADRESSE = f"https://admin.booking.com/fresa/x/get_document?ses={SES}"


def test_laden_prueft_ziel_nach_weiterleitung():
    import base64

    q = booking.Booking(Konto("booking", "standard"), None)
    pdf = base64.b64encode(b"%PDF-1.4 x").decode()
    assert q._laden(_Seite({"status": 200, "ziel": ADRESSE, "daten": pdf, "typ": "application/pdf"}), ADRESSE, "pdf")
    with pytest.raises(booking.DateiFehler, match=r"nicht vom Anbieter \(https://andere.example\)"):
        q._laden(_Seite({"status": -1, "ziel": "https://andere.example/x.pdf", "daten": ""}), ADRESSE, "pdf")
    with pytest.raises(booking.DateiFehler, match="nicht vom Anbieter"):
        q._laden(_Seite({}), "https://andere.example/get_document", "pdf")
    # N2: Weiterleitung zur Anmeldung = Sitzung abgelaufen, nicht „unvollständig“
    with pytest.raises(booking.SitzungAbgelaufen):
        q._laden(_Seite({"status": -1, "ziel": "https://account.booking.com/sign-in", "daten": ""}), ADRESSE, "pdf")


def test_laden_fetch_scheitert_dann_sitzung_pruefen(monkeypatch):
    """N2: Scheitert fetch (z. B. Weiterleitung auf account.booking.com, fremder Host), wird in
    einem eigenen Tab geprüft, ob die Anmeldung noch gilt."""
    q = booking.Booking(Konto("booking", "standard"), None)
    monkeypatch.setattr(q, "_abgemeldet", lambda seite: True)
    with pytest.raises(booking.SitzungAbgelaufen):
        q._laden(_Seite(RuntimeError(f"TypeError: Failed to fetch {ADRESSE}")), ADRESSE, "pdf")
    monkeypatch.setattr(q, "_abgemeldet", lambda seite: False)  # K2: z. B. Netz weg → „nicht geladen“
    with pytest.raises(booking.DateiFehler) as fehler:
        q._laden(_Seite(RuntimeError(f"TypeError: Failed to fetch {ADRESSE}")), ADRESSE, "pdf")
    assert SES not in str(fehler.value) and "http" not in str(fehler.value)


def test_abschnitt_kaputt_rest_laeuft_weiter(tmp_path, falsches_booking):
    """N1: Lädt die Auszahlungsseite nicht, sind Rechnungen und Übersichten trotzdem da."""
    falsches_booking["verhalten"] = "auszahlungen_kaputt"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    abgeliefert = []
    erg = quelle.belege_holen(_umgebung(set(), abgeliefert, []))
    assert erg.status == "unvollstaendig" and erg.neu == 5
    assert {b.art for b in abgeliefert} == {"rechnung", "auszahlungsuebersicht"}
    meldung = next(a for a in erg.abweichungen if a.startswith("Auszahlungen: abgebrochen"))
    assert SES not in meldung and "http" not in meldung


@pytest.mark.parametrize("wert", ["12345a", "../x", ["111", "abc"], ","])
def test_unterkunft_ungueltig_wird_gemeldet(tmp_path, wert):
    """N3: Eine ungültige Einstellung „unterkunft“ wird nicht still verworfen."""
    with pytest.raises(booking.UnterkunftUngueltig):
        booking.unterkunft_einstellung(wert)
    quelle = booking.Booking(Konto("booking", "standard", optionen={"unterkunft": wert}), tmp_path / "profil")
    erg = quelle.belege_holen(_umgebung(set(), [], []))
    assert erg.status == "fehler" and "unterkunft" in erg.fehler and "Ziffern" in erg.fehler


def test_ohne_jahresfilter_unvollstaendig_mit_hinweis(tmp_path, falsches_booking):
    """N4: Ohne Jahresfilter nicht still nur das laufende Jahr: die Jahre kommen über die
    Adresse, und das Ergebnis sagt, dass ältere fehlen können."""
    falsches_booking["verhalten"] = "ohne_filter"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    abgeliefert = []
    erg = quelle.belege_holen(_umgebung(set(), abgeliefert, []))
    assert erg.status == "unvollstaendig"
    assert any("Jahresfilter nicht gefunden" in a and "2026, 2025, 2024" in a for a in erg.abweichungen)
    assert sum(1 for b in abgeliefert if b.art == "rechnung") == 5


# ── 2.1.1: K1 Listen in der Einstellungsdatei ────────────────────────────────


def test_unterkunft_als_liste_uebersteht_speichern(tmp_path):
    """K1: Eine Liste (und andere Werte) in den Konto-Optionen bleibt nach dem Speichern über
    die Oberfläche, was sie war — früher wurde daraus der Text "['1', '2']"."""
    from belegabruf import einstellungen
    from belegabruf.oberflaeche.aktionen import einstellungen_aus_eingaben

    datei = pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(f'belegordner = "{(tmp_path / "B").as_posix()}"\n\n[[konto]]\nquelle = "booking"\nname = ""\n'
                     'unterkunft = ["1234567", "7654321"]\nzahl = 3\nschalter = true\n', encoding="utf-8")
    vorher = einstellungen.laden().konten[0].optionen
    neu = einstellungen_aus_eingaben({"belegordner": str(tmp_path / "B"),
                                      "konten": [{"quelle": "booking", "name": "", "kennung": "standard"}]})
    einstellungen.speichern(neu)
    nachher = einstellungen.laden().konten[0].optionen
    assert nachher == vorher == {"unterkunft": ["1234567", "7654321"], "zahl": 3, "schalter": True}
    assert booking.unterkunft_einstellung(nachher["unterkunft"]) == ["1234567", "7654321"]


# ── Anmeldung erst mit Inhalt (2.2.2: offene Zwei-Faktor-Bestätigung) ─────────

EXTRANET_URL = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/home.html?hotel_id={HOTEL}&ses={SES}"
UNTERKUNFT_LINK = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/x.html?hotel_id={HOTEL}&ses={SES}"


def test_angemeldet_nur_mit_inhalt():
    assert booking.angemeldet(EXTRANET_URL, [UNTERKUNFT_LINK])
    # Zwei-Faktor offen: Adresse wie das Extranet (mit ses), aber keine Unterkunft auf der Seite
    assert not booking.angemeldet(EXTRANET_URL, [])
    assert not booking.angemeldet(EXTRANET_URL, ["https://admin.booking.com/hilfe.html"])
    assert not booking.angemeldet(EXTRANET_URL, [f"https://andere.example/x.html?hotel_id={HOTEL}"])
    assert not booking.angemeldet(EXTRANET_URL, ["https://admin.booking.com/x.html?hotel_id=abc"])
    assert not booking.angemeldet(EXTRANET_URL.replace(f"&ses={SES}", ""), [UNTERKUNFT_LINK])
    assert not booking.angemeldet("https://account.booking.com/sign-in?ses=x", [UNTERKUNFT_LINK])


class _AnmeldeSeite:
    """Attrappe für _angemeldet bzw. den Prüfer im Anmeldefenster."""

    def __init__(self, url, links):
        self.url, self.links = url, links

    def wait_for_selector(self, selektor, timeout):
        if not self.links:
            raise TimeoutError("kein Inhalt")

    def evaluate(self, js, *argumente):
        return self.links


def test_fenster_bleibt_offen_bei_zwei_faktor(monkeypatch):
    monkeypatch.setattr(booking, "ZWEI_FAKTOR_HINWEIS_NACH_S", 0)
    q = booking.Booking(Konto("booking", "standard"), None)
    meldungen: list[str] = []
    fertig = q._fertig_pruefer(meldungen.append)
    halb = _AnmeldeSeite(EXTRANET_URL, [])
    assert fertig(halb) is False and fertig(halb) is False
    assert meldungen == [booking.ZWEI_FAKTOR_HINWEIS]  # genau einmal
    assert "Zwei-Faktor" in meldungen[0] and SES not in meldungen[0]
    assert fertig(_AnmeldeSeite("https://account.booking.com/sign-in", [])) is False
    assert fertig(_AnmeldeSeite(EXTRANET_URL, [UNTERKUNFT_LINK])) is True
    assert q._angemeldet(halb, warten_ms=100) is False
    assert q._angemeldet(_AnmeldeSeite(EXTRANET_URL, [UNTERKUNFT_LINK]), warten_ms=100) is True


def test_kein_hinweis_solange_die_seite_kurz_laedt():
    q = booking.Booking(Konto("booking", "standard"), None)
    meldungen: list[str] = []
    fertig = q._fertig_pruefer(meldungen.append)
    assert fertig(_AnmeldeSeite(EXTRANET_URL, [])) is False
    assert meldungen == []  # erst nach ZWEI_FAKTOR_HINWEIS_NACH_S


def test_zwei_faktor_offen_gilt_nicht_als_angemeldet(tmp_path, falsches_booking, monkeypatch):
    """Extranet-Adresse mit ses, aber ohne Unterkunft: Prüfung, Abruf und Anmeldefenster sagen
    „nicht angemeldet“ — das Fenster wartet weiter (hier: bis zum Zeitlimit)."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    monkeypatch.setattr(booking, "ZWEI_FAKTOR_HINWEIS_NACH_S", 0)
    falsches_booking["verhalten"] = "zwei_faktor"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is False
    erg = quelle.belege_holen(_umgebung(set(), [], []))
    assert erg.status == "abgelaufen" and erg.neu == 0
    assert falsches_booking["dateien"] == []

    gesehen: list[bool] = []

    def warten(kontext, seite, fertig, hinweis, **k):
        assert booking.ist_extranet(seite.url)  # die Adresse sieht schon aus wie das Extranet
        gesehen.extend([fertig(seite), fertig(seite)])
        return "zeit"

    monkeypatch.setattr(browser, "auf_mensch_warten", warten)
    meldungen: list[str] = []
    assert quelle.anmelden_lassen(meldungen.append) is False
    assert gesehen == [False, False]
    assert meldungen.count(booking.ZWEI_FAKTOR_HINWEIS) == 1
    assert not any(SES in m for m in meldungen)


def test_normalfall_angemeldet(tmp_path, falsches_booking, monkeypatch):
    def warten(*a, **k):
        raise AssertionError("schon angemeldet: kein Warten")

    monkeypatch.setattr(browser, "auf_mensch_warten", warten)
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is True
    assert quelle.anmelden_lassen(lambda t: None) is True


def test_zwei_faktor_mitten_im_abruf(tmp_path, falsches_booking, monkeypatch):
    """Startseite angemeldet, aber die Finanzseite zeigt eine Bestätigung: „abgelaufen“ mit
    Hinweis — nicht „0 Belege, alles gut“ und keine Abschnittsfehler."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "zwei_faktor_mittendrin"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    meldungen: list[str] = []
    erg = quelle.belege_holen(_umgebung(set(), [], meldungen))
    assert erg.status == "abgelaufen" and erg.neu == 0
    assert booking.BESTAETIGEN_HINWEIS in erg.hinweise
    assert erg.abweichungen == []
    assert not any(SES in m for m in meldungen + erg.hinweise)


def test_kein_finanzzugriff(tmp_path, falsches_booking, monkeypatch):
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "kein_zugriff"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    erg = quelle.belege_holen(_umgebung(set(), [], []))
    assert erg.status == "fehler" and erg.fehler == booking.KEIN_ZUGRIFF_TEXT
    assert "keinen Zugriff auf Finanzen" in erg.fehler


@pytest.mark.parametrize("status, text, erwartet", [
    (403, "", True),
    (200, "Sie haben keinen Zugriff auf diese Seite.", True),
    (200, "Sie haben keinen\nZugriff auf diese Seite.", True),
    (200, "You don't have access to this page", True),
    (200, "You don’t have permission to view finance", True),
    (200, "Access denied.", True),
    (200, "No access", True),
    (200, "Not authorized", True),
    (200, "Zugriff verweigert", True),
    (200, "Zahlungen an Booking.com  Nach Jahr filtern 2026", False),
    (None, "", False),
    # Fast-Treffer: nur Wortteile, kein Hinweis auf fehlende Rechte
    (200, "Diese Funktion ist no accessible yet", False),
    (200, "Einstellungen für nicht berechtigte Zahlungen", False),
    (200, "Mehr zu keine Berechtigungsstufen", False),
    (200, "Tab: not_authorizedx", False),
    (200, "Siehe access deniedlist", False),
    (200, "Unterkunft keinen Zugriffscode nötig", False),
])
def test_ohne_finanz_zugriff(status, text, erwartet):
    assert booking.ohne_finanz_zugriff(status, text) is erwartet


def test_kein_finanzzugriff_bei_einer_unterkunft(tmp_path, falsches_booking, monkeypatch):
    """Co-Hosting: Für eine der beiden Unterkünfte fehlt das Recht „Finance“. Die andere wird
    trotzdem geholt, das Konto ist „unvollständig“ mit einem Hinweis zu genau dieser Unterkunft."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "kein_zugriff_teil"
    konto = Konto("booking", "standard", optionen={"unterkunft": f"{HOTEL}, {ANDERES_HOTEL}"})
    quelle = booking.Booking(konto, tmp_path / "profil")
    abgeliefert: list = []
    erg = quelle.belege_holen(_umgebung(set(), abgeliefert, []))
    assert erg.status == "unvollstaendig" and erg.fehler == ""
    assert {b.art for b in abgeliefert} == {"rechnung", "auszahlungsuebersicht", "auszahlung"}
    hinweis = [a for a in erg.abweichungen if "kein Zugriff auf Finanzen" in a]
    assert len(hinweis) == 1 and ANDERES_HOTEL in hinweis[0] and "Finance" in hinweis[0]
    assert not any(HOTEL in a for a in erg.abweichungen)


def test_kein_finanzzugriff_bei_allen_unterkuenften(tmp_path, falsches_booking, monkeypatch):
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "kein_zugriff"
    konto = Konto("booking", "standard", optionen={"unterkunft": f"{HOTEL}, {ANDERES_HOTEL}"})
    erg = booking.Booking(konto, tmp_path / "profil").belege_holen(_umgebung(set(), [], []))
    assert erg.status == "fehler" and erg.fehler == booking.KEIN_ZUGRIFF_TEXT


def test_403_ohne_menue_ist_kein_zugriff(tmp_path, falsches_booking, monkeypatch):
    """Eine 403-Seite ohne Extranet-Menü heißt „kein Zugriff“ — nicht „Zwei-Faktor verlangt“."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "kein_zugriff_403"
    quelle = booking.Booking(Konto("booking", "standard"), tmp_path / "profil")
    erg = quelle.belege_holen(_umgebung(set(), [], []))
    assert erg.status == "fehler" and erg.fehler == booking.KEIN_ZUGRIFF_TEXT
    assert booking.BESTAETIGEN_HINWEIS not in erg.hinweise


def test_403_mit_codefeld_ist_bestaetigung(tmp_path, falsches_booking, monkeypatch):
    """403 mit Code-Feld: erneute Bestätigung, nicht „Recht Finance holen“."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "403_mit_code"
    erg = booking.Booking(Konto("booking", "standard"), tmp_path / "profil").belege_holen(_umgebung(set(), [], []))
    assert erg.status == "abgelaufen" and booking.BESTAETIGEN_HINWEIS in erg.hinweise
    assert erg.fehler == "" and not any("Finance" in a for a in erg.abweichungen)


def test_403_sperrseite_ist_kein_rechteproblem(tmp_path, falsches_booking, monkeypatch):
    """Sperrseite des Netzwerkdienstes („Access Denied … Reference #“): nicht geladen, kein „Finance“-Hinweis."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "403_sperre"
    erg = booking.Booking(Konto("booking", "standard"), tmp_path / "profil").belege_holen(_umgebung(set(), [], []))
    assert erg.status == "unvollstaendig" and erg.fehler == ""
    assert any("gesperrt (403)" in a for a in erg.abweichungen)
    assert not any("Finance" in a for a in erg.abweichungen)


def test_403_erst_bei_auszahlungen_nur_dieser_abschnitt(tmp_path, falsches_booking, monkeypatch):
    """Rechnungen geholt, erst die Auszahlungsseite verweigert: „unvollständig“, nicht „fehler“."""
    monkeypatch.setattr(booking, "INHALT_WARTEN_MS", 1500)
    falsches_booking["verhalten"] = "403_auszahlungen"
    abgeliefert: list = []
    erg = booking.Booking(Konto("booking", "standard"), tmp_path / "profil").belege_holen(
        _umgebung(set(), abgeliefert, []))
    assert erg.status == "unvollstaendig" and erg.fehler == ""
    assert {b.art for b in abgeliefert} >= {"rechnung", "auszahlungsuebersicht"}
    assert "auszahlung" not in {b.art for b in abgeliefert}
    assert erg.abweichungen == ["Auszahlungen: kein Zugriff (Booking.com verweigert diese Seite)."]
