"""Baustein Airbnb: Rechnungen über die Servicegebühren für Gastgeber.

Wo sie liegen: Konto → Steuern → Steuerdokumente → Rechnungen („Lade mehrere
Steuerrechnungen …“). Airbnb bietet dort nur die letzten 12 Monate an, je Monat
ein Sammel-PDF. Jede Zeile darin ist eine Rechnung und verlinkt auf die
Einzelrechnung (www.airbnb.de/invoice/<Kennung>).

Ablauf:
1. Monats-PDFs holen                     → airbnb/kontrolle/<JJJJ-MM>_<konto>.pdf
2. Zeilen und Links aus den Monats-PDFs lesen
3. Jede noch nicht vorhandene Einzelrechnung im angemeldeten Browser öffnen,
   Inhalt prüfen (nie eine Anmelde-, 404- oder leere Seite!), als PDF abliefern
                                         → airbnb/<Jahr>/<Datum>_<Buchungscode>_<Rechnungsnummer>.pdf
4. Anzahl Einzelrechnungen gegen die Zeilen der Monats-PDFs prüfen
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import pymupdf

from belegabruf import browser, pfade, pruefung
from belegabruf.quellen.basis import Beleg, Ergebnis, Quelle, SitzungAbgelaufen, Umgebung

ADRESSE = "https://www.airbnb.de"
DOKUMENTE_PFAD = "/account-settings/taxes/tax-documents/"

MONATE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

RE_RECHNUNGSNUMMER = re.compile(r"\b([A-Z]{2,6}-\d{4,}-[A-Z]{2}-\d{3,})\b")
RE_BUCHUNGSCODE = re.compile(r"\b(HM[A-Z0-9]{8})\b")
RE_DATUM = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
RE_INVOICE_LINK = re.compile(r"/invoice/([A-Za-z0-9_-]+)")


def _ist_anmeldeseite(url: str) -> bool:
    url = url.lower()
    return any(t in url for t in ("/login", "signup_login", "/authenticate", "/account-verification"))


def _kurz(fehler: Exception) -> str:
    return f"{type(fehler).__name__}: {str(fehler).splitlines()[0][:120]}" if str(fehler) else type(fehler).__name__


def _aufrufen(seite, url: str):
    """Seite laden. Airbnb ist manchmal langsam (über 15 Sekunden): großzügig warten,
    bei Zeitüberschreitung ein zweites Mal versuchen."""
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


def monat_aus_text(text: str) -> tuple[int, int] | None:
    """'Oktober 2026' → (2026, 10)."""
    teile = text.strip().lower().split()
    if len(teile) == 2 and teile[0] in MONATE and teile[1].isdigit():
        return int(teile[1]), MONATE[teile[0]]
    return None


@dataclass
class Zeile:
    """Eine Zeile im Monats-PDF = eine Einzelrechnung."""

    kennung: str  # aus dem Link /invoice/<kennung>
    url: str
    rechnungsnummer: str = ""
    buchungscode: str = ""
    datum: str = ""
    dokumentart: str = ""  # "Rechnung" oder "Gutschrift" (Spalte DOKUMENTART)


@dataclass
class Monatsuebersicht:
    zeilen: list[Zeile] = field(default_factory=list)
    anzahl_zeilen: int = 0  # gezählt am Text (Buchungscodes), unabhängig von den Links
    ohne_link: list[str] = field(default_factory=list)  # Buchungscodes von Zeilen ohne Link


def monats_pdf_lesen(inhalt: bytes) -> Monatsuebersicht:
    """Liest Zeilen und Links aus einem Monats-PDF.

    Jeder Link liegt über einer Tabellenzeile. Zu jedem Link werden die Wörter
    in derselben Höhe gesammelt (Rechnungsnummer, Datum, Buchungscode).
    """
    ergebnis = Monatsuebersicht()
    gesehen: dict[str, Zeile] = {}
    with pymupdf.open(stream=inhalt, filetype="pdf") as dok:
        for seite in dok:
            text = seite.get_text()
            # Jede Zeile hat genau einen Buchungscode — so wird unabhängig von den Links gezählt.
            codes_im_text = RE_BUCHUNGSCODE.findall(text)
            ergebnis.anzahl_zeilen += len(codes_im_text)
            woerter = seite.get_text("words")
            for link in seite.get_links():
                uri = link.get("uri") or ""
                treffer = RE_INVOICE_LINK.search(uri)
                if not treffer:
                    continue
                kennung = treffer.group(1)
                rechteck = link["from"]
                oben, unten = rechteck.y0 - 2, rechteck.y1 + 14  # etwas Luft für Umbrüche
                in_zeile = sorted(
                    (w for w in woerter if w[1] < unten and w[3] > oben),
                    key=lambda w: (round(w[1]), w[0]),
                )
                zeile = gesehen.get(kennung) or Zeile(kennung=kennung, url=uri)
                spalte_links = sorted(
                    (w for w in in_zeile if w[0] < rechteck.x1 + 2 and w[2] > rechteck.x0 - 2),
                    key=lambda w: (w[1], w[0]),
                )
                nummer_text = "".join(w[4] for w in spalte_links)
                if not zeile.rechnungsnummer:
                    m = RE_RECHNUNGSNUMMER.search(nummer_text)
                    zeile.rechnungsnummer = m.group(1) if m else ""
                zeilentext = " ".join(w[4] for w in in_zeile)
                if not zeile.buchungscode:
                    m = RE_BUCHUNGSCODE.search(zeilentext)
                    zeile.buchungscode = m.group(1) if m else ""
                if not zeile.datum:
                    m = RE_DATUM.search(zeilentext)
                    zeile.datum = m.group(1) if m else ""
                if not zeile.dokumentart:
                    m = re.search(r"\b(Gutschrift|Rechnung|Credit note|Invoice)\b", zeilentext)
                    zeile.dokumentart = m.group(1) if m else ""
                if kennung not in gesehen:
                    gesehen[kennung] = zeile
                    ergebnis.zeilen.append(zeile)
            # Ältere Rechnungen (anderes Nummernformat) haben im PDF keinen Link.
            verlinkt = {z.buchungscode for z in gesehen.values()}
            ergebnis.ohne_link += [c for c in codes_im_text if c not in verlinkt]
    return ergebnis


@dataclass
class Rechnungsdaten:
    rechnungsnummer: str
    datum: str
    buchungscode: str


def rechnungsseite_lesen(text: str) -> Rechnungsdaten:
    """Liest Rechnungsnummer, Ausstellungsdatum und Buchungscode aus der Einzelrechnung."""
    sauber = re.sub(r"-\s+", "-", " ".join(text.split()))
    nummer = RE_RECHNUNGSNUMMER.search(sauber)
    datum = re.search(r"Ausstellungsdatum[^0-9]{0,40}(20\d{2}-\d{2}-\d{2})", sauber) or RE_DATUM.search(sauber)
    code = RE_BUCHUNGSCODE.search(sauber)
    return Rechnungsdaten(
        rechnungsnummer=nummer.group(1) if nummer else "",
        datum=datum.group(1) if datum else "",
        buchungscode=code.group(1) if code else "",
    )


def dateiname(datum: str, buchungscode: str, rechnungsnummer: str, gutschrift: bool = False) -> str:
    """<Rechnungsdatum>_<Buchungscode>_<Rechnungsnummer>.pdf — Gutschriften tragen dieselbe
    Nummer wie ihre Rechnung und bekommen deshalb den Zusatz _Gutschrift."""
    teile = [datum or "ohne-datum", buchungscode or "ohne-buchungscode", rechnungsnummer or "ohne-nummer"]
    if gutschrift:
        teile.append("Gutschrift")
    return "_".join(re.sub(r"[^A-Za-z0-9-]", "", t) for t in teile) + ".pdf"


class Airbnb(Quelle):
    name = "airbnb"
    anzeigename = "Airbnb"

    def _adresse(self) -> str:
        return str(self.konto.optionen.get("adresse") or ADRESSE).rstrip("/")

    # 1. Sitzung prüfen ------------------------------------------------------
    def sitzung_pruefen(self) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=False) as kontext:
            seite = browser.neue_seite(kontext)
            seite.goto(self._adresse() + DOKUMENTE_PFAD, wait_until="domcontentloaded")
            seite.wait_for_timeout(2500)
            return self._sieht_angemeldet_aus(seite)

    def _sieht_angemeldet_aus(self, seite) -> bool:
        return not _ist_anmeldeseite(seite.url) and "/account-settings" in seite.url

    # 2. Anmelden lassen -----------------------------------------------------
    def anmelden_lassen(self, melden: Callable[[str], None]) -> bool:
        with browser.profil_oeffnen(self.profil, sichtbar=True) as kontext:
            seite = browser.neue_seite(kontext)
            seite.goto(
                f"{self._adresse()}/login?redirect_url=%2Faccount-settings%2Ftaxes%2Ftax-documents%2F",
                wait_until="domcontentloaded",
            )
            browser.auf_mensch_warten(kontext, seite, self._sieht_angemeldet_aus, melden)
        # Unabhängig davon, was im Fenster passiert ist: unsichtbar nachprüfen.
        return self.sitzung_pruefen()

    # 3. Belege holen --------------------------------------------------------
    def _dialog_oeffnen(self, seite):
        # Nicht auf "networkidle" warten: Airbnb hält im Hintergrund Verbindungen offen.
        _aufrufen(seite, self._adresse() + DOKUMENTE_PFAD)
        knopf = seite.locator("button", has_text="Lade mehrere Steuerrechnungen").first
        try:
            knopf.wait_for(timeout=60000)
        except Exception:  # noqa: BLE001
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen() from None
            raise
        knopf.click()
        dialog = seite.locator("[role=dialog]")
        dialog.locator("select").wait_for(timeout=20000)
        return dialog

    def _monate(self, seite) -> list[tuple[str, str]]:
        dialog = self._dialog_oeffnen(seite)
        optionen = dialog.locator("select").evaluate(
            "e => [...e.options].filter(o => o.value).map(o => [o.value, o.textContent.trim()])"
        )
        return [(wert, text) for wert, text in optionen]

    def _monats_pdf_laden(self, seite, beschriftung: str) -> bytes | None:
        # Die Werte der Auswahl ändern sich bei jedem Öffnen; die Beschriftung nicht.
        dialog = self._dialog_oeffnen(seite)
        dialog.locator("select").select_option(label=beschriftung)
        pdf = dialog.locator("input[value=PDF]")
        for _ in range(3):
            if pdf.is_checked():
                break
            try:
                dialog.get_by_text("PDF-Datei").first.click(timeout=5000)
            except Exception:  # noqa: BLE001 - dann direkt das Auswahlfeld anklicken
                pdf.evaluate("e => e.click()")
            seite.wait_for_timeout(500)
        if not pdf.is_checked():
            raise RuntimeError("PDF-Auswahl im Dialog nicht möglich")
        try:
            with seite.expect_download(timeout=90000) as warten:
                dialog.locator("button", has_text="Herunterladen").click()
        except Exception:  # noqa: BLE001 - kein Download (z. B. Monat ohne Rechnungen)
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen() from None
            return None
        pfad = warten.value.path()
        return pfad.read_bytes() if pfad else None

    def belege_holen(self, umgebung: Umgebung) -> Ergebnis:
        erg = Ergebnis(self.name, self.konto.name)
        melden = umgebung.melden
        heute = date.today()
        vormonat = (heute.year, heute.month - 1) if heute.month > 1 else (heute.year - 1, 12)
        alle_zeilen: list[Zeile] = []
        text_zeilen = 0

        with browser.profil_oeffnen(self.profil, sichtbar=umgebung.sichtbar) as kontext:
            seite = browser.neue_seite(kontext)
            try:
                monate = self._monate(seite)
            except SitzungAbgelaufen:
                erg.status = "abgelaufen"
                return erg
            melden(f"{len(monate)} Monate verfügbar.")

            # Schritt 1 + 2: Monatsübersichten
            for _, text in monate:
                jm = monat_aus_text(text)
                if jm is None:
                    erg.hinweise.append(f"Monat '{text}' nicht erkannt, übersprungen.")
                    continue
                kuerzel = f"{jm[0]:04d}-{jm[1]:02d}"
                schluessel = f"monat:{kuerzel}"
                lokal = umgebung.vorhandene_datei(schluessel)
                abgeschlossen = jm < vormonat  # ältere Monate ändern sich nicht mehr
                if lokal is not None and abgeschlossen:
                    inhalt = lokal.read_bytes()
                else:
                    browser.pause()
                    try:
                        try:
                            inhalt = self._monats_pdf_laden(seite, text)
                        except SitzungAbgelaufen:
                            raise
                        except Exception:  # noqa: BLE001 - einmal in Ruhe wiederholen
                            browser.pause(5, 10)
                            inhalt = self._monats_pdf_laden(seite, text)
                    except SitzungAbgelaufen:
                        erg.status = "abgelaufen"
                        break
                    except Exception as fehler:  # noqa: BLE001 - ein Monat darf scheitern
                        erg.abweichungen.append(f"{text}: Monatsübersicht nicht geladen ({_kurz(fehler)}).")
                        erg.status = "unvollstaendig"
                        continue
                    if inhalt is None or not pruefung.ist_pdf(inhalt):
                        erg.abweichungen.append(f"{text}: Monatsübersicht kam nicht an.")
                        erg.status = "unvollstaendig"
                        continue
                    neu = not umgebung.bekannt(schluessel)
                    umgebung.abliefern(Beleg(
                        quelle=self.name, konto=self.konto.name, art="kontrolle",
                        schluessel=schluessel, inhalt=inhalt, jahr=jm[0],
                        dateiname=f"{kuerzel}_{pfade.kurzname(self.konto.name)}.pdf",
                    ))
                    if neu:
                        erg.kontrolle_neu += 1
                try:
                    uebersicht = monats_pdf_lesen(inhalt)
                except Exception:  # noqa: BLE001
                    erg.abweichungen.append(f"{text}: Monatsübersicht nicht lesbar.")
                    continue
                for code in uebersicht.ohne_link:
                    erg.abweichungen.append(
                        f"{text}: Rechnung zur Buchung {code} hat in der Monatsübersicht keinen Link "
                        "(älteres Format) — Airbnb bietet dafür keine Einzelrechnung an. "
                        "Beleg ist dann die Monatsübersicht im Ordner kontrolle."
                    )
                rest = uebersicht.anzahl_zeilen - len(uebersicht.zeilen) - len(uebersicht.ohne_link)
                if rest:
                    erg.abweichungen.append(
                        f"{text}: {uebersicht.anzahl_zeilen} Rechnungszeilen, aber "
                        f"{len(uebersicht.zeilen)} Links in der Monatsübersicht."
                    )
                melden(f"{text}: {len(uebersicht.zeilen)} Rechnung(en)")
                text_zeilen += uebersicht.anzahl_zeilen
                alle_zeilen += uebersicht.zeilen

            # Schritt 3: Einzelrechnungen
            offen = [z for z in alle_zeilen if not umgebung.bekannt(f"rechnung:{z.kennung}")]
            erg.schon_da = len(alle_zeilen) - len(offen)
            weiter = erg.status != "abgelaufen"
            if offen and weiter:
                melden(f"{len(offen)} neue Einzelrechnung(en) werden geholt …")
            for nr, zeile in enumerate(offen if weiter else [], 1):
                browser.pause()
                try:
                    grund = self._einzelrechnung(seite, zeile, umgebung, erg)
                except SitzungAbgelaufen:
                    erg.status = "abgelaufen"
                    melden("Die Anmeldung ist abgelaufen. Der nächste Lauf holt den Rest nach.")
                    break
                except Exception as fehler:  # noqa: BLE001 - eine Rechnung darf scheitern
                    grund = _kurz(fehler)
                if grund:
                    erg.status = "unvollstaendig"
                    erg.abweichungen.append(
                        f"Rechnung {zeile.rechnungsnummer or zeile.kennung}: nicht gespeichert ({grund})."
                    )
                elif nr % 10 == 0:
                    melden(f"… {nr} von {len(offen)}")

        # Schritt 4: Kontrolle (Zeilen ohne Link gibt es nicht einzeln, die zählen nicht mit)
        erg.erwartet = len(alle_zeilen)
        if text_zeilen != erg.erwartet:
            erg.hinweise.append(
                f"Die Monatsübersichten haben {text_zeilen} Zeilen, davon {erg.erwartet} mit Einzelrechnung."
            )
        erg.vorhanden = sum(1 for z in alle_zeilen if umgebung.bekannt(f"rechnung:{z.kennung}"))
        return erg

    def _einzelrechnung(self, seite, zeile: Zeile, umgebung: Umgebung, erg: Ergebnis) -> str | None:
        """Holt eine Einzelrechnung. Gibt None bei Erfolg zurück, sonst den Grund."""
        url = zeile.url if zeile.url.startswith("http") else self._adresse() + zeile.url
        antwort = _aufrufen(seite, url)
        if _ist_anmeldeseite(seite.url):
            raise SitzungAbgelaufen()
        if antwort is not None and antwort.status >= 400:
            return f"Fehlerseite {antwort.status}"
        try:
            seite.get_by_text("Rechnungsnummer").first.wait_for(timeout=20000)
            seite.wait_for_timeout(800)  # Schriften und Logo fertig laden lassen
        except Exception:  # noqa: BLE001 - die Prüfung unten sagt, was fehlt
            if _ist_anmeldeseite(seite.url):
                raise SitzungAbgelaufen() from None
        seitentext = seite.inner_text("body")
        pflicht = ["Rechnungsnummer", zeile.rechnungsnummer, zeile.buchungscode]
        grund = pruefung.seite_ist_beleg(seitentext, pflicht)
        if grund == "Anmeldeseite":
            raise SitzungAbgelaufen()
        if grund:
            return grund
        daten = rechnungsseite_lesen(seitentext)
        inhalt = seite.pdf(format="A4", print_background=True)
        # Auch das fertige PDF prüfen: Steht die Rechnungsnummer wirklich drin?
        nummer = daten.rechnungsnummer or zeile.rechnungsnummer
        grund = pruefung.seite_ist_beleg(pruefung.pdf_text(inhalt), [nummer])
        if grund:
            return f"PDF unbrauchbar: {grund}"
        datum = daten.datum or zeile.datum
        try:
            rechnungsdatum = date.fromisoformat(datum)
        except ValueError:
            rechnungsdatum = None
        beleg = Beleg(
            quelle=self.name,
            konto=self.konto.name,
            art="rechnung",
            schluessel=f"rechnung:{zeile.kennung}",
            dateiname=dateiname(
                datum, daten.buchungscode or zeile.buchungscode, nummer,
                gutschrift=zeile.dokumentart.lower() in {"gutschrift", "credit note"},
            ),
            inhalt=inhalt,
            jahr=rechnungsdatum.year if rechnungsdatum else date.today().year,
            rechnungsdatum=rechnungsdatum,
            rechnungsnummer=nummer,
            buchungscode=daten.buchungscode or zeile.buchungscode,
        )
        orte = umgebung.abliefern(beleg)
        erg.neu += 1
        erg.neue_dateien += orte
        return None
