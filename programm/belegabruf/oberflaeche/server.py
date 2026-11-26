"""Der lokale Server der Bedienseite — nur für diesen Rechner, nur mit Schlüssel.

Sicherheitsregeln (ADR-005):

* lauscht nur auf ``127.0.0.1``, auf einem freien Port;
* ein Zufallsschlüssel (``secrets``) steht in der Adresse der Seite. Ohne ihn gibt es
  nichts: ``GET /`` braucht ihn als ``?k=``, jede ``/api/``-Anfrage im Kopf
  ``X-Belegabruf-Schluessel``;
* der ``Host``-Kopf muss genau ``127.0.0.1:<port>`` sein (schützt vor DNS-Rebinding);
* schreibende Anfragen nur per ``POST`` mit JSON und Schlüssel im Kopf; ein fremder
  ``Origin`` wird abgelehnt; es gibt **kein CORS** (keine ``Access-Control-*``-Köpfe);
* Antworten tragen strenge Sicherheitsköpfe (CSP, kein Caching, kein Referrer);
* Passwörter kommen nur herein (direkt in den Passwortspeicher) und nie zurück;
* der Server schreibt **nichts** ins Log.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlsplit

from belegabruf.oberflaeche.aktionen import Eingabefehler, Steuerung

KOPF_SCHLUESSEL = "X-Belegabruf-Schluessel"
HOECHSTENS_BYTES = 256 * 1024
#: So viel eines zu großen Rumpfs wird noch gelesen (und verworfen), bevor 413 kommt.
VERWERFEN_HOECHSTENS = 1024 * 1024


def _seite(nonce: str) -> bytes:
    text = resources.files("belegabruf.oberflaeche").joinpath("seite.html").read_text(encoding="utf-8")
    return text.replace("{{NONCE}}", nonce).encode("utf-8")


class Bedienserver(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, steuerung: Steuerung | None = None):
        self.schluessel = secrets.token_urlsafe(32)
        self.steuerung = steuerung or Steuerung()
        super().__init__(("127.0.0.1", 0), Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def adresse(self) -> str:
        return f"http://127.0.0.1:{self.port}/?k={self.schluessel}"

    def im_hintergrund(self) -> threading.Thread:
        faden = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        faden.start()
        return faden


class Handler(BaseHTTPRequestHandler):
    server: Bedienserver
    server_version = "Belegabruf"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # Nie etwas ins Log — in Adressen steht der Schlüssel.
    def log_message(self, format, *args):  # noqa: A002
        return

    def log_error(self, format, *args):  # noqa: A002
        return

    # ── Prüfungen ───────────────────────────────────────────────────────────

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.port}"

    def _schluessel_ok(self, wert: str | None) -> bool:
        return bool(wert) and hmac.compare_digest(str(wert).encode(), self.server.schluessel.encode())

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://127.0.0.1:{self.server.port}"

    # ── Antworten ───────────────────────────────────────────────────────────

    def _senden(self, status: int, rumpf: bytes, typ: str, nonce: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(rumpf)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        skript = f"'nonce-{nonce}'" if nonce else "'none'"
        self.send_header("Content-Security-Policy",
                         f"default-src 'none'; script-src {skript}; style-src {skript}; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; "
                         "frame-ancestors 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(rumpf)

    def _json(self, status: int, daten) -> None:
        self._senden(status, json.dumps(daten, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _verwerfen(self, laenge: int) -> None:
        """Liest höchstens ``laenge`` Bytes und verwirft sie — mit kurzer Frist, damit ein
        Absender, der weniger schickt als angekündigt, keinen Faden festhält."""
        rest = laenge
        vorher = self.connection.gettimeout()
        try:
            self.connection.settimeout(5)
            while rest > 0:
                stueck = self.rfile.read(min(rest, 64 * 1024))
                if not stueck:
                    break
                rest -= len(stueck)
        except OSError:
            pass  # Absender hat schon abgebrochen
        finally:
            try:
                self.connection.settimeout(vorher)  # die kurze Frist gilt nur hier
            except OSError:
                pass  # Verbindung schon zu

    def _verweigern(self, status: int = HTTPStatus.FORBIDDEN) -> None:
        self._senden(status, b"Nicht erlaubt.", "text/plain; charset=utf-8")

    # ── GET ────────────────────────────────────────────────────────────────

    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            return self._verweigern()
        teile = urlsplit(self.path)
        if teile.path == "/":
            schluessel = parse_qs(teile.query).get("k", [None])[0]
            if not self._schluessel_ok(schluessel):
                return self._verweigern()
            nonce = secrets.token_urlsafe(16)
            return self._senden(HTTPStatus.OK, _seite(nonce), "text/html; charset=utf-8", nonce=nonce)
        if not self._schluessel_ok(self.headers.get(KOPF_SCHLUESSEL)):
            return self._verweigern()
        st = self.server.steuerung
        if teile.path == "/api/zustand":
            return self._json(HTTPStatus.OK, st.zustand())
        if teile.path == "/api/auftrag":
            try:
                seit = int(parse_qs(teile.query).get("seit", ["0"])[0])
            except ValueError:
                seit = 0
            return self._json(HTTPStatus.OK, st.auftrag_stand(seit))
        return self._verweigern(HTTPStatus.NOT_FOUND)

    def do_HEAD(self):  # noqa: N802
        return self._verweigern(HTTPStatus.METHOD_NOT_ALLOWED)

    # ── POST ───────────────────────────────────────────────────────────────

    def do_POST(self):  # noqa: N802
        if not self._host_ok() or not self._origin_ok():
            return self._verweigern()
        if not self._schluessel_ok(self.headers.get(KOPF_SCHLUESSEL)):
            return self._verweigern()
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._verweigern(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        try:
            laenge = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._verweigern(HTTPStatus.BAD_REQUEST)
        if laenge < 0 or laenge > HOECHSTENS_BYTES:
            # Erst den Rumpf (bis zu einer Grenze) lesen und verwerfen, dann antworten und die
            # Verbindung schließen: Schlösse der Server mit ungelesenen Daten im Puffer, sähe der
            # Absender (je nach System, z. B. macOS) nur „Connection reset“ statt der Antwort 413.
            self._verwerfen(min(max(laenge, 0), VERWERFEN_HOECHSTENS))
            self.close_connection = True
            return self._verweigern(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            daten = json.loads(self.rfile.read(laenge).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json(HTTPStatus.BAD_REQUEST, {"fehler": "Ungültige Anfrage."})
        if not isinstance(daten, dict):
            return self._json(HTTPStatus.BAD_REQUEST, {"fehler": "Ungültige Anfrage."})

        st = self.server.steuerung
        pfad = urlsplit(self.path).path
        aktionen = {
            "/api/einstellungen": lambda: st.einstellungen_speichern(daten),
            "/api/mail-passwort": lambda: st.mail_passwort_setzen(daten),
            "/api/mail-passwort-loeschen": st.mail_passwort_loeschen,
            "/api/konto-holen": lambda: st.konto_holen_setzen(daten),
            "/api/mail-pruefen": st.mail_pruefen,
            "/api/pruefen": lambda: _auftrag(st.pruefen(daten)),
            "/api/anmelden": lambda: _auftrag(st.anmelden(daten)),
            "/api/holen": lambda: _auftrag(st.holen(daten)),
            "/api/beenden": lambda: _beenden(st),
        }
        if pfad not in aktionen:
            return self._verweigern(HTTPStatus.NOT_FOUND)
        try:
            return self._json(HTTPStatus.OK, aktionen[pfad]())
        except Eingabefehler as fehler:
            antwort = {"fehler": str(fehler)}
            if fehler.felder:
                antwort["felder"] = fehler.felder
            return self._json(HTTPStatus.BAD_REQUEST, antwort)
        except Exception as fehler:  # noqa: BLE001 - nie Einzelheiten (Pfade, Werte) nach außen
            return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                              {"fehler": f"Das hat nicht geklappt ({type(fehler).__name__})."})

    # Alles andere: nein, ohne CORS-Köpfe.
    def do_OPTIONS(self):  # noqa: N802
        return self._verweigern(HTTPStatus.METHOD_NOT_ALLOWED)

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS  # noqa: N815


def _auftrag(auftrag) -> dict:
    return {"gestartet": auftrag.art}


def _beenden(st: Steuerung) -> dict:
    st.beendet.set()
    return {"beendet": True, "wartet": st.beschaeftigt()}
