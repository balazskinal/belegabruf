# ADR-004: Abliefern — zuerst per Mail, danach per API

- **Datum:** 25.11.2026
- **Status:** ✅ gilt · Mail-Weg = Version 1.3.0 · API-Ziele (sevDesk, Lexware Office) **geparkt**
  seit 26.11.2026 (Nachtrag unten)

## Kontext

Neben dem lokalen Ordner sollen die Belege direkt in der Buchhaltung landen — zuerst in sevDesk, später
eventuell in Lexware Office. Ursprünglich war dafür nur der API-Weg vorgesehen. Die Prüfung der sevDesk-
API (25.11.2026, an echten Belegen) hat gezeigt:

- `POST /Voucher/Factory/uploadTempFile` + `POST /Voucher/Factory/saveVoucher` legen über den
  API-Schlüssel einen **Entwurf** an (Status 50), mit PDF, Datum, Rechnungsnummer und Lieferant als Text
  — **auch ohne Betrag, Positionen und Konto**.
- Die **Belegerkennung** (Auslesen von Betrag, Steuer, Absender), die die sevDesk-Oberfläche nutzt, läuft
  über einen **undokumentierten** Aufruf, der den API-Schlüssel **ablehnt** (401) und nur mit der
  Browser-Anmeldung geht.
- Per **Mail** an die Belegadresse liest sevDesk den Beleg dagegen selbst aus — ebenso Lexware Office und
  andere Programme mit Belegadresse.

## Entscheidung

1. **Version 1.3: Ziel „mail“.** Jede neue Rechnung geht als eigene Mail mit PDF-Anhang an eine oder
   mehrere Adressen. Damit ist jedes System mit Belegadresse auf einmal angebunden (Buchhaltungsprogramm,
   Steuerberatung).
   - **Jeder richtet sein eigenes Postfach ein** (Abfrage in der Ersteinrichtung). Das Programm bringt
     keinen Versanddienst mit.
   - Nur Senden, kein Lesen von Postfächern. Verschlüsselung (SSL oder STARTTLS) ist Pflicht.
   - Das Passwort liegt im Passwortspeicher (ADR-003). „Einrichten“ prüft die Anmeldung, ohne eine Mail zu
     schicken.
   - Eine Mail je Rechnung und Empfänger, nie doppelt (Protokoll, ADR-002). Beim **allerersten**
     Einschalten eines Empfängers gilt alles schon Geholte als verschickt (seit 2.0.0 wählbar, siehe
     Nachtrag unten und ADR-005 Punkt 11). Bleibt die Antwort des Servers
     nach dem Senden aus, gilt die Mail als „unklar“ und wird nicht noch einmal geschickt.
2. **Version 2.1: Ziel „sevdesk“ über die API.** Nur `uploadTempFile` und `saveVoucher` (dazu `GET
   /SevClient` beim Einrichten). Eingetragen wird nur, was das Programm ohnehin weiß (Datum,
   Rechnungsnummer, Lieferant); Betrag und Konto ergänzt man in sevDesk. Die **Steuerregel** wählt jeder
   selbst in der Einrichtung — es gibt keine Vorgabe.
3. **Lexware Office** über seine API (`POST /v1/files`, liest selbst aus), sobald jemand mit echtem Konto
   testen kann.

## Verworfen

- **Erkennung über die Browser-Anmeldung bei sevDesk** (undokumentierter Aufruf): hängt an der
  Oberfläche und bricht ohne Ankündigung.
- **PDF im Programm selbst auslesen**, um den sevDesk-Entwurf zu füllen: zu großer Aufwand für den Nutzen.

## Folgen

- Wer sevDesk nutzt, hat mit dem Mail-Weg die bessere Erkennung; der API-Weg bleibt für alle, die keine
  Mail verschicken wollen.

## Nachtrag 25.11.2026 (Version 2.0.0): Erster Versand wählbar

Neue Einstellung `[mail] erstversand` (Balazs):

- `"nicht"` (Vorgabe, auch für alte Dateien ohne den Schlüssel): Belege, die es beim allerersten
  Einschalten eines Empfängers schon gibt, gelten als verschickt (`mail:<adresse>:schon`), wie bisher.
  **Neu** gilt das auch für den **ersten Lauf eines neuen Kontos**: Alles, was er holt, wird nur abgelegt.
- `"auch"`: Nichts wird vorab markiert. Der schon geholte Bestand geht beim Einschalten bzw. an eine neue
  Adresse einmal raus, beim ersten Lauf eines neuen Kontos alles aus dem Zeitraum „Belege ab“.

Der erste Lauf steht als `einstellung:erstlauf` (offen/fertig) im Protokoll des Kontos. Er endet, sobald
ein Lauf die Rechnungsliste gelesen hat (Status ok oder unvollständig) — nicht erst bei einem fehlerfreien
Lauf, sonst würde ein Konto mit einer dauerhaft kaputten Rechnung nie mailen. Bisherige Protokolle mit
Rechnungen gelten nicht als neu. Geprüft wird die Einstellung zentral in `einstellungen.pruefen`.

## Nachtrag 26.11.2026: API-Ziele geparkt

Die Ziele sevDesk und Lexware Office über die API werden vorerst **nicht gebaut**.
- Jede Nutzerin und jeder Nutzer müsste dafür einen API-Schlüssel mit Schreibrechten auf die eigene
  Buchhaltung hinterlegen. Das wollen die wenigsten, und es ist ein Risiko, das der Nutzen nicht aufwiegt.
- Der Mailweg (1.3.0) erreicht dieselben Programme schon heute über ihre Beleg-Mailadresse und hat sich
  bewährt.

Der fertige sevDesk-Stand bleibt als geschlossener PR #3 mit Label „geparkt“ und Branch `version-2`
erhalten, ebenso die Issues #12 und #14. Wieder aufnehmen, wenn jemand den API-Weg ausdrücklich braucht.
