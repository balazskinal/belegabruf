"""Tests ohne Browser und ohne echte Belege (alle Beispieldaten sind erfunden)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pymupdf
import pytest

from belegabruf import ablauf, aktualisierung, einstellungen, pfade, pruefung, quellen, zustand
from belegabruf import protokoll as protokoll_modul
from belegabruf.einstellungen import Einstellungen, Konto
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
        if datei.suffix not in {".py", ".md", ".toml", ".yml", ".command", ".cmd", ".txt", ".sh", ".ps1", ".html", ""}:
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


# ── Ein Starter je System: richtet sich selbst ein, jeder Schritt nur, wenn nötig ──


WURZEL = Path(__file__).resolve().parents[2]


MAC = "Belegabruf Mac.command"
MAC_TERMINAL = "Fehlersuche/Belegabruf Terminal Mac.command"
WIN = "Belegabruf Windows.cmd"
WIN_TERMINAL = "Fehlersuche/Belegabruf Terminal Windows.cmd"


def _starter_kopie(tmp_path):
    """Baut den ausgepackten Ordner nach (wie im ZIP), absichtlich in einem Pfad mit Leerzeichen."""
    import shutil

    ziel = tmp_path / "Mein Ordner" / "belegabruf-v2"
    (ziel / "Fehlersuche").mkdir(parents=True)
    for name in (MAC, MAC_TERMINAL):
        shutil.copy2(WURZEL / name, ziel / name)
    (ziel / "programm").mkdir()
    (ziel / "programm" / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    return ziel


def _falsches_uv(tmp_path, sync_klappt=True):
    """Ein „uv“, das nur mitschreibt. „uv sync“ legt eine .venv mit einem falschen Python
    an, das die Startprüfung nach Dateien beantwortet (browser-da / umgebung-alt)."""
    log = tmp_path / "aufrufe.log"
    uv = tmp_path / "bin" / "uv"
    uv.write_text(
        "#!/bin/bash\n"
        f'echo "uv $*" >> "{log}"\n'
        'if [ "$1" = sync ]; then\n'
        + ("  exit 1\n" if not sync_klappt else
           "  mkdir -p .venv/bin\n"
           "  printf '%s\\n' '#!/bin/bash' "
           f"'echo \"python $*\" >> \"{log}\"' "
           f"'if [ \"$3\" = browser ]; then [ -e \"{tmp_path}/browser-da\" ]; exit $?; fi' "
           "'[ -e .venv/.belegabruf-sync ] && ! [ uv.lock -nt .venv/.belegabruf-sync ]' > .venv/bin/python\n"
           "  chmod +x .venv/bin/python\n")
        + "fi\n"
        'if [ "$*" = "run --locked --no-dev --quiet playwright install --no-shell chromium" ]; then '
        f'touch "{tmp_path}/browser-da"; fi\n'
        "exit 0\n", encoding="utf-8")
    uv.chmod(0o755)
    return log


def _starten(tmp_path, ordner=None, datei=MAC, mit_uv=True):
    import subprocess

    ordner = ordner or tmp_path / "Mein Ordner" / "belegabruf-v2"
    pfad = f"{tmp_path / 'bin'}:/usr/bin:/bin" if mit_uv else "/usr/bin:/bin"
    return subprocess.run(["/bin/bash", str(ordner / datei)], input="\n", capture_output=True, text=True,
                          env={"PATH": pfad, "HOME": str(tmp_path / "home")}, timeout=30)


def _aufrufe(log):
    zeilen = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    log.unlink(missing_ok=True)
    return [z for z in zeilen if not z.startswith("python")]


pytestmark_mac = pytest.mark.skipif(__import__("sys").platform == "win32", reason="Mac-Starter")


@pytestmark_mac
def test_starter_erststart_dann_nur_noch_starten(tmp_path):
    import time

    ordner = _starter_kopie(tmp_path)
    log = _falsches_uv(tmp_path)
    lauf = _starten(tmp_path)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert "Richte die neue Version ein" in lauf.stdout and "Hole den Browser" in lauf.stdout
    assert _aufrufe(log) == ["uv sync --locked --no-dev --quiet", "uv run --locked --no-dev --quiet playwright install --no-shell chromium",
                             "uv run --locked --no-dev --quiet belege oberflaeche"]
    # zweiter Start: alles da → nur das Fenster
    lauf = _starten(tmp_path)
    assert "Richte" not in lauf.stdout and "Hole" not in lauf.stdout
    assert _aufrufe(log) == ["uv run --locked --no-dev --quiet belege oberflaeche"]
    # Update im Arbeitsordner: uv.lock neuer → nur Bausteine, Browser ist schon da
    time.sleep(1.1)
    (ordner / "programm" / "uv.lock").write_text("neu", encoding="utf-8")
    lauf = _starten(tmp_path)
    assert _aufrufe(log) == ["uv sync --locked --no-dev --quiet", "uv run --locked --no-dev --quiet belege oberflaeche"]
    # Browser weg (z. B. Cache geleert) → nur der Browser
    (tmp_path / "browser-da").unlink()
    _starten(tmp_path)
    assert _aufrufe(log) == ["uv run --locked --no-dev --quiet playwright install --no-shell chromium",
                             "uv run --locked --no-dev --quiet belege oberflaeche"]


@pytestmark_mac
def test_starter_halbe_einrichtung_wird_weggeraeumt(tmp_path):
    ordner = _starter_kopie(tmp_path)
    log = _falsches_uv(tmp_path, sync_klappt=False)
    lauf = _starten(tmp_path)
    assert lauf.returncode == 1 and "noch einmal doppelklicken" in lauf.stdout
    assert not (ordner / "programm" / ".venv").exists()
    assert not any("belege" in a for a in _aufrufe(log))


@pytestmark_mac
def test_starter_holt_uv_wenn_es_fehlt(tmp_path):
    """Ohne uv lädt der Starter es (hier: „curl“ als Attrappe, die ein falsches uv anlegt)."""
    _starter_kopie(tmp_path)
    log = _falsches_uv(tmp_path)
    versteck = tmp_path / "versteck"
    versteck.mkdir()
    (tmp_path / "bin" / "uv").rename(versteck / "uv")
    curl = tmp_path / "bin" / "curl"
    curl.write_text("#!/bin/bash\n"
                    f'echo "curl $*" >> "{log}"\n'
                    'echo "mkdir -p \\"$HOME/.local/bin\\"; cp \\"' + str(versteck / "uv") + '\\" \\"$HOME/.local/bin/uv\\""\n',
                    encoding="utf-8")
    curl.chmod(0o755)
    lauf = _starten(tmp_path)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    aufrufe = _aufrufe(log)
    assert aufrufe[0] == "curl -LsSf https://astral.sh/uv/install.sh" and "Hole das Hilfsprogramm uv" in lauf.stdout
    assert aufrufe[-1] == "uv run --locked --no-dev --quiet belege oberflaeche"


@pytestmark_mac
def test_terminal_starter_liegt_in_fehlersuche(tmp_path):
    ordner = _starter_kopie(tmp_path)
    log = _falsches_uv(tmp_path)
    lauf = _starten(tmp_path, datei=MAC_TERMINAL)
    assert lauf.returncode == 1 and "Belegabruf Mac" in lauf.stdout  # erst den Starter
    _starten(tmp_path)
    _aufrufe(log)
    lauf = _starten(tmp_path, datei=MAC_TERMINAL)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert _aufrufe(log) == ["uv run --locked --no-dev --quiet belege start"]
    assert (ordner / "programm" / ".venv").exists()


def test_oben_liegen_nur_die_zwei_starter():
    """Im Repo wie im ZIP: oben die zwei Starter, die Terminal-Starter in Fehlersuche/."""
    oben = sorted(p.name for p in WURZEL.iterdir() if p.suffix in {".command", ".cmd"})
    assert oben == [MAC, WIN], oben
    assert sorted(p.name for p in (WURZEL / "Fehlersuche").iterdir()) == [
        "Belegabruf Terminal Mac.command", "Belegabruf Terminal Windows.cmd"]
    assert not (WURZEL / "Start Mac").exists() and not (WURZEL / "Start Windows").exists()


def test_mac_starter_sind_ausfuehrbar():
    import os

    for name in (MAC, MAC_TERMINAL):
        assert os.access(WURZEL / name, os.X_OK), name


def test_windows_starter_ablauf_und_crlf():
    for name in (WIN, WIN_TERMINAL):
        roh = (WURZEL / name).read_bytes()
        assert roh.count(b"\n") == roh.count(b"\r\n"), f"{name}: Zeilenenden müssen CRLF sein"
    text = (WURZEL / WIN).read_text(encoding="utf-8")
    reihenfolge = ["where uv", "astral.sh/uv/install.ps1", ":uvda", "startpruefung umgebung", ":sync",
                   "uv sync --locked --no-dev --quiet", ".belegabruf-sync", ":browser", "startpruefung browser",
                   "playwright install --no-shell chromium", ":start", "belege oberflaeche", ":syncfehler",
                   "rmdir /s /q .venv"]
    stellen = [text.index(t) for t in reihenfolge]
    assert stellen == sorted(stellen)
    assert 'cd /d "%~dp0programm"' in text
    assert 'cd /d "%~dp0..\\programm"' in (WURZEL / WIN_TERMINAL).read_text(encoding="utf-8")


def test_alle_starter_laufen_mit_locked():
    """Jeder Aufruf von uv sync/run in den Startern ist --locked (nie eine andere Version als uv.lock)."""
    import re

    for name in (MAC, MAC_TERMINAL, WIN, WIN_TERMINAL):
        text = (WURZEL / name).read_text(encoding="utf-8")
        aufrufe = re.findall(r"^\s*(?:if ! )?uv (?:run|sync)[^\n]*", text, re.M)
        assert aufrufe, name
        for aufruf in aufrufe:
            assert "--locked" in aufruf, f"{name}: {aufruf}"


def test_startpruefung_umgebung(tmp_path):
    import os
    import time

    from belegabruf import startpruefung

    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    assert not startpruefung.umgebung_aktuell(tmp_path)  # keine .venv
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / startpruefung.MERKER).write_text("", encoding="utf-8")
    assert startpruefung.umgebung_aktuell(tmp_path)
    spaeter = time.time() + 10
    os.utime(tmp_path / "uv.lock", (spaeter, spaeter))
    assert not startpruefung.umgebung_aktuell(tmp_path)


def test_startpruefung_browser(tmp_path, monkeypatch):
    from belegabruf import startpruefung

    revision = startpruefung.chromium_revision()
    assert revision and revision.isdigit()  # liest die browsers.json des installierten Playwright
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert not startpruefung.chromium_da()
    (tmp_path / f"chromium-{revision}").mkdir()
    assert not startpruefung.chromium_da()  # halb geladen zählt nicht
    (tmp_path / f"chromium-{revision}" / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
    assert startpruefung.chromium_da()
    assert not (tmp_path / f"chromium-headless-shell-{revision}").exists()


@pytestmark_mac
@pytest.mark.parametrize("datei", [MAC, MAC_TERMINAL])
def test_starter_ohne_programmordner_meldet_sich(tmp_path, datei):
    import shutil

    (tmp_path / "Fehlersuche").mkdir()
    shutil.copy2(WURZEL / datei, tmp_path / datei)  # nur der Starter herausgezogen, ohne „programm“
    lauf = _starten(tmp_path, ordner=tmp_path, datei=datei, mit_uv=False)
    assert lauf.returncode == 1 and "Ordner „programm“ fehlt" in lauf.stdout and "vollständig auspacken" in lauf.stdout


def test_starter_holt_uv_nur_von_fester_adresse():
    import re

    mac = (WURZEL / MAC).read_text(encoding="utf-8")
    win = (WURZEL / WIN).read_text(encoding="utf-8")
    assert re.findall(r"curl [^|]*\|", mac) == ["curl -LsSf https://astral.sh/uv/install.sh |"]
    assert 'irm https://astral.sh/uv/install.ps1 | iex' in win
    for text in (mac, win):
        zeile = next(z for z in text.splitlines() if "astral.sh/uv/install" in z and ("curl" in z or "irm" in z))
        assert "$" not in zeile.split("astral.sh")[0] and "%" not in zeile, zeile  # keine Variablen in der Adresse
    for name in (WIN, WIN_TERMINAL):
        text = (WURZEL / name).read_text(encoding="utf-8")
        assert '2>nul || (' in text and 'Der Ordner "programm" fehlt neben' in text
    assert "uv sync --locked --no-dev" in win and "uv sync --locked --no-dev" in mac


def test_startpruefung_erkennt_falsche_python_version(tmp_path):
    """2.2.1: Eine .venv mit anderem Python als .python-version (z. B. halb eingerichtet mit 3.15)
    gilt als nicht eingerichtet — der Starter ruft dann uv sync, das die .venv neu aufbaut."""
    from belegabruf import startpruefung

    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / startpruefung.MERKER).write_text("", encoding="utf-8")
    for cfg, passt in (("version_info = 3.12\n", True), ("version_info = 3.12.13\n", True),
                       ("version = 3.12.8\n", True), ("version_info = 3.15.0\n", False),
                       ("version_info = 3.1\n", False), ("", False)):
        (venv / "pyvenv.cfg").write_text("home = /x\n" + cfg, encoding="utf-8")
        assert startpruefung.umgebung_aktuell(tmp_path) is passt, cfg
    (venv / "pyvenv.cfg").unlink()
    assert not startpruefung.umgebung_aktuell(tmp_path)  # unbekannt: lieber neu einrichten
    (tmp_path / ".python-version").unlink()
    assert startpruefung.umgebung_aktuell(tmp_path)  # ohne .python-version wie bisher


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="baut das ZIP mit bash und zip")
def test_python_version_landet_im_zip(tmp_path):
    """Der Schritt „ZIP bauen“ aus release.yml, genau so ausgeführt: programm/.python-version
    ist im ZIP (sonst richtet der Starter wieder irgendeine Python-Version ein)."""
    import re
    import shutil
    import subprocess
    import zipfile

    if not shutil.which("zip"):
        pytest.skip("zip fehlt")
    workflow = (WURZEL / ".github/workflows/release.yml").read_text(encoding="utf-8")
    schritt = re.search(r"- name: ZIP bauen\n\s+run: \|\n((?:\s{10}.*\n|\n)+?)\n\s+- name:", workflow)
    assert schritt, "Schritt „ZIP bauen“ nicht gefunden"
    befehle = "\n".join(z[10:] for z in schritt.group(1).splitlines())
    quelle = tmp_path / "quelle"
    shutil.copytree(WURZEL, quelle, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "dist",
                                                                  ".pytest_cache", ".ruff_cache"))
    lauf = subprocess.run(["bash", "-e", "-c", befehle], cwd=quelle, capture_output=True, text=True,
                          env={**__import__("os").environ, "GITHUB_REF_NAME": "v9.9.9"}, timeout=120)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    with zipfile.ZipFile(quelle / "dist" / "belegabruf.zip") as z:
        namen = z.namelist()
    assert "belegabruf-v9.9.9/programm/.python-version" in namen
    with zipfile.ZipFile(quelle / "dist" / "belegabruf.zip") as z:
        assert z.read("belegabruf-v9.9.9/programm/.python-version").decode().strip() == "3.12"


@pytest.mark.parametrize("inhalt, erwartet", [
    ("3.12\n", (3, 12)),
    ("3.12.7\n", (3, 12)),
    ("cpython-3.12\n", (3, 12)),
    ("cpython-3.12.7-macos-aarch64-none\n", (3, 12)),
    ("cpython@3.12\n", (3, 12)),
    ("# Kommentar\n\n  3.13  \n", (3, 13)),
    ("pypy\n", None),
    ("", None),
])
def test_python_version_robust_gelesen(inhalt, erwartet):
    from belegabruf import startpruefung

    assert startpruefung.gewollte_python(inhalt) == erwartet


@pytest.mark.parametrize("datei", ["3.12.7\n", "cpython-3.12\n", "# fest\n3.12\n"])
def test_kein_neues_einrichten_bei_anderer_schreibweise(tmp_path, datei):
    """Mit „3.12.7“ oder „cpython-3.12“ und einer .venv mit 3.12 nicht bei jedem Start neu."""
    from belegabruf import startpruefung

    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".python-version").write_text(datei, encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / startpruefung.MERKER).write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("version_info = 3.12\n", encoding="utf-8")
    assert startpruefung.umgebung_aktuell(tmp_path)
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("version_info = 3.15.0\n", encoding="utf-8")
    assert not startpruefung.umgebung_aktuell(tmp_path)
