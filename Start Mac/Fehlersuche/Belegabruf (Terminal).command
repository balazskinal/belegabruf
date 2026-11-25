#!/bin/bash
# Belegabruf im Terminal (Menü wie bis Version 1.x, z. B. zur Fehlersuche) (macOS). Per Doppelklick starten.
# Das eigentliche Programm liegt im Ordner "programm" zwei Ebenen höher.
cd "$(dirname "$0")/../../programm" || exit 1
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1 || [ ! -x .venv/bin/python ]; then
  echo "Belegabruf ist noch nicht eingerichtet. Bitte zuerst \"Belegabruf\" im Ordner \"Start Mac\" doppelklicken."
  read -r -p "Enter zum Schließen"
  exit 1
fi

uv run --no-dev --quiet belege start
