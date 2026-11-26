"""Einrichten mit einer Zeile (2.2.0): installieren.sh mit einem nachgebauten curl (kein Netz)
und Prüfungen an installieren.ps1 und release.yml.

Alle Releases sind erfunden; das ZIP wird im Test gebaut.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
SH = WURZEL / "installieren.sh"
PS1 = WURZEL / "installieren.ps1"
REPO = "https://github.com/balazskinal/belegabruf"
API = "https://api.github.com/repos/balazskinal/belegabruf/releases"

nur_mac = pytest.mark.skipif(sys.platform != "darwin", reason="installieren.sh ist für den Mac (plutil)")


def _zip(pfad: Path, tag: str) -> bytes:
    with zipfile.ZipFile(pfad, "w") as z:
        oben = f"belegabruf-{tag}/"
        z.writestr(oben + "Belegabruf Mac.command", "#!/bin/bash\necho start\n")
        z.writestr(oben + "Belegabruf Windows.cmd", "@echo off\r\n")
        z.writestr(oben + "programm/pyproject.toml", f'version = "{tag[1:]}"\n')
        z.writestr(oben + "Fehlersuche/Belegabruf Terminal Mac.command", "#!/bin/bash\n")
        z.writestr(oben + "Doku/README.md", "# Belegabruf\n")
    return pfad.read_bytes()


class Netz:
    """Was das falsche curl liefert: Adresse → Datei. Unbekannte Adressen: Fehler 22 wie curl -f."""

    def __init__(self, tmp_path: Path):
        self.ordner = tmp_path / "netz"
        self.ordner.mkdir()
        self.karte: dict[str, Path] = {}

    def datei(self, url: str, inhalt: bytes) -> None:
        ziel = self.ordner / f"{len(self.karte)}.bin"
        ziel.write_bytes(inhalt)
        self.karte[url] = ziel

    def release(self, tag: str, *, fester_name=False, digest=True, url=None, latest=False, sha_datei=False):
        name = "belegabruf.zip" if fester_name else f"belegabruf-{tag}.zip"
        zip_url = url or f"{REPO}/releases/download/{tag}/{name}"
        inhalt = _zip(self.ordner / f"{tag}.zip", tag)
        summe = hashlib.sha256(inhalt).hexdigest()
        asset = {"name": name, "browser_download_url": zip_url}
        if digest:
            asset["digest"] = f"sha256:{summe}"
        daten = json.dumps({"tag_name": tag, "assets": [{"name": "anderes.txt", "browser_download_url": "x"}, asset]})
        self.datei(f"{API}/latest" if latest else f"{API}/tags/{tag}", daten.encode())
        self.datei(zip_url, inhalt)
        if sha_datei:
            self.datei(zip_url + ".sha256", f"{summe}  belegabruf.zip\n".encode())
        return inhalt

    def curl(self, bin_ordner: Path) -> None:
        zeilen = "\n".join(f"{u}\t{p}" for u, p in self.karte.items())
        (self.ordner / "karte.txt").write_text(zeilen + "\n", encoding="utf-8")
        curl = bin_ordner / "curl"
        curl.write_text(
            "#!/bin/bash\n"
            'ziel=""; url=""\n'
            'while [ $# -gt 0 ]; do case "$1" in -o) ziel="$2"; shift 2;; -*) shift;; *) url="$1"; shift;; esac; done\n'
            f'echo "$url" >> "{self.ordner}/aufrufe.log"\n'
            f'quelle=$(awk -F"\\t" -v u="$url" \'$1==u {{print $2}}\' "{self.ordner}/karte.txt")\n'
            '[ -n "$quelle" ] || exit 22\n'
            'cp "$quelle" "$ziel"\n', encoding="utf-8")
        curl.chmod(0o755)

    def aufrufe(self) -> list[str]:
        log = self.ordner / "aufrufe.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def netz(tmp_path):
    return Netz(tmp_path)


def _starten(tmp_path, netz: Netz, version: str = "", ziel: Path | None = None):
    bin_ordner = tmp_path / "bin"
    bin_ordner.mkdir(exist_ok=True)
    netz.curl(bin_ordner)
    heim = tmp_path / "heim"
    heim.mkdir(exist_ok=True)
    umgebung = {"PATH": f"{bin_ordner}:/usr/bin:/bin:/usr/sbin", "HOME": str(heim), "TMPDIR": str(tmp_path),
                "BELEGABRUF_NICHT_STARTEN": "1"}
    if version:
        umgebung["BELEGABRUF_VERSION"] = version
    if ziel is not None:
        umgebung["BELEGABRUF_ZIEL"] = str(ziel)
    lauf = subprocess.run(["/bin/bash", str(SH)], capture_output=True, text=True, env=umgebung, timeout=60)
    return lauf, heim / "Applications" / "Belegabruf"


@nur_mac
def test_einrichten_dann_update_behaelt_eigenes(tmp_path, netz):
    netz.release("v2.0.1")
    lauf, ziel = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert "Prüfsumme stimmt" in lauf.stdout and "ist eingerichtet" in lauf.stdout
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.0.1"
    assert (ziel / "Belegabruf Mac.command").stat().st_mode & 0o111
    (ziel / "meine-notiz.txt").write_text("bleibt")
    (ziel / "programm" / "alt.txt").write_text("gehört zur alten Version")
    netz.release("v2.1.1")
    lauf, ziel = _starten(tmp_path, netz, "v2.1.1")
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert "aktualisiert" in lauf.stdout
    assert (ziel / "programm" / "pyproject.toml").read_text() == 'version = "2.1.1"\n'
    assert not (ziel / "programm" / "alt.txt").exists()  # Programmdateien ersetzt
    assert (ziel / "meine-notiz.txt").read_text() == "bleibt"  # Eigenes bleibt
    assert not (ziel / ".belegabruf-alt").exists()


@nur_mac
def test_neueste_version_mit_festem_namen_und_sha256_datei(tmp_path, netz):
    netz.release("v2.2.0", fester_name=True, digest=False, latest=True, sha_datei=True)
    lauf, ziel = _starten(tmp_path, netz)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.2.0"
    assert netz.aufrufe()[0] == f"{API}/latest"


@nur_mac
def test_ohne_api_feste_adresse_der_neuesten_version(tmp_path, netz):
    """GitHub-Liste nicht erreichbar: …/latest/download/belegabruf.zip mit .sha256."""
    inhalt = _zip(tmp_path / "x.zip", "v2.2.0")
    netz.datei(f"{REPO}/releases/latest/download/belegabruf.zip", inhalt)
    netz.datei(f"{REPO}/releases/latest/download/belegabruf.zip.sha256",
               f"{hashlib.sha256(inhalt).hexdigest()}  belegabruf.zip\n".encode())
    lauf, ziel = _starten(tmp_path, netz)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.2.0"


@nur_mac
def test_falsche_pruefsumme_nichts_geaendert(tmp_path, netz):
    netz.release("v2.0.1")
    _starten(tmp_path, netz, "v2.0.1")
    netz.release("v2.1.1")
    zip_url = f"{REPO}/releases/download/v2.1.1/belegabruf-v2.1.1.zip"
    netz.datei(zip_url, b"PK\x03\x04 untergeschoben")  # anderer Inhalt als die Prüfsumme sagt
    lauf, ziel = _starten(tmp_path, netz, "v2.1.1")
    assert lauf.returncode == 1 and "Prüfsumme des ZIPs stimmt nicht" in lauf.stderr
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.0.1"


@nur_mac
def test_ohne_pruefsumme_wird_nichts_installiert(tmp_path, netz):
    netz.release("v2.0.1", digest=False)
    lauf, ziel = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 1 and "keine Prüfsumme" in lauf.stderr and not ziel.exists()


@nur_mac
@pytest.mark.parametrize("url", [
    "https://andere.example/belegabruf-v2.0.1.zip",
    "http://github.com/balazskinal/belegabruf/releases/download/v2.0.1/belegabruf-v2.0.1.zip",
    "https://github.com/jemand/belegabruf/releases/download/v2.0.1/belegabruf-v2.0.1.zip",
    "https://raw.githubusercontent.com/balazskinal/belegabruf/main/belegabruf-v2.0.1.zip",
])
def test_fremde_download_adresse_abgelehnt(tmp_path, netz, url):
    netz.release("v2.0.1", url=url)
    lauf, ziel = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 1 and "Unerwartete Download-Adresse" in lauf.stderr
    assert url not in netz.aufrufe() and not ziel.exists()


@nur_mac
@pytest.mark.parametrize("version", ["2.0.1", "v2.0", "v2.0.1;rm", "../v2.0.1", "v2.0.1-rc1"])
def test_ungueltige_version(tmp_path, netz, version):
    lauf, _ = _starten(tmp_path, netz, version)
    assert lauf.returncode == 1 and "keine Versionsnummer" in lauf.stderr and netz.aufrufe() == []


@nur_mac
def test_fremder_ordner_wird_nicht_angefasst(tmp_path, netz):
    netz.release("v2.0.1")
    ziel = tmp_path / "heim" / "Applications" / "Belegabruf"
    ziel.mkdir(parents=True)
    (ziel / "Steuer 2025.pdf").write_text("wichtig")
    lauf, _ = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 1 and "liegen schon andere Dateien" in lauf.stderr
    assert sorted(p.name for p in ziel.iterdir()) == ["Steuer 2025.pdf"]


@nur_mac
def test_ziel_ausserhalb_des_benutzerordners_abgelehnt(tmp_path, netz):
    lauf, _ = _starten(tmp_path, netz, "v2.0.1", ziel=Path("/tmp/belegabruf-fremd"))
    assert lauf.returncode == 1 and "Benutzerordner" in lauf.stderr


def test_skripte_ohne_sudo_und_nur_github():
    import re

    sh = SH.read_text(encoding="utf-8")
    ps = PS1.read_text(encoding="utf-8")
    assert sh.startswith("#!/bin/bash") and "set -euo pipefail" in sh
    for text in (sh, ps):
        assert not re.search(r"^\s*sudo\b|[|;&]\s*sudo\b", text, re.M)
        assert "RunAs" not in text and "-Verb" not in text
        assert "raw.githubusercontent" not in text  # nur für den Testaufruf des Skripts selbst
    assert "--proto '=https' --proto-redir '=https'" in sh
    for text in (sh, ps):
        assert "api.github.com/repos/$repo/releases" in text.replace("$REPO", "$repo")
        assert "/releases/" in text and "Get-FileHash" in ps
    assert ps.count("Stop-Einrichtung") > 5 and "Expand-Archive" in ps


def test_release_baut_festes_zip_mit_pruefsumme_und_skripten():
    alles = (WURZEL / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "cp \"dist/$NAME.zip\" dist/belegabruf.zip" in alles and "sha256sum belegabruf.zip" in alles
    for asset in ("dist/belegabruf.zip", "dist/belegabruf.zip.sha256", "dist/installieren.sh", "dist/installieren.ps1"):
        assert asset in alles
    assert "releases/latest/download/installieren.sh | bash" in alles


def test_update_hinweis_nennt_die_zeile(monkeypatch):
    from belegabruf import aktualisierung

    monkeypatch.setattr(aktualisierung.sys, "platform", "darwin")
    assert aktualisierung.update_zeile() == f"curl -fsSL {REPO}/releases/latest/download/installieren.sh | bash"
    monkeypatch.setattr(aktualisierung.sys, "platform", "win32")
    assert aktualisierung.update_zeile() == f"irm {REPO}/releases/latest/download/installieren.ps1 | iex"
    assert "PowerShell" in aktualisierung.update_hinweis()


# ── Nachbesserung nach der Prüfung (M1, M2, N2–N4) ───────────────────────────


@nur_mac
def test_abgeschnittenes_skript_tut_nichts(tmp_path, netz):
    """M1: Bricht die Übertragung ab (curl | bash), läuft nichts halb: Alles steckt in main(),
    das erst die letzte Zeile aufruft. Danach läuft der vollständige Aufruf sauber durch."""
    netz.release("v2.0.1")
    zeilen = SH.read_text(encoding="utf-8").splitlines(keepends=True)
    for schnitt in (len(zeilen) // 3, len(zeilen) // 2, len(zeilen) - 2, len(zeilen) - 1):
        teil = tmp_path / "teil.sh"
        teil.write_text("".join(zeilen[:schnitt]), encoding="utf-8")
        bin_ordner = tmp_path / "bin"
        bin_ordner.mkdir(exist_ok=True)
        netz.curl(bin_ordner)
        heim = tmp_path / "heim"
        heim.mkdir(exist_ok=True)
        subprocess.run(["/bin/bash", str(teil)], capture_output=True, text=True, timeout=60,
                       env={"PATH": f"{bin_ordner}:/usr/bin:/bin:/usr/sbin", "HOME": str(heim),
                            "TMPDIR": str(tmp_path), "BELEGABRUF_VERSION": "v2.0.1", "BELEGABRUF_NICHT_STARTEN": "1"})
        assert not (heim / "Applications" / "Belegabruf").exists(), f"abgeschnitten nach Zeile {schnitt}: lief los"
        assert netz.aufrufe() == []
    lauf, ziel = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr


def _alter_stand(ziel: Path, tag: str = "v2.0.1") -> None:
    """Ein Update, das mittendrin abbrach: alte Fassung in .belegabruf-alt, die neue halb da."""
    alt = ziel / ".belegabruf-alt"
    (alt / "programm").mkdir(parents=True)
    (alt / "programm" / "pyproject.toml").write_text(f'version = "{tag[1:]}"\n')
    (alt / "Belegabruf Mac.command").write_text("#!/bin/bash\n")
    (alt / ".belegabruf-version").write_text(tag + "\n")
    (ziel / "Doku").mkdir()  # schon von der neuen Fassung eingespielt
    (ziel / "meine-notiz.txt").write_text("bleibt")


@nur_mac
def test_reste_eines_abgebrochenen_updates_werden_zurueckgespielt(tmp_path, netz):
    ziel = tmp_path / "heim" / "Applications" / "Belegabruf"
    _alter_stand(ziel)
    netz.release("v2.1.1")
    lauf, ziel = _starten(tmp_path, netz, "v2.1.1")
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert "nicht fertig" in lauf.stdout and "aktualisiert" in lauf.stdout  # als Belegabruf erkannt
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.1.1"
    assert not (ziel / ".belegabruf-alt").exists() and (ziel / "meine-notiz.txt").read_text() == "bleibt"


@nur_mac
def test_mv_scheitert_beim_beiseitelegen_alte_version_bleibt(tmp_path, netz):
    """M2: Scheitert ein mv beim Beiseitelegen, kommt alles zurück (und der Lauf meldet es)."""
    netz.release("v2.0.1")
    _starten(tmp_path, netz, "v2.0.1")
    netz.release("v2.1.1")
    falsch = tmp_path / "bin" / "mv"
    falsch.write_text('#!/bin/bash\ncase "$1|$2" in */Fehlersuche\\|*/.belegabruf-alt/) exit 1;; esac\n'
                      'exec /bin/mv "$@"\n', encoding="utf-8")
    falsch.chmod(0o755)
    lauf, ziel = _starten(tmp_path, netz, "v2.1.1")
    assert lauf.returncode == 1 and "wiederhergestellt" in lauf.stderr
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.0.1"
    assert (ziel / "programm" / "pyproject.toml").read_text() == 'version = "2.0.1"\n'
    assert not (ziel / ".belegabruf-alt").exists()
    falsch.unlink()
    lauf, ziel = _starten(tmp_path, netz, "v2.1.1")  # danach geht es ganz normal
    assert lauf.returncode == 0 and (ziel / ".belegabruf-version").read_text().strip() == "v2.1.1"


@nur_mac
def test_zielpfad_wird_normalisiert(tmp_path, netz):
    """N2: „..“ wird aufgelöst, bevor geprüft wird."""
    netz.release("v2.0.1")
    heim = tmp_path / "heim"
    lauf, _ = _starten(tmp_path, netz, "v2.0.1", ziel=Path(f"{heim}/Documents/../../ausserhalb"))
    assert lauf.returncode == 1 and "Benutzerordner" in lauf.stderr
    lauf, _ = _starten(tmp_path, netz, "v2.0.1", ziel=Path(f"{heim}/a/../Belegabruf"))
    assert lauf.returncode == 0 and (heim / "Belegabruf" / ".belegabruf-version").exists()


@nur_mac
def test_laufpruefung_nimmt_den_pfad_woertlich(tmp_path, netz):
    """N4: Ein Punkt im Ordnernamen ist kein Platzhalter — ein anderes Programm in einem
    ähnlich heißenden Ordner blockiert das Update nicht, das eigene schon."""
    netz.release("v2.0.1")
    heim = tmp_path / "heim"
    ziel = heim / "Bele.abruf"
    fremd = subprocess.Popen(["/bin/bash", "-c", f"exec -a '{heim}/BeleXabruf/programm/x' sleep 30"])
    try:
        lauf, _ = _starten(tmp_path, netz, "v2.0.1", ziel=ziel)
        assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    finally:
        fremd.kill()
    eigen = subprocess.Popen(["/bin/bash", "-c", f"exec -a '{ziel}/programm/.venv/bin/python' sleep 30"])
    try:
        lauf, _ = _starten(tmp_path, netz, "v2.0.1", ziel=ziel)
        assert lauf.returncode == 1 and "läuft gerade" in lauf.stderr
    finally:
        eigen.kill()


@nur_mac
def test_ohne_json_in_plutil_liest_javascript(tmp_path, netz):
    """N3: Kann plutil (älteres macOS) kein JSON, liest JavaScript für Automation die Antwort."""
    netz.release("v2.0.1")
    (tmp_path / "bin").mkdir(exist_ok=True)
    plutil = tmp_path / "bin" / "plutil"
    plutil.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    plutil.chmod(0o755)
    lauf, ziel = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert (ziel / ".belegabruf-version").read_text().strip() == "v2.0.1"


def test_installationsort_eine_konstante_je_skript():
    import re

    sh = SH.read_text(encoding="utf-8")
    ps = PS1.read_text(encoding="utf-8")
    assert sh.count('INSTALLATIONSORT="$HOME/Applications/Belegabruf"') == 1 and sh.count("$HOME/Applications/Belegabruf") == 1
    assert ps.count("'Programs\\Belegabruf'") == 1 and "$BelegabrufInstallationsort" in ps
    assert "GetFolderPath('LocalApplicationData')" in ps and "CreateShortcut" in ps and "'Belegabruf.lnk'" in ps
    assert sh.rstrip().endswith('main "$@"')
    assert "TrimEnd('\\') + '\\'" in ps  # Präfixvergleich mit Trenner
    assert "IndexOf($suche" in ps and not re.search(r"-like\s+\"\*\$ziel", ps)


@nur_mac
def test_programme_ordner_wird_angelegt_und_frueherer_ort_nur_erwaehnt(tmp_path, netz):
    """N1: Ziel ist ~/Applications/Belegabruf (angelegt, falls es ~/Applications nicht gibt).
    Eine frühere Installation in ~/Documents/Belegabruf bleibt unangetastet und wird erwähnt."""
    frueher = tmp_path / "heim" / "Documents" / "Belegabruf"
    (frueher / "programm").mkdir(parents=True)
    (frueher / ".belegabruf-version").write_text("v2.1.1\n")
    (frueher / "Belegabruf Mac.command").write_text("#!/bin/bash\n")
    vorher = sorted(str(p.relative_to(frueher)) for p in frueher.rglob("*"))
    netz.release("v2.0.1")
    lauf, ziel = _starten(tmp_path, netz, "v2.0.1")
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    assert ziel == tmp_path / "heim" / "Applications" / "Belegabruf" and (ziel / ".belegabruf-version").exists()
    assert "Spotlight" in lauf.stdout and "Programme" in lauf.stdout
    assert f"Eine frühere Installation liegt noch in {frueher}" in lauf.stdout
    assert sorted(str(p.relative_to(frueher)) for p in frueher.rglob("*")) == vorher
