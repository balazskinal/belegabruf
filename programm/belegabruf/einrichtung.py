"""Einrichtung im Terminal: Anbieter, Konten, Belegordner abfragen."""

from __future__ import annotations

from pathlib import Path

from belegabruf import einstellungen, pfade, quellen
from belegabruf.einstellungen import Einstellungen, Konto, SevDeskEinstellung


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


def _konten_abfragen(quelle: str, vorhanden: list[Konto]) -> list[Konto]:
    anzeige = quellen.anzeigename(quelle)
    if vorhanden:
        print(f"\n  Eingetragene {anzeige}-Konten:")
        for k in vorhanden:
            print(f"   - {k.name} ({'eingeschaltet' if k.aktiv else 'ausgeschaltet'})")
        if _ja(f"  {anzeige}-Konten so lassen?", True):
            return vorhanden
    konten: list[Konto] = []
    print(
        f"\n  Gib deinem {anzeige}-Konto einen Namen. Der Name ist nur für dich, damit du\n"
        "  mehrere Konten auseinanderhalten kannst (z. B. \"privat\" oder \"co-host\")."
    )
    while True:
        standard = "privat" if not konten else ""
        name = _frage(f"  Name für das {len(konten) + 1}. {anzeige}-Konto", standard)
        if not name:
            break
        if any(k.name == name for k in konten):
            print("  Diesen Namen gibt es schon.")
            continue
        konten.append(Konto(quelle=quelle, name=name))
        if not _ja(f"  Noch ein {anzeige}-Konto (z. B. ein Zugang als Co-Gastgeber)?", False):
            break
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
    vorher = sorted({k.quelle for k in alt.konten}) if alt else verfuegbar
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

    sevdesk_an, sevdesk_einst = _sevdesk_abfragen(alt)

    neu = Einstellungen(
        belegordner=ordner,
        konten=konten,
        ziele=["ordner", "sevdesk"] if sevdesk_an else ["ordner"],
        sichtbar=alt.sichtbar if alt else False,
        sevdesk=sevdesk_einst,
    )
    ordner.mkdir(parents=True, exist_ok=True)
    datei = einstellungen.speichern(neu)
    print(f"\n✓ Gespeichert in {datei}")
    print("  (Die Datei kannst du auch mit einem Texteditor ändern.)")
    return neu


# ── sevDesk ──────────────────────────────────────────────────────────────────


def _schluessel_eingeben(dienst: str, konto: str) -> bool:
    """Fragt den Schlüssel verdeckt ab (er erscheint nicht auf dem Bildschirm) und legt
    ihn in den Passwortspeicher. Er wird nie in eine Datei geschrieben."""
    import getpass

    from belegabruf.ziele import sevdesk

    print(
        "\n  Den API-Schlüssel findest du in sevDesk unter Einstellungen → Benutzer → API-Token.\n"
        "  Füge ihn hier ein und drück Enter. Man sieht beim Einfügen nichts — das ist Absicht."
    )
    try:
        wert = getpass.getpass("  API-Schlüssel (leer = abbrechen): ").strip()
    except (EOFError, KeyboardInterrupt):
        wert = ""
    if not wert:
        print("  Kein Schlüssel eingegeben.")
        return False
    sevdesk.schluessel_speichern(dienst, konto, wert)
    print("  ✓ Im Passwortspeicher deines Rechners abgelegt.")
    return True


def _sevdesk_abfragen(alt: Einstellungen | None) -> tuple[bool, SevDeskEinstellung]:
    from belegabruf.ziele import sevdesk

    einst = alt.sevdesk if alt else SevDeskEinstellung()
    vorher_an = bool(alt and alt.sevdesk_an)
    print(
        "\nSollen die Rechnungen zusätzlich als Entwurf nach sevDesk hochgeladen werden?\n"
        "  Eingetragen werden nur Datum, Rechnungsnummer und Lieferant; Betrag und Konto ergänzt\n"
        "  du in sevDesk. Das Programm lädt dort nur hoch — es liest, ändert oder löscht nichts.\n"
        "  Alles, was bis jetzt geholt ist, gilt dann als schon in sevDesk und wird nicht hochgeladen."
    )
    if not _ja("Nach sevDesk hochladen?", vorher_an):
        dienst, konto = einst.dienst_und_konto
        if vorher_an and dienst == "belegabruf" and sevdesk.schluessel_vorhanden(dienst, konto):
            if _ja("  Den sevDesk-Schlüssel aus dem Passwortspeicher löschen?", True):
                sevdesk.schluessel_loeschen(dienst, konto)
                print("  ✓ Gelöscht.")
        return False, einst

    print(
        "\n  Der Schlüssel liegt im Passwortspeicher deines Rechners (Mac: Schlüsselbund, Windows:\n"
        "  Anmeldeinformationsverwaltung), nie in einer Datei. Unter welchem Eintrag? Enter übernimmt\n"
        "  den Vorschlag. Hast du schon einen Eintrag, gib ihn als Dienst/Konto ein."
    )
    while True:
        eintrag = _frage("  Eintrag (Dienst/Konto)", einst.schluessel)
        dienst, _, konto = eintrag.partition("/")
        if dienst.strip() and konto.strip():
            break
        print("  Bitte in der Form Dienst/Konto, z. B. belegabruf/sevdesk.")
    einst = SevDeskEinstellung(schluessel=f"{dienst.strip()}/{konto.strip()}", steuerregel=einst.steuerregel)
    dienst, konto = einst.dienst_und_konto

    print(
        "\n  Jeder Entwurf braucht in sevDesk eine Steuerregel. Welche passt, hängt von deiner\n"
        "  Buchhaltung ab — frag im Zweifel deine Steuerberatung. Die Nummer steht z. B. in der\n"
        "  Vorlage deines Lieferanten Airbnb in sevDesk. Ohne Steuerregel wird nichts hochgeladen."
    )
    while True:
        regel = _frage("  Nummer der Steuerregel", einst.steuerregel)
        if regel.isdigit():
            break
        if not regel:
            print(
                "  ✗ Ohne Steuerregel kann sevDesk keinen Entwurf anlegen. Der Upload nach sevDesk bleibt\n"
                "    deshalb AUSGESCHALTET (alles andere ist gespeichert). Sobald du die Nummer weißt:\n"
                "    noch einmal „Einrichten“ doppelklicken."
            )
            return False, einst
        print("  Bitte nur die Nummer eingeben, z. B. 14.")
    einst = SevDeskEinstellung(schluessel=einst.schluessel, steuerregel=regel)

    if sevdesk.schluessel_vorhanden(dienst, konto):
        print("  Unter diesem Eintrag liegt schon ein Schlüssel.")
        if _ja("  Austauschen?", False):
            _schluessel_eingeben(dienst, konto)
    elif not _schluessel_eingeben(dienst, konto):
        print("  Ohne Schlüssel wird nichts hochgeladen. Du kannst ihn später über „Einrichten“ eingeben.")
        return True, einst

    print("  Prüfe den Schlüssel bei sevDesk …")
    try:
        meldung = sevdesk.schluessel_pruefen(sevdesk.Verbindung(sevdesk.schluessel_lesen(dienst, konto)))
    except Exception as fehler:  # noqa: BLE001
        meldung = f"Der Passwortspeicher ließ sich nicht lesen ({type(fehler).__name__})."
    if meldung:
        print(f"  ✗ {meldung}\n  Bitte noch einmal „Einrichten“ und den Schlüssel austauschen.")
    else:
        print("  ✓ Der Schlüssel funktioniert.")
    return True, einst
