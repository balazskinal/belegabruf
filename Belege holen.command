#!/bin/bash
# Belege holen (macOS). Per Doppelklick starten.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1 || [ ! -d .venv ]; then
  echo "Belegabruf ist noch nicht eingerichtet. Bitte zuerst \"Einrichten\" doppelklicken."
  read -r -p "Enter zum Schließen"
  exit 1
fi

uv run --no-dev --quiet belege start
