#!/bin/bash
# Belegabruf einrichten (macOS). Per Doppelklick starten.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"

echo "Belegabruf wird eingerichtet. Das dauert beim ersten Mal ein paar Minuten."
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "Hole das Hilfsprogramm uv (von astral.sh) …"
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "uv konnte nicht installiert werden. Besteht eine Internetverbindung?"; read -r -p "Enter zum Schließen"; exit 1; }
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "Hole Python und die nötigen Bausteine …"
uv sync --no-dev --quiet || { echo "Das hat nicht geklappt."; read -r -p "Enter zum Schließen"; exit 1; }

echo "Hole den Browser (Chromium) …"
uv run --no-dev playwright install chromium || { echo "Der Browser konnte nicht geladen werden."; read -r -p "Enter zum Schließen"; exit 1; }

uv run --no-dev belege einrichten
read -r -p "Fertig. Enter zum Schließen."
