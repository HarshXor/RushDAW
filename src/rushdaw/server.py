"""Tiny standard-library HTTP server for the RushDAW web UI + API."""
import hmac
import json
import mimetypes
import os
import queue
import re
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import __version__
from .export import available_formats, convert
from .mcp import RushDAWMCP
from .storage import Storage, StorageError

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB (rendered WAV or project with embedded audio)

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

SSE_PATH = "/sse"
MESSAGES_PATH = "/messages"
SSE_KEEPALIVE = 15.0  # seconds between keep-alive comments

_PROJ = re.compile(r"^/api/projects/([0-9a-f]{32})(?:/(file|revisions|restore|rename|undelete))?$")


class Handler(SimpleHTTPRequestHandler):
    server_version = "RushDAW/" + __version__
    storage = None  # set by make_server
    mcp = None      # RushDAWMCP, set by make_server
    api_key = None  # bearer token required for MCP (None = MCP off)
    sse_sessions = None  # session_id -> queue of JSON-RPC responses
    sse_lock = None
    sse_stop = None      # threading.Event: closes all SSE streams on shutdown

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
        if path == SSE_PATH:
            return self._mcp_sse_stream()
        if path == "/api/info":
            return self._json({"version": __version__, "formats": available_formats(), "home": self.storage.home,
                               "mcp": {"enabled": bool(self.api_key), "transport": "sse", "sse": SSE_PATH, "messages": MESSAGES_PATH}})
        if path.startswith("/api/"):
            return self._route("GET")
        return super().do_GET()

    def do_DELETE(self):
        return self._route("DELETE")

    # ----------------------------------------------------------- MCP (HTTP + SSE transport)
    # GET  /sse                         -> event stream; first event "endpoint" = /messages?session_id=...
    # POST /messages?session_id=<id>    -> JSON-RPC message(s); answered with 202, responses go to the stream
    # Both require "Authorization: Bearer <api key>". Without --api-key MCP is off (404).
    def _drain_body(self):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            if 0 < n <= 1024 * 1024:
                self.rfile.read(n)
        except (ValueError, OSError):
            pass

    def _mcp_gate(self):
        """True when the request may use MCP; otherwise an error response was sent."""
        if not self.api_key:
            self._drain_body()
            self._json({"error": "MCP is off. Start the server with: rushdaw --api-key <KEY>"}, 404)
            return False
        auth = self.headers.get("Authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() == "bearer" and token.strip() and hmac.compare_digest(token.strip().encode(), self.api_key.encode()):
            return True
        self._drain_body()  # let the client read the 401 cleanly
        self.close_connection = True
        body = json.dumps({"error": "unauthorized: send 'Authorization: Bearer <api key>'"}).encode()
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Bearer realm="rushdaw-mcp"')
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def _sse_send(self, event, data):
        self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _mcp_sse_stream(self):
        if not self._mcp_gate():
            return None
        sid = uuid.uuid4().hex
        q = queue.Queue()
        with self.sse_lock:
            self.sse_sessions[sid] = q
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._sse_send("endpoint", f"{MESSAGES_PATH}?session_id={sid}")
            idle = 0.0
            while not self.sse_stop.is_set():
                try:
                    msg = q.get(timeout=0.5)
                except queue.Empty:
                    idle += 0.5
                    if idle >= SSE_KEEPALIVE:  # comment line keeps proxies / clients from timing out
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        idle = 0.0
                    continue
                if msg is None:  # session closed
                    break
                self._sse_send("message", json.dumps(msg, ensure_ascii=False))
                idle = 0.0
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client disconnected
        finally:
            with self.sse_lock:
                self.sse_sessions.pop(sid, None)
        return None

    def _mcp_message(self, query):
        if not self._mcp_gate():
            return None
        sid = query.get("session_id", "")
        with self.sse_lock:
            q = self.sse_sessions.get(sid)
        if q is None:
            self._drain_body()
            return self._json({"error": "unknown or expired session_id – open GET /sse first"}, 404)
        try:
            msg = json.loads(self._body())
        except StorageError:
            return self._json({"error": "empty body"}, 400)
        except ValueError:
            q.put({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return self._json({"error": "parse error"}, 400)
        for m in (msg if isinstance(msg, list) else [msg]):
            r = self.mcp.handle(m)
            if r is not None:
                q.put(r)
        body = b"Accepted"
        self.send_response(202)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == MESSAGES_PATH:
            return self._mcp_message({k: v[0] for k, v in parse_qs(u.query).items()})
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


def make_server(host="127.0.0.1", port=8765, home=None, api_key=None):
    storage = Storage(home)
    stop = threading.Event()
    handler = type("RushDAWHandler", (Handler,), {"storage": storage, "mcp": RushDAWMCP(storage), "api_key": api_key or None,
                                                  "sse_sessions": {}, "sse_lock": threading.Lock(), "sse_stop": stop})
    httpd = RushDAWServer((host, port), handler)
    httpd.sse_stop = stop
    return httpd


class RushDAWServer(ThreadingHTTPServer):
    daemon_threads = True
    sse_stop = None  # set by make_server(); may still be None if binding the port failed inside __init__

    def _stop_sse(self):
        if self.sse_stop is not None:
            self.sse_stop.set()  # end open SSE streams so their threads exit

    def shutdown(self):
        self._stop_sse()
        super().shutdown()

    def server_close(self):
        self._stop_sse()
        super().server_close()
