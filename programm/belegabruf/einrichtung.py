"""Einrichtung im Terminal: Anbieter, Konten, Belegordner abfragen."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from belegabruf import einstellungen, pfade, quellen
from belegabruf.einstellungen import Einstellungen, Konto, MailEinstellung


def _frage(text: str, standard: str = "") -> str:
    zusatz = f" [{standard}]" if standard else ""
    try:
        antwort = input(f"{text}{zusatz}: ").strip()
    except EOFError:
        antwort = ""
    return antwort or standard


def _ja(text: str, standard: bool) -> bool:
    auswahl = "J/n" if standard else "j/N"
    while True:
        antwort = _frage(f"{text} ({auswahl})").lower()
        if not antwort:
            return standard
        if antwort in einstellungen.JA:
            return True
        if antwort in einstellungen.NEIN:
            return False
        print("  Bitte j oder n eingeben.")


def _titelschluessel(titel: str) -> str:
    """Vergleichsschlüssel für Namen; ein leerer Name bleibt leer (nicht „standard“)."""
    return pfade.kurzname(titel) if titel.strip() else ""


def _konten_abfragen(quelle: str, vorhanden: list[Konto]) -> list[Konto]:
    anzeige = quellen.anzeigename(quelle)
    if vorhanden:
        print(f"\n  Eingetragene {anzeige}-Konten:")
        for k in vorhanden:
            print(f"   - {k.anzeigetitel or '(ohne Namen)'} ({'eingeschaltet' if k.aktiv else 'ausgeschaltet'})")
        if _ja(f"  {anzeige}-Konten so lassen?", True):
            return vorhanden
    # Wer einen bisherigen Namen wieder eingibt (oder beim namenlosen Konto wieder nichts),
    # behält dessen Kennung — also Anmeldung und Protokoll — und seine übrigen Angaben.
    # Die Kennung eines bestehenden Kontos ändert sich hier nie stillschweigend.
    bisher: dict[str, Konto] = {}
    for k in vorhanden:
        bisher.setdefault(_titelschluessel(k.anzeigetitel), k)
    if len(vorhanden) == 1:
        # Nur ein Konto bisher: Enter ohne Namen meint dieses Konto, auch wenn es einen Namen hatte.
        bisher.setdefault("", vorhanden[0])

    def konto(titel: str) -> Konto:
        alt = bisher.get(_titelschluessel(titel))
        if alt is not None:
            return replace(alt, titel=titel, optionen=dict(alt.optionen))
        return Konto(quelle=quelle, name=einstellungen.kennung_fuer(titel), titel=titel)

    def passt(liste: list[Konto]) -> bool:
        try:
            einstellungen.konten_unterscheidbar(liste)
            return True
        except einstellungen.EinstellungsFehler as fehler:
            print(f"  {fehler}")
            return False

    print(f"\n  Ein Name ist nur nötig, wenn du mehrere {anzeige}-Konten hast (z. B. \"privat\" und\n"
          "  \"co-host\"). Bei nur einem Konto einfach Enter drücken.")
    konten: list[Konto] = []
    while True:
        if not konten:
            neu = konto(_frage(f"  Name für das {anzeige}-Konto (leer = ohne Namen)"))
        else:
            name = _frage(f"  Name für das {len(konten) + 1}. {anzeige}-Konto (leer = fertig)")
            if not name:
                break
            neu = konto(name)
        if not passt(konten + [neu]):
            continue
        konten.append(neu)
        beispiel = " (z. B. ein Zugang als Co-Gastgeber)" if quelle == "airbnb" else ""
        if not _ja(f"  Noch ein {anzeige}-Konto{beispiel}?", False):
            break
        while not konten[0].anzeigetitel:
            # Die Kennung (und damit die Anmeldung) des ersten Kontos bleibt dabei gleich.
            name = _frage(f"  Dann braucht auch das 1. {anzeige}-Konto einen Namen")
            if name and passt([Konto(quelle=quelle, name=konten[0].name, titel=name)]):
                konten[0].titel = name
    return konten


def einrichten() -> Einstellungen:
    print("\nBelegabruf einrichten")
    print("─────────────────────")
    print("Ein paar Fragen, dann ist alles eingestellt. Enter übernimmt den Vorschlag in [Klammern].")
    try:
        alt = einstellungen.laden()
    except einstellungen.EinstellungsFehler:
        alt = None

    verfuegbar = list(quellen.QUELLEN)
    print("\nWelche Anbieter willst du abrufen?")
    for nr, name in enumerate(verfuegbar, 1):
        print(f"  {nr}) {quellen.anzeigename(name)}")
    vorher = sorted({k.quelle for k in alt.konten}) if alt else verfuegbar[:1]
    standard = ",".join(str(verfuegbar.index(q) + 1) for q in vorher if q in verfuegbar) or "1"
    while True:
        antwort = _frage("Nummern, mit Komma getrennt", standard)
        try:
            gewaehlt = [verfuegbar[int(t) - 1] for t in antwort.replace(" ", "").split(",") if t]
            if gewaehlt and all(int(t) >= 1 for t in antwort.replace(" ", "").split(",") if t):
                break
        except (ValueError, IndexError):
            pass
        print("  Bitte die Nummern aus der Liste eingeben.")

    konten: list[Konto] = []
    for quelle in gewaehlt:
        vorhanden = [k for k in (alt.konten if alt else []) if k.quelle == quelle]
        konten += _konten_abfragen(quelle, vorhanden)
    # Konten von abgewählten Anbietern bleiben drin, aber ausgeschaltet.
    for k in alt.konten if alt else []:
        if k.quelle not in gewaehlt:
            k.aktiv = False
            konten.append(k)

    standard_ordner = str(alt.belegordner if alt else pfade.standard_belegordner())
    print("\nWo sollen die Belege hin? (Ordner wird angelegt, falls es ihn noch nicht gibt.)")
    ordner = Path(_frage("Belegordner", standard_ordner)).expanduser()

    mail_an, mail_einst = _mail_abfragen(alt)

    neu = Einstellungen(
        belegordner=ordner,
        konten=konten,
        ziele=["ordner", "mail"] if mail_an else ["ordner"],
        sichtbar=alt.sichtbar if alt else False,
        mail=mail_einst,
        ablage=alt.ablage if alt else "jahr",
    )
    ordner.mkdir(parents=True, exist_ok=True)
    datei = einstellungen.speichern(neu)
    print(f"\n✓ Gespeichert in {datei}")
    print("  (Die Datei kannst du auch mit einem Texteditor ändern.)")
    return neu


# ── Mail ─────────────────────────────────────────────────────────────────────


def _adresse_ok(adresse: str) -> bool:
    name, at, domain = adresse.partition("@")
    return bool(name and at and "." in domain and " " not in adresse and "," not in adresse)


def _passwort_eingeben(dienst: str, konto: str) -> bool:
    """Fragt das Passwort verdeckt ab (es erscheint nicht auf dem Bildschirm) und legt
    es in den Passwortspeicher. Es wird nie in eine Datei geschrieben."""
    import getpass

    from belegabruf.ziele import mail

    print("  Gib das Passwort für das Mailkonto ein (bei Gmail/Microsoft 365: das App-Passwort, siehe\n"
          "  README). Man sieht beim Tippen oder Einfügen nichts — das ist Absicht.")
    try:
        wert = getpass.getpass("  Passwort (leer = abbrechen): ")
    except (EOFError, KeyboardInterrupt):
        wert = ""
    if not wert:
        print("  Kein Passwort eingegeben.")
        return False
    mail.passwort_speichern(dienst, konto, wert)
    print("  ✓ Im Passwortspeicher deines Rechners abgelegt.")
    return True


def _mail_abfragen(alt: Einstellungen | None) -> tuple[bool, MailEinstellung]:
    from belegabruf.ziele import mail

    einst = alt.mail if alt else MailEinstellung()
    vorher_an = bool(alt and alt.mail_an)
    print(
        "\nRechnungen zusätzlich per Mail verschicken?\n"
        "  Jede neue Rechnung geht dann als eigene Mail mit PDF an die Adressen, die du angibst —\n"
        "  z. B. an die Belegadresse deines Buchhaltungsprogramms oder an deine Steuerberatung.\n"
        "  Was bis jetzt schon geholt ist, gilt für eine neue Adresse als verschickt und geht nicht raus.\n"
        "  Wichtig: Das Programm bringt keinen Versanddienst mit. Verschickt wird über DEIN eigenes\n"
        "  Postfach — dafür fragt es gleich nach dessen Zugangsdaten (Postausgangsserver, Passwort)."
    )
    if not _ja("Per Mail verschicken?", vorher_an):
        dienst, konto = einst.dienst_und_konto
        if vorher_an and dienst == "belegabruf" and mail.passwort_vorhanden(dienst, konto):
            if _ja("  Das Mail-Passwort aus dem Passwortspeicher löschen?", True):
                mail.passwort_loeschen(dienst, konto)
                print("  ✓ Gelöscht.")
        return False, einst

    print("\n  Die Angaben findest du bei deinem Mailanbieter unter „SMTP“ oder „Postausgangsserver“.")
    server = ""
    while not server:
        server = _frage("  Postausgangsserver (SMTP), z. B. smtp.example.com", einst.server)
    print("  Verschlüsselung: 1) SSL (meist Port 465)  2) STARTTLS (meist Port 587). Ohne gibt es keinen Versand.")
    while True:
        wahl = _frage("  Nummer", "2" if einst.verschluesselung == "starttls" else "1")
        if wahl in {"1", "2"}:
            break
        print("  Bitte 1 oder 2.")
    verschluesselung = "ssl" if wahl == "1" else "starttls"
    port_vorschlag = einst.port if einst.server and einst.verschluesselung == verschluesselung else (
        465 if verschluesselung == "ssl" else 587)
    while True:
        port = _frage("  Port", str(port_vorschlag))
        if port.isdigit():
            break
        print("  Bitte eine Zahl.")
    benutzer = ""
    while not benutzer:
        benutzer = _frage("  Benutzername (meist die Mailadresse)", einst.benutzer)
    absender = ""
    while not _adresse_ok(absender):
        absender = _frage("  Absenderadresse", einst.absender or (benutzer if _adresse_ok(benutzer) else ""))
    while True:
        antwort = _frage("  Empfänger (mehrere mit Komma trennen)", ", ".join(einst.empfaenger))
        empfaenger = [a.strip() for a in antwort.split(",") if a.strip()]
        falsch = [a for a in empfaenger if not _adresse_ok(a)]
        if empfaenger and not falsch:
            break
        print("  Bitte gültige Mailadressen" + (f" (nicht: {', '.join(falsch)})" if falsch else "") + ".")
    print("\n  Das Passwort liegt im Passwortspeicher deines Rechners (Mac: Schlüsselbund, Windows:\n"
          "  Anmeldeinformationsverwaltung), nie in einer Datei. Unter welchem Eintrag? Enter übernimmt\n"
          "  den Vorschlag.")
    while True:
        eintrag = _frage("  Eintrag (Dienst/Konto)", einst.passwort_eintrag)
        dienst, _, konto = eintrag.partition("/")
        if dienst.strip() and konto.strip():
            break
        print("  Bitte in der Form Dienst/Konto, z. B. belegabruf/mail.")
    einst = MailEinstellung(server=server, port=int(port), verschluesselung=verschluesselung,
                            benutzer=benutzer, absender=absender, empfaenger=empfaenger,
                            passwort_eintrag=f"{dienst.strip()}/{konto.strip()}")
    dienst, konto = einst.dienst_und_konto

    if mail.passwort_vorhanden(dienst, konto):
        print("  Unter diesem Eintrag liegt schon ein Passwort.")
        if _ja("  Austauschen?", False):
            _passwort_eingeben(dienst, konto)
    elif not _passwort_eingeben(dienst, konto):
        print("  Ohne Passwort wird nichts verschickt. Du kannst es später über „Einrichten“ eingeben.")
        return True, einst

    print("  Prüfe die Anmeldung am Mailserver (es wird keine Mail verschickt) …")
    try:
        meldung = mail.anmeldung_pruefen(einst, mail.passwort_lesen(dienst, konto))
    except Exception as fehler:  # noqa: BLE001
        meldung = f"Der Passwortspeicher ließ sich nicht lesen ({type(fehler).__name__})."
    if meldung:
        print(f"  ✗ {meldung}\n  Bitte noch einmal „Einrichten“ und die Angaben prüfen.")
    else:
        print("  ✓ Anmeldung klappt.")
    return True, einst
