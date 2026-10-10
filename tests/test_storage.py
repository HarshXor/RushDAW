import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from rushdaw.server import make_server
from rushdaw.storage import Storage, StorageError


def project_bytes(title="Song", bpm=180, tracks=2):
    return json.dumps({"app": "rushdaw", "version": 1, "audio": {"b1": {"name": "x.wav", "wav": "UklGRg=="}},
                       "project": {"title": title, "bpm": bpm, "sig": 4, "tracks": [{"id": i} for i in range(tracks)]}}).encode()


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Storage(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_layout_and_revisions(self):
        p = self.st.create_project("Demo", 180)
        r1 = self.st.save_revision(p["id"], project_bytes("Demo", tracks=2), "first")
        r2 = self.st.save_revision(p["id"], project_bytes("Demo v2", tracks=3), "")
        self.assertEqual((r1["number"], r2["number"]), (1, 2))
        # files on disk in file/<id>/rev-000N.rushdaw
        d = os.path.join(self.tmp.name, "file", p["id"])
        self.assertEqual(sorted(os.listdir(d)), ["rev-0001.rushdaw", "rev-0002.rushdaw"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "db.sql")))
        meta = self.st.get_project(p["id"])
        self.assertEqual(meta["head_revision"], 2)
        self.assertEqual(meta["name"], "Demo v2")
        self.assertEqual([r["message"] for r in meta["revisions"]], ["Revision 2", "first"])
        data, rev, _ = self.st.read_revision(p["id"], 1)
        self.assertEqual(rev["track_count"], 2)
        self.assertEqual(json.loads(data)["project"]["title"], "Demo")
        r3 = self.st.restore_revision(p["id"], 1)
        self.assertEqual(r3["number"], 3)
        self.assertEqual(json.loads(self.st.read_revision(p["id"])[0])["project"]["title"], "Demo")

    def test_db_holds_metadata_only(self):
        p = self.st.create_project("Meta")
        self.st.save_revision(p["id"], project_bytes(), "x")
        db = sqlite3.connect(os.path.join(self.tmp.name, "db.sql"))
        cols = {r[1] for t in ("projects", "revisions") for r in db.execute(f"PRAGMA table_info({t})")}
        db.close()
        self.assertFalse(cols & {"content", "data", "audio", "tracks"})

    def test_soft_delete_restore_rename(self):
        p = self.st.create_project("A")
        self.st.rename_project(p["id"], "B")
        self.assertEqual(self.st.get_project(p["id"])["name"], "B")
        self.st.delete_project(p["id"])
        self.assertEqual(self.st.list_projects(), [])
        self.assertEqual(len(self.st.list_projects(deleted=True)), 1)
        self.st.restore_project(p["id"])
        self.assertEqual(len(self.st.list_projects()), 1)

    def test_validation(self):
        with self.assertRaises(StorageError):
            self.st.get_project("../../etc")
        p = self.st.create_project("V")
        with self.assertRaises(StorageError):
            self.st.save_revision(p["id"], b'{"app":"other"}')
        with self.assertRaises(StorageError):
            self.st.read_revision(p["id"])


class ProjectApiTest(unittest.TestCase):
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

    def call(self, method, path, body=None, raw=False):
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        with urllib.request.urlopen(req) as r:
            out = r.read()
            return (out, r.headers) if raw else json.loads(out)

    def test_flow(self):
        p = self.call("POST", "/api/projects", {"name": "Api Song", "bpm": 170})
        pid = p["id"]
        self.call("POST", f"/api/projects/{pid}/revisions?message=one", project_bytes("Api Song"))
        self.call("POST", f"/api/projects/{pid}/revisions?message=two", project_bytes("Api Song", tracks=5))
        meta = self.call("GET", f"/api/projects/{pid}")
        self.assertEqual([r["message"] for r in meta["revisions"]], ["two", "one"])
        data, headers = self.call("GET", f"/api/projects/{pid}/file?rev=1&download=1", raw=True)
        self.assertEqual(headers["X-Revision"], "1")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(len(json.loads(data)["project"]["tracks"]), 2)
        self.call("POST", f"/api/projects/{pid}/restore?rev=1")
        self.assertEqual(self.call("GET", f"/api/projects/{pid}")["head_revision"], 3)
        imp = self.call("POST", "/api/projects/import?name=Imported", project_bytes("X"))
        self.assertEqual(imp["head_revision"], 1)
        self.call("DELETE", f"/api/projects/{pid}")
        ids = [x["id"] for x in self.call("GET", "/api/projects")["projects"]]
        self.assertNotIn(pid, ids)
        self.assertIn(pid, [x["id"] for x in self.call("GET", "/api/projects?deleted=1")["projects"]])
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.call("GET", "/api/projects/" + "0" * 32)
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
