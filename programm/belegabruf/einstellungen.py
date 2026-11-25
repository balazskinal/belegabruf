"""Einstellungsdatei lesen und schreiben (TOML, mit Erklärungen als Kommentar)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
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


@dataclass
class Konto:
    quelle: str
    name: str
    aktiv: bool = True
    optionen: dict = field(default_factory=dict)

    @property
    def bezeichnung(self) -> str:
        return f"{self.quelle} ({self.name})"


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

    @property
    def mail_an(self) -> bool:
        return "mail" in self.ziele

    def aktive_konten(self, quelle: str | None = None, konto: str | None = None) -> list[Konto]:
        return [
            k for k in self.konten
            if k.aktiv
            and (quelle is None or k.quelle == quelle)
            and (konto is None or k.name == konto)
        ]


def konten_unterscheidbar(konten: list[Konto]) -> None:
    """Zwei Konten derselben Quelle dürfen nicht denselben Ordnernamen ergeben: Profil
    (Anmeldung) und Protokoll hängen an ``pfade.kurzname``. Sonst teilten sich „Privat“
    und „privat!“ die Anmeldung, und das zweite hielte die Rechnungen des ersten für
    schon geholt."""
    gesehen: dict[tuple[str, str], str] = {}
    for k in konten:
        schluessel = (k.quelle, pfade.kurzname(k.name))
        if schluessel in gesehen:
            raise EinstellungsFehler(
                f"Die Konten „{gesehen[schluessel]}“ und „{k.name}“ bei {k.quelle} sind für das Programm "
                f"dasselbe (beide ergeben den Ordnernamen „{schluessel[1]}“). Bitte einem der beiden einen "
                "deutlich anderen Namen geben.")
        gesehen[schluessel] = k.name


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
        if not eintrag.get("quelle") or not eintrag.get("name"):
            raise EinstellungsFehler("Jedes [[konto]] braucht 'quelle' und 'name'.")
        optionen = {k: v for k, v in eintrag.items() if k not in {"quelle", "name", "aktiv"}}
        konten.append(
            Konto(
                quelle=str(eintrag["quelle"]).strip().lower(),
                name=str(eintrag["name"]).strip(),
                aktiv=_wahrheitswert(eintrag.get("aktiv"), True),
                optionen=optionen,
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
    return Einstellungen(
        belegordner=belegordner,
        konten=konten,
        ziele=ziele,
        sichtbar=_wahrheitswert(roh.get("sichtbar"), False),
        mail=mail,
    )


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
    )
    if mail.verschluesselung not in {"ssl", "starttls"}:
        raise EinstellungsFehler(
            f"[mail] verschluesselung = \"{mail.verschluesselung}\": erlaubt sind nur \"ssl\" und \"starttls\". "
            "Ohne Verschlüsselung wird keine Mail verschickt.")
    if not all(mail.dienst_und_konto):
        raise EinstellungsFehler(
            f"[mail] passwort_eintrag = \"{mail.passwort_eintrag}\" muss die Form \"Dienst/Konto\" haben.")
    for adresse in mail.empfaenger + ([mail.absender] if mail.absender else []):
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


def als_text(einst: Einstellungen) -> str:
    zeilen = [
        "# Einstellungen für Belegabruf",
        "#",
        "# Du kannst diese Datei mit jedem Texteditor ändern oder einfach noch einmal",
        "# \"Einrichten\" doppelklicken. Zeilen mit # am Anfang sind nur Erklärungen.",
        "# Hier stehen keine Passwörter — angemeldet wird immer im Browserfenster.",
        "# Das Mail-Passwort liegt im Passwortspeicher des Betriebssystems, nie hier.",
        "",
        "# Wohin die Belege gespeichert werden.",
        f"belegordner = {_toml_text(str(einst.belegordner))}",
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
    ]
    for konto in einst.konten:
        zeilen += [
            "",
            "[[konto]]",
            f"quelle = {_toml_text(konto.quelle)}",
            f"name = {_toml_text(konto.name)}",
            f"aktiv = {_toml_text('ja' if konto.aktiv else 'nein')}",
        ]
        for schluessel, wert in konto.optionen.items():
            zeilen.append(f"{schluessel} = {_toml_text(str(wert))}")
    m = einst.mail
    zeilen += [
        "",
        "# Nur wichtig, wenn bei ziele \"mail\" steht: Jede neue Rechnung geht als eigene Mail",
        "# mit PDF-Anhang an jeden Empfänger. verschluesselung: \"ssl\" (meist Port 465) oder",
        "# \"starttls\" (meist Port 587). passwort_eintrag: wo das Passwort im Passwortspeicher",
        "# liegt, als \"Dienst/Konto\" (nicht das Passwort selbst!). Ändern über \"Einrichten\".",
        "[mail]",
        f"server = {_toml_text(m.server)}",
        f"port = {int(m.port)}",
        f"verschluesselung = {_toml_text(m.verschluesselung)}",
        f"benutzer = {_toml_text(m.benutzer)}",
        f"absender = {_toml_text(m.absender)}",
        "empfaenger = [" + ", ".join(_toml_text(e) for e in m.empfaenger) + "]",
        f"passwort_eintrag = {_toml_text(m.passwort_eintrag)}",
    ]
    return "\n".join(zeilen) + "\n"


BEKANNT_OBEN = {"belegordner", "ziele", "sichtbar", "konto", "mail"}
BEKANNT_MAIL = {"server", "port", "verschluesselung", "benutzer", "absender", "empfaenger", "passwort_eintrag"}
#: Kommentarzeilen, die frühere Versionen selbst geschrieben haben (keine „eigenen“).
FRUEHERE_KOMMENTARE = {
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
