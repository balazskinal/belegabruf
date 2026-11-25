# ADR-003: Zugangsdaten nur im Passwortspeicher des Betriebssystems

- **Datum:** 24.11.2026
- **Status:** ✅ gilt · Vorgabe für alle Ziele (Mail, Buchhaltungsprogramme)

## Entscheidung

1. API-Schlüssel und Mail-Passwörter liegen **nie in einer Datei**, sondern im **Passwortspeicher des
   Betriebssystems**: macOS-Schlüsselbund, Windows-Anmeldeinformationsverwaltung. Umsetzung über die
   Python-Bibliothek `keyring` (ein Code für beide Systeme).
2. Die Einrichtung fragt verdeckt ab. In der Einstellungsdatei steht nur, **unter welchem Eintrag**
   (`Dienst/Konto`) der Wert liegt. Wer schon einen Eintrag hat, kann ihn angeben.
3. Zugangsdaten erscheinen nie in Ausgaben, Protokollen, Logs oder Fehlermeldungen; Meldungen von
   Servern werden vor der Ausgabe davon bereinigt.
4. Austauschen und Löschen über „Einrichten“. Gelöscht wird nur ein Eintrag, den das Programm selbst
   angelegt hat.
5. **So wenig Rechte wie möglich.** Kann ein Ziel die Rechte eines Schlüssels nicht einschränken, ruft das
   Programm trotzdem nur die Aufrufe auf, die es zum Abliefern braucht, und verweigert jeden anderen
   Aufruf, bevor er rausgeht.

## Verworfen

- Zugangsdaten in der Einstellungsdatei (Klartext).
- Umgebungsvariablen (Klartext, für Laien zu kompliziert).
- Ein bestimmter Passwortmanager als einzige Quelle (hat nicht jeder).

## Folgen

Beim Umzug auf n8n liegen die Zugangsdaten in den verschlüsselten Zugangsdaten von n8n.
