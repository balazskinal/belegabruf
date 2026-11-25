# ADR-004: Abliefern — zuerst per Mail, danach per API

- **Datum:** 25.11.2026
- **Status:** ✅ gilt · Mail-Weg = Version 1.3.0 · sevDesk-API = Version 1.4.0

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
     Einschalten eines Empfängers gilt alles schon Geholte als verschickt. Bleibt die Antwort des Servers
     nach dem Senden aus, gilt die Mail als „unklar“ und wird nicht noch einmal geschickt.
2. **Version 1.4: Ziel „sevdesk“ über die API.** Nur `uploadTempFile` und `saveVoucher` (dazu `GET
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
