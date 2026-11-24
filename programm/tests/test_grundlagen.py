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
