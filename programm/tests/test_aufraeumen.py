"""Aufräumen 2.0.1: zusammengelegte Prüfregeln und die kleinen Korrekturen (N1, N5).

Alle Adressen sind erfunden (example.com)."""

from __future__ import annotations

from datetime import date

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


def test_mailadresse_gleiche_regel_in_datei_und_oberflaeche(tmp_path):
    """Datei und Formular lehnen dieselben Adressen ab (früher prüften sie verschieden)."""
    from belegabruf.oberflaeche.aktionen import Eingabefehler, einstellungen_aus_eingaben

    for adresse in ("@example.com", "beleg@example"):
        with pytest.raises(einstellungen.EinstellungsFehler, match="keine Mailadresse"):
            einstellungen.aus_text(f'[mail]\nempfaenger = ["{adresse}"]\n')
        with pytest.raises(Eingabefehler) as fehler:
            einstellungen_aus_eingaben({"belegordner": str(tmp_path / "B"), "konten": [],
                                        "mail": {"empfaenger": [adresse]}})
        assert "keine Mailadresse" in fehler.value.felder["empfaenger"]


# ── eine Regel für Kontonamen ────────────────────────────────────────────────


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
