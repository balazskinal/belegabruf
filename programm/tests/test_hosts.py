"""Gemeinsame Host-Prüfung (2.1.1): Belege kommen nur vom Anbieter selbst.

Alle Adressen sind erfunden bzw. die öffentlichen Startadressen der Anbieter; kein Netz.
"""

from __future__ import annotations

import pytest

from belegabruf import pfade, pruefung
from belegabruf.einstellungen import Konto


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


HOSTS = {"www.airbnb.de"}


@pytest.mark.parametrize("url, erlaubt", [
    ("https://www.airbnb.de/invoice/abc", True),
    ("https://WWW.AIRBNB.DE/invoice/abc", True),
    ("https://www.airbnb.de:443/invoice/abc", True),
    ("http://www.airbnb.de/invoice/abc", False),
    ("https://www.airbnb.de:8443/invoice/abc", False),
    ("https://www.airbnb.de@andere.example/invoice/abc", False),
    ("https://nutzer:pw@www.airbnb.de/invoice/abc", False),
    ("https://www.airbnb.de＠andere.example/invoice/abc", False),  # Vollbreiten-@
    ("https://www.airbnb.de.andere.example/invoice/abc", False),
    ("https://andere.example/www.airbnb.de/invoice/abc", False),
    ("https://airbnb.de/invoice/abc", False),  # nur genau der erlaubte Host
    ("https://www.airbnb.de./invoice/abc", False),
    ("//www.airbnb.de/invoice/abc", False),
    ("javascript:alert(1)", False),
    ("", False),
    ("https://[::1]/x", False),
    ("https://www.airbnb.de:abc/x", False),
])
def test_adresse_erlaubt(url, erlaubt):
    assert pruefung.adresse_erlaubt(url, HOSTS) is erlaubt


def test_endung_eng_gefasst():
    assert pruefung.adresse_erlaubt("https://rechnung.anbieter.example/x", set(), ("anbieter.example",))
    assert not pruefung.adresse_erlaubt("https://anbieter.example.andere.example/x", set(), ("anbieter.example",))
    assert not pruefung.adresse_erlaubt("https://boeseanbieter.example/x", set(), ("anbieter.example",))


def test_meldung_nur_mit_herkunft():
    with pytest.raises(pruefung.FremdeAdresse) as info:
        pruefung.adresse_pruefen("https://andere.example:8443/pfad/geheim?ses=SITZUNG&sig=abc", HOSTS)
    text = str(info.value)
    assert text == "Adresse nicht vom Anbieter (https://andere.example:8443), nicht geholt"
    assert "geheim" not in text and "SITZUNG" not in text and "sig" not in text
    assert pruefung.herkunft("https://nutzer:pw@andere.example/x") == "https://andere.example"


# ── Airbnb und Skool: vor dem Aufruf und nach einer Weiterleitung ────────────


class _Seite:
    """Attrappe: goto merkt sich die Adresse; ``umleitung`` simuliert eine Weiterleitung."""

    def __init__(self, umleitung: str = ""):
        self.aufrufe: list[str] = []
        self.umleitung = umleitung
        self.url = "about:blank"

    def goto(self, url, **kwargs):
        self.aufrufe.append(url)
        self.url = self.umleitung or url
        return type("Antwort", (), {"status": 200})()

    def wait_for_load_state(self, *a, **k):
        pass


def _airbnb():
    from belegabruf.quellen.airbnb import Airbnb, Zeile

    quelle = Airbnb(Konto("airbnb", "a"), None)
    return quelle, Zeile


@pytest.mark.parametrize("link", [
    "https://andere.example/invoice/abc",
    "http://www.airbnb.de/invoice/abc",
    "https://www.airbnb.de:8443/invoice/abc",
    "https://www.airbnb.de＠andere.example/invoice/abc",
])
def test_airbnb_fremder_link_wird_nicht_aufgerufen(link):
    quelle, Zeile = _airbnb()
    seite = _Seite()
    with pytest.raises(pruefung.FremdeAdresse):
        quelle._einzelrechnung(seite, Zeile(kennung="abc", url=link), None, None)
    assert seite.aufrufe == []


def test_airbnb_weiterleitung_auf_fremden_host():
    quelle, Zeile = _airbnb()
    seite = _Seite(umleitung="https://andere.example/gefaelscht?token=geheim")
    with pytest.raises(pruefung.FremdeAdresse) as info:
        quelle._einzelrechnung(seite, Zeile(kennung="abc", url="/invoice/abc"), None, None)
    assert seite.aufrufe == ["https://www.airbnb.de/invoice/abc"] and "geheim" not in str(info.value)


def test_airbnb_eingestellte_laenderadresse_gilt():
    from belegabruf.quellen.airbnb import Airbnb

    quelle = Airbnb(Konto("airbnb", "a", optionen={"adresse": "https://www.airbnb.at"}), None)
    assert quelle._hosts() == {"www.airbnb.at"}


def test_skool_weiterleitung_auf_fremden_host():
    from belegabruf.quellen.skool import Skool, Zahlung

    quelle = Skool(Konto("skool", "s"), None)
    zahlung = Zahlung(kennung="in_abc", gruppe="gemeinschaft", pfad="/gemeinschaft/--/inv/in_abc", datum=None)
    seite = _Seite(umleitung="https://andere.example/inv?sig=geheim")
    with pytest.raises(pruefung.FremdeAdresse) as info:
        quelle._einzelrechnung(seite, zahlung, None, None)
    assert seite.aufrufe == ["https://www.skool.com/gemeinschaft/--/inv/in_abc"] and "geheim" not in str(info.value)
    assert quelle._hosts() == {"www.skool.com"}


def test_skool_fremde_adresse_eingestellt_wird_nicht_aufgerufen():
    from belegabruf.quellen.skool import Skool, Zahlung

    quelle = Skool(Konto("skool", "s"), None)
    monkey = Zahlung(kennung="in_abc", gruppe="x", pfad="@andere.example/inv", datum=None)  # Pfad, der den Host ändert
    seite = _Seite()
    with pytest.raises(pruefung.FremdeAdresse):
        quelle._einzelrechnung(seite, monkey, None, None)
    assert seite.aufrufe == []


def test_booking_nutzt_dieselbe_pruefung():
    from belegabruf.quellen import booking

    assert booking.ist_eigene_adresse("https://admin.booking.com/fresa/x")
    for fremd in ("http://admin.booking.com/x", "https://admin.booking.com:8443/x",
                  "https://admin.booking.com＠andere.example/x", "https://andere.example/x"):
        assert not booking.ist_eigene_adresse(fremd)
