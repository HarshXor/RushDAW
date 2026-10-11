import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import base64
import io
import time
import zipfile

from rushdaw.server import make_server
from rushdaw.storage import Storage, StorageError, build_package, unpack_package


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

    def test_mix_summary_and_old_db_migration(self):
        def proj(**flags):
            tr = [{"id": n, "name": n, "mute": n in flags.get("mute", ()), "solo": n in flags.get("solo", ())} for n in ("Drums", "Bass", "Guitar")]
            return json.dumps({"app": "rushdaw", "version": 1, "audio": {}, "project": {"title": "Mix", "bpm": 120, "sig": 4, "tracks": tr}}).encode()
        p = self.st.create_project("Mix")
        self.st.save_revision(p["id"], proj(solo=("Drums", "Bass"), mute=("Bass",)))
        mix = self.st.query_projects(q="Mix")["projects"][0]["mix"]
        self.assertEqual(mix, {"solo": ["Drums", "Bass"], "mute": ["Bass"], "audible": ["Drums"]})
        self.st.save_revision(p["id"], proj(mute=("Guitar",)))
        self.assertEqual(self.st.get_project(p["id"])["revisions"][0]["mix"]["audible"], ["Drums", "Bass"])
        # a database from before the 'mix' column: column added on open, value backfilled from the revision file
        db = sqlite3.connect(os.path.join(self.tmp.name, "db.sql"))
        db.execute("UPDATE revisions SET mix = NULL"); db.commit(); db.close()
        st2 = Storage(self.tmp.name)
        self.assertEqual(st2.query_projects(q="Mix")["projects"][0]["mix"]["mute"], ["Guitar"])
        db = sqlite3.connect(os.path.join(self.tmp.name, "db.sql"))
        self.assertIsNotNone(db.execute("SELECT mix FROM revisions WHERE number = 2").fetchone()[0]); db.close()

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


class PackageAndQueryTest(unittest.TestCase):
    """Export = .zip (project.rushdaw + audio/ files) that imports again in one go; listing is searched / filtered /
    paginated on the server."""
    WAV = b"RIFF" + b"\x00" * 40 + b"real-audio-bytes"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Storage(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def doc(self, title="Pkg Song"):
        return json.dumps({"app": "rushdaw", "version": 1,
                           "audio": {"b1": {"name": "Take 1", "wav": base64.b64encode(self.WAV).decode()},
                                     "b2": {"name": "guitar di.wav", "wav": base64.b64encode(self.WAV + b"2").decode()}},
                           "project": {"title": title, "bpm": 150, "sig": 4, "tracks": [{"id": "t1", "clips": [
                               {"id": "c1", "kind": "audio", "buf": "b1"}, {"id": "c2", "kind": "audio", "buf": "b2"}]}]}}).encode()

    def test_package_layout_and_roundtrip(self):
        p = self.st.create_project("Pkg Song", 150)
        self.st.save_revision(p["id"], self.doc(), "with audio")
        data, fname = self.st.export_package(p["id"])
        self.assertTrue(fname.endswith("-rev1.rushdaw.zip"))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = sorted(z.namelist())
            self.assertIn("project.rushdaw", names)
            audio = [n for n in names if n.startswith("audio/")]
            self.assertEqual(len(audio), 2)
            self.assertTrue(all(n.endswith(".wav") for n in audio))
            proj = json.loads(z.read("project.rushdaw"))
            self.assertTrue(all("file" in a and "wav" not in a for a in proj["audio"].values()))   # referenced, not embedded
            self.assertEqual(z.read(proj["audio"]["b1"]["file"]), self.WAV)                      # the real audio bytes
        imp = self.st.import_project(data)                                                       # one import = everything back
        back, _, _ = self.st.read_revision(imp["id"])
        doc = json.loads(back)
        self.assertEqual(base64.b64decode(doc["audio"]["b1"]["wav"]), self.WAV)
        self.assertEqual(base64.b64decode(doc["audio"]["b2"]["wav"]), self.WAV + b"2")
        self.assertEqual(doc["project"]["tracks"], json.loads(self.doc())["project"]["tracks"])
        self.assertEqual(imp["name"], "Pkg Song")

    def test_package_errors_and_nested_folder(self):
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("project.rushdaw", json.dumps({"app": "rushdaw", "project": {"title": "x", "tracks": []},
                                                      "audio": {"b1": {"name": "a", "file": "audio/missing.wav"}}}))
        with self.assertRaises(StorageError):
            unpack_package(bad.getvalue())
        # a user re-zipped the exported folder (everything inside "My Song/") -> still imports
        pkg = build_package(self.doc())
        nested = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(pkg)) as src, zipfile.ZipFile(nested, "w") as dst:
            for n in src.namelist():
                dst.writestr("My Song/" + n, src.read(n))
        doc = json.loads(unpack_package(nested.getvalue()))
        self.assertEqual(base64.b64decode(doc["audio"]["b2"]["wav"]), self.WAV + b"2")

    def test_query_projects_search_filters_pagination(self):
        ids = []
        for i, (name, bpm) in enumerate([("Crust One", 180), ("Doom Slow", 70), ("crust two", 190), ("Pop", 120), ("Punk", 200)]):
            p = self.st.create_project(name, bpm)
            self.st.save_revision(p["id"], project_bytes(name, bpm), "riff idea" if name == "Pop" else "")
            ids.append(p["id"])
        r = self.st.query_projects(q="crust")                                    # case-insensitive name search
        self.assertEqual(sorted(x["name"] for x in r["projects"]), ["Crust One", "crust two"])
        self.assertEqual([x["name"] for x in self.st.query_projects(q="riff")["projects"]], ["Pop"])   # revision notes too
        self.assertEqual(self.st.query_projects(q="100%")["total"], 0)            # LIKE wildcards are escaped
        r = self.st.query_projects(bpm_min=150, sort="bpm", order="asc")
        self.assertEqual([x["bpm"] for x in r["projects"]], [180, 190, 200])
        page2 = self.st.query_projects(sort="name", order="asc", per_page=2, page=2)
        self.assertEqual((page2["total"], page2["pages"], page2["page"]), (5, 3, 2))
        self.assertEqual([x["name"] for x in page2["projects"]], ["Doom Slow", "Pop"])
        today = time.strftime("%Y-%m-%d")
        self.assertEqual(self.st.query_projects(date_from=today, date_to=today)["total"], 5)
        self.assertEqual(self.st.query_projects(date_to="2000-01-01")["total"], 0)
        self.assertEqual(self.st.query_projects(date_field="created", date_from="2999-01-01")["total"], 0)
        self.st.delete_project(ids[0])
        self.assertEqual(self.st.query_projects()["total"], 4)
        self.assertEqual([x["name"] for x in self.st.query_projects(deleted=True)["projects"]], ["Crust One"])
        with self.assertRaises(StorageError):
            self.st.query_projects(sort="drop table")
        with self.assertRaises(StorageError):
            self.st.query_projects(date_from="yesterday")


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

    def test_export_zip_import_and_listing(self):
        wav = b"RIFF" + b"\x01" * 64
        doc = json.dumps({"app": "rushdaw", "version": 1, "audio": {"b9": {"name": "vox.wav", "wav": base64.b64encode(wav).decode()}},
                          "project": {"title": "Zip Song", "bpm": 140, "sig": 4, "tracks": []}}).encode()
        pid = self.call("POST", "/api/projects", {"name": "Zip Song", "bpm": 140})["id"]
        self.call("POST", f"/api/projects/{pid}/revisions?message=take", doc)
        data, headers = self.call("GET", f"/api/projects/{pid}/export", raw=True)
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertIn("Zip%20Song-rev1.rushdaw.zip", headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(sorted(n for n in z.namelist() if n != "README.txt")[0], "audio/b9-vox.wav")
        # editor state (unsaved) -> package
        data2, h2 = self.call("POST", "/api/package?name=Live%20State", doc, raw=True)
        self.assertIn("Live%20State.rushdaw.zip", h2["Content-Disposition"])
        imp = self.call("POST", "/api/projects/import?name=Re-imported", data2)
        back = self.call("GET", f"/api/projects/{imp['id']}/file")
        self.assertEqual(base64.b64decode(back["audio"]["b9"]["wav"]), wav)
        # listing: server-side search + pagination
        res = self.call("GET", "/api/projects?q=zip&per_page=1&page=1&sort=name&order=asc")
        self.assertEqual((res["total"], res["pages"], len(res["projects"])), (1, 1, 1))
        res = self.call("GET", "/api/projects?per_page=1&page=2")
        self.assertEqual((res["page"], len(res["projects"])), (2, 1))
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call("GET", "/api/projects?sort=evil")
        self.assertEqual(e.exception.code, 400)

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
