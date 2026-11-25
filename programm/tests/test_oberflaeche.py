"""Bedienoberfläche: Sicherheit des lokalen Servers und die Abläufe im (unsichtbaren) Browser.

Nur Attrappen: keine echten Anbieter, kein echter Passwortspeicher, kein echter Mailserver.
"""

from __future__ import annotations

import http.client
import json
from datetime import date
from pathlib import Path

import pytest

from belegabruf import ablauf, browser, einstellungen, pfade
from belegabruf.oberflaeche import aktionen
from belegabruf.oberflaeche.server import KOPF_SCHLUESSEL, Bedienserver
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle
from belegabruf.ziele import mail

GEHEIM = "streng-geheimes-passwort-4711"


@pytest.fixture(autouse=True)
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    monkeypatch.setattr(pfade, "standard_belegordner", lambda: tmp_path / "Belege")
    monkeypatch.setattr(aktionen.aktualisierung, "neuere_version", lambda: None)
    speicher = {}
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda d, k: speicher.get((d, k)))
    monkeypatch.setattr(keyring, "set_password", lambda d, k, w: speicher.__setitem__((d, k), w))
    yield speicher
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


@pytest.fixture
def server():
    s = Bedienserver()
    s.im_hintergrund()
    yield s
    s.shutdown()
    s.server_close()


def _anfrage(s: Bedienserver, methode: str, pfad: str, kopf: dict | None = None, rumpf=None, host=None):
    verbindung = http.client.HTTPConnection("127.0.0.1", s.port, timeout=10)
    koepfe = {"Host": host or f"127.0.0.1:{s.port}"}
    koepfe.update(kopf or {})
    daten = None
    if rumpf is not None:
        daten = json.dumps(rumpf).encode()
        koepfe.setdefault("Content-Type", "application/json")
    verbindung.request(methode, pfad, body=daten, headers=koepfe)
    antwort = verbindung.getresponse()
    inhalt = antwort.read()
    verbindung.close()
    return antwort, inhalt


def _mit(s):
    return {KOPF_SCHLUESSEL: s.schluessel}


# ── Sicherheit ───────────────────────────────────────────────────────────────


def test_nur_127_0_0_1_und_freier_port(server):
    assert server.server_address[0] == "127.0.0.1" and server.port > 0
    assert len(server.schluessel) >= 40


def test_seite_nur_mit_schluessel(server):
    assert _anfrage(server, "GET", "/")[0].status == 403
    assert _anfrage(server, "GET", "/?k=falsch")[0].status == 403
    antwort, inhalt = _anfrage(server, "GET", f"/?k={server.schluessel}")
    assert antwort.status == 200 and b"Belegabruf" in inhalt
    # Der Schlüssel steht nicht in der Seite selbst
    assert server.schluessel.encode() not in inhalt


def test_api_nur_mit_schluessel_im_kopf(server):
    assert _anfrage(server, "GET", "/api/zustand")[0].status == 403
    assert _anfrage(server, "GET", f"/api/zustand?k={server.schluessel}")[0].status == 403  # nicht in der Adresse
    assert _anfrage(server, "GET", "/api/zustand", {KOPF_SCHLUESSEL: "falsch"})[0].status == 403
    assert _anfrage(server, "GET", "/api/zustand", _mit(server))[0].status == 200


@pytest.mark.parametrize("host", ["evil.example.com", "localhost:{port}", "127.0.0.1", "127.0.0.1:1",
                                  "evil.example.com:{port}"])
def test_fremder_host_kopf_abgelehnt_dns_rebinding(server, host):
    host = host.format(port=server.port)
    assert _anfrage(server, "GET", f"/?k={server.schluessel}", host=host)[0].status == 403
    assert _anfrage(server, "GET", "/api/zustand", _mit(server), host=host)[0].status == 403
    assert _anfrage(server, "POST", "/api/beenden", _mit(server), {}, host=host)[0].status == 403
    assert not server.steuerung.beendet.is_set()


def test_post_regeln(server):
    # ohne Schlüssel, mit fremdem Origin, ohne JSON
    assert _anfrage(server, "POST", "/api/beenden", {}, {})[0].status == 403
    assert _anfrage(server, "POST", "/api/beenden", {**_mit(server), "Origin": "https://evil.example.com"}, {})[0].status == 403
    assert _anfrage(server, "POST", "/api/beenden", {**_mit(server), "Content-Type": "text/plain"}, {})[0].status == 415
    assert not server.steuerung.beendet.is_set()
    # Schreiben per GET geht nicht
    assert _anfrage(server, "GET", "/api/beenden", _mit(server))[0].status == 404
    assert not server.steuerung.beendet.is_set()
    # richtig
    antwort, _ = _anfrage(server, "POST", "/api/beenden", {**_mit(server), "Origin": f"http://127.0.0.1:{server.port}"}, {})
    assert antwort.status == 200 and server.steuerung.beendet.is_set()


def test_kein_cors_und_sicherheitskoepfe(server):
    for methode in ("OPTIONS", "PUT", "DELETE"):
        antwort, _ = _anfrage(server, methode, "/api/zustand",
                              {**_mit(server), "Origin": "https://evil.example.com",
                               "Access-Control-Request-Method": "POST"})
        assert antwort.status == 405
        assert not [k for k, _ in antwort.getheaders() if k.lower().startswith("access-control")]
    antwort, _ = _anfrage(server, "GET", f"/?k={server.schluessel}")
    koepfe = {k.lower(): v for k, v in antwort.getheaders()}
    assert "access-control-allow-origin" not in koepfe
    assert koepfe["cache-control"] == "no-store" and koepfe["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in koepfe["content-security-policy"]
    assert "unsafe-inline" not in koepfe["content-security-policy"]


def test_zu_grosse_anfrage(server):
    antwort, _ = _anfrage(server, "POST", "/api/einstellungen", _mit(server), {"x": "a" * 300_000})
    assert antwort.status == 413


def test_passwort_kommt_nie_zurueck_und_nicht_ins_log(server, umgebung, capfd, tmp_path):
    _speichern(server, tmp_path, mail_an=True)
    antwort, inhalt = _anfrage(server, "POST", "/api/mail-passwort", _mit(server), {"passwort": GEHEIM})
    assert antwort.status == 200 and GEHEIM.encode() not in inhalt
    assert umgebung[("belegabruf", "mail")] == GEHEIM
    for pfad in ("/api/zustand", "/api/auftrag"):
        _, inhalt = _anfrage(server, "GET", pfad, _mit(server))
        assert GEHEIM.encode() not in inhalt
    assert json.loads(_anfrage(server, "GET", "/api/zustand", _mit(server))[1])["mail"]["passwort"] == "hinterlegt"
    # nicht in der Einstellungsdatei, nicht im Log
    assert GEHEIM not in pfade.einstellungsdatei().read_text(encoding="utf-8")
    ausgabe = capfd.readouterr()
    assert GEHEIM not in ausgabe.out + ausgabe.err and server.schluessel not in ausgabe.out + ausgabe.err


def test_fehler_nennen_keine_einzelheiten(server, monkeypatch):
    def kaputt():
        raise RuntimeError(f"/geheimer/pfad {GEHEIM}")

    monkeypatch.setattr(server.steuerung, "mail_pruefen", kaputt)
    antwort, inhalt = _anfrage(server, "POST", "/api/mail-pruefen", _mit(server), {})
    assert antwort.status == 500 and GEHEIM.encode() not in inhalt and b"geheimer" not in inhalt


# ── Eingaben prüfen ──────────────────────────────────────────────────────────


def _eingaben(tmp_path, **mehr):
    daten = {"belegordner": str(tmp_path / "Belege"), "konten": [{"quelle": "airbnb", "name": "privat", "aktiv": True}],
             "mail_an": False, "mail": {}}
    daten.update(mehr)
    return daten


def _speichern(s, tmp_path, mail_an=False):
    daten = _eingaben(tmp_path, mail_an=mail_an, mail={
        "server": "smtp.example.com", "port": 465, "verschluesselung": "ssl", "benutzer": "ich@example.com",
        "absender": "ich@example.com", "empfaenger": ["belege@example.com"]})
    antwort, inhalt = _anfrage(s, "POST", "/api/einstellungen", _mit(s), daten)
    assert antwort.status == 200, inhalt
    return json.loads(inhalt)


@pytest.mark.parametrize("aenderung, meldung", [
    ({"belegordner": "relativer/pfad"}, "vollständigen Pfad"),
    ({"belegordner": "/tmp/x\u0000y"}, "ungültig"),
    ({"konten": [{"quelle": "gibtsnicht", "name": "a"}]}, "gibt es nicht"),
    ({"konten": [{"quelle": "airbnb", "name": "a\nb"}]}, "ungültig"),
    ({"konten": [{"quelle": "airbnb", "name": "a"}, {"quelle": "airbnb", "name": "A"}]}, "schon"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com", "port": 70000}}, "Port"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com; rm -rf /", "port": 465}}, "Postausgangsserver"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com", "verschluesselung": "keine"}}, "Verschlüsselung"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com", "port": 465, "benutzer": "a", "absender": "a@example.com",
                                "empfaenger": ["keine-adresse"]}}, "keine Mailadresse"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com"}}, "fehlt"),
])
def test_eingaben_werden_geprueft(server, tmp_path, aenderung, meldung):
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, **aenderung))
    assert antwort.status == 400
    assert meldung in json.loads(inhalt)["fehler"]
    assert not pfade.einstellungsdatei().exists()


def test_einstellungen_speichern_und_laden(server, tmp_path):
    z = _speichern(server, tmp_path, mail_an=True)
    assert z["eingerichtet"] and z["mail_an"] and z["konten"][0]["name"] == "privat"
    einst = einstellungen.laden()
    assert einst.mail.empfaenger == ["belege@example.com"] and (tmp_path / "Belege").is_dir()


def test_keine_shell_im_code():
    ordner = Path(aktionen.__file__).parent
    text = "".join(p.read_text(encoding="utf-8") for p in ordner.glob("*.py"))
    for verboten in ("subprocess", "os.system", "shell=True", "os.popen", "eval(", "exec("):
        assert verboten not in text, verboten


# ── Abläufe im Browser (headless) mit Attrappen-Quelle ───────────────────────


class Attrappe(Quelle):
    name = "airbnb"
    anzeigename = "Airbnb"
    angemeldet = True
    anmeldungen = 0

    def sitzung_pruefen(self):
        return Attrappe.angemeldet

    def anmelden_lassen(self, melden):
        Attrappe.anmeldungen += 1
        melden("Fenster wäre jetzt offen.")
        Attrappe.angemeldet = True
        return True

    def belege_holen(self, umgebung):
        erg = Ergebnis(self.name, self.konto.name)
        for kennung, datum in (("a1", "2026-11-03"), ("a2", "2026-11-04")):
            schluessel = f"rechnung:{kennung}"
            if umgebung.bekannt(schluessel):
                erg.schon_da += 1
                continue
            umgebung.melden(f"hole {kennung}")
            umgebung.abliefern(Beleg(quelle="airbnb", konto=self.konto.name, art="rechnung", schluessel=schluessel,
                                     dateiname=f"{datum}_{kennung}.pdf", inhalt=b"%PDF-1.4 test", jahr=2026,
                                     rechnungsdatum=date.fromisoformat(datum), rechnungsnummer=kennung.upper()))
            erg.neu += 1
        erg.erwartet = 2
        erg.vorhanden = 2
        return erg


def _chromium_da() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(channel="chromium", headless=True).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def seite(server, monkeypatch):
    if not _chromium_da():
        pytest.skip("Chromium nicht installiert")
    Attrappe.angemeldet, Attrappe.anmeldungen = True, 0
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Attrappe(konto, Path("/gibt-es-nicht")))
    monkeypatch.setattr(ablauf.zustand, "lauf_merken", lambda *a: None)
    monkeypatch.setattr(browser, "ENTER_IM_TERMINAL", False)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chromium", headless=True)
        p = b.new_page()
        fehler = []
        p.on("pageerror", lambda e: fehler.append(str(e)))
        p.goto(server.adresse)
        p.wait_for_selector("#version:not(:empty)")
        yield p
        assert fehler == []
        b.close()


def test_ablauf_einrichten_pruefen_anmelden_holen(seite, server, tmp_path):
    p = seite
    assert p.is_visible("#willkommen") and p.eval_on_selector("#einstellungen", "e => e.open")

    # Einrichten
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.fill("#kontenliste input[type=text]", "privat")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert p.is_hidden("#willkommen")
    assert p.inner_text("#konten").count("privat") == 1
    assert "unbekannt" in p.inner_text("#konten")

    # Prüfen: abgelaufen
    Attrappe.angemeldet = False
    p.click("#konten button:has-text('Prüfen')")
    p.wait_for_function("() => document.querySelector('#konten').innerText.includes('abgelaufen')")

    # Holen, solange nicht angemeldet: Hinweis, nichts geholt
    p.click("#holen")
    p.wait_for_selector("#zusammenfassung li")
    assert "nicht angemeldet" in p.inner_text("#protokoll")
    assert "nicht angemeldet" in p.inner_text("#zusammenfassung")

    # Anmelden
    p.click("#konten button:has-text('Anmelden')")
    p.wait_for_function("() => document.querySelector('#konten').innerText.includes('angemeldet')"
                        " && !document.querySelector('#konten').innerText.includes('abgelaufen')")
    assert Attrappe.anmeldungen == 1

    # Holen mit Fortschritt und Zusammenfassung wie im CLI
    p.click("#holen")
    p.wait_for_function("() => document.querySelector('#zusammenfassung').innerText.includes('2 neu')")
    assert "hole a1" in p.inner_text("#protokoll")
    zusammenfassung = p.inner_text("#zusammenfassung")
    assert "Airbnb (privat): fertig" in zusammenfassung and "✓ passt" in zusammenfassung
    assert (tmp_path / "Belege" / "airbnb" / "2026" / "2026-11-03_a1.pdf").exists()

    # Neu laden geht (Schlüssel bleibt in der Adresse des App-Fensters)
    p.reload()
    p.wait_for_function("() => document.querySelector('#konten').innerText.includes('privat')")


def test_fehlende_dateien_und_beenden(seite, server, tmp_path):
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.fill("#kontenliste input[type=text]", "privat")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    p.click("#holen")
    p.wait_for_function("() => document.querySelector('#zusammenfassung').innerText.includes('2 neu')")
    (tmp_path / "Belege" / "airbnb" / "2026" / "2026-11-03_a1.pdf").unlink()
    p.click("#holen")  # danach steht die Zahl der fehlenden Dateien am Knopf
    p.wait_for_function("() => document.querySelector('#fehlende').innerText.includes('(1)')")
    p.click("#fehlende")
    p.wait_for_function("() => document.querySelector('#zusammenfassung').innerText.includes('1 neu')")
    assert (tmp_path / "Belege" / "airbnb" / "2026" / "2026-11-03_a1.pdf").exists()

    p.click("#beenden")
    p.wait_for_selector("#ende:not(.versteckt)")
    assert server.steuerung.beendet.is_set()


def test_mail_passwort_und_pruefen_in_der_seite(seite, server, tmp_path, umgebung, monkeypatch):
    geprueft = []
    monkeypatch.setattr(mail, "anmeldung_pruefen", lambda einst, pw: geprueft.append(pw == GEHEIM) or None)
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.fill("#kontenliste input[type=text]", "privat")
    p.check("#mail-an")
    p.fill("#server", "smtp.example.com")
    p.select_option("#verschluesselung", "starttls")
    p.fill("#port", "587")
    p.fill("#benutzer", "ich@example.com")
    p.fill("#absender", "ich@example.com")
    p.fill("#empfaenger", "belege@example.com, steuer@example.com")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert p.inner_text("#passwort-status") == "fehlt"
    p.fill("#passwort", GEHEIM)
    p.click("#passwort-speichern")
    p.wait_for_function("() => document.querySelector('#passwort-status').innerText === 'hinterlegt'")
    assert p.input_value("#passwort") == ""  # Feld wird geleert
    assert GEHEIM not in p.content()
    p.click("#mail-pruefen")
    p.wait_for_selector("#mail-ergebnis.gut")
    assert geprueft == [True]
    assert einstellungen.laden().mail.empfaenger == ["belege@example.com", "steuer@example.com"]


def test_fehler_wird_angezeigt(seite, tmp_path):
    p = seite
    p.fill("#belegordner", "relativ")
    p.click("#speichern")
    p.wait_for_selector("#fehler:not(.versteckt)")
    assert "vollständigen Pfad" in p.inner_text("#fehler")
