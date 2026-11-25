"""Tests ohne Browser und ohne echte Belege (alle Beispieldaten sind erfunden)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pymupdf
import pytest

from belegabruf import aktualisierung, einstellungen, pfade, pruefung, zustand
from belegabruf.einstellungen import Einstellungen, Konto
from belegabruf import ablauf, quellen
from belegabruf import protokoll as protokoll_modul
from belegabruf.protokoll import Protokoll
from belegabruf.quellen import airbnb
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle
from belegabruf.ziele.ordner import Ordner


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    return tmp_path / "daten"


def _monats_pdf(zeilen: list[tuple[str, str, str, str]]) -> bytes:
    """Baut ein Monats-PDF wie bei Airbnb: je Zeile Nummer, Datum, Code + Link."""
    dok = pymupdf.open()
    seite = dok.new_page()
    seite.insert_text((40, 100), "Airbnb-Servicegebühr für die Nutzung der Online-Plattform")
    y = 150
    for nummer, datum, code, kennung in zeilen:
        teil1, teil2 = nummer[:18], nummer[18:]
        seite.insert_text((42, y), teil1, fontsize=8)
        seite.insert_text((42, y + 10), teil2, fontsize=8)
        seite.insert_text((170, y), datum, fontsize=8)
        seite.insert_text((273, y), code, fontsize=8)
        seite.insert_text((340, y), "Gutschrift" if kennung.startswith("g") else "Rechnung", fontsize=8)
        for dy in (0, 10):
            seite.insert_link({
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(42, y - 8 + dy, 153, y + 2 + dy),
                "uri": f"https://www.airbnb.de/invoice/{kennung}",
            })
        y += 40
    inhalt = dok.tobytes()
    dok.close()
    return inhalt


def test_monats_pdf_lesen():
    inhalt = _monats_pdf([
        ("AIUC-111111111-DE-2222222", "2026-10-27", "HMAAAA1111", "abc123"),
        ("AIUC-333333333-DE-4444444", "2026-10-29", "HMBBBB2222", "def456"),
    ])
    uebersicht = airbnb.monats_pdf_lesen(inhalt)
    assert uebersicht.anzahl_zeilen == 2
    assert [z.kennung for z in uebersicht.zeilen] == ["abc123", "def456"]
    erste = uebersicht.zeilen[0]
    assert erste.rechnungsnummer == "AIUC-111111111-DE-2222222"
    assert erste.buchungscode == "HMAAAA1111"
    assert erste.datum == "2026-10-27"
    assert erste.dokumentart == "Rechnung"


def test_zeile_ohne_link_wird_gemeldet():
    inhalt = _monats_pdf([("AIUC-111111111-DE-2222222", "2026-10-27", "HMAAAA1111", "abc123")])
    dok = pymupdf.open(stream=inhalt, filetype="pdf")
    dok[0].insert_text((42, 300), "123456789012345678  2025-11-03  HMCCCC3333  Rechnung", fontsize=8)
    uebersicht = airbnb.monats_pdf_lesen(dok.tobytes())
    assert uebersicht.anzahl_zeilen == 2
    assert len(uebersicht.zeilen) == 1
    assert uebersicht.ohne_link == ["HMCCCC3333"]


def test_monat_aus_text():
    assert airbnb.monat_aus_text("Oktober 2026") == (2026, 10)
    assert airbnb.monat_aus_text("März 2025") == (2025, 3)
    assert airbnb.monat_aus_text("Quatsch") is None


def test_dateiname_ohne_namen():
    assert airbnb.dateiname("2026-10-27", "HMAAAA1111", "AIUC-1-DE-2") == "2026-10-27_HMAAAA1111_AIUC-1-DE-2.pdf"


def test_rechnungsseite_lesen_mit_umbruch():
    text = ("Rechnung Ausstellungsdatum der Rechnung: 2026-10-27 Rechnungsnummer: AIUC-111111111-DE-\n"
            "2222222 Gebühren für die Buchung HMAAAA1111 am 2026-10-27")
    daten = airbnb.rechnungsseite_lesen(text)
    assert daten.rechnungsnummer == "AIUC-111111111-DE-2222222"
    assert daten.datum == "2026-10-27"
    assert daten.buchungscode == "HMAAAA1111"


@pytest.mark.parametrize("text,grund", [
    ("", "leere Seite"),
    ("Einloggen oder registrieren. " * 10, "Anmeldeseite"),
    ("Seite nicht gefunden – Fehler 404. " * 10, "Fehlerseite (z. B. 404)"),
])
def test_pruefung_lehnt_falsche_seiten_ab(text, grund):
    assert pruefung.seite_ist_beleg(text, ["Rechnungsnummer", "AIUC-1-DE-2"]) == grund


def test_pruefung_nimmt_echte_rechnung():
    text = "Rechnung von Airbnb. Rechnungsnummer: AIUC-1-DE-\n2 Buchung HMAAAA1111 " + "x" * 80
    assert pruefung.seite_ist_beleg(text, ["Rechnungsnummer", "AIUC-1-DE-2", "HMAAAA1111"]) is None


def test_einstellungen_hin_und_zurueck(tmp_path):
    einst = Einstellungen(
        belegordner=tmp_path / "Belege",
        konten=[Konto("airbnb", "privat"), Konto("airbnb", "co-host", aktiv=False)],
    )
    datei = einstellungen.speichern(einst)
    text = datei.read_text(encoding="utf-8")
    assert "# Einstellungen für Belegabruf" in text
    assert 'aktiv = "nein"' in text
    geladen = einstellungen.laden()
    assert geladen.belegordner == tmp_path / "Belege"
    assert [k.name for k in geladen.aktive_konten()] == ["privat"]


def test_einstellungen_liegen_nicht_im_programmordner(datenordner):
    assert pfade.einstellungsdatei().parent == datenordner
    assert pfade.profilordner("airbnb", "Mein Konto").name == "airbnb-mein-konto"


def _beleg(schluessel="rechnung:abc", inhalt=b"%PDF-1.4 test"):
    return Beleg(
        quelle="airbnb", konto="Mein Konto", art="rechnung", schluessel=schluessel,
        dateiname=f"2026-10-27_HMAAAA1111_{schluessel[-3:]}.pdf", inhalt=inhalt, jahr=2026,
        rechnungsdatum=date(2026, 10, 27), rechnungsnummer="AIUC-1-DE-2", buchungscode="HMAAAA1111",
    )


def test_protokoll_liegt_im_datenordner(tmp_path, datenordner):
    protokoll = Protokoll("airbnb", "Mein Konto", tmp_path / "Belege")
    assert protokoll.datei == datenordner / "protokolle" / "airbnb" / "mein-konto.csv"
    assert "profile" not in protokoll.datei.parts


def test_protokoll_entscheidet_nicht_der_ordner(tmp_path):
    belege = tmp_path / "Belege"
    beleg = _beleg()
    ort = Ordner(belege).abliefern(beleg)
    assert ort == belege / "airbnb" / "2026" / beleg.dateiname
    Protokoll("airbnb", "Mein Konto", belege).eintragen(beleg, ort, ["ordner"])
    # Datei gelöscht (z. B. an die Buchhaltung weitergegeben) → bleibt "schon geholt"
    ort.unlink()
    protokoll = Protokoll("airbnb", "Mein Konto", belege)
    assert protokoll.bekannt("rechnung:abc")
    assert protokoll.fehlende() == ["rechnung:abc"]


def test_altes_protokoll_wird_uebernommen(tmp_path):
    belege = tmp_path / "Belege"
    belege.mkdir()
    alt = belege / "protokoll.csv"
    alt.write_text(
        "zeitpunkt;quelle;konto;art;schluessel;rechnungsdatum;buchungscode;rechnungsnummer;datei;ziele\n"
        "2026-11-24T16:38:00;airbnb;Mein Konto;kontrolle;monat:2026-10;;;;airbnb/kontrolle/2026-10_mein-konto.pdf;ordner\n"
        "2026-11-24T16:39:00;airbnb;Mein Konto;rechnung;rechnung:abc;2026-10-27;HMAAAA1111;AIUC-1-DE-2;airbnb/2026/x.pdf;ordner\n",
        encoding="utf-8",
    )
    assert protokoll_modul.altes_protokoll_uebernehmen(belege) == 2
    assert not alt.exists()
    assert (belege / "protokoll.csv.uebernommen").exists()
    protokoll = Protokoll("airbnb", "Mein Konto", belege)
    assert protokoll.bekannt("rechnung:abc") and protokoll.bekannt("monat:2026-10")
    # Zweiter Start: nichts mehr zu tun
    assert protokoll_modul.altes_protokoll_uebernehmen(belege) == 0


class _Probequelle(Quelle):
    """Tut so, als böte der Anbieter zwei Rechnungen an."""

    name = "probe"
    anzeigename = "Probe"

    def sitzung_pruefen(self):
        return True

    def anmelden_lassen(self, melden):
        return True

    def belege_holen(self, umgebung):
        erg = Ergebnis(self.name, self.konto.name)
        for schluessel in ("rechnung:aaa", "rechnung:bbb"):
            if umgebung.bekannt(schluessel):
                erg.schon_da += 1
                continue
            b = _beleg(schluessel, inhalt=b"%PDF-" + schluessel.encode())
            b.quelle = self.name
            umgebung.abliefern(b)
            erg.neu += 1
        return erg


def test_geloeschte_datei_kommt_nur_auf_wunsch_wieder(tmp_path, monkeypatch):
    monkeypatch.setitem(quellen.QUELLEN, "probe", ("Probe", lambda: _Probequelle))
    einst = Einstellungen(belegordner=tmp_path / "Belege", konten=[Konto("probe", "Mein Konto")])
    konto = einst.konten[0]
    assert ablauf.abrufen(einst, konto, lambda t: None).neu == 2
    assert ablauf.abrufen(einst, konto, lambda t: None).neu == 0
    datei = tmp_path / "Belege" / "probe" / "2026" / "2026-10-27_HMAAAA1111_aaa.pdf"
    datei.unlink()
    # Normaler Lauf: kommt NICHT wieder, aber Hinweis
    erg = ablauf.abrufen(einst, konto, lambda t: None)
    assert erg.neu == 0 and not datei.exists()
    assert any("Fehlende Dateien neu holen" in h for h in erg.hinweise)
    assert ablauf.fehlende_dateien(einst, konto) == 1
    # Auf Wunsch: genau diese Datei kommt wieder
    erg = ablauf.abrufen(einst, konto, lambda t: None, nachholen=True)
    assert erg.neu == 1 and datei.exists()
    assert ablauf.fehlende_dateien(einst, konto) == 0


def test_gleicher_name_ueberschreibt_nicht(tmp_path):
    ordner = Ordner(tmp_path)
    def beleg(inhalt):
        return Beleg(quelle="airbnb", konto="privat", art="rechnung", schluessel=inhalt.decode(),
                     dateiname="x.pdf", inhalt=inhalt, jahr=2026)
    a = ordner.abliefern(beleg(b"%PDF-a"))
    b = ordner.abliefern(beleg(b"%PDF-b"))
    assert a != b and a.read_bytes() == b"%PDF-a" and b.name == "x-2.pdf"


def test_gutschrift_im_dateinamen():
    assert airbnb.dateiname("2026-06-01", "HMAAAA1111", "AIUC-1-DE-2", gutschrift=True).endswith("_Gutschrift.pdf")


def test_kontrolle_liegt_im_kontrollordner(tmp_path):
    ort = Ordner(tmp_path).lokale_datei("airbnb", "kontrolle", 2026, "2026-10_privat.pdf")
    assert ort == tmp_path / "airbnb" / "kontrolle" / "2026-10_privat.pdf"


def test_warnung_nach_zwei_monaten():
    zustand.lauf_merken("airbnb", "privat", datetime.now() - timedelta(days=70))
    assert zustand.zu_lange_her("airbnb", "privat") is not None
    zustand.lauf_merken("airbnb", "privat")
    assert zustand.zu_lange_her("airbnb", "privat") is None


def test_versionsvergleich():
    assert aktualisierung.ist_neuer("v1.0.1", "1.0.0")
    assert aktualisierung.ist_neuer("2.0.0", "1.9.9")
    assert not aktualisierung.ist_neuer("v1.0.0", "1.0.0")


def test_keine_hive_homes_bezuege_im_repo():
    wurzel = Path(__file__).resolve().parents[2]  # ganzes Repo
    verboten = ["hive" + " homes", "hive" + "-homes", "hive" + "homes"]
    for datei in wurzel.rglob("*"):
        if any(t in datei.parts for t in (".git", ".venv", "__pycache__")) or not datei.is_file():
            continue
        if datei.suffix not in {".py", ".md", ".toml", ".yml", ".command", ".cmd", ".txt", ""}:
            continue
        inhalt = datei.read_text(encoding="utf-8", errors="ignore").lower()
        for wort in verboten:
            assert wort not in inhalt, f"{datei} erwähnt '{wort}'"


def test_keine_syntaxwarnung_in_modulen():
    """Ungültige Escape-Sequenzen (z. B. in eingebettetem JavaScript) sieht jeder Nutzer als
    Warnung — und künftige Python-Versionen machen einen Fehler daraus."""
    import warnings

    ordner = Path(__file__).resolve().parents[1] / "belegabruf"
    for datei in sorted(ordner.rglob("*.py")):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            compile(datei.read_text(encoding="utf-8"), str(datei), "exec")


# ── Zeitraum je Konto („Belege ab“) ──────────────────────────────────────────


@pytest.mark.parametrize("wert, erwartet", [
    ("alle", None),
    ("letzter-monat", date(2026, 10, 1)),
    ("letzte-3-monate", date(2026, 8, 1)),
    ("letzte-12-monate", date(2025, 11, 1)),
    ("15.03.2026", date(2026, 3, 15)),
])
def test_zeitraum_ab_datum(wert, erwartet):
    assert einstellungen.ab_datum(wert, heute=date(2026, 11, 25)) == erwartet


def test_zeitraum_ueber_den_jahreswechsel():
    assert einstellungen.ab_datum("letzter-monat", heute=date(2027, 1, 5)) == date(2026, 12, 1)
    assert einstellungen.ab_datum("letzte-3-monate", heute=date(2027, 1, 31)) == date(2026, 10, 1)


@pytest.mark.parametrize("falsch", ["gestern", "31.02.2026", "2026-03-15", "3 monate"])
def test_zeitraum_falsch(falsch):
    with pytest.raises(einstellungen.EinstellungsFehler, match="belege_ab"):
        einstellungen.zeitraum_normal(falsch)


def test_zeitraum_in_der_datei(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('[[konto]]\nquelle = "airbnb"\nname = "a"\n', encoding="utf-8")
    einst = einstellungen.laden(datei)
    assert einst.konten[0].belege_ab == "alle" and einst.konten[0].ab() is None  # alte Datei = alle
    assert "belege_ab =" not in einstellungen.als_text(einst)
    einst.konten[0].belege_ab = "letzte-3-monate"
    wieder = einstellungen.aus_text(einstellungen.als_text(einst))
    assert wieder.konten[0].belege_ab == "letzte-3-monate" and wieder.konten[0].optionen == {}


def _airbnb_ohne_browser(monkeypatch, monate: dict[str, bytes], geholt: list):
    from contextlib import contextmanager

    from belegabruf import browser

    @contextmanager
    def profil(profil, sichtbar):
        yield object()

    monkeypatch.setattr(browser, "profil_oeffnen", profil)
    monkeypatch.setattr(browser, "neue_seite", lambda kontext: object())
    monkeypatch.setattr(browser, "pause", lambda *a, **k: None)
    geladen = []
    monkeypatch.setattr(airbnb.Airbnb, "_monate", lambda self, seite: [("", m) for m in monate])
    monkeypatch.setattr(airbnb.Airbnb, "_monats_pdf_laden",
                        lambda self, seite, text: geladen.append(text) or monate[text])

    def einzeln(self, seite, zeile, umgebung, erg):
        geholt.append(zeile.kennung)
        umgebung.abliefern(Beleg(quelle="airbnb", konto="a", art="rechnung", schluessel=f"rechnung:{zeile.kennung}",
                                 dateiname=f"{zeile.kennung}.pdf", inhalt=b"%PDF", jahr=2026,
                                 rechnungsdatum=date.fromisoformat(zeile.datum)))
        erg.neu += 1

    monkeypatch.setattr(airbnb.Airbnb, "_einzelrechnung", einzeln)
    return geladen


def test_airbnb_zeitraum_filtert_vor_dem_download(monkeypatch, tmp_path):
    from belegabruf.quellen.basis import Umgebung

    monate = {
        "August 2026": _monats_pdf([("AIUC-111111111-DE-1111111", "2026-08-20", "HMAAAA1111", "aug1")]),
        "September 2026": _monats_pdf([("AIUC-222222222-DE-2222222", "2026-09-03", "HMBBBB2222", "sep1"),
                                       ("AIUC-333333333-DE-3333333", "2026-09-20", "HMCCCC3333", "sep2")]),
        "Oktober 2026": _monats_pdf([("AIUC-444444444-DE-4444444", "2026-10-02", "HMDDDD4444", "okt1")]),
    }
    geholt: list[str] = []
    geladen = _airbnb_ohne_browser(monkeypatch, monate, geholt)
    bekannt: set[str] = set()

    def umgebung(ab):
        def abliefern(beleg):
            bekannt.add(beleg.schluessel)
            return []
        return Umgebung(bekannt=lambda s: s in bekannt, abliefern=abliefern, vorhandene_datei=lambda s: None,
                        melden=lambda t: None, ab=ab)

    quelle = airbnb.Airbnb(Konto("airbnb", "a"), tmp_path / "profil")
    erg = quelle.belege_holen(umgebung(date(2026, 9, 15)))
    # August gar nicht geladen, im September nur ab dem 15.; nichts davon im Protokoll
    assert geladen == ["September 2026", "Oktober 2026"]
    assert geholt == ["sep2", "okt1"] and erg.uebersprungen == 1
    assert erg.erwartet == 2 and erg.vorhanden == 2
    assert "monat:2026-08" not in bekannt and "rechnung:sep1" not in bekannt and "rechnung:aug1" not in bekannt
    assert any("1 Monat(e) vor dem Zeitraum" in h for h in erg.hinweise)

    # Zeitraum erweitert: das Übersprungene wird nachgeholt
    geholt.clear()
    erg = quelle.belege_holen(umgebung(None))
    assert sorted(geholt) == ["aug1", "sep1"] and erg.uebersprungen == 0 and erg.schon_da == 2


def test_zusammenfassung_und_json_nennen_uebersprungene():
    import json

    erg = Ergebnis("skool", "standard", neu=2, uebersprungen=3, ab="2026-08-01", anzeige="Skool")
    text = ablauf.zusammenfassung([erg], Path("/tmp/Belege"))
    assert "2 neu, 0 schon vorhanden, 3 übersprungen (älter als Zeitraum)" in text
    assert "Zeitraum: Belege ab 01.08.2026" in text
    daten = json.loads(json.dumps(erg.als_dict()))
    assert daten["uebersprungen"] == 3 and daten["ab"] == "2026-08-01"


def test_ablauf_gibt_zeitraum_an_die_quelle(monkeypatch, tmp_path):
    gesehen = {}

    class Fake(Quelle):
        name = "airbnb"

        def sitzung_pruefen(self):
            return True

        def anmelden_lassen(self, melden):
            return True

        def belege_holen(self, umgebung):
            gesehen["ab"] = umgebung.ab
            return Ergebnis(self.name, self.konto.name, uebersprungen=4)

    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Fake(konto, tmp_path))
    konto = Konto("airbnb", "a", belege_ab="01.06.2026")
    erg = ablauf.abrufen(Einstellungen(belegordner=tmp_path / "B", konten=[konto]), konto, lambda t: None)
    assert gesehen["ab"] == date(2026, 6, 1) and erg.ab == "2026-06-01" and erg.uebersprungen == 4


# ── Update nur durch Auspacken: Startdateien richten sich selbst ein ─────────


def _startdatei_ausfuehren(tmp_path, name: str, uv_da: bool = True, sync_klappt: bool = True):
    """Führt eine Mac-Startdatei in einer Kopie aus, mit einem falschen „uv“, das nur
    mitschreibt (lädt nichts, startet nichts)."""
    import shutil
    import subprocess

    wurzel = Path(__file__).resolve().parents[2]
    (tmp_path / "Start Mac").mkdir()
    (tmp_path / "programm").mkdir()
    shutil.copy(wurzel / "Start Mac" / name, tmp_path / "Start Mac" / name)
    werkzeuge = tmp_path / "bin"
    werkzeuge.mkdir()
    protokoll = tmp_path / "uv.log"
    if uv_da:
        falsches_uv = werkzeuge / "uv"
        falsches_uv.write_text(
            "#!/bin/bash\n"
            f'echo "$*" >> "{protokoll}"\n'
            f'if [ "$1" = sync ]; then mkdir -p .venv; {"exit 0" if sync_klappt else "exit 1"}; fi\n'
            "exit 0\n", encoding="utf-8")
        falsches_uv.chmod(0o755)
    umgebung = {"PATH": f"{werkzeuge}:/usr/bin:/bin", "HOME": str(tmp_path / "home")}
    lauf = subprocess.run(["/bin/bash", str(tmp_path / "Start Mac" / name)], input="\n", capture_output=True,
                          text=True, env=umgebung, timeout=30)
    aufrufe = protokoll.read_text(encoding="utf-8").splitlines() if protokoll.exists() else []
    return lauf, aufrufe


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Mac-Startdatei")
@pytest.mark.parametrize("name, befehl", [("Belege holen.command", "belege oberflaeche"),
                                          ("Belegabruf (Terminal).command", "belege start")])
def test_startdatei_richtet_neue_version_selbst_ein(tmp_path, name, befehl):
    lauf, aufrufe = _startdatei_ausfuehren(tmp_path, name)
    assert "Richte die neue Version ein" in lauf.stdout
    assert aufrufe == ["sync --no-dev --quiet", "run --no-dev --quiet playwright install --no-shell chromium",
                       f"run --no-dev --quiet {befehl}"]
    # zweiter Start: schon eingerichtet, nur noch starten
    (tmp_path / "uv.log").unlink()
    import subprocess

    lauf = subprocess.run(["/bin/bash", str(tmp_path / "Start Mac" / name)], input="\n", capture_output=True,
                          text=True, env={"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path / "home")},
                          timeout=30)
    assert "Richte" not in lauf.stdout
    assert (tmp_path / "uv.log").read_text(encoding="utf-8").splitlines() == [f"run --no-dev --quiet {befehl}"]


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Mac-Startdatei")
def test_startdatei_ohne_uv_verweist_auf_einrichten(tmp_path):
    lauf, aufrufe = _startdatei_ausfuehren(tmp_path, "Belege holen.command", uv_da=False)
    assert lauf.returncode == 1 and "Einrichten" in lauf.stdout and aufrufe == []


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Mac-Startdatei")
def test_startdatei_halbe_einrichtung_wird_weggeraeumt(tmp_path):
    lauf, aufrufe = _startdatei_ausfuehren(tmp_path, "Belege holen.command", sync_klappt=False)
    assert lauf.returncode == 1 and "Einrichten" in lauf.stdout
    assert not (tmp_path / "programm" / ".venv").exists()  # nächster Start versucht es erneut
    assert not any("belege" in a for a in aufrufe)


def test_windows_startdateien_richten_sich_selbst_ein():
    wurzel = Path(__file__).resolve().parents[2]
    for name, befehl in (("Belege holen.cmd", "belege oberflaeche"), ("Belegabruf (Terminal).cmd", "belege start")):
        roh = (wurzel / "Start Windows" / name).read_bytes()
        assert roh.count(b"\n") == roh.count(b"\r\n"), f"{name}: Zeilenenden müssen CRLF sein"
        text = roh.decode("utf-8")
        reihenfolge = ["if exist .venv goto eingerichtet", "Richte die neue Version ein", "uv sync --no-dev --quiet",
                       "playwright install --no-shell chromium", ":eingerichtet", befehl, ":selbstfehler",
                       "rmdir /s /q .venv"]
        stellen = [text.index(t) for t in reihenfolge]
        assert stellen == sorted(stellen), name
