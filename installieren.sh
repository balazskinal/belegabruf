#!/bin/bash
# Belegabruf einrichten oder aktualisieren (macOS) — mit einer Zeile im Terminal:
#
#   curl -fsSL https://github.com/balazskinal/belegabruf/releases/latest/download/installieren.sh | bash
#
# Was dieses Skript tut (und nichts sonst):
#   1. die neueste Version (bzw. BELEGABRUF_VERSION, z. B. v2.1.1) bei GitHub nachschlagen,
#   2. das ZIP von github.com/balazskinal/belegabruf laden und seine SHA-256-Prüfsumme prüfen
#      (aus der Release-Liste von GitHub bzw. der mitveröffentlichten .sha256) — ohne Prüfsumme
#      oder bei Abweichung bricht es ab,
#   3. nach ~/Documents/Belegabruf auspacken. Bei einem Update werden nur die eigenen
#      Programmdateien ersetzt; was du selbst in den Ordner gelegt hast, bleibt. Einstellungen,
#      Anmeldungen und Protokolle liegen im Datenordner (~/Library/Application Support/belegabruf)
#      und werden nicht angefasst,
#   4. „Belegabruf Mac“ starten und den Ordner im Finder zeigen.
# Kein sudo, keine Änderungen außerhalb von ~/Documents/Belegabruf (und einem Arbeitsordner in /tmp).
#
# Warum so: Was curl lädt, bekommt von macOS keine Quarantäne — so erscheint die Meldung
# „Apple konnte nicht überprüfen …“ nicht, die bei einem im Browser geladenen ZIP kommt.

set -euo pipefail

REPO="balazskinal/belegabruf"
ZIEL="${BELEGABRUF_ZIEL:-$HOME/Documents/Belegabruf}"
VERSION="${BELEGABRUF_VERSION:-}"
API="https://api.github.com/repos/$REPO/releases"
DOWNLOADS="https://github.com/$REPO/releases/"
# Nur diese Einträge gehören dem Programm; nur sie werden bei einem Update ersetzt.
EIGENE=("Belegabruf Mac.command" "Belegabruf Windows.cmd" "programm" "Fehlersuche" "Doku" ".belegabruf-version")

meldung() { printf '%s\n' "$*"; }
abbruch() {
  printf '\n✗ %s\n' "$*" >&2
  printf 'Es wurde nichts geändert. Bei Fragen: https://github.com/%s\n' "$REPO" >&2
  exit 1
}

[ "$(uname -s)" = "Darwin" ] || abbruch "Dieses Skript ist für den Mac. Unter Windows: siehe README (PowerShell-Zeile)."
for werkzeug in curl unzip shasum plutil; do
  command -v "$werkzeug" >/dev/null 2>&1 || abbruch "Das Programm „$werkzeug“ fehlt auf diesem Mac."
done
if [ -n "$VERSION" ] && ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  abbruch "BELEGABRUF_VERSION=„$VERSION“ ist keine Versionsnummer wie v2.1.1."
fi
case "$ZIEL" in
  "$HOME"/*) ;;
  *) abbruch "Der Zielordner muss in deinem Benutzerordner liegen." ;;
esac

ARBEIT="$(mktemp -d "${TMPDIR:-/tmp}/belegabruf-einrichten.XXXXXX")"
trap 'rm -rf "$ARBEIT"' EXIT

laden() {  # laden <Adresse> <Datei> — nur https, auch bei Weiterleitungen
  curl -fsSL --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 20 -o "$2" "$1"
}

adresse_erlaubt() {  # Nur Downloads dieses Repos bei GitHub.
  case "$1" in
    "${DOWNLOADS}download/"*|"${DOWNLOADS}latest/download/"*) return 0 ;;
    *) return 1 ;;
  esac
}

feld() {  # feld <JSON-Datei> <Schlüsselpfad> — leer, wenn es das Feld nicht gibt
  plutil -extract "$2" raw -o - "$1" 2>/dev/null || true
}

# ── 1. Welche Version, welches ZIP, welche Prüfsumme? ─────────────────────────
meldung "Belegabruf einrichten …"
if [ -n "$VERSION" ]; then
  RELEASE_URL="$API/tags/$VERSION"
else
  RELEASE_URL="$API/latest"
fi
TAG=""; ZIP_URL=""; ERWARTET=""
if laden "$RELEASE_URL" "$ARBEIT/release.json" 2>/dev/null; then
  TAG="$(feld "$ARBEIT/release.json" tag_name)"
  [ -n "$TAG" ] || abbruch "GitHub hat keine Version geliefert."
  # Bevorzugt das ZIP mit festem Namen (ab 2.2.0), sonst das versionierte (ältere Versionen).
  for gesucht in "belegabruf.zip" "belegabruf-$TAG.zip"; do
    i=0
    while name="$(feld "$ARBEIT/release.json" "assets.$i.name")" && [ -n "$name" ]; do
      if [ "$name" = "$gesucht" ]; then
        ZIP_URL="$(feld "$ARBEIT/release.json" "assets.$i.browser_download_url")"
        digest="$(feld "$ARBEIT/release.json" "assets.$i.digest")"
        case "$digest" in sha256:*) ERWARTET="${digest#sha256:}" ;; esac
        break 2
      fi
      i=$((i + 1))
    done
  done
  [ -n "$ZIP_URL" ] || abbruch "In der Version $TAG gibt es kein ZIP zum Herunterladen."
elif [ -z "$VERSION" ]; then
  # GitHub-Liste nicht erreichbar (z. B. zu viele Abfragen): feste Adresse der neuesten Version.
  ZIP_URL="${DOWNLOADS}latest/download/belegabruf.zip"
else
  abbruch "Die Version $VERSION gibt es bei GitHub nicht (oder GitHub ist nicht erreichbar)."
fi
adresse_erlaubt "$ZIP_URL" || abbruch "Unerwartete Download-Adresse — aus Sicherheitsgründen abgebrochen."

if [ -z "$ERWARTET" ] && [ "$(basename "$ZIP_URL")" = "belegabruf.zip" ]; then
  # Ohne Prüfsumme in der GitHub-Liste: die mitveröffentlichte Datei belegabruf.zip.sha256.
  if laden "$ZIP_URL.sha256" "$ARBEIT/zip.sha256" 2>/dev/null; then
    ERWARTET="$(awk '{print $1; exit}' "$ARBEIT/zip.sha256")"
  fi
fi
[[ "$ERWARTET" =~ ^[0-9a-f]{64}$ ]] || abbruch "Für diese Version gibt es keine Prüfsumme — ungeprüft wird nichts installiert."

# ── 2. Laden und prüfen ──────────────────────────────────────────────────────
meldung "Lade ${TAG:-die neueste Version} von GitHub …"
laden "$ZIP_URL" "$ARBEIT/belegabruf.zip" || abbruch "Das Herunterladen hat nicht geklappt. Besteht eine Internetverbindung?"
IST="$(shasum -a 256 "$ARBEIT/belegabruf.zip" | awk '{print $1}')"
[ "$IST" = "$ERWARTET" ] || abbruch "Die Prüfsumme des ZIPs stimmt nicht. Die Datei ist beschädigt oder nicht die echte — nicht installiert."
meldung "✓ Prüfsumme stimmt."

mkdir "$ARBEIT/aus"
unzip -q "$ARBEIT/belegabruf.zip" -d "$ARBEIT/aus" || abbruch "Das ZIP ließ sich nicht auspacken."
QUELLE="$(find "$ARBEIT/aus" -mindepth 1 -maxdepth 1 -type d -name 'belegabruf-v*' | head -n 1)"
[ -n "$QUELLE" ] && [ -f "$QUELLE/Belegabruf Mac.command" ] && [ -d "$QUELLE/programm" ] \
  || abbruch "Das ZIP hat nicht den erwarteten Inhalt."
[ -n "$TAG" ] || TAG="$(basename "$QUELLE" | sed 's/^belegabruf-//')"

# ── 3. Einspielen: nur die eigenen Einträge ersetzen ─────────────────────────
if [ -e "$ZIEL" ] && [ ! -d "$ZIEL" ]; then
  abbruch "„$ZIEL“ ist eine Datei, kein Ordner."
fi
if [ -d "$ZIEL" ] && [ -n "$(ls -A "$ZIEL")" ] && [ ! -e "$ZIEL/.belegabruf-version" ] \
   && [ ! -e "$ZIEL/Belegabruf Mac.command" ]; then
  abbruch "Im Ordner „$ZIEL“ liegen schon andere Dateien, aber kein Belegabruf. Bitte den Ordner umbenennen."
fi
if pgrep -f "$ZIEL/programm/" >/dev/null 2>&1; then
  abbruch "Belegabruf läuft gerade. Bitte erst beenden (Knopf „Beenden“ im Fenster), dann die Zeile noch einmal."
fi
UPDATE=0
if [ -e "$ZIEL/.belegabruf-version" ] || [ -e "$ZIEL/Belegabruf Mac.command" ]; then UPDATE=1; fi
mkdir -p "$ZIEL"
printf '%s\n' "$TAG" > "$QUELLE/.belegabruf-version"
# Die alte Fassung kommt kurz in einen eigenen Unterordner (gleiches Laufwerk, nur umbenannt)
# und wird erst nach dem erfolgreichen Einspielen gelöscht.
ALT="$ZIEL/.belegabruf-alt"
rm -rf "${ALT:?}"
mkdir "$ALT"
for eintrag in "${EIGENE[@]}"; do
  # Erst die alten Einträge beiseite (im Arbeitsordner), dann die neuen hinein. Geht etwas
  # schief, kommen die alten zurück.
  if [ -e "$ZIEL/$eintrag" ]; then mv "$ZIEL/$eintrag" "$ALT/"; fi
done
zurueck() {
  for eintrag in "${EIGENE[@]}"; do
    rm -rf "${ZIEL:?}/$eintrag"
    if [ -e "$ALT/$eintrag" ]; then mv "$ALT/$eintrag" "$ZIEL/"; fi
  done
  abbruch "Das Einspielen hat nicht geklappt; die bisherige Version ist wiederhergestellt."
}
for eintrag in "${EIGENE[@]}"; do
  if [ -e "$QUELLE/$eintrag" ]; then mv "$QUELLE/$eintrag" "$ZIEL/" || zurueck; fi
done
chmod +x "$ZIEL/Belegabruf Mac.command" "$ZIEL/Fehlersuche/"*.command 2>/dev/null || true
rm -rf "${ALT:?}"

if [ "$UPDATE" = 1 ]; then
  meldung "✓ Belegabruf ist auf $TAG aktualisiert: $ZIEL"
else
  meldung "✓ Belegabruf $TAG ist eingerichtet: $ZIEL"
fi
meldung "  Einstellungen und Anmeldungen bleiben im Datenordner (~/Library/Application Support/belegabruf)."
meldung "  Update später: dieselbe Zeile noch einmal ins Terminal."

# ── 4. Starten ───────────────────────────────────────────────────────────────
if [ "${BELEGABRUF_NICHT_STARTEN:-}" != "1" ]; then
  open "$ZIEL" || true
  open "$ZIEL/Belegabruf Mac.command" || meldung "Bitte „Belegabruf Mac“ im Ordner doppelklicken."
fi
