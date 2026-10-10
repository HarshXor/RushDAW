"""Command line entry point: ``rushdaw`` / ``python -m rushdaw``."""
import argparse
import os
import threading
import webbrowser

from . import __version__
from .server import make_server


def main(argv=None):
    p = argparse.ArgumentParser(prog="rushdaw", description="RushDAW web based DAW")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    p.add_argument("--home", default=None, help="data folder (default ~/.rushdaw or $RUSHDAW_HOME)")
    p.add_argument("--api-key", default=os.environ.get("RUSHDAW_API_KEY"),
                   help="optional: enable the MCP server (HTTP+SSE at /sse) protected by "
                        "'Authorization: Bearer <KEY>' (default: $RUSHDAW_API_KEY; MCP is off when not set)")
    p.add_argument("--version", action="version", version=f"rushdaw {__version__}")
    args = p.parse_args(argv)

    httpd = make_server(args.host, args.port, args.home, args.api_key)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{httpd.server_address[1]}/"
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
