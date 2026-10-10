import contextlib
import io
import socket
import tempfile
import threading
import unittest
from unittest import mock

from rushdaw import cli
from rushdaw.server import make_server


def _busy_socket():
    """A plain (non-RushDAW) listener on a free port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s


class BusyPortTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_make_server_on_busy_port_raises_oserror_not_attributeerror(self):
        s = _busy_socket()
        self.addCleanup(s.close)
        with self.assertRaises(OSError):
            make_server("127.0.0.1", s.getsockname()[1], self.tmp.name)

    def test_explicit_busy_port_gives_clear_message(self):
        s = _busy_socket()
        self.addCleanup(s.close)
        port = s.getsockname()[1]
        with self.assertRaises(SystemExit) as cm:
            cli.main(["--port", str(port), "--no-browser", "--home", self.tmp.name])
        self.assertIn(f"port {port} is already in use", str(cm.exception.code))

    def test_default_busy_port_moves_to_next_free_port(self):
        s = _busy_socket()
        self.addCleanup(s.close)
        port = s.getsockname()[1]
        out = io.StringIO()
        with mock.patch.object(cli, "DEFAULT_PORT", port), \
                mock.patch("rushdaw.server.ThreadingHTTPServer.serve_forever", return_value=None), \
                contextlib.redirect_stdout(out):
            cli.main(["--no-browser", "--home", self.tmp.name])
        text = out.getvalue()
        self.assertIn(f"Port {port} is in use by another program", text)
        self.assertIn("RushDAW", text)
        self.assertNotIn(f":{port}/", text.split("trying")[-1])

    def test_already_running_rushdaw_is_reused(self):
        httpd = make_server("127.0.0.1", 0, self.tmp.name)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        out = io.StringIO()
        with mock.patch.object(cli, "DEFAULT_PORT", port), contextlib.redirect_stdout(out):
            cli.main(["--no-browser"])
        self.assertIn(f"already running at http://localhost:{port}/", out.getvalue())


if __name__ == "__main__":
    unittest.main()
