"""Kommandozeile.

    belege oberflaeche          Bedienseite im Browserfenster (Doppelklick auf „Belegabruf Mac/Windows“)
    belege start                Menü im Terminal: prüfen, anmelden lassen, holen
    belege einrichten           Fragen beantworten, Einstellungsdatei schreiben
    belege pruefen [--json]     Sind die Konten angemeldet?
    belege anmelden --quelle airbnb [--konto NAME]
    belege holen [--quelle airbnb] [--konto NAME] [--json] [--fehlende]
                                Unbeaufsichtigt holen, öffnet nie ein Fenster
                                (für spätere Automatisierung, z. B. n8n)

Exit-Codes von "holen" und "pruefen": 0 alles gut, 2 Anmeldung nötig/abgelaufen, nicht alles
geholt oder nicht alles verschickt (später noch einmal), 1 Fehler.
"""

from __future__ import annotations

import argparse
import json
import sys

from belegabruf import __version__, ablauf, aktualisierung, einrichtung, einstellungen, pfade, zustand
from belegabruf.einstellungen import EinstellungsFehler


def _konsole_vorbereiten() -> None:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


# ── Start per Doppelklick ────────────────────────────────────────────────────


def _warte_enter(text: str = "\nDrück Enter, um das Fenster zu schließen.") -> None:
    try:
        input(text)
    except EOFError:
        pass


def start() -> int:
    try:
        einst = einstellungen.laden()
    except EinstellungsFehler:
        print("Belegabruf ist noch nicht eingerichtet — das machen wir jetzt.")
        einst = einrichtung.einrichten()

    uebernommen = ablauf.uebernahme(einst)
    if uebernommen:
        print(
            f"\nDas Protokoll aus Version 1 ist übernommen ({uebernommen} Einträge). Es liegt jetzt bei den\n"
            "Einstellungen (Ordner protokolle) und nicht mehr im Belegordner."
        )

    nachholen = False
    while True:
        konten = einst.aktive_konten()
        print(f"\nBelegabruf {__version__}")
        print("═" * (11 + len(__version__)))
        if konten:
            print("Heute werden geholt: " + ", ".join(
                k.anzeige for k in konten))
        else:
            print("Es ist kein Konto eingeschaltet.")
        print(f"Belegordner: {einst.belegordner}")

        neuer = aktualisierung.neuere_version()
        if neuer:
            print(f"\nHinweis: Es gibt eine neuere Version ({neuer}). Herunterladen unter")
            print(f"  {aktualisierung.NEUESTE_SEITE}")
            print(f"  (alten Ordner belegabruf-v… löschen, neues ZIP auspacken, \"{pfade.starter()}\" doppelklicken —\n"
                  "   Einstellungen, Anmeldungen und Protokolle bleiben erhalten.)")

        for k in konten:
            if k.quelle != "airbnb":  # nur Airbnb zeigt bloß die letzten 12 Monate
                continue
            zuletzt = zustand.zu_lange_her(k.quelle, k.name)
            if zuletzt:
                print(
                    f"\n⚠ Achtung: {k.anzeige} lief zuletzt am "
                    f"{zuletzt:%d.%m.%Y}. Airbnb zeigt nur die letzten 12 Monate —\n"
                    "  ältere Rechnungen sind sonst irgendwann weg. Am besten jeden Monat holen."
                )

        try:
            wahl = input("\nEnter = los · E = Einstellungen · Q = beenden: ").strip().lower()
        except EOFError:
            wahl = ""
        if wahl in {"q", "x"}:
            return 0
        if wahl == "e":
            auswahl = _einstellungsmenue(einst, konten)
            if auswahl == "fragen":
                einst = einrichtung.einrichten()
                continue
            if auswahl != "nachholen":
                continue
            nachholen = True
        if not konten:
            print("Ohne eingeschaltetes Konto gibt es nichts zu tun. Mit E kannst du eins eintragen.")
            continue
        break

    code = lauf(einst, konten, nachholen=nachholen)
    _warte_enter()
    return code


def _einstellungsmenue(einst, konten) -> str:
    fehlen = sum(ablauf.fehlende_dateien(einst, k) for k in konten)
    print("\nEinstellungen")
    print("─────────────")
    print("  1) Einstellungen ändern (Anbieter, Konten, Belegordner)")
    print(f"  2) Fehlende Dateien neu holen — {fehlen} schon geholte Rechnung(en) fehlen im Belegordner")
    print("     (geht nur, solange Airbnb sie noch anbietet: die letzten 12 Monate)")
    try:
        wahl = input("Nummer, oder Enter = zurück: ").strip()
    except EOFError:
        wahl = ""
    if wahl == "1":
        return "fragen"
    if wahl == "2":
        if not fehlen:
            print("Es fehlt nichts — alle geholten Rechnungen liegen im Belegordner.")
            return ""
        return "nachholen"
    return ""


def lauf(einst, konten, nachholen: bool = False) -> int:
    melden = print

    # 1. Alle Konten prüfen
    print("\nPrüfe die Anmeldungen …")
    nicht_angemeldet = []
    for k in konten:
        status = ablauf.sitzung_pruefen(k)
        anzeige = k.anzeige
        if status == "angemeldet":
            print(f"  ✓ {anzeige}: angemeldet")
        else:
            print(f"  · {anzeige}: {'nicht angemeldet' if status == 'abgemeldet' else status}")
            nicht_angemeldet.append(k)

    # 2. Erst alle Anmeldefenster
    ausgelassen = set()
    for k in nicht_angemeldet:
        anzeige = k.anzeige
        print(f"\nAnmeldung für {anzeige}: Gleich öffnet sich ein Browserfenster.")
        if ablauf.anmelden(k, melden):
            print(f"  ✓ {anzeige}: angemeldet")
        else:
            print(f"  ✗ {anzeige}: Anmeldung nicht erkannt — dieses Konto wird heute ausgelassen.")
            ausgelassen.add(k.schluessel)

    # 3. Abruf unbeaufsichtigt, nacheinander
    if nachholen:
        print("\nFehlende Dateien werden neu geholt (dazu auch alles, was neu ist).")
    print("\nJetzt werden die Belege geholt. Das dauert ein paar Minuten —")
    print("du musst nichts tun und kannst den Rechner nebenbei normal benutzen.")

    def bereit(k) -> bool:
        if k.schluessel in ausgelassen:
            return False
        print(f"\n{k.anzeige}:")
        return True

    ergebnisse = ablauf.alle_abrufen(einst, konten, bereit, lambda k: lambda t: print("  " + t),
                                     nachholen=nachholen)

    # 4. Zusammenfassung
    print(ablauf.zusammenfassung(ergebnisse, einst.belegordner))
    return ablauf.exit_code(ergebnisse)


# ── Einzelbefehle (auch für Automatisierung) ────────────────────────────────


def _konten_oder_fehler(args) -> tuple[einstellungen.Einstellungen, list]:
    einst = einstellungen.laden()
    konten = einst.aktive_konten(args.quelle, args.konto)
    if not konten:
        raise EinstellungsFehler("Kein passendes eingeschaltetes Konto in den Einstellungen.")
    return einst, konten


def befehl_holen(args) -> int:
    einst, konten = _konten_oder_fehler(args)
    # Bei --json geht der Fortschritt nach stderr, stdout bleibt reines JSON.
    ausgabe = sys.stderr if args.json else sys.stdout
    ergebnisse = ablauf.alle_abrufen(
        einst, konten, lambda k: ablauf.sitzung_pruefen(k) == "angemeldet",
        lambda k: lambda t: print(t, file=ausgabe), nachholen=args.fehlende)
    if args.json:
        print(json.dumps(
            {"version": __version__, "belegordner": str(einst.belegordner),
             "ergebnisse": [e.als_dict() for e in ergebnisse]},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(ablauf.zusammenfassung(ergebnisse, einst.belegordner))
    return ablauf.exit_code(ergebnisse)


def befehl_pruefen(args) -> int:
    _, konten = _konten_oder_fehler(args)
    ergebnis = [
        {"quelle": k.quelle, "konto": k.name, "anzeige": k.anzeige, "status": ablauf.sitzung_pruefen(k)}
        for k in konten
    ]
    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    else:
        for e in ergebnis:
            print(f"{e['anzeige']}: {e['status']}")
    return 0 if all(e["status"] == "angemeldet" for e in ergebnis) else 2


def befehl_anmelden(args) -> int:
    _, konten = _konten_oder_fehler(args)
    ok = True
    for k in konten:
        print(f"Anmeldung für {k.anzeige}:")
        ok = ablauf.anmelden(k, print) and ok
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    _konsole_vorbereiten()
    parser = argparse.ArgumentParser(prog="belege", description="Belege aus Anbieter-Konten holen.")
    parser.add_argument("--version", action="version", version=f"belegabruf {__version__}")
    unter = parser.add_subparsers(dest="befehl")
    unter.add_parser("oberflaeche", help="Bedienseite im Browserfenster öffnen")
    unter.add_parser("start", help="Menü im Terminal (wie der Starter in 'Fehlersuche')")
    unter.add_parser("einrichten", help="Einstellungen abfragen und speichern")
    for name, hilfe in (("holen", "unbeaufsichtigt holen"), ("pruefen", "Anmeldungen prüfen"),
                        ("anmelden", "Anmeldefenster öffnen")):
        p = unter.add_parser(name, help=hilfe)
        p.add_argument("--quelle", help="nur diese Quelle, z. B. airbnb")
        p.add_argument("--konto", help="nur dieses Konto (Name aus den Einstellungen)")
        if name != "anmelden":
            p.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
        if name == "holen":
            p.add_argument("--fehlende", action="store_true",
                           help="auch geholte Rechnungen neu holen, die im Belegordner fehlen")
    args = parser.parse_args(argv)

    try:
        if args.befehl == "oberflaeche":
            from belegabruf import oberflaeche

            return oberflaeche.starten()
        if args.befehl in (None, "start"):
            return start()
        if args.befehl == "einrichten":
            einst = einrichtung.einrichten()
            konten = einst.aktive_konten()
            if konten and einrichtung._ja("\nJetzt gleich die Anmeldungen prüfen?", True):
                for k in konten:
                    anzeige = k.anzeige
                    if ablauf.sitzung_pruefen(k) == "angemeldet":
                        print(f"  ✓ {anzeige}: angemeldet")
                        continue
                    print(f"\nAnmeldung für {anzeige}: Gleich öffnet sich ein Browserfenster.")
                    ok = ablauf.anmelden(k, print)
                    print(f"  {'✓' if ok else '✗'} {anzeige}: {'angemeldet' if ok else 'nicht angemeldet'}")
            print(f'\nAb jetzt reicht ein Doppelklick auf "{pfade.starter()}".')
            return 0
        return {"holen": befehl_holen, "pruefen": befehl_pruefen, "anmelden": befehl_anmelden}[
            args.befehl](args)
    except EinstellungsFehler as fehler:
        if getattr(args, "json", False):
            print(json.dumps({"fehler": str(fehler)}, ensure_ascii=False))
        else:
            print(f"\n{fehler}\nTipp: \"{pfade.starter()}\" doppelklicken und im Reiter „Einstellungen“ einrichten.")
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
