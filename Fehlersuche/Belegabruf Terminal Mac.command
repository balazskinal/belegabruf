#!/bin/bash
# Belegabruf im Terminal (Menü wie bis Version 1.x, z. B. zur Fehlersuche) (macOS). Per Doppelklick starten.
# Das eigentliche Programm liegt im Ordner "programm" eine Ebene höher (neben "Fehlersuche").
if ! cd "$(dirname "$0")/../programm" 2>/dev/null; then
  echo "Der Ordner „programm“ fehlt neben „Fehlersuche“. Bitte das ZIP vollständig auspacken und"
  echo "den Starter im ausgepackten Ordner doppelklicken (nicht einzeln herausziehen)."
  read -r -p "Enter zum Schließen"
  exit 1
fi
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1 || [ ! -x .venv/bin/python ]; then
  echo "Belegabruf ist noch nicht eingerichtet. Bitte zuerst \"Belegabruf Mac\" doppelklicken (liegt oben im Ordner)."
  read -r -p "Enter zum Schließen"
  exit 1
fi

uv run --locked --no-dev --quiet belege start
