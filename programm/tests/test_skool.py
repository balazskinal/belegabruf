"""Baustein Skool — mit erfundenen Seiten, nie gegen das echte Skool.

Alle Namen, Gruppen und Beträge sind erfunden.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from belegabruf import browser, pfade, pruefung
from belegabruf.einstellungen import Konto
from belegabruf.quellen import skool
from belegabruf.quellen.basis import Umgebung


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


# ── Lesen ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text, erwartet", [
    ("Oktober 25. 2026", date(2026, 10, 25)),
    ("October 25, 2026", date(2026, 10, 25)),
    ("25. Oktober 2026", date(2026, 10, 25)),
    ("Oct 5, 2026", date(2026, 10, 5)),
    ("März 1. 2026", date(2026, 3, 1)),
    ("Sept 30, 2026", date(2026, 9, 30)),
    ("Mai 31. 2026", date(2026, 5, 31)),
    ("Rechnung", None),
    ("Februar 30. 2026", None),
])
def test_datum_aus_text(text, erwartet):
    assert skool.datum_aus_text(text) == erwartet


def test_uebersicht_lesen():
    links = [
        ("/beispielgruppe/--/inv/in_1AAA111?cus=true", "Oktober 25. 2026"),
        ("/beispielgruppe/--/inv/in_1AAA111?cus=true", ""),  # derselbe Link noch einmal
        ("https://www.skool.com/andere-gruppe/--/inv/in_2BBB222?cus=true", "September 25. 2026"),
        ("/beispielgruppe/about", "Über uns"),  # kein Rechnungslink
        ("/settings?t=payment-methods", "Zahlungsmethoden"),
    ]
    zahlungen = skool.uebersicht_lesen(links)
    assert [(z.kennung, z.gruppe, z.datum) for z in zahlungen] == [
        ("in_1AAA111", "beispielgruppe", date(2026, 10, 25)),
        ("in_2BBB222", "andere-gruppe", date(2026, 9, 25)),
    ]
    assert zahlungen[1].pfad == "/andere-gruppe/--/inv/in_2BBB222?cus=true"


RECHNUNG_DE = """Rechnung
Rechnung 1A2B3C4D-0007
Beispielgruppe über Skool.com
An: Erika Muster, erika@example.com
Von: Skool.com Inc., United States
Beschreibung Menge Einzelpreis Betrag
Mitgliedschaft 1 $49.00 $49.00
Gesamt $49.00 USD
"""

RECHNUNG_EN = RECHNUNG_DE.replace("Rechnung", "Invoice").replace("über", "via").replace(
    "Beschreibung Menge Einzelpreis Betrag", "Description Qty Unit price Amount").replace("Gesamt", "Total")


def test_rechnung_pruefen():
    assert skool.rechnung_pruefen(RECHNUNG_DE) is None
    assert skool.rechnung_pruefen(RECHNUNG_EN) is None
    assert skool.rechnung_pruefen("") == "leere Seite"
    anmeldung = "Log in to Skool. Email Password Log in. Don't have an account? Sign up for free today and join."
    assert skool.rechnung_pruefen(anmeldung) == "Anmeldeseite"
    fehler = "404 — Page not found. We can't seem to find the page you are looking for. Back to the homepage."
    assert skool.rechnung_pruefen(fehler) == "Fehlerseite (z. B. 404)"
    ohne_betrag = RECHNUNG_DE.replace("Gesamt $49.00 USD", "").replace("$49.00", "")
    assert "Gesamtbetrag" in skool.rechnung_pruefen(ohne_betrag)


def test_rechnungsseite_lesen():
    daten = skool.rechnungsseite_lesen(RECHNUNG_DE)
    assert daten.rechnungsnummer == "1A2B3C4D-0007"
    assert daten.gesamt.startswith("$49.00")
    assert skool.rechnungsseite_lesen(RECHNUNG_EN).gesamt.startswith("$49.00")


def test_dateiname():
    assert skool.dateiname(date(2026, 10, 25), "beispielgruppe", "in_1AAA111") == \
        "2026-10-25_beispielgruppe_in_1AAA111.pdf"
    assert skool.dateiname(None, "a/../b", "in_1") == "ohne-datum_ab_in_1.pdf"


def test_quelle_bekannt():
    from belegabruf import quellen

    assert quellen.klasse("skool") is skool.Skool
    assert quellen.anzeigename("skool") == "Skool"


# ── Ganzer Ablauf im echten (unsichtbaren) Browser, mit erfundenen Seiten ────


UEBERSICHT_HTML = """<!doctype html><html><body><h1>Einstellungen</h1><h2>Zahlungsverlauf</h2>
<ul>
<li><a href="/beispielgruppe/--/inv/in_1AAA111?cus=true">Oktober 25. 2026</a></li>
<li><a href="/beispielgruppe/--/inv/in_1BBB222?cus=true">September 25. 2026</a></li>
<li><a href="/andere-gruppe/--/inv/in_1CCC333?cus=true">August 25. 2026</a></li>
</ul>
<button onclick="document.title='GEKLICKT'">Abo kündigen</button>
</body></html>"""


def _rechnung_html(nummer: str) -> str:
    zeilen = RECHNUNG_DE.replace("1A2B3C4D-0007", nummer).splitlines()
    return "<!doctype html><html><head><title>Rechnung · Skool</title></head><body>" + "".join(
        f"<p>{z}</p>" for z in zeilen) + "</body></html>"


def _chromium_da() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(channel="chromium", headless=True).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def falsches_skool(monkeypatch):
    """Leitet alle Aufrufe an www.skool.com auf erfundene Seiten um."""
    if not _chromium_da():
        pytest.skip("Chromium nicht installiert")
    aufrufe: list[str] = []
    seiten = {"verhalten": "ok"}
    original = browser.profil_oeffnen

    def antworten(route):
        url = route.request.url
        aufrufe.append(url)
        pfad = url.removeprefix("https://www.skool.com")
        if seiten["verhalten"] == "abgemeldet" or pfad.startswith("/login"):
            if not pfad.startswith("/login"):
                return route.fulfill(status=302, headers={"Location": "https://www.skool.com/login"})
            return route.fulfill(content_type="text/html", body="<html><body><h1>Log in</h1>"
                                 "<input type=password> Password Log in Sign up for free</body></html>")
        if pfad.startswith("/settings"):
            return route.fulfill(content_type="text/html", body=UEBERSICHT_HTML)
        if "/--/inv/" in pfad:
            kennung = pfad.split("/--/inv/")[1].split("?")[0]
            if seiten["verhalten"] == "leer" and kennung == "in_1BBB222":
                return route.fulfill(content_type="text/html", body="<html><body></body></html>")
            return route.fulfill(content_type="text/html", body=_rechnung_html(f"TEST{kennung[-3:]}-0001"))
        return route.fulfill(status=404, body="404 Page not found")

    @contextmanager
    def profil_mit_umleitung(profil, sichtbar):
        with original(profil, sichtbar=False) as kontext:
            kontext.route("https://www.skool.com/**", antworten)
            yield kontext

    monkeypatch.setattr(browser, "profil_oeffnen", profil_mit_umleitung)
    monkeypatch.setattr(browser, "pause", lambda *a, **k: None)
    return aufrufe, seiten


def _umgebung(bekannt: set[str], abgeliefert: list):
    def abliefern(beleg):
        abgeliefert.append(beleg)
        bekannt.add(beleg.schluessel)
        return [beleg.dateiname]

    return Umgebung(bekannt=lambda s: s in bekannt, abliefern=abliefern,
                    vorhandene_datei=lambda s: None, melden=lambda t: None)


def test_ablauf_holt_alle_rechnungen(tmp_path, falsches_skool):
    aufrufe, _ = falsches_skool
    quelle = skool.Skool(Konto("skool", "test"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is True
    bekannt, abgeliefert = set(), []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert))
    assert erg.status == "ok" and erg.neu == 3 and erg.erwartet == 3 and erg.vorhanden == 3
    assert [b.dateiname for b in abgeliefert] == [
        "2026-10-25_beispielgruppe_in_1AAA111.pdf",
        "2026-09-25_beispielgruppe_in_1BBB222.pdf",
        "2026-08-25_andere-gruppe_in_1CCC333.pdf",
    ]
    erste = abgeliefert[0]
    assert erste.schluessel == "rechnung:in_1AAA111" and erste.rechnungsnummer == "TEST111-0001"
    assert erste.rechnungsdatum == date(2026, 10, 25) and erste.jahr == 2026
    assert pruefung.ist_pdf(erste.inhalt) and "Gesamt" in pruefung.pdf_text(erste.inhalt)
    # Nur Seiten aufgerufen, nichts geklickt: keine Kündigung, keine Zahlungsmethoden.
    assert not any("cancel" in u or "payment-methods" in u for u in aufrufe)

    # Zweiter Lauf: nichts Neues
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert))
    assert erg.neu == 0 and erg.schon_da == 3 and len(abgeliefert) == 3


def test_leere_seite_wird_nicht_gespeichert(tmp_path, falsches_skool):
    _, seiten = falsches_skool
    seiten["verhalten"] = "leer"
    quelle = skool.Skool(Konto("skool", "test"), tmp_path / "profil")
    bekannt, abgeliefert = set(), []
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert))
    assert erg.status == "unvollstaendig" and erg.neu == 2 and erg.vorhanden == 2 and erg.erwartet == 3
    assert any("in_1BBB222" in a and "leere Seite" in a for a in erg.abweichungen)
    seiten["verhalten"] = "ok"
    erg = quelle.belege_holen(_umgebung(bekannt, abgeliefert))  # nächster Lauf holt sie nach
    assert erg.neu == 1 and erg.status == "ok"


def test_abgemeldet(tmp_path, falsches_skool):
    _, seiten = falsches_skool
    seiten["verhalten"] = "abgemeldet"
    quelle = skool.Skool(Konto("skool", "test"), tmp_path / "profil")
    assert quelle.sitzung_pruefen() is False
    erg = quelle.belege_holen(_umgebung(set(), []))
    assert erg.status == "abgelaufen" and erg.neu == 0
