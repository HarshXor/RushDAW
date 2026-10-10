"""Command line entry point: ``rushdaw`` / ``python -m rushdaw``."""
import argparse
import errno
import json
import os
import sys
import urllib.request
import threading
import webbrowser

from . import __version__
from .server import make_server

DEFAULT_PORT = 8765
PORT_TRIES = 20  # when the default port is busy, try 8766, 8767, ...


def _url(host, port):
    return f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"


def _running_rushdaw(host, port):
    """Return /api/info of a RushDAW server already listening on host:port, else None."""
    h = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with urllib.request.urlopen(f"http://{h}:{port}/api/info", timeout=1.5) as r:
            if not r.headers.get("Server", "").startswith("RushDAW/"):
                return None
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _bind(args):
    """Create the server. If the port is busy: reuse an already running RushDAW (same settings),
    otherwise (default port only) move on to the next free port. Returns (httpd, None) or (None, url_of_running)."""
    port = args.port or DEFAULT_PORT
    ports = [port] if args.port else range(port, port + PORT_TRIES)
    for pt in ports:
        try:
            return make_server(args.host, pt, args.home, args.api_key), None
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
        info = _running_rushdaw(args.host, pt)
        if info is not None and not args.home and not args.api_key:
            return None, _url(args.host, pt)  # RushDAW is already running there: just use it
        why = "another RushDAW with different settings" if info is not None else "another program"
        if args.port:
            sys.exit(f"rushdaw: port {pt} is already in use by {why}. Start with a different --port, e.g. --port {pt + 1}.")
        print(f"Port {pt} is in use by {why}, trying {pt + 1}…", flush=True)
    sys.exit(f"rushdaw: no free port between {port} and {port + PORT_TRIES - 1}. Use --port.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rushdaw", description="RushDAW web based DAW")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=None,
                   help=f"port (default {DEFAULT_PORT}; if busy, the next free port is used automatically)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    p.add_argument("--home", default=None, help="data folder (default ~/.rushdaw or $RUSHDAW_HOME)")
    p.add_argument("--api-key", default=os.environ.get("RUSHDAW_API_KEY"),
                   help="optional: enable the MCP server (HTTP+SSE at /sse) protected by "
                        "'Authorization: Bearer <KEY>' (default: $RUSHDAW_API_KEY; MCP is off when not set)")
    p.add_argument("--version", action="version", version=f"rushdaw {__version__}")
    args = p.parse_args(argv)

    httpd, running = _bind(args)
    if running:
        print(f"RushDAW is already running at {running} – opening it.", flush=True)
        if not args.no_browser:
            webbrowser.open(running)
        return
    url = _url(args.host, httpd.server_address[1])
    print(f"RushDAW {__version__} running at {url}  (Ctrl+C to stop)", flush=True)
    print(f"Data: {httpd.RequestHandlerClass.storage.home}  (db.sql + file/)", flush=True)
    if args.api_key:
        print(f"MCP:  {url}sse  (HTTP+SSE transport, header 'Authorization: Bearer <api key>')", flush=True)
    else:
        print("MCP:  off (optional – start with --api-key KEY to enable)", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping RushDAW.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
