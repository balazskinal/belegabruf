"""Gemeinsamer Umgang mit dem Browser (Playwright, Chromium).

Jedes Konto hat ein eigenes, dauerhaftes Browserprofil. Darin liegt die
Anmeldung — so, wie ein normaler Browser sich merkt, dass man eingeloggt ist.
Ein Passwort kennt das Programm nie.
"""

from __future__ import annotations

import random
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

#: Im Terminal: "Enter" beendet das Warten auf die Anmeldung. In der Bedienseite gibt es
#: kein Terminal zum Tippen — dann nur Fenster schließen bzw. automatisch erkennen.
ENTER_IM_TERMINAL = True

#: Die Bedienseite wurde geschlossen: offene Anmeldefenster nicht weiter offen halten.
ABBRECHEN = threading.Event()

# Menschliches Tempo: Pause zwischen zwei Abrufen (Sekunden).
PAUSE_MIN = 2.0
PAUSE_MAX = 5.0


class BrowserFehlt(Exception):
    """Chromium ist noch nicht installiert."""


class ProfilBelegt(Exception):
    """Ein anderes Fenster nutzt das Browserprofil gerade."""


def pause(minimum: float = PAUSE_MIN, maximum: float = PAUSE_MAX) -> None:
    time.sleep(random.uniform(minimum, maximum))


def _betriebssystem_im_useragent() -> str:
    if sys.platform == "win32":
        return "Windows NT 10.0; Win64; x64"
    if sys.platform == "darwin":
        return "Macintosh; Intel Mac OS X 10_15_7"
    return "X11; Linux x86_64"


def _useragent(chromium_version: str) -> str:
    # Derselbe Browser-Steckbrief im sichtbaren Anmeldefenster und im unsichtbaren
    # Abruf. Sonst sieht der Anbieter zwei verschiedene Browser und verwirft die
    # Anmeldung womöglich.
    haupt = chromium_version.split(".")[0]
    return (
        f"Mozilla/5.0 ({_betriebssystem_im_useragent()}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{haupt}.0.0.0 Safari/537.36"
    )


@contextmanager
def profil_oeffnen(profil: Path, sichtbar: bool) -> Iterator[BrowserContext]:
    """Öffnet das Browserprofil eines Kontos (sichtbar oder unsichtbar)."""
    profil.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            # Immer channel="chromium": Auch unsichtbar läuft dann das normale Chromium. Die
            # „Headless Shell“ von Playwright wird nie gebraucht und bei der Einrichtung nicht
            # geladen (--no-shell). Das gilt auch für diese Versions-Probe.
            probe = pw.chromium.launch(channel="chromium", headless=True)
            version = probe.version
            probe.close()
            kontext = pw.chromium.launch_persistent_context(
                user_data_dir=str(profil),
                channel="chromium",
                headless=not sichtbar,
                accept_downloads=True,
                locale="de-DE",
                user_agent=_useragent(version),
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as fehler:  # noqa: BLE001
            text = str(fehler)
            if "Executable doesn't exist" in text or "playwright install" in text:
                raise BrowserFehlt(
                    'Der Browser fehlt noch. Bitte "Belegabruf" doppelklicken (lädt ihn nach).'
                ) from fehler
            if "ProcessSingleton" in text or "SingletonLock" in text or "already in use" in text:
                raise ProfilBelegt(
                    "Das Browserprofil ist gerade in Benutzung. Ist noch ein Belegabruf-Fenster offen?"
                ) from fehler
            raise
        try:
            yield kontext
        finally:
            try:
                kontext.close()
            except Exception:  # noqa: BLE001 - Fenster schon zu
                pass


def neue_seite(kontext: BrowserContext) -> Page:
    return kontext.pages[0] if kontext.pages else kontext.new_page()


def auf_mensch_warten(
    kontext: BrowserContext,
    seite: Page,
    fertig: Callable[[Page], bool],
    hinweis: Callable[[str], None],
    hoechstens_minuten: int = 15,
) -> str:
    """Wartet, bis die Anmeldung erkannt wurde, Enter gedrückt oder das Fenster geschlossen ist.

    Gibt zurück: "erkannt", "enter", "geschlossen", "abgebrochen" (Bedienseite zu) oder "zeit".
    """
    enter = threading.Event()

    def lese_enter() -> None:
        try:
            sys.stdin.readline()
        except Exception:  # noqa: BLE001
            return
        enter.set()

    if ENTER_IM_TERMINAL:
        threading.Thread(target=lese_enter, daemon=True).start()
        hinweis(
            "  Melde dich im Browserfenster an (auch Zwei-Faktor). Danach geht es von allein weiter —\n"
            "  oder drück hier Enter, oder schließ das Fenster."
        )
    else:
        hinweis("Melde dich im neuen Fenster an (auch Zwei-Faktor). Danach geht es von allein weiter — "
                "oder schließ das Fenster, wenn du fertig bist.")
    ende = time.monotonic() + hoechstens_minuten * 60
    while time.monotonic() < ende:
        if enter.is_set():
            return "enter"
        if ABBRECHEN.is_set():
            return "abgebrochen"  # das Fenster schließt der Aufrufer (profil_oeffnen)
        offen = [s for s in kontext.pages if not s.is_closed()]
        if not offen:
            return "geschlossen"
        try:
            aktuell = offen[0]
            if fertig(aktuell):
                # Kurz warten, damit die Seite die Anmeldung fertig speichert.
                aktuell.wait_for_timeout(2500)
                return "erkannt"
            aktuell.wait_for_timeout(1000)
        except Exception:  # noqa: BLE001 - Fenster während des Wartens geschlossen
            if not [s for s in kontext.pages if not s.is_closed()]:
                return "geschlossen"
            time.sleep(1)
    return "zeit"
