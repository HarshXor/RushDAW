import http.client
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from rushdaw import model as M
from rushdaw.server import make_server

KEY = "test-secret-key"
APP_JS = os.path.join(os.path.dirname(__file__), "..", "src", "rushdaw", "static", "app.js")


class _Srv:
    def __init__(self, api_key):
        self.tmp = tempfile.TemporaryDirectory()
        self.httpd = make_server("127.0.0.1", 0, self.tmp.name, api_key)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()


class SSEClient:
    """Minimal MCP HTTP+SSE client: GET /sse, read 'endpoint', POST messages, read 'message' events."""

    def __init__(self, srv, token=KEY):
        self.srv, self.token = srv, token
        self.conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
        headers = {"Accept": "text/event-stream"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        self.conn.request("GET", "/sse", headers=headers)
        self.resp = self.conn.getresponse()
        self.status = self.resp.status
        self.endpoint = None
        if self.status == 200:
            ev, data = self.next_event()
            assert ev == "endpoint", ev
            self.endpoint = data

    def next_event(self):
        event, data = None, []
        while True:
            line = self.resp.fp.readline().decode("utf-8")
            if not line:
                raise EOFError("stream closed")
            line = line.rstrip("\r\n")
            if line == "":
                if event or data:
                    return event, "\n".join(data)
                continue
            if line.startswith(":"):
                continue
            k, _, v = line.partition(":")
            v = v[1:] if v.startswith(" ") else v
            if k == "event":
                event = v
            elif k == "data":
                data.append(v)

    def post(self, body, token="default"):
        tok = self.token if token == "default" else token
        headers = {"Content-Type": "application/json"}
        if tok is not None:
            headers["Authorization"] = f"Bearer {tok}"
        req = urllib.request.Request(self.srv.base + self.endpoint, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req) as r:
            return r.status

    def request(self, method, params=None, mid=1):
        assert self.post({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}) == 202
        ev, data = self.next_event()
        assert ev == "message", ev
        return json.loads(data)

    def close(self):
        self.resp.close()
        self.conn.close()


class AuthTest(unittest.TestCase):
    def test_off_without_key(self):
        s = _Srv(None)
        try:
            c = SSEClient(s)
            self.assertEqual(c.status, 404)
            c.close()
            info = json.loads(urllib.request.urlopen(s.base + "/api/info").read())
            self.assertFalse(info["mcp"]["enabled"])
        finally:
            s.close()

    def test_bearer_required(self):
        s = _Srv(KEY)
        try:
            for tok in (None, "wrong-key"):
                c = SSEClient(s, tok)
                self.assertEqual(c.status, 401)
                self.assertIn("Bearer", c.resp.headers.get("WWW-Authenticate", ""))
                c.close()
            c = SSEClient(s)
            self.assertEqual(c.status, 200)
            self.assertTrue(c.endpoint.startswith("/messages?session_id="))
            # posting messages also needs the token
            with self.assertRaises(urllib.error.HTTPError) as cm:
                c.post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, token="wrong")
            self.assertEqual(cm.exception.code, 401)
            self.assertEqual(c.request("ping")["result"], {})
            c.close()
            # unknown session
            req = urllib.request.Request(s.base + "/messages?session_id=deadbeef", data=b"{}", headers={"Authorization": f"Bearer {KEY}"}, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 404)
            # the old Streamable-HTTP endpoint no longer exists
            req = urllib.request.Request(s.base + "/mcp", data=b"{}", headers={"Authorization": f"Bearer {KEY}"}, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 404)
        finally:
            s.close()


class McpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = _Srv(KEY)
        cls.c = SSEClient(cls.s)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        cls.s.close()

    def rpc(self, method, params=None):
        McpTest.n += 1
        out = self.c.request(method, params, self.n)
        self.assertEqual(out["id"], self.n)
        return out

    def call(self, _tool, ok=True, **args):
        res = self.rpc("tools/call", {"name": _tool, "arguments": args})["result"]
        self.assertEqual(res["isError"], not ok, res["content"][0]["text"])
        self.assertEqual(json.loads(res["content"][0]["text"]), res["structuredContent"])
        return res["structuredContent"]

    def test_protocol(self):
        init = self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})["result"]
        self.assertEqual(init["protocolVersion"], "2024-11-05")
        self.assertIn("tools", init["capabilities"])
        self.assertEqual(self.c.post({"jsonrpc": "2.0", "method": "notifications/initialized"}), 202)
        tools = {t["name"]: t for t in self.rpc("tools/list")["result"]["tools"]}
        for name in ("list_projects", "get_project", "create_project", "add_track", "update_track", "set_drum_pads",
                     "set_drum_pattern", "set_drum_tuning", "set_notes", "set_track_effects", "restore_revision"):
            self.assertIn(name, tools)
            self.assertEqual(tools[name]["inputSchema"]["type"], "object")
        self.assertEqual(self.rpc("nope")["error"]["code"], -32601)
        # batch: two requests + a notification -> two message events
        self.assertEqual(self.c.post([{"jsonrpc": "2.0", "id": 901, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/x"},
                                      {"jsonrpc": "2.0", "id": 902, "method": "ping"}]), 202)
        ids = [json.loads(self.c.next_event()[1])["id"] for _ in range(2)]
        self.assertEqual(ids, [901, 902])

    def test_edit_flow(self):
        p = self.call("create_project", name="MCP Song", bpm=190, template="metal")
        pid = p["project_id"]
        self.assertEqual([t["type"] for t in p["tracks"]], ["drum", "synth", "guitar", "audio"])
        # layers
        g2 = self.call("add_track", project_id=pid, type="guitar", name="Lead Guitar")["track"]
        self.assertEqual(g2["type"], "guitar")
        self.assertEqual(len(g2["clips"]), 1)
        self.call("update_track", project_id=pid, track="Lead Guitar", pan=-0.4, volume=0.7, mute=True, reverb_send=0.2)
        self.call("duplicate_track", project_id=pid, track="Lead Guitar")
        self.call("move_track", project_id=pid, track="Lead Guitar (copy)", position=1)
        # pads
        drums = "Drums 1"
        self.call("set_drum_pattern", project_id=pid, track=drums, patterns={"kick": "x..x", "snare": "....x.......x..."}, clear_others=True)
        self.call("set_drum_pads", project_id=pid, track=drums, part="china", steps=[1, 9])
        self.call("set_drum_pads", project_id=pid, track=drums, part="kick", steps=[4], on=False)
        self.call("set_drum_tuning", project_id=pid, track=drums, part="snare", pitch=3, decay=1.4)
        self.call("set_pattern_length", project_id=pid, track=drums, bars=2)
        # notes / synth / fx / master
        self.call("set_notes", project_id=pid, track="Guitar 1", notes=[{"note": "E2", "step": 1, "length": 2}, {"note": "G2", "step": 5}])
        self.call("set_synth", project_id=pid, track="Guitar 1", preset="Palm Mute Guitar", params={"drive": 0.9})
        fx = self.call("set_track_effects", project_id=pid, track="Guitar 1", effects=[{"type": "dist", "params": {"drive": 0.7}}, {"type": "reverb"}])["track"]["fx"]
        self.call("update_effect", project_id=pid, track="Guitar 1", effect_id=fx[1]["id"], params={"mix": 0.2}, on=False)
        self.call("set_master", project_id=pid, preset="Loud Pop", params={"ceiling": -0.8})
        region = self.call("add_region", project_id=pid, track=drums, start_beat=16, length_beats=8)["clip_id"]
        self.call("update_clip", project_id=pid, clip_id=region, start_beat=20)

        doc = self.call("get_project", project_id=pid)
        tracks = {t["name"]: t for t in doc["tracks"]}
        self.assertEqual(doc["tracks"][0]["name"], "Lead Guitar (copy)")
        d = tracks[drums]
        self.assertEqual(d["pattern_bars"], 2)
        self.assertEqual(d["pads"]["kick"], "x...x..xx..xx..x" + "." * 16)  # "x..x" repeated, step 4 cleared, bar 2 empty
        self.assertEqual(d["pads"]["snare"][:16], "....x.......x...")
        self.assertEqual(d["pads"]["rim"][:16], "x.......x.......")
        self.assertEqual(d["pads"]["crash"], "." * 32)
        self.assertEqual(d["kit"]["snare"], {"pitch": 3, "decay": 1.4, "level": 1})
        self.assertEqual([c["start_beat"] for c in d["clips"]], [0, 20])
        lead = tracks["Lead Guitar"]
        self.assertEqual((lead["pan"], lead["volume"], lead["mute"], lead["reverb_send"]), (-0.4, 0.7, True, 0.2))
        g = tracks["Guitar 1"]
        self.assertEqual([(n["note"], n["step"], n["length"]) for n in g["notes"]], [("E2", 1, 2), ("G2", 5, 1)])
        self.assertEqual((g["synth"]["preset"], g["synth"]["drive"]), ("Palm Mute Guitar", 0.9))
        self.assertEqual([(f["type"], f["on"]) for f in g["fx"]], [("dist", True), ("reverb", False)])
        self.assertEqual(g["fx"][1]["params"]["mix"], 0.2)
        self.assertEqual(doc["master"]["ceiling"], -0.8)

        # every edit is a revision; restore works
        revs = self.call("list_revisions", project_id=pid)
        self.assertEqual(revs["latest"], len(revs["revisions"]))
        self.assertTrue(all(r["message"].startswith("MCP: ") for r in revs["revisions"]))
        self.call("restore_revision", project_id=pid, revision=1)
        self.assertEqual(len(self.call("get_project", project_id=pid)["tracks"]), 4)
        # stored file is a valid document the web UI can load
        raw = urllib.request.urlopen(self.s.base + f"/api/projects/{pid}/file?rev=5").read()
        stored = json.loads(raw)
        self.assertEqual(stored["app"], "rushdaw")
        self.assertTrue(all("clips" in t and "fx" in t for t in stored["project"]["tracks"]))

    def test_errors(self):
        pid = self.call("create_project", name="Err", template="empty")["project_id"]
        self.assertIn("not found", self.call("update_track", ok=False, project_id=pid, track="Nope", pan=0)["error"])
        self.assertIn("between", self.call("update_track", ok=False, project_id=pid, track=1, pan=5)["error"])
        self.assertIn("not a drum", self.call("set_drum_pads", ok=False, project_id=pid, track=1, part="kick", steps=[1])["error"])
        self.assertIn("unknown drum part", self.call("set_drum_tuning", ok=False, project_id=pid, track=self.call("add_track", project_id=pid, type="drum")["track"]["id"], part="cowbell")["error"])
        self.assertIn("missing", self.call("get_project", ok=False)["error"])
        self.assertIn("unknown argument", self.call("list_projects", ok=False, foo=1)["error"])
        self.assertIn("unknown tool", self.call("does_not_exist", ok=False)["error"])
        self.assertIn("invalid project id", self.call("get_project", ok=False, project_id="../../x")["error"])


class ModelSyncTest(unittest.TestCase):
    """The Python model must mirror static/app.js so MCP edits load correctly in the UI."""

    def test_constants_match_app_js(self):
        with open(APP_JS, encoding="utf-8") as f:
            js = f.read()
        self.assertEqual(re.findall(r"\{ id: '(\w+)', name: '[^']+' \}", js.split("const DRUMS")[1].split("];")[0]), M.DRUM_IDS)
        block = lambda name: js.split(f"const {name} = {{")[1].split("\n};")[0]
        self.assertEqual(re.findall(r"^\s+'([^']+)':", block("DRUM_PRESETS"), re.M), list(M.DRUM_PRESETS))
        self.assertEqual(re.findall(r"^\s+'([^']+)':", block("SYNTH_PRESETS"), re.M), list(M.SYNTH_PRESETS))
        self.assertEqual(re.findall(r"^\s+'([^']+)':", block("MASTER_PRESETS"), re.M), list(M.MASTER_PRESETS))
        self.assertEqual(re.findall(r"^\s+(\w+): \{ name:", block("FX_TYPES"), re.M), list(M.FX_TYPES))
        for preset, rows in M.DRUM_PRESETS.items():
            for part, pat in rows.items():
                self.assertIn(f"{part}: '{pat}'", block("DRUM_PRESETS"), preset)


if __name__ == "__main__":
    unittest.main()
