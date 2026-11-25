"""Bedienoberfläche im Browserfenster (ADR-005).

``starten()`` öffnet den lokalen Server und die Bedienseite im mitgebrachten
Chromium (nicht im Standardbrowser). Abruf, Prüfen und Anmelden laufen über
dieselben Bausteine wie das CLI.
"""

from __future__ import annotations

import sys
import time

from belegabruf import browser, pfade
from belegabruf.oberflaeche.server import Bedienserver


def _fenster_offen_halten(server: Bedienserver) -> None:
    """Öffnet die Bedienseite als eigenes App-Fenster und wartet, bis es geschlossen
    oder auf der Seite „Beenden“ gedrückt wird."""
    from playwright.sync_api import sync_playwright

    profil = pfade.datenordner() / "profile" / "_bedienseite"
    profil.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        kontext = pw.chromium.launch_persistent_context(
            user_data_dir=str(profil), channel="chromium", headless=False, no_viewport=True,
            args=[f"--app={server.adresse}", "--window-size=1040,880"],
        )
        try:
            seite = kontext.pages[0] if kontext.pages else kontext.new_page()
            if not seite.url.startswith("http://127.0.0.1"):
                seite.goto(server.adresse)
            while not server.steuerung.beendet.is_set():
                offen = [s for s in kontext.pages if not s.is_closed()]
                if not offen:
                    break
                try:
                    offen[0].wait_for_timeout(400)
                except Exception:  # noqa: BLE001 - Fenster wurde gerade geschlossen
                    if not [s for s in kontext.pages if not s.is_closed()]:
                        break
        finally:
            try:
                kontext.close()
            except Exception:  # noqa: BLE001
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
            print('Der Browser fehlt noch. Bitte einmal "Einrichten" doppelklicken.')
        else:
            print(f"Das Fenster „Belegabruf“ ist zu oder ließ sich nicht öffnen ({type(fehler).__name__}).")
        code = 1
    st = server.steuerung
    if st.beschaeftigt():
        print("Warte, bis der laufende Vorgang fertig ist … (nicht schließen)")
        while st.beschaeftigt():
            time.sleep(0.5)
    server.shutdown()
    server.server_close()
    print("Belegabruf ist beendet. Dieses Fenster kann jetzt zu.")
    print('Wieder öffnen: Doppelklick auf "Belege holen".')
    return code
