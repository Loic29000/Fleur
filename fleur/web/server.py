"""Serveur local de l'application d'analyse (http://127.0.0.1, jamais exposé
sur le réseau). Chaque appel d'API exige le jeton aléatoire de la session,
pour qu'aucun autre site ouvert dans le navigateur ne puisse l'interroger."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fleur.db import Database

log = logging.getLogger("fleur")
STATIC = Path(__file__).parent / "static"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class AnalysisApp:
    """Logique des routes, indépendante du transport HTTP (testable)."""

    def __init__(self, db_path: str | Path, cfg: dict, table_open=None):
        self.db_path = str(db_path)
        self.cfg = cfg
        # fonction qui dit si une table Winamax est ouverte (calculateur bloqué)
        self.table_open = table_open or (lambda: False)
        self._local = threading.local()
        self.routes = {}

    def db(self) -> Database:
        db = getattr(self._local, "db", None)
        if db is None:
            db = self._local.db = Database(self.db_path)
        return db

    def route(self, name: str):
        def deco(fn):
            self.routes[name] = fn
            return fn
        return deco

    def handle(self, method: str, path: str, query: dict[str, str], body: dict | None) -> tuple[str, object]:
        """Renvoie (type, contenu) : type 'json' ou 'text'."""
        from fleur.web import routes  # enregistre les routes à la première requête
        routes.install(self)
        key = f"{method} {path}"
        fn = self.routes.get(key)
        if fn is None:
            # routes avec identifiant : /api/hand/<id>
            for pattern, candidate in self.routes.items():
                if pattern.endswith("/*") and key.startswith(pattern[:-1]):
                    return candidate(self, key[len(pattern) - 1:], query, body)
            raise ApiError(HTTPStatus.NOT_FOUND, "route inconnue")
        return fn(self, None, query, body)


def make_handler(app: AnalysisApp, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Fleur"

        def log_message(self, fmt, *args):  # pas de bruit dans la console
            log.debug("web : " + fmt, *args)

        def _send(self, status: int, ctype: str, data: bytes, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, method: str) -> None:
            url = urlparse(self.path)
            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                html = (STATIC / "index.html").read_bytes()
                return self._send(200, "text/html; charset=utf-8", html)
            if not url.path.startswith("/api/"):
                return self._send(404, "text/plain; charset=utf-8", b"introuvable")
            if not secrets.compare_digest(query.pop("t", ""), token):
                return self._send(403, "text/plain; charset=utf-8", b"jeton invalide")
            body = None
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, "text/plain; charset=utf-8", b"JSON invalide")
            try:
                kind, content = app.handle(method, url.path, query, body)
            except ApiError as exc:
                data = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
                return self._send(exc.status, "application/json; charset=utf-8", data)
            except Exception as exc:  # ne jamais faire tomber le serveur
                log.exception("erreur de l'application d'analyse")
                data = json.dumps({"error": f"erreur interne : {exc}"}, ensure_ascii=False).encode()
                return self._send(500, "application/json; charset=utf-8", data)
            if kind == "text":
                name = query.get("nom", "main.txt")
                return self._send(200, "text/plain; charset=utf-8", content.encode("utf-8"),
                                  {"Content-Disposition": f'inline; filename="{name}"'})
            data = json.dumps(content, ensure_ascii=False, default=str).encode()
            self._send(200, "application/json; charset=utf-8", data)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


class AnalysisServer:
    def __init__(self, db_path: str | Path, cfg: dict, table_open=None, port: int = 0):
        self.app = AnalysisApp(db_path, cfg, table_open)
        self.token = secrets.token_urlsafe(18)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self.app, self.token))
        self.httpd.daemon_threads = True
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}/?t={self.token}"

    def start(self) -> "AnalysisServer":
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="fleur-web", daemon=True)
        self.thread.start()
        log.info("application d'analyse : %s", self.url.split("?")[0])
        return self

    def open(self, tab: str = "") -> None:
        webbrowser.open(self.url + (f"#{tab}" if tab else ""))

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
