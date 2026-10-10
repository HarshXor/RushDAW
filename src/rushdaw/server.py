"""Tiny standard-library HTTP server for the RushDAW web UI + API."""
import json
import mimetypes
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import __version__
from .export import available_formats, convert
from .storage import Storage, StorageError

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB (rendered WAV or project with embedded audio)

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

_PROJ = re.compile(r"^/api/projects/([0-9a-f]{32})(?:/(file|revisions|restore|rename|undelete))?$")


class Handler(SimpleHTTPRequestHandler):
    server_version = "RushDAW/" + __version__
    storage = None  # set by make_server

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=STATIC_DIR, **kw)

    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("RUSHDAW_DEBUG"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ----------------------------------------------------------- helpers
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_UPLOAD:
            raise StorageError("invalid body size", 400)
        return self.rfile.read(length)

    def _json_body(self):
        try:
            return json.loads(self._body() or b"{}")
        except ValueError:
            raise StorageError("invalid JSON body", 400)

    def _route(self, method):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        st = self.storage
        try:
            if u.path == "/api/projects":
                if method == "GET":
                    return self._json({"home": st.home, "projects": st.list_projects(deleted=q.get("deleted") == "1")})
                if method == "POST":
                    b = self._json_body()
                    return self._json(st.create_project(b.get("name"), b.get("bpm", 120), b.get("sig", 4)), 201)
            if u.path == "/api/projects/import" and method == "POST":
                return self._json(st.import_project(self._body(), q.get("name")), 201)
            m = _PROJ.match(u.path)
            if m:
                pid, sub = m.group(1), m.group(2)
                if sub is None and method == "GET":
                    return self._json(st.get_project(pid))
                if sub is None and method == "DELETE":
                    return self._json(st.delete_project(pid))
                if sub == "undelete" and method == "POST":
                    return self._json(st.restore_project(pid))
                if sub == "rename" and method == "POST":
                    return self._json(st.rename_project(pid, self._json_body().get("name")))
                if sub == "revisions" and method == "POST":
                    return self._json(st.save_revision(pid, self._body(), q.get("message", "")), 201)
                if sub == "restore" and method == "POST":
                    return self._json(st.restore_revision(pid, int(q.get("rev", "0"))), 201)
                if sub == "file" and method == "GET":
                    rev = int(q["rev"]) if q.get("rev") else None
                    data, r, p = st.read_revision(pid, rev)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Revision", str(r["number"]))
                    if q.get("download"):
                        fname = f"{p['name']}-rev{r['number']}.rushdaw"
                        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(fname)}")
                    self.end_headers()
                    self.wfile.write(data)
                    return None
            return self._json({"error": "not found"}, 404)
        except StorageError as e:
            return self._json({"error": str(e)}, e.status)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)

    # ----------------------------------------------------------- verbs
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/info":
            return self._json({"version": __version__, "formats": available_formats(), "home": self.storage.home})
        if path.startswith("/api/"):
            return self._route("GET")
        return super().do_GET()

    def do_DELETE(self):
        return self._route("DELETE")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/export":
            return self._route("POST")
        q = parse_qs(u.query)
        fmt = q.get("format", ["mp3"])[0]
        title = q.get("title", ["RushDAW"])[0]
        try:
            data = self._body()
        except StorageError as e:
            return self._json({"error": str(e)}, 400)
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


def make_server(host="127.0.0.1", port=8765, home=None):
    handler = type("RushDAWHandler", (Handler,), {"storage": Storage(home)})
    return ThreadingHTTPServer((host, port), handler)
