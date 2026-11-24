"""Baustein Airbnb: Rechnungen über die Servicegebühren für Gastgeber.

Wo sie liegen: Konto → Steuern → Steuerdokumente → Rechnungen. Airbnb bietet dort
nur die letzten 12 Monate an, je Monat ein Sammel-PDF. In jeder Zeile des
Sammel-PDFs steht eine Buchung, und die Zeile ist ein Link auf die Einzelrechnung.

Ablauf:
1. Monats-PDFs holen (→ airbnb/kontrolle/)
2. Links zu den Einzelrechnungen aus den Monats-PDFs lesen
3. Jede noch nicht vorhandene Einzelrechnung im angemeldeten Browser öffnen,
   Inhalt prüfen (keine Anmelde-, 404- oder leere Seite!) und als PDF abliefern
4. Anzahl Einzelrechnungen gegen die Zeilen der Monats-PDFs prüfen
"""

from __future__ import annotations

from typing import Callable

from belegabruf import browser
from belegabruf.quellen.basis import Ergebnis, Quelle, Umgebung

ADRESSE = "https://www.airbnb.de"
STEUER_SEITE = f"{ADRESSE}/account-settings/taxes"
ANMELDE_SEITE = f"{ADRESSE}/login"


def _ist_anmeldeseite(url: str) -> bool:
    url = url.lower()
    return any(t in url for t in ("/login", "signup_login", "/authenticate", "/account-verification"))


class Airbnb(Quelle):
    name = "airbnb"
    anzeigename = "Airbnb"

    def _adresse(self) -> str:
        return str(self.konto.optionen.get("adresse") or ADRESSE).rstrip("/")

    # 1. Sitzung prüfen ------------------------------------------------------
    def sitzung_pruefen(self) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=False) as kontext:
            seite = browser.neue_seite(kontext)
            return self._angemeldet_nach_aufruf(seite)

    def _angemeldet_nach_aufruf(self, seite) -> bool:
        seite.goto(f"{self._adresse()}/account-settings/taxes", wait_until="domcontentloaded")
        seite.wait_for_timeout(2500)
        return self._sieht_angemeldet_aus(seite)

    def _sieht_angemeldet_aus(self, seite) -> bool:
        if _ist_anmeldeseite(seite.url):
            return False
        return "/account-settings" in seite.url

    # 2. Anmelden lassen -----------------------------------------------------
    def anmelden_lassen(self, melden: Callable[[str], None]) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=True) as kontext:
            seite = browser.neue_seite(kontext)
            seite.goto(
                f"{self._adresse()}/login?redirect_url=%2Faccount-settings%2Ftaxes",
                wait_until="domcontentloaded",
            )
            browser.auf_mensch_warten(kontext, seite, self._sieht_angemeldet_aus, melden)
        # Unabhängig davon, was im Fenster passiert ist: unsichtbar nachprüfen.
        return self.sitzung_pruefen()

    # 3. Belege holen --------------------------------------------------------
    def belege_holen(self, umgebung: Umgebung) -> Ergebnis:
        raise NotImplementedError
