"""Local web UI: `mousectl gui`."""
from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import config, daemon, protocol as P
from .hidraw import DeviceError

TOKEN = secrets.token_urlsafe(24)
_lock = threading.Lock()


def device() -> dict:
    try:
        path = P.find_config_node()
        return {"connected": True, "path": path, "report_rate": P.report_rate()}
    except DeviceError as e:
        return {"connected": False, "error": str(e)}


def meta() -> dict:
    return {
        "buttons": {k: v[1] for k, v in P.BUTTONS.items()},
        "mouse_actions": {k: v[1] for k, v in P.MOUSE_ACTIONS.items()},
        "media": {k: v[1] for k, v in P.MEDIA.items()},
        "keys": sorted(P.KEYS), "modifiers": sorted(P.MODIFIERS),
        "light_modes": P.LIGHT_MODES, "speed_max": P.SPEED_MAX, "brightness_max": P.BRIGHTNESS_MAX,
        "dpi": {"min": P.DPI_MIN, "max": P.DPI_MAX, "step": P.DPI_STEP, "stages": P.DPI_STAGES},
        "scroll": list(P.SCROLL),
    }


def live() -> dict:
    return {"device": device(), "daemon": daemon.read_status()}


def apply(cfg: dict, parts=None, save=True) -> dict:
    clean = P.validate(cfg)
    with _lock:
        try:
            with P.Mouse() as m:
                m.apply(clean, parts or ("lighting", "scroll", "fire", "buttons", "dpi"))
            applied = True
        except DeviceError:
            applied = False
    if save:
        config.save(clean)   # the daemon notices the change and re-applies after a re-plug
    return {"ok": True, "config": clean, "applied": applied}


class Handler(BaseHTTPRequestHandler):
    server_version = "mousectl"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode())

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        if self.path in ("/", "/index.html"):
            html = resources.files(__package__).joinpath("static/index.html").read_text("utf-8")
            return self._send(200, html.replace("__TOKEN__", TOKEN).encode(), "text/html; charset=utf-8")
        if self.headers.get("X-Token") != TOKEN:
            return self._send(403, b"forbidden", "text/plain")
        if self.path == "/api/state":
            return self._json(200, {"config": config.load(), "meta": meta(), **live()})
        if self.path == "/api/live":
            return self._json(200, live())
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Token") != TOKEN:
            return self._send(403, b"forbidden", "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > 1 << 20:
            return self._send(413, b"too large", "text/plain")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/apply":
                return self._json(200, apply(body["config"], body.get("parts"), bool(body.get("save", True))))
            self._send(404, b"not found", "text/plain")
        except (DeviceError, KeyError, ValueError, TypeError, OSError) as e:
            self._json(400, {"ok": False, "error": f"missing {e}" if isinstance(e, KeyError) else str(e)})


def serve(port=0, open_browser=True):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"mousectl GUI running at {url}  (Ctrl+C to quit)")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
