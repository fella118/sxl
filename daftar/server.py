"""Demo web server: a simulated WhatsApp phone per client plus the owner's dashboard.

Standard library only. For a real deployment, put the WhatsApp Cloud API webhook
in front of Service.receive() and pass a `send` hook that calls the API.
"""

import base64
import binascii
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import anthropic

from . import seed
from .agent import Assistant
from .service import Service
from .store import Store

STATIC = Path(__file__).parent / "static"
MAX_BODY = 25 * 1024 * 1024


class App:
    def __init__(self, db_path: Path, files_dir: Path, llm=None):
        self.db_path, self.files_dir = Path(db_path), Path(files_dir)
        self.llm = llm
        self.lock = threading.Lock()
        self._open(fresh=not self.db_path.exists())

    def _open(self, fresh: bool) -> None:
        self.store = Store(self.db_path)
        if fresh:
            seed.seed(self.store)
        if self.llm is None:
            self.llm = anthropic.Anthropic()
        assistant = Assistant(self.store, self.llm, seed.FIRM, seed.DEADLINE_DAY)
        self.service = Service(self.store, assistant, firm=seed.FIRM, deadline_day=seed.DEADLINE_DAY,
                               files_dir=self.files_dir)

    def reset(self) -> None:
        self.store.db.close()
        self.db_path.unlink(missing_ok=True)
        for f in sorted(self.files_dir.rglob("*"), reverse=True):
            f.unlink() if f.is_file() else f.rmdir()
        self._open(fresh=True)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        # --- helpers -------------------------------------------------------
        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("requête trop lourde")
            return json.loads(self.rfile.read(length) or b"{}")

        # --- routes --------------------------------------------------------
        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                data = (STATIC / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif url.path == "/api/state":
                with app.lock:
                    self._json(app.service.report())
            elif url.path == "/api/messages":
                code = parse_qs(url.query).get("client", [""])[0]
                with app.lock:
                    self._json(app.store.messages(code))
            elif url.path.startswith("/api/file/"):
                self._file(url.path.rsplit("/", 1)[-1])
            else:
                self._json({"error": "introuvable"}, 404)

        def _file(self, raw_id: str):
            if not raw_id.isdigit():
                return self._json({"error": "introuvable"}, 404)
            with app.lock:
                f = app.store.file(int(raw_id))
            path = Path(f["path"]).resolve() if f else None
            if not path or app.files_dir.resolve() not in path.parents or not path.is_file():
                return self._json({"error": "introuvable"}, 404)
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f["mime"] or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
                with app.lock:
                    if path == "/api/kickoff":
                        return self._json({"sent": app.service.kickoff()})
                    if path == "/api/advance-day":
                        return self._json({"sent": app.service.advance_day(), "today": app.store.today.isoformat()})
                    if path == "/api/reset":
                        app.reset()
                        return self._json({"ok": True})
                    if path == "/api/resolve-flag":
                        app.store.resolve_flag(int(body["id"]))
                        return self._json({"ok": True})
                    if path == "/api/message":
                        files = [(f["name"], f["mime"], base64.b64decode(f["data"], validate=True))
                                 for f in body.get("files", [])]
                        reply = app.service.receive(body["client"], body.get("text", ""), files)
                        return self._json({"reply": reply})
                return self._json({"error": "introuvable"}, 404)
            except (KeyError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 400)
            except anthropic.AuthenticationError:
                return self._json({"error": "Clé API Claude invalide ou manquante (ANTHROPIC_API_KEY)."}, 502)
            except TypeError as exc:
                if "authentication" not in str(exc):
                    raise
                return self._json({"error": "Clé API Claude manquante : définissez ANTHROPIC_API_KEY."}, 502)
            except anthropic.APIConnectionError:
                return self._json({"error": "Impossible de joindre l'API Claude."}, 502)
            except anthropic.APIStatusError as exc:
                return self._json({"error": f"Erreur API Claude ({exc.status_code}) : {exc.message}"}, 502)

    return Handler


def serve(db_path: Path, files_dir: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    app = App(db_path, files_dir)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Daftar demo on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
