#!/bin/bash
# Belege holen — Bedienseite im Browserfenster (macOS). Per Doppelklick starten.
# Das eigentliche Programm liegt im Ordner "programm" daneben.
cd "$(dirname "$0")/../programm" || exit 1
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1 || [ ! -d .venv ]; then
  echo "Belegabruf ist noch nicht eingerichtet. Bitte zuerst \"Einrichten\" in diesem Ordner doppelklicken."
  read -r -p "Enter zum Schließen"
  exit 1
fi

# Dieses Terminalfenster klein machen; es muss offen bleiben, solange Belegabruf läuft.
printf '\033[8;12;62t'
uv run --no-dev --quiet belege oberflaeche
