"""Schnelle Prüfung für den Starter „Belegabruf“ — ohne Playwright zu starten.

    python -m belegabruf.startpruefung umgebung   Exit 0: Bausteine passen zu uv.lock
    python -m belegabruf.startpruefung browser    Exit 0: Chromium für dieses Playwright ist da

Exit 1 heißt jeweils: nachholen (``uv sync`` bzw. ``playwright install``). Bei Zweifeln
lieber 1: Beides ist harmlos, wenn schon alles da ist, es dauert nur etwas länger.
"""

from __future__ import annotations

import json
import os
import sys
from importlib.util import find_spec
from pathlib import Path

#: Legt der Starter nach jedem erfolgreichen ``uv sync`` an (bzw. frischt es auf).
MERKER = ".belegabruf-sync"


def umgebung_aktuell(programm: Path) -> bool:
    """Ist die .venv jünger als uv.lock und pyproject.toml (seit dem letzten Sync)?"""
    merker = programm / ".venv" / MERKER
    if not merker.exists():
        return False
    stand = merker.stat().st_mtime
    return all(not (programm / d).exists() or (programm / d).stat().st_mtime <= stand
               for d in ("uv.lock", "pyproject.toml"))


def browserordner() -> Path:
    """Wo Playwright die Browser ablegt (wie Playwright selbst es bestimmt)."""
    eigen = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if eigen and eigen != "0":
        return Path(eigen).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"


def chromium_revision() -> str | None:
    """Die Chromium-Version, die dieses Playwright erwartet (aus seiner browsers.json)."""
    spec = find_spec("playwright")
    if spec is None or not spec.origin:
        return None
    datei = Path(spec.origin).parent / "driver" / "package" / "browsers.json"
    try:
        eintraege = json.loads(datei.read_text(encoding="utf-8"))["browsers"]
    except (OSError, ValueError, KeyError):
        return None
    for e in eintraege:
        if e.get("name") == "chromium":
            if e.get("revisionOverrides"):
                return None  # je nach System anders — dann lieber installieren lassen
            return str(e.get("revision") or "") or None
    return None


def chromium_da() -> bool:
    revision = chromium_revision()
    if revision is None or os.environ.get("PLAYWRIGHT_BROWSERS_PATH") == "0":
        return False
    return (browserordner() / f"chromium-{revision}" / "INSTALLATION_COMPLETE").exists()


def main(argv: list[str] | None = None) -> int:
    was = (argv if argv is not None else sys.argv[1:] or [""])[0]
    if was == "umgebung":
        return 0 if umgebung_aktuell(Path.cwd()) else 1
    if was == "browser":
        return 0 if chromium_da() else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
