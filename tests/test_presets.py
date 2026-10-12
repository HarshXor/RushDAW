"""User presets shared by all projects: effect-chain presets (Effects tab) and mastering presets -
CRUD incl. rename in SQLite, the HTTP API, the MCP tools and the JS <-> Python built-in chain sync."""
import json
import re
import tempfile
import unittest
import urllib.error
import urllib.request

from rushdaw import model as M
from rushdaw.storage import Storage, StorageError

from test_mcp import APP_JS, KEY, SSEClient, _Srv


def _js_chain_presets():
    with open(APP_JS, encoding="utf-8") as f:
        js = f.read()
    block = js.split("const FX_CHAIN_PRESETS = {")[1].split("\n};")[0]
    out = {}
    for name, body in re.findall(r"^\s+'([^']+)': (\[.*\]),$", block, re.M):
        body = re.sub(r"([{,]\s*)(\w+):", r'\1"\2":', body.replace("'", '"'))
        out[name] = json.loads(body)
    return out


class FxPresetModelTest(unittest.TestCase):
    def test_builtin_chains_match_app_js(self):
        js = _js_chain_presets()
        self.assertEqual(list(js), list(M.FX_CHAIN_PRESETS))
        self.assertEqual(js, {k: [list(e) for e in v] for k, v in M.FX_CHAIN_PRESETS.items()})
        for name, chain in M.FX_CHAIN_PRESETS.items():  # every built-in chain is valid
            M.clean_fx_chain(chain)

    def test_validation(self):
        with self.assertRaises(M.ModelError):
            M.clean_fx_chain([{"type": "nope"}])
        with self.assertRaises(M.ModelError):
            M.clean_fx_chain([{"type": "dist", "params": {"drive": 99}}])
        with self.assertRaises(M.ModelError):
            M.clean_fx_preset_name("vocal")  # built-in name (case-insensitive)
        chain = M.clean_fx_chain([{"type": "dist", "params": {"drive": 0.5}, "on": False}, ["reverb", {"mix": 0.2}]])
        self.assertEqual([(e["type"], e["on"]) for e in chain], [("dist", False), ("reverb", True)])
        self.assertEqual(chain[0]["p"]["drive"], 0.5)
        self.assertNotIn("id", chain[0])

    def test_storage_crud_and_rename(self):
        with tempfile.TemporaryDirectory() as d:
            st = Storage(d)
            chain = M.clean_fx_chain([["eq", {"low": 2}], ["comp", {"ratio": 3}]])
            st.save_fx_preset("My Vox", chain)
            st.save_fx_preset("Gtr", chain)
            self.assertEqual([p["name"] for p in st.list_fx_presets()], ["Gtr", "My Vox"])
            with self.assertRaises(StorageError):
                st.save_fx_preset("my vox", chain, overwrite=False)  # names are case-insensitive
            st.save_fx_preset("My Vox", chain[:1], overwrite=True)
            self.assertEqual(len(st.get_fx_preset("My Vox")["chain"]), 1)
            self.assertEqual(st.rename_fx_preset("My Vox", "Lead Vox")["name"], "Lead Vox")
            self.assertFalse(st.fx_preset_exists("My Vox"))
            with self.assertRaises(StorageError) as e:
                st.rename_fx_preset("Lead Vox", "gtr")  # clash
            self.assertEqual(e.exception.status, 409)
            self.assertEqual(st.rename_fx_preset("Lead Vox", "LEAD VOX")["name"], "LEAD VOX")  # case change only
            st.delete_fx_preset("LEAD VOX")
            with self.assertRaises(StorageError):
                st.delete_fx_preset("LEAD VOX")
            # mastering presets rename the same way
            st.save_master_preset("Loud", M.master_preset_full({}))
            self.assertEqual(st.rename_master_preset("Loud", "Louder")["name"], "Louder")
            self.assertEqual([p["name"] for p in st.list_master_presets()], ["Louder"])


class PresetApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = _Srv(None)

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def req(self, method, path, body=None):
        r = urllib.request.Request(self.s.base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_fx_and_master_crud(self):
        code, lst = self.req("GET", "/api/fx-presets")
        self.assertEqual((code, len(lst["builtin"]), lst["user"]), (200, len(M.FX_CHAIN_PRESETS), []))
        chain = [{"type": "dist", "params": {"drive": 0.6}}, {"type": "reverb", "params": {"mix": 0.2}}]
        self.assertEqual(self.req("POST", "/api/fx-presets", {"name": "Crust Gtr", "chain": chain})[0], 201)
        self.assertEqual(self.req("POST", "/api/fx-presets", {"name": "Crust Gtr", "chain": chain})[0], 409)
        self.assertEqual(self.req("POST", "/api/fx-presets", {"name": "Vocal", "chain": chain})[0], 400)  # built-in name
        self.assertEqual(self.req("POST", "/api/fx-presets", {"name": "Bad", "chain": [{"type": "x"}]})[0], 400)
        code, r = self.req("POST", "/api/fx-presets/rename", {"from": "Crust Gtr", "to": "Crust Guitar"})
        self.assertEqual((code, r["name"], [e["type"] for e in r["chain"]]), (200, "Crust Guitar", ["dist", "reverb"]))
        self.assertEqual([p["name"] for p in self.req("GET", "/api/fx-presets")[1]["user"]], ["Crust Guitar"])
        self.assertEqual(self.req("DELETE", "/api/fx-presets/Crust%20Guitar")[0], 200)
        self.assertEqual(self.req("DELETE", "/api/fx-presets/Crust%20Guitar")[0], 404)
        # mastering rename
        self.assertEqual(self.req("POST", "/api/master-presets", {"name": "Mine", "params": {"makeup": 4}})[0], 201)
        self.assertEqual(self.req("POST", "/api/master-presets/rename", {"from": "Mine", "to": "Metal"})[0], 400)  # built-in
        code, r = self.req("POST", "/api/master-presets/rename", {"from": "Mine", "to": "Mine 2"})
        self.assertEqual((code, r["name"], r["params"]["makeup"]), (200, "Mine 2", 4))


class PresetMcpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = _Srv(KEY)
        cls.c = SSEClient(cls.s)
        cls.n = 1000

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        cls.s.close()

    def call(self, _tool, ok=True, **args):
        PresetMcpTest.n += 1
        res = self.c.request("tools/call", {"name": _tool, "arguments": args}, self.n)["result"]
        self.assertEqual(res["isError"], not ok, res["content"][0]["text"])
        return res["structuredContent"]

    def test_fx_and_master_preset_tools(self):
        pid = self.call("create_project", name="FX presets", template="band")["project_id"]
        self.call("set_track_effects", project_id=pid, track="Guitar 1", effects=[{"type": "dist", "params": {"drive": 0.66}}, {"type": "delay"}])
        saved = self.call("save_fx_preset", name="My Lead", project_id=pid, track="Guitar 1")["saved"]
        self.assertEqual([e["type"] for e in saved["chain"]], ["dist", "delay"])
        lst = self.call("list_fx_presets")
        self.assertIn("Vocal", [p["name"] for p in lst["builtin"]])
        self.assertEqual([(p["name"], p["custom"]) for p in lst["user"]], [("My Lead", True)])
        # usable in another project
        pid2 = self.call("create_project", name="Other", template="band")["project_id"]
        r = self.call("apply_fx_preset", project_id=pid2, track="Bass", preset="my lead")
        self.assertEqual((r["preset"], r["custom"], [f["type"] for f in r["track"]["fx"]]), ("My Lead", True, ["dist", "delay"]))
        self.assertEqual(r["track"]["fx"][0]["params"]["drive"], 0.66)
        self.assertEqual(self.call("apply_fx_preset", project_id=pid2, track="Bass", preset="Lo-Fi")["custom"], False)
        self.assertIn("unknown effect preset", self.call("apply_fx_preset", ok=False, project_id=pid2, track="Bass", preset="Nope")["error"])
        self.assertEqual(self.call("rename_fx_preset", name="My Lead", new_name="Lead Crunch")["preset"]["name"], "Lead Crunch")
        self.assertIn("built-in", self.call("rename_fx_preset", ok=False, name="Vocal", new_name="X")["error"])
        self.assertIn("built-in", self.call("delete_fx_preset", ok=False, name="Bass")["error"])
        self.call("delete_fx_preset", name="Lead Crunch")
        self.assertEqual(self.call("list_fx_presets")["user"], [])
        # mastering presets: rename + custom flag
        self.call("save_master_preset", name="My Master", params={"makeup": 5})
        self.assertTrue(self.call("list_master_presets")["user"][0]["custom"])
        self.assertEqual(self.call("rename_master_preset", name="My Master", new_name="My Master 2")["preset"]["name"], "My Master 2")
        self.assertIn("built-in", self.call("rename_master_preset", ok=False, name="Metal", new_name="X")["error"])
        self.call("delete_master_preset", name="My Master 2")



if __name__ == "__main__":
    unittest.main()
