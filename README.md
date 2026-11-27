# Belegabruf

[![Prüfung](https://github.com/balazskinal/belegabruf/actions/workflows/pruefung.yml/badge.svg?branch=main)](https://github.com/balazskinal/belegabruf/actions/workflows/pruefung.yml)

Holt Rechnungen, die es nur im eingeloggten Konto eines Anbieters gibt, per Doppelklick auf den
eigenen Rechner. Es kann:

- **Airbnb:** die Rechnungen über die Airbnb-Servicegebühren für Gastgeber, jede Buchung als eigenes PDF.
- **Skool:** die Rechnungen für bezahlte Mitgliedschaften in Skool-Communities (siehe [Skool](#skool)).
- **Xentra:** die Rechnungen für das Xentra-Abonnement und Provisionen (siehe [Xentra](#xentra)).
- **Booking.com:** die Kommissionsrechnungen aus dem Extranet, dazu Auszahlungsübersichten und
  Auszahlungen zum Abgleich (siehe [Booking.com](#bookingcom)).

**Seit Version 1.3** verschickt es neue Rechnungen auf Wunsch zusätzlich **per Mail** — z. B. an die
Belegadresse deines Buchhaltungsprogramms oder an deine Steuerberatung. Verschickt wird über **dein
eigenes Postfach**; einen Versanddienst bringt das Programm nicht mit.

**Das ist kein Dienst — jeder betreibt seine eigene Kopie.** Niemand außer dir sieht deine
Anmeldung oder deine Belege. Es gibt keinen Server, kein Konto bei uns, keinen Support-Vertrag.

| | |
|---|---|
| macOS | getestet |
| Windows | **ungetestet** — gleicher Ablauf, wir suchen noch jemanden, der es ausprobiert |

---

## Einrichten — mit einer Zeile (empfohlen)

Eine Zeile kopieren, einfügen, Enter. Sie lädt die neueste Version von GitHub, **prüft ihre
Prüfsumme**, legt sie in den **Programme-Ordner deines Benutzerkontos** (siehe unten) und startet sie. Dabei
erscheint **keine Sicherheitsmeldung** (anders als beim ZIP aus dem Browser, siehe unten). Keine
Administratorrechte nötig; du brauchst eine Internetverbindung.

**Mac**
1. Das Programm **Terminal** öffnen: <kbd>⌘</kbd> + <kbd>Leertaste</kbd>, „Terminal“ tippen, Enter.
2. Diese Zeile einfügen und Enter drücken:

   ```bash
   curl -fsSL https://github.com/balazskinal/belegabruf/releases/latest/download/installieren.sh | bash
   ```

**Windows**
1. **PowerShell** öffnen: Startmenü, „PowerShell“ tippen, „Windows PowerShell“ anklicken (nicht „Als
   Administrator“ — das ist nicht nötig).
2. Diese Zeile einfügen (Rechtsklick) und Enter drücken:

   ```powershell
   irm https://github.com/balazskinal/belegabruf/releases/latest/download/installieren.ps1 | iex
   ```

Danach öffnet sich das Fenster „Belegabruf“. Beim ersten Mal lädt es noch ein paar Minuten lang alles
Nötige (siehe [Erster Start](#erster-start-einmalig-ca-5-minuten), ab Schritt 4).

| | wo es liegt | später starten |
|---|---|---|
| Mac | `~/Applications/Belegabruf` — im Finder: Benutzerordner → **Programme** → Belegabruf | **Spotlight** (<kbd>⌘</kbd> + <kbd>Leertaste</kbd>) „Belegabruf“, oder im Finder „Belegabruf Mac“ doppelklicken |
| Windows | `%LOCALAPPDATA%\Programs\Belegabruf` | **Startmenü → „Belegabruf“** (legt die Zeile an), oder „Belegabruf Windows“ im Ordner |

Der Programmordner liegt nicht in „Dokumente“ und nicht in iCloud bzw. OneDrive.

**Hast du Belegabruf bisher aus dem ZIP gestartet** (Ordner `belegabruf-v…`), kannst du den alten Ordner
löschen; ab jetzt startest du wie oben. Einstellungen und Anmeldungen bleiben, sie liegen im Datenordner.

**Update:** dieselbe Zeile noch einmal (Belegabruf vorher beenden). Ersetzt werden nur die
Programmdateien im Ordner „Belegabruf“; Einstellungen, Anmeldungen und Protokolle bleiben, sie liegen im
Datenordner. Was du selbst in den Ordner gelegt hast, bleibt ebenfalls.

Was die Zeile genau tut, steht im Skript selbst: [installieren.sh](https://github.com/balazskinal/belegabruf/blob/main/installieren.sh) (Mac),
[installieren.ps1](https://github.com/balazskinal/belegabruf/blob/main/installieren.ps1) (Windows). Es lädt nur von `github.com/balazskinal/belegabruf` und
bricht ab, wenn die Prüfsumme nicht stimmt oder fehlt.

## Was das Programm macht

1. Du doppelklickst **„Belegabruf Mac“** bzw. **„Belegabruf Windows“** und dann im Fenster
   **„Belege holen“**.
2. Es prüft, ob du bei Airbnb noch angemeldet bist. Wenn nicht, öffnet sich ein Browserfenster
   und **du** meldest dich ganz normal an (auch mit Zwei-Faktor). Dein Passwort steht nirgends.
3. Danach holt es alles allein und unsichtbar, in ruhigem, menschlichem Tempo:
   - die **Monatsübersichten** der letzten 12 Monate → Ordner `airbnb/kontrolle/`
   - jede **Einzelrechnung** daraus → `airbnb/<Jahr>/<Rechnungsdatum>_<Buchungscode>_<Rechnungsnummer>.pdf`
     (auf Wunsch nach Jahr und Monat: `airbnb/<Jahr>/<Monat>/…`, Einstellung „Unterordner“)
4. Am Ende steht eine Zusammenfassung: wie viele neu, wie viele schon da, und ob die Anzahl zu den
   Monatsübersichten passt.

Was einmal geholt wurde, wird nicht noch einmal geholt — **auch wenn du die Datei aus dem
Belegordner löschst oder verschiebst.** Das merkt sich ein **Protokoll** bei den Einstellungen (nicht
im Belegordner). Den Belegordner darfst du also jederzeit leeren oder an die Buchhaltung bzw. den
Steuerberater weiterreichen, ohne dass alles wiederkommt. Gastnamen kommen nirgends vor — weder in
Dateinamen noch im Protokoll.

**Belege nur vom Anbieter selbst.** Gespeichert wird ein Beleg nur, wenn er von der Adresse des
Anbieters kommt — über `https`, ohne fremden Port:

| Anbieter | erlaubte Adresse |
|---|---|
| Airbnb | `www.airbnb.de` (bzw. die eingestellte Länderadresse) |
| Skool | `www.skool.com` |
| Xentra | `app.myxentra.com` und der Download-Speicher des Rechnungsdienstes Chargebee (`cb-prod-eu-c1-downloads.s3.eu-central-1.amazonaws.com`) |
| Booking.com | `admin.booking.com` |

Zeigt ein Link woanders hin, ruft das Programm ihn nicht auf. Führt eine Weiterleitung woandershin, geht
die Anfrage zwar raus, **gespeichert wird aber nichts**. Die Zusammenfassung sagt dann „Adresse nicht vom
Anbieter (…), nicht geholt“ — nur mit dem Namen des fremden Rechners, ohne den Rest der Adresse — und der
Lauf gilt als „nicht alles geholt“.

5. Ist der **Mailversand** eingeschaltet, geht jede neue Rechnung als eigene Mail mit PDF an die
   eingestellten Adressen (siehe [Versand per Mail](#versand-per-mail)). Die Datei bleibt trotzdem im
   Belegordner.

**Wichtig:** Airbnb zeigt nur die **letzten 12 Monate**. Was älter ist, ist weg. Am besten einmal
im Monat laufen lassen. Liegt der letzte Lauf über zwei Monate zurück, warnt das Programm beim Start.

---

## Was im Ordner liegt

```
belegabruf-v…/
  Belegabruf Mac.command     ← der Starter für den Mac: richtet sich ein und öffnet das Fenster „Belegabruf“
  Belegabruf Windows.cmd     ← derselbe Starter für Windows
  programm/                  ← das eigentliche Programm, hier musst du nichts anfassen
  Fehlersuche/               ← nur, wenn etwas nicht klappt: das bisherige Menü im Terminal
    Belegabruf Terminal Mac.command
    Belegabruf Terminal Windows.cmd
  Doku/                      ← diese Anleitung (README.md) und die Lizenz (LICENSE)
```

Oben liegen nur die zwei Starter — du nimmst den für dein System. Den Ordner `programm` nicht
verschieben oder umbenennen, und die Starter nicht einzeln herausziehen: Sie suchen `programm` direkt
daneben. Eine Verknüpfung (Mac: Alias) auf dem Schreibtisch geht.

## Erster Start (einmalig, ca. 5 Minuten)

Am einfachsten mit der [Zeile oben](#einrichten--mit-einer-zeile-empfohlen). **Von Hand mit dem ZIP** geht
es so — dabei fragt dein Rechner einmal nach (siehe Schritt 3). Du brauchst eine Internetverbindung.
Installiert wird nur in deinem Benutzerkonto, keine Administratorrechte nötig.

1. **Herunterladen:** Auf der Seite [Neueste Version](https://github.com/balazskinal/belegabruf/releases/latest)
   die Datei `belegabruf-v….zip` laden.
2. **Auspacken:** Doppelklick auf die ZIP-Datei. Den entstandenen Ordner `belegabruf-v…` an einen
   Ort legen, wo er bleiben darf (z. B. in deinen Dokumenten-Ordner).
3. **Den Starter doppelklicken** — auf dem Mac **„Belegabruf Mac“**, unter Windows **„Belegabruf
   Windows“** (beide liegen oben im ausgepackten Ordner). Beim ersten Mal richtet er sich ein, danach
   öffnet er nur noch das Fenster.

   **Beim ersten Mal fragt dein Rechner nach, ob du das wirklich öffnen willst.** Das ist normal bei
   Programmen, die nicht aus einem App-Store kommen:
   - **Mac (macOS 15 und neuer):** Es erscheint die Meldung *„Apple konnte nicht überprüfen, ob
     ‚Belegabruf Mac.command‘ frei von Schadsoftware ist …“*.
     1. Dort auf **„Fertig“** klicken — **nicht** auf „In den Papierkorb legen“.
     2. *Systemeinstellungen → Datenschutz & Sicherheit* öffnen, ganz nach unten scrollen und bei
        „‚Belegabruf Mac.command‘ wurde blockiert …“ auf **„Trotzdem öffnen“** klicken; mit Passwort
        bzw. Touch ID bestätigen.
     3. **„Belegabruf Mac“ noch einmal doppelklicken** und die nächste Rückfrage bestätigen (je nach
        macOS-Version heißt der Knopf „Öffnen“ oder „Trotzdem öffnen“).

     Nach jedem **neu geladenen ZIP** (also bei jedem Update) fragt macOS wieder — dann dieselben
     Schritte.
   - **Windows:** Es erscheint „Der Computer wurde durch Windows geschützt“. Auf **„Weitere
     Informationen“** und dann **„Trotzdem ausführen“** klicken.
4. Ein schwarzes Fenster geht auf und lädt alles Nötige (ein Hilfsprogramm namens *uv*, Python und
   einen eigenen Browser). Das dauert beim ersten Mal ein paar Minuten.
5. Dann öffnet sich das Fenster **„Belegabruf“** mit den beiden Reitern **„Belege holen“** und
   **„Einstellungen“**. Beim ersten Start ist „Einstellungen“ offen. Dort:
   - den **Belegordner** (Vorschlag: `Dokumente/Belege`) und darunter die **Unterordner**: nach Jahr
     (wie bisher) oder nach Jahr und Monat. Das gilt für neue Belege; bereits abgelegte bleiben, wo sie
     sind,
   - deine **Konten**: den Anbieter (Airbnb, Skool, Xentra, Booking.com). Ein Name ist erst nötig, wenn du beim selben
     Anbieter mehrere Konten hast (z. B. einen Zugang als Co-Gastgeber) — dann bekommt jedes einen Namen
     nur für dich und seine eigene Anmeldung. Je Konto wählst du **„Belege ab“**: alle (Vorgabe), letzter
     Monat, letzte 3 oder 12 Monate (jeweils ab dem 1. des Monats) oder ab einem Datum. Ältere Belege
     werden nicht geholt und nicht vermerkt — erweiterst du den Zeitraum später, kommen sie beim nächsten
     Lauf (und werden, wenn der Versand per Mail an ist, auch verschickt),
   - auf Wunsch den **Versand per Mail** (siehe unten),

   dann **„Einstellungen speichern“**. Fehlt etwas, steht das direkt am Knopf, und die Felder sind rot
   markiert.
6. Gleich dort, in den **Einstellungen**, je Konto einmal **„Anmelden“**: Es öffnet sich ein eigenes
   Fenster, dort meldest du dich ganz normal an. Danach steht beim Konto „angemeldet“. Fertig. Im Reiter
   **„Belege holen“** wählst du mit dem **Haken** je Konto, welche Konten geholt werden; ein Klick merkt
   sich die Auswahl. „Alle Anmeldungen prüfen“ prüft trotzdem alle Konten.

Das schwarze Terminalfenster bleibt dabei klein offen — **nicht schließen, solange Belegabruf läuft.**
Beenden über den Knopf **„Beenden“** im Fenster „Belegabruf“ (oder das Fenster schließen).

## Skool

Skool zeigt die Rechnungen unter *Einstellungen → Zahlungsverlauf*, je Zahlung eine Rechnung. Einen
PDF-Knopf gibt es dort nicht: Das Programm öffnet jede Rechnung im (unsichtbaren) Browser, prüft, dass
Überschrift und Gesamtbetrag da sind, und speichert sie selbst als PDF:
`skool/<Jahr>/<Datum>_<Community>_<Rechnungs-ID>.pdf`. Bist du Mitglied in mehreren bezahlten
Communities, kommen alle mit; die Community steht im Dateinamen. Am Ende vergleicht es, ob so viele
Rechnungen geholt sind, wie der Zahlungsverlauf nennt. Das PDF kommt immer im **hellen Design**
heraus (gut zum Drucken und für die Texterkennung), auch wenn dein Skool-Konto auf Dunkel steht — das
gilt nur für den Ausdruck, deine Einstellung bei Skool bleibt, wie sie ist.

Das Programm **liest nur und lädt herunter**. Es klickt bei Skool nichts an — weder
Zahlungsmethoden noch Kündigung.

**Anmeldung mit Google:** Wer sich bei Skool sonst „Mit Google“ anmeldet, wird im Anmeldefenster des
Programms womöglich von Google blockiert („Dieser Browser oder diese App ist möglicherweise nicht
sicher“). Dann bei Skool mit **E-Mail und Passwort** anmelden. Hast du noch kein Skool-Passwort,
leg vorher in deinem normalen Browser eins fest (bei der Skool-Anmeldung über „Passwort vergessen“).
## Xentra

Xentra zeigt die Rechnungen unter *Abrechnung → Rechnungen*: Datum, Beschreibung, Betrag, Status und
ein Knopf „PDF herunterladen“. Das Programm drückt diesen Knopf für jede Zeile — wie du es mit der
Maus tun würdest —, lädt das PDF und speichert es als
`xentra/<Jahr>/<Datum>_xentra_<Rechnungsnummer>.pdf`. Die Beschreibung kommt absichtlich nicht in den
Dateinamen (bei Provisionen stehen dort Gastnamen). Am Ende vergleicht es, ob so viele Rechnungen
vorliegen, wie die Liste zeigt.

Das Programm **liest nur und lädt herunter**. Angeklickt werden nur der Reiter „Rechnungen“ und die
Knöpfe „PDF herunterladen“ — nichts an Abo, Zahlungsmethode oder Einstellungen. Damit es merkt, was
schon geholt ist, drückt es bei jedem Lauf alle Download-Knöpfe einmal; geladen und gespeichert wird
aber nur, was neu ist.

## Booking.com

Booking.com stellt alles im **Extranet** unter *Finanzen* bereit. Angemeldet wird wie überall im eigenen
Fenster (Benutzername, Passwort, meist Zwei-Faktor). Als „angemeldet“ gilt das Konto erst, wenn die
Zwei-Faktor-Bestätigung abgeschlossen ist und das Extranet die Unterkunft zeigt. Das Programm holt drei Arten von Dokumenten und legt
jede in einen eigenen Ordner unter `booking/` — nach Jahr bzw. Jahr und Monat, wie bei „Unterordner“
eingestellt:

| Ordner | Was | Verschickt? |
|---|---|---|
| `Rechnungen (an Booking.com)/` | die **Kommissionsrechnungen** (Reiter „Zahlungen an Booking.com“), je Monat ein PDF: `<Datum>_booking_<Rechnungsnummer>.pdf` | **ja** — das sind die Belege, nur sie gehen per Mail raus |
| `Auszahlungsübersichten (von Booking.com)/` | je abgeschlossenem Monat die Auszahlungsübersicht als PDF und CSV (Reiter „Zahlungen von Booking.com“): `<JJJJ-MM>_auszahlungsuebersicht.pdf/.csv` | nein, nur abgelegt |
| `Auszahlungen/` | je Auszahlung PDF und CSV (*Finanzen → Informationen zu Auszahlungen*): `<Auszahlungsdatum>_auszahlung_<Buchungsnummer(n)>_checkin-<Datum>.pdf/.csv` | nein, nur abgelegt |

- Bei einer Auszahlung mit mehreren Buchungen stehen bis zu drei Buchungsnummern im Namen, dann z. B. `+2`;
  der Check-in ist der früheste.
- **Gastnamen kommen nie in Dateinamen**, Protokoll oder Ausgaben — wie bei allen Anbietern. Zur Zuordnung
  reicht die Buchungsnummer; der Name steht in der CSV-Datei selbst, die unverändert abgelegt wird.
- Der laufende Monat kommt bei den Auszahlungsübersichten erst, wenn er vorbei ist (dann ist er vollständig).
  Auszahlungen holt das Programm für dieses und das letzte Jahr (ältere bietet Booking.com nur über einen
  eigenen Zeitraum an), Rechnungen für alle Jahre des Filters. „Belege ab“ gilt für alle drei Arten.
- **Mehrere Unterkünfte** unter einer Anmeldung: Geholt wird die, auf der das Extranet nach der Anmeldung
  landet. Für mehrere in der Einstellungsdatei beim Konto `unterkunft = "<ID>, <ID>"` eintragen (die ID
  steht im Extranet oben neben dem Namen der Unterkunft); jede wird für sich geholt, ihre ID steht dann
  im Dateinamen. Steht dort etwas anderes als Ziffern, holt das Programm nichts und sagt das in der
  Zusammenfassung.

### Co-Hosting / fremde Unterkünfte

**Booking.com:** Das klappt mit dem eigenen Extranet-Konto, wenn der Eigentümer einen je Unterkunft mit dem
Recht **„Finance“** (oder als Admin) einlädt. So lädt der Eigentümer ein: Nutzerkonto-Symbol →
„Create and manage users“ → „Add a user“ → Rechte wählen → „Send invite“. Belegabruf geht dann je
Unterkunft auf *Finanzen → Rechnungen und Dokumente* (die IDs wie oben bei `unterkunft` eintragen). Dafür
ruft es die Finanzseiten jeder Unterkunft direkt über ihre ID auf, nicht über das Menü. Ob ein Konto sie
sehen darf, entscheidet allein Booking.com: Im Gruppen-Extranet zeigt Booking.com das Finanzmenü nur
Primary-Konten; ob ein anderes Konto mit „Finance“-Recht die Seiten trotzdem öffnen kann, ist bisher nicht
an einem echten Konto ausprobiert. Verweigert Booking.com den Zugriff, meldet Belegabruf das (siehe
unten) und holt nichts an der Berechtigung vorbei. Fehlt das Recht nur bei einzelnen Unterkünften, holt das Programm die übrigen
trotzdem; das Konto steht dann auf „unvollständig“ mit dem Hinweis „kein Zugriff auf Finanzen für diese
Unterkunft“. Nur wenn keine Unterkunft Finanzen zeigt, heißt es „Dieses Booking-Konto hat keinen Zugriff
auf Finanzen“.

**Airbnb:** Belegabruf liest bisher nur die Steuerdokumente des eigenen Kontos. Der Weg für Co-Gastgeber
über *Einkünfte → „Als Co-Gastgeber ansehen“* wird noch nicht unterstützt. Bis dahin: ein eigenes Konto
des Eigentümers in Belegabruf anlegen (der Eigentümer meldet sich darin selbst an), oder der Eigentümer
exportiert die Rechnungen selbst.

Das Programm **liest nur und lädt herunter**. Angeklickt werden nur der Reiter „Zahlungen von
Booking.com“, der Jahresfilter und das Zeitraumfeld bei den Auszahlungen — nichts an Preisen,
Verfügbarkeit oder Einstellungen. Gespeichert wird nur, was von `https://admin.booking.com` kommt (siehe
„Belege nur vom Anbieter selbst“ oben) — ein Link auf eine andere Adresse wird nicht aufgerufen, und nach
einer Weiterleitung woandershin wird nichts gespeichert. Der Sitzungsschlüssel des Extranets (`ses` in der
Adresse) wird nie gespeichert oder ausgegeben.

## Benutzen

Doppelklick auf **„Belegabruf Mac“** bzw. **„Belegabruf Windows“**. Es öffnet sich das Fenster
**„Belegabruf“**:

- **Konten** — je Konto der Haken „Holen“ und der Zustand der Anmeldung (angemeldet, abgelaufen, noch
  nie angemeldet, unbekannt) mit dem Zeitpunkt der letzten Prüfung. **„Alle Anmeldungen prüfen“**
  aktualisiert ihn. Angemeldet wird im Reiter „Einstellungen“.
- **„Belege holen“** — holt alles Neue. Der Fortschritt läuft mit, am Ende steht die Zusammenfassung:
  wie viele neu, wie viele schon da, ob die Anzahl passt, was verschickt wurde.
- **„Fehlende Dateien neu holen“** — siehe unten.
- **Einstellungen** — Belegordner, Konten (hinzufügen, Zeitraum, **Anmelden**), Versand per Mail.
- **„Beenden“** — oben rechts.

Während des Abrufs musst du nichts tun und kannst den Rechner normal weiterbenutzen. Das kleine
Terminalfenster daneben bitte offen lassen, solange Belegabruf läuft.

**Läuft die Anmeldung ab** (Airbnb verlangt manchmal schnell eine neue Anmeldung), steht beim Konto
„abgelaufen“ und in der Zusammenfassung „nicht angemeldet“; darunter steht ein Hinweis „in den
Einstellungen anmelden“, der direkt zum Konto springt. Dort einmal **„Anmelden“**, dann noch einmal
**„Belege holen“** — der Rest wird nachgeholt.

**Eine Datei noch einmal holen:** Einfach löschen reicht nicht — das Protokoll weiß, dass sie schon
geholt wurde. Stattdessen **„Fehlende Dateien neu holen“** wählen (die Zahl am Knopf sagt, wie viele
fehlen). Dann kommt alles wieder, was im Protokoll steht, aber im Belegordner fehlt — soweit der
Anbieter es noch anbietet (bei Airbnb die letzten 12 Monate).

**Fehlersuche / lieber im Terminal?** Das bisherige Menü gibt es weiter: im Ordner `Fehlersuche`
**„Belegabruf Terminal Mac“** bzw. **„Belegabruf Terminal Windows“** doppelklicken (Enter = los,
E = Einstellungen, Q = beenden). Dort stehen alle Meldungen ausführlich im Terminal. Vorher muss der
normale Starter einmal gelaufen sein (er richtet alles ein). Einrichten als Fragen im
Terminal geht mit `uv run belege einrichten` (siehe unten) — dort lässt sich auch der Eintrag im
Passwortspeicher ändern.

## Versand per Mail

Auf Wunsch verschickt das Programm jede **neu geholte** Rechnung als **eigene Mail mit dem PDF im
Anhang** — an eine oder mehrere Adressen, je Rechnung und Adresse eine Mail. Betreff zum Beispiel
„Beleg Airbnb AIUC-… vom 27.10.2026“. So kommt die Rechnung überall an, wo es eine Belegadresse gibt
(Buchhaltungsprogramm, Steuerberatung), und wird dort gelesen wie jede andere Belegmail. sevDesk,
Lexware Office und viele andere Buchhaltungsprogramme haben dafür eine eigene Empfangsadresse für
Belege — die trägst du als Empfänger ein. Auch dein Steuerbüro kann Empfänger sein.

**Erster Versand** (Auswahl in den Einstellungen): Was passiert mit Belegen, die es beim Einschalten des
Mailversands schon gibt, mit dem Bestand für eine neu eingetragene Adresse und mit den Belegen aus dem
ersten Lauf eines neuen Kontos?
- **nicht verschicken (nur ablegen)** — die Vorgabe: Sie landen im Belegordner und gelten als verschickt.
  Gemailt wird erst, was danach neu dazukommt. Die Zusammenfassung sagt dann z. B. „12 Beleg(e) abgelegt,
  nicht verschickt (erster Lauf)“.
- **auch verschicken**: Beim Einschalten bzw. für eine neue Adresse geht der schon geholte Bestand einmal
  raus, beim ersten Lauf eines neuen Kontos alles aus dem Zeitraum „Belege ab“. Danach nur noch Neues.

Als „erster Lauf“ zählt, bis ein Lauf die Rechnungsliste des Kontos einmal gelesen hat. Erweiterst du den
Zeitraum „Belege ab“ später, werden die dann zusätzlich geholten älteren Rechnungen verschickt.

**Das Programm bringt keinen Versanddienst mit.** Verschickt wird über **dein eigenes Postfach** —
genauso, als würdest du die Mail selbst in deinem Mailprogramm schreiben. Deshalb fragt die Einrichtung
nach den Zugangsdaten deines Postfachs. Die Mails liegen danach je nach Anbieter auch in deinem Ordner
„Gesendet“.

**Einschalten:** Im Fenster „Belegabruf“ unter **Einstellungen** „Rechnungen zusätzlich per Mail
verschicken“ ankreuzen und unter **Mailanbieter** deinen Anbieter wählen (GMX, WEB.DE, Gmail,
Outlook.com, Microsoft 365, IONOS, STRATO, all-inkl.com, iCloud) — dann sind Server, Port und
Verschlüsselung schon eingetragen, und darunter steht, was bei diesem Anbieter zu beachten ist (z. B.
App-Passwort). Sonst „Anderer“ wählen und die Angaben selbst eintragen; die findest du bei deinem
Mailanbieter unter „SMTP“ oder „Postausgangsserver“. **Outlook.com** und **Microsoft 365** verlangen
zunehmend eine Anmeldung, die das Programm nicht kann (OAuth2) — dort am besten mit „Mail-Anmeldung
prüfen“ testen.

| Feld | Beispiel |
|---|---|
| Postausgangsserver | `smtp.example.com` |
| Verschlüsselung | SSL (meist Port 465) oder STARTTLS (meist Port 587) — **ohne Verschlüsselung wird nichts verschickt** |
| Benutzername | meist deine Mailadresse, z. B. `ich@example.com` |
| Absenderadresse | `ich@example.com` |
| Empfänger | z. B. `belege@example.com`, mehrere mit Komma |
| Passwort | eigenes Feld „Mail-Passwort“ → „Passwort hinterlegen“; danach steht dort nur „hinterlegt“ |

Mit **„Mail-Anmeldung prüfen“** meldet es sich einmal am Mailserver an und wieder ab — **ohne eine Mail zu schicken** —
und sagt, ob es klappt.

**Das Passwort** kommt in den **Passwortspeicher deines Rechners** (Mac: Schlüsselbund, Windows:
Anmeldeinformationsverwaltung) und **nie in eine Datei**. In den Einstellungen steht nur, unter
welchem Eintrag es liegt (Vorschlag: `belegabruf/mail`). Austauschen oder löschen im Reiter
„Einstellungen“ unter „Mail-Passwort“. Auf dem Mac fragt der Schlüsselbund beim ersten Versand, ob das Programm den Eintrag
lesen darf — dort **„Immer erlauben“** wählen (nach einem Update kann die Frage wiederkommen).

**Gmail und Microsoft 365:** Mit dem normalen Passwort klappt es dort meist nicht.
- **Gmail:** Zwei-Faktor-Anmeldung einschalten und ein **App-Passwort** anlegen (Google-Konto →
  Sicherheit → App-Passwörter). Server `smtp.gmail.com`, STARTTLS, Port 587.
- **Microsoft 365 / Outlook:** Für das Postfach muss **SMTP AUTH** eingeschaltet sein (macht die
  Verwaltung im Microsoft-365-Admin-Center); mit Zwei-Faktor zusätzlich ein App-Passwort. Server
  `smtp.office365.com`, STARTTLS, Port 587.
- Anmeldung über OAuth („Mit Google/Microsoft anmelden“) ist **nicht vorgesehen**.

**Alter Bestand:** Kommt eine Empfängeradresse **zum allerersten Mal** dazu, gilt alles, was bis
dahin geholt ist, für sie als **schon verschickt** und geht nicht raus. Verschickt wird nur, was danach
neu dazukommt. Schaltest du den Versand (oder eine Adresse) später aus und wieder ein, wird nichts
mehr als verschickt markiert: Dann geht alles raus, was in der Zwischenzeit geholt wurde. **Wer
zwischendurch von Hand verschicken will, schaltet den Versand deshalb nicht aus** — sonst kommen diese
Rechnungen beim Wiedereinschalten doppelt an.

**Achtung bei Neuinstallation oder neuem Konto:** Ist der Mailversand schon eingeschaltet, wenn ein
Konto zum ersten Mal abgerufen wird (neuer Rechner ohne die alten Protokolle, oder ein neu
hinzugefügtes Konto), gibt es noch nichts, was als verschickt gelten könnte. Dann gehen beim ersten Lauf
**alle verfügbaren Rechnungen** raus — bei Airbnb bis zu 12 Monate. Wer das nicht will, ruft zuerst
einmal ohne Mailversand ab und schaltet die Mail erst danach ein.

**Nie doppelt:** Das Protokoll merkt sich je Adresse, was verschickt ist. Klappt der Versand nicht
(kein Internet, falsches Passwort, der Server lehnt ab), bleibt die Rechnung im Belegordner, die
Zusammenfassung zeigt die Meldung des Servers, und der **nächste Lauf versucht es erneut**. Kommt
nach dem Senden keine Antwort vom Server, ist unklar, ob die Mail angekommen ist. Dann schickt das
Programm sie **nicht** noch einmal und sagt dir, bei welcher Rechnung du beim Empfänger nachsehen
sollst.

**Was das Programm am Mailserver tut:** nur anmelden, senden, abmelden. Es liest keine Postfächer.

## Wo was liegt

| Was | Wo |
|---|---|
| Deine Belege | der Belegordner aus den Einstellungen |
| Einstellungen | Mac: `~/Library/Application Support/belegabruf/einstellungen.toml` · Windows: `%APPDATA%\belegabruf\einstellungen.toml` |
| Anmeldungen (Browserprofile) | im selben Ordner unter `profile/` — **darf man jederzeit löschen** |
| Protokolle (was schon geholt und verschickt ist) | im selben Ordner unter `protokolle/<anbieter>/<konto>.csv` — **nie löschen** |
| Mail-Passwort | im Passwortspeicher des Betriebssystems, nie in einer Datei |

Die Einstellungsdatei ist eine Textdatei mit Erklärungen und lässt sich mit jedem Texteditor
ändern. Ein Konto lässt sich dort mit `aktiv = "nein"` vorübergehend ausschalten.

Der Ordner `profile/` enthält deine eingeloggten Sitzungen — **wie ein offener Browser, in dem du
angemeldet bist.** Gib ihn nicht weiter und leg ihn nicht in eine Cloud-Freigabe. Zum Abmelden
reicht es, ihn zu löschen; beim nächsten Start kommt dann das Anmeldefenster.

Der Ordner `protokolle/` dagegen **bitte nie löschen.** Darin steht, was schon geholt wurde. Ohne
ihn holt das Programm beim nächsten Lauf alle 12 Monate noch einmal — und wer die Belege schon
weitergegeben hat, hätte sie dann doppelt in der Buchhaltung.

**Umstieg von Version 1.0:** Dort lag das Protokoll als `protokoll.csv` im Belegordner. Beim ersten
Start von Version 1.1 wird es automatisch übernommen und danach in `protokoll.csv.uebernommen`
umbenannt (nicht gelöscht). Danach kannst du die alte Datei wegwerfen.

## Neue Version installieren (Update)

Beim Start steht ein Hinweis, wenn es eine neuere Version gibt.

**Mit einer Zeile (empfohlen):** Belegabruf beenden und
[dieselbe Zeile wie beim Einrichten](#einrichten--mit-einer-zeile-empfohlen) noch einmal ins Terminal bzw. in
PowerShell — fertig. Wer bisher mit dem ZIP gearbeitet hat: Die Zeile legt Belegabruf im Programme-Ordner
an (siehe [oben](#einrichten--mit-einer-zeile-empfohlen)); den alten Ordner `belegabruf-v…` kannst du danach
löschen (Einstellungen und Anmeldungen bleiben).

**Von Hand mit dem ZIP:**

1. Den **alten Ordner `belegabruf-v…` komplett löschen** (mit allem darin, auch `programm`).
2. Die neue ZIP-Datei von [Neueste Version](https://github.com/balazskinal/belegabruf/releases/latest) laden und auspacken.
3. **„Belegabruf Mac“ bzw. „Belegabruf Windows“ doppelklicken.** Beim ersten Start richtet sich die
   neue Version selbst ein („Richte die neue Version ein …“, einmalig, dauert einen Moment). Hattest du
   eine Verknüpfung auf den alten Starter, leg sie neu an.

Kurz: **ZIP auspacken, Belegabruf doppelklicken.**

Einstellungen, Anmeldungen, Protokolle und Belege bleiben dabei erhalten — sie liegen im Datenordner
(siehe [Wo was liegt](#wo-was-liegt)), nicht im Programmordner.

**Von 2.0.0 auf 2.0.1:** Die Starter heißen jetzt „Belegabruf Mac“ und „Belegabruf Windows“ und liegen
oben im Ordner; die Ordner `Start Mac` und `Start Windows` gibt es nicht mehr.
Ein automatisches Selbst-Update gibt es bewusst nicht.

## Was neu ist

- **2.2.3** — **Booking.com: Co-Hosting mit einzelnen Unterkünften ohne Finanzrecht.** Fehlt dem Konto bei
  einer Unterkunft das Recht „Finance“, bricht der Abruf nicht mehr für das ganze Konto ab: Die übrigen
  Unterkünfte werden geholt, das Konto steht auf „unvollständig“ mit einem Hinweis zu genau dieser
  Unterkunft. Eine Seite „Zugriff verweigert“ (403) ohne Extranet-Menü und ohne Code- oder Passwortfeld
  gilt als „kein Zugriff“, nicht mehr als „Bestätigung verlangt“ (eine Sperrseite des Netzwerkdienstes
  zählt als „nicht geladen“); verweigert Booking.com erst einen
  späteren Abschnitt (z. B. Auszahlungen), fehlt nur dieser. Die Meldung „kein Zugriff auf Finanzen“
  nennt jetzt das Recht „Finance“ statt nur Primary-Konten. Die Erkennung solcher Hinweise prüft nur noch ganze Wörter. Neu im README:
  Abschnitt „Co-Hosting / fremde Unterkünfte“ (Booking.com und Airbnb).
- **2.2.2** — **Booking.com: „angemeldet“ erst nach abgeschlossener Zwei-Faktor-Bestätigung.** Bisher konnte
  das Programm ein Booking-Konto schon als angemeldet zeigen, während Booking.com noch auf den Bestätigungscode
  wartete. Jetzt bleibt das Anmeldefenster offen, bis das Extranet wirklich die Unterkunft zeigt; hängt es
  an der Bestätigung, steht in der Oberfläche „Bitte schließ die Bestätigung (Zwei-Faktor) im
  Booking-Fenster ab“. Dieselbe Prüfung gilt beim „Prüfen“ und vor jedem Abruf. Verlangt Booking.com
  mitten im Abruf eine neue Bestätigung, meldet das Programm das als „Anmeldung abgelaufen“ mit Hinweis
  (nicht als „nichts Neues“). Darf ein Konto die Finanzen nicht sehen (im Group-Extranet nur
  Primary-Konten), sagt es „Dieses Booking-Konto hat keinen Zugriff auf Finanzen“.
- **2.2.1** — **Einrichtung auf Rechnern ohne passendes Python repariert.** Die Starter richten jetzt fest
  Python 3.12 ein; eine schon angelegte Umgebung mit anderer Python-Version wird beim nächsten Start
  neu aufgebaut. Bisher konnte uv auf einem neuen Rechner Python 3.15 laden; dafür gibt es einen von PyMuPDF
  benötigten Baustein (onnxruntime) noch nicht, und die Einrichtung brach mit „Das hat nicht geklappt“ ab.
  Dazu der Prüf-Workflow für jeden Pull Request (siehe „Prüfungen“).
- **2.2.0** — **Einrichten und Update mit einer Zeile** im Terminal bzw. in PowerShell (siehe ganz oben):
  lädt die neueste Version, prüft die Prüfsumme, legt sie in den Programme-Ordner des Benutzers (Mac
  `~/Applications/Belegabruf`, Windows `%LOCALAPPDATA%\Programs\Belegabruf` mit Eintrag im Startmenü) und
  startet sie — ohne Sicherheitsmeldung. Der Hinweis „neuere Version“ nennt jetzt diese Zeile. Pfade in Meldungen
  zeigen den Benutzerordner als `~`.
- **2.1.1** — **Belege nur vom Anbieter selbst**, für alle Anbieter gleich geprüft (siehe oben): nur
  `https`, kein fremder Port, keine Benutzerangaben, Host genau der des Anbieters — vor dem Aufruf und
  nach einer Weiterleitung. Abgewiesenes steht in der Zusammenfassung. Kleinigkeiten:
  - Listen in der Einstellungsdatei (z. B. `unterkunft = ["1234567", "7654321"]` bei Booking.com) bleiben
    nach dem Speichern im Fenster erhalten; bisher wurden sie zu Text.
  - Booking.com: Ist während eines Downloads das Netz weg, heißt es „nicht geladen“ statt „Anmeldung
    abgelaufen“ — abgelaufen nur, wenn wirklich die Anmeldeseite kommt.
  - **Konten ohne Namen finden ihre frühere Anmeldung wieder.** Hat ein Konto ohne Namen seine interne
    Kennung verloren (z. B. war die Einstellungsdatei beim Einrichten nicht lesbar, oder der Name wurde
    von Hand gelöscht), übernimmt es Anmeldung und Protokoll von früher — wenn genau eines in Frage kommt.
    Schon Geholtes kommt dann nicht noch einmal und wird deshalb nicht verschickt. Konten mit Namen und
    Konten, die du in den Einstellungen entfernt hast, geben nie etwas an ein anderes Konto weiter. Ist es
    nicht eindeutig, wird das Konto ausgelassen, und die Zusammenfassung sagt, was zu tun ist.
  - Ist die Einstellungsdatei nicht lesbar, speichert das Fenster nicht mehr darüber, sondern sagt, wie
    man sie repariert.
- **2.1.0** — **Booking.com** als neuer Anbieter: Kommissionsrechnungen (werden wie alle Belege abgelegt
  und auf Wunsch verschickt), dazu Auszahlungsübersichten und Auszahlungen als PDF und CSV, nur abgelegt,
  je Art in einem eigenen Ordner (siehe [Booking.com](#bookingcom), ADR-006).
- **2.0.1** — **Aufgeräumter Ordner:** Oben liegen nur noch die zwei Starter „Belegabruf Mac“ und
  „Belegabruf Windows“; `programm/`, `Fehlersuche/` und `Doku/` (Anleitung, Lizenz) sind Ordner. Sonst
  unverändert bis auf Kleinigkeiten:
  - Der Hinweis zu „Belege ab“ sagt jetzt, dass beim Erweitern des Zeitraums die nachgeholten Belege
    auch verschickt werden, wenn Mail an ist.
  - `--konto` im Terminal trifft je Anbieter nur noch ein Konto.
  - Die Terminal-Einrichtung (`belege einrichten`) behält beim Ändern der Mail-Angaben die Auswahl
    „Erster Versand“; bisher sprang sie auf „nicht verschicken“ zurück.
  - Neu eingegebene Mailadressen (im Fenster und im Terminal) müssen die Form `name@domain.tld` haben.
    Eine bestehende Einstellungsdatei wird weiter gelesen wie bisher.
  - Bei Unterordnern nach Monat: Ein Beleg ohne Rechnungsdatum aus einem früheren Jahr kommt in den
    Jahresordner (nicht in einen geratenen Monat).
- **2.0.0** — **Bedienung im Fenster statt im Terminal.** Nur noch **ein Starter je System:**
  „Belegabruf“ ersetzt „Einrichten“ und „Belege holen“; er richtet sich selbst ein und öffnet das Fenster
  „Belegabruf“: Einstellungen als Formular (auch Mail-Passwort, direkt in den Passwortspeicher), je
  Konto Anmelden und Prüfen, Belege holen mit Fortschritt und Zusammenfassung. Das bisherige Menü gibt es
  weiter über den Ordner „Fehlersuche“. Ein Kontoname ist nur noch nötig, wenn es beim selben Anbieter
  mehrere Konten gibt. Neu: Haken je Konto zum Holen, Zeitraum je Konto („Belege ab“), Unterordner nach
  Jahr und Monat, Mailanbieter als Auswahl. Update ab jetzt: neues ZIP auspacken, „Belegabruf“
  doppelklicken — die neue Version richtet sich selbst ein. **Windows ist noch ungetestet.**
- **1.3.0** — Neue Rechnungen auf Wunsch zusätzlich **per Mail** verschicken (über dein eigenes
  Postfach, siehe [Versand per Mail](#versand-per-mail)). Beim Update einmal „Einrichten“
  doppelklicken; die Frage nach dem Mailversand steht auf „nein“, bis du sie mit „j“ beantwortest.
- **1.2.0** — Zwei neue Anbieter: **Xentra** (Abo- und Provisionsrechnungen) und **Skool**
  (Rechnungen für bezahlte Communities, immer als helles PDF). Beim Update einmal „Einrichten“
  doppelklicken und die neuen Anbieter dazunehmen.
- **1.1.0** — Das Protokoll entscheidet, was schon geholt ist (nicht mehr der Belegordner); es liegt
  bei den Einstellungen. Neu: „Fehlende Dateien neu holen“.
- **1.0.0** — Erste Version: Airbnb-Rechnungen per Doppelklick.

## Rechtliches

- Das Programm ruft **deine eigenen Rechnungen aus deinem eigenen Konto** ab, so wie du es von Hand
  im Browser tun würdest, und in einem ähnlich ruhigen Tempo. Ob das zu den Nutzungsbedingungen des
  Anbieters passt, **prüft jeder selbst.**
- Fragen zu Aufbewahrungspflichten und Buchhaltung klärst du am besten mit deinem Steuerberater.
- Lizenz: MIT (siehe [LICENSE](LICENSE)). Keine Gewähr.

---

## Für Neugierige und Entwickler

Warum das Programm so gebaut ist, steht in den **Entscheidungen** unter
[`docs/entscheidungen/`](https://github.com/balazskinal/belegabruf/blob/main/docs/entscheidungen/README.md);
was als Nächstes kommt, in der [Roadmap](https://github.com/balazskinal/belegabruf/blob/main/docs/roadmap.md).

### Kommandozeile

Im Ordner `programm` (mit installiertem [uv](https://docs.astral.sh/uv/)):

```bash
uv run belege oberflaeche                       # Fenster „Belegabruf“ (wie Doppelklick auf „Belegabruf“)
uv run belege start                             # Menü im Terminal (wie der Starter in „Fehlersuche“)
uv run belege einrichten                        # Einrichten als Fragen im Terminal
uv run belege pruefen --json                    # sind die Konten angemeldet?
uv run belege anmelden --quelle airbnb --konto privat
uv run belege holen --quelle airbnb --json      # unbeaufsichtigt, öffnet nie ein Fenster
uv run belege holen --fehlende                  # dazu Fehlendes neu holen
```

`belege holen` gibt mit `--json` ein maschinenlesbares Ergebnis aus (Fortschritt geht nach stderr).
Exit-Code: 0 = alles gut, 2 = Anmeldung nötig oder abgelaufen, nicht alles geholt oder nicht alles
verschickt (später noch einmal), 1 = Fehler. So lassen sich die
Bausteine später auch aus einer Automatisierung (z. B. n8n) aufrufen.

### Sicherheit der Bedienoberfläche

Das Fenster „Belegabruf“ spricht mit einem kleinen Server im Programm selbst. Er ist **nur auf diesem
Rechner** erreichbar (`127.0.0.1`, freier Port) und nur mit einem **Zufallsschlüssel**, den nur das Fenster
kennt. Anfragen mit fremdem `Host` (Schutz vor DNS-Rebinding), fremdem `Origin` oder ohne Schlüssel lehnt
er ab; es gibt kein CORS, keine Protokolldatei, und Passwörter gehen nur hinein (direkt in den
Passwortspeicher), nie heraus. Die Tests dazu stehen in `programm/tests/test_oberflaeche.py`.

### Aufbau

```
Belegabruf Mac.command,      Starter (wechseln nach programm/, richten ein, rufen "belege oberflaeche" auf)
Belegabruf Windows.cmd
Fehlersuche/                 Starter für das Menü im Terminal ("belege start")
installieren.sh, .ps1         Einrichten/Update mit einer Zeile (die Release-Action hängt sie an jedes Release)
README.md, LICENSE           im ZIP unter Doku/ (die Release-Action kopiert sie dorthin)
programm/
  pyproject.toml, uv.lock    Abhängigkeiten (Python, Playwright, PyMuPDF, keyring)
  tests/
  belegabruf/
    cli.py            Kommandozeile und Menü im Terminal
    oberflaeche/      Fenster „Belegabruf“: lokaler Server (server.py), Aktionen (aktionen.py),
                      Bedienseite (seite.html) — ruft dieselben Bausteine wie das CLI
    ablauf.py         Gerüst: prüfen, anmelden lassen, holen, abliefern
    quellen/          ein Baustein je Anbieter: airbnb.py, skool.py, xentra.py, booking.py
      basis.py        die feste Schnittstelle für Bausteine
    ziele/            wohin Belege geliefert werden: ordner.py, mail.py
    protokoll.py      Protokoll je Anbieter und Konto — entscheidet, was schon geholt ist
    pruefung.py       nie eine Anmelde-, 404- oder leere Seite als Beleg speichern
```

Ein **Baustein (Quelle)** kann genau drei Dinge: `sitzung_pruefen()`, `anmelden_lassen()` und
`belege_holen()`. Er speichert nichts selbst, sondern übergibt jeden Beleg an die **Ziele**. Das
Ziel „ordner“ legt Dateien ab und ist immer dabei. **Lieferziele** wie „mail“ schicken danach weiter,
was laut Protokoll noch fehlt (`ablauf.liefern`, Schnittstelle `ziele/basis.py: Lieferziel`); das
Protokoll führt je Lieferziel „geliefert / schon / unklar / offen“. Weitere Ziele (z. B. Upload an
eine Buchhaltungssoftware per API) kommen als eigene Datei in `ziele/` dazu, ohne dass sich die
Quellen ändern. Zugangsdaten liegen nur im Passwortspeicher (`keyring`).

Tests (im Ordner `programm`): `uv run --group dev pytest`

### Prüfungen

Jeder Pull Request gegen `main` und jeder Push auf `main` durchläuft den Workflow
[Prüfung](https://github.com/balazskinal/belegabruf/blob/main/.github/workflows/pruefung.yml) (nur Leserechte, keine Secrets):

| Prüfung | was |
|---|---|
| **Tests** (Linux) | `uv sync --locked`, pytest mit Oberflächentests in Chromium, ruff, bandit, pip-audit, compileall, shellcheck — dieselben Schritte wie vor jedem Release ([tests.yml](https://github.com/balazskinal/belegabruf/blob/main/.github/workflows/tests.yml)) |
| **Tests Windows**, **Tests macOS** | pytest auf dem jeweiligen System, mit Oberflächentests |
| **Einrichtung Mac**, **Einrichtung Windows** | die Ein-Zeilen-Einrichtung aus dem PR echt mit der neuesten Version: Ordner, Version, Startmenü (Windows), Update als zweiter Lauf, Starter bis „Umgebung eingerichtet“; dazu shellcheck bzw. PSScriptAnalyzer |

### Neue Bausteine beitragen

Neue Bausteine (z. B. für einen weiteren Anbieter) bitte als **Pull Request**. Gemergt wird **nur
vom Maintainer**. Ein Baustein arbeitet mit den angemeldeten Sitzungen der Nutzer — deshalb wird
jeder fremde Beitrag vor einem Release vollständig geprüft. Regeln für Bausteine:

- kein Passwort, kein Token im Code; angemeldet wird immer vom Menschen im sichtbaren Fenster
- menschliches Tempo (`browser.pause()` zwischen Abrufen)
- Inhalt prüfen, bevor etwas als Beleg gilt (`pruefung.py`)
- keine personenbezogenen Daten Dritter (z. B. Gastnamen) in Dateinamen, Protokoll oder Ausgabe

### Neue Version veröffentlichen (Maintainer)

Version in `programm/pyproject.toml` erhöhen, committen, dann Tag setzen und pushen:

```bash
git tag v1.0.1
```

```bash
git push origin v1.0.1
```

Die GitHub Action baut das ZIP und hängt es an das Release.

## Offen

- **Windows:** noch von niemandem getestet — auch die Bedienoberfläche aus 2.0.0 nicht. Wer es
  ausprobiert, bitte Rückmeldung.
- **Mail:** Der erste echte Versand steht noch aus; getestet ist gegen einen nachgebauten Mailserver.
- Weitere Bausteine und das Ziel „Upload an die Buchhaltung per API“ folgen in späteren Versionen.
