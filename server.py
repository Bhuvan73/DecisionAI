"""DecisionAI web server: stdlib HTTP server (no third-party web framework needed) + JSON API + static frontend."""
from __future__ import annotations

import json
import logging
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.api import ApiError, AppService
from src.config import ROOT, Settings

WEB = ROOT / "web"
log = logging.getLogger("decision_assistant")
MAX_BODY = 64 * 1024
CSP = ("default-src 'self'; img-src 'self' https: http: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def make_handler(app: AppService, web_root: Path = WEB):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DecisionAI"

        def log_message(self, fmt, *args):  # route access logs through logging (never prints secrets: no query secrets exist)
            log.debug("%s %s", self.address_string(), fmt % args)

        # ---- helpers
        def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError(413, "Request too large.")
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                raise ApiError(400, "Invalid JSON.")
            if not isinstance(data, dict):
                raise ApiError(400, "Invalid JSON.")
            return data

        def _guard(self, fn):
            try:
                self._json(200, fn())
            except ApiError as e:
                self._json(e.status, {"error": e.message, **e.extra})
            except Exception:  # never leak internals or secrets to the browser
                log.exception("unhandled error on %s", self.path)
                self._json(500, {"error": "Something went wrong on the server. Please try again."})

        # ---- routing
        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            routes = {"/api/health": app.health, "/api/trending": app.trending, "/api/stores": app.stores,
                      "/api/recent": lambda: {"items": app.db.recent()}, "/api/alerts": lambda: {"alerts": app.alerts()}}
            if u.path in routes:
                return self._guard(routes[u.path])
            m = re.fullmatch(r"/api/products/([^/]+)(?:/(offers|history))?", u.path)
            if m:
                pid, part = m.group(1), m.group(2)
                if part == "offers":
                    return self._guard(lambda: app.offers(pid))
                if part == "history":
                    return self._guard(lambda: app.history(pid, q.get("seller", "")))
                return self._guard(lambda: app.product(pid))
            if u.path.startswith("/api/"):
                return self._json(404, {"error": "Not found."})
            self._static(u.path)

        def do_POST(self):
            u = urlparse(self.path)
            routes = {"/api/search": app.search, "/api/chat": app.chat, "/api/compare": app.compare, "/api/alerts": app.create_alert}
            if u.path in routes:
                return self._guard(lambda: routes[u.path](self._body()))
            if u.path == "/api/alerts/check":
                return self._guard(app.check_alerts)
            self._json(404, {"error": "Not found."})

        def do_DELETE(self):
            m = re.fullmatch(r"/api/alerts/(\d+)", urlparse(self.path).path)
            if not m:
                return self._json(404, {"error": "Not found."})
            self._guard(lambda: {"deleted": app.db.delete_alert(int(m.group(1)))})

        def _static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (web_root / rel).resolve()
            if web_root.resolve() not in target.parents and target != web_root.resolve():
                return self._json(404, {"error": "Not found."})
            if not target.is_file():
                target = web_root / "index.html"  # SPA fallback (hash routes live client-side)
                if "." in Path(rel).name:
                    return self._json(404, {"error": "Not found."})
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8" if "charset" not in ctype else ""
            self._send(200, target.read_bytes(), ctype, "no-cache")

    return Handler


def start_alert_scheduler(app: AppService, minutes: float):
    """Optional: re-check alerts every N minutes. Only runs while this process runs; uses provider credits."""
    def loop():
        while True:
            time.sleep(minutes * 60)
            try:
                app.check_alerts()
            except Exception:
                log.exception("scheduled alert check failed")
    threading.Thread(target=loop, daemon=True, name="alert-scheduler").start()


def create_server(app: AppService, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(app))


def main():
    settings = Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("urllib3", "requests"):  # their DEBUG logs contain full request URLs (which include API keys)
        logging.getLogger(noisy).setLevel(logging.WARNING)
    app = AppService(settings)
    if settings.alert_check_minutes > 0 and settings.live_enabled:
        start_alert_scheduler(app, settings.alert_check_minutes)
    srv = create_server(app, settings.host, settings.port)
    mode = "SerpApi key loaded" if settings.serpapi_key else "NO SerpApi key (set SERPAPI_KEY in .env: searches will show a setup message)"
    print(f"\nDecisionAI running: http://{settings.host}:{settings.port}  |  {mode}  |  AI {'on' if settings.ai_enabled else 'off'}\nPress Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
