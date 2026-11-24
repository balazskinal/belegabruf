"""Belegabruf — Rechnungen aus eingeloggten Anbieter-Konten auf den eigenen Rechner holen."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("belegabruf")
except PackageNotFoundError:  # pragma: no cover - nur beim Arbeiten ohne Installation
    __version__ = "0.0.0"

GITHUB_REPO = "balazskinal/belegabruf"
