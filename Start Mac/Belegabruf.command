#!/bin/bash
# Belegabruf (macOS). Per Doppelklick starten.
# Richtet sich beim ersten Mal und nach einem Update selbst ein; jeder Schritt nur, wenn nötig:
# uv holen → Bausteine (uv sync) → Browser (Chromium) → Fenster „Belegabruf“ öffnen.
# Das eigentliche Programm liegt im Ordner "programm" daneben.
if ! cd "$(dirname "$0")/../programm" 2>/dev/null; then
  echo "Der Ordner „programm“ fehlt neben „Start Mac“. Bitte das ZIP vollständig auspacken (nicht nur den Start-Ordner)."
  read -r -p "Enter zum Schließen"
  exit 1
fi
export PATH="$HOME/.local/bin:$PATH"

abbruch() {
  echo "$1"
  read -r -p "Enter zum Schließen"
  exit 1
}

# a) Hilfsprogramm uv
if ! command -v uv >/dev/null 2>&1; then
  echo "Belegabruf wird eingerichtet. Das dauert beim ersten Mal ein paar Minuten."
  echo "Hole das Hilfsprogramm uv (von astral.sh) …"
  curl -LsSf https://astral.sh/uv/install.sh | sh || abbruch "uv konnte nicht installiert werden. Besteht eine Internetverbindung?"
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || abbruch "uv konnte nicht installiert werden. Besteht eine Internetverbindung?"
fi

# b) Python und Bausteine: fehlt die Umgebung, oder ist uv.lock neuer (Update)?
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -m belegabruf.startpruefung umgebung >/dev/null 2>&1; then
  echo "Richte die neue Version ein … (Python und die nötigen Bausteine)"
  if ! uv sync --locked --no-dev --quiet; then
    rm -rf .venv
    abbruch "Das hat nicht geklappt. Besteht eine Internetverbindung? Dann einfach noch einmal doppelklicken."
  fi
  touch .venv/.belegabruf-sync
fi

# c) Browser (Chromium, ohne Headless Shell): nur wenn er für diese Playwright-Version fehlt.
#    Die Prüfung liest nur eine Datei, sie startet Playwright nicht.
if ! .venv/bin/python -m belegabruf.startpruefung browser >/dev/null 2>&1; then
  echo "Hole den Browser (Chromium) …"
  uv run --no-dev --quiet playwright install --no-shell chromium \
    || abbruch "Der Browser konnte nicht geladen werden. Besteht eine Internetverbindung? Dann einfach noch einmal doppelklicken."
fi

# d) Fenster „Belegabruf“. Dieses Terminalfenster klein machen; es muss offen bleiben.
printf '\033[8;12;62t'
uv run --no-dev --quiet belege oberflaeche
