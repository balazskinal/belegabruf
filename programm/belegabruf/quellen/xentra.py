"""Baustein Xentra: Rechnungen für das Xentra-Abonnement und Provisionen.

Wo sie liegen: ``https://app.myxentra.com/billing``, Reiter „Rechnungen“. Eine
Tabelle mit Datum (TT.MM.JJJJ), Beschreibung, Betrag, Status und einem Knopf
„PDF herunterladen“. Die Tabelle steht zweimal in der Seite (einmal versteckt für
die Handy-Ansicht) — es zählen nur die sichtbaren Zeilen.

Der Knopf öffnet ein neues Fenster und ruft bei Xentra die Abrechnung (Chargebee)
auf; die Antwort enthält eine befristete Adresse des PDFs. Das Programm klickt den
Knopf wie ein Mensch, liest aus diesem Aufruf nur die Rechnungs-ID und die
PDF-Adresse mit, lädt die Datei und schließt das Fenster wieder. Es ruft die
Abrechnung nie selbst auf.

**Regel: nur lesen und herunterladen.** Angeklickt werden nur der Reiter
„Rechnungen“ und die Knöpfe „PDF herunterladen“ — nichts an Abo, Zahlungsmethode
oder Einstellungen. Die Beschreibung einer Zeile (Provisionen nennen Gastnamen)
kommt nie in Dateinamen, Protokoll oder Ausgaben.

Ablage: xentra/<Jahr>/<JJJJ-MM-TT>_xentra_<rechnungs-id>.pdf
"""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from belegabruf import browser, pruefung
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung

ADRESSE = "https://app.myxentra.com"
ABRECHNUNG_PFAD = "/billing"
DOWNLOAD_AUFRUF = "chargebee-invoice-download"
KNOPF = "button[aria-label='PDF herunterladen'], button[title='PDF herunterladen']"

RE_DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")
RE_BETRAG = re.compile(r"-?\d[\d.]*,\d{2}\s?€|€\s?-?\d[\d.]*,\d{2}")
RE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ID_FELDER = ("invoice_id", "invoiceId", "invoiceID", "invoice", "id")


def _ist_anmeldeseite(url: str) -> bool:
    url = url.lower()
    return any(t in url for t in ("/login", "/signin", "/sign-in", "/auth", "/register", "/signup"))


def _kurz(fehler: Exception) -> str:
    return f"{type(fehler).__name__}: {str(fehler).splitlines()[0][:120]}" if str(fehler) else type(fehler).__name__


def datum_lesen(text: str) -> date | None:
    m = RE_DATUM.search(text or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def rechnungs_id_aus_anfrage(rumpf: str | None) -> str:
    """Die Chargebee-Rechnungs-ID aus dem Rumpf des Download-Aufrufs (JSON)."""
    if not rumpf:
        return ""
    try:
        daten = json.loads(rumpf)
    except (ValueError, TypeError):
        return ""
    gefunden: list[tuple[int, str]] = []

    def suchen(wert, tiefe=0):
        if tiefe > 4:
            return
        if isinstance(wert, dict):
            for schluessel, inhalt in wert.items():
                if isinstance(inhalt, (str, int)) and not isinstance(inhalt, bool) and schluessel in ID_FELDER:
                    gefunden.append((ID_FELDER.index(schluessel), str(inhalt)))
                else:
                    suchen(inhalt, tiefe + 1)

    suchen(daten)
    for _, kennung in sorted(gefunden):
        if RE_ID.match(kennung):
            return kennung
    return ""


ADRESS_FELDER = ("download_url", "downloadUrl", "pdf_url", "pdfUrl", "url")


def pdf_adresse_aus_antwort(rumpf: str | None) -> str:
    """Die (befristete) PDF-Adresse aus der Antwort des Download-Aufrufs — gezielt aus
    einem Feld wie ``download_url``, nie die erstbeste Adresse. Nur https."""
    if not rumpf:
        return ""
    try:
        daten = json.loads(rumpf)
    except (ValueError, TypeError):
        return ""
    gefunden: list[tuple[int, str]] = []

    def suchen(wert, tiefe=0):
        if tiefe > 5:
            return
        if isinstance(wert, dict):
            for schluessel, inhalt in wert.items():
                if schluessel in ADRESS_FELDER and isinstance(inhalt, str):
                    gefunden.append((ADRESS_FELDER.index(schluessel), inhalt))
                else:
                    suchen(inhalt, tiefe + 1)
        elif isinstance(wert, list):
            for inhalt in wert:
                suchen(inhalt, tiefe + 1)

    suchen(daten)
    for _, adresse in sorted(gefunden, key=lambda g: g[0]):
        if adresse.lower().startswith("https://"):
            return adresse
    return ""


class PdfZuGross(Exception):
    pass


class _NurHttps(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf https, höchstens drei."""

    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).lower().startswith("https://"):
            raise urllib.error.HTTPError(req.full_url, code, "Weiterleitung nicht auf https", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Eigener Zugang ohne Cookies und ohne Browserprofil: Die befristete PDF-Adresse braucht
# keine Anmeldung, also bekommt sie auch keine. (build_opener hat keinen Cookie-Speicher.)
_oeffner = urllib.request.build_opener(_NurHttps)


class DownloadUnvollstaendig(Exception):
    pass


#: Gesamtfrist je Download, zusätzlich zur Frist je Leseschritt: Ein Server, der
#: tröpfchenweise sendet, soll den Lauf nicht beliebig aufhalten.
GESAMTFRIST_S = 120
_STUECK = 64 * 1024


def _adresse_erlaubt(adresse: str) -> bool:
    return adresse.lower().startswith("https://")


def pdf_herunterladen(adresse: str) -> bytes:
    """Lädt das PDF ohne Cookies, nur über https, höchstens 20 MB, in höchstens
    GESAMTFRIST_S Sekunden. Ein abgebrochener Download wird erkannt (Länge gegen
    Content-Length, unvollständige Übertragung) und nie als Rechnung weitergegeben —
    PyMuPDF würde ein gekürztes PDF sonst stillschweigend reparieren.
    Fehlermeldungen nennen die Adresse nie (sie enthält ein Zugangstoken)."""
    if not _adresse_erlaubt(adresse):
        raise RuntimeError("PDF-Adresse ist nicht https")
    ende = time.monotonic() + GESAMTFRIST_S
    try:
        anfrage = urllib.request.Request(adresse, headers={"User-Agent": "belegabruf", "Accept": "application/pdf"})
        with _oeffner.open(anfrage, timeout=60) as antwort:
            angekuendigt = None
            laenge = antwort.headers.get("Content-Length")
            if laenge and str(laenge).strip().isdigit():
                angekuendigt = int(laenge)
                if angekuendigt > pruefung.MAX_PDF_BYTES:
                    raise PdfZuGross()
            # read1 gibt zurück, was gerade da ist; read(n) würde warten, bis n Bytes da sind —
            # dann griffe die Gesamtfrist bei einem tröpfelnden Server nicht.
            lesen = getattr(antwort, "read1", antwort.read)
            teile: list[bytes] = []
            gesamt = 0
            while True:
                if time.monotonic() > ende:
                    raise DownloadUnvollstaendig(f"Download dauerte länger als {GESAMTFRIST_S} Sekunden")
                stueck = lesen(_STUECK)
                if not stueck:
                    break
                teile.append(stueck)
                gesamt += len(stueck)
                if gesamt > pruefung.MAX_PDF_BYTES:
                    raise PdfZuGross()
            inhalt = b"".join(teile)
    except (PdfZuGross, DownloadUnvollstaendig):
        raise
    except http.client.IncompleteRead:
        raise DownloadUnvollstaendig("Download abgebrochen") from None
    except urllib.error.HTTPError as fehler:
        raise RuntimeError(f"PDF-Adresse antwortet mit {fehler.code}") from None
    except urllib.error.URLError as fehler:
        raise RuntimeError(f"PDF-Adresse nicht erreichbar ({type(fehler.reason).__name__})") from None
    except Exception as fehler:  # noqa: BLE001 - z. B. InvalidURL: nie die Adresse weitergeben
        raise RuntimeError(f"PDF nicht ladbar ({type(fehler).__name__})") from None
    if angekuendigt is not None and len(inhalt) != angekuendigt:
        raise DownloadUnvollstaendig(f"Download abgebrochen ({len(inhalt)} von {angekuendigt} Bytes)")
    return inhalt


def pdf_pruefen(inhalt: bytes | None) -> str | None:
    """None, wenn es ein brauchbares PDF ist, sonst der Grund."""
    if not inhalt:
        return "leere Datei"
    if not pruefung.ist_pdf(inhalt):
        return "kein PDF"
    try:
        import pymupdf

        with pymupdf.open(stream=inhalt, filetype="pdf") as dok:
            if dok.page_count < 1:
                return "PDF ohne Seiten"
    except Exception:  # noqa: BLE001
        return "PDF nicht lesbar"
    return None


def dateiname(datum: date | None, kennung: str) -> str:
    """<JJJJ-MM-TT>_xentra_<rechnungs-id>.pdf — nie mit Beschreibungstext."""
    tag = datum.isoformat() if datum else "ohne-datum"
    return f"{tag}_xentra_{re.sub(r'[^A-Za-z0-9_-]', '', kennung) or 'ohne-id'}.pdf"


@dataclass
class Zeile:
    """Eine sichtbare Tabellenzeile. Die Beschreibung wird absichtlich nicht gelesen."""

    nummer: int  # Position unter den sichtbaren Zeilen mit PDF-Knopf
    datum: date | None
    betrag: str


def _aufrufen(seite, url: str):
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


# JavaScript: sichtbare Zeilen mit PDF-Knopf, je Zeile nur Datum und Betrag (keine Beschreibung).
_ZEILEN_JS = r"""(knopf) => {
  const sichtbar = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)
                        && getComputedStyle(e).visibility !== 'hidden';
  const knoepfe = [...document.querySelectorAll(knopf)].filter(sichtbar);
  return knoepfe.map(k => {
    // Zeile: die Tabellenzeile, sonst das nächste Element nach oben, das ein Datum enthält.
    let zeile = k.closest('tr, [role=row]');
    if (!zeile) {
      zeile = k.parentElement;
      while (zeile && !/\d{1,2}\.\d{1,2}\.20\d{2}/.test(zeile.innerText || '')) zeile = zeile.parentElement;
    }
    const text = zeile ? zeile.innerText : '';
    const datum = (text.match(/\b\d{1,2}\.\d{1,2}\.20\d{2}\b/) || [''])[0];
    const betrag = (text.match(/-?\d[\d.]*,\d{2}\s?€|€\s?-?\d[\d.]*,\d{2}/) || [''])[0];
    return [datum, betrag];
  });
}"""


class Xentra(Quelle):
    name = "xentra"
    anzeigename = "Xentra"

    def _adresse(self) -> str:
        return str(self.konto.optionen.get("adresse") or ADRESSE).rstrip("/")

    # 1. Sitzung prüfen ------------------------------------------------------
    def sitzung_pruefen(self) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=False) as kontext:
            seite = browser.neue_seite(kontext)
            _aufrufen(seite, self._adresse() + ABRECHNUNG_PFAD)
            return self._reiter_da(seite, warten_ms=20000)

    def _reiter_da(self, seite, warten_ms: int) -> bool:
        if _ist_anmeldeseite(seite.url):
            return False
        try:
            seite.get_by_role("tab", name="Rechnungen").first.wait_for(timeout=warten_ms)
        except Exception:  # noqa: BLE001
            return False
        return not _ist_anmeldeseite(seite.url) and ABRECHNUNG_PFAD in seite.url

    def _angemeldet_im_fenster(self, seite) -> bool:
        url = seite.url.lower()
        return "myxentra.com" in url and not _ist_anmeldeseite(url) and "about:blank" not in url

    # 2. Anmelden lassen -----------------------------------------------------
    def anmelden_lassen(self, melden: Callable[[str], None]) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=True) as kontext:
            seite = browser.neue_seite(kontext)
            seite.goto(self._adresse() + ABRECHNUNG_PFAD, wait_until="domcontentloaded")
            seite.wait_for_timeout(2000)
            if not _ist_anmeldeseite(seite.url) and self._reiter_da(seite, warten_ms=5000):
                return True
            browser.auf_mensch_warten(kontext, seite, self._angemeldet_im_fenster, melden)
        return self.sitzung_pruefen()

    # 3. Belege holen --------------------------------------------------------
    def _zeilen_laden(self, seite) -> list[Zeile]:
        _aufrufen(seite, self._adresse() + ABRECHNUNG_PFAD)
        if not self._reiter_da(seite, warten_ms=30000):
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen()
            raise RuntimeError("Reiter „Rechnungen“ nicht gefunden")
        seite.get_by_role("tab", name="Rechnungen").first.click()
        try:
            # Die versteckte Handy-Tabelle steht zuerst in der Seite: auf einen sichtbaren Knopf warten.
            seite.locator(KNOPF).locator("visible=true").first.wait_for(state="visible", timeout=20000)
        except Exception:  # noqa: BLE001 - vielleicht gibt es (noch) keine Rechnungen
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen() from None
            return []
        seite.wait_for_timeout(800)
        roh = seite.evaluate(_ZEILEN_JS, KNOPF)
        return [Zeile(nummer=i, datum=datum_lesen(d), betrag=b) for i, (d, b) in enumerate(roh)]

    def _knopf(self, seite, nummer: int):
        return seite.locator(KNOPF).locator("visible=true").nth(nummer)

    def _pdf_laden(self, kontext, adresse: str) -> bytes:
        # Bewusst nicht über den Browser (kontext.request): der schickte die Cookies mit.
        return pdf_herunterladen(adresse)

    def _klicken(self, kontext, seite, zeile: Zeile) -> tuple[str, str]:
        """Klickt „PDF herunterladen“ und liest Rechnungs-ID und PDF-Adresse mit.
        Das neue Fenster wird gleich wieder geschlossen."""
        knopf = self._knopf(seite, zeile.nummer)
        popup = None
        try:
            with seite.expect_response(lambda r: DOWNLOAD_AUFRUF in r.url and r.request.method == "POST",
                                       timeout=60000) as warten:
                with kontext.expect_page(timeout=15000) as neues_fenster:
                    knopf.click()
                popup = neues_fenster.value
            antwort = warten.value
            kennung = rechnungs_id_aus_anfrage(antwort.request.post_data)
            if antwort.status >= 400:
                raise RuntimeError(f"Xentra antwortet beim Download mit {antwort.status}")
            try:
                adresse = pdf_adresse_aus_antwort(antwort.text())
            except Exception:  # noqa: BLE001
                adresse = ""
            if not adresse and popup is not None:
                # Die Seite schickt das neue Fenster selbst zum PDF — dort nachsehen.
                try:
                    popup.wait_for_url(lambda u: u.startswith("https://"), timeout=15000)
                    adresse = popup.url
                except Exception:  # noqa: BLE001
                    adresse = ""
            return kennung, adresse
        finally:
            if popup is not None:
                try:
                    popup.close()
                except Exception:  # noqa: BLE001
                    pass

    def belege_holen(self, umgebung: Umgebung) -> Ergebnis:
        erg = Ergebnis(self.name, self.konto.name)
        melden = umgebung.melden
        with browser.profil_oeffnen(self.profil, sichtbar=umgebung.sichtbar) as kontext:
            seite = browser.neue_seite(kontext)
            try:
                zeilen = self._zeilen_laden(seite)
            except SitzungAbgelaufen:
                erg.status = "abgelaufen"
                return erg
            except Exception as fehler:  # noqa: BLE001
                erg.status = "unvollstaendig"
                erg.abweichungen.append(f"Rechnungsliste nicht geladen ({_kurz(fehler)}).")
                return erg
            melden(f"{len(zeilen)} Rechnung(en) in der Liste.")
            # Zeitraum: ältere Zeilen gar nicht erst anklicken und nicht vermerken.
            erg.uebersprungen = sum(1 for z in zeilen if umgebung.zu_alt(z.datum))
            zeilen = [z for z in zeilen if not umgebung.zu_alt(z.datum)]
            erg.erwartet = len(zeilen)
            erg.vorhanden = 0
            for zeile in zeilen:
                bezeichnung = (f"Rechnung vom {zeile.datum:%d.%m.%Y}" if zeile.datum
                               else f"Rechnung Nr. {zeile.nummer + 1}")
                browser.pause()
                try:
                    kennung, adresse = self._klicken(kontext, seite, zeile)
                except Exception as fehler:  # noqa: BLE001 - eine Zeile darf scheitern
                    if _ist_anmeldeseite(seite.url):
                        erg.status = "abgelaufen"
                        melden("Die Anmeldung ist abgelaufen. Der nächste Lauf holt den Rest nach.")
                        break
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung}: nicht geholt ({_kurz(fehler)}).")
                    continue
                if not kennung:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung}: Rechnungs-ID nicht erkannt, nicht gespeichert.")
                    continue
                schluessel = f"rechnung:{kennung}"
                if umgebung.bekannt(schluessel):
                    erg.schon_da += 1
                    erg.vorhanden += 1
                    continue
                if not adresse:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung} ({kennung}): keine PDF-Adresse erhalten.")
                    continue
                try:
                    inhalt = self._pdf_laden(kontext, adresse)
                except DownloadUnvollstaendig as fehler:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung} ({kennung}): {fehler}, nicht gespeichert — "
                                            "der nächste Lauf versucht es erneut.")
                    continue
                except PdfZuGross:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung} ({kennung}): PDF größer als "
                                            f"{pruefung.MAX_PDF_BYTES // (1024 * 1024)} MB, nicht gespeichert.")
                    continue
                except Exception as fehler:  # noqa: BLE001
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung} ({kennung}): PDF nicht geladen ({_kurz(fehler)}).")
                    continue
                grund = pdf_pruefen(inhalt)
                if grund:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(f"{bezeichnung} ({kennung}): nicht gespeichert ({grund}).")
                    continue
                orte = umgebung.abliefern(Beleg(
                    quelle=self.name, konto=self.konto.name, art="rechnung", schluessel=schluessel,
                    dateiname=dateiname(zeile.datum, kennung), inhalt=inhalt,
                    jahr=zeile.datum.year if zeile.datum else date.today().year,
                    rechnungsdatum=zeile.datum, rechnungsnummer=kennung, betrag=zeile.betrag,
                ))
                erg.neu += 1
                erg.vorhanden += 1
                erg.neue_dateien += orte
        return erg
