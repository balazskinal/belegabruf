"""Kommandozeile.

    belege                      Start per Doppelklick: prüfen, anmelden lassen, holen
    belege einrichten           Fragen beantworten, Einstellungsdatei schreiben
    belege pruefen [--json]     Sind die Konten angemeldet?
    belege anmelden --quelle airbnb [--konto NAME]
    belege holen [--quelle airbnb] [--konto NAME] [--json]
                                Unbeaufsichtigt holen, öffnet nie ein Fenster
                                (für spätere Automatisierung, z. B. n8n)

Exit-Codes von "holen" und "pruefen": 0 alles gut, 2 Anmeldung nötig/abgelaufen, 1 Fehler.
"""

from __future__ import annotations

import argparse
import json
import sys

from belegabruf import __version__, ablauf, aktualisierung, einrichtung, einstellungen, quellen, zustand
from belegabruf.einstellungen import EinstellungsFehler


def _konsole_vorbereiten() -> None:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def _exit_code(ergebnisse: list) -> int:
    status = {e.status for e in ergebnisse}
    if "fehler" in status:
        return 1
    if status & {"anmeldung_noetig", "abgelaufen"}:
        return 2
    return 0


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

    while True:
        konten = einst.aktive_konten()
        print(f"\nBelegabruf {__version__}")
        print("═" * (11 + len(__version__)))
        if konten:
            print("Heute werden geholt: " + ", ".join(
                f"{quellen.anzeigename(k.quelle)} ({k.name})" for k in konten))
        else:
            print("Es ist kein Konto eingeschaltet.")
        print(f"Belegordner: {einst.belegordner}")

        neuer = aktualisierung.neuere_version()
        if neuer:
            print(f"\nHinweis: Es gibt eine neuere Version ({neuer}). Herunterladen unter")
            print(f"  {aktualisierung.NEUESTE_SEITE}")
            print("  (Programmordner löschen, neues ZIP auspacken — Einstellungen bleiben erhalten.)")

        for k in konten:
            zuletzt = zustand.zu_lange_her(k.quelle, k.name)
            if zuletzt:
                print(
                    f"\n⚠ Achtung: {quellen.anzeigename(k.quelle)} ({k.name}) lief zuletzt am "
                    f"{zuletzt:%d.%m.%Y}. Airbnb zeigt nur die letzten 12 Monate —\n"
                    "  ältere Rechnungen sind sonst irgendwann weg. Am besten jeden Monat holen."
                )

        try:
            wahl = input("\nEnter = los · E = Einstellungen ändern · Q = beenden: ").strip().lower()
        except EOFError:
            wahl = ""
        if wahl in {"q", "x"}:
            return 0
        if wahl == "e":
            einst = einrichtung.einrichten()
            continue
        if not konten:
            print("Ohne eingeschaltetes Konto gibt es nichts zu tun. Mit E kannst du eins eintragen.")
            continue
        break

    code = lauf(einst, konten)
    _warte_enter()
    return code


def lauf(einst, konten) -> int:
    melden = print

    # 1. Alle Konten prüfen
    print("\nPrüfe die Anmeldungen …")
    nicht_angemeldet = []
    for k in konten:
        status = ablauf.sitzung_pruefen(k)
        anzeige = f"{quellen.anzeigename(k.quelle)} ({k.name})"
        if status == "angemeldet":
            print(f"  ✓ {anzeige}: angemeldet")
        else:
            print(f"  · {anzeige}: {'nicht angemeldet' if status == 'abgemeldet' else status}")
            nicht_angemeldet.append(k)

    # 2. Erst alle Anmeldefenster
    ausgelassen = set()
    for k in nicht_angemeldet:
        anzeige = f"{quellen.anzeigename(k.quelle)} ({k.name})"
        print(f"\nAnmeldung für {anzeige}: Gleich öffnet sich ein Browserfenster.")
        if ablauf.anmelden(k, melden):
            print(f"  ✓ {anzeige}: angemeldet")
        else:
            print(f"  ✗ {anzeige}: Anmeldung nicht erkannt — dieses Konto wird heute ausgelassen.")
            ausgelassen.add(k.name + "\0" + k.quelle)

    # 3. Abruf unbeaufsichtigt, nacheinander
    print("\nJetzt werden die Belege geholt. Das dauert ein paar Minuten —")
    print("du musst nichts tun und kannst den Rechner nebenbei normal benutzen.")
    ergebnisse = []
    protokoll = ablauf.protokoll_fuer(einst)
    for k in konten:
        if k.name + "\0" + k.quelle in ausgelassen:
            from belegabruf.quellen.basis import Ergebnis

            ergebnisse.append(Ergebnis(k.quelle, k.name, status="anmeldung_noetig"))
            continue
        print(f"\n{quellen.anzeigename(k.quelle)} ({k.name}):")
        ergebnisse.append(ablauf.abrufen(einst, k, lambda t: print("  " + t), protokoll))

    # 4. Zusammenfassung
    print(ablauf.zusammenfassung(ergebnisse, einst.belegordner))
    return _exit_code(ergebnisse)


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
    ergebnisse = []
    protokoll = ablauf.protokoll_fuer(einst)
    for k in konten:
        if ablauf.sitzung_pruefen(k) != "angemeldet":
            from belegabruf.quellen.basis import Ergebnis

            ergebnisse.append(Ergebnis(k.quelle, k.name, status="anmeldung_noetig"))
            continue
        ergebnisse.append(ablauf.abrufen(einst, k, lambda t: print(t, file=ausgabe), protokoll))
    if args.json:
        print(json.dumps(
            {"version": __version__, "belegordner": str(einst.belegordner),
             "ergebnisse": [e.als_dict() for e in ergebnisse]},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(ablauf.zusammenfassung(ergebnisse, einst.belegordner))
    return _exit_code(ergebnisse)


def befehl_pruefen(args) -> int:
    _, konten = _konten_oder_fehler(args)
    ergebnis = [
        {"quelle": k.quelle, "konto": k.name, "status": ablauf.sitzung_pruefen(k)} for k in konten
    ]
    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    else:
        for e in ergebnis:
            print(f"{quellen.anzeigename(e['quelle'])} ({e['konto']}): {e['status']}")
    return 0 if all(e["status"] == "angemeldet" for e in ergebnis) else 2


def befehl_anmelden(args) -> int:
    _, konten = _konten_oder_fehler(args)
    ok = True
    for k in konten:
        print(f"Anmeldung für {quellen.anzeigename(k.quelle)} ({k.name}):")
        ok = ablauf.anmelden(k, print) and ok
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    _konsole_vorbereiten()
    parser = argparse.ArgumentParser(prog="belege", description="Belege aus Anbieter-Konten holen.")
    parser.add_argument("--version", action="version", version=f"belegabruf {__version__}")
    unter = parser.add_subparsers(dest="befehl")
    unter.add_parser("start", help="wie Doppelklick auf 'Belege holen'")
    unter.add_parser("einrichten", help="Einstellungen abfragen und speichern")
    for name, hilfe in (("holen", "unbeaufsichtigt holen"), ("pruefen", "Anmeldungen prüfen"),
                        ("anmelden", "Anmeldefenster öffnen")):
        p = unter.add_parser(name, help=hilfe)
        p.add_argument("--quelle", help="nur diese Quelle, z. B. airbnb")
        p.add_argument("--konto", help="nur dieses Konto (Name aus den Einstellungen)")
        if name != "anmelden":
            p.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    args = parser.parse_args(argv)

    try:
        if args.befehl in (None, "start"):
            return start()
        if args.befehl == "einrichten":
            einst = einrichtung.einrichten()
            konten = einst.aktive_konten()
            if konten and einrichtung._ja("\nJetzt gleich die Anmeldungen prüfen?", True):
                for k in konten:
                    anzeige = f"{quellen.anzeigename(k.quelle)} ({k.name})"
                    if ablauf.sitzung_pruefen(k) == "angemeldet":
                        print(f"  ✓ {anzeige}: angemeldet")
                        continue
                    print(f"\nAnmeldung für {anzeige}: Gleich öffnet sich ein Browserfenster.")
                    ok = ablauf.anmelden(k, print)
                    print(f"  {'✓' if ok else '✗'} {anzeige}: {'angemeldet' if ok else 'nicht angemeldet'}")
            print('\nAb jetzt reicht ein Doppelklick auf "Belege holen".')
            return 0
        return {"holen": befehl_holen, "pruefen": befehl_pruefen, "anmelden": befehl_anmelden}[
            args.befehl](args)
    except EinstellungsFehler as fehler:
        if getattr(args, "json", False):
            print(json.dumps({"fehler": str(fehler)}, ensure_ascii=False))
        else:
            print(f"\n{fehler}\nTipp: \"Einrichten\" doppelklicken.")
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
