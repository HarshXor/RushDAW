"""MCP (Model Context Protocol) server for RushDAW.

Transport: HTTP + SSE only.  ``GET /sse`` opens an event stream whose first
``endpoint`` event tells the client where to ``POST`` JSON-RPC messages
(``/messages?session_id=...``); responses are delivered as ``message`` events.
Auth: ``Authorization: Bearer <api key>`` on both endpoints, key given with
``rushdaw --api-key KEY`` (or ``RUSHDAW_API_KEY``).  The key is optional: without
it MCP is simply off.

Every editing tool loads the latest revision of a project, applies the change
and stores the result as a NEW revision (message ``MCP: ...``), so all MCP
edits appear in the project's history and can be restored/undone.
"""
import json
import threading

from . import __version__
from . import model as M
from .storage import StorageError

PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")  # first = default (HTTP+SSE era)
_edit_lock = threading.Lock()  # serialise read-modify-write of project documents

INSTRUCTIONS = (
    "RushDAW MCP: read and edit RushDAW projects (songs). Every edit creates a new revision in the "
    "project history. Tracks (layers) can be referenced by id, exact name or 1-based position. "
    "Drum pads: 16 steps per 4/4 bar (16th notes); steps are 1-based. Patterns are strings like "
    "'x...x...x...x...' (x = hit). Call get_reference for drum parts, presets and effect parameters."
)


class ToolError(Exception):
    pass


# --------------------------------------------------------------- helpers
def _S(**props):
    """Small JSON-schema builder: _S(project_id=('string', 'desc', True), ...)."""
    properties, required = {}, []
    for name, spec in props.items():
        typ, desc = spec[0], spec[1]
        req = spec[2] if len(spec) > 2 else False
        extra = spec[3] if len(spec) > 3 else {}
        p = {"description": desc, **extra}
        if typ:
            p["type"] = typ
        properties[name] = p
        if req:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


PID = ("string", "Project id (from list_projects / create_project).", True)
TRACK = (None, "Track (layer): id, exact name, or 1-based position.", True, {"type": ["string", "integer"]})
PART = ("string", "Drum part: kick, snare, ride, chh (closed hi-hat), ohh (open hi-hat), tomh, toml, rim/china, crash.", True)


class RushDAWMCP:
    def __init__(self, storage):
        self.st = storage
        self.tools = self._tools()

    # ------------------------------------------------------- document io
    def _load(self, pid, rev=None):
        try:
            data, r, meta = self.st.read_revision(pid, rev)
        except StorageError as e:
            raise ToolError(str(e))
        return json.loads(data), r, meta

    def _edit(self, pid, message, fn):
        """Load head revision, run fn(doc) -> result, save as new revision."""
        with _edit_lock:
            doc, _, _ = self._load(pid)
            result = fn(doc)
            try:
                saved = self.st.save_revision(pid, json.dumps(doc).encode(), ("MCP: " + message)[:200])
            except StorageError as e:
                raise ToolError(str(e))
        out = {"revision": saved["number"]}
        if isinstance(result, dict):
            out.update(result)
        return out

    def _track_edit(self, a, message, fn):
        def run(doc):
            proj = doc["project"]
            t = M.find_track(proj, a["track"])
            res = fn(proj, t)
            return {"track": M.track_summary(proj, t), **(res or {})}
        return self._edit(a["project_id"], message, run)

    @staticmethod
    def _drum(t):
        if t["type"] != "drum":
            raise M.ModelError(f"track '{t['name']}' is not a drum track")
        return t

    @staticmethod
    def _synth(t):
        if t["type"] != "synth":
            raise M.ModelError(f"track '{t['name']}' is not a synth/guitar (MIDI) track")
        return t

    # ------------------------------------------------------- tool table
    def _tools(self):
        T = {}

        def tool(name, description, schema, readonly=False):
            def deco(fn):
                T[name] = {"fn": fn, "def": {"name": name, "description": description, "inputSchema": schema,
                                             "annotations": {"readOnlyHint": readonly}}}
                return fn
            return deco

        # ---------------- reference / projects
        @tool("get_reference", "List drum parts, drum presets, synth/guitar presets, effect types with parameter ranges, master presets and template names.", _S(), True)
        def get_reference(a):
            return {"drum_parts": [{"id": p, "name": n} for p, n in M.DRUMS], "drum_presets": list(M.DRUM_PRESETS),
                    "synth_presets": list(M.SYNTH_PRESETS), "synth_params": {k: v if isinstance(v, list) else {"min": v[0], "max": v[1]} for k, v in M.SYNTH_PARAMS.items()},
                    "effects": {k: {p: ({"default": s[0], "choices": s[1]} if isinstance(s[1], list) else {"default": s[0], "min": s[1], "max": s[2]}) for p, s in v.items()} for k, v in M.FX_TYPES.items()},
                    "master_params": {k: {"min": v[0], "max": v[1]} for k, v in M.MASTER_PARAMS.items()}, "master_presets": list(M.MASTER_PRESETS),
                    "track_types": list(M.TRACK_TYPES), "templates": ["empty", "metal", "band"],
                    "drum_tuning": {k: {"min": v[0], "max": v[1], "default": M.KIT_DEFAULT[k]} for k, v in M.KIT_RANGES.items()},
                    "note_range": {"min": M.LOW_NOTE, "max": M.HIGH_NOTE, "min_name": M.note_name(M.LOW_NOTE), "max_name": M.note_name(M.HIGH_NOTE)}}

        @tool("list_projects", "List all projects (id, name, bpm, latest revision, last update).", _S(), True)
        def list_projects(a):
            return {"projects": [{"id": p["id"], "name": p["name"], "bpm": p["bpm"], "time_signature": f"{p['sig']}/4",
                                  "revision": p["head_revision"], "revisions": p["revision_count"], "updated_at": p["updated_at"]}
                                 for p in self.st.list_projects()]}

        @tool("get_project", "Get a project's full content: tracks/layers with mixer settings, effects, clips, drum pads (as x/. strings), drum tuning, synth notes, master.",
              _S(project_id=PID, revision=("integer", "Revision number (default: latest)."),
                 detail=("boolean", "Include pads/notes (default true).")), True)
        def get_project(a):
            doc, r, meta = self._load(a["project_id"], a.get("revision"))
            return {"id": meta["id"], "name": meta["name"], "revision": r["number"], "latest_revision": meta["head_revision"],
                    **M.project_summary(doc, a.get("detail", True))}

        @tool("create_project", "Create a new project. Templates: empty (one audio track), metal (drums, bass, guitar, audio), band (metal + Vocal track with vocal FX).",
              _S(name=("string", "Project name.", True), bpm=("number", "Tempo 40-240 (default 180)."),
                 time_signature=("integer", "Beats per bar: 3, 4 or 6 (default 4).", False, {"enum": [3, 4, 6]}),
                 template=("string", "empty | metal | band (default metal).", False, {"enum": ["empty", "metal", "band"]})))
        def create_project(a):
            bpm = M.num(a.get("bpm", 180), "bpm", 40, 240)
            sig = int(a.get("time_signature", 4))
            if sig not in (3, 4, 6):
                raise M.ModelError("time_signature must be 3, 4 or 6")
            doc = M.new_document(a["name"].strip()[:120] or "New Song", bpm, sig)
            self._apply_template(doc["project"], a.get("template", "metal"))
            meta = self.st.create_project(doc["project"]["title"], bpm, sig)
            self.st.save_revision(meta["id"], json.dumps(doc).encode(), "MCP: created")
            return {"project_id": meta["id"], "revision": 1, **M.project_summary(doc, False)}

        @tool("update_project", "Change project title, tempo (BPM) or time signature.",
              _S(project_id=PID, title=("string", "New title."), bpm=("number", "Tempo 40-240."),
                 time_signature=("integer", "3, 4 or 6.", False, {"enum": [3, 4, 6]})))
        def update_project(a):
            def run(doc):
                proj = doc["project"]
                if "title" in a:
                    proj["title"] = str(a["title"]).strip()[:120] or proj["title"]
                if "bpm" in a:
                    proj["bpm"] = M.num(a["bpm"], "bpm", 40, 240)
                if "time_signature" in a:
                    sig = int(a["time_signature"])
                    if sig not in (3, 4, 6):
                        raise M.ModelError("time_signature must be 3, 4 or 6")
                    proj["sig"] = sig
                    for t in proj["tracks"]:
                        if t["type"] == "drum":
                            M.resize_grid(proj, t)
                        if t["type"] == "synth":
                            t["notes"] = [n for n in t["notes"] if n["s"] < M.pat_steps(proj, t)]
                return {"title": proj["title"], "bpm": proj["bpm"], "time_signature": f"{proj['sig']}/4"}
            return self._edit(a["project_id"], "update project", run)

        @tool("list_revisions", "List a project's revision history (newest first).", _S(project_id=PID), True)
        def list_revisions(a):
            try:
                p = self.st.get_project(a["project_id"])
            except StorageError as e:
                raise ToolError(str(e))
            return {"latest": p["head_revision"], "revisions": [{"revision": r["number"], "message": r["message"], "created_at": r["created_at"],
                                                                 "tracks": r["track_count"], "size": r["size"]} for r in p["revisions"]]}

        @tool("restore_revision", "Make an older revision the latest again (creates a new revision; nothing is lost).",
              _S(project_id=PID, revision=("integer", "Revision number to restore.", True)))
        def restore_revision(a):
            try:
                r = self.st.restore_revision(a["project_id"], int(a["revision"]))
            except StorageError as e:
                raise ToolError(str(e))
            return {"revision": r["number"], "restored_from": int(a["revision"])}

        @tool("delete_project", "Move a project to the Trash (soft delete; files and history are kept, restorable in the UI).", _S(project_id=PID))
        def delete_project(a):
            try:
                return self.st.delete_project(a["project_id"])
            except StorageError as e:
                raise ToolError(str(e))

        @tool("set_master", "Edit master bus / mastering: apply a master preset and/or set parameters (vol, eqLow, eqMid, eqHigh, compThr, compRatio, compAtk, compRel, makeup, ceiling, reverbSize, delayDiv, delayFb).",
              _S(project_id=PID, preset=("string", "Master preset name (see get_reference)."),
                 params=("object", "Parameter values, e.g. {\"makeup\": 4, \"ceiling\": -1}.")))
        def set_master(a):
            def run(doc):
                m = {**M.MASTER_DEFAULT, **(doc["project"].get("master") or {})}
                if a.get("preset"):
                    if a["preset"] not in M.MASTER_PRESETS:
                        raise M.ModelError("unknown master preset. Presets: " + ", ".join(M.MASTER_PRESETS))
                    m.update(M.MASTER_PRESETS[a["preset"]])
                for k, v in (a.get("params") or {}).items():
                    if k not in M.MASTER_PARAMS:
                        raise M.ModelError(f"unknown master parameter '{k}'. Parameters: " + ", ".join(M.MASTER_PARAMS))
                    m[k] = M.num(v, k, *M.MASTER_PARAMS[k])
                doc["project"]["master"] = m
                return {"master": m}
            return self._edit(a["project_id"], "master " + (a.get("preset") or "params"), run)

        # ---------------- tracks / layers
        @tool("add_track", "Add a track (layer): audio, drum, synth or guitar. MIDI tracks get a pattern region by default.",
              _S(project_id=PID, type=("string", "audio | drum | synth | guitar", True, {"enum": list(M.TRACK_TYPES)}),
                 name=("string", "Track name."), region_start_beat=("number", "Start beat of the first pattern region (default 0)."),
                 region_length_beats=("number", "Length in beats of the first region (default 4 bars)."),
                 add_region=("boolean", "Add a pattern region for drum/synth/guitar (default true).")))
        def add_track(a):
            def run(doc):
                proj = doc["project"]
                t = M.new_track(proj, a["type"], a.get("name"))
                if t["type"] != "audio" and a.get("add_region", True):
                    t["clips"].append({"id": M.nid("c"), "kind": "midi", "start": M.num(a.get("region_start_beat", 0), "region_start_beat", 0, 100000),
                                       "len": M.num(a.get("region_length_beats", proj["sig"] * 4), "region_length_beats", 0.25, 100000)})
                return {"track": M.track_summary(proj, t)}
            return self._edit(a["project_id"], f"add {a['type']} track", run)

        @tool("update_track", "Mixer settings of a track/layer: name, volume (0-1.5, 0.8 default), pan (-1 left .. 0 center .. 1 right), mute, solo, channel EQ (dB), compressor, reverb/delay sends.",
              _S(project_id=PID, track=TRACK, name=("string", "New name."), volume=("number", "0 - 1.5"), pan=("number", "-1 (hard left) .. 0 (center) .. 1 (hard right)"),
                 mute=("boolean", "Mute the layer."), solo=("boolean", "Solo the layer."), eq_low=("number", "-15..15 dB"), eq_mid=("number", "-15..15 dB"), eq_high=("number", "-15..15 dB"),
                 comp_threshold=("number", "-60..0 dB"), comp_ratio=("number", "1..20"), reverb_send=("number", "0..1"), delay_send=("number", "0..1"), color=("string", "CSS color, e.g. #00e5ff")))
        def update_track(a):
            def fn(proj, t):
                if "name" in a:
                    t["name"] = str(a["name"]).strip()[:60] or t["name"]
                if "volume" in a:
                    t["vol"] = M.num(a["volume"], "volume", 0, 1.5)
                if "pan" in a:
                    t["pan"] = round(M.num(a["pan"], "pan", -1, 1), 2)
                for k in ("mute", "solo"):
                    if k in a:
                        t[k] = bool(a[k])
                for k, key in (("eq_low", "low"), ("eq_mid", "mid"), ("eq_high", "high")):
                    if k in a:
                        t["eq"][key] = M.num(a[k], k, -15, 15)
                if "comp_threshold" in a:
                    t["comp"]["thr"] = M.num(a["comp_threshold"], "comp_threshold", -60, 0)
                if "comp_ratio" in a:
                    t["comp"]["ratio"] = M.num(a["comp_ratio"], "comp_ratio", 1, 20)
                if "reverb_send" in a:
                    t["rev"] = M.num(a["reverb_send"], "reverb_send", 0, 1)
                if "delay_send" in a:
                    t["dly"] = M.num(a["delay_send"], "delay_send", 0, 1)
                if "color" in a:
                    t["color"] = str(a["color"])[:20]
            return self._track_edit(a, "update track", fn)

        @tool("delete_track", "Remove a track/layer from the project (previous revisions keep it).", _S(project_id=PID, track=TRACK))
        def delete_track(a):
            def run(doc):
                proj = doc["project"]
                t = M.find_track(proj, a["track"])
                proj["tracks"] = [x for x in proj["tracks"] if x is not t]
                return {"deleted": {"id": t["id"], "name": t["name"]}}
            return self._edit(a["project_id"], "delete track", run)

        @tool("duplicate_track", "Copy a track/layer (with clips, pads, notes, effects) and insert it right below the original.",
              _S(project_id=PID, track=TRACK, name=("string", "Name of the copy (default '<name> (copy)').")))
        def duplicate_track(a):
            def run(doc):
                proj = doc["project"]
                src = M.find_track(proj, a["track"])
                t = M.clone(src)
                t["id"] = M.nid("t")
                t["name"] = (a.get("name") or src["name"] + " (copy)")[:60]
                t["solo"] = t["arm"] = False
                for c in t["clips"]:
                    c["id"] = M.nid("c")
                for f in t.get("fx", []):
                    f["id"] = M.nid("f")
                proj["tracks"].insert(proj["tracks"].index(src) + 1, t)
                return {"track": M.track_summary(proj, t)}
            return self._edit(a["project_id"], "duplicate track", run)

        @tool("move_track", "Reorder a track/layer to a 1-based position.", _S(project_id=PID, track=TRACK, position=("integer", "New 1-based position.", True)))
        def move_track(a):
            def run(doc):
                proj = doc["project"]
                t = M.find_track(proj, a["track"])
                proj["tracks"].remove(t)
                pos = int(M.clamp(int(a["position"]), 1, len(proj["tracks"]) + 1))
                proj["tracks"].insert(pos - 1, t)
                return {"order": [x["name"] for x in proj["tracks"]]}
            return self._edit(a["project_id"], "move track", run)

        # ---------------- effects
        @tool("set_track_effects", "Replace a track's insert effect chain. Effects run in list order. Types: eq, comp, dist, filter, chorus, tremolo, delay, reverb (params: see get_reference).",
              _S(project_id=PID, track=TRACK, effects=("array", "List of {type, params?, on?}. Empty list removes all effects.", True,
                                                       {"items": {"type": "object", "properties": {"type": {"type": "string"}, "params": {"type": "object"}, "on": {"type": "boolean"}}, "required": ["type"]}})))
        def set_track_effects(a):
            def fn(proj, t):
                t["fx"] = [M.new_fx(e.get("type"), e.get("params"), e.get("on", True)) for e in a["effects"]]
            return self._track_edit(a, "set effects", fn)

        @tool("add_effect", "Add one insert effect to a track (appended, or at a 1-based position).",
              _S(project_id=PID, track=TRACK, type=("string", "eq | comp | dist | filter | chorus | tremolo | delay | reverb", True, {"enum": list(M.FX_TYPES)}),
                 params=("object", "Effect parameters."), position=("integer", "1-based position in the chain.")))
        def add_effect(a):
            def fn(proj, t):
                fx = M.new_fx(a["type"], a.get("params"))
                pos = a.get("position")
                t.setdefault("fx", []).insert(len(t["fx"]) if pos is None else int(M.clamp(int(pos), 1, len(t["fx"]) + 1)) - 1, fx)
                return {"effect_id": fx["id"]}
            return self._track_edit(a, f"add {a['type']}", fn)

        @tool("update_effect", "Change parameters of an effect, bypass it (on=false) or remove it (remove=true).",
              _S(project_id=PID, track=TRACK, effect_id=("string", "Effect id (from get_project).", True), params=("object", "Parameters to change."),
                 on=("boolean", "Enable/bypass."), remove=("boolean", "Remove this effect.")))
        def update_effect(a):
            def fn(proj, t):
                fx = next((f for f in t.get("fx", []) if f["id"] == a["effect_id"]), None)
                if fx is None:
                    raise M.ModelError(f"effect '{a['effect_id']}' not found on track '{t['name']}'")
                if a.get("remove"):
                    t["fx"].remove(fx)
                    return {"removed": fx["id"]}
                merged = M.new_fx(fx["type"], {**fx["p"], **(a.get("params") or {})}, a.get("on", fx["on"]))
                fx["p"], fx["on"] = merged["p"], merged["on"]
            return self._track_edit(a, "update effect", fn)

        # ---------------- drum pads
        @tool("set_drum_pads", "Turn individual drum pads (steps) on or off for one part. Steps are 1-based 16th notes (1-16 for bar 1, 17-32 for bar 2, ...).",
              _S(project_id=PID, track=TRACK, part=PART, steps=("array", "1-based step numbers.", True, {"items": {"type": "integer"}}),
                 on=("boolean", "true = hit (default), false = clear.")))
        def set_drum_pads(a):
            def fn(proj, t):
                self._drum(t)
                row, n = M.drum_row(a["part"]), M.pat_steps(proj, t)
                for s in a["steps"]:
                    s = int(s)
                    if not 1 <= s <= n:
                        raise M.ModelError(f"step {s} out of range 1-{n} (pattern is {t['pattern']['bars']} bar(s); use set_pattern_length for more)")
                    t["pattern"]["grid"][row][s - 1] = 1 if a.get("on", True) else 0
            return self._track_edit(a, f"pads {a['part']}", fn)

        @tool("set_drum_pattern", "Write whole pad rows from strings, e.g. {\"kick\": \"x...x...x...x...\", \"snare\": \"....x.......x...\"}. 'x' = hit, '.' = rest; '|' and spaces are ignored; short patterns repeat to fill the pattern length. Parts not listed are unchanged unless clear_others=true.",
              _S(project_id=PID, track=TRACK, patterns=("object", "Map part -> pattern string.", True), bars=("integer", "Optionally set the pattern length first (1, 2, 4, 8)."),
                 clear_others=("boolean", "Clear all parts not given (default false).")))
        def set_drum_pattern(a):
            def fn(proj, t):
                self._drum(t)
                if a.get("bars"):
                    self._set_bars(proj, t, a["bars"])
                rows = {M.drum_row(p): pat for p, pat in a["patterns"].items()}
                n = M.pat_steps(proj, t)
                for r in range(len(M.DRUMS)):
                    if r in rows:
                        t["pattern"]["grid"][r] = M.pattern_to_row(rows[r], n)
                    elif a.get("clear_others"):
                        t["pattern"]["grid"][r] = [0] * n
            return self._track_edit(a, "drum pattern", fn)

        @tool("apply_drum_preset", "Replace a drum track's pads with a preset beat (e.g. Metal Double Bass, Blast Beat, D-Beat, Punk Beat, Hardcore Breakdown...).",
              _S(project_id=PID, track=TRACK, preset=("string", "Preset name (see get_reference).", True)))
        def apply_drum_preset(a):
            def fn(proj, t):
                M.apply_drum_preset(proj, self._drum(t), a["preset"])
            return self._track_edit(a, f"preset {a['preset']}", fn)

        @tool("clear_drum_pads", "Clear all pads of one part, or of the whole drum track when part is omitted.",
              _S(project_id=PID, track=TRACK, part=("string", "Drum part (omit = all parts).")))
        def clear_drum_pads(a):
            def fn(proj, t):
                self._drum(t)
                n = M.pat_steps(proj, t)
                rows = [M.drum_row(a["part"])] if a.get("part") else range(len(M.DRUMS))
                for r in rows:
                    t["pattern"]["grid"][r] = [0] * n
            return self._track_edit(a, "clear pads", fn)

        @tool("set_drum_tuning", "Tune a drum part: pitch in semitones (-12..12), decay multiplier (0.3..2), level (0..1.5).",
              _S(project_id=PID, track=TRACK, part=PART, pitch=("number", "-12..12 semitones"), decay=("number", "0.3..2 (1 = default length)"), level=("number", "0..1.5")))
        def set_drum_tuning(a):
            def fn(proj, t):
                self._drum(t)
                pid = M.DRUM_IDS[M.drum_row(a["part"])]
                kit = {**M.KIT_DEFAULT, **(t.setdefault("kit", {}).get(pid) or {})}
                for k, (lo, hi) in M.KIT_RANGES.items():
                    if k in a:
                        kit[k] = M.num(a[k], k, lo, hi)
                t["kit"][pid] = kit
            return self._track_edit(a, f"tune {a['part']}", fn)

        @tool("set_pattern_length", "Set the pattern length in bars (1, 2, 4 or 8) of a drum or synth/guitar track. Longer patterns keep existing pads; shorter ones cut them.",
              _S(project_id=PID, track=TRACK, bars=("integer", "1, 2, 4 or 8", True, {"enum": [1, 2, 4, 8]})))
        def set_pattern_length(a):
            def fn(proj, t):
                self._set_bars(proj, t, a["bars"])
            return self._track_edit(a, f"pattern {a['bars']} bars", fn)

        # ---------------- synth / guitar
        @tool("set_notes", "Write notes of a synth/guitar track's pattern. Each note: {note: 'E2' or MIDI number, step: 1-based 16th step, length: steps (default 1)}. Range C2 (36) - C6 (84).",
              _S(project_id=PID, track=TRACK, notes=("array", "Notes to write.", True, {"items": {"type": "object", "properties": {"note": {"type": ["string", "integer"]}, "step": {"type": "integer"}, "length": {"type": "integer"}}, "required": ["note", "step"]}}),
                 replace=("boolean", "Replace all existing notes (default true); false = add/overwrite.")))
        def set_notes(a):
            def fn(proj, t):
                self._synth(t)
                n = M.pat_steps(proj, t)
                new = []
                for x in a["notes"]:
                    p = M.parse_note(x.get("note", x.get("pitch")))
                    if not M.LOW_NOTE <= p <= M.HIGH_NOTE:
                        raise M.ModelError(f"note {x.get('note')} outside {M.note_name(M.LOW_NOTE)}-{M.note_name(M.HIGH_NOTE)}")
                    s = int(x["step"])
                    if not 1 <= s <= n:
                        raise M.ModelError(f"step {s} out of range 1-{n}")
                    new.append({"p": p, "s": s - 1, "l": int(M.clamp(int(x.get("length", 1)), 1, n - s + 1))})
                keep = [] if a.get("replace", True) else [o for o in t["notes"] if not any(o["p"] == q["p"] and o["s"] == q["s"] for q in new)]
                t["notes"] = keep + new
            return self._track_edit(a, "notes", fn)

        @tool("set_synth", "Change the sound of a synth/guitar track: preset (e.g. Bass, Lead, Power Chord Guitar, Palm Mute Guitar...) and/or params (wave, attack, release, cutoff, detune, gain, drive, pluck, chord).",
              _S(project_id=PID, track=TRACK, preset=("string", "Synth preset (see get_reference)."), params=("object", "Parameters to change.")))
        def set_synth(a):
            def fn(proj, t):
                self._synth(t)
                s = t["synth"]
                if a.get("preset"):
                    if a["preset"] not in M.SYNTH_PRESETS:
                        raise M.ModelError("unknown synth preset. Presets: " + ", ".join(M.SYNTH_PRESETS))
                    s = {**M.SYNTH_DEFAULTS, **M.SYNTH_PRESETS[a["preset"]], "preset": a["preset"]}
                for k, v in (a.get("params") or {}).items():
                    spec = M.SYNTH_PARAMS.get(k)
                    if spec is None:
                        raise M.ModelError(f"unknown synth parameter '{k}'. Parameters: " + ", ".join(M.SYNTH_PARAMS))
                    if isinstance(spec, list):
                        if v not in spec:
                            raise M.ModelError(f"'{k}' must be one of {spec}")
                        s[k] = v
                    else:
                        s[k] = M.num(v, k, *spec)
                t["synth"] = s
            return self._track_edit(a, "synth sound", fn)

        # ---------------- clips / regions
        @tool("add_region", "Add a pattern region (clip) to a drum/synth/guitar track; the track's pattern loops inside it. Beats are quarter notes from the song start (bar 2 starts at beat 4 in 4/4).",
              _S(project_id=PID, track=TRACK, start_beat=("number", "Start beat (0 = song start).", True), length_beats=("number", "Length in beats (default 4 bars).")))
        def add_region(a):
            def fn(proj, t):
                if t["type"] == "audio":
                    raise M.ModelError("audio tracks get clips by importing/recording audio in the UI")
                c = {"id": M.nid("c"), "kind": "midi", "start": M.num(a["start_beat"], "start_beat", 0, 100000),
                     "len": M.num(a.get("length_beats", proj["sig"] * 4), "length_beats", 0.25, 100000)}
                t["clips"].append(c)
                return {"clip_id": c["id"]}
            return self._track_edit(a, "add region", fn)

        @tool("update_clip", "Move/resize a clip or region, move it to another compatible track, or change an audio clip's gain.",
              _S(project_id=PID, clip_id=("string", "Clip id (from get_project).", True), start_beat=("number", "New start beat."),
                 length_beats=("number", "New length (MIDI regions)."), duration_sec=("number", "New duration in seconds (audio clips, trims the end)."),
                 gain=("number", "Audio clip gain 0..2."), track=(None, "Move to this track (same type).", False, {"type": ["string", "integer"]})))
        def update_clip(a):
            def run(doc):
                proj = doc["project"]
                t, c = M.find_clip(proj, a["clip_id"])
                if "start_beat" in a:
                    c["start"] = M.num(a["start_beat"], "start_beat", 0, 100000)
                if "length_beats" in a:
                    if c["kind"] != "midi":
                        raise M.ModelError("length_beats is for MIDI regions; use duration_sec for audio clips")
                    c["len"] = M.num(a["length_beats"], "length_beats", 0.25, 100000)
                if "duration_sec" in a:
                    if c["kind"] != "audio":
                        raise M.ModelError("duration_sec is for audio clips")
                    c["dur"] = M.num(a["duration_sec"], "duration_sec", 0.05, 100000)
                if "gain" in a:
                    c["gain"] = M.num(a["gain"], "gain", 0, 2)
                if a.get("track") is not None:
                    nt = M.find_track(proj, a["track"])
                    if nt["type"] != t["type"]:
                        raise M.ModelError(f"cannot move a {t['type']} clip to a {nt['type']} track")
                    t["clips"].remove(c)
                    nt["clips"].append(c)
                    t = nt
                return {"clip": {"id": c["id"], "track": t["name"], "start_beat": c["start"]}}
            return self._edit(a["project_id"], "update clip", run)

        @tool("delete_clip", "Delete a clip or pattern region.", _S(project_id=PID, clip_id=("string", "Clip id.", True)))
        def delete_clip(a):
            def run(doc):
                t, c = M.find_clip(doc["project"], a["clip_id"])
                t["clips"].remove(c)
                return {"deleted": c["id"], "track": t["name"]}
            return self._edit(a["project_id"], "delete clip", run)

        return T

    def _set_bars(self, proj, t, bars):
        bars = int(bars)
        if bars not in (1, 2, 4, 8):
            raise M.ModelError("bars must be 1, 2, 4 or 8")
        if t["type"] == "drum":
            t["pattern"]["bars"] = bars
            M.resize_grid(proj, t)
        else:
            t["bars"] = bars
            t["notes"] = [n for n in t["notes"] if n["s"] < M.pat_steps(proj, t)]

    @staticmethod
    def _apply_template(proj, tpl):
        if tpl not in ("empty", "metal", "band"):
            raise M.ModelError("template must be empty, metal or band")
        if tpl == "empty":
            M.new_track(proj, "audio")
            return
        d = M.new_track(proj, "drum")
        d["clips"].append({"id": M.nid("c"), "kind": "midi", "start": 0, "len": 16})
        b = M.new_track(proj, "synth", "Bass")
        b["synth"] = {"preset": "Bass", **M.SYNTH_DEFAULTS, **M.SYNTH_PRESETS["Bass"]}
        b["notes"] = [{"p": p, "s": s, "l": l} for p, s, l in [(36, 0, 3), (36, 6, 2), (43, 10, 2), (41, 12, 4)]]
        b["clips"].append({"id": M.nid("c"), "kind": "midi", "start": 0, "len": 16})
        g = M.new_track(proj, "guitar")
        g["notes"] = [{"p": p, "s": s, "l": l} for p, s, l in [(40, 0, 2), (40, 2, 1), (40, 3, 1), (43, 4, 2), (45, 6, 2), (40, 8, 2), (46, 10, 1), (45, 11, 1), (43, 12, 4)]]
        g["clips"].append({"id": M.nid("c"), "kind": "midi", "start": 0, "len": 16})
        v = M.new_track(proj, "audio", "Vocal" if tpl == "band" else None)
        if tpl == "band":
            v["fx"] = [M.new_fx("eq", {"low": -4, "lowF": 120, "mid": 1.5, "midF": 2500, "high": 3}), M.new_fx("comp", {"thr": -24, "ratio": 4, "makeup": 6}),
                       M.new_fx("delay", {"time": 0.5, "feedback": 0.25, "mix": 0.12}), M.new_fx("reverb", {"size": 2.2, "mix": 0.25})]

    # ------------------------------------------------------- JSON-RPC
    def handle(self, msg):
        """Handle one JSON-RPC message; returns a response dict or None for notifications."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
            return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
        mid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
        is_notification = "id" not in msg
        try:
            if method == "initialize":
                want = params.get("protocolVersion")
                result = {"protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "rushdaw", "title": "RushDAW", "version": __version__},
                          "instructions": INSTRUCTIONS}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [t["def"] for t in self.tools.values()]}
            elif method == "tools/call":
                result = self.call_tool(params.get("name"), params.get("arguments") or {})
            elif method.startswith("notifications/"):
                return None
            else:
                return None if is_notification else _err(mid, -32601, f"Method not found: {method}")
        except Exception as e:  # unexpected server error
            return None if is_notification else _err(mid, -32603, f"Internal error: {e}")
        return None if is_notification else {"jsonrpc": "2.0", "id": mid, "result": result}

    def call_tool(self, name, args):
        tool = self.tools.get(name)
        if tool is None:
            return _tool_result({"error": f"unknown tool '{name}'"}, True)
        if not isinstance(args, dict):
            return _tool_result({"error": "arguments must be an object"}, True)
        missing = [k for k in tool["def"]["inputSchema"]["required"] if k not in args]
        if missing:
            return _tool_result({"error": "missing required argument(s): " + ", ".join(missing)}, True)
        unknown = [k for k in args if k not in tool["def"]["inputSchema"]["properties"]]
        if unknown:
            return _tool_result({"error": "unknown argument(s): " + ", ".join(unknown)}, True)
        try:
            return _tool_result(tool["fn"](args), False)
        except (ToolError, M.ModelError, StorageError, KeyError, TypeError, ValueError) as e:
            return _tool_result({"error": str(e) or e.__class__.__name__}, True)


def _tool_result(obj, is_error):
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False, indent=1)}],
            "structuredContent": obj, "isError": is_error}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}
