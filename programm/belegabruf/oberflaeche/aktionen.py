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
from datetime import date, datetime, timedelta
from pathlib import Path

from belegabruf import __version__, ablauf, aktualisierung, einstellungen, pfade, quellen
from belegabruf import zustand as merkzettel
from belegabruf.einstellungen import Einstellungen, EinstellungsFehler, Konto, MailEinstellung
from belegabruf.ziele import mail


class Eingabefehler(Exception):
    """Eine Eingabe aus der Bedienseite ist nicht zulässig (Meldung für Menschen).

    ``felder``: welches Feld was braucht (Feldname → ein Satz), damit die Seite die
    Felder markieren kann. Maßgeblich bleibt die Prüfung hier auf dem Server."""

    def __init__(self, text: str, felder: dict[str, str] | None = None):
        super().__init__(text)
        self.felder = dict(felder or {})


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
        self.kontozustand: dict[str, str] = {}  # "quelle/name" → angemeldet | abgelaufen | nie | unbekannt
        self.geprueft: dict[str, datetime] = {}  # "quelle/name" → Zeitpunkt der letzten Prüfung
        self.neuere: str | None = None
        self.beendet = threading.Event()
        threading.Thread(target=self._version_pruefen, daemon=True).start()

    def _version_pruefen(self) -> None:
        try:
            self.neuere = aktualisierung.neuere_version()
        except Exception:  # noqa: BLE001
            self.neuere = None

    # Aufträge ---------------------------------------------------------------

    def anmeldestand_merken(self, k: Konto, status: str) -> None:
        """Ergebnis einer Prüfung bzw. Anmeldung: „angemeldet“, „abgemeldet“ oder ein Fehlertext."""
        schluessel = k.schluessel
        if status == "angemeldet":
            merkzettel.angemeldet_merken(k.quelle, k.name)
            self.kontozustand[schluessel] = "angemeldet"
        elif status == "abgemeldet":
            self.kontozustand[schluessel] = "abgelaufen" if merkzettel.je_angemeldet(k.quelle, k.name) else "nie"
        else:
            self.kontozustand[schluessel] = "unbekannt"
        self.geprueft[schluessel] = datetime.now()

    def anmeldestand(self, k: Konto) -> str:
        schluessel = k.schluessel
        if schluessel in self.kontozustand:
            return self.kontozustand[schluessel]
        bekannt = merkzettel.je_angemeldet(k.quelle, k.name) or pfade.profilordner(k.quelle, k.name).exists()
        return "unbekannt" if bekannt else "nie"

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
                erste_zeile = str(fehler).splitlines()[0][:200] if str(fehler) else ""
                auftrag.melden(f"Fehler: {type(fehler).__name__}: {erste_zeile}")
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
            schluessel = k.schluessel
            geprueft = self.geprueft.get(schluessel)
            try:
                fehlen = ablauf.fehlende_dateien(einst, k) if eingerichtet else 0
            except Exception:  # noqa: BLE001
                fehlen = 0
            # name = interne Kennung (für Prüfen/Anmelden), titel = Name für Menschen (darf leer sein)
            konten.append({"quelle": k.quelle, "anzeige": quellen.anzeigename(k.quelle), "name": k.name,
                           "titel": k.anzeigetitel, "bezeichnung": k.anzeige, "aktiv": k.aktiv,
                           "belege_ab": k.belege_ab,
                           "ab_text": f"Belege ab {k.ab():%d.%m.%Y}" if k.ab() else "", "zustand": self.anmeldestand(k),
                           "geprueft": _zeitpunkt_text(geprueft) if geprueft else "",
                           "fehlende": fehlen})
        m = einst.mail
        return {
            "version": __version__,
            "neuere_version": self.neuere,
            "neueste_seite": aktualisierung.NEUESTE_SEITE if self.neuere else "",
            "eingerichtet": eingerichtet,
            "belegordner": str(einst.belegordner),
            "ablage": einst.ablage,
            "quellen": [{"name": n, "anzeige": quellen.anzeigename(n)} for n in quellen.QUELLEN],
            "konten": konten,
            "mail_an": einst.mail_an,
            "mail": {"server": m.server, "port": m.port, "verschluesselung": m.verschluesselung,
                     "benutzer": m.benutzer, "absender": m.absender, "empfaenger": list(m.empfaenger),
                     "passwort": "hinterlegt" if _passwort_da(m) else "fehlt", "erstversand": m.erstversand},
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

    def konto_holen_setzen(self, daten: dict) -> dict:
        """Haken „Holen“ je Konto (gespeichert als ``aktiv``) — sofort, ohne das
        Einstellungsformular. Gesperrt, solange ein Vorgang läuft."""
        aktiv = daten.get("aktiv")
        if not isinstance(aktiv, bool):
            raise Eingabefehler("Ungültige Eingabe.")
        with self._sperre:
            if self.beschaeftigt():
                raise Eingabefehler("Bitte warten, bis der laufende Vorgang fertig ist.")
            einst = _geladen()
            konto = _konten_waehlen(einst, daten, genau_eins=True)[0]
            konto.aktiv = aktiv
            if einstellungen.fremde_inhalte():
                einstellungen.sichern()
            einstellungen.speichern(einst)
        return {"aktiv": aktiv}

    def mail_passwort_setzen(self, daten: dict) -> dict:
        wert = daten.get("passwort")
        if not isinstance(wert, str) or not wert or len(wert) > 1000 or "\n" in wert or "\r" in wert:
            raise Eingabefehler("Bitte ein Passwort eingeben.")
        einst = _geladen()
        mail.passwort_speichern(*einst.mail.dienst_und_konto, wert)
        return {"passwort": "hinterlegt"}

    def mail_passwort_loeschen(self) -> dict:
        """Wie in der Terminal-Einrichtung: nur Einträge, die Belegabruf selbst angelegt hat
        (Dienst „belegabruf“), nie einen fremden Eintrag im Passwortspeicher."""
        einst = _geladen()
        dienst, konto = einst.mail.dienst_und_konto
        if dienst != "belegabruf":
            raise Eingabefehler(f"Der Eintrag „{dienst}/…“ gehört nicht Belegabruf; bitte im Passwortspeicher "
                                "selbst löschen.")
        mail.passwort_loeschen(dienst, konto)
        return {"passwort": "fehlt"}

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
                self.anmeldestand_merken(k, status)
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
            self.anmeldestand_merken(k, "angemeldet" if ok else "abgemeldet")
            a.melden("✓ angemeldet" if ok else "✗ Anmeldung nicht erkannt.")
            a.code = 0 if ok else 2

        return self.starten("anmelden", arbeit)

    def holen(self, daten: dict) -> Auftrag:
        einst = _geladen()
        konten = einst.aktive_konten()
        if not konten:
            raise Eingabefehler("Kein Konto angehakt — bitte bei mindestens einem Konto den Haken „Holen“ setzen.")
        nachholen = daten.get("fehlende") is True

        def arbeit(a: Auftrag):
            uebernommen = ablauf.uebernahme(einst)
            if uebernommen:
                a.melden(f"Das Protokoll aus Version 1 ist übernommen ({uebernommen} Einträge).")

            def bereit(k: Konto) -> bool:
                a.melden(f"{k.anzeige}: prüfe die Anmeldung …")
                status = ablauf.sitzung_pruefen(k)
                self.anmeldestand_merken(k, status)
                if status != "angemeldet":
                    a.melden(f"{k.anzeige}: nicht angemeldet — bitte im Reiter „Einstellungen“ bei diesem Konto "
                             "„Anmelden“ wählen.")
                    return False
                if nachholen:
                    a.melden(f"{k.anzeige}: fehlende Dateien werden neu geholt (dazu alles, was neu ist).")
                a.melden(f"{k.anzeige}: hole die Belege — das dauert ein paar Minuten …")
                return True

            def melden_fuer(k: Konto):
                return lambda t: a.melden(f"{k.anzeige}: {t.strip()}")

            ergebnisse = ablauf.alle_abrufen(einst, konten, bereit, melden_fuer, nachholen=nachholen)
            for k, ergebnis in zip(konten, ergebnisse, strict=True):
                if ergebnis.status == "abgelaufen":  # mittendrin abgelaufen
                    self.anmeldestand_merken(k, "abgemeldet")
            a.zusammenfassung = zusammenfassung_als_liste(ablauf.zusammenfassung(ergebnisse, einst.belegordner))
            a.code = ablauf.exit_code(ergebnisse)

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


def _zeitpunkt_text(zeit: datetime, jetzt: datetime | None = None) -> str:
    """„geprüft heute 21:30“, „geprüft gestern 08:05“, sonst mit Datum."""
    jetzt = jetzt or datetime.now()
    if zeit.date() == jetzt.date():
        tag = "heute"
    elif zeit.date() == (jetzt - timedelta(days=1)).date():
        tag = "gestern"
    else:
        tag = f"am {zeit:%d.%m.}"
    return f"geprüft {tag} {zeit:%H:%M}"


def _zustand_text(status: str) -> str:
    return {"angemeldet": "angemeldet", "abgemeldet": "nicht angemeldet"}.get(status, status)


def _konten_waehlen(einst: Einstellungen, daten: dict, genau_eins: bool = False) -> list[Konto]:
    quelle, name = daten.get("quelle"), daten.get("name")
    if quelle is None and name is None and not genau_eins:
        konten = list(einst.konten)  # „Alle Anmeldungen prüfen“: alle, unabhängig vom Haken
    else:
        konten = [k for k in einst.konten if k.quelle == quelle and k.name == name]
    if not konten:
        raise Eingabefehler("Dieses Konto gibt es nicht (mehr). Bitte die Seite neu laden.")
    return konten


_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")
_SERVERNAME = re.compile(r"[A-Za-z0-9.-]+")


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


class _Sammler:
    """Sammelt alle Feldfehler, damit die Seite alle auf einmal markieren kann."""

    def __init__(self):
        self.felder: dict[str, str] = {}

    def feld(self, name: str, satz: str) -> None:
        self.felder.setdefault(name, satz)

    def text(self, name: str, wert, bezeichnung: str, hoechstens: int = 200) -> str:
        try:
            return _text(wert, bezeichnung, hoechstens)
        except Eingabefehler as fehler:
            self.feld(name, str(fehler))
            return ""

    def pruefen(self) -> None:
        if self.felder:
            raise Eingabefehler(next(iter(self.felder.values())), self.felder)


def einstellungen_aus_eingaben(daten: dict) -> Einstellungen:
    """Baut Einstellungen aus den Formularfeldern und prüft sie streng — nach denselben
    Regeln wie die Einstellungsdatei, dazu Pfad, Kontonamen und Port. Fehler nennen
    das betroffene Feld (``Eingabefehler.felder``)."""
    if not isinstance(daten, dict):
        raise Eingabefehler("Ungültige Eingabe.")
    try:
        alt = einstellungen.laden()
    except EinstellungsFehler:
        alt = None
    sammler = _Sammler()
    ordner = _belegordner_lesen(sammler, daten.get("belegordner"))
    konten = _konten_lesen(sammler, daten.get("konten"), alt)
    mail_an = daten.get("mail_an") is True
    roh_mail = daten.get("mail") or {}
    if not isinstance(roh_mail, dict):
        raise Eingabefehler("Mail: ungültige Eingabe.")
    m = _mail_lesen(sammler, roh_mail, mail_an, alt.mail if alt else MailEinstellung())
    ablage = _auswahl(sammler, "ablage", daten.get("ablage"), alt.ablage if alt else "jahr",
                      einstellungen.ABLAGEN, "Unterordner: bitte „nach Jahr“ oder „nach Jahr und Monat“ wählen.")
    sammler.pruefen()

    neu = Einstellungen(
        belegordner=ordner, konten=konten,
        ziele=["ordner", "mail"] if mail_an else ["ordner"],
        sichtbar=alt.sichtbar if alt else False,
        mail=m,
        ablage=ablage,
    )
    try:
        return einstellungen.pruefen(neu)
    except EinstellungsFehler as fehler:
        raise Eingabefehler(str(fehler).replace("[mail] ", "Mail: ")) from None


def _auswahl(sammler: _Sammler, feld: str, wert, bisher: str, erlaubt: tuple[str, ...], satz: str) -> str:
    """Ein Auswahlfeld: leer = bisheriger Wert; sonst nur einer der erlaubten Werte."""
    if wert is None or wert == "":
        wert = bisher
    if wert not in erlaubt:
        sammler.feld(feld, satz)
        return erlaubt[0]
    return wert


def _belegordner_lesen(sammler: _Sammler, wert) -> Path | None:
    text = sammler.text("belegordner", wert, "Belegordner", 1000)
    ordner = Path(text).expanduser() if text else None
    if ordner is None:
        sammler.feld("belegordner", "Bitte den Belegordner angeben.")
    elif not ordner.is_absolute():
        sammler.feld("belegordner", "Belegordner: bitte einen vollständigen Pfad angeben (z. B. /Users/… bzw. C:\\…).")
    elif ordner.exists() and not ordner.is_dir():
        sammler.feld("belegordner", "Belegordner: an dieser Stelle liegt eine Datei, kein Ordner.")
    return ordner


def _konten_lesen(sammler: _Sammler, roh_konten, alt: Einstellungen | None) -> list[Konto]:
    """Die Kontozeilen; Feldfehler heißen konto-<Zeile>-quelle/-name/-ab."""
    alte = {(k.quelle, k.name): k for k in (alt.konten if alt else [])}
    roh_konten = roh_konten or []
    if not isinstance(roh_konten, list) or len(roh_konten) > 50:
        raise Eingabefehler("Konten: ungültige Eingabe.")
    zeilen: list[int] = []
    konten: list[Konto] = []
    for nr, eintrag in enumerate(roh_konten):
        if not isinstance(eintrag, dict):
            raise Eingabefehler("Konten: ungültige Eingabe.")
        konto = _konto_lesen(sammler, nr, eintrag, alte)
        if konto is not None:
            zeilen.append(nr)
            konten.append(konto)
    # Namen je Anbieter: dieselben Regeln wie beim Laden der Datei, hier mit Feldbezug.
    for index, satz in einstellungen.kontonamen_fehler(konten):
        sammler.feld(f"konto-{zeilen[index]}-name", satz)
    return konten


def _konto_lesen(sammler: _Sammler, nr: int, eintrag: dict, alte: dict) -> Konto | None:
    quelle = sammler.text(f"konto-{nr}-quelle", eintrag.get("quelle"), "Anbieter", 40).lower()
    if quelle not in quellen.QUELLEN:
        sammler.feld(f"konto-{nr}-quelle", f"Anbieter „{quelle}“ gibt es nicht." if quelle
                     else "Bitte einen Anbieter wählen.")
        return None
    titel = sammler.text(f"konto-{nr}-name", eintrag.get("name"), "Kontoname", 60)
    # Ein schon eingetragenes Konto behält seine Kennung (Anmeldung, Protokoll), auch
    # wenn es umbenannt wird. Eine Kennung, die es nicht gibt, wird nicht übernommen.
    kennung = eintrag.get("kennung")
    if not (isinstance(kennung, str) and (quelle, kennung) in alte):
        kennung = einstellungen.kennung_fuer(titel)
    bisher = alte.get((quelle, kennung))
    try:
        belege_ab = einstellungen.zeitraum_normal(eintrag.get("belege_ab"))
    except EinstellungsFehler:
        sammler.feld(f"konto-{nr}-ab", "Belege ab: bitte ein Datum als TT.MM.JJJJ, z. B. 01.01.2026.")
        belege_ab = "alle"
    ab = einstellungen.ab_datum(belege_ab)
    if ab is not None and ab > date.today():
        sammler.feld(f"konto-{nr}-ab", "Belege ab: Das Datum liegt in der Zukunft — dann würde nichts geholt.")
    # Ob ein Konto geholt wird, steuert der Haken im Reiter „Belege holen“ (sofort
    # gespeichert). Das Formular ändert das nicht: bisherige Konten behalten ihren Stand.
    return Konto(quelle=quelle, name=kennung, titel=titel, belege_ab=belege_ab,
                 aktiv=bisher.aktiv if bisher else eintrag.get("aktiv") is not False,
                 optionen=dict(bisher.optionen) if bisher else {})


def _port_lesen(sammler: _Sammler, port_roh, mail_an: bool) -> int:
    if port_roh is None or port_roh == "":
        if mail_an:
            sammler.feld("port", "Port: bitte ausfüllen (SSL meist 465, STARTTLS meist 587).")
        return 465
    zahl = isinstance(port_roh, int) or (isinstance(port_roh, str) and port_roh.strip().isdigit())
    if isinstance(port_roh, bool) or not zahl or not 1 <= int(port_roh) <= 65535:
        sammler.feld("port", "Port: bitte eine Zahl zwischen 1 und 65535.")
        return 465
    return int(port_roh)


def _empfaenger_lesen(sammler: _Sammler, roh) -> list[str]:
    roh = roh or []
    if isinstance(roh, str):
        roh = roh.split(",")
    if not isinstance(roh, list) or len(roh) > 20:
        raise Eingabefehler("Empfänger: ungültige Eingabe.")
    empfaenger = [e for e in (sammler.text("empfaenger", e, "Empfänger", 254) for e in roh) if e]
    falsch = [e for e in empfaenger if not einstellungen.mailadresse_ok(e)]
    if falsch:
        sammler.feld("empfaenger", f"Empfänger: „{falsch[0]}“ ist keine Mailadresse.")
    return empfaenger


def _mail_lesen(sammler: _Sammler, roh: dict, mail_an: bool, bisher: MailEinstellung) -> MailEinstellung:
    port = _port_lesen(sammler, roh.get("port"), mail_an)
    verschluesselung = sammler.text("verschluesselung", roh.get("verschluesselung") or "ssl",
                                    "Verschlüsselung", 10).lower()
    verschluesselung = _auswahl(sammler, "verschluesselung", verschluesselung, "ssl", ("ssl", "starttls"),
                                "Verschlüsselung: nur SSL oder STARTTLS — ohne gibt es keinen Versand.")
    empfaenger = _empfaenger_lesen(sammler, roh.get("empfaenger"))
    server = sammler.text("server", roh.get("server"), "Postausgangsserver", 253)
    benutzer = sammler.text("benutzer", roh.get("benutzer"), "Benutzername", 254)
    absender = sammler.text("absender", roh.get("absender"), "Absender", 254)
    if server and not _SERVERNAME.fullmatch(server):
        sammler.feld("server", "Postausgangsserver: bitte nur den Namen, z. B. smtp.example.com.")
    if absender and not einstellungen.mailadresse_ok(absender):
        sammler.feld("absender", f"Absender: „{absender}“ ist keine Mailadresse.")
    if mail_an:
        for name, wert, satz in (
            ("server", server, "Postausgangsserver: bitte ausfüllen, z. B. smtp.example.com."),
            ("benutzer", benutzer, "Benutzername: bitte ausfüllen (meist die Mailadresse)."),
            ("absender", absender, "Absender: bitte ausfüllen."),
            ("empfaenger", empfaenger, "Empfänger: bitte mindestens eine Adresse."),
        ):
            if not wert:
                sammler.feld(name, satz)
    erstversand = _auswahl(sammler, "erstversand", roh.get("erstversand"), bisher.erstversand,
                           einstellungen.ERSTVERSAND, "Bitte „nicht verschicken“ oder „auch verschicken“ wählen.")
    return MailEinstellung(
        server=server, port=port, verschluesselung=verschluesselung,
        benutzer=benutzer, absender=absender, empfaenger=empfaenger,
        passwort_eintrag=bisher.passwort_eintrag, erstversand=erstversand,
    )


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
