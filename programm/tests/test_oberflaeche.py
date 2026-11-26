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
from belegabruf.einstellungen import Konto
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
    import threading

    monkeypatch.setattr(browser, "ABBRECHEN", threading.Event())  # starten() setzt es beim Ende
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
    ({"konten": [{"quelle": "airbnb", "name": "a"}, {"quelle": "airbnb", "name": "A"}]}, "dasselbe"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com", "port": 70000}}, "Port"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com; rm -rf /", "port": 465}}, "Postausgangsserver"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com", "verschluesselung": "keine"}}, "Verschlüsselung"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com", "port": 465, "benutzer": "a", "absender": "a@example.com",
                                "empfaenger": ["keine-adresse"]}}, "keine Mailadresse"),
    ({"mail_an": True, "mail": {"server": "smtp.example.com"}}, "ausfüllen"),
])
def test_eingaben_werden_geprueft(server, tmp_path, aenderung, meldung):
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, **aenderung))
    assert antwort.status == 400
    antwort = json.loads(inhalt)
    assert meldung in antwort["fehler"] or any(meldung in s for s in antwort.get("felder", {}).values())
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
    # Erster Start ohne Konten: Reiter „Einstellungen“ ist offen
    assert p.is_visible("#willkommen") and p.get_attribute("#reiter-einstellungen", "aria-selected") == "true"

    # Einrichten
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    p.click("#reiter-holen")
    assert p.is_hidden("#willkommen")
    # Ein einzelnes Konto braucht keinen Namen: Anzeige nur „Airbnb“.
    assert p.is_hidden("#kontenliste input.kontoname")
    assert p.inner_text("#konten").count("Airbnb") == 1
    assert "noch nie angemeldet" in p.inner_text("#konten")
    assert p.locator("#konten button").count() == 0  # im Reiter „Belege holen“ nur der Status
    assert "noch nicht angemeldet" in p.inner_text("#anmelde-hinweise")

    # Prüfen: weiter nicht angemeldet, mit Zeitpunkt der Prüfung
    Attrappe.angemeldet = False
    p.click("#alle-pruefen")
    p.wait_for_function("() => document.querySelector('#konten').innerText.includes('geprüft heute')")
    assert "noch nie angemeldet" in p.inner_text("#konten")

    # Holen, solange nicht angemeldet: Hinweis, nichts geholt
    p.click("#holen")
    p.wait_for_selector("#zusammenfassung li")
    assert "nicht angemeldet" in p.inner_text("#protokoll")
    assert "nicht angemeldet" in p.inner_text("#zusammenfassung")

    # Anmelden: Sprung aus dem Hinweis in die Einstellungen, Konto hervorgehoben
    p.click("#anmelde-hinweise button")
    assert p.get_attribute("#reiter-einstellungen", "aria-selected") == "true"
    assert p.locator("#kontenliste .kontozeile.hervorgehoben").count() == 1
    assert p.evaluate("document.activeElement.textContent") == "Anmelden"
    p.click("#kontenliste button:has-text('Anmelden')")
    p.wait_for_function("() => document.querySelector('#kontenliste .marke.angemeldet')")
    assert Attrappe.anmeldungen == 1
    p.click("#reiter-holen")
    assert "angemeldet" in p.inner_text("#konten") and p.inner_text("#anmelde-hinweise") == ""

    # Später abgelaufen: nach dem Prüfen sofort „abgelaufen“ und Hinweis
    Attrappe.angemeldet = False
    p.click("#alle-pruefen")
    p.wait_for_function("() => document.querySelector('#konten').innerText.includes('abgelaufen')")
    assert "Anmeldung bei Airbnb abgelaufen" in p.inner_text("#anmelde-hinweise")
    Attrappe.angemeldet = True
    p.click("#alle-pruefen")
    p.wait_for_function("() => document.querySelector('#konten .marke.angemeldet')")

    # Holen mit Fortschritt und Zusammenfassung wie im CLI
    p.click("#holen")
    p.wait_for_function("() => document.querySelector('#zusammenfassung').innerText.includes('2 neu')")
    assert "hole a1" in p.inner_text("#protokoll")
    zusammenfassung = p.inner_text("#zusammenfassung")
    assert "Airbnb: fertig" in zusammenfassung and "✓ passt" in zusammenfassung
    assert (tmp_path / "Belege" / "airbnb" / "2026" / "2026-11-03_a1.pdf").exists()

    # Neu laden geht (Schlüssel bleibt in der Adresse des App-Fensters)
    p.reload()
    p.wait_for_function("() => document.querySelector('#konten').innerText.includes('Airbnb')")


def test_fehlende_dateien_und_beenden(seite, server, tmp_path):
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    p.click("#reiter-holen")
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
    p.wait_for_selector("#speichern-meldung:not(.versteckt)")
    assert "vollständigen Pfad" in p.inner_text("#satz-belegordner")
    # Fehler ohne Feldbezug (hier: ein Vorgang läuft) stehen ebenfalls am Knopf
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.evaluate("""() => { window.fetch = async () => new Response(JSON.stringify({fehler: "Bitte warten."}),
                                                                   {status: 400}); }""")
    p.click("#speichern")
    p.wait_for_function("() => document.querySelector('#speichern-meldung').innerText === 'Bitte warten.'")


# ── Gleichzeitigkeit, Beenden, eigene Inhalte der Einstellungsdatei ──────────


class LangsameAttrappe(Attrappe):
    """Holt so lange, bis der Test das Tor öffnet."""

    import threading as _t
    tor = _t.Event()

    def belege_holen(self, umgebung):
        LangsameAttrappe.tor.wait(10)
        return super().belege_holen(umgebung)


def test_nur_ein_vorgang_zur_zeit_auch_serverseitig(server, tmp_path, monkeypatch):
    import time

    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: LangsameAttrappe(konto, Path("/x")))
    monkeypatch.setattr(ablauf.zustand, "lauf_merken", lambda *a: None)
    LangsameAttrappe.tor.clear()
    _speichern(server, tmp_path)
    assert _anfrage(server, "POST", "/api/holen", _mit(server), {})[0].status == 200
    time.sleep(0.3)
    # Während des Abrufs: kein zweites Holen, kein Anmelden, kein Prüfen, kein Speichern
    for pfad, rumpf in (("/api/holen", {}), ("/api/anmelden", {"quelle": "airbnb", "name": "privat"}),
                        ("/api/pruefen", {}), ("/api/einstellungen", _eingaben(tmp_path))):
        antwort, inhalt = _anfrage(server, "POST", pfad, _mit(server), rumpf)
        assert antwort.status == 400, pfad
        assert "warten" in json.loads(inhalt)["fehler"]
    zustand = json.loads(_anfrage(server, "GET", "/api/zustand", _mit(server))[1])
    assert zustand["beschaeftigt"] and zustand["auftrag_art"] == "holen"
    LangsameAttrappe.tor.set()
    for _ in range(50):
        if not server.steuerung.beschaeftigt():
            break
        time.sleep(0.1)
    assert _anfrage(server, "POST", "/api/anmelden", _mit(server), {"quelle": "airbnb", "name": "privat"})[0].status == 200


def test_knoepfe_in_der_seite_gesperrt(seite, server, tmp_path, monkeypatch):
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: LangsameAttrappe(konto, Path("/x")))
    LangsameAttrappe.tor.clear()
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    p.click("#reiter-holen")
    p.click("#holen")
    p.wait_for_function("() => document.querySelector('#holen').disabled")
    for knopf in ("#alle-pruefen", "#speichern", "#kontenliste button:has-text('Anmelden')"):
        assert p.is_disabled(knopf), knopf
    # Reiter wechseln geht während des Vorgangs; in den Einstellungen ist nur Speichern gesperrt
    p.click("#reiter-einstellungen")
    assert p.is_visible("#formular") and p.is_disabled("#speichern")
    assert p.is_enabled("#belegordner") and p.is_enabled("#passwort-speichern")
    p.click("#reiter-holen")
    LangsameAttrappe.tor.set()
    p.wait_for_function("() => !document.querySelector('#holen').disabled")
    assert p.is_enabled("#kontenliste button:has-text('Anmelden')")


def _starten_mit(monkeypatch, fenster):
    from belegabruf import oberflaeche

    erzeugt = []
    alt = oberflaeche.Bedienserver

    class Merker(alt):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            erzeugt.append(self)

    monkeypatch.setattr(oberflaeche, "Bedienserver", Merker)
    monkeypatch.setattr(oberflaeche, "_fenster_offen_halten", fenster)
    code = oberflaeche.starten()
    return code, erzeugt[0]


def _laeuft_noch(s) -> bool:
    try:
        _anfrage(s, "GET", "/api/zustand", _mit(s))
        return True
    except OSError:
        return False


def test_fenster_zu_waehrend_abruf_wartet_und_beendet_sauber(monkeypatch, tmp_path, capsys):
    import threading
    import time

    fertig = threading.Event()

    def fenster(server):
        # Ein Vorgang läuft, dann schließt der Nutzer das Fenster.
        def arbeit(a):
            time.sleep(1.0)
            fertig.set()
        server.steuerung.starten("holen", arbeit)

    code, server = _starten_mit(monkeypatch, fenster)
    assert fertig.is_set()  # nicht mittendrin abgebrochen
    assert code == 0 and not _laeuft_noch(server)  # kein verwaister Server
    ausgabe = capsys.readouterr().out
    assert "Warte, bis der laufende Vorgang fertig ist" in ausgabe and "beendet" in ausgabe
    assert "Doppelklick auf \"Belegabruf Mac\"" in ausgabe  # sagt, wie man es wieder öffnet


def test_abgestuerztes_fenster_beendet_sauber(monkeypatch, capsys):
    def fenster(server):
        raise RuntimeError("Target page, context or browser has been closed")

    code, server = _starten_mit(monkeypatch, fenster)
    assert code == 1 and not _laeuft_noch(server)
    assert "Doppelklick auf \"Belegabruf Mac\"" in capsys.readouterr().out


def test_eigene_inhalte_warnung_und_sicherung(server, tmp_path):
    datei = pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(
        f'# Meine Notiz: Konto privat ist das alte\nbelegordner = "{tmp_path / "Belege"}"\n'
        'ziele = ["ordner"]\nlieblingsfarbe = "blau"\n\n[[konto]]\nquelle = "airbnb"\nname = "privat"\n'
        'aktiv = "ja"\nadresse = "https://www.airbnb.de"\n', encoding="utf-8")
    zustand = json.loads(_anfrage(server, "GET", "/api/zustand", _mit(server))[1])
    assert "Eintrag „lieblingsfarbe“" in zustand["datei_fremd"] and "eigene Kommentare" in zustand["datei_fremd"]
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path))
    assert antwort.status == 200 and json.loads(inhalt)["gesichert"] == "einstellungen.toml.vorher"
    vorher = datei.with_name("einstellungen.toml.vorher").read_text(encoding="utf-8")
    assert "Meine Notiz" in vorher and "lieblingsfarbe" in vorher
    neu = datei.read_text(encoding="utf-8")
    assert 'adresse = "https://www.airbnb.de"' in neu  # Zusatzangaben im Konto bleiben
    # Danach ist nichts Fremdes mehr da → keine Warnung, keine weitere Sicherung
    assert json.loads(_anfrage(server, "GET", "/api/zustand", _mit(server))[1])["datei_fremd"] == []
    _, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path))
    assert json.loads(inhalt)["gesichert"] == ""


def test_eigene_datei_ohne_fremdes_keine_warnung(server, tmp_path):
    _speichern(server, tmp_path)
    assert json.loads(_anfrage(server, "GET", "/api/zustand", _mit(server))[1])["datei_fremd"] == []


def test_warnung_steht_vor_dem_speichern_in_der_seite(server, tmp_path, monkeypatch):
    if not _chromium_da():
        pytest.skip("Chromium nicht installiert")
    datei = pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(f'# eigene Notiz\nbelegordner = "{tmp_path / "Belege"}"\n', encoding="utf-8")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chromium")
        p = b.new_page()
        p.goto(server.adresse)
        p.wait_for_selector("#version:not(:empty)")
        p.click("#reiter-einstellungen")
        assert "eigene Kommentare" in p.inner_text("#fremd-hinweis")
        p.click("#speichern")
        p.wait_for_selector("#gespeichert:not(.versteckt)")
        assert "einstellungen.toml.vorher" in p.inner_text("#gespeichert")
        b.close()


# ── Prüfbefunde 2.0.0 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("namen", [("Privat", "privat!"), ("Co Host", "co-host"), ("Müller", "Mueller")])
def test_aehnliche_kontonamen_abgelehnt_formular(server, tmp_path, namen):
    konten = [{"quelle": "airbnb", "name": n} for n in namen]
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=konten))
    assert antwort.status == 400 and "dasselbe" in json.loads(inhalt)["fehler"]


def test_gleicher_name_bei_verschiedenen_quellen_erlaubt(server, tmp_path):
    konten = [{"quelle": "airbnb", "name": "privat"}, {"quelle": "skool", "name": "Privat"}]
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=konten))[0].status == 200


def test_aehnliche_kontonamen_in_der_datei(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('[[konto]]\nquelle = "airbnb"\nname = "Privat"\n\n[[konto]]\nquelle = "airbnb"\nname = "privat!"\n',
                     encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler, match="Ordnernamen „privat“"):
        einstellungen.laden(datei)


def test_aehnliche_kontonamen_im_terminal_einrichten(monkeypatch, capsys):
    import builtins

    from belegabruf import einrichtung

    eingaben = iter(["Privat", "j", "privat!", "Geschäft", "n"])
    monkeypatch.setattr(builtins, "input", lambda text="": next(eingaben))
    konten = einrichtung._konten_abfragen("airbnb", [])
    assert [k.name for k in konten] == ["Privat", "Geschäft"]
    assert "dasselbe" in capsys.readouterr().out


@pytest.mark.parametrize("port", [0, True, "abc", "4.5", -1, 70000, [465]])
def test_ungueltige_ports_abgelehnt_statt_umgedeutet(server, tmp_path, port):
    daten = _eingaben(tmp_path, mail_an=False, mail={"server": "smtp.example.com", "port": port})
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), daten)
    assert antwort.status == 400 and "Port" in json.loads(inhalt)["fehler"]


def test_leerer_port_ist_vorgabe(server, tmp_path):
    daten = _eingaben(tmp_path, mail={"server": "", "port": ""})
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), daten)[0].status == 200
    assert einstellungen.laden().mail.port == 465


def test_einstellungen_atomar_geschrieben(tmp_path, monkeypatch):
    import os

    datei = tmp_path / "e.toml"
    einst = einstellungen.Einstellungen(belegordner=tmp_path / "B", konten=[])
    einstellungen.speichern(einst, datei)
    vorher = datei.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.teil"))

    def kaputt(quelle, ziel):
        raise OSError("Platte voll")

    monkeypatch.setattr(os, "replace", kaputt)
    einst.belegordner = tmp_path / "Anders"
    with pytest.raises(OSError):
        einstellungen.speichern(einst, datei)
    assert datei.read_text(encoding="utf-8") == vorher  # die alte Datei ist unversehrt


def test_schluessel_nicht_in_der_kommandozeile(monkeypatch):
    from belegabruf import oberflaeche

    gestartet = {}

    class FalscheSeite:
        url = "data:text/html,"

        def __init__(self):
            self.zu = False

        def goto(self, adresse):
            gestartet["goto"] = adresse

        def is_closed(self):
            return self.zu

        def wait_for_timeout(self, ms):
            self.zu = True

    class FalscherKontext:
        def __init__(self, **kw):
            gestartet.update(kw)
            self.pages = [FalscheSeite()]

        def close(self):
            pass

    class FalscherChromium:
        def launch_persistent_context(self, **kw):
            return FalscherKontext(**kw)

    class FalschesPW:
        chromium = FalscherChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: FalschesPW())
    s = Bedienserver()
    try:
        oberflaeche._fenster_offen_halten(s)
    finally:
        s.server_close()
    assert not any(s.schluessel in str(a) for a in gestartet["args"])
    assert gestartet["goto"] == s.adresse


# ── Anmerkungen aus dem Test 2.0.0: Kontoname optional ───────────────────────


def _toml(tmp_path, text):
    datei = tmp_path / "e.toml"
    datei.write_text(f'belegordner = "{tmp_path / "Belege"}"\n' + text, encoding="utf-8")
    return datei


def test_bisheriges_konto_mit_namen_behaelt_pfade(tmp_path):
    from belegabruf.protokoll import Protokoll

    einst = einstellungen.laden(_toml(tmp_path, '[[konto]]\nquelle = "airbnb"\nname = "Co-Host"\n'))
    k = einst.konten[0]
    assert k.name == "Co-Host" and k.anzeigetitel == "Co-Host" and k.anzeige == "Airbnb (Co-Host)"
    assert ablauf.quelle_fuer(k).profil == pfade.datenordner() / "profile" / "airbnb-co-host"
    assert Protokoll(k.quelle, k.name, einst.belegordner).datei == \
        pfade.datenordner() / "protokolle" / "airbnb" / "co-host.csv"
    text = einstellungen.als_text(einst)
    assert 'name = "Co-Host"' in text and "kennung" not in text.replace("# kennung", "")


def test_konto_ohne_namen(tmp_path):
    einst = einstellungen.laden(_toml(tmp_path, '[[konto]]\nquelle = "airbnb"\n'))
    k = einst.konten[0]
    assert k.name == "standard" and k.anzeigetitel == "" and k.anzeige == "Airbnb"
    assert ablauf.quelle_fuer(k).profil.name == "airbnb-standard"
    wieder = einstellungen.aus_text(einstellungen.als_text(einst))
    assert (wieder.konten[0].name, wieder.konten[0].anzeigetitel) == ("standard", "")
    assert "Airbnb: fertig" in ablauf.zusammenfassung(
        [Ergebnis("airbnb", "standard", anzeige=k.anzeige)], einst.belegordner)


def test_mehrere_konten_brauchen_namen(tmp_path):
    with pytest.raises(einstellungen.EinstellungsFehler, match="braucht jedes einen Namen"):
        einstellungen.laden(_toml(tmp_path, '[[konto]]\nquelle = "airbnb"\n\n[[konto]]\nquelle = "airbnb"\nname = "Co"\n'))
    # bei verschiedenen Anbietern je eines ohne Namen: erlaubt
    einst = einstellungen.laden(_toml(tmp_path, '[[konto]]\nquelle = "airbnb"\n\n[[konto]]\nquelle = "skool"\n'))
    assert [k.anzeige for k in einst.konten] == ["Airbnb", "Skool"]


def test_formular_ohne_namen_und_umbenennen_behaelt_kennung(server, tmp_path):
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server),
                               _eingaben(tmp_path, konten=[{"quelle": "airbnb", "name": ""}]))
    assert antwort.status == 200
    konto = json.loads(inhalt)["konten"][0]
    assert (konto["name"], konto["titel"], konto["bezeichnung"]) == ("standard", "", "Airbnb")

    # zweites Konto dazu: ohne Namen geht es nicht mehr
    zwei = [{"quelle": "airbnb", "name": "", "kennung": "standard"}, {"quelle": "airbnb", "name": "Co"}]
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=zwei))
    assert antwort.status == 400 and "braucht jedes einen Namen" in json.loads(inhalt)["fehler"]

    # das erste bekommt einen Namen: Kennung (Anmeldung, Protokoll) bleibt „standard“
    zwei[0]["name"] = "Privat"
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=zwei))
    assert antwort.status == 200
    konten = {k["titel"]: k["name"] for k in json.loads(inhalt)["konten"]}
    assert konten == {"Privat": "standard", "Co": "Co"}
    assert 'kennung = "standard"' in pfade.einstellungsdatei().read_text(encoding="utf-8")
    einst = einstellungen.laden()
    assert ablauf.quelle_fuer(einst.konten[0]).profil.name == "airbnb-standard"

    # umbenennen eines benannten Kontos behält dessen Kennung auch
    zwei = [{"quelle": "airbnb", "name": "Privat", "kennung": "standard"},
            {"quelle": "airbnb", "name": "Co-Gastgeber", "kennung": "Co"}]
    _, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=zwei))
    assert {k["titel"]: k["name"] for k in json.loads(inhalt)["konten"]} == {"Privat": "standard", "Co-Gastgeber": "Co"}


def test_formular_fremde_kennung_wird_nicht_uebernommen(server, tmp_path):
    konten = [{"quelle": "airbnb", "name": "", "kennung": "../../irgendwas"}]
    _, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=konten))
    assert json.loads(inhalt)["konten"][0]["name"] == "standard"


def test_terminal_einrichten_ohne_namen_und_zweites_konto(monkeypatch):
    import builtins

    from belegabruf import einrichtung

    eingaben = iter([""])
    monkeypatch.setattr(builtins, "input", lambda text="": next(eingaben, "n"))
    konten = einrichtung._konten_abfragen("airbnb", [])
    assert [(k.name, k.anzeigetitel) for k in konten] == [("standard", "")]

    eingaben = iter(["", "j", "Privat", "Co", "n"])
    konten = einrichtung._konten_abfragen("airbnb", [])
    assert [(k.name, k.anzeigetitel) for k in konten] == [("standard", "Privat"), ("Co", "Co")]


def test_namensfeld_erscheint_erst_beim_zweiten_konto(seite, tmp_path):
    p = seite
    assert p.is_hidden("#kontenliste input.kontoname")
    p.click("#konto-dazu")
    felder = p.locator("#kontenliste input.kontoname")
    assert felder.nth(0).is_visible() and felder.nth(1).is_visible()
    assert felder.nth(0).evaluate("e => e.required")
    p.locator("#kontenliste button:has-text('Entfernen')").nth(1).click()
    assert p.is_hidden("#kontenliste input.kontoname")


def test_haken_je_konto_im_reiter_belege_holen(server, tmp_path, monkeypatch):
    """Nachtrag A: Haken in der Kontenliste, ein Klick speichert; ohne Haken kein Holen;
    „Alle Anmeldungen prüfen“ prüft trotzdem alle."""
    konten = [{"quelle": "airbnb", "name": "Privat"}, {"quelle": "airbnb", "name": "Co"}]
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=konten))[0].status == 200
    geprueft = []
    monkeypatch.setattr(ablauf, "sitzung_pruefen", lambda k: geprueft.append(k.name) or "angemeldet")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chromium")
        p = b.new_page()
        p.goto(server.adresse)
        p.wait_for_selector("#version:not(:empty)")
        haken = p.locator("#konten input.holen-haken")
        assert haken.count() == 2 and haken.nth(0).get_attribute("aria-label") == "Airbnb (Privat): Belege holen"
        assert p.locator("#kontenliste input[type=checkbox]").count() == 0  # in den Einstellungen entfällt er
        haken.nth(1).uncheck()
        p.wait_for_function("() => document.querySelector('#konten tr:nth-child(2)').classList.contains('aus')")
        assert [k.aktiv for k in einstellungen.laden().konten] == [True, False]  # sofort gespeichert
        assert p.is_enabled("#holen")
        haken.nth(0).uncheck()
        p.wait_for_selector("#kein-haken:not(.versteckt)")
        assert p.is_disabled("#holen")
        assert [k.aktiv for k in einstellungen.laden().konten] == [False, False]
        # Auswahl wird gemerkt
        p.reload()
        p.wait_for_selector("#version:not(:empty)")
        assert p.is_disabled("#holen") and not p.locator("#konten input.holen-haken").nth(0).is_checked()
        # Prüfen: alle Konten, unabhängig vom Haken
        p.click("#alle-pruefen")
        p.wait_for_function("() => document.querySelectorAll('#konten .marke.angemeldet').length === 2")
        assert sorted(geprueft) == ["Co", "Privat"]
        # Einstellungen speichern ändert den Haken nicht zurück
        p.click("#reiter-einstellungen")
        p.click("#speichern")
        p.wait_for_selector("#gespeichert:not(.versteckt)")
        assert [k.aktiv for k in einstellungen.laden().konten] == [False, False]
        b.close()
    antwort, inhalt = _anfrage(server, "POST", "/api/holen", _mit(server), {})
    assert antwort.status == 400 and "angehakt" in json.loads(inhalt)["fehler"]


def test_haken_setzen_gesperrt_waehrend_vorgang_und_prueft_eingaben(server, tmp_path):
    _speichern(server, tmp_path)
    for rumpf in ({"quelle": "airbnb", "name": "privat", "aktiv": "nein"}, {"quelle": "airbnb", "name": "x", "aktiv": False}):
        assert _anfrage(server, "POST", "/api/konto-holen", _mit(server), rumpf)[0].status == 400
    assert _anfrage(server, "POST", "/api/konto-holen", {}, {"quelle": "airbnb", "name": "privat", "aktiv": False})[0].status == 403
    import threading

    tor = threading.Event()
    server.steuerung.starten("holen", lambda a: tor.wait(10))
    try:
        antwort, inhalt = _anfrage(server, "POST", "/api/konto-holen", _mit(server),
                                   {"quelle": "airbnb", "name": "privat", "aktiv": False})
        assert antwort.status == 400 and "warten" in json.loads(inhalt)["fehler"]
    finally:
        tor.set()
    assert einstellungen.laden().konten[0].aktiv is True


def test_einrichtung_laedt_keine_headless_shell():
    """Headless läuft über channel="chromium" mit dem normalen Chromium — die eigene
    Headless Shell wird nicht gebraucht und nicht geladen (spart Platz und Zeit)."""
    import re

    wurzel = Path(__file__).resolve().parents[2]
    for datei in (wurzel / "Belegabruf Mac.command", wurzel / "Belegabruf Windows.cmd"):
        text = datei.read_text(encoding="utf-8")
        assert "playwright install --no-shell chromium" in text, datei
    gefunden = 0
    for datei in (wurzel / "programm" / "belegabruf").rglob("*.py"):
        text = datei.read_text(encoding="utf-8")
        for aufruf in re.finditer(r"\.(launch|launch_persistent_context)\((.*?)\)\n", text, re.S):
            gefunden += 1
            assert 'channel="chromium"' in aufruf.group(2), f"{datei.name}: Start ohne channel=chromium"
    assert gefunden >= 3


# ── Rückmeldung beim Speichern: Feldbezug ────────────────────────────────────


def test_fehlerantwort_nennt_alle_fehlenden_mailfelder(server, tmp_path):
    daten = _eingaben(tmp_path, mail_an=True, mail={"server": "", "port": "", "benutzer": "", "absender": "",
                                                    "empfaenger": []})
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), daten)
    assert antwort.status == 400
    felder = json.loads(inhalt)["felder"]
    assert set(felder) == {"server", "port", "benutzer", "absender", "empfaenger"}
    assert not pfade.einstellungsdatei().exists()


def test_fehlerantwort_nennt_kontozeile_und_belegordner(server, tmp_path):
    daten = _eingaben(tmp_path, belegordner="", konten=[{"quelle": "airbnb", "name": ""},
                                                        {"quelle": "airbnb", "name": "Co"},
                                                        {"quelle": "skool", "name": ""}])
    felder = json.loads(_anfrage(server, "POST", "/api/einstellungen", _mit(server), daten)[1])["felder"]
    assert set(felder) == {"belegordner", "konto-0-name"}


def test_mail_aus_braucht_keine_mailfelder(server, tmp_path):
    daten = _eingaben(tmp_path, mail_an=False, mail={"server": "", "port": "", "benutzer": ""})
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), daten)[0].status == 200


def test_speichern_markiert_fehlende_mailfelder_in_der_seite(seite, tmp_path):
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.check("#mail-an")
    p.fill("#port", "")
    p.click("#speichern")
    p.wait_for_selector("#speichern-meldung:not(.versteckt)")
    assert p.inner_text("#speichern-meldung") == "Bitte die markierten Felder ausfüllen."
    markiert = p.eval_on_selector_all("#formular .feld-fehler", "es => es.map(e => e.id)")
    assert set(markiert) == {"server", "port", "benutzer", "absender", "empfaenger"}
    assert p.get_attribute("#server", "aria-invalid") == "true"
    assert "ausfüllen" in p.inner_text("#satz-server")
    assert p.is_hidden("#fehler")  # nicht (nur) oben, sondern am Knopf
    # Ausfüllen nimmt die Markierung weg
    p.fill("#server", "smtp.example.com")
    assert not p.eval_on_selector("#server", "e => e.classList.contains('feld-fehler')")
    assert p.query_selector("#satz-server") is None
    assert p.is_visible("#speichern-meldung")  # andere Felder sind noch rot
    for feld, wert in (("#port", "465"), ("#benutzer", "ich@example.com"), ("#absender", "ich@example.com"),
                       ("#empfaenger", "belege@example.com")):
        p.fill(feld, wert)
    assert p.is_hidden("#speichern-meldung")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert pfade.einstellungsdatei().exists()


def test_speichern_markiert_fehlenden_kontonamen(seite, tmp_path):
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.click("#konto-dazu")
    p.locator("#kontenliste input.kontoname").nth(1).fill("Co")
    p.click("#speichern")
    p.wait_for_selector("#speichern-meldung:not(.versteckt)")
    erstes = p.locator("#kontenliste input.kontoname").nth(0)
    assert erstes.evaluate("e => e.classList.contains('feld-fehler')")
    assert "braucht jedes einen Namen" in p.inner_text("#formular .feldsatz")
    assert not pfade.einstellungsdatei().exists()


def test_absender_wird_aus_benutzername_vorbelegt(seite):
    p = seite
    p.check("#mail-an")
    p.locator("#benutzer").press_sequentially("ich")
    assert p.input_value("#absender") == ""  # ohne @ nichts
    p.locator("#benutzer").press_sequentially("@example.com")
    assert p.input_value("#absender") == "ich@example.com"
    assert p.input_value("#empfaenger") == ""
    # von Hand geändert: bleibt stehen
    p.fill("#absender", "rechnungen@example.com")
    p.fill("#benutzer", "anderer@example.com")
    assert p.input_value("#absender") == "rechnungen@example.com"
    # von Hand geleert: wieder vorbelegen
    p.fill("#absender", "")
    p.fill("#benutzer", "neu@example.com")
    assert p.input_value("#absender") == "neu@example.com"


def test_port_springt_mit_der_verschluesselung(seite):
    p = seite
    p.check("#mail-an")
    assert p.input_value("#port") == "465"
    p.select_option("#verschluesselung", "starttls")
    assert p.input_value("#port") == "587"
    p.select_option("#verschluesselung", "ssl")
    assert p.input_value("#port") == "465"
    p.fill("#port", "")
    p.select_option("#verschluesselung", "starttls")
    assert p.input_value("#port") == "587"
    # eigener Port bleibt stehen, und bleibt von Hand änderbar
    p.fill("#port", "2525")
    p.select_option("#verschluesselung", "ssl")
    assert p.input_value("#port") == "2525"
    p.fill("#port", "26")
    assert p.input_value("#port") == "26"


# ── Zwei Reiter ──────────────────────────────────────────────────────────────


def test_reiter_tastatur_und_aria(seite):
    p = seite
    assert p.get_attribute("[role=tablist]", "aria-label")
    reiter = p.locator("[role=tab]")
    assert reiter.count() == 2
    for i in range(2):
        r = reiter.nth(i)
        tafel = p.locator("#" + r.get_attribute("aria-controls"))
        assert tafel.get_attribute("role") == "tabpanel"
        assert tafel.get_attribute("aria-labelledby") == r.get_attribute("id")
    # Erster Start ohne Konten: „Einstellungen“
    assert p.get_attribute("#reiter-einstellungen", "aria-selected") == "true"
    assert p.get_attribute("#reiter-einstellungen", "tabindex") == "0"
    assert p.get_attribute("#reiter-holen", "tabindex") == "-1"
    assert p.is_visible("#tafel-einstellungen") and p.is_hidden("#tafel-holen")
    p.focus("#reiter-einstellungen")
    p.keyboard.press("ArrowLeft")
    assert p.evaluate("document.activeElement.id") == "reiter-holen"
    assert p.get_attribute("#reiter-holen", "aria-selected") == "true"
    assert p.is_visible("#tafel-holen") and p.is_hidden("#tafel-einstellungen")
    p.keyboard.press("ArrowRight")
    assert p.evaluate("document.activeElement.id") == "reiter-einstellungen"
    p.keyboard.press("Home")
    assert p.evaluate("document.activeElement.id") == "reiter-holen"
    p.keyboard.press("End")
    assert p.get_attribute("#reiter-einstellungen", "aria-selected") == "true"
    # Tab-Taste führt aus der Reiterleiste in die Tafel, nicht zum anderen Reiter
    p.keyboard.press("Tab")
    assert p.evaluate("document.activeElement.id") == "tafel-einstellungen"


def test_mit_konten_oeffnet_belege_holen(server, tmp_path):
    _speichern(server, tmp_path)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chromium")
        p = b.new_page()
        p.goto(server.adresse)
        p.wait_for_selector("#version:not(:empty)")
        assert p.get_attribute("#reiter-holen", "aria-selected") == "true"
        assert p.is_visible("#holen") and p.is_hidden("#formular")
        b.close()


# ── Ablage nach Jahr oder nach Jahr und Monat ────────────────────────────────


def test_ablage_standard_jahr_und_pruefung(tmp_path):
    assert einstellungen.laden(_toml(tmp_path, '[[konto]]\nquelle = "airbnb"\n')).ablage == "jahr"
    assert einstellungen.laden(_toml(tmp_path, 'ablage = "monat"\n')).ablage == "monat"
    with pytest.raises(einstellungen.EinstellungsFehler, match="ablage"):
        einstellungen.laden(_toml(tmp_path, 'ablage = "woche"\n'))
    einst = einstellungen.laden(_toml(tmp_path, 'ablage = "monat"\n'))
    assert einstellungen.aus_text(einstellungen.als_text(einst)).ablage == "monat"


def test_ordner_nach_monat_kontrolle_bleibt(tmp_path):
    from belegabruf.ziele.ordner import Ordner

    beleg = Beleg(quelle="airbnb", konto="standard", art="rechnung", schluessel="rechnung:x",
                  dateiname="2026-03-15_X.pdf", inhalt=b"%PDF", jahr=2026, rechnungsdatum=date(2026, 3, 15))
    assert Ordner(tmp_path).abliefern(beleg) == tmp_path / "airbnb" / "2026" / "2026-03-15_X.pdf"
    assert Ordner(tmp_path, ablage="monat").abliefern(beleg) == tmp_path / "airbnb" / "2026" / "03" / "2026-03-15_X.pdf"
    kontrolle = Beleg(quelle="airbnb", konto="standard", art="kontrolle", schluessel="kontrolle:2026-03",
                      dateiname="2026-03_standard.pdf", inhalt=b"%PDF", jahr=2026)
    assert Ordner(tmp_path, ablage="monat").abliefern(kontrolle) == tmp_path / "airbnb" / "kontrolle" / "2026-03_standard.pdf"


def test_umstellen_auf_monat_holt_nichts_doppelt_und_verschiebt_nichts(tmp_path, monkeypatch):
    """Duplikatschutz über das Protokoll (Schlüssel), nicht über den Pfad."""
    runde = {"belege": [("a1", "2026-10-30")]}

    class Zwei(Attrappe):
        def belege_holen(self, umgebung):
            erg = Ergebnis(self.name, self.konto.name)
            for kennung, datum in runde["belege"]:
                schluessel = f"rechnung:{kennung}"
                if umgebung.bekannt(schluessel):
                    erg.schon_da += 1
                    continue
                umgebung.abliefern(Beleg(quelle="airbnb", konto=self.konto.name, art="rechnung",
                                         schluessel=schluessel, dateiname=f"{datum}_{kennung}.pdf",
                                         inhalt=b"%PDF " + kennung.encode(), jahr=2026,
                                         rechnungsdatum=date.fromisoformat(datum)))
                erg.neu += 1
            return erg

    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Zwei(konto, Path("/x")))
    belege = tmp_path / "Belege"
    konto = einstellungen.Konto(quelle="airbnb", name="standard", titel="")
    jahr = einstellungen.Einstellungen(belegordner=belege, konten=[konto])
    assert ablauf.abrufen(jahr, konto, lambda t: None).neu == 1
    alt = belege / "airbnb" / "2026" / "2026-10-30_a1.pdf"
    assert alt.exists()

    monat = einstellungen.Einstellungen(belegordner=belege, konten=[konto], ablage="monat")
    runde["belege"] = [("a1", "2026-10-30"), ("a2", "2026-11-04")]
    erg = ablauf.abrufen(monat, konto, lambda t: None)
    assert (erg.neu, erg.schon_da) == (1, 1)
    assert alt.exists() and not (belege / "airbnb" / "2026" / "10").exists()  # nichts verschoben, nichts doppelt
    assert (belege / "airbnb" / "2026" / "11" / "2026-11-04_a2.pdf").exists()
    assert ablauf.fehlende_dateien(monat, konto) == 0  # der alte Beleg gilt weiter als vorhanden


def test_ablage_in_der_seite(seite, tmp_path):
    p = seite
    assert p.input_value("#ablage") == "jahr"
    assert "bereits abgelegte bleiben, wo sie sind" in p.inner_text("#ablage-hinweis")
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.select_option("#ablage", "monat")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert einstellungen.laden().ablage == "monat"
    p.reload()
    p.wait_for_selector("#version:not(:empty)")
    assert p.input_value("#ablage") == "monat"


def test_ablage_bleibt_beim_speichern_ohne_angabe(server, tmp_path):
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, ablage="monat"))[0].status == 200
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path))[0].status == 200
    assert einstellungen.laden().ablage == "monat"
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, ablage="../x"))
    assert antwort.status == 400 and "ablage" in json.loads(inhalt)["felder"]


# ── Zeitraum je Konto in der Seite ───────────────────────────────────────────


def test_zeitraum_je_konto_in_der_seite(seite, tmp_path):
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    wahl = p.locator("#kontenliste select[aria-label='Belege ab']")
    datum = p.locator("#kontenliste input.ab-datum")
    assert wahl.input_value() == "alle" and datum.is_hidden()
    wahl.select_option("datum")
    assert datum.is_visible()
    datum.fill("31.02.2026")
    p.click("#speichern")
    p.wait_for_selector("#speichern-meldung:not(.versteckt)")
    assert datum.evaluate("e => e.classList.contains('feld-fehler')")
    assert "TT.MM.JJJJ" in p.inner_text("#formular .feldsatz")
    datum.fill("01.03.2026")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert einstellungen.laden().konten[0].belege_ab == "01.03.2026"
    p.locator("#kontenliste select[aria-label='Belege ab']").select_option("letzte-3-monate")
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert einstellungen.laden().konten[0].belege_ab == "letzte-3-monate"
    p.reload()
    p.wait_for_selector("#version:not(:empty)")
    p.click("#reiter-einstellungen")
    assert p.locator("#kontenliste select[aria-label='Belege ab']").input_value() == "letzte-3-monate"
    assert "Belege ab 01." in p.inner_text("#konten")


# ── Mailanbieter-Auswahl ─────────────────────────────────────────────────────


@pytest.mark.parametrize("anbieter, host, port, art", [
    ("gmx", "mail.gmx.net", "587", "starttls"), ("webde", "smtp.web.de", "587", "starttls"),
    ("gmail", "smtp.gmail.com", "465", "ssl"), ("outlook", "smtp-mail.outlook.com", "587", "starttls"),
    ("m365", "smtp.office365.com", "587", "starttls"), ("ionos", "smtp.ionos.de", "465", "ssl"),
    ("strato", "smtp.strato.de", "465", "ssl"), ("icloud", "smtp.mail.me.com", "587", "starttls"),
])
def test_mailanbieter_fuellt_vor(seite, anbieter, host, port, art):
    p = seite
    p.check("#mail-an")
    p.select_option("#mailanbieter", anbieter)
    assert (p.input_value("#server"), p.input_value("#port"), p.input_value("#verschluesselung")) == (host, port, art)
    assert p.is_enabled("#server") and p.is_enabled("#port")  # bleiben änderbar


def test_mailanbieter_hinweise_und_all_inkl(seite):
    p = seite
    p.check("#mail-an")
    p.select_option("#mailanbieter", "gmail")
    assert "App-Passwort" in p.inner_text("#anbieter-hinweis")
    assert p.get_attribute("#anbieter-hinweis a", "href").startswith("https://support.google.com/")
    assert p.get_attribute("#anbieter-hinweis a", "rel") == "noopener noreferrer"
    p.select_option("#mailanbieter", "m365")
    assert "SMTP AUTH" in p.inner_text("#anbieter-hinweis")
    p.select_option("#mailanbieter", "outlook")
    assert "OAuth2" in p.inner_text("#anbieter-hinweis")
    p.select_option("#mailanbieter", "ionos")
    assert p.is_hidden("#anbieter-hinweis")
    p.select_option("#mailanbieter", "allinkl")
    assert p.input_value("#server") == "" and p.input_value("#port") == "465"
    assert "KAS" in p.inner_text("#anbieter-hinweis") and "kasserver" in p.get_attribute("#server", "placeholder")
    p.locator("#server").press_sequentially("w0123456.kasserver.com")
    assert p.input_value("#mailanbieter") == "allinkl"  # Server eintippen gehört dazu


def test_mailanbieter_handaenderung_springt_auf_anderer(seite):
    p = seite
    p.check("#mail-an")
    p.select_option("#mailanbieter", "gmx")
    p.fill("#port", "465")
    assert p.input_value("#mailanbieter") == "anderer" and p.is_hidden("#anbieter-hinweis")
    p.select_option("#mailanbieter", "strato")
    p.fill("#server", "smtp.example.com")
    assert p.input_value("#mailanbieter") == "anderer"
    p.select_option("#mailanbieter", "icloud")
    p.select_option("#verschluesselung", "ssl")
    assert p.input_value("#mailanbieter") == "anderer"


@pytest.mark.parametrize("host, port, art, erwartet", [
    ("smtp.strato.de", 465, "ssl", "strato"), ("SMTP.web.de", 587, "starttls", "webde"),
    ("w0999999.kasserver.com", 465, "ssl", "allinkl"), ("smtp.strato.de", 587, "starttls", "anderer"),
    ("smtp.example.com", 465, "ssl", "anderer"),
])
def test_mailanbieter_wird_beim_laden_erkannt(host, tmp_path, port, art, erwartet, umgebung):
    s = Bedienserver()
    s.im_hintergrund()
    try:
        daten = _eingaben(tmp_path, mail_an=True, mail={
            "server": host, "port": port, "verschluesselung": art, "benutzer": "ich@example.com",
            "absender": "ich@example.com", "empfaenger": ["belege@example.com"]})
        assert _anfrage(s, "POST", "/api/einstellungen", _mit(s), daten)[0].status == 200
        assert "anbieter" not in pfade.einstellungsdatei().read_text(encoding="utf-8").split("[mail]")[1]
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="chromium")
            p = b.new_page()
            p.goto(s.adresse)
            p.wait_for_selector("#version:not(:empty)")
            assert p.input_value("#mailanbieter") == erwartet
            b.close()
    finally:
        s.shutdown()
        s.server_close()


# ── Prüfbefund M1: Terminal-Einrichtung behält Kennungen ─────────────────────


def _terminal(monkeypatch, eingaben):
    import builtins

    folge = iter(eingaben)
    monkeypatch.setattr(builtins, "input", lambda text="": next(folge, "n"))


def test_terminal_namenloses_konto_mit_eigener_kennung_bleibt(monkeypatch):
    from belegabruf import einrichtung

    # So entsteht es, wenn man den Namen in der Oberfläche leert: Kennung „Privat“, kein Name.
    alt = Konto(quelle="airbnb", name="Privat", titel="", aktiv=False, belege_ab="letzte-3-monate",
                optionen={"adresse": "https://www.airbnb.de"})
    _terminal(monkeypatch, ["n", ""])  # „so lassen?“ nein, dann Enter
    konten = einrichtung._konten_abfragen("airbnb", [alt])
    assert [(k.name, k.anzeigetitel) for k in konten] == [("Privat", "")]
    k = konten[0]
    assert (k.aktiv, k.belege_ab, k.optionen) == (False, "letzte-3-monate", {"adresse": "https://www.airbnb.de"})


def test_terminal_namenlos_und_benannt_gemischt(monkeypatch):
    from belegabruf import einrichtung

    alt = [Konto(quelle="airbnb", name="standard", titel="Privat"), Konto(quelle="airbnb", name="Co", titel="Co")]
    # „so lassen?“ nein; wieder „Privat“ und „Co“ eingeben → beide Kennungen bleiben
    _terminal(monkeypatch, ["n", "Privat", "j", "Co", "n"])
    konten = einrichtung._konten_abfragen("airbnb", alt)
    assert [(k.name, k.anzeigetitel) for k in konten] == [("standard", "Privat"), ("Co", "Co")]


def test_terminal_umbenannt_dann_wieder_eingegeben(monkeypatch):
    from belegabruf import einrichtung

    # In der Oberfläche umbenannt: Kennung „Privat“, Name „Ferienwohnung“
    alt = [Konto(quelle="airbnb", name="Privat", titel="Ferienwohnung"), Konto(quelle="airbnb", name="Co", titel="Co")]
    _terminal(monkeypatch, ["n", "ferienwohnung", "j", "Co", "n"])
    konten = einrichtung._konten_abfragen("airbnb", alt)
    assert [(k.name, k.anzeigetitel) for k in konten] == [("Privat", "ferienwohnung"), ("Co", "Co")]


def test_terminal_einziges_konto_enter_behaelt_kennung(monkeypatch):
    from belegabruf import einrichtung

    _terminal(monkeypatch, ["n", ""])
    konten = einrichtung._konten_abfragen("airbnb", [Konto(quelle="airbnb", name="Hauptkonto", titel="Hauptkonto")])
    assert [(k.name, k.anzeigetitel) for k in konten] == [("Hauptkonto", "")]
    datei_text = einstellungen.als_text(einstellungen.Einstellungen(belegordner=Path("/tmp/B"), konten=konten))
    assert 'kennung = "Hauptkonto"' in datei_text


# ── Prüfbefund N2: Beenden hängt an der Bedienseite, Hilfe im Standardbrowser ──


def test_hilfefenster_haelt_programm_nicht_am_leben(monkeypatch):
    from belegabruf import oberflaeche

    geoeffnet = []
    monkeypatch.setattr(oberflaeche.webbrowser, "open", geoeffnet.append)
    takte = {"n": 0}

    class Seite:
        def __init__(self, url, haupt=False):
            self.url, self.haupt, self.zu = url, haupt, False

        def goto(self, adresse):
            pass

        def is_closed(self):
            return self.zu

        def close(self):
            self.zu = True

        def wait_for_timeout(self, ms):
            takte["n"] += 1
            if takte["n"] == 1:  # Hilfelink geklickt: neue Seite, Adresse kommt etwas später
                kontext.pages.append(hilfe)
            if takte["n"] == 2:
                hilfe.url = "https://support.google.com/mail/answer/185833"
            if takte["n"] == 3:
                kontext.pages.append(Seite("https://example.com/zweite"))
            if takte["n"] == 5:
                self.zu = True  # Bedienseite geschlossen
            assert takte["n"] < 50, "wartet trotz geschlossener Bedienseite weiter"

    hilfe = Seite("about:blank")

    class Kontext:
        def __init__(self):
            self.pages = [Seite("data:text/html,", haupt=True)]
            self.geschlossen = False

        def close(self):
            self.geschlossen = True

    kontext = Kontext()

    class PW:
        class chromium:  # noqa: N801
            @staticmethod
            def launch_persistent_context(**kw):
                return kontext

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: PW())
    s = Bedienserver()
    try:
        oberflaeche._fenster_offen_halten(s)
    finally:
        s.server_close()
    assert takte["n"] == 5 and kontext.geschlossen
    assert geoeffnet == ["https://support.google.com/mail/answer/185833", "https://example.com/zweite"]
    assert hilfe.zu  # nicht im Fenster der Bedienseite geblieben


def test_anmeldefenster_bricht_ab_wenn_bedienseite_zu(monkeypatch):
    monkeypatch.setattr(browser, "ABBRECHEN", __import__("threading").Event())
    browser.ABBRECHEN.set()

    class Seite:
        def is_closed(self):
            return False

    class Kontext:
        pages = [Seite()]

    assert browser.auf_mensch_warten(Kontext(), Seite(), lambda s: False, lambda t: None) == "abgebrochen"


def test_starten_setzt_abbrechen_nach_dem_fenster(monkeypatch, capsys):
    monkeypatch.setattr(browser, "ABBRECHEN", __import__("threading").Event())
    _, server = _starten_mit(monkeypatch, lambda server: None)
    assert browser.ABBRECHEN.is_set() and server.steuerung.beendet.is_set()


# ── Prüfbefund N3: „ab Datum“ in der Zukunft ─────────────────────────────────


def test_datum_in_der_zukunft_abgewiesen(server, tmp_path):
    from datetime import timedelta

    morgen = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server),
                               _eingaben(tmp_path, konten=[{"quelle": "airbnb", "name": "", "belege_ab": morgen}]))
    assert antwort.status == 400
    assert "Zukunft" in json.loads(inhalt)["felder"]["konto-0-ab"]
    heute = date.today().strftime("%d.%m.%Y")
    konten = [{"quelle": "airbnb", "name": "", "belege_ab": heute}]
    assert _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=konten))[0].status == 200


def test_datum_in_der_zukunft_aus_der_datei_gibt_hinweis(monkeypatch, tmp_path):
    class Leer(Attrappe):
        def belege_holen(self, umgebung):
            return Ergebnis(self.name, self.konto.name)

    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Leer(konto, Path("/x")))
    konto = Konto(quelle="airbnb", name="standard", titel="", belege_ab="01.01.2099")
    erg = ablauf.abrufen(einstellungen.Einstellungen(belegordner=tmp_path / "B", konten=[konto]), konto, lambda t: None)
    assert any("Zukunft" in h for h in erg.hinweise)


# ── Prüfbefund N4: verständliche Meldung bei der Kennung „standard“ ──────────


def test_kollision_mit_standard_kennung_verstaendlich(server, tmp_path):
    # früher namenlos, inzwischen „Privat“ (Kennung standard); neues Konto „Standard“
    _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=[{"quelle": "airbnb", "name": ""}]))
    zwei = [{"quelle": "airbnb", "name": "Privat", "kennung": "standard"}, {"quelle": "airbnb", "name": "Standard"}]
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), _eingaben(tmp_path, konten=zwei))
    satz = json.loads(inhalt)["felder"]["konto-1-name"]
    assert antwort.status == 400
    assert "„Privat“" in satz and "früher ohne Namen" in satz and "„Standard“ einen anderen Namen" in satz


def test_kollision_mit_namenlosem_konto_in_der_datei(tmp_path):
    a = Konto(quelle="airbnb", name="standard", titel="")
    b = Konto(quelle="airbnb", name="Standard", titel="Standard")
    text = einstellungen.kollision_text("Airbnb", a, b, "standard")
    assert text.startswith("Bei Airbnb gibt es schon ein Konto ohne Namen") and "einem der beiden einen Namen" in text


# ── Ein Starter: was nur „Einrichten“ konnte, geht jetzt in der Seite ──────────


def test_mail_passwort_loeschen(server, tmp_path, umgebung, monkeypatch):
    import keyring
    from keyring.errors import PasswordDeleteError

    def loeschen(d, k):
        if (d, k) not in umgebung:
            raise PasswordDeleteError()
        del umgebung[(d, k)]

    monkeypatch.setattr(keyring, "delete_password", loeschen)
    _speichern(server, tmp_path, mail_an=True)
    _anfrage(server, "POST", "/api/mail-passwort", _mit(server), {"passwort": GEHEIM})
    antwort, inhalt = _anfrage(server, "POST", "/api/mail-passwort-loeschen", _mit(server), {})
    assert antwort.status == 200 and json.loads(inhalt)["passwort"] == "fehlt"
    assert ("belegabruf", "mail") not in umgebung
    assert _anfrage(server, "POST", "/api/mail-passwort-loeschen", {}, {})[0].status == 403
    # fremder Eintrag im Passwortspeicher: nie anfassen
    text = pfade.einstellungsdatei().read_text(encoding="utf-8").replace(
        'passwort_eintrag = "belegabruf/mail"', 'passwort_eintrag = "mein-mailprogramm/ich"')
    pfade.einstellungsdatei().write_text(text, encoding="utf-8")
    umgebung[("mein-mailprogramm", "ich")] = "x"
    antwort, inhalt = _anfrage(server, "POST", "/api/mail-passwort-loeschen", _mit(server), {})
    assert antwort.status == 400 and umgebung[("mein-mailprogramm", "ich")] == "x"


def test_alte_datei_aus_einrichten_gilt_nicht_als_eigene_kommentare(tmp_path):
    datei = tmp_path / "e.toml"
    einst = einstellungen.Einstellungen(belegordner=tmp_path / "B", konten=[Konto(quelle="airbnb", name="a")])
    alt = einstellungen.als_text(einst).replace(
        "# Du kannst diese Datei mit jedem Texteditor ändern oder im Fenster „Belegabruf“\n"
        "# im Reiter „Einstellungen“. Zeilen mit # am Anfang sind nur Erklärungen.",
        "# Du kannst diese Datei mit jedem Texteditor ändern oder einfach noch einmal\n"
        '# "Einrichten" doppelklicken. Zeilen mit # am Anfang sind nur Erklärungen.').replace(
        "Ändern: belege einrichten.", 'Ändern über "Einrichten".')
    assert '"Einrichten" doppelklicken' in alt and 'Ändern über "Einrichten"' in alt
    datei.write_text(alt, encoding="utf-8")
    assert einstellungen.fremde_inhalte(datei) == []


def test_hinweise_ohne_terminal_taste():
    import inspect

    quelltext = inspect.getsource(ablauf)
    assert "E →" not in quelltext and "„Fehlende Dateien neu holen“" in quelltext


# ── Infoboxen beim Drüberfahren und bei Tastaturfokus ────────────────────────


def _box_zu(p, knopf: str):
    return p.locator(f"#{p.get_attribute(knopf, 'aria-describedby')}")


def test_infobox_am_grauen_knopf_bei_hover_fokus_und_esc(seite):
    p = seite
    p.click("#reiter-holen")
    assert p.is_disabled("#fehlende")  # nichts fehlt → grau
    box = _box_zu(p, "#fehlende")
    assert box.get_attribute("role") == "tooltip" and box.is_hidden()
    text = box.text_content()
    assert "versehentlich gelöscht oder verschoben" in text and "nicht erneut gemailt" in text and "Grau" in text
    # Maus auf den grauen Knopf: Infobox erscheint trotzdem (Hülle bekommt den Hover)
    p.hover("#fehlende", force=True)
    assert box.is_visible()
    p.mouse.move(5, 5)
    assert box.is_hidden()
    # ohne Maus: das ⓘ daneben per Tastatur
    info = p.locator("#fehlende ~ button.info-knopf")
    assert info.get_attribute("aria-describedby") == box.get_attribute("id")
    info.focus()
    assert box.is_visible()
    p.keyboard.press("Escape")
    assert box.is_hidden()
    p.keyboard.press("Tab")
    p.keyboard.press("Shift+Tab")
    assert box.is_visible()  # wieder fokussiert → wieder da


def test_infoboxen_an_allen_vier_stellen(server, tmp_path):
    _speichern(server, tmp_path)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chromium")
        p = b.new_page()
        p.goto(server.adresse)
        p.wait_for_selector("#version:not(:empty)")
        assert "auch bei Konten ohne Haken" in _box_zu(p, "#alle-pruefen").text_content()
        haken = p.locator("#konten input.holen-haken").first
        assert haken.get_attribute("aria-describedby") == "info-holen"
        assert "übersprungen" in p.locator("#info-holen").text_content()
        p.hover("#kopf-holen .info-huelle")
        assert p.is_visible("#info-holen")
        p.click("#reiter-einstellungen")
        wahl = p.locator("#kontenliste select[aria-label='Belege ab']")
        box = p.locator("#" + wahl.get_attribute("aria-describedby"))
        assert "nicht vermerkt" in box.text_content() and box.is_hidden()
        wahl.focus()
        assert box.is_visible()
        # keine HTML-Einschleusung: nur Text
        assert p.evaluate("[...document.querySelectorAll('.infobox')].every(e => e.children.length === 0)")
        b.close()


# ── Erster Versand per Mail: „nicht verschicken“ (Vorgabe) oder „auch verschicken“ ──


class _MailZiel:
    def __init__(self, adresse="belege@example.com"):
        self.name = f"mail:{adresse}"
        self.anzeigename = f"Mail an {adresse}"
        self.gesendet = []

    def senden(self, sendung, vor_senden):
        vor_senden()
        self.gesendet.append(sendung.rechnungsnummer)

    def schliessen(self):
        pass


def _mail_lauf(tmp_path, monkeypatch, belege, erstversand="nicht", belege_ab="alle", empfaenger=("belege@example.com",),
               status="ok"):
    """Ein Abruf mit Attrappe: holt `belege` (Kennung, Datum), schickt an falsche Mailziele."""
    class Quelle_(Attrappe):
        def belege_holen(self, umgebung_):
            erg = Ergebnis(self.name, self.konto.name, status=status)
            for kennung, datum in belege:
                if umgebung_.zu_alt(date.fromisoformat(datum)):
                    erg.uebersprungen += 1
                    continue
                if umgebung_.bekannt(f"rechnung:{kennung}"):
                    erg.schon_da += 1
                    continue
                umgebung_.abliefern(Beleg(quelle="airbnb", konto=self.konto.name, art="rechnung",
                                          schluessel=f"rechnung:{kennung}", dateiname=f"{datum}_{kennung}.pdf",
                                          inhalt=b"%PDF", jahr=2026, rechnungsdatum=date.fromisoformat(datum),
                                          rechnungsnummer=kennung))
                erg.neu += 1
            return erg

    ziele = [_MailZiel(a) for a in empfaenger]
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Quelle_(konto, Path("/x")))
    monkeypatch.setattr(ablauf, "lieferziele_erstellen", lambda einst: ziele)
    konto = Konto(quelle="airbnb", name="neu", belege_ab=belege_ab)
    einst = einstellungen.Einstellungen(
        belegordner=tmp_path / "B", konten=[konto], ziele=["ordner", "mail"],
        mail=einstellungen.MailEinstellung(server="smtp.example.com", benutzer="ich@example.com",
                                           absender="ich@example.com", empfaenger=list(empfaenger),
                                           erstversand=erstversand))
    return ablauf.abrufen(einst, konto, lambda t: None), ziele


def test_erstversand_nicht_erster_lauf_neues_konto_nur_ablegen(tmp_path, monkeypatch, umgebung):
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-11-04")])
    assert ziel.gesendet == [] and erg.erstlauf_abgelegt == 2
    text = ablauf.zusammenfassung([erg], tmp_path)
    assert "2 Beleg(e) abgelegt, nicht verschickt (erster Lauf)" in text
    assert (tmp_path / "B" / "airbnb" / "2026" / "2026-10-02_a1.pdf").exists()  # abgelegt
    # zweiter Lauf: nur das Neue geht raus
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-11-04"), ("a3", "2026-11-20")])
    assert ziel.gesendet == ["a3"] and erg.erstlauf_abgelegt == 0


def test_erstversand_auch_neues_konto_schickt_zeitraum(tmp_path, monkeypatch, umgebung):
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("alt", "2026-01-10"), ("n1", "2026-10-02"), ("n2", "2026-11-04")],
                              erstversand="auch", belege_ab="01.10.2026")
    assert erg.uebersprungen == 1 and sorted(ziel.gesendet) == ["n1", "n2"] and erg.erstlauf_abgelegt == 0


def test_erstversand_nicht_neue_adresse_bekommt_nur_neues(tmp_path, monkeypatch, umgebung):
    # erster Lauf mit einer Adresse, zweiter (normal), dann kommt eine zweite Adresse dazu
    _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02")])
    _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-10-20")])
    erg, (alt, neu) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-10-20"), ("a3", "2026-11-04")],
                                 empfaenger=("belege@example.com", "steuer@example.com"))
    assert alt.gesendet == ["a3"] and neu.gesendet == ["a3"]  # a1, a2 gelten für die neue Adresse als verschickt
    assert erg.lieferungen["mail:steuer@example.com"]["schon_markiert"] == 2


def test_erstversand_auch_neue_adresse_bekommt_bestand(tmp_path, monkeypatch, umgebung):
    _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02")], erstversand="auch")
    erg, (alt, neu) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-11-04")], erstversand="auch",
                                 empfaenger=("belege@example.com", "steuer@example.com"))
    assert alt.gesendet == ["a2"] and sorted(neu.gesendet) == ["a1", "a2"]


def test_erstlauf_bleibt_offen_bis_die_liste_gelesen_ist(tmp_path, monkeypatch, umgebung):
    # erster Versuch: Anmeldung mittendrin abgelaufen → gilt weiter als erster Lauf
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02")], status="abgelaufen")
    assert ziel.gesendet == []
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-11-04")])
    assert ziel.gesendet == [] and erg.erstlauf_abgelegt == 1  # a2 kam im (fortgesetzten) ersten Lauf
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-11-04"), ("a3", "2026-11-20")])
    assert ziel.gesendet == ["a3"]


def test_bisheriges_protokoll_ist_kein_erster_lauf(tmp_path, monkeypatch, umgebung):
    """Nach dem Update: ein Protokoll mit Rechnungen, aber ohne Erstlauf-Zeile, ist nicht neu."""
    from belegabruf.protokoll import Protokoll

    p = Protokoll("airbnb", "neu", tmp_path / "B")
    p.eintragen(Beleg(quelle="airbnb", konto="neu", art="rechnung", schluessel="rechnung:a1", dateiname="x.pdf",
                      inhalt=b"", jahr=2026, rechnungsdatum=date(2026, 10, 2)), None, ["ordner"])
    p.schalten("mail:belege@example.com", True)
    p.als_schon_markieren("mail:belege@example.com")
    erg, (ziel,) = _mail_lauf(tmp_path, monkeypatch, [("a1", "2026-10-02"), ("a2", "2026-11-04")])
    assert ziel.gesendet == ["a2"] and erg.erstlauf_abgelegt == 0


def test_erstversand_in_der_datei_und_pruefung(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('ziele = ["ordner"]\n[mail]\nserver = ""\n', encoding="utf-8")
    assert einstellungen.laden(datei).mail.erstversand == "nicht"  # alte Datei ohne Schlüssel
    datei.write_text('[mail]\nerstversand = "auch"\n', encoding="utf-8")
    einst = einstellungen.laden(datei)
    assert einst.mail.erstversand == "auch"
    assert einstellungen.aus_text(einstellungen.als_text(einst)).mail.erstversand == "auch"
    einst.mail.erstversand = "immer"
    with pytest.raises(einstellungen.EinstellungsFehler, match="erstversand"):
        einstellungen.pruefen(einst)


def test_erstversand_in_der_seite(seite, tmp_path):
    p = seite
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.check("#mail-an")
    assert p.is_checked("input[name=erstversand][value=nicht]")
    assert "nur abgelegt" in p.inner_text("#erstversand-erklaerung")
    assert p.get_attribute("#erstversand", "aria-describedby") == "erstversand-erklaerung"
    assert "Achtung: Bei einem neuen Konto" not in p.inner_text("#mail-erklaerung")
    p.check("input[name=erstversand][value=auch]")
    assert "einmal raus" in p.inner_text("#erstversand-erklaerung")
    for feld, wert in (("#server", "smtp.example.com"), ("#benutzer", "ich@example.com"),
                       ("#empfaenger", "belege@example.com")):
        p.fill(feld, wert)
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    assert einstellungen.laden().mail.erstversand == "auch"
    p.reload()
    p.wait_for_selector("#version:not(:empty)")
    p.click("#reiter-einstellungen")
    assert p.is_checked("input[name=erstversand][value=auch]")


def test_erstversand_ungueltig_vom_server_abgewiesen(server, tmp_path):
    daten = _eingaben(tmp_path, mail={"erstversand": "immer"})
    antwort, inhalt = _anfrage(server, "POST", "/api/einstellungen", _mit(server), daten)
    assert antwort.status == 400 and "erstversand" in json.loads(inhalt)["felder"]


def test_mailtext_nennt_belegadressen(seite):
    text = " ".join(seite.locator("#mail-erklaerung").text_content().split())
    assert "sevDesk, Lexware Office" in text and "Steuerbüro" in text
    assert seite.locator("#mail-erklaerung a").count() == 0  # Produktnamen ohne Links



# ── Anmelden im Reiter „Einstellungen“, Status im Reiter „Belege holen“ ──────


def test_zeitpunkt_der_pruefung():
    from datetime import datetime

    jetzt = datetime(2026, 11, 25, 22, 0)
    assert aktionen._zeitpunkt_text(datetime(2026, 11, 25, 21, 30), jetzt) == "geprüft heute 21:30"
    assert aktionen._zeitpunkt_text(datetime(2026, 11, 24, 8, 5), jetzt) == "geprüft gestern 08:05"
    assert aktionen._zeitpunkt_text(datetime(2026, 11, 2, 9, 0), jetzt) == "geprüft am 02.11. 09:00"


def test_anmeldestand_nie_abgelaufen_unbekannt(tmp_path):
    from belegabruf import zustand as merkzettel

    st = aktionen.Steuerung()
    k = Konto(quelle="airbnb", name="standard", titel="")
    assert st.anmeldestand(k) == "nie"  # kein Profil, nie angemeldet
    st.anmeldestand_merken(k, "abgemeldet")
    assert st.anmeldestand(k) == "nie"
    st.anmeldestand_merken(k, "angemeldet")
    assert st.anmeldestand(k) == "angemeldet" and merkzettel.je_angemeldet("airbnb", "standard")
    st.anmeldestand_merken(k, "abgemeldet")
    assert st.anmeldestand(k) == "abgelaufen"
    assert aktionen.Steuerung().anmeldestand(k) == "unbekannt"  # nach Neustart: schon mal angemeldet, ungeprüft


def test_mittendrin_abgelaufen_zeigt_abgelaufen(server, tmp_path, monkeypatch):
    class Mittendrin(Attrappe):
        def belege_holen(self, umgebung_):
            return Ergebnis(self.name, self.konto.name, status="abgelaufen")

    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Mittendrin(konto, Path("/x")))
    Attrappe.angemeldet = True
    _speichern(server, tmp_path)
    _anfrage(server, "POST", "/api/holen", _mit(server), {})
    server.steuerung.faden.join(10)
    konto = json.loads(_anfrage(server, "GET", "/api/zustand", _mit(server))[1])["konten"][0]
    assert konto["zustand"] == "abgelaufen" and konto["geprueft"].startswith("geprüft heute")


def test_neues_konto_anmelden_erst_nach_dem_speichern(seite, tmp_path):
    p = seite
    zeile = p.locator("#kontenliste .kontozeile").first
    assert "nach dem Speichern" in zeile.inner_text()
    assert zeile.locator("button:has-text('Anmelden')").is_hidden()
    p.fill("#belegordner", str(tmp_path / "Belege"))
    p.click("#speichern")
    p.wait_for_selector("#gespeichert:not(.versteckt)")
    zeile = p.locator("#kontenliste .kontozeile").first
    assert zeile.locator("button:has-text('Anmelden')").is_visible()
    assert "noch nie angemeldet" in zeile.inner_text()
