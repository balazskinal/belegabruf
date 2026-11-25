"""Mail und sevDesk zusammen: Ein Ziel hält das andere nie auf. Nur Attrappen."""

from __future__ import annotations

from pathlib import Path

import pytest

import test_mail as tm
import test_sevdesk as ts
from belegabruf import ablauf, pfade
from belegabruf.einstellungen import Einstellungen, Konto, MailEinstellung, SevDeskEinstellung
from belegabruf.protokoll import Protokoll
from belegabruf.ziele import mail, sevdesk


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


@pytest.fixture
def beide(monkeypatch):
    server = tm.Server()
    tm.FalschesSMTP.server = server
    monkeypatch.setattr(mail.smtplib, "SMTP", tm.FalschesSMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", tm.FalschesSMTP_SSL)
    monkeypatch.setattr(mail, "passwort_lesen", lambda d, k: tm.PLATZHALTER)
    api = ts.Attrappe()
    monkeypatch.setattr(sevdesk.urllib.request, "urlopen", api)
    monkeypatch.setattr(sevdesk, "schluessel_lesen", lambda d, k: ts.PLATZHALTER)
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: tm.Falsch(konto, Path("/x")))
    monkeypatch.setattr(ablauf.zustand, "lauf_merken", lambda *a: None)
    return server, api


def _einst(tmp_path) -> Einstellungen:
    return Einstellungen(
        belegordner=tmp_path / "Belege", konten=[Konto("airbnb", "privat")],
        ziele=["ordner", "mail", "sevdesk"],
        mail=MailEinstellung(server="smtp.example.com", verschluesselung="ssl", benutzer="ich@example.com",
                             absender="ich@example.com", empfaenger=[tm.A]),
        sevdesk=SevDeskEinstellung(steuerregel="14"),
    )


def _lauf(einst):
    return ablauf.abrufen(einst, einst.konten[0], lambda t: None)


def test_beide_ziele_bekommen_jede_rechnung(tmp_path, beide):
    server, api = beide
    tm.Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(_einst(tmp_path))
    assert erg.lieferungen[mail.ziel_name(tm.A)]["geliefert"] == 1
    assert erg.lieferungen["sevdesk"]["geliefert"] == 1
    p = Protokoll("airbnb", "privat", tmp_path / "Belege")
    assert p.ziele_von("rechnung:a1") == ["ordner", "mail:beleg@example.com", "sevdesk"]
    assert p.kennung("rechnung:a1", "sevdesk") == "901"
    text = ablauf.zusammenfassung([erg], tmp_path)
    assert "Mail an beleg@example.com: 1 verschickt" in text
    assert "sevDesk: 1 als Entwurf hochgeladen" in text


def test_falsches_mailpasswort_haelt_sevdesk_nicht_auf(tmp_path, beide):
    server, api = beide
    server.verhalten = "anmeldung"
    tm.Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(_einst(tmp_path))
    assert erg.lieferungen[mail.ziel_name(tm.A)]["offen"] == 1
    assert erg.lieferungen["sevdesk"]["geliefert"] == 1


def test_sevdesk_ohne_antwort_haelt_mail_nicht_auf(tmp_path, beide):
    server, api = beide
    api.verhalten = "zeitueberschreitung"
    tm.Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1"), ("a2", "2026-11-04", "AIUC-2")]
    erg = _lauf(_einst(tmp_path))
    assert erg.lieferungen["sevdesk"]["unklar"] == ["AIUC-1"]
    assert erg.lieferungen[mail.ziel_name(tm.A)]["geliefert"] == 2


def test_sevdesk_schluessel_fehlt_mail_geht_trotzdem(tmp_path, beide, monkeypatch):
    def fehlt(d, k):
        raise sevdesk.SchluesselFehlt("kein Schlüssel")

    monkeypatch.setattr(sevdesk, "schluessel_lesen", fehlt)
    tm.Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(_einst(tmp_path))
    assert erg.lieferungen["sevdesk"]["fehler"] == "kein Schlüssel" and erg.lieferungen["sevdesk"]["offen"] == 1
    assert erg.lieferungen[mail.ziel_name(tm.A)]["geliefert"] == 1
