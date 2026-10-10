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

    def test_dbeat_crust_template(self):
        p = self.call("create_project", name="Crust", bpm=176, template="dbeat")
        self.assertEqual([(t["name"], t["type"]) for t in p["tracks"]], [("Drums", "drum"), ("Bass", "bass"), ("Guitar 1", "guitar"), ("Vocal", "audio")])
        full = {t["type"]: t for t in self.call("get_project", project_id=p["project_id"])["tracks"]}
        # classic d-beat over 2 bars (crash / hi-hat / snare / kick from top to bottom)
        dr = full["drum"]
        self.assertEqual(dr["pattern_bars"], 2)
        self.assertEqual(dr["pads"]["crash"], "x" + "." * 31)                       # only on the 1
        self.assertEqual(dr["pads"]["ohh"], "..x.x.x.x.x.x.x." + "x.x.x.x.x.x.x.x.")  # open hi-hat 8ths, none under the crash
        self.assertEqual(dr["pads"]["snare"], "..x." * 8)                         # every '&'
        self.assertEqual(dr["pads"]["kick"], "x..x.x.." * 4)                      # K..K.K..
        for other in ("chh", "tomh", "tomm", "toml", "ride", "phh"):
            self.assertEqual(set(dr["pads"][other]), {"."}, other)
        self.assertEqual((full["bass"]["synth"]["preset"], full["guitar"]["synth"]["preset"]), ("Pick Bass", "Power Chord Guitar"))
        self.assertEqual([f["type"] for f in full["bass"]["fx"]], ["dist"])
        # the distorted guitar's amp is visible in ITS effects (not hidden in the instrument)
        self.assertEqual([f["type"] for f in full["guitar"]["fx"]], ["amp"])
        self.assertEqual(full["guitar"]["synth"]["drive"], 0)
        self.assertEqual(full["guitar"]["fx"][0]["params"]["drive"], 0.8)
        self.assertEqual(len(full["guitar"]["notes"]), len(M.CRUST_RIFF))
        self.assertIn("dbeat", self.call("get_reference")["templates"])
        with open(APP_JS, encoding="utf-8") as f:
            js = f.read()
        js_riff = re.search(r"const CRUST_RIFF = (\[.*?\]);", js).group(1)
        self.assertEqual(json.loads(js_riff), [list(n) for n in M.CRUST_RIFF])

    def test_regions_are_independent(self):
        pid = self.call("create_project", name="Regions", template="metal")["project_id"]
        drums = self.call("get_project", project_id=pid)["tracks"][0]
        r1 = drums["clips"][0]
        self.assertEqual((r1["pattern_bars"], len(r1["pads"]["kick"])), (4, 64))   # 4-bar region = 64 literal steps
        r1 = r1["id"]
        r2 = self.call("add_region", project_id=pid, track=drums["id"], start_beat=16, length_beats=4, copy_from=r1)["clip_id"]
        r3 = self.call("add_region", project_id=pid, track=drums["id"], start_beat=20, empty=True)["clip_id"]
        regs = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}
        self.assertEqual(regs[r2]["pads"]["kick"], regs[r1]["pads"]["kick"][:16])   # copy cut to 1 bar
        self.assertTrue(all(set(v) == {"."} for v in regs[r3]["pads"].values()))     # empty bar
        # edit only region 2
        res = self.call("set_drum_pattern", project_id=pid, track=drums["id"], clip_id=r2, patterns={"kick": "x..............."}, clear_others=True)
        self.assertEqual(res["edited"], f"region {r2}")
        regs = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}
        self.assertEqual(regs[r2]["pads"]["kick"], "x" + "." * 15)
        self.assertNotEqual(regs[r1]["pads"]["kick"][:16], regs[r2]["pads"]["kick"])
        # NOT a loop: clearing one step in bar 1 of region 1 leaves the same step in bars 2-4 alone
        self.call("set_drum_pads", project_id=pid, track=drums["id"], clip_id=r1, part="kick", steps=[1], on=False)
        k = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}[r1]["pads"]["kick"]
        self.assertEqual((k[0], k[16], k[32], k[48]), (".", "x", "x", "x"))
        # extending a region adds EMPTY bars (the old content is not repeated)
        self.call("update_clip", project_id=pid, clip_id=r2, length_beats=12)
        p2 = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}[r2]["pads"]
        self.assertEqual((p2["kick"], len(p2["snare"])), ("x" + "." * 47, 48))
        self.call("set_pattern_length", project_id=pid, track=drums["id"], clip_id=r3, bars=2)
        regs = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}
        self.assertEqual((regs[r3]["pattern_bars"], regs[r3]["length_beats"]), (2, 8))
        # shortening cuts the end
        self.call("update_clip", project_id=pid, clip_id=r2, length_beats=2)
        self.assertEqual({c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}[r2]["pads"]["kick"], "x.......")
        # whole-track edit (no clip_id) still changes every region
        self.call("set_drum_pads", project_id=pid, track=drums["id"], part="crash", steps=[1])
        regs = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][0]["clips"]}
        self.assertTrue(all(r["pads"]["crash"][0] == "x" for r in regs.values()))
        # synth/guitar regions too: notes are literal positions over the region
        g = self.call("get_project", project_id=pid)["tracks"][2]
        g1 = g["clips"][0]
        self.assertEqual(max(n["step"] for n in g1["notes"]) > 16, True)               # riff written out over 4 bars
        g2 = self.call("add_region", project_id=pid, track=g["id"], start_beat=16, copy_from=g1["id"])["clip_id"]
        self.call("set_notes", project_id=pid, track=g["id"], clip_id=g2, notes=[{"note": "A2", "step": 33, "length": 4}])
        gr = {c["id"]: c for c in self.call("get_project", project_id=pid)["tracks"][2]["clips"]}
        self.assertEqual([(n["note"], n["step"]) for n in gr[g2]["notes"]], [("A2", 33)])
        self.assertEqual(len(gr[g1["id"]]["notes"]), len(g1["notes"]))
        self.assertIn("not found", self.call("set_notes", ok=False, project_id=pid, track=g["id"], clip_id="nope", notes=[])["error"])
        self.assertIn("either", self.call("add_region", ok=False, project_id=pid, track=g["id"], start_beat=0, empty=True, copy_from=g2)["error"])

    def test_sustained_notes_and_envelope(self):
        pid = self.call("create_project", name="Sustain", template="metal")["project_id"]
        g = self.call("get_project", project_id=pid)["tracks"][2]
        self.assertEqual((g["synth"]["decay"], g["synth"]["susLevel"]), (2.0, 0.35))   # Clean Guitar envelope
        self.call("set_notes", project_id=pid, track=g["id"], clip_id=g["clips"][0]["id"], notes=[{"note": "A2", "step": 1, "length": 32}])
        n = self.call("get_project", project_id=pid)["tracks"][2]["clips"][0]["notes"]
        self.assertEqual([(x["note"], x["step"], x["length"]) for x in n], [("A2", 1, 32)])           # one long note over 2 bars
        self.call("set_synth", project_id=pid, track=g["id"], params={"decay": 0.5, "susLevel": 0.8, "release": 1.2})
        s = self.call("get_project", project_id=pid)["tracks"][2]["synth"]
        self.assertEqual((s["decay"], s["susLevel"], s["release"]), (0.5, 0.8, 1.2))
        self.assertIn("between", self.call("set_synth", ok=False, project_id=pid, track=g["id"], params={"susLevel": 2})["error"])
        pm = M.SYNTH_PRESETS["Palm Mute Guitar"]
        self.assertEqual((pm["susLevel"], pm["pluck"]), (0.0, 0))                                       # palm mute dies away
        with open(APP_JS, encoding="utf-8") as f:
            js = f.read()
        for needle in ("function prepSustain", "src.loop = true", "const envOf", "loopEnd", "drawEnv"):
            self.assertIn(needle, js)

    def test_old_regions_get_their_own_copy(self):
        proj = {"sig": 4, "tracks": [
            {"type": "drum", "pattern": {"bars": 1, "grid": [[1] + [0] * 15 for _ in M.DRUMS], "ids": list(M.DRUM_IDS)},
             "clips": [{"id": "a", "kind": "midi", "start": 0, "len": 4}, {"id": "b", "kind": "midi", "start": 4, "len": 4}]},
            {"type": "synth", "bars": 1, "notes": [{"p": 40, "s": 0, "l": 2}], "clips": [{"id": "c", "kind": "midi", "start": 0, "len": 4}]}]}
        M.fill_regions(proj)
        a, b = proj["tracks"][0]["clips"]
        self.assertEqual(a["pattern"]["grid"], proj["tracks"][0]["pattern"]["grid"])  # 1-bar region = the 1-bar template
        a["pattern"]["grid"][0][5] = 1                                   # editing a ...
        self.assertEqual(b["pattern"]["grid"][0][5], 0)                  # ... never changes b
        self.assertEqual(proj["tracks"][0]["pattern"]["grid"][0][5], 0)  # nor the template
        c = proj["tracks"][1]["clips"][0]
        self.assertEqual((c["bars"], c["notes"]), (1, [{"p": 40, "s": 0, "l": 2}]))
        # an old LOOPING region longer than its pattern is unrolled once into literal steps (same sound, no loop)
        old = {"sig": 4, "tracks": [{"type": "drum", "pattern": {"bars": 1, "grid": [[1, 0, 0, 0] * 4 for _ in M.DRUMS], "ids": list(M.DRUM_IDS)},
                                     "clips": [{"id": "x", "kind": "midi", "start": 0, "len": 8,
                                                "pattern": {"bars": 1, "grid": [[1] + [0] * 15 for _ in M.DRUMS], "ids": list(M.DRUM_IDS)}}]}]}
        M.fill_regions(old)
        x = old["tracks"][0]["clips"][0]
        self.assertEqual(x["pattern"]["grid"][0], ([1] + [0] * 15) * 2)
        self.assertTrue(x["linear"])
        M.fill_regions(old)                                              # idempotent
        self.assertEqual(len(x["pattern"]["grid"][0]), 32)
        self.assertIsNot(c["notes"], proj["tracks"][1]["notes"])
        with open(APP_JS, encoding="utf-8") as f:
            js = f.read()
        for fn in ("function ensureRegions", "function edHolder", "function newRegion", "function shiftLeft", "function fitRegion", "function linearize", "function laneMenu", "function clipMenu"):
            self.assertIn(fn, js)

    def test_edit_flow(self):
        p = self.call("create_project", name="MCP Song", bpm=190, template="metal")
        pid = p["project_id"]
        self.assertEqual([t["type"] for t in p["tracks"]], ["drum", "bass", "guitar", "audio"])
        full = self.call("get_project", project_id=pid)["tracks"]
        self.assertEqual([(t["synth"]["preset"], t["synth"]["engine"]) for t in full if t["type"] in ("bass", "guitar")],
                         [("Finger Bass", "sample"), ("Clean Guitar", "sample")])
        b2 = self.call("add_track", project_id=pid, type="bass")["track"]
        self.assertEqual((b2["type"], b2["synth"]["preset"]), ("bass", "Finger Bass"))
        self.call("set_synth", project_id=pid, track=b2["id"], params={"brightness": 0.2, "sustain": 0.9, "body": 0.6})
        self.assertIn("between", self.call("set_synth", ok=False, project_id=pid, track=b2["id"], params={"sustain": 2})["error"])
        self.call("delete_track", project_id=pid, track=b2["id"])
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
        self.call("set_drum_pads", project_id=pid, track=drums, part="pedal", steps=[1, 9])
        self.call("set_drum_pads", project_id=pid, track=drums, part="kick", steps=[4], on=False)
        self.call("set_drum_tuning", project_id=pid, track=drums, part="snare", pitch=3, decay=1.4)
        self.call("set_drum_tuning", project_id=pid, track=drums, part="Floor Tom", pitch=-20, decay=3.5, level=1.8)
        self.assertIn("between", self.call("set_drum_tuning", ok=False, project_id=pid, track=drums, part="kick", pitch=30)["error"])
        self.call("set_drum_tuning", project_id=pid, track=drums, part="crash", volume_db=-6)      # per-part volume in dB
        self.call("set_drum_tuning", project_id=pid, track=drums, part="High Tom", tune_percent=200, decay_percent=150, volume_percent=80)
        self.assertIn("either", self.call("set_drum_tuning", ok=False, project_id=pid, track=drums, part="kick", tune_percent=120, pitch=1)["error"])
        self.assertIn("between", self.call("set_drum_tuning", ok=False, project_id=pid, track=drums, part="kick", tune_percent=500)["error"])
        self.call("set_drum_tuning", project_id=pid, track=drums, part="ride", volume_db=-48)      # bottom of the fader = off
        self.assertIn("either", self.call("set_drum_tuning", ok=False, project_id=pid, track=drums, part="kick", volume_db=-3, level=1)["error"])
        self.assertIn("between", self.call("set_drum_tuning", ok=False, project_id=pid, track=drums, part="kick", volume_db=12)["error"])
        self.call("set_pattern_length", project_id=pid, track=drums, bars=2)
        # notes / synth / fx / master
        self.call("set_notes", project_id=pid, track="Guitar 1", notes=[{"note": "E2", "step": 1, "length": 2}, {"note": "G2", "step": 5}])
        self.call("set_synth", project_id=pid, track="Guitar 1", preset="Palm Mute Guitar", params={"drive": 0.9})
        # the amp is a visible insert effect on THIS layer only (synth drive moves into it)
        gt = {t["name"]: t for t in self.call("get_project", project_id=pid)["tracks"]}
        self.assertEqual(gt["Guitar 1"]["synth"]["drive"], 0)
        self.assertEqual([(f["type"], f["params"]["drive"]) for f in gt["Guitar 1"]["fx"]], [("amp", 0.9)])
        self.assertFalse(any(f["type"] == "amp" for f in gt["Lead Guitar"]["fx"]))
        self.call("set_synth", project_id=pid, track="Guitar 1", preset="Clean Guitar")  # clean preset removes its amp
        self.assertEqual({t["name"]: t for t in self.call("get_project", project_id=pid)["tracks"]}["Guitar 1"]["fx"], [])
        self.call("set_synth", project_id=pid, track="Guitar 1", preset="Palm Mute Guitar")
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
        self.assertEqual(d["pads"]["phh"][:16], "x.......x.......")
        self.assertEqual(d["pads"]["crash"], "." * 32)
        self.assertEqual(d["kit"]["snare"], {"pitch": 3, "decay": 1.4, "level": 1})
        self.assertEqual(d["kit"]["toml"], {"pitch": -20, "decay": 3.5, "level": 1.8})
        self.assertAlmostEqual(d["kit"]["crash"]["level"], 0.501187, places=5)
        self.assertEqual(d["kit"]["ride"]["level"], 0)
        self.assertEqual(d["kit"]["tomh"], {"pitch": 12, "decay": 1.5, "level": 0.8})
        self.assertEqual(list(d["pads"]), ["kick", "snare", "chh", "ohh", "tomh", "tomm", "toml", "crash", "ride", "phh"])
        self.assertEqual([c["start_beat"] for c in d["clips"]], [0, 20])
        lead = tracks["Lead Guitar"]
        self.assertEqual((lead["pan"], lead["volume"], lead["mute"], lead["reverb_send"]), (-0.4, 0.7, True, 0.2))
        g = tracks["Guitar 1"]
        self.assertEqual([(n["note"], n["step"], n["length"]) for n in g["notes"]], [("E2", 1, 2), ("G2", 5, 1)])
        self.assertEqual((g["synth"]["preset"], g["synth"]["drive"]), ("Palm Mute Guitar", 0))
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


class MigrationTest(unittest.TestCase):
    def test_legacy_kit_rows_are_remapped(self):
        legacy = ["kick", "snare", "ride", "chh", "ohh", "tomh", "toml", "rim", "crash"]
        grid = [[1 if j == i else 0 for j in range(16)] for i in range(len(legacy))]  # row i hits step i
        proj = {"sig": 4, "tracks": [{"type": "drum", "pattern": {"bars": 1, "grid": grid}}]}
        M.migrate_drums(proj)
        p = proj["tracks"][0]["pattern"]
        self.assertEqual(p["ids"], M.DRUM_IDS)
        for r, pid in enumerate(M.DRUM_IDS):
            want = legacy.index(pid) if pid in legacy else None
            self.assertEqual(p["grid"][r].index(1) if 1 in p["grid"][r] else None, want, pid)

    def test_old_synth_guitar_and_bass_become_natural_strings(self):
        old = {"wave": "sawtooth", "attack": 0.003, "release": 0.12, "cutoff": 3200, "detune": 7, "gain": 0.22}
        proj = {"tracks": [
            {"type": "synth", "instrument": "guitar", "synth": {"preset": "Power Chord Guitar", **old}},
            {"type": "synth", "name": "Bass", "synth": {"preset": "Bass", **old}},
            {"type": "synth", "synth": {"preset": "Lead", **old}},                                  # real synth: untouched
            {"type": "synth", "instrument": "guitar", "synth": {"preset": "Lead Guitar", "engine": "osc"}},  # user's choice: untouched
            {"type": "synth", "instrument": "guitar", "synth": {"preset": "Clean Guitar", "engine": "string", "brightness": 0.4}},  # modeled -> real
        ]}
        M.migrate_strings(proj)
        g, b, lead, chosen, modeled = proj["tracks"]
        self.assertEqual((modeled["synth"]["engine"], modeled["synth"]["sample"]), ("sample", "electric_guitar_clean"))
        self.assertEqual((g["synth"]["preset"], g["synth"]["engine"]), ("Power Chord Guitar", "sample"))
        self.assertEqual((b["instrument"], b["synth"]["preset"], b["synth"]["engine"]), ("bass", "Finger Bass", "sample"))
        self.assertEqual(lead["synth"]["preset"], "Lead")
        self.assertNotIn("engine", lead["synth"])
        self.assertEqual(chosen["synth"]["engine"], "osc")
        with open(APP_JS, encoding="utf-8") as f:
            self.assertIn("function migrateStringTrack", f.read())

    def test_sample_files_exist_for_every_set(self):
        base = os.path.join(os.path.dirname(APP_JS), "samples")
        with open(APP_JS, encoding="utf-8") as f:
            js = f.read()
        for sid in M.SAMPLE_SETS:
            m = re.search(sid + r": \{ name: '[^']+', lo: (\d+), hi: (\d+) \}", js)
            self.assertIsNotNone(m, sid)
            for note in range(int(m.group(1)), int(m.group(2)) + 1, 3):
                path = os.path.join(base, sid, f"{note}.mp3")
                self.assertTrue(os.path.getsize(path) > 1000, path)
        self.assertTrue(os.path.exists(os.path.join(base, "NOTICE.txt")))


class VocalMidiTest(unittest.TestCase):
    def test_vocal_track_and_formant_fx(self):
        proj = {"tracks": [], "bpm": 120, "sig": 4}
        v = M.new_track(proj, "vocal")
        self.assertEqual((v["type"], v["instrument"], v["name"], v["synth"]["engine"], v["synth"]["preset"]), ("synth", "vocal", "Voice", "voice", "Choir Aah"))
        self.assertEqual([f["type"] for f in v["fx"]], ["eq", "chorus", "reverb"])
        f = M.new_fx("formant", {"vowel": "u", "shift": 1.2})
        self.assertEqual((f["p"]["vowel"], f["p"]["shift"], f["p"]["mix"]), ("u", 1.2, 0.8))
        with self.assertRaises(M.ModelError):
            M.new_fx("formant", {"vowel": "x"})
        for name in ("Choir Ooh", "Solo Hoo", "Solo Haa", "Choir Ohh"):
            self.assertEqual(M.SYNTH_PRESETS[name]["engine"], "voice")


class NaturalDrumTest(unittest.TestCase):
    def test_drum_samples_bundled(self):
        base = os.path.join(os.path.dirname(APP_JS), "samples", "drums")
        for part in ("kick", "snare", "chh", "ohh", "tomh", "tomm", "toml", "crash", "ride"):
            for layer in (1, 2, 3):
                for rr in (1, 2, 3):
                    path = os.path.join(base, f"{part}-{layer}-{rr}.mp3")
                    self.assertTrue(os.path.getsize(path) > 1000, path)

    def test_velocity_chars_and_feel(self):
        self.assertEqual(M.pattern_to_row("x.o.g...", 8), [1, 0, 0.6, 0, 0.3, 0, 0, 0])
        self.assertEqual(M.row_to_pattern([1, 0, 0.6, 0, 0.3, 0.8]), "x.o.gx")
        proj = {"tracks": [], "bpm": 120, "sig": 4}
        d = M.new_track(proj, "drum")
        self.assertEqual(d["feel"]["hum"], 6)
        g = M.new_track(proj, "guitar")
        self.assertNotIn("feel", g)  # guitar / bass timing unchanged


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
        self.assertEqual(re.search(r"KIT_RANGES = \{ pitch: \[(-?\d+), (-?\d+)\], decay: \[([\d.]+), ([\d.]+)\], level: \[([\d.]+), ([\d.]+)\] \}", js).groups(),
                         tuple(str(x) for k in ("pitch", "decay", "level") for x in M.KIT_RANGES[k]))
        self.assertEqual(re.findall(r"'(\w+)'", js.split("const LEGACY_DRUM_IDS = ")[1].split(";")[0]), M.LEGACY_DRUM_IDS)
        self.assertEqual(re.search(r"DEFAULT_GUITAR_PRESET = '([^']+)', DEFAULT_BASS_PRESET = '([^']+)'", js).groups(),
                         (M.DEFAULT_GUITAR_PRESET, M.DEFAULT_BASS_PRESET))
        # every preset's parameter values must match between JS and Python
        for name, params in M.SYNTH_PRESETS.items():
            line = next(l for l in block("SYNTH_PRESETS").splitlines() if l.strip().startswith(f"'{name}':"))
            js_params = dict(re.findall(r"(\w+): ('[^']*'|[-\d.]+)", line.split("{", 1)[1]))
            py_params = {k: (f"'{v}'" if isinstance(v, str) else repr(v)) for k, v in params.items()}
            self.assertEqual({k: v.strip("'") if v.startswith("'") else float(v) for k, v in js_params.items()},
                             {k: v.strip("'") if v.startswith("'") else float(v) for k, v in py_params.items()}, name)
        for preset, rows in M.DRUM_PRESETS.items():
            for part, pat in rows.items():
                self.assertIn(f"{part}: '{pat}'", block("DRUM_PRESETS"), preset)


if __name__ == "__main__":
    unittest.main()
