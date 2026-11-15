"""Prototype frontend server: static files + same-origin proxy to the read-only API (no CORS needed).

Usage from the repository root (start the API from backend/ first):
    python frontend/serve.py                      # http://127.0.0.1:5173  → API http://127.0.0.1:8000
    python frontend/serve.py --api http://127.0.0.1:8010 --port 5174

Only the Python standard library is used. Routes:
    /api/<path>   → forwarded as GET to <API>/<path> (query string kept). Only GET is allowed.
    /i18n/<lang>.json → the panel's official translations (backend/src/flame_in_freefall/app/i18n).
    anything else → files under frontend/ (index.html for "/").
"""

from __future__ import annotations

import argparse
import mimetypes
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
I18N = HERE.parent / "backend" / "src" / "flame_in_freefall" / "app" / "i18n"
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def make_handler(api_base: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "fif-frontend/0.1"

        def log_message(self, fmt, *args):  # quieter console: only errors
            if args and str(args[1]).startswith(("4", "5")):
                super().log_message(fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("#", 1)[0]
            if path.startswith("/api/"):
                return self._proxy(path[4:])
            if path.startswith("/i18n/"):
                name = Path(path.split("?", 1)[0]).name
                f = I18N / name
                if f.suffix == ".json" and f.exists():
                    return self._send(200, f.read_bytes(), "application/json; charset=utf-8")
                return self._send(404, b"{}", "application/json")
            if path.split("?", 1)[0] == "/":  # IGNIS is the site; the old prototype stays at /index.html
                self.send_response(302)
                self.send_header("Location", "/ignis/")
                self.end_headers()
                return
            rel = path.split("?", 1)[0].lstrip("/") or "index.html"
            f = (HERE / rel).resolve()
            if f.is_dir() and HERE in f.parents and (f / "index.html").is_file():
                if not path.split("?", 1)[0].endswith("/"):  # /ignis → /ignis/ so relative URLs resolve
                    self.send_response(301)
                    self.send_header("Location", path.split("?", 1)[0] + "/")
                    self.end_headers()
                    return
                f = f / "index.html"
            if HERE not in f.parents and f != HERE or not f.is_file() or f.name == "serve.py":
                f = HERE / "index.html"  # single-page app: unknown paths fall back to the shell
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def _proxy(self, sub: str, body: bytes | None = None) -> None:
            try:
                req = urllib.request.Request(api_base.rstrip("/") + sub, data=body,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    self._send(r.status, r.read(), r.headers.get("Content-Type", "application/json"))
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get("Content-Type", "application/json"))
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                self._send(502, b'{"detail": "api_unreachable"}', "application/json")

        def do_POST(self) -> None:
            allowed = {"/api/search/semantic", "/api/search/hybrid", "/api/compare/investigations",
                       "/api/compare/experiments", "/api/analyze/investigation", "/api/analyze/comparison",
                       "/api/analyze/scenario", "/api/assistant/query", "/api/design/agent"}
            simulator = re.fullmatch(r"/api/design/simulators/[a-z0-9_]{1,64}", self.path)
            if self.path not in allowed and not simulator:
                return self._send(405, b'{"detail": "read-only"}', "application/json")
            if self.headers.get("Transfer-Encoding"):
                return self._send(400, b'{"detail": "content_length_required"}', "application/json")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send(400, b'{"detail": "invalid_content_length"}', "application/json")
            if not 0 < length <= 1024 * 1024:
                return self._send(413, b'{"detail": "body_too_large_or_empty"}', "application/json")
            self._proxy(self.path[4:], self.rfile.read(length))

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="Flame in Freefall prototype frontend")
    ap.add_argument("--api", default="http://127.0.0.1:8000", help="base URL of the running fif-app API")
    ap.add_argument("--port", type=int, default=5173)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.api))
    print(f"IGNIS: http://127.0.0.1:{a.port}  (API: {a.api})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
