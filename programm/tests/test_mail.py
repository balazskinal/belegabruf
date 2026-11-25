"""Ziel mail — nur gegen einen gefälschten Mailserver, nie echter Versand.

Alle Adressen sind erfunden (example.com), das "Passwort" ist ein Platzhalter.
"""

from __future__ import annotations

import email
import smtplib
from datetime import date
from email import policy
from pathlib import Path

import pytest

from belegabruf import ablauf, einstellungen, pfade
from belegabruf.einstellungen import Einstellungen, Konto, MailEinstellung
from belegabruf.protokoll import Protokoll
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle
from belegabruf.ziele import mail

PLATZHALTER = "test-passwort-0000"
A = "beleg@example.com"
B = "steuer@example.com"


@pytest.fixture(autouse=True)
def datenordner(tmp_path, monkeypatch):
    monkeypatch.setenv("BELEGABRUF_DATEN", str(tmp_path / "daten"))
    yield tmp_path / "daten"
    # Sicherung: Kein Test darf je den echten Datenordner benutzt haben.
    assert str(pfade.datenordner()).startswith(str(tmp_path)), "Test lief gegen den echten Datenordner"


class Server:
    """Gemeinsamer Zustand des gefälschten Mailservers."""

    def __init__(self):
        self.mails: list[tuple[str, str, bytes]] = []  # (absender, empfänger, rumpf)
        self.befehle: list[str] = []
        self.verhalten = "ok"  # ok | kein_netz | anmeldung | empfaenger | data_ablehnen | keine_antwort | kein_tls
        self.abgelehnte_empfaenger: set[str] = set()


class FalschesSMTP:
    """Spricht wie smtplib.SMTP, ohne Netz."""

    server: Server

    def __init__(self, host, port, timeout=None, context=None):
        s = self.server
        s.befehle.append(f"verbinden {host}:{port} {type(self).__name__}")
        if s.verhalten == "kein_netz":
            raise ConnectionRefusedError("Connection refused")
        self._von = ""
        self._an = ""

    def ehlo(self):
        self.server.befehle.append("ehlo")
        return 250, b"ok"

    def starttls(self, context=None):
        if self.server.verhalten == "kein_tls":
            raise smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")
        self.server.befehle.append("starttls")
        return 220, b"ready"

    def login(self, benutzer, passwort):
        self.server.befehle.append(f"login {benutzer}")
        assert passwort == PLATZHALTER
        if self.server.verhalten == "anmeldung":
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication credentials invalid")
        return 235, b"ok"

    def mail(self, von):
        self.server.befehle.append("mail")
        self._von = von
        return 250, b"ok"

    def rcpt(self, an):
        self.server.befehle.append("rcpt")
        if self.server.verhalten == "empfaenger" or an in self.server.abgelehnte_empfaenger:
            return 550, b"5.1.1 user unknown"
        self._an = an
        return 250, b"ok"

    def data(self, rumpf):
        self.server.befehle.append("data")
        v = self.server.verhalten
        if v == "data_ablehnen":
            raise smtplib.SMTPDataError(552, b"5.3.4 message too big")
        if v == "keine_antwort":
            self.server.mails.append((self._von, self._an, rumpf))  # kam an, Antwort fehlt
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        self.server.mails.append((self._von, self._an, rumpf))
        return 250, b"queued"

    def rset(self):
        self.server.befehle.append("rset")

    def quit(self):
        self.server.befehle.append("quit")

    def close(self):
        self.server.befehle.append("close")


class FalschesSMTP_SSL(FalschesSMTP):
    pass


@pytest.fixture
def server(monkeypatch):
    s = Server()
    FalschesSMTP.server = s
    monkeypatch.setattr(mail.smtplib, "SMTP", FalschesSMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FalschesSMTP_SSL)
    monkeypatch.setattr(mail, "passwort_lesen", lambda dienst, konto: PLATZHALTER)
    monkeypatch.setattr(ablauf, "quelle_fuer", lambda konto: Falsch(konto, Path("/gibt-es-nicht")))
    monkeypatch.setattr(ablauf.zustand, "lauf_merken", lambda *a: None)
    return s


def _pdf(text: str) -> bytes:
    import pymupdf

    dok = pymupdf.open()
    dok.new_page().insert_text((50, 100), text)
    inhalt = dok.tobytes()
    dok.close()
    return inhalt


class Falsch(Quelle):
    """Quelle ohne Browser: liefert vorgegebene Rechnungen."""

    name = "airbnb"
    anzeigename = "Airbnb"
    rechnungen: list = []  # (kennung, datum, nummer)

    def sitzung_pruefen(self):
        return True

    def anmelden_lassen(self, melden):
        return True

    def belege_holen(self, umgebung):
        erg = Ergebnis(self.name, self.konto.name)
        for kennung, datum, nummer in self.rechnungen:
            schluessel = f"rechnung:{kennung}"
            if umgebung.bekannt(schluessel):
                erg.schon_da += 1
                continue
            gutschrift = kennung.startswith("g")
            umgebung.abliefern(Beleg(
                quelle="airbnb", konto=self.konto.name, art="rechnung", schluessel=schluessel,
                dateiname=f"{datum}_HMX_{nummer}{'_Gutschrift' if gutschrift else ''}.pdf",
                inhalt=_pdf(nummer), jahr=int(datum[:4]),
                rechnungsdatum=date.fromisoformat(datum), rechnungsnummer=nummer,
            ))
            erg.neu += 1
        return erg


def _einst(tmp_path: Path, empfaenger=(A,), an=True, verschluesselung="ssl") -> Einstellungen:
    return Einstellungen(
        belegordner=tmp_path / "Belege",
        konten=[Konto("airbnb", "privat")],
        ziele=["ordner", "mail"] if an else ["ordner"],
        mail=MailEinstellung(server="smtp.example.com", port=465 if verschluesselung == "ssl" else 587,
                             verschluesselung=verschluesselung, benutzer="ich@example.com",
                             absender="ich@example.com", empfaenger=list(empfaenger)),
    )


def _lauf(einst, nachholen=False) -> Ergebnis:
    return ablauf.abrufen(einst, einst.konten[0], lambda t: None, nachholen=nachholen)


def _protokoll(einst) -> Protokoll:
    return Protokoll("airbnb", "privat", einst.belegordner)


def _stand(erg, adresse=A) -> dict:
    return erg.lieferungen[mail.ziel_name(adresse)]


# ── Die Mail ─────────────────────────────────────────────────────────────────


def test_eine_mail_je_rechnung_und_empfaenger(tmp_path, server):
    einst = _einst(tmp_path, empfaenger=(A, B))
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1"), ("g1", "2026-11-04", "AIUC-1")]
    erg = _lauf(einst)
    assert _stand(erg, A)["geliefert"] == 2 and _stand(erg, B)["geliefert"] == 2
    assert [(von, an) for von, an, _ in server.mails] == [("ich@example.com", A)] * 2 + [("ich@example.com", B)] * 2
    m = email.message_from_bytes(server.mails[0][2], policy=policy.default)
    assert m["Subject"] == "Beleg Airbnb AIUC-1 vom 03.11.2026"
    assert m["To"] == A and m["From"] == "ich@example.com"
    anhang = next(m.iter_attachments())
    assert anhang.get_content_type() == "application/pdf"
    assert anhang.get_filename() == "2026-11-03_HMX_AIUC-1.pdf"
    assert anhang.get_content().startswith(b"%PDF")
    g = email.message_from_bytes(server.mails[1][2], policy=policy.default)
    assert g["Subject"] == "Beleg Airbnb AIUC-1 vom 04.11.2026 (Gutschrift)"
    assert m["Message-ID"] != g["Message-ID"]
    # eine Verbindung für alles, mit SSL angemeldet und am Ende abgemeldet
    assert server.befehle[0] == "verbinden smtp.example.com:465 FalschesSMTP_SSL"
    assert server.befehle.count("login ich@example.com") == 1 and server.befehle[-1] == "quit"
    assert PLATZHALTER not in "".join(server.befehle)
    p = _protokoll(einst)
    assert p.ziele_von("rechnung:a1") == ["ordner", "mail:beleg@example.com", "mail:steuer@example.com"]


def test_starttls(tmp_path, server):
    einst = _einst(tmp_path, verschluesselung="starttls")
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(einst)
    assert server.befehle[:4] == ["verbinden smtp.example.com:587 FalschesSMTP", "ehlo", "starttls", "ehlo"]


def test_server_ohne_starttls_verschickt_nichts(tmp_path, server):
    einst = _einst(tmp_path, verschluesselung="starttls")
    server.verhalten = "kein_tls"
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(einst)
    assert "kein STARTTLS" in _stand(erg)["fehler"] and server.mails == []
    assert "login ich@example.com" not in server.befehle


def test_ohne_verschluesselung_kein_versand(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('ziele = ["mail"]\n[mail]\nserver = "smtp.example.com"\nverschluesselung = "keine"\n',
                     encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler, match="Ohne Verschlüsselung"):
        einstellungen.laden(datei)


# ── Nie doppelt, alter Bestand ───────────────────────────────────────────────


def test_zweiter_lauf_schickt_nichts_doppelt(tmp_path, server):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(einst)
    erg = _lauf(einst)
    assert _stand(erg)["geliefert"] == 0 and len(server.mails) == 1
    assert "verbinden" not in " ".join(server.befehle[server.befehle.index("quit") + 1:])  # nichts offen → keine Verbindung


def test_alter_bestand_geht_nicht_raus(tmp_path, server):
    Falsch.rechnungen = [("a1", "2026-10-01", "AIUC-1"), ("a2", "2026-10-02", "AIUC-2")]
    _lauf(_einst(tmp_path, an=False))  # Version 1.x, ohne Mail
    Falsch.rechnungen += [("a3", "2026-11-20", "AIUC-3")]
    erg = _lauf(_einst(tmp_path))
    assert _stand(erg)["schon_markiert"] == 2 and _stand(erg)["geliefert"] == 1
    assert len(server.mails) == 1 and b"AIUC-3" in server.mails[0][2]
    assert _protokoll(_einst(tmp_path)).zustand("rechnung:a1", "mail:beleg@example.com") == "schon"


def test_neuer_empfaenger_spaeter_bekommt_keinen_altbestand(tmp_path, server):
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(_einst(tmp_path, empfaenger=(A,)))
    Falsch.rechnungen += [("a2", "2026-11-05", "AIUC-2")]
    erg = _lauf(_einst(tmp_path, empfaenger=(A, B)))
    assert _stand(erg, B)["schon_markiert"] == 1  # a1 gilt für B als verschickt
    assert [(an, b"AIUC-2" in r) for _, an, r in server.mails] == [(A, False), (A, True), (B, True)]


def test_wieder_einschalten_markiert_nichts(tmp_path, server):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    server.verhalten = "anmeldung"
    assert _stand(_lauf(einst))["offen"] == 1  # gescheitert
    Falsch.rechnungen += [("a2", "2026-11-05", "AIUC-2")]
    _lauf(_einst(tmp_path, an=False))  # Mail aus
    _lauf(_einst(tmp_path, an=False))
    server.verhalten = "ok"
    erg = _lauf(einst)  # wieder an: beide gehen raus, nichts markiert
    assert _stand(erg)["schon_markiert"] == 0 and _stand(erg)["geliefert"] == 2


def test_empfaenger_entfernt_und_wieder_dazu(tmp_path, server):
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(_einst(tmp_path, empfaenger=(A, B)))
    Falsch.rechnungen += [("a2", "2026-11-05", "AIUC-2")]
    _lauf(_einst(tmp_path, empfaenger=(A,)))  # B entfernt
    assert _protokoll(_einst(tmp_path)).ist_an("mail:steuer@example.com") is False
    erg = _lauf(_einst(tmp_path, empfaenger=(A, B)))  # B wieder dazu: a2 geht an B
    assert _stand(erg, B)["schon_markiert"] == 0 and _stand(erg, B)["geliefert"] == 1


def test_fehlende_datei_neu_holen_schickt_nicht_doppelt(tmp_path, server):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(einst)
    datei = _protokoll(einst).lokale_datei("rechnung:a1")
    datei.unlink()
    _lauf(einst, nachholen=True)
    assert datei.exists() and len(server.mails) == 1


def test_gross_und_kleinschreibung_ist_ein_empfaenger(tmp_path, server):
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    _lauf(_einst(tmp_path, empfaenger=(A, "Beleg@Example.com")))
    assert len(server.mails) == 1


# ── Fehler ───────────────────────────────────────────────────────────────────


def test_falsches_passwort_verstaendlich_nichts_verloren(tmp_path, server):
    einst = _einst(tmp_path, empfaenger=(A, B))
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1"), ("a2", "2026-11-04", "AIUC-2")]
    server.verhalten = "anmeldung"
    erg = _lauf(einst)
    assert "lehnt die Anmeldung ab" in _stand(erg)["fehler"] and PLATZHALTER not in _stand(erg)["fehler"]
    assert _stand(erg, A)["offen"] == 2 and _stand(erg, B)["offen"] == 2
    assert server.mails == [] and server.befehle.count("login ich@example.com") == 1  # hält an
    text = ablauf.zusammenfassung([erg], einst.belegordner)
    assert "noch nicht verschickt" in text and PLATZHALTER not in text
    assert _protokoll(einst).lokale_datei("rechnung:a1").exists()
    server.verhalten = "ok"
    erg = _lauf(einst)
    assert _stand(erg, A)["geliefert"] == 2 and _stand(erg, B)["geliefert"] == 2


def test_kein_netz(tmp_path, server):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    server.verhalten = "kein_netz"
    erg = _lauf(einst)
    assert "nicht erreichbar" in _stand(erg)["fehler"] and _stand(erg)["offen"] == 1
    server.verhalten = "ok"
    assert _stand(_lauf(einst))["geliefert"] == 1


def test_empfaenger_abgelehnt_haelt_nur_diesen_an(tmp_path, server):
    einst = _einst(tmp_path, empfaenger=(A, B))
    server.abgelehnte_empfaenger = {A}
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1"), ("a2", "2026-11-04", "AIUC-2")]
    erg = _lauf(einst)
    assert "lehnt den Empfänger beleg@example.com ab: 550" in _stand(erg, A)["fehler"]
    assert _stand(erg, A)["offen"] == 2
    assert _stand(erg, B)["geliefert"] == 2
    assert "rset" in server.befehle


def test_server_nimmt_mail_nicht_an(tmp_path, server):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    server.verhalten = "data_ablehnen"
    erg = _lauf(einst)
    assert "552" in _stand(erg)["fehler"] and _stand(erg)["offen"] == 1
    assert _protokoll(einst).zustand("rechnung:a1", "mail:beleg@example.com") == "offen"


def test_keine_antwort_nach_senden_wird_nicht_wiederholt(tmp_path, server):
    einst = _einst(tmp_path, empfaenger=(A, B))
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    server.verhalten = "keine_antwort"
    erg = _lauf(einst)
    assert _stand(erg, A)["unklar"] == ["AIUC-1"] and _stand(erg, A)["offen"] == 0
    assert _stand(erg, B)["offen"] == 1  # Verbindung weg: B kommt beim nächsten Lauf
    assert "beim Empfänger nachsehen" in ablauf.zusammenfassung([erg], einst.belegordner)
    server.verhalten = "ok"
    erg = _lauf(einst)
    assert [an for _, an, _ in server.mails] == [A, B]  # A nicht noch einmal
    assert _protokoll(einst).zustand("rechnung:a1", "mail:beleg@example.com") == "unklar"


def test_absturz_waehrend_senden_wird_nicht_wiederholt(tmp_path, server, monkeypatch):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]

    def absturz(self, rumpf):
        raise KeyboardInterrupt

    # Nur den Absturz zurücknehmen — nie monkeypatch.undo(), das nähme auch den
    # Test-Datenordner zurück und schriebe in den echten.
    with monkeypatch.context() as m:
        m.setattr(FalschesSMTP, "data", absturz)
        with pytest.raises(KeyboardInterrupt):
            _lauf(einst)
    _lauf(einst)
    assert server.mails == []
    assert _protokoll(einst).zustand("rechnung:a1", "mail:beleg@example.com") == "unklar"


def test_passwort_fehlt(tmp_path, server, monkeypatch):
    def fehlt(dienst, konto):
        raise mail.PasswortFehlt("kein Passwort")

    monkeypatch.setattr(mail, "passwort_lesen", fehlt)
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    erg = _lauf(einst)
    assert _stand(erg)["fehler"] == "kein Passwort" and _stand(erg)["offen"] == 1
    assert server.befehle == []


def test_datei_fehlt_vor_versand(tmp_path, server):
    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    server.verhalten = "kein_netz"
    _lauf(einst)
    _protokoll(einst).lokale_datei("rechnung:a1").unlink()
    server.verhalten = "ok"
    erg = _lauf(einst)
    assert _stand(erg)["offen"] == 1 and server.mails == []
    assert any("Fehlende Dateien neu holen" in h for h in erg.hinweise)


def test_exit_code(tmp_path, server):
    from belegabruf import cli

    einst = _einst(tmp_path)
    Falsch.rechnungen = [("a1", "2026-11-03", "AIUC-1")]
    server.verhalten = "anmeldung"
    assert cli._exit_code([_lauf(einst)]) == 2
    server.verhalten = "ok"
    assert cli._exit_code([_lauf(einst)]) == 0


def test_passwort_nie_im_text():
    p = mail.Postausgang(MailEinstellung(server="smtp.example.com"), PLATZHALTER)
    assert PLATZHALTER not in repr(p)
    assert p.sauber(f"bad {PLATZHALTER}".encode()) == "bad ***"


# ── Einstellungen ────────────────────────────────────────────────────────────


def test_einstellungen_hin_und_zurueck(tmp_path):
    einst = _einst(tmp_path, empfaenger=(A, B), verschluesselung="starttls")
    datei = einstellungen.speichern(einst, tmp_path / "e.toml")
    geladen = einstellungen.laden(datei)
    assert geladen.mail_an and geladen.mail == einst.mail
    assert geladen.mail.dienst_und_konto == ("belegabruf", "mail")


def test_alte_einstellungsdatei_ohne_mail(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('belegordner = "/x"\nziele = ["ordner"]\n', encoding="utf-8")
    geladen = einstellungen.laden(datei)
    assert not geladen.mail_an and geladen.mail.empfaenger == []


def test_mail_an_aber_angaben_fehlen(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('ziele = ["ordner", "mail"]\n[mail]\nserver = "smtp.example.com"\n', encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler, match="benutzer, absender, empfaenger"):
        einstellungen.laden(datei)


def test_falsche_adresse(tmp_path):
    datei = tmp_path / "e.toml"
    datei.write_text('[mail]\nempfaenger = ["keine-adresse"]\n', encoding="utf-8")
    with pytest.raises(einstellungen.EinstellungsFehler, match="keine Mailadresse"):
        einstellungen.laden(datei)


# ── Einrichten (Eingaben gespielt, Passwortspeicher als Attrappe) ────────────


class _Speicher:
    def __init__(self):
        self.daten = {}

    def get_password(self, dienst, konto):
        return self.daten.get((dienst, konto))

    def set_password(self, dienst, konto, wert):
        self.daten[(dienst, konto)] = wert

    def delete_password(self, dienst, konto):
        self.daten.pop((dienst, konto))


def _einrichten(monkeypatch, tmp_path, antworten, speicher, verdeckt=""):
    import builtins
    import getpass

    import keyring

    from belegabruf import einrichtung

    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, name, getattr(speicher, name))
    eingaben = iter(antworten)
    monkeypatch.setattr(builtins, "input", lambda text="": next(eingaben))
    monkeypatch.setattr(getpass, "getpass", lambda text="": verdeckt)
    monkeypatch.setattr(pfade, "standard_belegordner", lambda: tmp_path / "Belege")
    return einrichtung.einrichten()


def _falscher_server(monkeypatch) -> Server:
    s = Server()
    FalschesSMTP.server = s
    monkeypatch.setattr(mail.smtplib, "SMTP", FalschesSMTP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FalschesSMTP_SSL)
    return s


# Anbieter, Kontoname, noch ein Konto?, Belegordner, dann die Mail-Fragen
VORNE = ["", "", "n", ""]


def test_einrichten_mit_mail(tmp_path, monkeypatch, capsys):
    s = _falscher_server(monkeypatch)
    speicher = _Speicher()
    einst = _einrichten(monkeypatch, tmp_path, VORNE + [
        "j", "smtp.example.com", "2", "", "ich@example.com", "", f"{A}, {B}", "",
    ], speicher, verdeckt=PLATZHALTER)
    assert einst.mail_an
    assert einst.mail == MailEinstellung(server="smtp.example.com", port=587, verschluesselung="starttls",
                                         benutzer="ich@example.com", absender="ich@example.com",
                                         empfaenger=[A, B])
    assert speicher.daten == {("belegabruf", "mail"): PLATZHALTER}
    assert s.mails == [] and "data" not in s.befehle and s.befehle[-1] == "quit"  # nur Anmeldung geprüft
    ausgabe = capsys.readouterr().out
    assert "Anmeldung klappt" in ausgabe and PLATZHALTER not in ausgabe
    text = pfade.einstellungsdatei().read_text(encoding="utf-8")
    assert PLATZHALTER not in text and 'passwort_eintrag = "belegabruf/mail"' in text


def test_einrichten_falsches_passwort(tmp_path, monkeypatch, capsys):
    s = _falscher_server(monkeypatch)
    s.verhalten = "anmeldung"
    _einrichten(monkeypatch, tmp_path, VORNE + [
        "j", "smtp.example.com", "1", "", "ich@example.com", "", A, "",
    ], _Speicher(), verdeckt=PLATZHALTER)
    ausgabe = capsys.readouterr().out
    assert "lehnt die Anmeldung ab" in ausgabe and PLATZHALTER not in ausgabe


def test_einrichten_vorgabe_ist_nein(tmp_path, monkeypatch):
    s = _falscher_server(monkeypatch)
    einst = _einrichten(monkeypatch, tmp_path, VORNE + [""], _Speicher())
    assert not einst.mail_an and s.befehle == []
