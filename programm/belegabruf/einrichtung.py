"""Einrichtung im Terminal: Anbieter, Konten, Belegordner abfragen."""

from __future__ import annotations

from pathlib import Path

from belegabruf import einstellungen, pfade, quellen
from belegabruf.einstellungen import Einstellungen, Konto


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
        beispiel = " (z. B. ein Zugang als Co-Gastgeber)" if quelle == "airbnb" else ""
        if not _ja(f"  Noch ein {anzeige}-Konto{beispiel}?", False):
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

    neu = Einstellungen(
        belegordner=ordner,
        konten=konten,
        ziele=alt.ziele if alt else ["ordner"],
        sichtbar=alt.sichtbar if alt else False,
    )
    ordner.mkdir(parents=True, exist_ok=True)
    datei = einstellungen.speichern(neu)
    print(f"\n✓ Gespeichert in {datei}")
    print("  (Die Datei kannst du auch mit einem Texteditor ändern.)")
    return neu
