"""Ziel "mail": jede neue Rechnung per Mail (SMTP) mit PDF-Anhang verschicken.

Eine Mail je Rechnung und Empfänger. So kommt der Beleg in jedem System an, das eine
Belegadresse hat (Buchhaltungsprogramm, Steuerberatung) — dort wird er gelesen wie
jede andere Belegmail.

**Regel: Das Programm sendet nur.** Es liest keine Postfächer und ruft am Mailserver
nur Anmelden, Senden und Abmelden auf. Verschlüsselung ist Pflicht (SSL oder
STARTTLS); ohne gibt es keinen Versand.

Das Passwort liegt im Passwortspeicher des Betriebssystems (Bibliothek ``keyring``)
und erscheint nie in Ausgaben, Dateien oder Protokollen.
"""

from __future__ import annotations

import hashlib
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.policy import SMTP as SMTP_REGELN
from email.utils import formatdate

from belegabruf.ziele.basis import Abgelehnt, Lieferziel, Sendung, Unklar

ZEITLIMIT = 60
VERSCHLUESSELUNGEN = ("ssl", "starttls")
QUELLEN_NAMEN = {"airbnb": "Airbnb"}


class PasswortFehlt(Exception):
    """Im Passwortspeicher liegt kein Passwort unter dem eingestellten Eintrag."""


# ── Passwort ─────────────────────────────────────────────────────────────────


def passwort_lesen(dienst: str, konto: str) -> str:
    import keyring

    wert = keyring.get_password(dienst, konto)
    if not wert:
        raise PasswortFehlt(
            f"Im Passwortspeicher liegt kein Mail-Passwort unter „{dienst}/{konto}“. "
            "Doppelklick auf „Einrichten“ und das Passwort eingeben."
        )
    return wert


def passwort_speichern(dienst: str, konto: str, wert: str) -> None:
    import keyring

    keyring.set_password(dienst, konto, wert)


def passwort_loeschen(dienst: str, konto: str) -> bool:
    import keyring
    from keyring.errors import PasswordDeleteError

    try:
        keyring.delete_password(dienst, konto)
        return True
    except PasswordDeleteError:
        return False


def passwort_vorhanden(dienst: str, konto: str) -> bool:
    try:
        passwort_lesen(dienst, konto)
        return True
    except PasswortFehlt:
        return False


# ── Verbindung ───────────────────────────────────────────────────────────────


def _text(wert) -> str:
    if isinstance(wert, bytes):
        return wert.decode("utf-8", errors="replace")
    return str(wert)


class Postausgang:
    """Eine Verbindung zum Mailserver je Lauf, geteilt von allen Empfängern."""

    def __init__(self, einst, passwort: str, smtp_klassen=None):
        self.einst = einst  # einstellungen.MailEinstellung
        self._passwort = passwort
        self._smtp, self._smtp_ssl = smtp_klassen or (smtplib.SMTP, smtplib.SMTP_SSL)
        self._verbindung = None

    def __repr__(self) -> str:  # nie das Passwort zeigen, auch nicht in Fehlerberichten
        return f"Postausgang({self.einst.server})"

    def sauber(self, text) -> str:
        text = _text(text)
        return text.replace(self._passwort, "***") if self._passwort else text

    def verbindung(self):
        if self._verbindung is not None:
            return self._verbindung
        e = self.einst
        if e.verschluesselung not in VERSCHLUESSELUNGEN:
            raise Abgelehnt("Ohne Verschlüsselung (ssl oder starttls) wird keine Mail verschickt.",
                            alle_anhalten=True)
        kontext = ssl.create_default_context()
        try:
            if e.verschluesselung == "ssl":
                smtp = self._smtp_ssl(e.server, e.port, timeout=ZEITLIMIT, context=kontext)
            else:
                smtp = self._smtp(e.server, e.port, timeout=ZEITLIMIT)
                smtp.ehlo()
                smtp.starttls(context=kontext)
                smtp.ehlo()
        except smtplib.SMTPNotSupportedError as fehler:
            raise Abgelehnt(f"Der Mailserver {e.server} bietet kein STARTTLS an — ohne Verschlüsselung "
                            "wird nicht verschickt. Port und Verschlüsselung prüfen.", alle_anhalten=True) from fehler
        except ssl.SSLError as fehler:
            raise Abgelehnt(f"Verschlüsselte Verbindung zu {e.server} fehlgeschlagen ({fehler.reason or fehler}). "
                            "Port und Verschlüsselung prüfen.", alle_anhalten=True) from fehler
        except (OSError, smtplib.SMTPException) as fehler:
            raise Abgelehnt(f"Der Mailserver {e.server}:{e.port} ist nicht erreichbar "
                            f"({type(fehler).__name__}). Internet, Server und Port prüfen.",
                            alle_anhalten=True) from fehler
        try:
            smtp.login(e.benutzer, self._passwort)
        except smtplib.SMTPAuthenticationError as fehler:
            self._zu(smtp)
            raise Abgelehnt(
                f"Der Mailserver lehnt die Anmeldung ab (Benutzer oder Passwort falsch?). Meldung: "
                f"{fehler.smtp_code} {self.sauber(fehler.smtp_error)}", alle_anhalten=True) from fehler
        except smtplib.SMTPNotSupportedError as fehler:
            self._zu(smtp)
            raise Abgelehnt("Der Mailserver erlaubt keine Anmeldung mit Passwort (SMTP AUTH). "
                            "Siehe README: App-Passwort bzw. SMTP AUTH einschalten.", alle_anhalten=True) from fehler
        except (OSError, smtplib.SMTPException) as fehler:
            self._zu(smtp)
            raise Abgelehnt(f"Anmeldung am Mailserver fehlgeschlagen ({type(fehler).__name__}: "
                            f"{self.sauber(fehler)}).", alle_anhalten=True) from fehler
        self._verbindung = smtp
        return smtp

    @staticmethod
    def _zu(smtp) -> None:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001
            try:
                smtp.close()
            except Exception:  # noqa: BLE001
                pass

    def kaputt(self) -> None:
        """Verbindung gilt als verloren (nächster Versand baut neu auf)."""
        if self._verbindung is not None:
            try:
                self._verbindung.close()
            except Exception:  # noqa: BLE001
                pass
        self._verbindung = None

    def schliessen(self) -> None:
        if self._verbindung is not None:
            self._zu(self._verbindung)
        self._verbindung = None


def anmeldung_pruefen(einst, passwort: str, smtp_klassen=None) -> str | None:
    """Nur für "Einrichten": anmelden und wieder abmelden, ohne eine Mail zu schicken.
    None, wenn es geht, sonst eine verständliche Meldung."""
    postausgang = Postausgang(einst, passwort, smtp_klassen)
    try:
        postausgang.verbindung()
    except Abgelehnt as fehler:
        return str(fehler)
    postausgang.schliessen()
    return None


# ── Die Mail ─────────────────────────────────────────────────────────────────


def nachricht(absender: str, empfaenger: str, sendung: Sendung) -> EmailMessage:
    anbieter = QUELLEN_NAMEN.get(sendung.quelle, sendung.quelle.capitalize())
    datum = sendung.rechnungsdatum.strftime("%d.%m.%Y") if sendung.rechnungsdatum else ""
    art = "Gutschrift" if sendung.gutschrift else "Rechnung"
    betreff = f"Beleg {anbieter} {sendung.rechnungsnummer}" + (f" vom {datum}" if datum else "")
    if sendung.gutschrift:
        betreff += " (Gutschrift)"
    m = EmailMessage(policy=SMTP_REGELN)
    m["From"] = absender
    m["To"] = empfaenger
    m["Subject"] = betreff
    m["Date"] = formatdate(localtime=True)
    # Gleiche Rechnung + gleicher Empfänger = gleiche Message-ID. Empfangende Systeme
    # können so Doppelte erkennen, falls doch einmal etwas zweimal ankommt.
    kennung = hashlib.sha256(f"{sendung.schluessel}|{empfaenger}".encode()).hexdigest()[:32]
    domain = absender.rpartition("@")[2] or "belegabruf.invalid"
    m["Message-ID"] = f"<{kennung}.belegabruf@{domain}>"
    m.set_content(
        f"Im Anhang: {art} {sendung.rechnungsnummer}" + (f" vom {datum}" if datum else "")
        + f" von {anbieter}.\n\nAutomatisch verschickt von Belegabruf.\n"
    )
    m.add_attachment(sendung.inhalt, maintype="application", subtype="pdf", filename=sendung.dateiname)
    return m


class MailZiel(Lieferziel):
    """Ein Empfänger. Im Protokoll heißt er ``mail:<adresse>``."""

    gruppe = "mail"

    def __init__(self, postausgang: Postausgang, empfaenger: str):
        self.postausgang = postausgang
        self.empfaenger = empfaenger
        self.name = ziel_name(empfaenger)
        self.anzeigename = f"Mail an {empfaenger}"

    def senden(self, sendung: Sendung, vor_senden) -> None:  # Mails haben keine Kennung
        p = self.postausgang
        smtp = p.verbindung()
        rumpf = nachricht(p.einst.absender, self.empfaenger, sendung).as_bytes()
        # Bis vor DATA ist sicher nichts verschickt.
        try:
            code, antwort = smtp.mail(p.einst.absender)
            if code != 250:
                smtp.rset()
                raise Abgelehnt(f"Der Mailserver lehnt den Absender {p.einst.absender} ab: "
                                f"{code} {p.sauber(antwort)}", alle_anhalten=True)
            code, antwort = smtp.rcpt(self.empfaenger)
            if code not in (250, 251):
                smtp.rset()
                raise Abgelehnt(f"Der Mailserver lehnt den Empfänger {self.empfaenger} ab: "
                                f"{code} {p.sauber(antwort)}")
        except (smtplib.SMTPServerDisconnected, OSError) as fehler:
            p.kaputt()
            raise Abgelehnt(f"Die Verbindung zum Mailserver ist abgebrochen ({type(fehler).__name__}), "
                            "noch bevor etwas verschickt wurde.", alle_anhalten=True) from fehler
        vor_senden()
        try:
            smtp.data(rumpf)
        except smtplib.SMTPDataError as fehler:
            # Der Server hat geantwortet und nicht angenommen.
            raise Abgelehnt(f"Der Mailserver nimmt die Mail nicht an: {fehler.smtp_code} "
                            f"{p.sauber(fehler.smtp_error)}") from fehler
        except (smtplib.SMTPServerDisconnected, OSError, socket.timeout) as fehler:
            p.kaputt()
            raise Unklar(f"Nach dem Senden kam vom Mailserver keine Antwort ({type(fehler).__name__}).") from fehler

    def schliessen(self) -> None:
        self.postausgang.schliessen()


def ziel_name(empfaenger: str) -> str:
    return f"mail:{empfaenger.strip().lower()}"
