#!/bin/bash
# Belegabruf im Terminal (Menü wie bis Version 1.x, z. B. zur Fehlersuche) (macOS). Per Doppelklick starten.
# Das eigentliche Programm liegt im Ordner "programm" daneben.
cd "$(dirname "$0")/../programm" || exit 1
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "Belegabruf ist noch nicht eingerichtet. Bitte zuerst \"Einrichten\" in diesem Ordner doppelklicken."
  read -r -p "Enter zum Schließen"
  exit 1
fi

# Nach einem Update (neues ZIP ausgepackt) fehlt .venv: dann selbst einrichten.
# Einstellungen, Anmeldungen und Protokolle liegen im Benutzerordner und bleiben.
if [ ! -d .venv ]; then
  echo "Richte die neue Version ein … (einmalig, dauert einen Moment)"
  if ! uv sync --no-dev --quiet; then
    rm -rf .venv
    echo "Das hat nicht geklappt. Bitte \"Einrichten\" doppelklicken."
    read -r -p "Enter zum Schließen"
    exit 1
  fi
  if ! uv run --no-dev --quiet playwright install --no-shell chromium; then
    rm -rf .venv
    echo "Der Browser konnte nicht geladen werden. Bitte \"Einrichten\" doppelklicken."
    read -r -p "Enter zum Schließen"
    exit 1
  fi
fi

uv run --no-dev --quiet belege start
