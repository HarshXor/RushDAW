"""Resize from the front (left edge): model.trim_region_start + MCP update_clip(trim_start_beats)."""
import unittest

from rushdaw import model as M

import test_mcp as T  # module import: keeps McpTest from being collected twice


def drum_region(start=4, steps=16):
    t = {"type": "drum", "clips": []}
    c = {"id": "c1", "kind": "midi", "start": start, "len": steps / 4,
         "pattern": {"bars": 1, "grid": [[1 if i % 4 == 0 else 0 for i in range(steps)] for _ in M.DRUM_IDS]}}
    t["clips"].append(c)
    return t, c


def hits(c, row=0):
    return [c["start"] + i / 4 for i, v in enumerate(c["pattern"]["grid"][row]) if v]


class TrimStartModelTest(unittest.TestCase):
    proj = {"bpm": 120, "sig": 4}

    def test_drum_shrink_and_extend_keep_song_positions(self):
        t, c = drum_region()
        before = hits(c)                                  # beats 4, 5, 6, 7
        M.trim_region_start(self.proj, t, c, 1.25)        # cut 5 steps from the front
        self.assertEqual((c["start"], c["len"]), (5.25, 2.75))
        self.assertEqual(hits(c), [b for b in before if b >= 5.25])
        self.assertEqual(len(c["pattern"]["grid"][0]), 11)
        M.trim_region_start(self.proj, t, c, -3.25)       # extend back to beat 2: new steps are empty
        self.assertEqual((c["start"], c["len"]), (2.0, 6.0))
        self.assertEqual(hits(c), [6.0, 7.0])
        M.trim_region_start(self.proj, t, c, -99)         # never before bar 1
        self.assertEqual(c["start"], 0)
        M.trim_region_start(self.proj, t, c, 99)          # keeps at least one step
        self.assertEqual(c["len"], 0.25)

    def test_notes_crossing_the_cut_are_shortened(self):
        t = {"type": "synth", "clips": []}
        c = {"id": "c", "kind": "midi", "start": 0, "len": 4, "notes": [{"p": 40, "s": 0, "l": 2}, {"p": 43, "s": 2, "l": 8}, {"p": 45, "s": 12, "l": 4}]}
        M.trim_region_start(self.proj, t, c, 1)           # 4 steps
        self.assertEqual(c["notes"], [{"p": 43, "s": 0, "l": 6}, {"p": 45, "s": 8, "l": 4}])
        M.trim_region_start(self.proj, t, c, -1)
        self.assertEqual(c["notes"], [{"p": 43, "s": 4, "l": 6}, {"p": 45, "s": 12, "l": 4}])

    def test_audio_moves_offset(self):
        t = {"type": "audio", "clips": []}
        c = {"id": "a", "kind": "audio", "start": 8, "offset": 1.0, "dur": 4.0}  # 120 bpm: 0.5 s per beat
        M.trim_region_start(self.proj, t, c, 2)
        self.assertEqual((c["start"], c["offset"], c["dur"]), (10, 2.0, 3.0))
        M.trim_region_start(self.proj, t, c, -10)         # only back to the start of the recording
        self.assertEqual((c["start"], c["offset"], c["dur"]), (6, 0.0, 5.0))


class MonoNotesTest(unittest.TestCase):
    def test_one_pitch_one_voice(self):
        out = M.mono_notes([{"p": 57, "s": 0, "l": 16}, {"p": 57, "s": 4, "l": 4}, {"p": 60, "s": 0, "l": 16},
                            {"p": 57, "s": 4, "l": 8, "v": 0.5}])
        self.assertEqual(out, [{"p": 57, "s": 0, "l": 4}, {"p": 60, "s": 0, "l": 16}, {"p": 57, "s": 4, "l": 8, "v": 0.5}])


class SustainVsDecayTest(unittest.TestCase):
    def test_js_and_python_agree(self):
        import re
        with open(T.APP_JS, encoding="utf-8") as f:
            js = f.read()
        self.assertEqual(sorted(re.findall(r"(\w+): \{ name: '[^']+', lo: \d+, hi: \d+, sustained: true \}", js)), sorted(M.SUSTAINED_SAMPLE_SETS))
        legacy = dict((k, float(v)) for k, v in re.findall(r"'([^']+)': ([0-9.]+)", js.split("const LEGACY_DECAY_SUS = {")[1].split("};")[0]))
        self.assertEqual(legacy, M.LEGACY_DECAY_SUS)

    def test_decay_presets_ring_naturally_and_old_tracks_migrate(self):
        for name, p in M.SYNTH_PRESETS.items():
            if p.get("engine") == "sample" and p["sample"] not in M.SUSTAINED_SAMPLE_SETS and name != "Palm Mute Guitar":
                self.assertEqual(p["susLevel"], 1, name)
        proj = {"tracks": [{"type": "synth", "instrument": "guitar", "synth": {**M.SYNTH_PRESETS["Clean Guitar"], "preset": "Clean Guitar", "susLevel": 0.35}},
                           {"type": "synth", "instrument": "guitar", "synth": {**M.SYNTH_PRESETS["Clean Guitar"], "preset": "Clean Guitar", "susLevel": 0.5}}]}
        M.migrate_strings(proj)
        self.assertEqual([t["synth"]["susLevel"] for t in proj["tracks"]], [1, 0.5])  # user-edited value is kept


class TrimStartMcpTest(T.McpTest):
    def rpc(self, method, params=None):
        TrimStartMcpTest.n += 1
        out = self.c.request(method, params, TrimStartMcpTest.n)
        self.assertEqual(out["id"], TrimStartMcpTest.n)
        return out

    def test_update_clip_trim_start(self):
        pid = self.call("create_project", name="Trim", template="metal")["project_id"]
        proj = self.call("get_project", project_id=pid)
        drums = next(t for t in proj["tracks"] if t["type"] == "drum")
        clip = drums["clips"][0]
        r = self.call("update_clip", project_id=pid, clip_id=clip["id"], trim_start_beats=2)["clip"]
        self.assertEqual((r["start_beat"], r["length_beats"]), (clip["start_beat"] + 2, clip["length_beats"] - 2))
        r = self.call("update_clip", project_id=pid, clip_id=clip["id"], trim_start_beats=-2)["clip"]
        self.assertEqual((r["start_beat"], r["length_beats"]), (clip["start_beat"], clip["length_beats"]))


    def test_set_notes_never_doubles_a_pitch(self):
        pid = self.call("create_project", name="Mono", template="empty")["project_id"]
        self.call("add_track", project_id=pid, type="vocal", name="Voice")
        r = self.call("set_notes", project_id=pid, track="Voice", notes=[
            {"note": "A3", "step": 1, "length": 16}, {"note": "A3", "step": 1, "length": 8}, {"note": "A3", "step": 9, "length": 8}])
        got = [(n["pitch"], n["step"], n["length"]) for n in r["track"]["notes"]]
        self.assertEqual(got, [(57, 1, 8), (57, 9, 8)])  # duplicate at step 1: last wins; never two voices on A3
        proj = self.call("get_project", project_id=pid)
        clip = next(t for t in proj["tracks"] if t["name"] == "Voice")["clips"][0]
        self.assertEqual([(n["step"], n["length"]) for n in clip["notes"]], [(1, 8), (9, 8)])


for _n in [n for n in dir(T.McpTest) if n.startswith("test_")]:
    setattr(TrimStartMcpTest, _n, None)

if __name__ == "__main__":
    unittest.main()
