import io
import tempfile
import json
import math
import struct
import threading
import unittest
import urllib.request
import wave

from rushdaw.export import available_formats, convert
from rushdaw.server import make_server


def sine_wav(seconds=0.5, sr=44100):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(
            struct.pack("<hh", v, v)
            for v in (int(8000 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(int(sr * seconds)))
        )
        w.writeframes(frames)
    return buf.getvalue()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.httpd = make_server("127.0.0.1", 0, cls.tmp.name)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def test_static_files(self):
        for path in ("/", "/app.js", "/style.css"):
            with urllib.request.urlopen(self.base + path) as r:
                self.assertEqual(r.status, 200)
                self.assertGreater(len(r.read()), 100)

    def test_info(self):
        with urllib.request.urlopen(self.base + "/api/info") as r:
            info = json.load(r)
        self.assertIn("wav", info["formats"])

    def test_export_mp3_and_mp4(self):
        if "mp3" not in available_formats():
            self.skipTest("ffmpeg unavailable")
        for fmt in ("mp3", "mp4"):
            req = urllib.request.Request(self.base + f"/api/export?format={fmt}", data=sine_wav(), method="POST")
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200)
                self.assertGreater(len(r.read()), 1000)

    def test_bad_format(self):
        with self.assertRaises(ValueError):
            convert(sine_wav(0.1), "exe")


if __name__ == "__main__":
    unittest.main()
