"""Übernahme verwaister Konten (2.1.1) — mit genau der Dateiform, die beim Einrichten am
25.11.2026 entstanden ist: Konten mit ``name = ""`` und ohne ``kennung``, Profil und Protokoll
aber unter der früheren Kennung (``airbnb-airbnb``, ``protokolle/airbnb/airbnb.csv``).

Alle Daten sind erfunden; Adressen nur example.com.
"""

from __future__ import annotations

from datetime import date

import pytest

from belegabruf import ablauf, einstellungen, pfade
from belegabruf.protokoll import Protokoll
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


DATEI = """# Einstellungen für Belegabruf
belegordner = "{ordner}"
ablage = "jahr"
ziele = [{ziele}]
sichtbar = "nein"

[[konto]]
quelle = "airbnb"
name = ""
aktiv = "ja"

[[konto]]
quelle = "skool"
name = ""
aktiv = "ja"

[[konto]]
quelle = "xentra"
name = ""
aktiv = "ja"

[mail]
server = "smtp.example.com"
port = 465
verschluesselung = "ssl"
benutzer = "ich@example.com"
absender = "ich@example.com"
empfaenger = ["beleg@example.com"]
passwort_eintrag = "belegabruf/mail"
erstversand = "{erstversand}"
"""


def _beleg(quelle: str, nr: int, datum: date) -> Beleg:
    return Beleg(quelle=quelle, konto=quelle, art="rechnung", schluessel=f"rechnung:{quelle}-{nr}",
                 dateiname=f"{datum}_{quelle}_{nr}.pdf", inhalt=b"%PDF-1.4 test", jahr=datum.year,
                 rechnungsdatum=datum, rechnungsnummer=f"NR-{nr}")


def _alter_stand(tmp_path, mail=False, erstversand="nicht", profile=True, protokolle=True):
    """Wie bei Balazs am Abend des 25.11.: Datei ohne Kennungen, Rest unter den alten Namen."""
    daten = pfade.datenordner()
    datei = pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    ziele = '"ordner", "mail"' if mail else '"ordner"'
    datei.write_text(DATEI.format(ordner=tmp_path / "Belege", ziele=ziele, erstversand=erstversand), encoding="utf-8")
    for quelle in ("airbnb", "skool", "xentra"):
        if profile:
            (daten / "profile" / f"{quelle}-{quelle}").mkdir(parents=True)
        if protokolle:
            p = Protokoll(quelle, quelle, tmp_path / "Belege")
            for nr in (1, 2):
                p.eintragen(_beleg(quelle, nr, date(2026, 10, nr)), tmp_path / "Belege" / f"{quelle}-{nr}.pdf", ["ordner"])
            p.erstlauf_setzen("fertig")
    return datei


def test_balazs_dateiform_findet_alte_kennungen(tmp_path):
    datei = _alter_stand(tmp_path)
    vorher = datei.read_text(encoding="utf-8")
    einst = einstellungen.laden()
    assert [(k.quelle, k.name, k.uebernommen_von) for k in einst.konten] == [
        ("airbnb", "airbnb", "standard"), ("skool", "skool", "standard"), ("xentra", "xentra", "standard")]
    assert all(not k.auslassen_grund for k in einst.konten)
    assert datei.read_text(encoding="utf-8") == vorher  # Laden ändert die Datei nie
    # Profil und Protokoll sind wieder die alten — keine neuen leeren
    k = einst.konten[0]
    assert pfade.profilordner(k.quelle, k.name).name == "airbnb-airbnb"
    assert ablauf.protokoll_fuer(einst, k).datei.name == "airbnb.csv"
    assert not (pfade.datenordner() / "protokolle" / "airbnb" / "standard.csv").exists()


def test_beim_speichern_wird_die_kennung_festgeschrieben(tmp_path):
    datei = _alter_stand(tmp_path)
    einstellungen.speichern(einstellungen.laden())
    text = datei.read_text(encoding="utf-8")
    assert 'kennung = "airbnb"' in text and 'kennung = "skool"' in text and 'kennung = "xentra"' in text
    einst = einstellungen.laden()
    assert [k.name for k in einst.konten] == ["airbnb", "skool", "xentra"]
    assert all(not k.uebernommen_von for k in einst.konten)  # jetzt ganz normal


def test_speichern_ueber_die_oberflaeche_behaelt_die_uebernahme(tmp_path):
    from belegabruf.oberflaeche.aktionen import Steuerung, einstellungen_aus_eingaben

    _alter_stand(tmp_path)
    zustand = Steuerung().zustand()
    zeilen = [{"quelle": k["quelle"], "name": k["titel"], "kennung": k["name"]} for k in zustand["konten"]]
    neu = einstellungen_aus_eingaben({"belegordner": str(tmp_path / "Belege"), "konten": zeilen})
    assert [k.name for k in neu.konten] == ["airbnb", "skool", "xentra"]


class _Falsch(Quelle):
    """Liefert die zwei alten Rechnungen und eine neue."""

    name = "airbnb"
    anzeigename = "Airbnb"

    def sitzung_pruefen(self):
        return True

    def anmelden_lassen(self, melden):
        return True

    def belege_holen(self, umgebung):
        erg = Ergebnis(self.name, self.konto.name)
        for nr in (1, 2, 3):
            beleg = _beleg("airbnb", nr, date(2026, 11 if nr == 3 else 10, nr))
            if umgebung.bekannt(beleg.schluessel):
                erg.schon_da += 1
                continue
            umgebung.abliefern(beleg)
            erg.neu += 1
        return erg


@pytest.mark.parametrize("erstversand", ["nicht", "auch"])
def test_uebernahme_verschickt_nie_den_altbestand(tmp_path, monkeypatch, erstversand):
    """Auch mit „auch verschicken“ und neu eingeschaltetem Mail: Was im übernommenen Protokoll
    steht, gilt als verarbeitet. Nur die wirklich neue Rechnung ist für Mail offen."""
    _alter_stand(tmp_path, mail=True, erstversand=erstversand)
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: _Falsch(konto, tmp_path / "profil"))
    offen: list[list[str]] = []
    monkeypatch.setattr(ablauf, "liefern", lambda einst, protokoll, erg, melden, markiert=None, ziele=None:
                        offen.append(protokoll.offen_fuer("mail:beleg@example.com")))
    einst = einstellungen.laden()
    erg = ablauf.abrufen(einst, einst.konten[0], lambda t: None)
    assert erg.neu == 1 and erg.schon_da == 2
    assert offen == [["rechnung:airbnb-3"]]
    assert any("übernommen" in h and "2 Rechnung(en) daraus gelten als verschickt" in h for h in erg.hinweise)
    # Zweiter Lauf (noch nicht gespeichert): die Übernahme markiert nicht noch einmal — die neue
    # Rechnung bleibt offen, wenn ihr Versand z. B. gescheitert ist.
    erg = ablauf.abrufen(einstellungen.laden(), einstellungen.laden().konten[0], lambda t: None)
    assert offen[-1] == ["rechnung:airbnb-3"] and erg.neu == 0


def test_mehrere_waisen_nicht_raten_sondern_auslassen(tmp_path, monkeypatch):
    _alter_stand(tmp_path)
    Protokoll("airbnb", "zweites", tmp_path / "Belege").erstlauf_setzen("fertig")  # zweites altes Protokoll
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: pytest.fail("ausgelassenes Konto geöffnet"))
    einst = einstellungen.laden()
    airbnb = einst.konten[0]
    assert airbnb.name == "standard" and "airbnb, zweites" in airbnb.auslassen_grund
    # rät nie, eine fremde Kennung einzutragen — der Ausweg ist ein Name
    assert "kennung" not in airbnb.auslassen_grund and "Namen" in airbnb.auslassen_grund
    ergebnisse = ablauf.alle_abrufen(einst, [airbnb], lambda k: pytest.fail("angemeldet"), lambda k: print)
    assert ergebnisse[0].status == "fehler" and "nicht eindeutig" in ergebnisse[0].fehler
    assert ablauf.exit_code(ergebnisse) == 1
    assert not (pfade.datenordner() / "protokolle" / "airbnb" / "standard.csv").exists()
    # Skool und Xentra sind eindeutig und werden übernommen
    assert [k.name for k in einst.konten[1:]] == ["skool", "xentra"]


def test_konten_mit_namen_werden_nie_umgebogen(tmp_path):
    """M1: Nur ein Konto ohne Namen kann seine Kennung verloren haben. Konten mit Namen bleiben,
    wie sie sind — auch wenn ein altes Protokoll ohne Konto daliegt."""
    datei = _alter_stand(tmp_path)
    datei.write_text(datei.read_text(encoding="utf-8").replace(
        '[[konto]]\nquelle = "skool"', '[[konto]]\nquelle = "airbnb"\nname = "Zweitkonto"\n\n[[konto]]\nquelle = "skool"', 1)
        .replace('quelle = "airbnb"\nname = ""', 'quelle = "airbnb"\nname = "Erstkonto"', 1), encoding="utf-8")
    einst = einstellungen.laden()
    airbnb = [k for k in einst.konten if k.quelle == "airbnb"]
    assert [k.name for k in airbnb] == ["Erstkonto", "Zweitkonto"]
    assert all(not (k.uebernommen_von or k.auslassen_grund) for k in airbnb)


def test_nur_ein_altes_profil(tmp_path):
    """Ohne Protokoll, aber mit altem Profil: die Anmeldung wird übernommen."""
    _alter_stand(tmp_path, protokolle=False)
    einst = einstellungen.laden()
    assert [k.name for k in einst.konten] == ["airbnb", "skool", "xentra"]


def test_neu_eingerichtet_ohne_alte_daten_bleibt_standard(tmp_path):
    _alter_stand(tmp_path, profile=False, protokolle=False)
    einst = einstellungen.laden()
    assert [k.name for k in einst.konten] == ["standard"] * 3
    assert all(not (k.uebernommen_von or k.auslassen_grund) for k in einst.konten)


def test_schon_neu_angefangen_bleibt(tmp_path):
    """Hat das Konto schon ein eigenes Protokoll (vor 2.1.1 neu angefangen), wird nichts umgehängt
    und kein Dauerhinweis gezeigt (N1)."""
    _alter_stand(tmp_path)
    Protokoll("airbnb", "standard", tmp_path / "Belege").erstlauf_setzen("fertig")
    k = einstellungen.laden().konten[0]
    assert k.name == "standard" and not k.uebernommen_von and not k.auslassen_grund


def test_gewoehnliches_konto_bleibt_unberuehrt(tmp_path):
    datei = _alter_stand(tmp_path)
    datei.write_text(datei.read_text(encoding="utf-8").replace('name = ""', 'name = ""\nkennung = "airbnb"', 1),
                     encoding="utf-8")
    k = einstellungen.laden().konten[0]
    assert k.name == "airbnb" and not k.uebernommen_von


# ── (c) Nie über eine unlesbare Datei speichern ──────────────────────────────


def test_speichern_bei_unlesbarer_datei_abgelehnt(tmp_path):
    from belegabruf.oberflaeche.aktionen import Eingabefehler, einstellungen_aus_eingaben

    datei = _alter_stand(tmp_path)
    kaputt = datei.read_text(encoding="utf-8").replace('ablage = "jahr"', 'ablage = "quartal"')
    datei.write_text(kaputt, encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungNichtLesbar):
        einstellungen.laden()
    with pytest.raises(Eingabefehler) as fehler:
        einstellungen_aus_eingaben({"belegordner": str(tmp_path / "Belege"),
                                    "konten": [{"quelle": "airbnb", "name": ""}]})
    assert "nicht lesbar" in str(fehler.value) and "umbenennen" in str(fehler.value)
    assert datei.read_text(encoding="utf-8") == kaputt  # nichts überschrieben


def test_terminal_einrichtung_bei_unlesbarer_datei_abgelehnt(tmp_path):
    from belegabruf import einrichtung

    datei = _alter_stand(tmp_path)
    datei.write_text("das ist kein TOML = = =", encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler, match="nicht lesbar"):
        einrichtung.einrichten()


def test_erstes_einrichten_ohne_datei_geht_weiter(tmp_path):
    from belegabruf.oberflaeche.aktionen import einstellungen_aus_eingaben

    einst = einstellungen_aus_eingaben({"belegordner": str(tmp_path / "Belege"),
                                        "konten": [{"quelle": "airbnb", "name": ""}]})
    assert [k.name for k in einst.konten] == ["standard"]


# ── Nachbesserung nach der Prüfung (M1–M3, N2, N3) ──────────────────────────


def test_entferntes_konto_vererbt_nichts(tmp_path):
    """M1: „Ferienwohnung“ (anderer Airbnb-Zugang) wird entfernt, danach ein Konto neu angelegt —
    mit oder ohne Namen. Es bekommt nie Anmeldung und Protokoll des entfernten Kontos."""
    from belegabruf.einstellungen import Einstellungen, Konto

    ordner = tmp_path / "Belege"
    vorher = Einstellungen(belegordner=ordner, konten=[Konto("airbnb", "Ferienwohnung", titel="Ferienwohnung")])
    einstellungen.speichern(vorher)
    (pfade.datenordner() / "profile" / "airbnb-ferienwohnung").mkdir(parents=True)
    Protokoll("airbnb", "Ferienwohnung", ordner).erstlauf_setzen("fertig")
    # in der Oberfläche entfernt und ohne Namen neu angelegt
    einstellungen.speichern(Einstellungen(belegordner=ordner, konten=[Konto("airbnb", "standard", titel="")]))
    k = einstellungen.laden().konten[0]
    assert k.name == "standard" and not k.uebernommen_von and not k.auslassen_grund
    # … oder mit Namen
    einstellungen.speichern(Einstellungen(belegordner=ordner, konten=[Konto("airbnb", "Privat", titel="Privat")]))
    k = einstellungen.laden().konten[0]
    assert k.name == "Privat" and not k.uebernommen_von
    # Kommt „Ferienwohnung“ wieder, gehört ihm seine Anmeldung wieder
    einstellungen.speichern(Einstellungen(belegordner=ordner, konten=[Konto("airbnb", "Ferienwohnung",
                                                                            titel="Ferienwohnung")]))
    from belegabruf import zustand

    assert "airbnb/ferienwohnung" not in zustand.entfernt()


def test_ausdrueckliche_kennung_wird_nie_umgebogen(tmp_path):
    datei = _alter_stand(tmp_path)
    datei.write_text(datei.read_text(encoding="utf-8").replace('name = ""', 'name = ""\nkennung = "standard"', 1),
                     encoding="utf-8")
    k = einstellungen.laden().konten[0]
    assert k.name == "standard" and not k.uebernommen_von


def test_uebernahme_laesst_gescheiterte_mails_offen(tmp_path, monkeypatch):
    """M2: War Mail im alten Protokoll schon an und ist eine Rechnung beim Versand gescheitert,
    bleibt sie nach der Übernahme offen und geht beim nächsten Versuch raus."""
    _alter_stand(tmp_path, mail=True)
    alt = Protokoll("airbnb", "airbnb", tmp_path / "Belege")
    ziel = "mail:beleg@example.com"
    alt.schalten(ziel, True)
    alt.als_geliefert("rechnung:airbnb-1", ziel)  # Rechnung 2 bleibt offen (Versand gescheitert)
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: _Falsch(konto, tmp_path / "profil"))
    offen: list[list[str]] = []
    monkeypatch.setattr(ablauf, "liefern", lambda einst, protokoll, erg, melden, markiert=None, ziele=None:
                        offen.append(protokoll.offen_fuer(ziel)))
    einst = einstellungen.laden()
    erg = ablauf.abrufen(einst, einst.konten[0], lambda t: None)
    assert offen == [["rechnung:airbnb-2", "rechnung:airbnb-3"]]
    assert not any("gelten als verschickt" in h for h in erg.hinweise)


def test_oberflaeche_sagt_sofort_dass_die_datei_nicht_lesbar_ist(tmp_path, monkeypatch):
    """M3: zustand nennt den Grund (mit ~ statt Benutzerpfad, N2) und verspricht nicht „wird ersetzt“."""
    from belegabruf.oberflaeche.aktionen import Steuerung

    datei = _alter_stand(tmp_path)
    datei.write_text(datei.read_text(encoding="utf-8").replace('ablage = "jahr"', 'ablage = "quartal"'),
                     encoding="utf-8")
    monkeypatch.setattr(pfade.Path, "home", classmethod(lambda cls: tmp_path))
    z = Steuerung().zustand()
    assert "nicht lesbar" in z["nicht_lesbar"] and "quartal" in z["nicht_lesbar"]
    assert z["datei_fremd"] == [] and not z["eingerichtet"]
    assert str(tmp_path) not in z["nicht_lesbar"] and "~" in z["nicht_lesbar"]
    assert einstellungen.fremde_inhalte() == []


def test_seite_sperrt_speichern_bei_unlesbarer_datei():
    from importlib import resources

    seite = resources.files("belegabruf.oberflaeche").joinpath("seite.html").read_text(encoding="utf-8")
    assert 'id="nicht-lesbar"' in seite and "zustand.nicht_lesbar" in seite
    assert '$("speichern").disabled = Boolean(zustand && zustand.nicht_lesbar)' in seite


def test_airbnb_erlaubt_auch_airbnb_com():
    from belegabruf.einstellungen import Konto
    from belegabruf.quellen.airbnb import Airbnb

    assert Airbnb(Konto("airbnb", "a"), None)._hosts() == {"www.airbnb.de", "www.airbnb.com"}
