"""Bedienoberfläche im Browserfenster (ADR-005).

``starten()`` öffnet den lokalen Server und die Bedienseite im mitgebrachten
Chromium (nicht im Standardbrowser). Abruf, Prüfen und Anmelden laufen über
dieselben Bausteine wie das CLI.
"""

from __future__ import annotations

import sys
import time
import webbrowser

from belegabruf import browser, pfade
from belegabruf.oberflaeche.server import Bedienserver


def _hilfe_weiterreichen(kontext, haupt, wartet: dict) -> None:
    """Weitere Seiten (Hilfelinks mit target=_blank) gehören nicht ins Fenster der
    Bedienseite: https-Adressen öffnet der Standardbrowser, die Seite hier wird zu."""
    for seite in list(kontext.pages):
        if seite is haupt or seite.is_closed():
            continue
        adresse = seite.url
        if adresse in ("", "about:blank") and wartet.get(id(seite), 0) < 5:
            wartet[id(seite)] = wartet.get(id(seite), 0) + 1  # Adresse kommt gleich
            continue
        wartet.pop(id(seite), None)
        try:
            seite.close()
        except Exception:  # noqa: BLE001 - Hilfeseite schon zu  # nosec B110
            pass
        if adresse.startswith("https://"):
            webbrowser.open(adresse)


def _fenster_offen_halten(server: Bedienserver) -> None:
    """Öffnet die Bedienseite als eigenes App-Fenster und wartet, bis **dieses** Fenster
    geschlossen oder auf der Seite „Beenden“ gedrückt wird. Andere Seiten (Hilfe) halten
    das Programm nicht am Leben."""
    from playwright.sync_api import sync_playwright

    profil = pfade.datenordner() / "profile" / "_bedienseite"
    profil.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        kontext = pw.chromium.launch_persistent_context(
            user_data_dir=str(profil), channel="chromium", headless=False, no_viewport=True,
            # Der Schlüssel kommt nicht in die Kommandozeile (die sehen per „ps“ auch andere
            # Benutzer); das App-Fenster startet leer und lädt die Seite danach.
            args=["--app=data:text/html,<title>Belegabruf</title>", "--window-size=1040,880"],
        )
        try:
            seite = kontext.pages[0] if kontext.pages else kontext.new_page()
            seite.goto(server.adresse)
            wartet: dict = {}
            while not server.steuerung.beendet.is_set() and not seite.is_closed():
                try:
                    _hilfe_weiterreichen(kontext, seite, wartet)
                    seite.wait_for_timeout(400)
                except Exception:  # noqa: BLE001 - Fenster wurde gerade geschlossen
                    if seite.is_closed():
                        break
        finally:
            try:
                kontext.close()
            except Exception:  # noqa: BLE001 - Fenster schon zu  # nosec B110
                pass


def starten() -> int:
    browser.ENTER_IM_TERMINAL = False
    server = Bedienserver()
    server.im_hintergrund()
    print("Belegabruf läuft.\n")
    print("  ┌──────────────────────────────────────────────────┐")
    print("  │  Nicht schließen, solange Belegabruf läuft.      │")
    print("  │  Bedienen und beenden im Fenster „Belegabruf“.   │")
    print("  └──────────────────────────────────────────────────┘\n")
    sys.stdout.flush()
    code = 0
    try:
        _fenster_offen_halten(server)
    except browser.BrowserFehlt as fehler:
        print(fehler)
        code = 1
    except Exception as fehler:  # noqa: BLE001
        text = str(fehler)
        if "Executable doesn't exist" in text or "playwright install" in text:
            print(f'Der Browser fehlt noch. Bitte "{pfade.starter()}" noch einmal doppelklicken (lädt ihn nach).')
        else:
            print(f"Das Fenster „Belegabruf“ ist zu oder ließ sich nicht öffnen ({type(fehler).__name__}).")
        code = 1
    st = server.steuerung
    st.beendet.set()
    browser.ABBRECHEN.set()  # ein offenes Anmeldefenster schließt sich
    if st.beschaeftigt():
        print("Warte, bis der laufende Vorgang fertig ist … (nicht schließen)")
        while st.beschaeftigt():
            time.sleep(0.5)
    server.shutdown()
    server.server_close()
    print("Belegabruf ist beendet. Dieses Fenster kann jetzt zu.")
    print(f'Wieder öffnen: Doppelklick auf "{pfade.starter()}".')
    return code
