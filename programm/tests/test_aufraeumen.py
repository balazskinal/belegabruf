"""Aufräumen 2.0.1: zusammengelegte Prüfregeln und die kleinen Korrekturen (N1, N5).

Alle Adressen sind erfunden (example.com)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from belegabruf import einstellungen, pfade
from belegabruf.einstellungen import Einstellungen, Konto, MailEinstellung


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


# ── N1: --konto trifft je Anbieter höchstens ein Konto ───────────────────────


def _einst(*konten):
    return Einstellungen(belegordner=pfade.standard_belegordner(), konten=list(konten))


def test_konto_ueber_kreuz_trifft_nur_eins():
    """„Privat“ wurde in „Geschäft“ umbenannt, „Geschäft“ in „Büro“: --konto Geschäft
    meint das Konto, das jetzt so heißt — nicht zusätzlich das mit der alten Kennung."""
    a = Konto("airbnb", "Privat", titel="Geschäft")
    b = Konto("airbnb", "Geschäft", titel="Büro")
    einst = _einst(a, b)
    assert einst.aktive_konten(konto="Geschäft") == [a]
    assert einst.aktive_konten(konto="Büro") == [b]
    assert einst.aktive_konten(konto="Privat") == [a]  # alte Kennung geht weiter, wenn kein Name passt


def test_konto_gleicher_name_bei_zwei_anbietern_bleibt_moeglich():
    a = Konto("airbnb", "Privat")
    s = Konto("skool", "Privat")
    assert _einst(a, s).aktive_konten(konto="Privat") == [a, s]
    assert _einst(a, s).aktive_konten("skool", "Privat") == [s]


def test_konto_ausgeschaltet_wird_nicht_getroffen():
    a = Konto("airbnb", "Privat", titel="Geschäft", aktiv=False)
    b = Konto("airbnb", "Geschäft", titel="Büro")
    assert _einst(a, b).aktive_konten(konto="Geschäft") == [b]  # nur eingeschaltete zählen


# ── eine Regel für Mailadressen ──────────────────────────────────────────────


@pytest.mark.parametrize("adresse, ok", [
    ("beleg@example.com", True),
    ("vorname.name+belege@mail.example.com", True),
    ("keine-adresse", False),
    ("@example.com", False),
    ("beleg@", False),
    ("beleg@example", False),
    ("beleg@.com", False),
    ("a@b@example.com", False),
    ("beleg @example.com", False),
    ("a@example.com,b@example.com", False),
])
def test_mailadresse_ok(adresse, ok):
    assert einstellungen.mailadresse_ok(adresse) is ok


def test_neue_eingaben_pruefen_streng(tmp_path):
    """Formular und Terminal-Einrichtung nehmen nur name@domain.tld an."""
    from belegabruf.oberflaeche.aktionen import Eingabefehler, einstellungen_aus_eingaben

    for adresse in ("@example.com", "beleg@example"):
        with pytest.raises(Eingabefehler) as fehler:
            einstellungen_aus_eingaben({"belegordner": str(tmp_path / "B"), "konten": [],
                                        "mail": {"empfaenger": [adresse]}})
        assert "keine Mailadresse" in fehler.value.felder["empfaenger"]


DATEI_2_0_0 = """# Einstellungen für Belegabruf
belegordner = '{ordner}'
ablage = "jahr"

[[konto]]
quelle = "airbnb"
name = "Privat"
belege_ab = "alle"

[mail]
server = "smtp.example.com"
port = 465
verschluesselung = "ssl"
benutzer = "x@y"
absender = "x@y"
empfaenger = ["x@y", "beleg@example.com"]
erstversand = "nicht"
"""


@pytest.mark.parametrize("ziele", ['ziele = ["ordner"]\n', 'ziele = ["ordner", "mail"]\n'])
def test_datei_aus_2_0_0_mit_milder_adresse_laedt_weiter(tmp_path, ziele):
    """Eine Datei aus 2.0.0 mit „x@y“ (ohne Punkt) muss lesbar bleiben — mit Mail aus und an.
    Sonst zeigte die Oberfläche „nicht eingerichtet“, und neues Einrichten gäbe neue Kennungen."""
    datei = pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(ziele + DATEI_2_0_0.format(ordner=tmp_path / "Belege"), encoding="utf-8")
    einst = einstellungen.laden()
    assert [k.name for k in einst.konten] == ["Privat"]
    assert einst.mail.empfaenger == ["x@y", "beleg@example.com"] and einst.mail.absender == "x@y"
    assert einstellungen.pruefen(einst).mail.absender == "x@y"  # auch das Zurückschreiben geht


def test_datei_ohne_at_wird_weiter_abgelehnt():
    with pytest.raises(einstellungen.EinstellungsFehler, match="keine Mailadresse"):
        einstellungen.aus_text('[mail]\nempfaenger = ["keine-adresse"]\n')


def test_oberflaeche_zeigt_konten_einer_datei_aus_2_0_0(tmp_path):
    from belegabruf.oberflaeche.aktionen import Steuerung

    datei = pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text('ziele = ["ordner"]\n' + DATEI_2_0_0.format(ordner=tmp_path / "Belege"), encoding="utf-8")
    zustand = Steuerung().zustand()
    assert zustand["eingerichtet"] and [k["name"] for k in zustand["konten"]] == ["Privat"]


# ── eine Regel für Kontonamen ────────────────────────────────────────────────


def test_fehlender_name_und_verwechslung_zugleich():
    """N2: Fehlt bei einem Konto der Name, werden die übrigen trotzdem auf Verwechslung geprüft."""
    konten = [Konto("airbnb", "standard", titel=""), Konto("airbnb", "Privat", titel="Privat"),
              Konto("airbnb", "privat!", titel="privat!")]
    fehler = dict(einstellungen.kontonamen_fehler(konten))
    assert set(fehler) == {0, 2}
    assert "braucht jedes einen Namen" in fehler[0] and "dasselbe" in fehler[2]
    with pytest.raises(einstellungen.EinstellungsFehler, match="braucht jedes einen Namen"):
        einstellungen.konten_unterscheidbar(konten)  # die erste Meldung bleibt der fehlende Name


def test_kontonamen_fehler_nennt_jedes_betroffene_konto():
    konten = [Konto("airbnb", "standard", titel=""), Konto("airbnb", "b", titel="B"),
              Konto("skool", "x", titel="X"), Konto("skool", "x!", titel="x!")]
    fehler = dict(einstellungen.kontonamen_fehler(konten))
    assert set(fehler) == {0, 3}
    assert "braucht jedes einen Namen" in fehler[0] and "dasselbe" in fehler[3]
    with pytest.raises(einstellungen.EinstellungsFehler, match="braucht jedes einen Namen"):
        einstellungen.konten_unterscheidbar(konten)


def test_formular_markiert_namen_nach_derselben_regel(tmp_path):
    from belegabruf.oberflaeche.aktionen import Eingabefehler, einstellungen_aus_eingaben

    with pytest.raises(Eingabefehler) as fehler:
        einstellungen_aus_eingaben({"belegordner": str(tmp_path / "B"), "konten": [
            {"quelle": "nirgendwo", "name": "a"},  # Zeile 0 fällt weg, die Nummern bleiben richtig
            {"quelle": "airbnb", "name": "Privat"},
            {"quelle": "airbnb", "name": "privat!"},
        ]})
    felder = fehler.value.felder
    assert "konto-0-quelle" in felder and "konto-2-name" in felder and "konto-1-name" not in felder


def test_schluessel_eines_kontos():
    assert Konto("airbnb", "privat").schluessel == "airbnb/privat"


# ── Terminal-Einrichtung behält „Erster Versand“ ─────────────────────────────


def test_einrichtung_behaelt_erstversand(monkeypatch):
    import builtins

    from belegabruf import einrichtung
    from belegabruf.ziele import mail

    alt = Einstellungen(belegordner=pfade.standard_belegordner(), konten=[], ziele=["ordner", "mail"],
                        mail=MailEinstellung(server="smtp.example.com", benutzer="ich@example.com",
                                             absender="ich@example.com", empfaenger=["beleg@example.com"],
                                             erstversand="auch"))
    monkeypatch.setattr(builtins, "input", lambda text="": "")  # überall Enter = so lassen
    monkeypatch.setattr(mail, "passwort_vorhanden", lambda dienst, konto: True)
    monkeypatch.setattr(mail, "passwort_lesen", lambda dienst, konto: "platzhalter")
    monkeypatch.setattr(mail, "anmeldung_pruefen", lambda einst, passwort: None)
    mail_an, neu = einrichtung._mail_abfragen(alt)
    assert mail_an and neu.erstversand == "auch" and neu.empfaenger == ["beleg@example.com"]


# ── N5: Monatsordner nur mit Datum ───────────────────────────────────────────


def _beleg(datum, jahr):
    from belegabruf.quellen.basis import Beleg

    return Beleg(quelle="airbnb", konto="a", schluessel="rechnung:x", art="rechnung", dateiname="x.pdf",
                 inhalt=b"%PDF-1.4", jahr=jahr, rechnungsdatum=datum)


def test_monatsordner_nach_rechnungsdatum(tmp_path):
    from belegabruf.ziele.ordner import Ordner

    ziel = Ordner(tmp_path, ablage="monat")
    assert ziel.abliefern(_beleg(date(2025, 3, 9), 2025)) == tmp_path / "airbnb" / "2025" / "03" / "x.pdf"


def test_ohne_datum_aus_frueherem_jahr_kein_falscher_monat(tmp_path):
    """Ohne Rechnungsdatum ist der Monat unbekannt. Aus einem früheren Jahr kommt der Beleg
    in den Jahresordner — nicht in den heutigen Monat jenes Jahres."""
    from belegabruf.ziele.ordner import Ordner

    ziel = Ordner(tmp_path, ablage="monat")
    assert ziel.abliefern(_beleg(None, 2024)) == tmp_path / "airbnb" / "2024" / "x.pdf"
    heute = date.today()
    assert ziel.abliefern(_beleg(None, heute.year)) == (
        tmp_path / "airbnb" / str(heute.year) / f"{heute.month:02d}" / "x.pdf")  # wie bisher


# ── eine Abruf-Schleife für Terminal, „belege holen“ und Oberfläche ──────────


def test_alle_abrufen_laesst_nicht_angemeldete_aus(monkeypatch):
    from belegabruf import ablauf
    from belegabruf.quellen.basis import Ergebnis

    a, b = Konto("airbnb", "a", titel="A"), Konto("airbnb", "b", titel="B")
    geholt = []

    def abrufen(einst, konto, melden, nachholen=False):
        geholt.append((konto.name, nachholen))
        melden("los")
        return Ergebnis(konto.quelle, konto.name)

    monkeypatch.setattr(ablauf, "abrufen", abrufen)
    meldungen = []
    ergebnisse = ablauf.alle_abrufen(_einst(a, b), [a, b], lambda k: k is b,
                                     lambda k: lambda t: meldungen.append(f"{k.name}: {t}"), nachholen=True)
    assert [e.status for e in ergebnisse] == ["anmeldung_noetig", "ok"]
    assert ergebnisse[0].anzeige == "Airbnb (A)"
    assert geholt == [("b", True)] and meldungen == ["b: los"]
    assert ablauf.exit_code(ergebnisse) == 2


def test_belege_ab_sagt_dass_nachgeholtes_verschickt_wird():
    """H1: Text und Infobox zu „Belege ab“ nennen den Versand beim Erweitern des Zeitraums."""
    from importlib import resources

    seite = resources.files("belegabruf.oberflaeche").joinpath("seite.html").read_text(encoding="utf-8")
    info = seite[seite.index("  belege_ab: "):].split("\n\n")[0]
    assert "nachgeholten Belege auch verschickt" in info.replace('" + "', "").replace("\n    + \"", "")
    absatz = seite[seite.index("„Belege ab“: ältere Belege"):].split("</p>")[0]
    assert "auch verschickt" in absatz


def test_texte_nennen_den_starter_beim_namen(monkeypatch):
    """Nach dem Umzug heißt der Starter „Belegabruf Mac“ bzw. „Belegabruf Windows“ — so steht
    es auch in den Hinweisen (wieder öffnen, Browser fehlt, Update)."""
    echt = pfade.sys.platform
    monkeypatch.setattr(pfade.sys, "platform", "darwin")
    assert pfade.starter() == "Belegabruf Mac"
    monkeypatch.setattr(pfade.sys, "platform", "win32")
    assert pfade.starter() == "Belegabruf Windows"
    monkeypatch.setattr(pfade.sys, "platform", echt)  # nicht mit vorgetäuschtem Windows weitermachen
    # Seit 2.2.0 nennt der Update-Hinweis der Seite die Zeile für Terminal bzw. PowerShell.
    seite = (Path(pfade.__file__).parent / "oberflaeche" / "seite.html").read_text(encoding="utf-8")
    assert "Update mit einer Zeile ${zustand.update_wo}: ${zustand.update_zeile}" in seite
