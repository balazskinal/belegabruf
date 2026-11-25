"""Was die Bedienseite tun kann — dieselben Bausteine wie das CLI (ablauf, einstellungen …).

Hier gibt es keinen zweiten Programmkern: Prüfen, Anmelden und Holen rufen die
Funktionen aus ``ablauf`` auf, die auch ``belege start`` und ``belege holen`` nutzen.

**Geheimnisse** (Mail-Passwort) kommen nur herein und gehen direkt in den
Passwortspeicher. Keine Funktion hier gibt sie je zurück; nach außen heißt es nur
„hinterlegt“ oder „fehlt“.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from belegabruf import __version__, ablauf, aktualisierung, einstellungen, pfade, quellen
from belegabruf.einstellungen import EinstellungsFehler, Einstellungen, Konto, MailEinstellung
from belegabruf.quellen.basis import Ergebnis
from belegabruf.ziele import mail


class Eingabefehler(Exception):
    """Eine Eingabe aus der Bedienseite ist nicht zulässig (Meldung für Menschen)."""


# ── Laufende Aufträge (Prüfen, Anmelden, Holen) ──────────────────────────────


@dataclass
class Auftrag:
    art: str
    meldungen: list[str] = field(default_factory=list)
    laeuft: bool = True
    zusammenfassung: list[dict] | None = None
    code: int | None = None

    def melden(self, text: str) -> None:
        for zeile in str(text).splitlines():
            if zeile.strip():
                self.meldungen.append(zeile.strip())


class Steuerung:
    """Hält den Zustand der Bedienseite: höchstens ein Auftrag zur Zeit."""

    def __init__(self):
        self._sperre = threading.Lock()
        self.auftrag: Auftrag | None = None
        self.faden: threading.Thread | None = None
        self.kontozustand: dict[str, str] = {}  # "quelle/name" → angemeldet | abgelaufen | unbekannt
        self.neuere: str | None = None
        self.beendet = threading.Event()
        threading.Thread(target=self._version_pruefen, daemon=True).start()

    def _version_pruefen(self) -> None:
        try:
            self.neuere = aktualisierung.neuere_version()
        except Exception:  # noqa: BLE001
            self.neuere = None

    # Aufträge ---------------------------------------------------------------

    def beschaeftigt(self) -> bool:
        return self.auftrag is not None and self.auftrag.laeuft

    def starten(self, art: str, arbeit) -> Auftrag:
        with self._sperre:
            if self.beschaeftigt():
                raise Eingabefehler("Es läuft schon etwas. Bitte warten, bis es fertig ist.")
            auftrag = Auftrag(art=art)
            self.auftrag = auftrag

        def laufen():
            try:
                arbeit(auftrag)
            except Exception as fehler:  # noqa: BLE001 - nie abstürzen, immer melden
                auftrag.melden(f"Fehler: {type(fehler).__name__}: {str(fehler).splitlines()[0][:200] if str(fehler) else ''}")
                auftrag.code = 1
            finally:
                auftrag.laeuft = False

        self.faden = threading.Thread(target=laufen, daemon=True)
        self.faden.start()
        return auftrag

    def auftrag_stand(self, seit: int) -> dict:
        a = self.auftrag
        if a is None:
            return {"art": None, "laeuft": False, "meldungen": [], "anzahl": 0}
        seit = max(0, min(seit, len(a.meldungen)))
        return {"art": a.art, "laeuft": a.laeuft, "meldungen": a.meldungen[seit:], "anzahl": len(a.meldungen),
                "zusammenfassung": a.zusammenfassung, "code": a.code}

    # Zustand für die Seite ---------------------------------------------------

    def zustand(self) -> dict:
        try:
            einst = einstellungen.laden()
            eingerichtet = True
        except EinstellungsFehler:
            einst = Einstellungen(belegordner=pfade.standard_belegordner(), konten=[])
            eingerichtet = False
        konten = []
        for k in einst.konten:
            schluessel = f"{k.quelle}/{k.name}"
            try:
                fehlen = ablauf.fehlende_dateien(einst, k) if eingerichtet else 0
            except Exception:  # noqa: BLE001
                fehlen = 0
            # name = interne Kennung (für Prüfen/Anmelden), titel = Name für Menschen (darf leer sein)
            konten.append({"quelle": k.quelle, "anzeige": quellen.anzeigename(k.quelle), "name": k.name,
                           "titel": k.anzeigetitel, "bezeichnung": k.anzeige, "aktiv": k.aktiv, "zustand": self.kontozustand.get(schluessel, "unbekannt"),
                           "fehlende": fehlen})
        m = einst.mail
        return {
            "version": __version__,
            "neuere_version": self.neuere,
            "neueste_seite": aktualisierung.NEUESTE_SEITE if self.neuere else "",
            "eingerichtet": eingerichtet,
            "belegordner": str(einst.belegordner),
            "quellen": [{"name": n, "anzeige": quellen.anzeigename(n)} for n in quellen.QUELLEN],
            "konten": konten,
            "mail_an": einst.mail_an,
            "mail": {"server": m.server, "port": m.port, "verschluesselung": m.verschluesselung,
                     "benutzer": m.benutzer, "absender": m.absender, "empfaenger": list(m.empfaenger),
                     "passwort": "hinterlegt" if _passwort_da(m) else "fehlt"},
            "beschaeftigt": self.beschaeftigt(),
            "auftrag_art": self.auftrag.art if self.beschaeftigt() else None,
            "datei_fremd": _fremd(),
        }

    # Einstellungen ------------------------------------------------------------

    def einstellungen_speichern(self, daten: dict) -> dict:
        # Unter derselben Sperre wie das Starten eines Auftrags: Kein Speichern mitten im
        # Abruf, und kein Abruf startet mitten im Speichern.
        with self._sperre:
            if self.beschaeftigt():
                raise Eingabefehler("Bitte warten, bis der laufende Vorgang fertig ist.")
            einst = einstellungen_aus_eingaben(daten)
            einst.belegordner.mkdir(parents=True, exist_ok=True)
            gesichert = einstellungen.sichern() if einstellungen.fremde_inhalte() else None
            einstellungen.speichern(einst)
        zustand = self.zustand()
        zustand["gesichert"] = gesichert.name if gesichert else ""
        return zustand

    def mail_passwort_setzen(self, daten: dict) -> dict:
        wert = daten.get("passwort")
        if not isinstance(wert, str) or not wert or len(wert) > 1000 or "\n" in wert or "\r" in wert:
            raise Eingabefehler("Bitte ein Passwort eingeben.")
        einst = _geladen()
        mail.passwort_speichern(*einst.mail.dienst_und_konto, wert)
        return {"passwort": "hinterlegt"}

    def mail_pruefen(self) -> dict:
        einst = _geladen()
        if not einst.mail.server:
            raise Eingabefehler("Bitte zuerst die Mail-Angaben speichern.")
        try:
            passwort = mail.passwort_lesen(*einst.mail.dienst_und_konto)
        except mail.PasswortFehlt:
            return {"ok": False, "meldung": "Es ist noch kein Passwort hinterlegt."}
        meldung = mail.anmeldung_pruefen(einst.mail, passwort)
        return {"ok": meldung is None, "meldung": meldung or "Anmeldung klappt (es wurde keine Mail verschickt)."}

    # Aufträge -----------------------------------------------------------------

    def pruefen(self, daten: dict) -> Auftrag:
        einst = _geladen()
        konten = _konten_waehlen(einst, daten)

        def arbeit(a: Auftrag):
            for k in konten:
                a.melden(f"Prüfe {k.anzeige} …")
                status = ablauf.sitzung_pruefen(k)
                self.kontozustand[f"{k.quelle}/{k.name}"] = _zustand_aus(status)
                a.melden(f"{k.anzeige}: {_zustand_text(status)}")
            a.code = 0

        return self.starten("pruefen", arbeit)

    def anmelden(self, daten: dict) -> Auftrag:
        einst = _geladen()
        konten = _konten_waehlen(einst, daten, genau_eins=True)
        k = konten[0]

        def arbeit(a: Auftrag):
            a.melden(f"Anmeldung bei {k.anzeige}: Es öffnet sich ein eigenes Fenster.")
            ok = ablauf.anmelden(k, a.melden)
            self.kontozustand[f"{k.quelle}/{k.name}"] = "angemeldet" if ok else "abgelaufen"
            a.melden("✓ angemeldet" if ok else "✗ Anmeldung nicht erkannt.")
            a.code = 0 if ok else 2

        return self.starten("anmelden", arbeit)

    def holen(self, daten: dict) -> Auftrag:
        einst = _geladen()
        konten = einst.aktive_konten()
        if not konten:
            raise Eingabefehler("Es ist kein Konto eingeschaltet.")
        nachholen = daten.get("fehlende") is True

        def arbeit(a: Auftrag):
            uebernommen = ablauf.uebernahme(einst)
            if uebernommen:
                a.melden(f"Das Protokoll aus Version 1 ist übernommen ({uebernommen} Einträge).")
            ergebnisse: list[Ergebnis] = []
            for k in konten:
                anzeige = k.anzeige
                a.melden(f"{anzeige}: prüfe die Anmeldung …")
                status = ablauf.sitzung_pruefen(k)
                self.kontozustand[f"{k.quelle}/{k.name}"] = _zustand_aus(status)
                if status != "angemeldet":
                    a.melden(f"{anzeige}: nicht angemeldet — bitte bei diesem Konto „Anmelden“ wählen.")
                    ergebnisse.append(Ergebnis(k.quelle, k.name, status="anmeldung_noetig", anzeige=k.anzeige))
                    continue
                if nachholen:
                    a.melden(f"{anzeige}: fehlende Dateien werden neu geholt (dazu alles, was neu ist).")
                a.melden(f"{anzeige}: hole die Belege — das dauert ein paar Minuten …")
                ergebnisse.append(ablauf.abrufen(einst, k, lambda t, n=anzeige: a.melden(f"{n}: {t.strip()}"),
                                                 nachholen=nachholen))
            a.zusammenfassung = zusammenfassung_als_liste(ablauf.zusammenfassung(ergebnisse, einst.belegordner))
            from belegabruf.cli import _exit_code

            a.code = _exit_code(ergebnisse)

        return self.starten("holen", arbeit)


# ── Hilfen ───────────────────────────────────────────────────────────────────


def _fremd() -> list[str]:
    try:
        return einstellungen.fremde_inhalte()
    except Exception:  # noqa: BLE001
        return []


def _geladen() -> Einstellungen:
    try:
        return einstellungen.laden()
    except EinstellungsFehler as fehler:
        raise Eingabefehler(f"{fehler} Bitte zuerst die Einstellungen speichern.") from None


def _passwort_da(m: MailEinstellung) -> bool:
    try:
        return mail.passwort_vorhanden(*m.dienst_und_konto)
    except Exception:  # noqa: BLE001 - Passwortspeicher gesperrt o. Ä.
        return False


def _zustand_aus(status: str) -> str:
    if status == "angemeldet":
        return "angemeldet"
    if status == "abgemeldet":
        return "abgelaufen"
    return "unbekannt"


def _zustand_text(status: str) -> str:
    return {"angemeldet": "angemeldet", "abgemeldet": "nicht angemeldet"}.get(status, status)


def _konten_waehlen(einst: Einstellungen, daten: dict, genau_eins: bool = False) -> list[Konto]:
    quelle, name = daten.get("quelle"), daten.get("name")
    if quelle is None and name is None and not genau_eins:
        konten = einst.aktive_konten()
    else:
        konten = [k for k in einst.konten if k.quelle == quelle and k.name == name]
    if not konten:
        raise Eingabefehler("Dieses Konto gibt es nicht (mehr). Bitte die Seite neu laden.")
    return konten


_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")


def _text(wert, feld: str, hoechstens: int = 200, pflicht: bool = False) -> str:
    if wert is None:
        wert = ""
    if not isinstance(wert, str):
        raise Eingabefehler(f"{feld}: ungültige Eingabe.")
    wert = wert.strip()
    if _STEUERZEICHEN.search(wert) or len(wert) > hoechstens:
        raise Eingabefehler(f"{feld}: ungültige Eingabe.")
    if pflicht and not wert:
        raise Eingabefehler(f"{feld}: bitte ausfüllen.")
    return wert


def einstellungen_aus_eingaben(daten: dict) -> Einstellungen:
    """Baut Einstellungen aus den Formularfeldern und prüft sie streng — nach denselben
    Regeln wie die Einstellungsdatei, dazu Pfad, Kontonamen und Port."""
    if not isinstance(daten, dict):
        raise Eingabefehler("Ungültige Eingabe.")
    ordner_text = _text(daten.get("belegordner"), "Belegordner", 1000, pflicht=True)
    ordner = Path(ordner_text).expanduser()
    if not ordner.is_absolute():
        raise Eingabefehler("Belegordner: bitte einen vollständigen Pfad angeben (z. B. /Users/… bzw. C:\\…).")
    if ordner.exists() and not ordner.is_dir():
        raise Eingabefehler("Belegordner: an dieser Stelle liegt eine Datei, kein Ordner.")

    try:
        alt = einstellungen.laden()
    except EinstellungsFehler:
        alt = None
    alte = {(k.quelle, k.name): k for k in (alt.konten if alt else [])}

    konten: list[Konto] = []
    roh_konten = daten.get("konten") or []
    if not isinstance(roh_konten, list) or len(roh_konten) > 50:
        raise Eingabefehler("Konten: ungültige Eingabe.")
    for eintrag in roh_konten:
        if not isinstance(eintrag, dict):
            raise Eingabefehler("Konten: ungültige Eingabe.")
        quelle = _text(eintrag.get("quelle"), "Anbieter", 40, pflicht=True).lower()
        if quelle not in quellen.QUELLEN:
            raise Eingabefehler(f"Anbieter „{quelle}“ gibt es nicht.")
        titel = _text(eintrag.get("name"), "Kontoname", 60)
        # Ein schon eingetragenes Konto behält seine Kennung (Anmeldung, Protokoll), auch
        # wenn es umbenannt wird. Eine Kennung, die es nicht gibt, wird nicht übernommen.
        kennung = eintrag.get("kennung")
        if not (isinstance(kennung, str) and (quelle, kennung) in alte):
            kennung = einstellungen.kennung_fuer(titel)
        neu_konto = Konto(quelle=quelle, name=kennung, aktiv=eintrag.get("aktiv") is not False,
                          optionen=dict(alte[(quelle, kennung)].optionen) if (quelle, kennung) in alte else {},
                          titel=titel)
        try:
            einstellungen.konten_unterscheidbar(konten + [neu_konto])
        except EinstellungsFehler as fehler:
            raise Eingabefehler(str(fehler)) from None
        konten.append(neu_konto)

    mail_an = daten.get("mail_an") is True
    roh_mail = daten.get("mail") or {}
    if not isinstance(roh_mail, dict):
        raise Eingabefehler("Mail: ungültige Eingabe.")
    port_roh = roh_mail.get("port")
    if port_roh is None or port_roh == "":
        port_roh = 465  # leer = Vorgabe
    if isinstance(port_roh, bool) or not (isinstance(port_roh, int) or
                                          (isinstance(port_roh, str) and port_roh.strip().isdigit())):
        raise Eingabefehler("Port: bitte eine Zahl zwischen 1 und 65535.")
    port = int(port_roh)
    if not 1 <= port <= 65535:
        raise Eingabefehler("Port: bitte eine Zahl zwischen 1 und 65535.")
    verschluesselung = _text(roh_mail.get("verschluesselung") or "ssl", "Verschlüsselung", 10).lower()
    if verschluesselung not in {"ssl", "starttls"}:
        raise Eingabefehler("Verschlüsselung: nur SSL oder STARTTLS — ohne gibt es keinen Versand.")
    empfaenger_roh = roh_mail.get("empfaenger") or []
    if isinstance(empfaenger_roh, str):
        empfaenger_roh = empfaenger_roh.split(",")
    if not isinstance(empfaenger_roh, list) or len(empfaenger_roh) > 20:
        raise Eingabefehler("Empfänger: ungültige Eingabe.")
    empfaenger = [_text(e, "Empfänger", 254) for e in empfaenger_roh]
    alte_mail = alt.mail if alt else MailEinstellung()
    m = MailEinstellung(
        server=_text(roh_mail.get("server"), "Postausgangsserver", 253),
        port=port, verschluesselung=verschluesselung,
        benutzer=_text(roh_mail.get("benutzer"), "Benutzername", 254),
        absender=_text(roh_mail.get("absender"), "Absender", 254),
        empfaenger=[e for e in empfaenger if e],
        passwort_eintrag=alte_mail.passwort_eintrag,
    )
    if m.server and not re.fullmatch(r"[A-Za-z0-9.-]+", m.server):
        raise Eingabefehler("Postausgangsserver: bitte nur den Namen, z. B. smtp.example.com.")

    neu = Einstellungen(
        belegordner=ordner, konten=konten,
        ziele=["ordner", "mail"] if mail_an else ["ordner"],
        sichtbar=alt.sichtbar if alt else False,
        mail=m,
    )
    try:
        return einstellungen.pruefen(neu)
    except EinstellungsFehler as fehler:
        raise Eingabefehler(str(fehler).replace("[mail] ", "Mail: ")) from None


def zusammenfassung_als_liste(text: str) -> list[dict]:
    """Die Zusammenfassung des CLI (gleicher Inhalt), als Liste für die Seite."""
    zeilen = []
    for zeile in text.splitlines():
        if not zeile.strip() or set(zeile.strip()) <= {"─"} or zeile.strip() == "Zusammenfassung":
            continue
        inhalt = zeile.strip()
        if zeile.startswith("  ! "):
            art = "warnung"
            inhalt = inhalt[2:]
        elif zeile.startswith("  · "):
            art = "hinweis"
            inhalt = inhalt[2:]
        elif zeile.startswith("  "):
            art = "zeile"
        elif inhalt.startswith("Belegordner:"):
            art = "ordner"
        else:
            art = "konto"
        zeilen.append({"art": art, "text": inhalt})
    return zeilen
