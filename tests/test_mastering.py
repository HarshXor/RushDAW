"""Mastering: preset naming ("X" untouched / "Custom" once edited or none), user presets (SQLite) with export/import,
the HTTP API, the MCP tools and the JS <-> Python constant sync."""
import json
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.request

from rushdaw import model as M
from rushdaw.storage import Storage

import test_mcp as T  # (module import: keeps McpTest itself from being collected twice)
from test_mcp import APP_JS, _Srv


class MasterModelTest(unittest.TestCase):
    def test_label_states(self):
        m = M.default_master()
        self.assertEqual(M.master_label(m), "Default")
        M.apply_master_preset(m, "Metal", M.MASTER_PRESETS["Metal"])
        self.assertEqual(M.master_label(m), "Metal")
        m["makeup"] = 3.5
        self.assertEqual(M.master_label(m), "Custom")
        m["makeup"] = M.master_preset_full(M.MASTER_PRESETS["Metal"])["makeup"]
        self.assertEqual(M.master_label(m), "Metal")  # back to the preset values -> plain name again
        m["reverbSize"] = 5  # send bus is not part of a preset
        self.assertEqual(M.master_label(m), "Metal")
        m["preset"] = None
        self.assertEqual(M.master_label(m), "Custom")

    def test_migrate_old_master(self):
        old = {"vol": 1, "eqLow": 0, "eqMid": 0, "eqHigh": 0, "compThr": -18, "compRatio": 2.5, "compAtk": 0.01,
               "compRel": 0.25, "makeup": 3, "ceiling": -1, "reverbSize": 2.5, "delayDiv": 0.75, "delayFb": 0.35}
        self.assertEqual(M.master_label(M.migrate_master(old)), "Default")
        self.assertEqual(M.master_label(M.migrate_master({**old, "makeup": 9})), "Custom")
        # new keys default to the neutral values = the old chain
        m = M.migrate_master(old)
        self.assertEqual((m["hpf"], m["sat"], m["width"], m["compKnee"], m["limRel"]), (20, 0, 1, 30, 0.08))

    def test_every_preset_in_range(self):
        for name, p in M.MASTER_PRESETS.items():
            for k, v in M.master_preset_full(p).items():
                lo, hi = M.MASTER_PARAMS[k]
                self.assertTrue(lo <= v <= hi, f"{name}.{k}={v} outside {lo}..{hi}")

    def test_validation(self):
        with self.assertRaises(M.ModelError):
            M.clean_master_params({"makeup": 99})
        with self.assertRaises(M.ModelError):
            M.clean_master_params({"bogus": 1})
        with self.assertRaises(M.ModelError):
            M.clean_preset_name("balanced")  # built-in name (case-insensitive)
        with self.assertRaises(M.ModelError):
            M.clean_preset_name("Custom")
        self.assertEqual(M.clean_master_params({"sat": 0.5, "reverbSize": 3})["sat"], 0.5)  # send params ignored

    def test_storage_and_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            st = Storage(d)
            st.save_master_preset("Mine", M.clean_master_params({"makeup": 5}))
            self.assertEqual([p["name"] for p in st.list_master_presets()], ["Mine"])
            f = M.master_preset_file(st.list_master_presets() + [{"name": "Metal", "params": M.MASTER_PRESETS["Metal"]}])
            res = M.import_master_presets(st, json.dumps(f))["imported"]
            self.assertEqual([r["name"] for r in res], ["Mine (2)", "Metal (imported)"])  # never overwrites / clashes
            self.assertEqual(st.get_master_preset("mine (2)")["params"]["makeup"], 5)
            st.delete_master_preset("Mine")
            self.assertEqual(len(st.list_master_presets()), 2)
            with self.assertRaises(M.ModelError):
                M.import_master_presets(st, '{"app": "other", "presets": []}')


class MasterApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = _Srv(None)

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def req(self, method, path, body=None, status=200):
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.s.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r) as resp:
                self.assertEqual(resp.status, status)
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, status, e.read())
            return json.loads(e.read() or b"{}")

    def test_crud_import(self):
        lst = self.req("GET", "/api/master-presets")
        self.assertEqual([p["name"] for p in lst["builtin"]], list(M.MASTER_PRESETS))
        self.assertEqual(lst["user"], [])
        self.req("POST", "/api/master-presets", {"name": "Live Room", "params": {"width": 1.3}}, 201)
        self.req("POST", "/api/master-presets", {"name": "Live Room", "params": {}, "overwrite": False}, 409)
        self.req("POST", "/api/master-presets", {"name": "Loud Pop", "params": {}}, 400)
        self.req("POST", "/api/master-presets", {"name": "X", "params": {"ceiling": 4}}, 400)
        f = M.master_preset_file([{"name": "Live Room", "params": {"width": 1.3}}])
        imp = self.req("POST", "/api/master-presets/import", json.dumps(f).encode(), 201)
        self.assertEqual(imp["imported"][0]["name"], "Live Room (2)")
        names = [p["name"] for p in self.req("GET", "/api/master-presets")["user"]]
        self.assertEqual(names, ["Live Room", "Live Room (2)"])
        self.req("DELETE", "/api/master-presets/" + urllib.request.quote("Live Room (2)"))
        self.req("DELETE", "/api/master-presets/Nope", None, 404)


class MasterMcpTest(T.McpTest):
    """Re-uses McpTest's server/SSE client + call(); only the mastering tests run here."""

    def rpc(self, method, params=None):
        MasterMcpTest.n += 1
        out = self.c.request(method, params, MasterMcpTest.n)
        self.assertEqual(out["id"], MasterMcpTest.n)
        return out

    def test_mastering_tools(self):
        pid = self.call("create_project", name="Master me", template="metal")["project_id"]
        st = self.call("list_master_presets", project_id=pid)
        self.assertEqual(st["project"]["preset_label"], "Default")
        r = self.call("set_master", project_id=pid, preset="punk / crust")  # case-insensitive
        self.assertEqual((r["preset_label"], r["preset"]), ("Punk / Crust", "Punk / Crust"))
        before = [p for p in self.call("list_master_presets")["builtin"] if p["name"] == "Punk / Crust"]
        r = self.call("set_master", project_id=pid, params={"sat": 0.5})
        # edited -> detached: just "Custom", stored in the project only
        self.assertEqual((r["preset_label"], r["preset"]), ("Custom", None))
        self.assertEqual(self.call("get_project", project_id=pid, detail=False)["master_preset_label"], "Custom")
        after = [p for p in self.call("list_master_presets")["builtin"] if p["name"] == "Punk / Crust"]
        self.assertEqual(before, after)  # the preset itself is untouched
        # effect chains: a loaded preset becomes "Custom" once edited, the saved preset stays as it was
        self.call("save_fx_preset", name="FxKeep", effects=[{"type": "dist", "params": {"drive": 0.4}}])
        self.call("apply_fx_preset", project_id=pid, track=1, preset="FxKeep")
        tr = lambda: self.call("get_project", project_id=pid)["tracks"][0]
        self.assertEqual(tr()["fx_preset"], "FxKeep")
        self.call("add_effect", project_id=pid, track=1, type="reverb")
        self.assertEqual(tr()["fx_preset"], "Custom")
        kept = [p for p in self.call("list_fx_presets")["user"] if p["name"] == "FxKeep"][0]
        self.assertEqual([e["type"] for e in kept["chain"]], ["dist"])
        saved = self.call("save_master_preset", name="Crusty", project_id=pid)
        self.assertEqual(saved["project"]["preset_label"], "Crusty")
        self.assertEqual(saved["saved"]["params"]["sat"], 0.5)
        self.call("save_master_preset", ok=False, name="Crusty", params={"sat": 0.1})  # exists, no overwrite
        self.call("save_master_preset", ok=False, name="Metal")  # built-in name
        r = self.call("set_master", project_id=pid, preset="Custom")
        self.assertEqual(r["preset_label"], "Custom")
        exp = self.call("export_master_preset", names=["Crusty", "Warm"])["file"]
        self.assertEqual([p["name"] for p in exp["presets"]], ["Crusty", "Warm"])
        imp = self.call("import_master_presets", data=exp)["imported"]
        self.assertEqual([x["name"] for x in imp], ["Crusty (2)", "Warm (imported)"])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.rushmaster.json")
            self.call("export_master_preset", project_id=pid, path=path)
            self.assertEqual(self.call("import_master_presets", path=path)["imported"][0]["name"], "Custom (imported)")  # "Custom" is reserved
        self.assertEqual(self.call("set_master", project_id=pid, preset="crusty (2)")["preset_label"], "Crusty (2)")
        self.call("delete_master_preset", ok=False, name="Balanced")
        self.call("delete_master_preset", name="Crusty (2)")
        self.call("set_master", ok=False, project_id=pid, preset="Nope")
        self.call("set_master", ok=False, project_id=pid, params={"width": 3})


# don't run the inherited McpTest tests a second time
for _n in [n for n in dir(T.McpTest) if n.startswith("test_")]:
    setattr(MasterMcpTest, _n, None)


class MasterSyncTest(unittest.TestCase):
    def test_js_constants_match_model(self):
        with open(APP_JS, encoding="utf-8") as f:
            js = f.read()
        grab = lambda name: json.loads(re.search(rf"^const {name} = (.+);$", js, re.M).group(1))
        self.assertEqual(grab("MASTER_KEYS"), M.MASTER_KEYS)
        self.assertEqual(grab("MASTER_DEFAULTS"), M.MASTER_DEFAULT)
        self.assertEqual({k: tuple(v) for k, v in grab("MASTER_RANGES").items()}, M.MASTER_PARAMS)
        block = js.split("const MASTER_PRESETS = {")[1].split("\n};")[0]
        presets = {n: json.loads(v) for n, v in re.findall(r"^\s+'([^']+)': (\{.*\}),$", block, re.M)}
        self.assertEqual(presets, M.MASTER_PRESETS)
        self.assertEqual(list(presets), list(M.MASTER_PRESETS))


if __name__ == "__main__":
    unittest.main()
