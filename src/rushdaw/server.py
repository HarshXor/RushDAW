"""Tiny standard-library HTTP server for the RushDAW web UI + export API."""
import json
import mimetypes
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .export import available_formats, convert

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB rendered WAV

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Handler(SimpleHTTPRequestHandler):
    server_version = "RushDAW/" + __version__

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=STATIC_DIR, **kw)

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("RUSHDAW_DEBUG"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/info":
            return self._json({"version": __version__, "formats": available_formats()})
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/export":
            return self._json({"error": "not found"}, 404)
        q = parse_qs(u.query)
        fmt = q.get("format", ["mp3"])[0]
        title = q.get("title", ["RushDAW"])[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_UPLOAD:
            return self._json({"error": "invalid body size"}, 400)
        data = self.rfile.read(length)
        if data[:4] != b"RIFF":
            return self._json({"error": "body must be a WAV file"}, 400)
        try:
            out, ext, mime = convert(data, fmt, title)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # ffmpeg failure
            return self._json({"error": str(e)}, 500)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Content-Disposition", f'attachment; filename="export.{ext}"')
        self.end_headers()
        self.wfile.write(out)


def make_server(host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), Handler)
