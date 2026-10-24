"""Export progress jobs: ffmpeg progress reporting, cancel, and identical output with / without progress."""
import io
import json
import math
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave

from rushdaw import export as E
from rushdaw.server import make_server


def make_wav(seconds=3.0, sr=48000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(int(seconds * sr)):
            v = int(12000 * math.sin(2 * math.pi * 220 * i / sr))
            frames += struct.pack("<hh", v, -v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


@unittest.skipUnless(E.find_ffmpeg(), "ffmpeg not available")
class ExportJobTests(unittest.TestCase):
    def test_wav_duration(self):
        self.assertAlmostEqual(E.wav_duration(make_wav(2.5)), 2.5, places=3)
        self.assertEqual(E.wav_duration(b"nope"), 0.0)

    def test_progress_and_identical_output(self):
        wav = make_wav(4.0)
        plain, ext, _ = E.convert(wav, "flac", "T")
        job = E.job_start("t-ident-1")
        seen = []
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                seen.append(E.job_get("t-ident-1")["progress"])
                time.sleep(0.005)
        th = threading.Thread(target=watch)
        th.start()
        try:
            with_job, ext2, _ = E.convert(wav, "flac", "T", job)
        finally:
            stop.set()
            th.join()
        self.assertEqual(ext, ext2)
        self.assertEqual(plain, with_job, "progress reporting must not change the encoded file")
        self.assertEqual(E.job_get("t-ident-1")["progress"], 1.0)
        self.assertTrue(all(0.0 <= p <= 1.0 for p in seen))

    def test_cancel_before_start(self):
        self.assertTrue(E.job_cancel("t-cancel-early"))
        job = E.job_start("t-cancel-early")
        with self.assertRaises(E.Cancelled):
            E.convert(make_wav(1.0), "mp3", "T", job)

    def test_cancel_while_running(self):
        job = E.job_start("t-cancel-run")
        res = {}

        def run():
            try:
                E.convert(make_wav(60.0), "mp4", "T", job)  # video: slow enough to cancel mid-way
                res["r"] = "finished"
            except E.Cancelled:
                res["r"] = "cancelled"
        th = threading.Thread(target=run)
        th.start()
        for _ in range(400):  # wait until ffmpeg is running
            if job.get("proc") is not None:
                break
            time.sleep(0.01)
        E.job_cancel("t-cancel-run")
        th.join(30)
        self.assertEqual(res.get("r"), "cancelled")

    def test_bad_job_ids(self):
        self.assertIsNone(E.job_start("../etc"))
        self.assertIsNone(E.job_get("x" * 100))
        self.assertFalse(E.job_cancel(""))


@unittest.skipUnless(E.find_ffmpeg(), "ffmpeg not available")
class ExportJobHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.httpd = make_server("127.0.0.1", 0, home=cls.tmp.name)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.th = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def req(self, path, method="GET", body=None, ctype=None):
        r = urllib.request.Request(self.base + path, data=body, method=method)
        if ctype:
            r.add_header("Content-Type", ctype)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_export_with_job_reports_done(self):
        code, data = self.req("/api/export?format=mp3&title=x&job=http-job-1", "POST", make_wav(2.0), "audio/wav")
        self.assertEqual(code, 200)
        self.assertGreater(len(data), 1000)
        code, j = self.req("/api/jobs/http-job-1")
        self.assertEqual(code, 200)
        j = json.loads(j)
        self.assertTrue(j["done"])
        self.assertEqual(j["progress"], 1.0)
        self.assertEqual(j["stage"], "done")

    def test_cancelled_job_refuses_export(self):
        self.assertEqual(self.req("/api/jobs/http-job-2", "DELETE")[0], 200)
        code, data = self.req("/api/export?format=mp3&title=x&job=http-job-2", "POST", make_wav(1.0), "audio/wav")
        self.assertEqual(code, 499)
        self.assertEqual(json.loads(data)["error"], "cancelled")

    def test_unknown_and_invalid_jobs(self):
        self.assertEqual(self.req("/api/jobs/does-not-exist")[0], 404)
        self.assertEqual(self.req("/api/jobs/bad%20id", "DELETE")[0], 400)


if __name__ == "__main__":
    unittest.main()
