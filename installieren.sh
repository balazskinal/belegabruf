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
#   3. in den Installationsordner (INSTALLATIONSORT unten: ~/Applications/Belegabruf, im Finder
#      „Programme“ im Benutzerordner — ohne Rückfrage zu „Dokumente“ und ohne iCloud) auspacken. Bei einem Update werden nur
#      die eigenen Programmdateien ersetzt; was du selbst in den Ordner gelegt hast, bleibt.
#      Einstellungen, Anmeldungen und Protokolle liegen im Datenordner
#      (~/Library/Application Support/belegabruf) und werden nicht angefasst,
#   4. „Belegabruf Mac“ starten und den Ordner im Finder zeigen.
# Kein sudo, keine Änderungen außerhalb des Installationsordners (und eines Arbeitsordners in /tmp).
#
# Warum so: Was curl lädt, bekommt von macOS keine Quarantäne — so erscheint die Meldung
# „Apple konnte nicht überprüfen …“ nicht, die bei einem im Browser geladenen ZIP kommt.
#
# Das ganze Skript steckt in main() und läuft erst mit der letzten Zeile los: Bricht die
# Übertragung (curl | bash) mittendrin ab, wird nichts halb ausgeführt.

set -euo pipefail

# Der Installationsordner — die einzige Stelle dafür. ~/Applications zeigt der Finder als
# „Programme“ im Benutzerordner; es braucht keinen Zugriff auf „Dokumente“ und liegt nicht in iCloud.
INSTALLATIONSORT="$HOME/Applications/Belegabruf"
# Bewusst kein Blick in ~/Documents o. Ä.: Schon der Zugriff löst auf dem Mac die Rückfrage
# „Terminal möchte auf Dokumente zugreifen“ aus.

REPO="balazskinal/belegabruf"
API="https://api.github.com/repos/$REPO/releases"
DOWNLOADS="https://github.com/$REPO/releases/"
# Nur diese Einträge gehören dem Programm; nur sie werden bei einem Update ersetzt.
EIGENE=("Belegabruf Mac.command" "Belegabruf Windows.cmd" "programm" "Fehlersuche" "Doku" ".belegabruf-version")
ALT_NAME=".belegabruf-alt"

meldung() { printf '%s\n' "$*"; }

abbruch() {
  printf '\n✗ %s\n' "$*" >&2
  printf 'Bei Fragen: https://github.com/%s\n' "$REPO" >&2
  exit 1
}

normalisieren() {  # Pfad ohne „.“ und „..“ (rein textlich, der Ordner muss nicht existieren)
  local teil teile=() ergebnis=() IFS=/
  read -r -a teile <<< "$1"  # ohne Platzhalter-Auflösung (kein Globbing)
  [ ${#teile[@]} -gt 0 ] || { printf '/'; return 0; }
  for teil in "${teile[@]}"; do
    case "$teil" in
      ""|.) ;;
      ..) if [ ${#ergebnis[@]} -gt 0 ]; then unset 'ergebnis[${#ergebnis[@]}-1]'; fi ;;
      *) ergebnis+=("$teil") ;;
    esac
  done
  if [ ${#ergebnis[@]} -eq 0 ]; then printf '/'; else printf '/%s' "${ergebnis[*]}"; fi
}

regex_wortlich() {  # Text als wörtliches Muster für pgrep (keine Sonderzeichen)
  printf '%s' "$1" | sed 's/[][\\.^$*+?(){}|/]/\\&/g'
}

laden() {  # laden <Adresse> <Datei> — nur https, auch bei Weiterleitungen
  curl -fsSL --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 20 -o "$2" "$1"
}

adresse_erlaubt() {  # Nur Downloads dieses Repos bei GitHub.
  case "$1" in
    "${DOWNLOADS}download/"*|"${DOWNLOADS}latest/download/"*) return 0 ;;
    *) return 1 ;;
  esac
}

feld() {  # feld <JSON-Datei> <Schlüsselpfad wie assets.0.name> — leer, wenn es das Feld nicht gibt
  local wert
  if wert="$(plutil -extract "$2" raw -o - "$1" 2>/dev/null)"; then
    printf '%s' "$wert"
    return 0
  fi
  # Älteres macOS ohne JSON in plutil: JavaScript für Automation (seit macOS 10.10 dabei).
  osascript -l JavaScript - "$1" "$2" 2>/dev/null <<'JS' || true
function run(argv) {
  ObjC.import('Foundation');
  var text = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null).js;
  var wert = JSON.parse(text);
  var teile = argv[1].split('.');
  for (var i = 0; i < teile.length; i++) {
    if (wert === null || wert === undefined) return '';
    wert = wert[teile[i]];
  }
  return (wert === null || wert === undefined || typeof wert === 'object') ? '' : String(wert);
}
JS
}

ist_belegabruf() {  # ist_belegabruf <Ordner>
  [ -e "$1/.belegabruf-version" ] || [ -e "$1/Belegabruf Mac.command" ] || [ -d "$1/$ALT_NAME" ]
}

reste_zurueckspielen() {  # Ein abgebrochenes Update zurücknehmen: die alte Fassung gilt.
  local ziel="$1" alt="$1/$ALT_NAME" eintrag
  [ -d "$alt" ] || return 0
  meldung "Ein früheres Update wurde nicht fertig — stelle die bisherige Version wieder her …"
  for eintrag in "${EIGENE[@]}"; do
    if [ -e "$alt/$eintrag" ]; then
      rm -rf "${ziel:?}/$eintrag"
      mv "$alt/$eintrag" "$ziel/" || abbruch "Die bisherige Version ließ sich nicht wiederherstellen (siehe $alt)."
    fi
  done
  rmdir "$alt" 2>/dev/null || abbruch "Im Ordner $alt liegen unerwartete Dateien — bitte nachsehen."
}

main() {
  local ziel version
  ziel="$(normalisieren "${BELEGABRUF_ZIEL:-$INSTALLATIONSORT}")"
  version="${BELEGABRUF_VERSION:-}"

  [ "$(uname -s)" = "Darwin" ] || abbruch "Dieses Skript ist für den Mac. Unter Windows: siehe README (PowerShell-Zeile)."
  local werkzeug
  for werkzeug in curl unzip shasum plutil osascript; do
    command -v "$werkzeug" >/dev/null 2>&1 || abbruch "Das Programm „$werkzeug“ fehlt auf diesem Mac."
  done
  if [ -n "$version" ] && ! [[ "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    abbruch "BELEGABRUF_VERSION=„$version“ ist keine Versionsnummer wie v2.1.1."
  fi
  case "$ziel" in
    "$HOME"/?*) ;;
    *) abbruch "Der Installationsordner muss in deinem Benutzerordner liegen (nicht: $ziel)." ;;
  esac

  ARBEIT="$(mktemp -d "${TMPDIR:-/tmp}/belegabruf-einrichten.XXXXXX")"
  trap 'rm -rf "$ARBEIT"' EXIT

  # ── 1. Welche Version, welches ZIP, welche Prüfsumme? ───────────────────────
  meldung "Belegabruf einrichten …"
  local release_url tag="" zip_url="" erwartet="" gesucht name digest i
  if [ -n "$version" ]; then release_url="$API/tags/$version"; else release_url="$API/latest"; fi
  if laden "$release_url" "$ARBEIT/release.json" 2>/dev/null; then
    tag="$(feld "$ARBEIT/release.json" tag_name)"
    [ -n "$tag" ] || abbruch "Die Antwort von GitHub ließ sich nicht lesen (keine Version darin)."
    # Bevorzugt das ZIP mit festem Namen (ab 2.2.0), sonst das versionierte (ältere Versionen).
    for gesucht in "belegabruf.zip" "belegabruf-$tag.zip"; do
      i=0
      while name="$(feld "$ARBEIT/release.json" "assets.$i.name")" && [ -n "$name" ]; do
        if [ "$name" = "$gesucht" ]; then
          zip_url="$(feld "$ARBEIT/release.json" "assets.$i.browser_download_url")"
          digest="$(feld "$ARBEIT/release.json" "assets.$i.digest")"
          case "$digest" in sha256:*) erwartet="${digest#sha256:}" ;; esac
          break 2
        fi
        i=$((i + 1))
      done
    done
    [ -n "$zip_url" ] || abbruch "In der Version $tag gibt es kein ZIP zum Herunterladen."
  elif [ -z "$version" ]; then
    # GitHub-Liste nicht erreichbar (z. B. zu viele Abfragen): feste Adresse der neuesten Version.
    zip_url="${DOWNLOADS}latest/download/belegabruf.zip"
  else
    abbruch "Die Version $version gibt es bei GitHub nicht (oder GitHub ist nicht erreichbar)."
  fi
  adresse_erlaubt "$zip_url" || abbruch "Unerwartete Download-Adresse — aus Sicherheitsgründen abgebrochen."

  if [ -z "$erwartet" ] && [ "$(basename "$zip_url")" = "belegabruf.zip" ]; then
    # Ohne Prüfsumme in der GitHub-Liste: die mitveröffentlichte Datei belegabruf.zip.sha256.
    if laden "$zip_url.sha256" "$ARBEIT/zip.sha256" 2>/dev/null; then
      erwartet="$(awk '{print $1; exit}' "$ARBEIT/zip.sha256")"
    fi
  fi
  [[ "$erwartet" =~ ^[0-9a-f]{64}$ ]] || abbruch "Für diese Version gibt es keine Prüfsumme — ungeprüft wird nichts installiert."

  # ── 2. Laden und prüfen ────────────────────────────────────────────────────
  meldung "Lade ${tag:-die neueste Version} von GitHub …"
  laden "$zip_url" "$ARBEIT/belegabruf.zip" || abbruch "Das Herunterladen hat nicht geklappt. Besteht eine Internetverbindung?"
  local ist
  ist="$(shasum -a 256 "$ARBEIT/belegabruf.zip" | awk '{print $1}')"
  [ "$ist" = "$erwartet" ] || abbruch "Die Prüfsumme des ZIPs stimmt nicht. Die Datei ist beschädigt oder nicht die echte — nicht installiert."
  meldung "✓ Prüfsumme stimmt."

  mkdir "$ARBEIT/aus"
  unzip -q "$ARBEIT/belegabruf.zip" -d "$ARBEIT/aus" || abbruch "Das ZIP ließ sich nicht auspacken."
  local quelle
  quelle="$(find "$ARBEIT/aus" -mindepth 1 -maxdepth 1 -type d -name 'belegabruf-v*' | head -n 1)"
  [ -n "$quelle" ] && [ -f "$quelle/Belegabruf Mac.command" ] && [ -d "$quelle/programm" ] \
    || abbruch "Das ZIP hat nicht den erwarteten Inhalt."
  [ -n "$tag" ] || tag="$(basename "$quelle" | sed 's/^belegabruf-//')"

  # ── 3. Einspielen: nur die eigenen Einträge ersetzen ───────────────────────
  if [ -e "$ziel" ] && [ ! -d "$ziel" ]; then abbruch "„$ziel“ ist eine Datei, kein Ordner."; fi
  if [ -d "$ziel" ] && [ -n "$(ls -A "$ziel")" ] && ! ist_belegabruf "$ziel"; then
    abbruch "Im Ordner „$ziel“ liegen schon andere Dateien, aber kein Belegabruf. Bitte den Ordner umbenennen."
  fi
  if pgrep -f "$(regex_wortlich "$ziel/programm/")" >/dev/null 2>&1; then
    abbruch "Belegabruf läuft gerade. Bitte erst beenden (Knopf „Beenden“ im Fenster), dann die Zeile noch einmal."
  fi
  local update=0
  if ist_belegabruf "$ziel"; then update=1; fi
  mkdir -p "$ziel"
  reste_zurueckspielen "$ziel"
  printf '%s\n' "$tag" > "$quelle/.belegabruf-version"

  # Die alte Fassung kommt kurz in einen eigenen Unterordner (gleiches Laufwerk, nur umbenannt)
  # und wird erst nach dem erfolgreichen Einspielen gelöscht. Scheitert ein Schritt — oder
  # bricht das Skript ab —, spielt zurueck() bzw. der nächste Aufruf sie zurück.
  local alt="$ziel/$ALT_NAME" eintrag
  mkdir "$alt"
  zurueck() {
    reste_zurueckspielen "$ziel"
    abbruch "Das Einspielen hat nicht geklappt; die bisherige Version ist wiederhergestellt."
  }
  for eintrag in "${EIGENE[@]}"; do
    if [ -e "$ziel/$eintrag" ]; then mv "$ziel/$eintrag" "$alt/" || zurueck; fi
  done
  for eintrag in "${EIGENE[@]}"; do
    if [ -e "$quelle/$eintrag" ]; then mv "$quelle/$eintrag" "$ziel/" || zurueck; fi
  done
  chmod +x "$ziel/Belegabruf Mac.command" "$ziel/Fehlersuche/"*.command 2>/dev/null || true
  rm -rf "${alt:?}"

  if [ "$update" = 1 ]; then
    meldung "✓ Belegabruf ist auf $tag aktualisiert: $ziel"
  else
    meldung "✓ Belegabruf $tag ist eingerichtet: $ziel"
  fi
  meldung "  Starten künftig: Spotlight (⌘ + Leertaste) „Belegabruf“ — oder im Finder unter"
  meldung "  Benutzerordner → Programme → Belegabruf → „Belegabruf Mac“."
  meldung "  Hast du Belegabruf bisher aus einem ZIP-Ordner gestartet, kannst du diesen löschen."
  meldung "  Einstellungen und Anmeldungen liegen im Datenordner und bleiben."
  meldung "  Update später: dieselbe Zeile noch einmal ins Terminal."

  # ── 4. Starten ─────────────────────────────────────────────────────────────
  if [ "${BELEGABRUF_NICHT_STARTEN:-}" != "1" ]; then
    open "$ziel" || true
    open "$ziel/Belegabruf Mac.command" || meldung "Bitte „Belegabruf Mac“ im Ordner doppelklicken."
  fi
}

main "$@"
