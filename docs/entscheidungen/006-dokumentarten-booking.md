# ADR-006: Mehrere Dokumentarten je Anbieter — verschickt werden nur Rechnungen

- **Datum:** 26.11.2026
- **Status:** ✅ gilt ab 2.1.0 (Quelle Booking.com, #13)

## Kontext

Bis 2.0 holte jeder Anbieter genau eine Art von Beleg: Rechnungen (bei Airbnb dazu Monatsübersichten
„zur Kontrolle“). Booking.com bietet im Extranet drei Arten von Dokumenten:

1. **Kommissionsrechnungen** („Zahlungen an Booking.com“) — die eigentlichen Belege für die Buchhaltung.
2. **Auszahlungsübersichten** je Monat („Zahlungen von Booking.com“), PDF und CSV.
3. **Auszahlungen** je Auszahlung (PDF und CSV), mit den Buchungen, die darin stecken.

Balazs will alle drei im Belegordner haben, getrennt nach Art, aber nur die Rechnungen an die
Buchhaltung schicken.

## Entscheidung

1. **Dokumentart = `Beleg.art`.** Neben `rechnung` und `kontrolle` gibt es Arten, die nur abgelegt werden:
   `auszahlungsuebersicht` und `auszahlung`. Lieferziele (Mail, später API) bekommen weiterhin **nur
   `rechnung`** — `Protokoll.offen_fuer` filtert schon darauf. Die Zusammenfassung nennt die übrigen
   Dokumente getrennt („nur im Belegordner, werden nicht verschickt“).
2. **Jede Art im Protokoll.** Auch abgelegte Dokumente stehen mit eigenem Schlüssel im Protokoll
   (`auszahlung:<Unterkunft>:<ID>:pdf|csv` usw.), damit sie nicht doppelt geholt werden. „Fehlende
   Dateien neu holen“ und der erste Lauf eines Kontos zählen weiter nur Rechnungen.
3. **Eigener Ordner je Art**: `Beleg.unterordner` legt unter den Anbieterordner einen Ordner, darunter
   gilt die Ablage nach Jahr bzw. Monat wie sonst: `booking/Rechnungen (an Booking.com)/2026/…`. Ohne
   `unterordner` bleibt alles wie bisher (`airbnb/2026/…`).
4. **„Belege ab“ gilt für alle Arten** — für Rechnungen nach Rechnungsdatum, für Übersichten nach
   Monatsende, für Auszahlungen nach Auszahlungsdatum.
5. **Gastnamen nie** in Dateinamen, Protokoll oder Ausgaben, auch nicht bei Auszahlungen. Balazs hatte den
   Namen im Dateinamen als „eventuell“ genannt; die Regel gilt aber seit 1.0 für alle Anbieter (Airbnb,
   Xentra), und Dateinamen wandern weiter — an Steuerberatung, Buchhaltung, in Mails. Die Buchungsnummer
   reicht zur Zuordnung; der Name steht in der unverändert abgelegten CSV-Datei von Booking.com.
6. **Unterkünfte:** Geholt wird die Unterkunft, auf der das Extranet nach der Anmeldung landet. Mehrere
   über `unterkunft = "<ID>, <ID>"` im Konto, jede für sich (eigener Protokollschlüssel, bei mehr als einer
   die ID im Dateinamen). Links der Startseite zählen bewusst nicht: Beim echten Lauf stand dort eine
   zweite, fremde ID ohne Rechnungen. Nur eine Gruppen-Startseite ohne `hotel_id` nimmt ihre Links.

7. **Nur von admin.booking.com.** Dateien werden nur von `https://admin.booking.com` geladen — Links mit
   anderem Host oder ohne https werden verworfen, und nach einer Weiterleitung wird die Zieladresse erneut
   geprüft. Sonst könnte ein untergeschobener Link als „Rechnung“ abgelegt und verschickt werden
   (Prüfung zu PR #19, M1).

## Folgen

- Weitere Anbieter mit mehreren Dokumentarten (z. B. Auszahlungsberichte bei Airbnb) können dasselbe
  Muster nutzen.
- Laufende Monate bei den Auszahlungsübersichten werden erst nach Monatsende geholt (sonst läge eine
  unvollständige Fassung im Ordner, die wegen des Protokolls nie ersetzt würde).
- Auszahlungen älter als das Vorjahr holt das Programm nicht (Booking.com zeigt sie nur über einen
  „Individuellen Zeitraum“); Rechnungen schon. Das reicht für den laufenden Abgleich.
