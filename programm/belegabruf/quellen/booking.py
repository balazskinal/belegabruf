"""Baustein Booking.com: Kommissionsrechnungen, Auszahlungsübersichten und Auszahlungen.

Alles liegt im Extranet (``https://admin.booking.com``). Nach der Anmeldung tragen alle
Seiten ``hotel_id`` (die Unterkunft) und ``ses`` (den Sitzungsschlüssel) in der Adresse.
Als angemeldet gilt ein Konto aber erst, wenn das Extranet Inhalt zeigt (Links auf eine
Unterkunft) — die Adresse allein reicht nicht, sie kann schon während der Zwei-Faktor-
Bestätigung so aussehen (siehe ``angemeldet``).
``ses`` liest das Programm nur aus der aktuellen Seite und hält es im Speicher — es
steht nie in Protokoll, Ausgaben, Fehlermeldungen oder Dateinamen.

Drei Arten von Dokumenten (siehe ADR-006):

1. **Rechnungen** — Finanzen → Rechnungen, Reiter „Zahlungen an Booking.com“: je Monat
   eine Kommissionsrechnung mit Link „PDF“ (``/fresa/extranet/finance/invoices/get_document``).
   Jahresfilter über ``&year=JJJJ`` in der Adresse. **Das sind die Belege** (Art
   ``rechnung``); nur sie gehen an Lieferziele wie Mail.
2. **Auszahlungsübersichten** — derselbe Seite, Reiter „Zahlungen von Booking.com“: je
   Monat PDF (``monthlyStatementPDF``) und CSV (``historyCSV``). Jahresfilter über das
   Auswahlfeld „Nach Jahr filtern“. Art ``auszahlungsuebersicht``, nur abgelegt.
3. **Auszahlungen** — Finanzen → Informationen zu Auszahlungen: je Auszahlung PDF
   (``payoutPDF``) und CSV (``payoutCSV``). Zeitraum „Dieses Jahr“ bzw. „Letztes Jahr“.
   Art ``auszahlung``, nur abgelegt. Der Dateiname nennt Auszahlungsdatum,
   Buchungsnummer(n) und Check-in aus der CSV.

**Regel: nur lesen und herunterladen.** Angeklickt werden nur der Reiter „Zahlungen von
Booking.com“, der Jahresfilter und das Zeitraum-Auswahlfeld. Dateien lädt die Seite
selbst (``fetch`` mit ihrer Anmeldung), wie beim Klick auf „PDF“.

**Gastnamen** stehen in den Auszahlungs-CSV (Spalte „Name des Gastes“). Das Programm
liest daraus nur Buchungsnummer, Check-in, Auszahlungsdatum und -nummer; Namen kommen
nie in Dateinamen, Protokoll oder Ausgaben. Die CSV-Datei selbst wird unverändert
abgelegt (sie ist das Dokument von Booking.com).

**Mehrere Unterkünfte:** Geholt wird die Unterkunft, auf der das Extranet nach der
Anmeldung landet. Mehrere: ``unterkunft = "<id>, <id>"`` im Konto (Einstellungsdatei),
jede wird für sich geholt. Landet das Extranet auf einer Gruppen-Startseite ohne
Unterkunft, holt es alle dort verlinkten. Bei mehr als einer Unterkunft steht ihre ID im
Dateinamen; im Protokoll immer.

Ablage (Ablage nach Jahr; nach Monat zusätzlich <MM>/):
    booking/Rechnungen (an Booking.com)/<JJJJ>/<JJJJ-MM-TT>_booking_<nummer>.pdf
    booking/Auszahlungsübersichten (von Booking.com)/<JJJJ>/<JJJJ-MM>_auszahlungsuebersicht.pdf|.csv
    booking/Auszahlungen/<JJJJ>/<JJJJ-MM-TT>_auszahlung_<buchungsnr>[_…|+n]_checkin-<JJJJ-MM-TT>.pdf|.csv
"""

from __future__ import annotations

import base64
import calendar
import csv
import io
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qs, urlencode, urlsplit

from belegabruf import browser, pruefung
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung

ADRESSE = "https://admin.booking.com"
EXTRANET = "/hotel/hoteladmin/extranet_ng/manage/"
RECHNUNGEN_SEITE = EXTRANET + "finance_invoices.html"
AUSZAHLUNGEN_SEITE = EXTRANET + "payouts.html"

RECHNUNG_LINK = "get_document"
UEBERSICHT_PDF = "monthlyStatementPDF"
UEBERSICHT_CSV = "historyCSV"
AUSZAHLUNG_PDF = "payoutPDF"
AUSZAHLUNG_CSV = "payoutCSV"
REITER_VON = "Zahlungen von Booking.com"
ZEITRAUM_FELD = "#report-period-filter"

#: Unterordner je Dokumentart (unter booking/). Für Menschen lesbar.
UNTERORDNER = {
    "rechnung": "Rechnungen (an Booking.com)",
    "auszahlungsuebersicht": "Auszahlungsübersichten (von Booking.com)",
    "auszahlung": "Auszahlungen",
}

#: Höchstens so viele Buchungsnummern im Dateinamen einer Auszahlung, dann „+n“.
HOECHSTENS_NUMMERN = 3

MONATE = {
    "jan": 1, "feb": 2, "mär": 3, "mar": 3, "mrz": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}
RE_DATUM = re.compile(r"\b(\d{1,2})\.?\s*([A-Za-zÄÖÜäöü]{3,})\.?\s+(20\d{2})\b")
RE_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
RE_NUMMER = re.compile(r"^\d{5,20}$")
RE_UUID = re.compile(r"^[0-9a-fA-F-]{8,64}$")
RE_HOTEL = re.compile(r"^\d{1,15}$")
RE_ADRESSE = re.compile(r"https?://\S+|\bses=[^&\s\"']+", re.I)


# ── Hilfen ohne Browser (getestet mit erfundenen Daten) ──────────────────────


def heute() -> date:
    return date.today()


def datum_lesen(text: str | None) -> date | None:
    """„3. Nov. 2026“, „26. Nov. 2026“, „3 Juli 2026“ oder „2026-11-03“ → Datum."""
    text = text or ""
    m = RE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = RE_DATUM.search(text)
    if not m:
        return None
    monat = MONATE.get(m.group(2)[:3].lower())
    if monat is None:
        return None
    try:
        return date(int(m.group(3)), monat, int(m.group(1)))
    except ValueError:
        return None


def ist_anmeldeseite(url: str) -> bool:
    url = (url or "").lower()
    return "account.booking.com" in url or "/sign-in" in url or "sign_in" in url or "/login" in url


def ist_extranet(url: str) -> bool:
    teile = urlsplit(url or "")
    return teile.netloc.endswith("admin.booking.com") and "/hoteladmin/" in teile.path and not ist_anmeldeseite(url)


def hat_unterkunft(links: list[str]) -> bool:
    """Zeigt die Seite Inhalt einer Unterkunft? Mindestens ein Link auf admin.booking.com mit
    gültiger ``hotel_id`` (Menü bzw. Unterkunftsauswahl des Extranets)."""
    return any(ist_eigene_adresse(str(link)) and RE_HOTEL.fullmatch(parameter(str(link)).get("hotel_id", ""))
               for link in links or [])


def angemeldet(url: str, links: list[str]) -> bool:
    """Angemeldet ist ein Konto erst, wenn eine geschützte Extranet-Seite wirklich Inhalt zeigt:
    Extranet-Adresse mit ``ses`` **und** mindestens eine Unterkunft in den Links. Die Adresse allein
    reicht nicht — während der Zwei-Faktor-Bestätigung kann sie schon wie das Extranet aussehen."""
    return ist_extranet(url) and "ses" in parameter(url) and hat_unterkunft(links)


#: Merkmale einer geladenen Finanzseite (Rechnungs-/Übersichts-/Auszahlungslinks, Reiter,
#: Zeitraumfeld). Mitten im Abruf zählt eine Seite als Extranet mit Inhalt, wenn sie eine
#: Unterkunft verlinkt oder eines dieser Merkmale zeigt — so gilt ein Jahr ohne Rechnungen
#: nicht als Bestätigungsseite.
FINANZ_MERKMALE = ('a[href*="get_document"], a[href*="monthlyStatementPDF"], a[href*="payoutPDF"], '
                   '#report-period-filter, [role=tablist]')

#: So lange (ms) wartet die Prüfung, bis die Extranet-Seite ihre Unterkünfte zeigt.
INHALT_WARTEN_MS = 30000
#: Nach so vielen Sekunden auf einer Extranet-Adresse ohne Inhalt kommt der Zwei-Faktor-Hinweis
#: (vorher nicht — sonst sähe ihn jeder kurz, solange die Seite nach der Anmeldung lädt).
ZWEI_FAKTOR_HINWEIS_NACH_S = 5.0
ZWEI_FAKTOR_HINWEIS = ("Noch nicht angemeldet: Bitte schließ die Bestätigung (Zwei-Faktor) im Booking-Fenster ab. "
                       "Danach geht es von allein weiter.")


def sauber(text: str) -> str:
    """Entfernt Adressen und Sitzungsschlüssel aus einem Text (für Meldungen)."""
    return RE_ADRESSE.sub("…", str(text or ""))


#: Von hier (und nur von hier) lädt die Quelle Dateien.
HOSTS = {"admin.booking.com"}


def ist_eigene_adresse(url: str) -> bool:
    """Nur https://admin.booking.com (gemeinsame Prüfung ``pruefung.adresse_erlaubt``)."""
    return pruefung.adresse_erlaubt(url, HOSTS)


def parameter(url: str) -> dict[str, str]:
    """hotel_id, ses und lang aus der Adresse der aktuellen Seite (nur im Speicher halten)."""
    werte = parse_qs(urlsplit(url or "").query)
    return {k: werte[k][0] for k in ("hotel_id", "ses", "lang") if werte.get(k)}


def seitenadresse(pfad: str, hotel_id: str, ses: str, **extra: str) -> str:
    return f"{ADRESSE}{pfad}?" + urlencode({"hotel_id": hotel_id, "lang": "de", "ses": ses, **extra})


class UnterkunftUngueltig(Exception):
    """Die Einstellung ``unterkunft`` enthält etwas, das keine Unterkunfts-ID ist."""


def unterkunft_einstellung(wert: object) -> list[str]:
    """``unterkunft`` aus dem Konto: "123", "123, 456", 123 oder ["123", "456"]. Leer = [].
    Wirft UnterkunftUngueltig, wenn ein Teil keine ID ist (nicht still verwerfen)."""
    if wert is None or wert == "" or wert == []:
        return []
    teile = wert if isinstance(wert, list) else str(wert).split(",")
    ids = [str(t).strip() for t in teile if str(t).strip()]
    falsch = [i for i in ids if not RE_HOTEL.fullmatch(i)]
    if falsch or not ids:
        raise UnterkunftUngueltig(
            f"Einstellung unterkunft = „{sauber(str(wert))[:60]}“: Erwartet wird die Unterkunfts-ID (nur Ziffern), "
            "mehrere mit Komma, z. B. unterkunft = \"1234567, 7654321\". Bitte in der Einstellungsdatei korrigieren.")
    return list(dict.fromkeys(ids))


def unterkuenfte(seiten_url: str, links: list[str], einstellung: object = "") -> list[str]:
    """Welche Unterkünfte geholt werden.

    * ``einstellung`` (``unterkunft = "<ID>"`` bzw. mehrere mit Komma im Konto): genau diese.
    * Sonst die Unterkunft, auf der das Extranet nach der Anmeldung landet (``hotel_id`` der
      Adresse). Links der Startseite zählen nicht — dort stehen auch fremde IDs (beim echten
      Lauf am 26.11.2026 eine zweite ohne Rechnungen).
    * Landet es auf einer Gruppen-Startseite ohne ``hotel_id``: alle IDs aus deren Links."""
    eigene = unterkunft_einstellung(einstellung)
    if eigene:
        return eigene
    hier = parameter(seiten_url).get("hotel_id", "")
    if RE_HOTEL.fullmatch(hier):
        return [hier]
    gefunden: list[str] = []
    for adresse in links:
        hotel = parameter(adresse).get("hotel_id", "")
        if RE_HOTEL.fullmatch(hotel) and hotel not in gefunden:
            gefunden.append(hotel)
    return gefunden


@dataclass
class Rechnung:
    nummer: str
    datum: date | None
    url: str  # enthält ses — nie ausgeben


@dataclass
class Uebersicht:
    jahr: int
    monat: int
    pdf: str = ""
    csv: str = ""


@dataclass
class Auszahlung:
    kennung: str  # payout_uuid
    datum: date | None
    pdf: str = ""
    csv: str = ""


@dataclass
class AuszahlungsDaten:
    """Was aus der Auszahlungs-CSV gelesen wird — bewusst ohne Gastnamen."""

    buchungsnummern: list[str] = field(default_factory=list)
    checkins: list[date] = field(default_factory=list)
    datum: date | None = None
    nummer: str = ""


def rechnungen_aus_links(roh: list[dict]) -> list[Rechnung]:
    """roh: [{"href": …, "datum": "3. Nov. 2026"}] aus der Seite. Nummer aus
    ``invoice_name`` (z. B. „1000-1234567890“ → „1234567890“)."""
    ergebnis: dict[str, Rechnung] = {}
    for eintrag in roh:
        href = str(eintrag.get("href") or "")
        if RECHNUNG_LINK not in href or not ist_eigene_adresse(href):
            continue
        name = parse_qs(urlsplit(href).query).get("invoice_name", [""])[0]
        nummer = name.rsplit("-", 1)[-1]
        if not RE_NUMMER.fullmatch(nummer):
            continue
        ergebnis.setdefault(nummer, Rechnung(nummer=nummer, datum=datum_lesen(eintrag.get("datum")), url=href))
    return list(ergebnis.values())


def uebersichten_aus_links(roh: list[dict]) -> list[Uebersicht]:
    ergebnis: dict[tuple[int, int], Uebersicht] = {}
    for eintrag in roh:
        href = str(eintrag.get("href") or "")
        if not ist_eigene_adresse(href):
            continue
        werte = parse_qs(urlsplit(href).query)
        try:
            jahr, monat = int(werte["year"][0]), int(werte["month"][0])
        except (KeyError, ValueError, IndexError):
            continue
        if not (2000 <= jahr <= 2100 and 1 <= monat <= 12):
            continue
        u = ergebnis.setdefault((jahr, monat), Uebersicht(jahr, monat))
        if UEBERSICHT_PDF in href:
            u.pdf = href
        elif UEBERSICHT_CSV in href:
            u.csv = href
    return sorted(ergebnis.values(), key=lambda u: (u.jahr, u.monat))


def auszahlungen_aus_links(roh: list[dict]) -> list[Auszahlung]:
    ergebnis: dict[str, Auszahlung] = {}
    for eintrag in roh:
        href = str(eintrag.get("href") or "")
        if not ist_eigene_adresse(href):
            continue
        kennung = parse_qs(urlsplit(href).query).get("payout_uuid", [""])[0]
        if not RE_UUID.fullmatch(kennung):
            continue
        a = ergebnis.setdefault(kennung, Auszahlung(kennung, datum_lesen(eintrag.get("datum"))))
        if AUSZAHLUNG_PDF in href:
            a.pdf = href
        elif AUSZAHLUNG_CSV in href:
            a.csv = href
    return list(ergebnis.values())


def auszahlung_lesen(inhalt: bytes) -> AuszahlungsDaten:
    """Liest Buchungsnummern, Check-ins, Datum und Nummer der Auszahlung aus der CSV.
    Die Spalte „Name des Gastes“ wird nie gelesen."""
    text = inhalt.decode("utf-8-sig", errors="replace")
    daten = AuszahlungsDaten()
    for zeile in csv.DictReader(io.StringIO(text)):
        nummer = (zeile.get("Buchungsnummer") or "").strip()
        if RE_NUMMER.fullmatch(nummer) and nummer not in daten.buchungsnummern:
            daten.buchungsnummern.append(nummer)
        checkin = datum_lesen(zeile.get("Check-in"))
        if checkin and checkin not in daten.checkins:
            daten.checkins.append(checkin)
        daten.datum = daten.datum or datum_lesen(zeile.get("Datum der Auszahlung"))
        auszahlungsnummer = re.sub(r"[^A-Za-z0-9]", "", zeile.get("Auszahlungsnummer") or "")[:40]
        daten.nummer = daten.nummer or auszahlungsnummer
    return daten


def _id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "", text)[:40]


def _hotel(hotel: str, mehrere: bool) -> str:
    return f"_{_id(hotel)}" if mehrere else ""


def rechnung_dateiname(r: Rechnung, hotel: str = "", mehrere: bool = False) -> str:
    tag = r.datum.isoformat() if r.datum else "ohne-datum"
    return f"{tag}_booking_{_id(r.nummer)}{_hotel(hotel, mehrere)}.pdf"


def uebersicht_dateiname(u: Uebersicht, endung: str, hotel: str = "", mehrere: bool = False) -> str:
    return f"{u.jahr:04d}-{u.monat:02d}_auszahlungsuebersicht{_hotel(hotel, mehrere)}.{endung}"


def auszahlung_dateiname(datum: date | None, daten: AuszahlungsDaten, endung: str,
                         hotel: str = "", mehrere: bool = False) -> str:
    """<Datum>_auszahlung_<Buchungsnr>[_<Nr>…|+n]_checkin-<frühester Check-in>.<endung>"""
    tag = (daten.datum or datum).isoformat() if (daten.datum or datum) else "ohne-datum"
    nummern = daten.buchungsnummern[:HOECHSTENS_NUMMERN]
    teil = "_".join(nummern) if nummern else "ohne-buchung"
    rest = len(daten.buchungsnummern) - len(nummern)
    if rest > 0:
        teil += f"+{rest}"
    checkin = f"_checkin-{min(daten.checkins).isoformat()}" if daten.checkins else ""
    return f"{tag}_auszahlung_{teil}{checkin}{_hotel(hotel, mehrere)}.{endung}"


def monatsende(jahr: int, monat: int) -> date:
    return date(jahr, monat, calendar.monthrange(jahr, monat)[1])


def jahre_noetig(verfuegbar: list[int], ab: date | None, vorlauf: int = 0) -> list[int]:
    """Welche Jahre des Filters gebraucht werden (neueste zuerst). ``vorlauf``: so viele
    Jahre vor dem Zeitraum zusätzlich (die Dezember-Rechnung steht im Filter des Vorjahres)."""
    jahre = sorted(set(verfuegbar), reverse=True)
    if ab is None:
        return jahre
    return [j for j in jahre if j >= ab.year - vorlauf]


# JavaScript: Links mit einem der Muster; je Link die Adresse und nur das erste Datum der Zeile
# (keine weiteren Zeileninhalte — in Auszahlungszeilen könnten sonst Namen stehen).
_LINKS_JS = r"""(muster) => {
  const re = /\b\d{1,2}\.?\s*[A-Za-zÄÖÜäöü]{3,}\.?\s+20\d{2}\b/;
  return [...document.querySelectorAll('a[href]')]
    .filter(a => muster.some(m => a.href.includes(m)))
    .map(a => {
      const zeile = a.closest('tr') || a.parentElement;
      const treffer = zeile ? (zeile.innerText || '').match(re) : null;
      return {href: a.href, datum: treffer ? treffer[0] : ''};
    });
}"""

# JavaScript: alle Links mit hotel_id (Unterkunftsauswahl, Menü) — nur die Adressen.
_HOTEL_LINKS_JS = "() => [...document.querySelectorAll('a[href*=\"hotel_id=\"]')].map(a => a.href)"

# JavaScript: eine Datei mit der Anmeldung der Seite laden (wie ein Klick auf „PDF“).
_LADEN_JS = r"""async ([adresse, hoechstens]) => {
  const antwort = await fetch(adresse, {credentials: 'include'});
  const typ = antwort.headers.get('content-type') || '';
  const ziel = antwort.url || '';
  if (!ziel.startsWith('https://admin.booking.com/')) return {status: -1, typ, ziel, daten: ''};
  if (!antwort.ok) return {status: antwort.status, typ, ziel, daten: ''};
  const puffer = new Uint8Array(await antwort.arrayBuffer());
  if (puffer.length > hoechstens) return {status: 413, typ, ziel, daten: ''};
  let s = '';
  for (let i = 0; i < puffer.length; i += 0x8000) s += String.fromCharCode(...puffer.subarray(i, i + 0x8000));
  return {status: antwort.status, typ, ziel, daten: btoa(s)};
}"""


class BestaetigungNoetig(SitzungAbgelaufen):
    """Mitten im Abruf zeigt Booking.com statt der Finanzseite eine Bestätigung (Zwei-Faktor) oder
    eine andere Seite ohne Extranet-Inhalt. Booking.com fragt laut seiner Hilfe je nach Aktion
    erneut nach, auch mehrmals am Tag. Zählt wie ein Ablauf der Anmeldung."""


class KeinFinanzZugriff(Exception):
    """Das Extranet lädt, aber dieses Konto darf die Finanzen dieser Unterkunft nicht sehen
    (z. B. ohne das Recht „Finance“)."""


BESTAETIGEN_HINWEIS = ("Booking.com hat mitten im Abruf eine Bestätigung verlangt (Zwei-Faktor). Bitte bei "
                       "diesem Konto neu anmelden und bestätigen — der nächste Lauf holt den Rest nach.")
KEIN_ZUGRIFF_TEXT = ("Dieses Booking-Konto hat keinen Zugriff auf Finanzen. Bitte vom Eigentümer für die "
                     "Unterkunft das Recht „Finance“ (oder Admin) geben lassen oder mit einem Konto anmelden, "
                     "das die Finanzen sieht.")
#: Nur einzelne Unterkünfte ohne Finanzrecht (z. B. Co-Hosting): je Unterkunft als Abweichung.
KEIN_ZUGRIFF_UNTERKUNFT = ("Unterkunft {hotel}: kein Zugriff auf Finanzen für diese Unterkunft — bitte vom "
                           "Eigentümer das Recht „Finance“ geben lassen. Die übrigen Unterkünfte wurden geholt.")

#: Woran eine Seite ohne Finanzberechtigung zu erkennen ist (nur geprüft, wenn die erwarteten
#: Rechnungslinks und der Jahresfilter fehlen; der Text wird nie gespeichert oder ausgegeben).
#: Nur ganze Wörter: „no access“ trifft, „no accessible“ oder „unauthorized_tab“ nicht.
#: Felder, an denen eine Bestätigungs- oder Anmeldeseite zu erkennen ist.
EINGABE_MERKMALE = ('input[type=password], input[autocomplete="one-time-code"], input[name*="code" i], '
                    'input[id*="code" i], input[inputmode=numeric]')

#: Sperrseite eines Netzwerkdienstes (z. B. Akamai „Access Denied … Reference #…“), kein Rechteproblem.
RE_SPERRSEITE = re.compile(r"\bReference\s+#\s*[0-9a-f.]+|errors\.edgesuite\.net|\bRay ID\b", re.I)

RE_KEIN_ZUGRIFF = re.compile(
    r"\b(?:keinen\s+zugriff|keine\s+berechtigung|nicht\s+berechtigt|zugriff\s+verweigert|"
    r"(?:don['’]t|do\s+not|doesn['’]t|does\s+not)\s+have\s+(?:access|permission)|no\s+access|"
    r"access\s+denied|not\s+authori[sz]ed)\b",
    re.I)


def ohne_finanz_zugriff(status: int | None, text: str) -> bool:
    """403 beim Laden der Finanzseite oder ein eindeutiger Hinweis im Seitentext."""
    return status == 403 or bool(RE_KEIN_ZUGRIFF.search(text or ""))


class DateiFehler(Exception):
    """Eine Datei kam nicht oder nicht brauchbar an (Meldung ohne Adresse)."""


def _aufrufen(seite, url: str):
    for versuch in (1, 2):
        try:
            antwort = seite.goto(url, wait_until="commit", timeout=60000)
            seite.wait_for_load_state("domcontentloaded", timeout=60000)
            return antwort
        except Exception as fehler:  # noqa: BLE001
            if versuch == 2:
                raise DateiFehler(f"Seite nicht geladen ({type(fehler).__name__})") from None
            browser.pause(5, 10)
    return None


class Booking(Quelle):
    name = "booking"
    anzeigename = "Booking.com"

    # 1. Sitzung prüfen ------------------------------------------------------
    def _angemeldet(self, seite, warten_ms: int = 0) -> bool:
        """Zeigt diese Seite das Extranet mit Inhalt (siehe ``angemeldet``)? Mit ``warten_ms``
        wartet sie so lange auf die Unterkunfts-Links. Liest nur Adressen, nichts ins Protokoll."""
        try:
            if not ist_extranet(seite.url) or "ses" not in parameter(seite.url):
                return False
            if warten_ms:
                try:
                    seite.wait_for_selector('a[href*="hotel_id="]', timeout=warten_ms)
                except Exception:  # noqa: BLE001 - kein Inhalt (z. B. Zwei-Faktor offen)
                    return False
            return angemeldet(seite.url, seite.evaluate(_HOTEL_LINKS_JS))
        except Exception:  # noqa: BLE001 - Seite lädt gerade neu oder ist zu
            return False

    def _fertig_pruefer(self, melden: Callable[[str], None]) -> Callable[[object], bool]:
        """Bedingung fürs Anmeldefenster: fertig erst mit Extranet-Inhalt. Steht das Fenster eine
        Weile auf einer Extranet-Adresse ohne Inhalt (offene Zwei-Faktor-Bestätigung), kommt einmal
        der Hinweis — das Fenster bleibt offen."""
        stand = {"seit": None, "gemeldet": False}

        def fertig(seite) -> bool:
            if self._angemeldet(seite):
                return True
            try:
                halb = ist_extranet(seite.url)
            except Exception:  # noqa: BLE001
                halb = False
            if not halb:
                stand["seit"] = None
                return False
            jetzt = time.monotonic()
            stand["seit"] = stand["seit"] if stand["seit"] is not None else jetzt
            if not stand["gemeldet"] and jetzt - stand["seit"] >= ZWEI_FAKTOR_HINWEIS_NACH_S:
                melden(ZWEI_FAKTOR_HINWEIS)
                stand["gemeldet"] = True
            return False

        return fertig

    def _startseite(self, seite) -> bool:
        """Öffnet das Extranet; True nur, wenn es angemeldet mit Inhalt da ist (siehe ``angemeldet``)."""
        _aufrufen(seite, ADRESSE + "/")
        try:
            seite.wait_for_url(lambda u: ist_extranet(u) or ist_anmeldeseite(u), timeout=30000)
        except Exception:  # noqa: BLE001
            return False
        return self._angemeldet(seite, warten_ms=INHALT_WARTEN_MS)

    def sitzung_pruefen(self) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=False) as kontext:
            return self._startseite(browser.neue_seite(kontext))

    def _abgemeldet(self, seite) -> bool:
        """Prüft in einem eigenen Tab, ob die Sitzung abgelaufen ist (die aktuelle Seite bleibt,
        wie sie ist). True nur bei einer echten Umleitung auf die Anmeldeseite — ein Netzfehler
        zählt nicht als Ablauf (dann „nicht geladen“)."""
        probe = seite.context.new_page()
        try:
            probe.goto(ADRESSE + "/", wait_until="commit", timeout=60000)
            probe.wait_for_url(lambda u: ist_extranet(u) or ist_anmeldeseite(u), timeout=30000)
            return ist_anmeldeseite(probe.url)
        except Exception:  # noqa: BLE001 - kein Netz o. Ä.: unklar, also nicht „abgelaufen“
            return False
        finally:
            try:
                probe.close()
            except Exception:  # noqa: BLE001 - Prüf-Tab schon zu  # nosec B110
                pass

    # 2. Anmelden lassen -----------------------------------------------------
    def anmelden_lassen(self, melden: Callable[[str], None]) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=True) as kontext:
            seite = browser.neue_seite(kontext)
            seite.goto(ADRESSE + "/", wait_until="domcontentloaded")
            seite.wait_for_timeout(3000)
            if ist_extranet(seite.url) and self._angemeldet(seite, warten_ms=min(5000, INHALT_WARTEN_MS)):
                return True
            browser.auf_mensch_warten(kontext, seite, self._fertig_pruefer(melden), melden)
        # Unabhängig davon, wie das Fenster endete (erkannt, Enter, zu, Zeitlimit): unsichtbar
        # mit derselben strengen Prüfung nachsehen.
        return self.sitzung_pruefen()

    # 3. Belege holen --------------------------------------------------------
    def _links(self, seite, muster: list[str], warten_ms: int = 20000, erg: Ergebnis | None = None,
               vorsilbe: str = "") -> list[dict]:
        """Die Links mit einem der Muster. Links auf andere Hosts werden verworfen und (mit
        ``erg``) als Abweichung gemeldet — nur mit Host, ohne Pfad und Query."""
        selektor = ", ".join(f'a[href*="{m}"]' for m in muster)
        try:
            seite.wait_for_selector(selektor, timeout=warten_ms)
        except Exception:  # noqa: BLE001 - vielleicht gibt es (in diesem Jahr) nichts
            self._noch_angemeldet(seite)  # oder Booking.com fragt gerade nach einer Bestätigung
            return []
        seite.wait_for_timeout(800)
        roh = seite.evaluate(_LINKS_JS, muster)
        fremd = sorted({pruefung.herkunft(e.get("href")) for e in roh if not ist_eigene_adresse(e.get("href", ""))})
        if erg is not None:
            for host in fremd:
                self._abweichung(erg, f"{vorsilbe}Adresse nicht vom Anbieter ({host}), nicht geholt.")
        return [e for e in roh if ist_eigene_adresse(e.get("href", ""))]

    def _laden(self, seite, adresse: str, art: str) -> bytes:
        """Lädt eine Datei mit der Anmeldung der Seite — nur von admin.booking.com, auch nach
        einer Weiterleitung. Prüft Größe und Typ."""
        if not ist_eigene_adresse(adresse):
            raise DateiFehler(str(pruefung.FremdeAdresse(adresse)))
        try:
            antwort = seite.evaluate(_LADEN_JS, [adresse, pruefung.MAX_PDF_BYTES])
        except Exception:  # noqa: BLE001 - z. B. Weiterleitung zur Anmeldung (fremder Host, fetch scheitert)
            if ist_anmeldeseite(seite.url) or self._abgemeldet(seite):
                raise SitzungAbgelaufen() from None
            raise DateiFehler("nicht geladen") from None
        ziel = str(antwort.get("ziel") or "")
        if ist_anmeldeseite(ziel) or antwort.get("status") in (401, 403):
            raise SitzungAbgelaufen()
        if antwort.get("status") == -1 or (ziel and not ist_eigene_adresse(ziel)):
            raise DateiFehler(str(pruefung.FremdeAdresse(ziel)))  # nach einer Weiterleitung
        if antwort.get("status") == 413:
            raise DateiFehler(f"größer als {pruefung.MAX_PDF_BYTES // (1024 * 1024)} MB")
        if antwort.get("status") != 200 or not antwort.get("daten"):
            raise DateiFehler(f"Booking.com antwortet mit {antwort.get('status')}")
        inhalt = base64.b64decode(antwort["daten"])
        if art == "pdf":
            if not pruefung.ist_pdf(inhalt):
                raise DateiFehler("kein PDF")
        elif "html" in str(antwort.get("typ", "")).lower() or inhalt.lstrip()[:1] == b"<":
            raise DateiFehler("keine CSV-Datei")
        return inhalt

    def _abliefern(self, umgebung: Umgebung, art: str, schluessel: str, dateiname: str, inhalt: bytes,
                   datum: date | None, nummer: str = "", buchungen: str = "") -> None:
        umgebung.abliefern(Beleg(
            quelle=self.name, konto=self.konto.name, art=art, schluessel=schluessel,
            dateiname=dateiname, inhalt=inhalt, jahr=datum.year if datum else heute().year,
            rechnungsdatum=datum, rechnungsnummer=nummer, buchungscode=buchungen[:200],
            unterordner=UNTERORDNER[art],
        ))

    @staticmethod
    def _abweichung(erg: Ergebnis, text: str) -> None:
        erg.status = "unvollstaendig"
        if text not in erg.abweichungen:  # z. B. derselbe fremde Host auf jeder Jahresseite
            erg.abweichungen.append(text)

    def belege_holen(self, umgebung: Umgebung) -> Ergebnis:
        erg = Ergebnis(self.name, self.konto.name)
        erg.erwartet = 0
        erg.vorhanden = 0
        zaehler = {"auszahlungsuebersicht": 0, "auszahlung": 0}
        try:
            einstellung = unterkunft_einstellung(self.konto.optionen.get("unterkunft"))
        except UnterkunftUngueltig as fehler:
            erg.status = "fehler"
            erg.fehler = str(fehler)
            return erg
        with browser.profil_oeffnen(self.profil, sichtbar=umgebung.sichtbar) as kontext:
            seite = browser.neue_seite(kontext)
            try:
                if not self._startseite(seite):
                    erg.status = "abgelaufen"
                    return erg
                ses = parameter(seite.url)["ses"]
                hotels = unterkuenfte(seite.url, seite.evaluate(_HOTEL_LINKS_JS), einstellung)
                if not hotels:
                    self._abweichung(erg, "Keine Unterkunft gefunden.")
                    return erg
                mehrere = len(hotels) > 1
                umgebung.melden(f"{len(hotels)} Unterkunft/Unterkünfte." if mehrere else "Angemeldet.")
                ohne_zugriff = [h for h in hotels
                                if not self._unterkunft_holen(seite, h, ses, mehrere, umgebung, erg, zaehler)]
                if ohne_zugriff and len(ohne_zugriff) == len(hotels):
                    raise KeinFinanzZugriff()  # keine einzige Unterkunft: Meldung für das ganze Konto
                for hotel in ohne_zugriff:
                    self._abweichung(erg, KEIN_ZUGRIFF_UNTERKUNFT.format(hotel=hotel))
            except BestaetigungNoetig:
                erg.status = "abgelaufen"
                erg.hinweise.append(BESTAETIGEN_HINWEIS)
                umgebung.melden(BESTAETIGEN_HINWEIS)
            except SitzungAbgelaufen:
                erg.status = "abgelaufen"
                umgebung.melden("Die Anmeldung ist abgelaufen. Der nächste Lauf holt den Rest nach.")
            except KeinFinanzZugriff:
                erg.status = "fehler"
                erg.fehler = KEIN_ZUGRIFF_TEXT
                umgebung.melden(KEIN_ZUGRIFF_TEXT)
        teile = []
        if zaehler["auszahlungsuebersicht"]:
            teile.append(f"{zaehler['auszahlungsuebersicht']} Datei(en) Auszahlungsübersicht")
        if zaehler["auszahlung"]:
            teile.append(f"{zaehler['auszahlung']} Datei(en) zu Auszahlungen")
        if teile:
            erg.hinweise.append(" und ".join(teile) + " neu abgelegt (nur im Belegordner, werden nicht verschickt).")
        return erg

    def _unterkunft_holen(self, seite, hotel, ses, mehrere, umgebung: Umgebung, erg: Ergebnis,
                          zaehler: dict[str, int]) -> bool:
        """Die drei Abschnitte einer Unterkunft. Scheitert einer, laufen die anderen (und weitere
        Unterkünfte) weiter; das Konto ist dann „unvollständig“. Nur ein Ablauf der Anmeldung bricht ab.
        False, wenn dieses Konto für die Unterkunft kein Finanzrecht hat — das entscheidet nur der erste
        Abschnitt (Rechnungen). Fehlt der Zugriff erst bei einem späteren, ist nur dieser Abschnitt betroffen."""
        vorsilbe = f"Unterkunft {hotel}: " if mehrere else ""
        abschnitte = (
            ("Rechnungen", "rechnung", self._rechnungen),
            ("Auszahlungsübersichten", "auszahlungsuebersicht", self._uebersichten),
            ("Auszahlungen", "auszahlung", self._auszahlungen),
        )
        for name, art, holen in abschnitte:
            try:
                neu = holen(seite, hotel, ses, mehrere, umgebung, erg, vorsilbe)
            except SitzungAbgelaufen:
                raise
            except KeinFinanzZugriff:
                if art == abschnitte[0][1]:
                    return False
                self._abweichung(erg, f"{vorsilbe}{name}: kein Zugriff (Booking.com verweigert diese Seite).")
                continue
            except DateiFehler as fehler:
                self._abweichung(erg, f"{vorsilbe}{name}: abgebrochen ({fehler}).")
                continue
            except Exception as fehler:  # noqa: BLE001 - nur der Typ, nie der Text (könnte Adressen enthalten)
                self._abweichung(erg, f"{vorsilbe}{name}: abgebrochen ({type(fehler).__name__}).")
                continue
            if art in zaehler:
                zaehler[art] += neu or 0
        return True

    def _seite_oeffnen(self, seite, pfad: str, hotel: str, ses: str, **extra: str) -> None:
        """Öffnet eine Extranet-Seite. Zeigt sie statt des Extranets eine Anmelde- oder
        Bestätigungsseite, bricht der Abruf als „abgelaufen“ ab (nicht als „0 Belege“)."""
        antwort = _aufrufen(seite, seitenadresse(pfad, hotel, ses, **extra))
        self._letzter_status = getattr(antwort, "status", None)
        if ist_anmeldeseite(seite.url):
            raise SitzungAbgelaufen()
        try:
            seite.wait_for_selector(f'a[href*="hotel_id="], {FINANZ_MERKMALE}', timeout=INHALT_WARTEN_MS)
        except Exception:  # noqa: BLE001 - weder Unterkunft noch Finanzinhalt: unten entscheiden
            pass  # nosec B110
        self._noch_angemeldet(seite, status=self._letzter_status)

    def _noch_angemeldet(self, seite, status: int | None = None) -> None:
        """Nach einem Fehlschlag auf der Seite: Anmeldeseite → abgelaufen; Seite ohne Extranet-
        Inhalt (z. B. Zwei-Faktor-Abfrage mittendrin) → BestaetigungNoetig. Sonst nichts.
        ``status`` nur direkt nach dem Laden: Ein 403 ohne Menü heißt „kein Zugriff“, nicht
        „Bestätigung verlangt“."""
        if ist_anmeldeseite(seite.url):
            raise SitzungAbgelaufen()
        if self._angemeldet(seite):
            return
        try:
            finanzseite = ist_extranet(seite.url) and seite.locator(FINANZ_MERKMALE).count() > 0
        except Exception:  # noqa: BLE001
            finanzseite = False
        if finanzseite:
            return
        if status == 403 and ist_extranet(seite.url) and not self._eingabefeld(seite):
            if self._sperrseite(seite):  # z. B. „Access Denied“ des Netzwerkdienstes, kein Rechteproblem
                raise DateiFehler("Booking.com hat die Seite gesperrt (403)")
            raise KeinFinanzZugriff()
        raise BestaetigungNoetig()  # auch 403 mit Code- oder Passwortfeld: erneute Bestätigung

    @staticmethod
    def _sperrseite(seite) -> bool:
        """Sperrseite eines Netzwerkdienstes statt einer Booking.com-Seite (Text nur durchsucht)?"""
        try:
            return bool(RE_SPERRSEITE.search(seite.inner_text("body", timeout=5000)))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _eingabefeld(seite) -> bool:
        """Fragt die Seite nach einem Code oder Passwort (Zwei-Faktor, neue Anmeldung)? Im Zweifel ja —
        dann lieber „neu anmelden“ als „Recht Finance holen“."""
        try:
            return seite.locator(EINGABE_MERKMALE).count() > 0
        except Exception:  # noqa: BLE001
            return True

    def _finanzzugriff_pruefen(self, seite) -> None:
        """Nur aufgerufen, wenn Rechnungslinks und Jahresfilter fehlen: steckt fehlende
        Berechtigung dahinter? Der Seitentext wird nur durchsucht, nie gespeichert."""
        try:
            text = seite.inner_text("body", timeout=5000)
        except Exception:  # noqa: BLE001
            text = ""
        if ohne_finanz_zugriff(getattr(self, "_letzter_status", None), text):
            raise KeinFinanzZugriff()

    # Jahresfilter ----------------------------------------------------------

    def _jahresknopf(self, seite):
        return seite.locator("button").filter(has_text=re.compile(r"^\s*20\d{2}\s*$")).locator("visible=true").first

    def _jahre_im_filter(self, seite) -> list[int] | None:
        """Die Jahre im sichtbaren Filter „Nach Jahr filtern“ (öffnen, lesen, schließen).
        None, wenn kein Filter zu finden ist."""
        knopf = self._jahresknopf(seite)
        try:
            jetzt = int(knopf.inner_text(timeout=10000).strip())
        except Exception:  # noqa: BLE001
            return None
        try:
            knopf.click(timeout=10000)
            seite.wait_for_timeout(800)
            texte = seite.get_by_role("menuitem").all_inner_texts()
            seite.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            texte = []
        jahre = {int(t.strip()) for t in texte if re.fullmatch(r"\s*20\d{2}\s*", t)}
        return sorted(jahre | {jetzt}, reverse=True)

    def _jahr_waehlen(self, seite, jahr: int) -> bool:
        """Wählt das Jahr im Filter. False, wenn das Menü dieses Jahr (gerade) nicht anbietet —
        dann gibt es dort nichts (beim echten Lauf: 2024 bei den Auszahlungsübersichten)."""
        knopf = self._jahresknopf(seite)
        if knopf.inner_text(timeout=10000).strip() == str(jahr):
            return True
        knopf.click(timeout=10000)
        seite.wait_for_timeout(800)
        eintrag = seite.get_by_role("menuitem", name=str(jahr), exact=True)
        if eintrag.count() == 0:
            seite.keyboard.press("Escape")
            return False
        eintrag.first.click(timeout=10000)
        seite.wait_for_timeout(3000)
        return True

    def _jahre(self, seite, umgebung: Umgebung, erg: Ergebnis, wo: str, vorlauf: int = 0) -> list[int]:
        """Welche Jahre abgefragt werden. Ohne Filter: das laufende Jahr und (so weit „Belege ab“
        es verlangt, sonst zwei weitere) die Jahre davor — und eine Meldung, dass es unvollständig
        sein kann."""
        verfuegbar = self._jahre_im_filter(seite)
        if verfuegbar is None:
            jetzt = heute().year
            bis = (umgebung.ab.year - vorlauf) if umgebung.ab else jetzt - 2
            verfuegbar = list(range(jetzt, min(bis, jetzt) - 1, -1))
            self._abweichung(erg, f"{wo}: Jahresfilter nicht gefunden — abgefragt wurden nur "
                                  f"{', '.join(map(str, verfuegbar))}; ältere fehlen womöglich.")
        return jahre_noetig(verfuegbar, umgebung.ab, vorlauf)

    # Rechnungen (Belege) -----------------------------------------------------

    def _rechnungen(self, seite, hotel, ses, mehrere, umgebung: Umgebung, erg: Ergebnis, vorsilbe: str) -> int:
        self._seite_oeffnen(seite, RECHNUNGEN_SEITE, hotel, ses)
        if not self._links(seite, [RECHNUNG_LINK]) and self._jahre_im_filter(seite) is None:
            self._finanzzugriff_pruefen(seite)
        rechnungen: dict[str, Rechnung] = {}
        for jahr in self._jahre(seite, umgebung, erg, f"{vorsilbe}Rechnungen", vorlauf=1):
            self._seite_oeffnen(seite, RECHNUNGEN_SEITE, hotel, ses, year=str(jahr))
            for r in rechnungen_aus_links(self._links(seite, [RECHNUNG_LINK], erg=erg, vorsilbe=vorsilbe)):
                rechnungen.setdefault(r.nummer, r)
        liste = [r for r in rechnungen.values() if not umgebung.zu_alt(r.datum)]
        erg.uebersprungen += len(rechnungen) - len(liste)
        erg.erwartet += len(liste)
        umgebung.melden(f"{vorsilbe}{len(liste)} Rechnung(en) in der Liste.")
        for r in sorted(liste, key=lambda r: (r.datum or date.min, r.nummer)):
            schluessel = f"rechnung:{hotel}:{r.nummer}"
            if umgebung.bekannt(schluessel):
                erg.schon_da += 1
                erg.vorhanden += 1
                continue
            browser.pause()
            try:
                inhalt = self._laden(seite, r.url, "pdf")
            except DateiFehler as fehler:
                self._abweichung(erg, f"{vorsilbe}Rechnung {r.nummer}: nicht gespeichert ({fehler}).")
                continue
            self._abliefern(umgebung, "rechnung", schluessel, rechnung_dateiname(r, hotel, mehrere), inhalt,
                            r.datum, nummer=r.nummer)
            erg.neu += 1
            erg.vorhanden += 1
        return 0  # Rechnungen zählen in erg.neu

    # Auszahlungsübersichten (je Monat) --------------------------------------

    def _uebersichten(self, seite, hotel, ses, mehrere, umgebung: Umgebung, erg: Ergebnis, vorsilbe: str) -> int:
        neu = 0
        for u in self._uebersichten_lesen(seite, hotel, ses, umgebung, erg, vorsilbe):
            neu += self._uebersicht_ablegen(seite, hotel, mehrere, u, umgebung, erg, vorsilbe)
        return neu

    def _uebersichten_lesen(self, seite, hotel, ses, umgebung: Umgebung, erg: Ergebnis,
                            vorsilbe: str) -> list[Uebersicht]:
        """Die abgeschlossenen Monate im Zeitraum, aus dem Reiter „Zahlungen von Booking.com“."""
        self._seite_oeffnen(seite, RECHNUNGEN_SEITE, hotel, ses)
        try:
            # Im Extranet ein Reiter (role=tab); zur Sicherheit auch ein gleich beschrifteter Knopf.
            seite.get_by_role("tab", name=REITER_VON, exact=True).or_(
                seite.get_by_role("button", name=REITER_VON, exact=True)).first.click(timeout=20000)
        except Exception:  # noqa: BLE001
            self._noch_angemeldet(seite)
            self._abweichung(erg, f"{vorsilbe}Reiter „{REITER_VON}“ nicht gefunden.")
            return []
        self._links(seite, [UEBERSICHT_PDF])
        gefunden: dict[tuple[int, int], Uebersicht] = {}
        for jahr in self._jahre(seite, umgebung, erg, f"{vorsilbe}Auszahlungsübersichten"):
            try:
                if not self._jahr_waehlen(seite, jahr):
                    continue
            except Exception:  # noqa: BLE001
                self._abweichung(erg, f"{vorsilbe}Auszahlungsübersichten {jahr}: Jahr nicht wählbar.")
                continue
            for u in uebersichten_aus_links(self._links(seite, [UEBERSICHT_PDF, UEBERSICHT_CSV], erg=erg,
                                                        vorsilbe=vorsilbe)):
                if u.jahr == jahr:
                    gefunden.setdefault((u.jahr, u.monat), u)
        jetzt = heute()
        liste = []
        for (jahr, monat), u in sorted(gefunden.items()):
            if (jahr, monat) >= (jetzt.year, jetzt.month):
                continue  # laufender Monat: erst nach Monatsende (dann vollständig)
            if umgebung.zu_alt(monatsende(jahr, monat)):
                erg.uebersprungen += 1
                continue
            liste.append(u)
        return liste

    def _uebersicht_ablegen(self, seite, hotel, mehrere, u: Uebersicht, umgebung: Umgebung, erg: Ergebnis,
                            vorsilbe: str) -> int:
        neu = 0
        for endung, adresse in (("pdf", u.pdf), ("csv", u.csv)):
            schluessel = f"auszahlungsuebersicht:{hotel}:{u.jahr:04d}-{u.monat:02d}:{endung}"
            if not adresse or umgebung.bekannt(schluessel):
                continue
            browser.pause(1, 3)
            try:
                inhalt = self._laden(seite, adresse, endung)
            except DateiFehler as fehler:
                self._abweichung(erg, f"{vorsilbe}Auszahlungsübersicht {u.monat:02d}/{u.jahr} "
                                      f"({endung.upper()}): nicht gespeichert ({fehler}).")
                continue
            self._abliefern(umgebung, "auszahlungsuebersicht", schluessel,
                            uebersicht_dateiname(u, endung, hotel, mehrere), inhalt, date(u.jahr, u.monat, 1))
            neu += 1
        return neu

    # Auszahlungen (je Auszahlung) --------------------------------------------

    def _auszahlungen(self, seite, hotel, ses, mehrere, umgebung: Umgebung, erg: Ergebnis, vorsilbe: str) -> int:
        neu = 0
        for a in self._auszahlungen_lesen(seite, hotel, ses, umgebung, erg, vorsilbe):
            neu += self._auszahlung_ablegen(seite, hotel, mehrere, a, umgebung, erg, vorsilbe)
        return neu

    def _auszahlungen_lesen(self, seite, hotel, ses, umgebung: Umgebung, erg: Ergebnis,
                            vorsilbe: str) -> list[Auszahlung]:
        """Die Auszahlungen im Zeitraum: „Dieses Jahr“ und, wenn nötig, „Letztes Jahr“."""
        self._seite_oeffnen(seite, AUSZAHLUNGEN_SEITE, hotel, ses)
        jetzt = heute()
        zeitraeume = ["THIS_YEAR"]
        if umgebung.ab is None or umgebung.ab.year < jetzt.year:
            zeitraeume.append("LAST_YEAR")  # älter bietet die Seite nur als „Individueller Zeitraum“
        gefunden: dict[str, Auszahlung] = {}
        for zeitraum in zeitraeume:
            try:
                seite.wait_for_selector(ZEITRAUM_FELD, timeout=20000)
                seite.select_option(ZEITRAUM_FELD, zeitraum)
                seite.wait_for_timeout(3000)
            except Exception:  # noqa: BLE001
                self._noch_angemeldet(seite)
                self._abweichung(erg, f"{vorsilbe}Auszahlungen: Zeitraum nicht wählbar.")
                continue
            for a in auszahlungen_aus_links(self._links(seite, [AUSZAHLUNG_PDF, AUSZAHLUNG_CSV], erg=erg,
                                                        vorsilbe=vorsilbe)):
                gefunden.setdefault(a.kennung, a)
        liste = []
        for a in sorted(gefunden.values(), key=lambda a: (a.datum or date.min, a.kennung)):
            if a.datum is not None and a.datum > jetzt:
                continue  # noch nicht ausgezahlt
            if umgebung.zu_alt(a.datum):
                erg.uebersprungen += 1
                continue
            liste.append(a)
        return liste

    def _auszahlung_ablegen(self, seite, hotel, mehrere, a: Auszahlung, umgebung: Umgebung, erg: Ergebnis,
                            vorsilbe: str) -> int:
        """Erst die CSV (für den Dateinamen), dann das PDF; beide unter demselben Namen."""
        schluessel = {e: f"auszahlung:{hotel}:{a.kennung}:{e}" for e in ("pdf", "csv")}
        if all(umgebung.bekannt(s) for s in schluessel.values()):
            return 0
        bezeichnung = f"{vorsilbe}Auszahlung vom {a.datum:%d.%m.%Y}" if a.datum else f"{vorsilbe}Auszahlung"
        browser.pause(1, 3)
        try:
            csv_inhalt = self._laden(seite, a.csv, "csv") if a.csv else b""
            daten = auszahlung_lesen(csv_inhalt) if csv_inhalt else AuszahlungsDaten()
            pdf_inhalt = self._laden(seite, a.pdf, "pdf") if a.pdf else b""
        except DateiFehler as fehler:
            self._abweichung(erg, f"{bezeichnung}: nicht gespeichert ({fehler}).")
            return 0
        datum = daten.datum or a.datum
        neu = 0
        for endung, inhalt in (("csv", csv_inhalt), ("pdf", pdf_inhalt)):
            if not inhalt or umgebung.bekannt(schluessel[endung]):
                continue
            self._abliefern(umgebung, "auszahlung", schluessel[endung],
                            auszahlung_dateiname(datum, daten, endung, hotel, mehrere), inhalt, datum,
                            nummer=daten.nummer, buchungen=" ".join(daten.buchungsnummern))
            neu += 1
        return neu
