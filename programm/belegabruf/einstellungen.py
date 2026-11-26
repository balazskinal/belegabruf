"""Einstellungsdatei lesen und schreiben (TOML, mit Erklärungen als Kommentar)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from belegabruf import pfade

JA = {"ja", "j", "yes", "y", "true", "1", "an", "ein"}
NEIN = {"nein", "n", "no", "false", "0", "aus"}


class EinstellungsFehler(Exception):
    """Die Einstellungsdatei fehlt oder ist nicht lesbar."""


def _wahrheitswert(wert: object, standard: bool = True) -> bool:
    if isinstance(wert, bool):
        return wert
    if wert is None:
        return standard
    text = str(wert).strip().lower()
    if text in JA:
        return True
    if text in NEIN:
        return False
    raise EinstellungsFehler(f"'{wert}' ist weder ja noch nein.")


#: Interne Kennung eines Kontos ohne Namen (je Anbieter höchstens eines).
STANDARD_KENNUNG = "standard"


@dataclass
class Konto:
    """Ein Konto bei einem Anbieter.

    ``name`` ist die **interne Kennung**: Daran hängen Browserprofil (Anmeldung),
    Protokoll und Zustand. Sie ändert sich nie von selbst. ``titel`` ist der Name für
    Menschen — leer heißt „kein Name“ (Anzeige nur „Airbnb“). Bei bisherigen Konten
    mit Namen sind beide gleich, die Pfade bleiben also, wie sie waren."""

    quelle: str
    name: str
    aktiv: bool = True
    optionen: dict = field(default_factory=dict)
    titel: str | None = None  # None = wie name
    belege_ab: str = "alle"  # Zeitraum, siehe ZEITRAEUME und ab_datum()

    def ab(self, heute: date | None = None) -> date | None:
        """Ab welchem Rechnungsdatum geholt wird (None = alle)."""
        return ab_datum(self.belege_ab, heute)

    @property
    def anzeigetitel(self) -> str:
        return self.name if self.titel is None else self.titel

    @property
    def bezeichnung(self) -> str:
        return f"{self.quelle} ({self.name})"

    @property
    def schluessel(self) -> str:
        """Eindeutig über alle Anbieter: „airbnb/privat“ (Quelle und Kennung)."""
        return f"{self.quelle}/{self.name}"

    @property
    def anzeige(self) -> str:
        """„Airbnb“ oder „Airbnb (Privat)“."""
        from belegabruf import quellen

        return kontoanzeige(quellen.anzeigename(self.quelle), self.anzeigetitel)


#: Zeitraum je Konto („Belege ab“). Relativ = ab dem 1. des Monats vor N Monaten,
#: gerechnet am Tag des Laufs; dazu ein festes Datum als TT.MM.JJJJ.
ZEITRAEUME = {"alle": None, "letzter-monat": 1, "letzte-3-monate": 3, "letzte-12-monate": 12}


def zeitraum_normal(wert: object) -> str:
    """Prüft und vereinheitlicht „Belege ab“: ein Schlüssel aus ZEITRAEUME oder TT.MM.JJJJ."""
    text = str(wert if wert is not None else "alle").strip().lower() or "alle"
    if text in ZEITRAEUME:
        return text
    try:
        return datetime.strptime(text, "%d.%m.%Y").date().strftime("%d.%m.%Y")
    except ValueError:
        raise EinstellungsFehler(
            f"belege_ab = \"{wert}\": erlaubt sind \"alle\", \"letzter-monat\", \"letzte-3-monate\", "
            "\"letzte-12-monate\" oder ein Datum als TT.MM.JJJJ.") from None


def ab_datum(wert: str, heute: date | None = None) -> date | None:
    """„letzte-3-monate“ am 25.11.2026 → 01.08.2026; „01.03.2026“ → 01.03.2026; „alle“ → None."""
    wert = zeitraum_normal(wert)
    if wert in ZEITRAEUME:
        monate = ZEITRAEUME[wert]
        if monate is None:
            return None
        heute = heute or date.today()
        index = heute.year * 12 + (heute.month - 1) - monate
        return date(index // 12, index % 12 + 1, 1)
    return datetime.strptime(wert, "%d.%m.%Y").date()


def kontoanzeige(anbieter: str, titel: str) -> str:
    return f"{anbieter} ({titel})" if titel else anbieter


def kennung_fuer(titel: str) -> str:
    """Die interne Kennung eines neuen Kontos: der Name, ohne Namen „standard“."""
    return titel.strip() or STANDARD_KENNUNG


#: Vorgabe für den Eintrag im Passwortspeicher des Betriebssystems: "Dienst/Konto".
STANDARD_PASSWORT_EINTRAG = "belegabruf/mail"


def dienst_und_konto(eintrag: str) -> tuple[str, str]:
    dienst, _, konto = eintrag.partition("/")
    return dienst.strip(), konto.strip()


@dataclass
class MailEinstellung:
    """Ziel mail. Hier steht nie das Passwort selbst, nur wo es im Passwortspeicher
    des Betriebssystems liegt (Schlüsselbund bzw. Anmeldeinformationsverwaltung)."""

    server: str = ""
    port: int = 465
    verschluesselung: str = "ssl"  # ssl | starttls — ohne Verschlüsselung kein Versand
    benutzer: str = ""
    absender: str = ""
    empfaenger: list[str] = field(default_factory=list)
    passwort_eintrag: str = STANDARD_PASSWORT_EINTRAG  # "Dienst/Konto"
    # Belege, die es beim Einschalten (bzw. für eine neue Adresse) schon gibt, und Belege aus
    # dem ersten Lauf eines neuen Kontos: "nicht" verschicken (nur ablegen) oder "auch".
    erstversand: str = "nicht"

    @property
    def dienst_und_konto(self) -> tuple[str, str]:
        return dienst_und_konto(self.passwort_eintrag)


@dataclass
class Einstellungen:
    belegordner: Path
    konten: list[Konto]
    ziele: list[str] = field(default_factory=lambda: ["ordner"])
    sichtbar: bool = False  # Abruf im sichtbaren Fenster (nur zur Fehlersuche)
    mail: MailEinstellung = field(default_factory=MailEinstellung)
    ablage: str = "jahr"  # Unterordner: "jahr" (<quelle>/<JJJJ>/) oder "monat" (<quelle>/<JJJJ>/<MM>/)

    @property
    def mail_an(self) -> bool:
        return "mail" in self.ziele

    def aktive_konten(self, quelle: str | None = None, konto: str | None = None) -> list[Konto]:
        """Die eingeschalteten Konten, auf Wunsch nur einer Quelle bzw. nur eines Kontos.

        ``konto`` ist der Name, wie er in der Oberfläche steht; die interne Kennung geht auch
        (für alte Aufrufe). Je Anbieter trifft es höchstens ein Konto: Passt der Name zu
        einem Konto, zählt nur das — eine gleichlautende Kennung eines anderen (umbenannten)
        Kontos wird dann nicht mehr mitgenommen."""
        auswahl = [k for k in self.konten if k.aktiv and (quelle is None or k.quelle == quelle)]
        if konto is None:
            return auswahl
        quellen_der_auswahl = dict.fromkeys(k.quelle for k in auswahl)
        treffer = (_eines_je_quelle([k for k in auswahl if k.quelle == q], konto) for q in quellen_der_auswahl)
        return [k for k in treffer if k is not None]


def _eines_je_quelle(konten: list[Konto], konto: str) -> Konto | None:
    """Das Konto eines Anbieters zu ``konto``: erst nach Name, dann nach Kennung."""
    for passt in (lambda k: k.anzeigetitel == konto, lambda k: k.name == konto):
        gefunden = next((k for k in konten if passt(k)), None)
        if gefunden is not None:
            return gefunden
    return None


def kollision_text(anbieter: str, a: Konto, b: Konto, kurz: str) -> str:
    """Meldung, wenn zwei Konten desselben Anbieters für das Programm dasselbe sind.
    Geht es um die Kennung „standard“ eines (früher) namenlosen Kontos, sagt sie das."""
    standard = [k for k in (a, b) if k.name == STANDARD_KENNUNG]
    if kurz == STANDARD_KENNUNG and standard:
        frueher = standard[0]
        anderes = b if frueher is a else a
        if not frueher.anzeigetitel:
            return (f"Bei {anbieter} gibt es schon ein Konto ohne Namen; das heißt intern „standard“. "
                    f"Gib einem der beiden einen Namen (nicht „Standard“).")
        return (f"Das Konto „{frueher.anzeigetitel}“ bei {anbieter} war früher ohne Namen und heißt intern "
                f"deshalb „standard“ (daran hängt seine Anmeldung). Bitte dem Konto "
                f"„{anderes.anzeigetitel or anderes.name}“ einen anderen Namen geben.")
    return (f"Die Konten „{a.anzeigetitel or a.name}“ und „{b.anzeigetitel or b.name}“ bei {anbieter} sind für "
            f"das Programm dasselbe (beide ergeben den Ordnernamen „{kurz}“). Bitte einem der beiden einen "
            "deutlich anderen Namen geben.")


def kontonamen_fehler(konten: list[Konto]) -> list[tuple[int, str]]:
    """Regeln für Kontonamen je Anbieter — die einzige Stelle dafür (Datei, Oberfläche,
    Terminal). Gibt je betroffenem Konto (Index in ``konten``) einen Satz zurück:

    * Ein einzelnes Konto braucht keinen Namen. Gibt es beim selben Anbieter mehrere,
      braucht jedes einen Namen.
    * Zwei Konten derselben Quelle dürfen weder denselben Ordnernamen (Kennung) noch
      zum Verwechseln ähnliche Namen haben: Profil (Anmeldung) und Protokoll hängen an
      ``pfade.kurzname``. Sonst teilten sich „Privat“ und „privat!“ die Anmeldung, und
      das zweite hielte die Rechnungen des ersten für schon geholt."""
    from belegabruf import quellen

    je_quelle: dict[str, list[int]] = {}
    for nr, k in enumerate(konten):
        je_quelle.setdefault(k.quelle, []).append(nr)
    fehler: list[tuple[int, str]] = []
    for quelle, nummern in je_quelle.items():
        anbieter = quellen.anzeigename(quelle)
        ohne_namen = [nr for nr in nummern if not konten[nr].anzeigetitel.strip()]
        if len(nummern) > 1 and ohne_namen:
            satz = f"Bei {anbieter} sind mehrere Konten eingetragen — dann braucht jedes einen Namen."
            fehler += [(nr, satz) for nr in ohne_namen]
            nummern = [nr for nr in nummern if nr not in ohne_namen]  # die übrigen gleich mitprüfen
        kennungen: dict[str, int] = {}
        titel: dict[str, int] = {}
        for nr in nummern:
            k = konten[nr]
            for verzeichnis, wert in ((kennungen, k.name), (titel, k.anzeigetitel or k.name)):
                kurz = pfade.kurzname(wert)
                if kurz in verzeichnis:
                    fehler.append((nr, kollision_text(anbieter, konten[verzeichnis[kurz]], k, kurz)))
                    break
                verzeichnis[kurz] = nr
    return fehler


def konten_unterscheidbar(konten: list[Konto]) -> None:
    """Wirft die erste Verletzung der Namensregeln (siehe ``kontonamen_fehler``)."""
    fehler = kontonamen_fehler(konten)
    if fehler:
        raise EinstellungsFehler(fehler[0][1])


def mailadresse_ok(adresse: str) -> bool:
    """Eine einzelne Mailadresse: etwas@etwas.tld, ohne Leerzeichen und Komma.
    Die Regel für neue Eingaben (Oberfläche, Terminal-Einrichtung). Beim Laden der Datei
    gilt bewusst weiter die mildere Regel von 2.0.0 (siehe ``_mail_lesen``)."""
    name, at, domain = adresse.partition("@")
    return bool(name and at and "@" not in domain and "." in domain.strip(".")
                and " " not in adresse and "," not in adresse)


def laden(datei: Path | None = None) -> Einstellungen:
    datei = datei or pfade.einstellungsdatei()
    if not datei.exists():
        raise EinstellungsFehler(f"Noch nicht eingerichtet (keine Datei {datei}).")
    return aus_text(datei.read_text(encoding="utf-8"), str(datei))


def pruefen(einst: Einstellungen) -> Einstellungen:
    """Prüft Einstellungen, die nicht aus der Datei kommen (z. B. aus der Bedienseite),
    nach denselben Regeln wie beim Laden. Gibt die geprüfte Fassung zurück."""
    return aus_text(als_text(einst), "Eingaben")


def aus_text(text: str, herkunft: str = "Einstellungen") -> Einstellungen:
    try:
        roh = tomllib.loads(text)
    except tomllib.TOMLDecodeError as fehler:
        raise EinstellungsFehler(f"Die Einstellungsdatei {herkunft} ist fehlerhaft: {fehler}") from fehler

    belegordner = Path(str(roh.get("belegordner") or pfade.standard_belegordner())).expanduser()
    konten = []
    for eintrag in roh.get("konto", []):
        if not isinstance(eintrag, dict) or not eintrag.get("quelle"):
            raise EinstellungsFehler("Jedes [[konto]] braucht 'quelle'.")
        titel = str(eintrag.get("name") or "").strip()
        kennung = str(eintrag.get("kennung") or "").strip() or kennung_fuer(titel)
        optionen = {k: v for k, v in eintrag.items() if k not in {"quelle", "name", "aktiv", "kennung", "belege_ab"}}
        konten.append(
            Konto(
                quelle=str(eintrag["quelle"]).strip().lower(),
                name=kennung,
                aktiv=_wahrheitswert(eintrag.get("aktiv"), True),
                optionen=optionen,
                titel=titel,
                belege_ab=zeitraum_normal(eintrag.get("belege_ab")),
            )
        )
    konten_unterscheidbar(konten)
    ziele = roh.get("ziele") or ["ordner"]
    if isinstance(ziele, str):
        ziele = [ziele]
    ziele = [str(z).strip().lower() for z in ziele]
    if "ordner" not in ziele:  # Der Belegordner ist immer dabei.
        ziele.insert(0, "ordner")
    mail = _mail_lesen(roh.get("mail") or {}, pruefen="mail" in ziele)
    ablage = str(roh.get("ablage") or "jahr").strip().lower()
    if ablage not in ABLAGEN:
        raise EinstellungsFehler(f"ablage = \"{ablage}\": erlaubt sind nur \"jahr\" und \"monat\".")
    return Einstellungen(
        belegordner=belegordner,
        konten=konten,
        ziele=ziele,
        sichtbar=_wahrheitswert(roh.get("sichtbar"), False),
        mail=mail,
        ablage=ablage,
    )


#: Unterordner im Belegordner: nach Jahr (wie bisher) oder nach Jahr und Monat.
ABLAGEN = ("jahr", "monat")


#: Erstversand: "nicht" = schon vorhandene und erste Belege nur ablegen; "auch" = auch mailen.
ERSTVERSAND = ("nicht", "auch")


def _mail_lesen(roh: object, pruefen: bool) -> MailEinstellung:
    if not isinstance(roh, dict):
        raise EinstellungsFehler("[mail] muss ein Abschnitt sein.")
    empfaenger = roh.get("empfaenger") or []
    if isinstance(empfaenger, str):
        empfaenger = [empfaenger]
    try:
        port = int(roh.get("port") or 465)
    except (TypeError, ValueError) as fehler:
        raise EinstellungsFehler(f"[mail] port = \"{roh.get('port')}\" ist keine Zahl.") from fehler
    mail = MailEinstellung(
        server=str(roh.get("server") or "").strip(),
        port=port,
        verschluesselung=str(roh.get("verschluesselung") or "ssl").strip().lower(),
        benutzer=str(roh.get("benutzer") or "").strip(),
        absender=str(roh.get("absender") or "").strip(),
        empfaenger=[str(e).strip() for e in empfaenger if str(e).strip()],
        passwort_eintrag=str(roh.get("passwort_eintrag") or STANDARD_PASSWORT_EINTRAG).strip(),
        erstversand=str(roh.get("erstversand") or "nicht").strip().lower(),
    )
    if mail.erstversand not in ERSTVERSAND:
        raise EinstellungsFehler(
            f"[mail] erstversand = \"{mail.erstversand}\": erlaubt sind nur \"nicht\" und \"auch\".")
    if mail.verschluesselung not in {"ssl", "starttls"}:
        raise EinstellungsFehler(
            f"[mail] verschluesselung = \"{mail.verschluesselung}\": erlaubt sind nur \"ssl\" und \"starttls\". "
            "Ohne Verschlüsselung wird keine Mail verschickt.")
    if not all(mail.dienst_und_konto):
        raise EinstellungsFehler(
            f"[mail] passwort_eintrag = \"{mail.passwort_eintrag}\" muss die Form \"Dienst/Konto\" haben.")
    for adresse in mail.empfaenger + ([mail.absender] if mail.absender else []):
        # Beim Laden die milde Regel von 2.0.0: Eine Datei, die bisher lesbar war, bleibt es
        # (sonst wirkte sie „nicht eingerichtet“, und neue Kennungen holten alles noch einmal).
        # Neue Eingaben in Formular und Terminal prüft mailadresse_ok streng.
        if "@" not in adresse or "," in adresse or " " in adresse:
            raise EinstellungsFehler(f"[mail] \"{adresse}\" ist keine Mailadresse.")
    if pruefen:
        fehlt = [n for n in ("server", "benutzer", "absender") if not getattr(mail, n)]
        if not mail.empfaenger:
            fehlt.append("empfaenger")
        if fehlt:
            raise EinstellungsFehler(
                "Bei ziele steht \"mail\", aber in [mail] fehlt: " + ", ".join(fehlt) + ".")
    return mail


def _toml_text(wert: str) -> str:
    return '"' + wert.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_schluessel(schluessel: str) -> str:
    return schluessel if re.fullmatch(r"[A-Za-z0-9_-]+", schluessel) else _toml_text(schluessel)


def _toml_wert(wert: object) -> str:
    """Ein Wert aus der Einstellungsdatei, wieder als TOML: Text, Zahl, ja/nein, Liste, Tabelle.
    (Früher wurde alles zu Text — eine Liste wie ["1", "2"] kam als "['1', '2']" zurück.)"""
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, (int, float)):
        return repr(wert)
    if isinstance(wert, list):
        return "[" + ", ".join(_toml_wert(w) for w in wert) + "]"
    if isinstance(wert, dict):
        return "{ " + ", ".join(f"{_toml_schluessel(str(k))} = {_toml_wert(v)}" for k, v in wert.items()) + " }"
    return _toml_text(str(wert))


def als_text(einst: Einstellungen) -> str:
    zeilen = [
        "# Einstellungen für Belegabruf",
        "#",
        "# Du kannst diese Datei mit jedem Texteditor ändern oder im Fenster „Belegabruf“",
        "# im Reiter „Einstellungen“. Zeilen mit # am Anfang sind nur Erklärungen.",
        "# Hier stehen keine Passwörter — angemeldet wird immer im Browserfenster.",
        "# Das Mail-Passwort liegt im Passwortspeicher des Betriebssystems, nie hier.",
        "",
        "# Wohin die Belege gespeichert werden.",
        f"belegordner = {_toml_text(str(einst.belegordner))}",
        "",
        "# Unterordner für neue Rechnungen: \"jahr\" (<anbieter>/<JJJJ>/, wie bisher) oder",
        "# \"monat\" (<anbieter>/<JJJJ>/<MM>/), jeweils nach Rechnungsdatum. Bereits abgelegte",
        "# Belege bleiben, wo sie sind.",
        f"ablage = {_toml_text(einst.ablage)}",
        "",
        "# Wohin die Belege geliefert werden: \"ordner\" (der Belegordner oben, immer dabei)",
        "# und auf Wunsch \"mail\" (Versand per Mail, siehe Abschnitt [mail] unten).",
        "ziele = [" + ", ".join(_toml_text(z) for z in einst.ziele) + "]",
        "",
        "# Abruf im sichtbaren Browserfenster? Nur zur Fehlersuche: \"ja\".",
        f"sichtbar = {_toml_text('ja' if einst.sichtbar else 'nein')}",
        "",
        "# Ein Block [[konto]] je Konto. Mehrere Konten bei derselben Quelle sind",
        "# erlaubt (z. B. ein eigenes und ein Co-Gastgeber-Konto) — jedes bekommt",
        "# seine eigene Anmeldung. Mit aktiv = \"nein\" wird ein Konto übersprungen.",
        "# name darf leer bleiben, solange es nur ein Konto bei der Quelle gibt.",
        "# kennung (falls vorhanden) bitte nicht ändern: Daran hängt die Anmeldung.",
        "# belege_ab: \"alle\" (Vorgabe), \"letzter-monat\", \"letzte-3-monate\", \"letzte-12-monate\"",
        "# (jeweils ab dem 1. des Monats) oder ein Datum als \"TT.MM.JJJJ\". Ältere Belege werden nicht",
        "# geholt und nicht vermerkt — wird der Zeitraum erweitert, kommen sie beim nächsten Lauf.",
    ]
    for konto in einst.konten:
        titel = konto.anzeigetitel
        zeilen += [
            "",
            "[[konto]]",
            f"quelle = {_toml_text(konto.quelle)}",
            f"name = {_toml_text(titel)}",
        ]
        if konto.name != kennung_fuer(titel):
            zeilen.append(f"kennung = {_toml_text(konto.name)}")
        zeilen += [
            f"aktiv = {_toml_text('ja' if konto.aktiv else 'nein')}",
        ]
        if konto.belege_ab != "alle":
            zeilen.append(f"belege_ab = {_toml_text(konto.belege_ab)}")
        for schluessel, wert in konto.optionen.items():
            zeilen.append(f"{_toml_schluessel(schluessel)} = {_toml_wert(wert)}")
    m = einst.mail
    zeilen += [
        "",
        "# Nur wichtig, wenn bei ziele \"mail\" steht: Jede neue Rechnung geht als eigene Mail",
        "# mit PDF-Anhang an jeden Empfänger. verschluesselung: \"ssl\" (meist Port 465) oder",
        "# \"starttls\" (meist Port 587). passwort_eintrag: wo das Passwort im Passwortspeicher",
        "# liegt, als \"Dienst/Konto\" (nicht das Passwort selbst!). Ändern: belege einrichten.",
        "[mail]",
        f"server = {_toml_text(m.server)}",
        f"port = {int(m.port)}",
        f"verschluesselung = {_toml_text(m.verschluesselung)}",
        f"benutzer = {_toml_text(m.benutzer)}",
        f"absender = {_toml_text(m.absender)}",
        "empfaenger = [" + ", ".join(_toml_text(e) for e in m.empfaenger) + "]",
        f"passwort_eintrag = {_toml_text(m.passwort_eintrag)}",
        "# Belege, die es beim Einschalten bzw. für eine neue Adresse schon gibt, und Belege aus dem",
        "# ersten Lauf eines neuen Kontos: \"nicht\" verschicken (nur ablegen) oder \"auch\" verschicken.",
        f"erstversand = {_toml_text(m.erstversand)}",
    ]
    return "\n".join(zeilen) + "\n"


BEKANNT_OBEN = {"belegordner", "ziele", "sichtbar", "konto", "mail", "ablage"}
BEKANNT_MAIL = {"server", "port", "verschluesselung", "benutzer", "absender", "empfaenger", "passwort_eintrag",
                "erstversand"}
#: Kommentarzeilen, die frühere Versionen selbst geschrieben haben (keine „eigenen“).
FRUEHERE_KOMMENTARE = {
    # bis 2.0.0 (Startdatei „Einrichten“)
    '# Du kannst diese Datei mit jedem Texteditor ändern oder einfach noch einmal',
    '# "Einrichten" doppelklicken. Zeilen mit # am Anfang sind nur Erklärungen.',
    '# liegt, als "Dienst/Konto" (nicht das Passwort selbst!). Ändern über "Einrichten".',
    '# Wohin die Belege geliefert werden. Version 1 kennt nur "ordner"',
    '# (der Belegordner oben). Später kommt "sevdesk" dazu.',
}


def fremde_inhalte(datei: Path | None = None) -> list[str]:
    """Was in der vorhandenen Einstellungsdatei steht, das beim Neuschreiben verloren
    ginge: eigene Kommentare und unbekannte Einträge. (Zusätzliche Angaben in einem
    [[konto]] bleiben erhalten.) Leere Liste, wenn nichts verloren ginge."""
    datei = datei or pfade.einstellungsdatei()
    if not datei.exists():
        return []
    text = datei.read_text(encoding="utf-8")
    try:
        roh = tomllib.loads(text)
        einst = aus_text(text)
    except (tomllib.TOMLDecodeError, EinstellungsFehler):
        return ["die Datei ist fehlerhaft und wird ersetzt"]
    funde = [f"Eintrag „{k}“" for k in roh if k not in BEKANNT_OBEN]
    mail_roh = roh.get("mail") if isinstance(roh.get("mail"), dict) else {}
    funde += [f"Eintrag „mail.{k}“" for k in mail_roh if k not in BEKANNT_MAIL]
    eigene = {z.strip() for z in text.splitlines() if z.strip().startswith("#")}
    vorlage = {z.strip() for z in als_text(einst).splitlines() if z.strip().startswith("#")}
    if eigene - vorlage - FRUEHERE_KOMMENTARE:
        funde.append("eigene Kommentare")
    return funde


def sichern(datei: Path | None = None) -> Path | None:
    """Legt eine Kopie der vorhandenen Datei daneben (einstellungen.toml.vorher)."""
    import shutil
    from datetime import datetime

    datei = datei or pfade.einstellungsdatei()
    if not datei.exists():
        return None
    ziel = datei.with_name(datei.name + ".vorher")
    if ziel.exists():
        ziel = datei.with_name(f"{datei.name}.vorher-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(datei, ziel)
    return ziel


def speichern(einst: Einstellungen, datei: Path | None = None) -> Path:
    """Schreibt atomar: erst eine Zwischendatei, auf die Platte gebracht (fsync), dann
    ersetzen. So liegt nie eine halbe Einstellungsdatei da, auch wenn der Rechner
    mittendrin ausgeht."""
    import os

    datei = datei or pfade.einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    zwischen = datei.with_name(datei.name + ".teil")
    with open(zwischen, "w", encoding="utf-8") as f:
        f.write(als_text(einst))
        f.flush()
        os.fsync(f.fileno())
    os.replace(zwischen, datei)
    return datei
