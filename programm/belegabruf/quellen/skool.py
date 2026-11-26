"""Baustein Skool: Rechnungen für bezahlte Mitgliedschaften in Skool-Communities.

Wo sie liegen: Einstellungen → Zahlungsverlauf (``/settings?t=payment-history``).
Dort steht je Zahlung ein Link mit dem Datum als Text; er führt zur Einzelrechnung
``/<gruppe>/--/inv/<stripe-rechnungs-id>``. Mehrere Communities sind möglich — die
Gruppe steht im Pfad.

Die Einzelrechnung ist eine HTML-Seite ohne PDF-Knopf. Das Programm öffnet sie im
angemeldeten (unsichtbaren) Browser, prüft den Inhalt und druckt sie selbst als PDF.

**Regel: nur lesen und herunterladen.** Der Baustein ruft nur Seiten auf und klickt
nichts an — schon gar nicht Zahlungsmethoden, Kündigung oder Ähnliches.

Ablauf:
1. Zahlungsverlauf öffnen, alle Rechnungslinks einsammeln (Datum, Gruppe, ID)
2. Jede noch nicht geholte Rechnung öffnen, Inhalt prüfen (Überschrift, Gesamtbetrag;
   nie eine Anmelde-, Fehler- oder leere Seite), als PDF abliefern
                                         → skool/<Jahr>/<Datum>_<gruppe>_<id>.pdf
3. Kontrolle: so viele Rechnungen geholt, wie der Zahlungsverlauf nennt
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from belegabruf import browser, pruefung
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung

ADRESSE = "https://www.skool.com"
UEBERSICHT_PFAD = "/settings?t=payment-history"

RE_LINK = re.compile(r"^(?:https?://[^/]+)?/([^/?#]+)/--/inv/(in_[A-Za-z0-9]+)")

MONATE = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7, "october": 10,
    "december": 12,
}
for _name, _nr in list(MONATE.items()):  # Kurzformen: "Okt", "Oct", "Sept." …
    MONATE.setdefault(_name[:3], _nr)
MONATE["sept"] = 9

# Überschrift und Gesamtbetrag in beiden Sprachen
UEBERSCHRIFTEN = ("rechnung", "invoice")
GESAMT = ("gesamt", "total")
RE_BETRAG = re.compile(r"(?:US\$|\$|USD|€|EUR)\s?-?\d[\d.,]*|-?\d[\d.,]*\s?(?:US\$|\$|USD|€|EUR)")
RE_RECHNUNGSNUMMER = re.compile(r"\b([A-Z0-9]{6,12}-\d{4,})\b")


def _ist_anmeldeseite(url: str) -> bool:
    url = url.lower()
    return "/login" in url or "/signup" in url or "accounts.google.com" in url


def _kurz(fehler: Exception) -> str:
    return f"{type(fehler).__name__}: {str(fehler).splitlines()[0][:120]}" if str(fehler) else type(fehler).__name__


def datum_aus_text(text: str) -> date | None:
    """'Oktober 25. 2026', 'October 25, 2026', '25. Oktober 2026', 'Oct 25, 2026' → date."""
    woerter = re.findall(r"[A-Za-zÄÖÜäöü]+|\d+", text)
    monat = next((MONATE[w.lower()] for w in woerter if w.lower() in MONATE), None)
    zahlen = [int(w) for w in woerter if w.isdigit()]
    jahr = next((z for z in zahlen if 2000 <= z <= 2100), None)
    tag = next((z for z in zahlen if 1 <= z <= 31), None)
    if monat is None or jahr is None or tag is None:
        return None
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


@dataclass
class Zahlung:
    """Ein Eintrag im Zahlungsverlauf = eine Rechnung."""

    kennung: str  # Stripe-Rechnungs-ID, z. B. in_1AbC…
    gruppe: str
    pfad: str
    datum: date | None


def uebersicht_lesen(links: list[tuple[str, str]]) -> list[Zahlung]:
    """(href, Linktext) aus dem Zahlungsverlauf → Zahlungen (ohne Doppelte)."""
    zahlungen: dict[str, Zahlung] = {}
    for href, text in links:
        treffer = RE_LINK.match(href or "")
        if not treffer:
            continue
        gruppe, kennung = treffer.groups()
        if kennung in zahlungen:
            if zahlungen[kennung].datum is None:
                zahlungen[kennung].datum = datum_aus_text(text)
            continue
        pfad = href[href.index(f"/{gruppe}/--/inv/"):] if "://" in href else href
        zahlungen[kennung] = Zahlung(kennung=kennung, gruppe=gruppe, pfad=pfad, datum=datum_aus_text(text))
    return list(zahlungen.values())


def _sauber(text: str) -> str:
    return " ".join(text.split())


def rechnung_pruefen(text: str) -> str | None:
    """Ist das eine Rechnung? None, wenn ja, sonst der Grund."""
    sauber = _sauber(text)
    klein = sauber.lower()
    if len(sauber) < 80:
        return "leere Seite"
    fehlt = []
    if not any(w in klein for w in UEBERSCHRIFTEN):
        fehlt.append("Überschrift Rechnung")
    if not any(w in klein for w in GESAMT):
        fehlt.append("Gesamtbetrag")
    elif not RE_BETRAG.search(sauber):
        fehlt.append("Betrag")
    if not fehlt:
        return None
    # Woran liegt es? Gleiche Merkmale wie bei den anderen Bausteinen.
    grund = pruefung.seite_ist_beleg(text, ["\0"])  # erzwingt die Merkmalsuche
    if grund in {"Fehlerseite (z. B. 404)", "Anmeldeseite"}:
        return grund
    return "erwartete Angaben fehlen (" + ", ".join(fehlt) + ")"


@dataclass
class Rechnungsdaten:
    rechnungsnummer: str
    gesamt: str


def rechnungsseite_lesen(text: str) -> Rechnungsdaten:
    """Rechnungsnummer (falls vorhanden) und Gesamtbetrag aus der Einzelrechnung."""
    sauber = _sauber(text)
    nummer = RE_RECHNUNGSNUMMER.search(sauber)
    gesamt = ""
    m = re.search(r"\b(?:Gesamt|Total)\b[^0-9$€]{0,30}(" + RE_BETRAG.pattern + ")", sauber, re.IGNORECASE)
    if m:
        gesamt = m.group(1).strip()
    return Rechnungsdaten(rechnungsnummer=nummer.group(1) if nummer else "", gesamt=gesamt)


def dateiname(datum: date | None, gruppe: str, kennung: str) -> str:
    """<JJJJ-MM-TT>_<gruppe>_<id>.pdf"""
    teile = [datum.isoformat() if datum else "ohne-datum", gruppe or "ohne-gruppe", kennung]
    return "_".join(re.sub(r"[^A-Za-z0-9_-]", "", t) or "x" for t in teile) + ".pdf"


# Nur für diese eine Seite im Browser, nie in Skool gespeichert: Klassen und Attribute,
# mit denen Seiten ein dunkles Design schalten, auf hell setzen. localStorage und die
# Kontoeinstellung bei Skool bleiben unberührt.
_HELL_JS = r"""() => {
  for (const e of [document.documentElement, document.body]) {
    if (!e) continue;
    for (const k of [...e.classList]) if (/dark/i.test(k)) e.classList.remove(k);
    for (const a of ['data-theme', 'data-color-mode', 'data-mode', 'data-color-scheme', 'theme'])
      if (e.hasAttribute(a)) e.setAttribute(a, 'light');
    e.style.colorScheme = 'light';
  }
}"""

# Hintergrund des Rumpfs (oder des ersten Elements mit Hintergrund) als Helligkeit 0…255.
_HELLIGKEIT_JS = r"""() => {
  const farbe = e => getComputedStyle(e).backgroundColor;
  let e = document.body, f = farbe(e);
  const leer = f => !f || f === 'transparent' || /rgba\(.*,\s*0\)$/.test(f);
  if (leer(f)) f = farbe(document.documentElement);
  if (leer(f)) {
    const kinder = [...document.body.querySelectorAll('*')].slice(0, 200);
    const mit = kinder.find(k => !leer(farbe(k)) && k.offsetWidth > window.innerWidth / 2);
    f = mit ? farbe(mit) : 'rgb(255, 255, 255)';
  }
  const [r, g, b] = (f.match(/\d+(\.\d+)?/g) || [255, 255, 255]).map(Number);
  return 0.299 * r + 0.587 * g + 0.114 * b;
}"""

# Letzter Ausweg, falls die Seite trotzdem dunkel bleibt: helle Druckfarben erzwingen.
_HELL_CSS = """@media print { html, body, body * {
  background-color: #fff !important; color: #000 !important; border-color: #ccc !important; } }"""


def hell_machen(seite) -> None:
    """Vor dem PDF: helles Design, gut zum Drucken und für die Texterkennung in
    Buchhaltungsprogrammen — auch wenn das Skool-Konto auf Dunkel steht."""
    seite.emulate_media(color_scheme="light", media="print")
    seite.evaluate(_HELL_JS)
    seite.wait_for_timeout(300)
    if seite.evaluate(_HELLIGKEIT_JS) < 128:
        seite.add_style_tag(content=_HELL_CSS)
        seite.wait_for_timeout(200)


def _aufrufen(seite, url: str):
    """Seite laden, bei Zeitüberschreitung ein zweites Mal versuchen."""
    for versuch in (1, 2):
        try:
            antwort = seite.goto(url, wait_until="commit", timeout=60000)
            seite.wait_for_load_state("domcontentloaded", timeout=60000)
            return antwort
        except Exception:  # noqa: BLE001
            if versuch == 2:
                raise
            browser.pause(5, 10)
    return None


class Skool(Quelle):
    name = "skool"
    anzeigename = "Skool"

    def _adresse(self) -> str:
        return str(self.konto.optionen.get("adresse") or ADRESSE).rstrip("/")

    def _hosts(self) -> set[str]:
        """Erlaubter Host für Belegseiten: der der eingestellten Adresse (Vorgabe www.skool.com)."""
        return {pruefung.host_von(self._adresse())}

    # 1. Sitzung prüfen ------------------------------------------------------
    def sitzung_pruefen(self) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=False) as kontext:
            seite = browser.neue_seite(kontext)
            _aufrufen(seite, self._adresse() + UEBERSICHT_PFAD)
            seite.wait_for_timeout(3000)
            return self._auf_zahlungsverlauf(seite)

    def _auf_zahlungsverlauf(self, seite) -> bool:
        return not _ist_anmeldeseite(seite.url) and "/settings" in seite.url

    def _angemeldet_im_fenster(self, seite) -> bool:
        # Nach der Anmeldung leitet Skool auf die Startseite oder eine Community weiter.
        url = seite.url.lower()
        return "skool.com" in url and not _ist_anmeldeseite(url)

    # 2. Anmelden lassen -----------------------------------------------------
    def anmelden_lassen(self, melden: Callable[[str], None]) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=True) as kontext:
            seite = browser.neue_seite(kontext)
            seite.goto(self._adresse() + "/login", wait_until="domcontentloaded")
            melden("  Tipp: Wenn die Anmeldung mit Google hier blockiert wird, melde dich mit E-Mail und\n"
                   "  Passwort bei Skool an (ggf. vorher bei Skool ein Passwort festlegen).")
            browser.auf_mensch_warten(kontext, seite, self._angemeldet_im_fenster, melden)
        return self.sitzung_pruefen()

    # 3. Belege holen --------------------------------------------------------
    def _zahlungen(self, seite) -> list[Zahlung] | None:
        """Alle Rechnungslinks im Zahlungsverlauf. None, wenn die Seite nicht geladen hat."""
        _aufrufen(seite, self._adresse() + UEBERSICHT_PFAD)
        if _ist_anmeldeseite(seite.url):
            raise SitzungAbgelaufen()
        try:
            seite.wait_for_selector("a[href*='/--/inv/']", timeout=30000)
        except Exception:  # noqa: BLE001 - vielleicht gibt es einfach keine Zahlungen
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen() from None
            text = seite.inner_text("body").lower()
            if "zahlungsverlauf" in text or "payment history" in text:
                return []
            return None
        # Falls die Liste beim Blättern nachlädt: nach unten scrollen (nichts anklicken).
        vorher = -1
        for _ in range(10):
            anzahl = seite.locator("a[href*='/--/inv/']").count()
            if anzahl == vorher:
                break
            vorher = anzahl
            seite.mouse.wheel(0, 4000)
            seite.wait_for_timeout(1200)
        links = seite.locator("a[href*='/--/inv/']").evaluate_all(
            "els => els.map(e => [e.getAttribute('href') || '', (e.innerText || '').trim()])"
        )
        return uebersicht_lesen([(h, t) for h, t in links])

    def belege_holen(self, umgebung: Umgebung) -> Ergebnis:
        erg = Ergebnis(self.name, self.konto.name)
        melden = umgebung.melden
        with browser.profil_oeffnen(self.profil, sichtbar=umgebung.sichtbar) as kontext:
            seite = browser.neue_seite(kontext)
            try:
                zahlungen = self._zahlungen(seite)
            except SitzungAbgelaufen:
                erg.status = "abgelaufen"
                return erg
            except Exception as fehler:  # noqa: BLE001
                erg.status = "unvollstaendig"
                erg.abweichungen.append(f"Zahlungsverlauf nicht geladen ({_kurz(fehler)}).")
                return erg
            if zahlungen is None:
                erg.status = "unvollstaendig"
                erg.abweichungen.append("Im Zahlungsverlauf wurden keine Rechnungen gefunden — die Seite hat "
                                        "vielleicht nicht fertig geladen. Später noch einmal starten.")
                return erg
            gruppen = sorted({z.gruppe for z in zahlungen})
            melden(f"{len(zahlungen)} Rechnung(en) im Zahlungsverlauf"
                   + (f" ({', '.join(gruppen)})" if gruppen else "") + ".")
            for z in zahlungen:
                if z.datum is None:
                    erg.hinweise.append(f"Rechnung {z.kennung}: Datum im Zahlungsverlauf nicht erkannt.")
            # Zeitraum: ältere Rechnungen gar nicht erst öffnen und nicht vermerken.
            erg.uebersprungen = sum(1 for z in zahlungen if umgebung.zu_alt(z.datum))
            zahlungen = [z for z in zahlungen if not umgebung.zu_alt(z.datum)]

            offen = [z for z in zahlungen if not umgebung.bekannt(f"rechnung:{z.kennung}")]
            erg.schon_da = len(zahlungen) - len(offen)
            if offen:
                melden(f"{len(offen)} neue Rechnung(en) werden geholt …")
            for nr, zahlung in enumerate(offen, 1):
                browser.pause()
                try:
                    grund = self._einzelrechnung(seite, zahlung, umgebung, erg)
                except SitzungAbgelaufen:
                    erg.status = "abgelaufen"
                    melden("Die Anmeldung ist abgelaufen. Der nächste Lauf holt den Rest nach.")
                    break
                except pruefung.FremdeAdresse as fehler:
                    grund = str(fehler)
                except Exception as fehler:  # noqa: BLE001 - eine Rechnung darf scheitern
                    grund = _kurz(fehler)
                if grund:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"Rechnung {zahlung.kennung}: nicht gespeichert ({grund}).")
                elif nr % 10 == 0:
                    melden(f"… {nr} von {len(offen)}")

        erg.erwartet = len(zahlungen)
        erg.vorhanden = sum(1 for z in zahlungen if umgebung.bekannt(f"rechnung:{z.kennung}"))
        return erg

    def _einzelrechnung(self, seite, zahlung: Zahlung, umgebung: Umgebung, erg: Ergebnis) -> str | None:
        """Holt eine Rechnung. Gibt None bei Erfolg zurück, sonst den Grund."""
        url = pruefung.adresse_pruefen(self._adresse() + zahlung.pfad, self._hosts())
        antwort = _aufrufen(seite, url)
        if _ist_anmeldeseite(seite.url):
            raise SitzungAbgelaufen()
        pruefung.adresse_pruefen(seite.url, self._hosts())  # auch nach einer Weiterleitung
        if antwort is not None and antwort.status >= 400:
            return f"Fehlerseite {antwort.status}"
        try:
            seite.wait_for_function(
                "() => /(Gesamt|Total)/i.test(document.body.innerText)", timeout=30000)
            seite.wait_for_timeout(800)  # Schriften fertig laden lassen
        except Exception:  # noqa: BLE001 - die Prüfung unten sagt, was fehlt
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen() from None
        seitentext = seite.inner_text("body")
        grund = rechnung_pruefen(seitentext)
        if grund == "Anmeldeseite":
            raise SitzungAbgelaufen()
        if grund:
            return grund
        daten = rechnungsseite_lesen(seitentext)
        hell_machen(seite)
        inhalt = seite.pdf(format="A4", print_background=True)
        if pruefung.zu_gross(inhalt):
            return f"PDF größer als {pruefung.MAX_PDF_BYTES // (1024 * 1024)} MB"
        # Auch das fertige PDF prüfen: Steht die Rechnung wirklich drin?
        grund = rechnung_pruefen(pruefung.pdf_text(inhalt))
        if grund:
            return f"PDF unbrauchbar: {grund}"
        datum = zahlung.datum
        beleg = Beleg(
            quelle=self.name,
            konto=self.konto.name,
            art="rechnung",
            schluessel=f"rechnung:{zahlung.kennung}",
            dateiname=dateiname(datum, zahlung.gruppe, zahlung.kennung),
            inhalt=inhalt,
            jahr=datum.year if datum else date.today().year,
            rechnungsdatum=datum,
            rechnungsnummer=daten.rechnungsnummer or zahlung.kennung,
            betrag=daten.gesamt,
        )
        orte = umgebung.abliefern(beleg)
        erg.neu += 1
        erg.neue_dateien += orte
        return None
