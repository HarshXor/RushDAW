"""Server-side model of a RushDAW project (mirrors static/app.js).

Used by the MCP tools to read and edit ``.rushdaw`` project documents without a
browser.  Every structure produced here must be loadable by the web UI, so the
constants below are kept in sync with ``static/app.js`` (see tests).
"""
import json
import math
import copy
import itertools
import re
import time

COLORS = ['#00e5ff', '#ffffff', '#7fffd4', '#00b8d4', '#b2f5ff', '#4dd0e1', '#d9d9d9', '#1de9b6']
DRUMS = [  # (id, display name) – order == row order of the drum grid
    ('kick', 'Kick'), ('snare', 'Snare'), ('chh', 'Closed Hi-Hat'), ('ohh', 'Open Hi-Hat'), ('tomh', 'High Tom'),
    ('tomm', 'Mid Tom'), ('toml', 'Floor Tom'), ('crash', 'Crash Cymbal'), ('ride', 'Ride Cymbal'), ('phh', 'Pedal Hi-Hat'),
]
DRUM_IDS = [d[0] for d in DRUMS]
# row order of projects saved before pattern['ids'] existed (old 9-part kit)
LEGACY_DRUM_IDS = ['kick', 'snare', 'ride', 'chh', 'ohh', 'tomh', 'toml', 'rim', 'crash']
DRUM_ALIASES = {'hihat': 'chh', 'hh': 'chh', 'closedhh': 'chh', 'closedhat': 'chh', 'openhh': 'ohh', 'openhat': 'ohh',
                'pedal': 'phh', 'pedalhh': 'phh', 'pedalhat': 'phh', 'hhpedal': 'phh', 'footHH': 'phh',
                'bass': 'kick', 'bassdrum': 'kick', 'bd': 'kick', 'sd': 'snare', 'tom': 'tomm', 'hitom': 'tomh',
                'tom1': 'tomh', 'tom2': 'tomm', 'tom3': 'toml', 'midtom': 'tomm', 'floor': 'toml', 'lowtom': 'toml',
                'crash': 'crash', 'cymbal': 'crash', 'ride': 'ride'}
DRUM_ALIASES = {k.lower(): v for k, v in DRUM_ALIASES.items()}
DEFAULT_DRUM_PRESET = 'Metal Double Bass'
CRUST_RIFF = [(40, 0, 2), (40, 2, 1), (40, 3, 1), (43, 4, 2), (41, 6, 2), (40, 8, 2), (40, 10, 1), (40, 11, 1), (46, 12, 2), (45, 14, 2)]  # = CRUST_RIFF in app.js
DRUM_PRESETS = {
    'Metal Double Bass': {'kick': 'xxxxxxxxxxxxxxxx', 'snare': '....x.......x...', 'crash': 'x...............', 'ride': 'x...x...x...x...'},
    'Metal Gallop': {'kick': 'x.xxx.xxx.xxx.xx', 'snare': '....x.......x...', 'crash': 'x...x...x...x...'},
    'Blast Beat': {'kick': 'x.x.x.x.x.x.x.x.', 'snare': '.x.x.x.x.x.x.x.x', 'crash': 'x.......x.......'},
    'Hammer Blast': {'kick': 'x.x.x.x.x.x.x.x.', 'snare': 'x.x.x.x.x.x.x.x.', 'ride': 'x...x...x...x...'},
    'Thrash Skank': {'kick': 'x...x...x...x...', 'snare': '..x...x...x...x.', 'crash': 'x.x.x.x.x.x.x.x.'},
    'Hardcore Breakdown': {'kick': 'x..x..x...x..x..', 'snare': '........x.......', 'crash': 'x.......x.......', 'toml': '......x.......x.', 'phh': '..x...x...x...x.'},
    'Hardcore Two-Step': {'kick': 'x.xx....x.xx....', 'snare': '....x.......x...', 'chh': 'x.x.x.x.x.x.x.x.', 'crash': 'x...............'},
    'D-Beat': {'kick': 'x..x.x..x..x.x..', 'snare': '..x...x...x...x.', 'ohh': 'x.x.x.x.x.x.x.x.', 'crash': 'x...............'},
    # 2 bars: crash on the 1, OPEN hi-hat 8ths (not under the crash), snare on every '&', kick K..K.K.. (classic d-beat)
    'Crust D-Beat': {'kick': 'x..x.x..x..x.x..x..x.x..x..x.x..', 'snare': '..x...x...x...x...x...x...x...x.',
                     'ohh': '..x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.', 'crash': 'x...............................'},
    'Punk Beat': {'kick': 'x.x...x.x.x...x.', 'snare': '....x.......x...', 'chh': 'x.x.x.x.x.x.x.x.', 'crash': 'x...............'},
    'Punk Polka': {'kick': 'x...x...x...x...', 'snare': '..x...x...x...x.', 'chh': 'x.x.x.x.x.x.x.x.'},
    'Pop-Punk Drive': {'kick': 'x.....x.x.......', 'snare': '....x.......x...', 'ohh': 'x.x.x.x.x.x.x.x.', 'crash': 'x...............'},
    'Four on the floor': {'kick': 'x...x...x...x...', 'snare': '....x.......x...', 'chh': '..x...x...x...x.', 'ohh': '......x.......x.'},
    'Rock': {'kick': 'x.......x.x.....', 'snare': '....x.......x...', 'chh': 'x.x.x.x.x.x.x.x.', 'crash': 'x...............'},
    'Hip-Hop': {'kick': 'x......x..x.....', 'snare': '....x.......x...', 'chh': 'x.x.x.x.x.x.xxx.', 'ohh': '...........x....'},
    'Trap': {'kick': 'x.....x...x.....', 'snare': '........x.......', 'chh': 'xxxxxxxxx.xxxxxx', 'ohh': '.......x........'},
    'Reggaeton': {'kick': 'x...x...x...x...', 'snare': '...x..x....x..x.', 'chh': 'x.x.x.x.x.x.x.x.'},
    'Empty': {},
}
SYNTH_DEFAULTS = {'engine': 'osc', 'sample': 'electric_guitar_clean', 'decay': 1.5, 'susLevel': 0.3, 'drive': 0, 'chord': 'none', 'pluck': 0, 'brightness': 0.5, 'sustain': 0.5, 'pick': 0.13, 'body': 0.5, 'vowel': 'a', 'voices': 1, 'breath': 0, 'vibrato': 0}
DEFAULT_VOCAL_PRESET = 'Choir Aah'
DEFAULT_GUITAR_PRESET, DEFAULT_BASS_PRESET = 'Clean Guitar', 'Finger Bass'
SAMPLE_SETS = ['electric_guitar_clean', 'acoustic_guitar_steel', 'electric_bass_finger', 'electric_bass_pick',
               'electric_guitar_muted', 'choir_aahs', 'voice_oohs', 'acoustic_grand_piano', 'electric_piano_1', 'string_ensemble_1']
_SMP = {'engine': 'sample', 'wave': 'sawtooth', 'attack': 0.001, 'detune': 0, 'pluck': 0}
SYNTH_PRESETS = {
    # real instruments: recorded guitar / bass (FluidR3_GM soundfont)
    'Clean Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.3, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none', 'decay': 2.0, 'susLevel': 0.35},
    'Acoustic Guitar': {**_SMP, 'sample': 'acoustic_guitar_steel', 'release': 0.4, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none', 'decay': 2.5, 'susLevel': 0.3},
    'Finger Bass': {**_SMP, 'sample': 'electric_bass_finger', 'release': 0.2, 'cutoff': 12000, 'gain': 0.75, 'drive': 0, 'chord': 'none', 'decay': 2.5, 'susLevel': 0.45},
    'Pick Bass': {**_SMP, 'sample': 'electric_bass_pick', 'release': 0.15, 'cutoff': 12000, 'gain': 0.75, 'drive': 0, 'chord': 'none', 'decay': 2.0, 'susLevel': 0.4},
    # synth sounds (oscillators)
    'Keys': {'wave': 'triangle', 'attack': 0.005, 'release': 0.4, 'cutoff': 5000, 'detune': 4, 'gain': 0.5},
    'Synth Bass': {'wave': 'sawtooth', 'attack': 0.005, 'release': 0.15, 'cutoff': 900, 'detune': 0, 'gain': 0.55},
    'Lead': {'wave': 'square', 'attack': 0.01, 'release': 0.2, 'cutoff': 3500, 'detune': 8, 'gain': 0.35},
    'Pad': {'wave': 'sawtooth', 'attack': 0.5, 'release': 1.2, 'cutoff': 2200, 'detune': 12, 'gain': 0.3},
    'Pluck': {'wave': 'sawtooth', 'attack': 0.002, 'release': 0.12, 'cutoff': 2600, 'detune': 5, 'gain': 0.4},
    'Sub 808': {'wave': 'sine', 'attack': 0.003, 'release': 0.6, 'cutoff': 400, 'detune': 0, 'gain': 0.8},
    # amped guitars: real clean guitar recording -> amp distortion -> cabinet
    'Crunch Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.2, 'cutoff': 6000, 'gain': 0.4, 'drive': 0.35, 'chord': 'none', 'decay': 3.0, 'susLevel': 0.6},
    'Distortion Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.2, 'cutoff': 5000, 'gain': 0.32, 'drive': 0.8, 'chord': 'none', 'decay': 4.0, 'susLevel': 0.75},
    'Power Chord Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.2, 'cutoff': 5000, 'gain': 0.26, 'drive': 0.8, 'chord': 'power', 'decay': 4.0, 'susLevel': 0.75},
    'Palm Mute Guitar': {**_SMP, 'sample': 'electric_guitar_muted', 'release': 0.05, 'cutoff': 3500, 'gain': 0.32, 'drive': 0.75, 'chord': 'power', 'decay': 0.3, 'susLevel': 0.0},
    # real keys / strings (recorded, FluidR3_GM)
    'Piano': {**_SMP, 'sample': 'acoustic_grand_piano', 'release': 0.5, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none', 'decay': 4.0, 'susLevel': 0.05},
    'Electric Piano': {**_SMP, 'sample': 'electric_piano_1', 'release': 0.4, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none', 'decay': 3.0, 'susLevel': 0.15},
    'Strings': {**_SMP, 'sample': 'string_ensemble_1', 'attack': 0.25, 'release': 0.8, 'cutoff': 12000, 'gain': 0.95, 'drive': 0, 'chord': 'none', 'decay': 1.0, 'susLevel': 0.9},
    # choir: real recorded choir "aah" / "ooh" (FluidR3_GM), sustain-looped for long notes
    'Choir Aah': {**_SMP, 'sample': 'choir_aahs', 'attack': 0.15, 'release': 0.6, 'cutoff': 12000, 'gain': 1.5, 'drive': 0, 'chord': 'none', 'decay': 1.0, 'susLevel': 0.85},
    'Choir Ooh': {**_SMP, 'sample': 'voice_oohs', 'attack': 0.15, 'release': 0.7, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none', 'decay': 1.0, 'susLevel': 0.85},
    'Choir Ohh': {**_SMP, 'sample': 'voice_oohs', 'attack': 0.15, 'release': 0.6, 'cutoff': 2600, 'gain': 0.65, 'drive': 0, 'chord': 'none', 'decay': 1.0, 'susLevel': 0.85},
    # solo voice (formant-synthesized single voice "hooo" / "haaa"; no free solo recordings)
    'Solo Hoo': {'engine': 'voice', 'vowel': 'u', 'voices': 1, 'wave': 'sawtooth', 'attack': 0.06, 'release': 0.35, 'cutoff': 6000, 'detune': 0, 'gain': 0.6, 'drive': 0, 'chord': 'none', 'pluck': 0, 'breath': 0.35, 'vibrato': 0.5, 'decay': 0.8, 'susLevel': 0.8},
    'Solo Haa': {'engine': 'voice', 'vowel': 'a', 'voices': 1, 'wave': 'sawtooth', 'attack': 0.05, 'release': 0.35, 'cutoff': 7500, 'detune': 0, 'gain': 0.5, 'drive': 0, 'chord': 'none', 'pluck': 0, 'breath': 0.35, 'vibrato': 0.5, 'decay': 0.8, 'susLevel': 0.8},
    # modeled string (Karplus-Strong), kept for experimenting
    'Modeled String': {'engine': 'string', 'wave': 'sawtooth', 'attack': 0.002, 'release': 0.12, 'cutoff': 3800, 'detune': 0, 'gain': 0.55, 'drive': 0, 'chord': 'none', 'pluck': 0, 'brightness': 0.4, 'sustain': 0.55, 'pick': 0.14, 'body': 0.5},
}
SYNTH_PARAMS = {  # name: (min, max) or list of choices
    'engine': ['sample', 'voice', 'string', 'osc'], 'vowel': ['a', 'e', 'i', 'o', 'u'], 'voices': (1, 6), 'breath': (0, 1), 'vibrato': (0, 1), 'sample': list(SAMPLE_SETS), 'wave': ['sine', 'triangle', 'square', 'sawtooth'], 'attack': (0.001, 2), 'release': (0.01, 3),
    'cutoff': (100, 12000), 'detune': (0, 50), 'gain': (0, 1.5), 'drive': (0, 1), 'pluck': (0, 3), 'chord': ['none', 'power'],
    'brightness': (0.05, 1), 'sustain': (0, 1), 'pick': (0.02, 0.5), 'body': (0, 1),
    'decay': (0.03, 10), 'susLevel': (0, 1),  # sample engine: Decay seconds, Sustain level while a note is held
}
MASTER_DEFAULT = {'vol': 1, 'eqLow': 0, 'eqMid': 0, 'eqHigh': 0, 'compThr': -18, 'compRatio': 2.5, 'compAtk': 0.01,
                  'compRel': 0.25, 'makeup': 3, 'ceiling': -1, 'reverbSize': 2.5, 'delayDiv': 0.75, 'delayFb': 0.35}
MASTER_PARAMS = {'vol': (0, 1.5), 'eqLow': (-12, 12), 'eqMid': (-12, 12), 'eqHigh': (-12, 12), 'compThr': (-50, 0),
                 'compRatio': (1, 20), 'compAtk': (0.001, 0.2), 'compRel': (0.02, 1), 'makeup': (0, 18), 'ceiling': (-12, 0),
                 'reverbSize': (0.3, 6), 'delayDiv': (0.25, 2), 'delayFb': (0, 0.9)}
MASTER_PRESETS = {
    'Flat (off)': {'eqLow': 0, 'eqMid': 0, 'eqHigh': 0, 'compThr': 0, 'compRatio': 1, 'makeup': 0, 'ceiling': -0.3},
    'Balanced': {'eqLow': 1, 'eqMid': 0, 'eqHigh': 1.5, 'compThr': -18, 'compRatio': 2.5, 'makeup': 3, 'ceiling': -1},
    'Loud Pop': {'eqLow': 2, 'eqMid': -1, 'eqHigh': 3, 'compThr': -24, 'compRatio': 4, 'makeup': 7, 'ceiling': -0.5},
    'Warm': {'eqLow': 3, 'eqMid': 0.5, 'eqHigh': -2, 'compThr': -20, 'compRatio': 3, 'makeup': 4, 'ceiling': -1},
    'Bass Boost': {'eqLow': 5, 'eqMid': -1, 'eqHigh': 0.5, 'compThr': -20, 'compRatio': 3, 'makeup': 4, 'ceiling': -1},
    'Bright': {'eqLow': -1, 'eqMid': 1, 'eqHigh': 4, 'compThr': -18, 'compRatio': 2.5, 'makeup': 3, 'ceiling': -1},
}
FX_TYPES = {  # type: {param: (default, min, max)} or (default, [choices])
    'eq': {'low': (0, -15, 15), 'lowF': (120, 30, 600), 'mid': (0, -15, 15), 'midF': (1000, 200, 8000), 'high': (0, -15, 15), 'highF': (6000, 1500, 16000)},
    'comp': {'thr': (-20, -60, 0), 'ratio': (4, 1, 20), 'attack': (0.01, 0.001, 0.3), 'release': (0.2, 0.02, 1), 'makeup': (3, 0, 24)},
    'dist': {'drive': (0.5, 0, 1), 'tone': (4500, 500, 12000), 'level': (0.6, 0, 1.5), 'mix': (1, 0, 1)},
    'amp': {'gain': (10, 0, 36), 'drive': (0.8, 0, 1), 'tone': (4800, 500, 12000), 'level': (0.32, 0, 1.5)},  # guitar amp
    'filter': {'mode': ('lowpass', ['lowpass', 'highpass', 'bandpass']), 'freq': (2000, 30, 18000), 'q': (1, 0.1, 15)},
    'chorus': {'rate': (1.5, 0.1, 8), 'depth': (0.004, 0, 0.012), 'mix': (0.5, 0, 1)},
    'tremolo': {'rate': (5, 0.5, 20), 'depth': (0.5, 0, 1)},
    'delay': {'time': (0.75, 0.125, 2), 'feedback': (0.35, 0, 0.9), 'tone': (5000, 500, 12000), 'mix': (0.3, 0, 1)},
    'reverb': {'size': (2, 0.2, 8), 'tone': (8000, 1000, 16000), 'mix': (0.3, 0, 1)},
    'formant': {'vowel': ('a', ['a', 'e', 'i', 'o', 'u']), 'shift': (1, 0.6, 1.6), 'mix': (0.8, 0, 1)},  # vocal formant filter
}
CHOIR_FX = [('eq', {'low': -3, 'lowF': 150, 'high': 2, 'highF': 7000}), ('chorus', {'rate': 0.4, 'depth': 0.005, 'mix': 0.35}), ('reverb', {'size': 3.5, 'mix': 0.35})]
KIT_DEFAULT = {'pitch': 0, 'decay': 1, 'level': 1}
KIT_RANGES = {'pitch': (-24, 24), 'decay': (0.1, 4), 'level': (0, 2)}  # wide: ±2 octaves, 10-400% decay, 0-200% level
KIT_VOL_DB = (-48, 6)  # per-part Volume fader in dB (-48 = off); stored as linear 'level'


def tune_percent_to_pitch(pct):
    """Pitch percent (100 = default) -> semitones, rounded to the 0.5 steps of the editor's Tune knob."""
    import math
    return max(KIT_RANGES['pitch'][0], min(KIT_RANGES['pitch'][1], round(12 * math.log2(pct / 100) * 2) / 2))


def kit_db_to_level(db):
    return 0.0 if db <= KIT_VOL_DB[0] else min(KIT_RANGES['level'][1], round(10 ** (db / 20), 6))
VEL_CHAR = {'x': 1, 'X': 1, 'o': 0.6, 'g': 0.3}  # pad velocity chars (mirrors VEL_CHAR in app.js)
FEEL_DEFAULT = {'hum': 0, 'swing': 0, 'push': 0}  # per-track timing feel: humanize ms, swing 0..0.6, push ms
TRACK_TYPES = ('audio', 'drum', 'synth', 'guitar', 'bass', 'vocal')
LOW_NOTE, HIGH_NOTE = 36, 84
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_counter = itertools.count(1)


class ModelError(ValueError):
    """Invalid edit request (reported back to the MCP client as a tool error)."""


def nid(prefix):
    """Unique id compatible with the browser's nid() format (prefix + base36)."""
    def b36(n):
        s = ''
        while True:
            n, r = divmod(n, 36)
            s = '0123456789abcdefghijklmnopqrstuvwxyz'[r] + s
            if not n:
                return s
    return f"{prefix}{b36(int(time.time() * 1000))}{b36(next(_counter))}s"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def num(value, name, lo=None, hi=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ModelError(f"'{name}' must be a number")
    if v != v:  # NaN
        raise ModelError(f"'{name}' must be a number")
    if lo is not None and hi is not None and not (lo <= v <= hi):
        raise ModelError(f"'{name}' must be between {lo} and {hi} (got {value})")
    return int(v) if v.is_integer() and isinstance(value, int) else v


# ------------------------------------------------------------------ documents
def new_document(title, bpm=180, sig=4):
    return {'app': 'rushdaw', 'version': 1, 'audio': {},
            'project': {'title': title, 'bpm': bpm, 'sig': sig, 'tracks': [], 'loop': {'start': 0, 'end': 16},
                        'master': dict(MASTER_DEFAULT)}}


def steps_per_bar(proj):
    return int(proj.get('sig') or 4) * 4


def pat_steps(proj, t):
    # a MIDI region is LINEAR: one step per 16th over its whole length (nothing loops);
    # a track's template pattern uses its bar count
    if t.get('kind') == 'midi':
        return region_steps(t)
    bars = t['pattern']['bars'] if 'pattern' in t else t.get('bars', 1)
    return int(bars) * steps_per_bar(proj)


def region_steps(c):
    return max(1, int(round(c['len'] * 4)))


def fit_region(proj, t, c):
    """Make a region's data exactly as long as the region: new steps are empty, steps past the end are cut."""
    n = region_steps(c)
    if t['type'] == 'drum':
        c['pattern']['grid'] = [(list(r) + [0] * n)[:n] for r in c['pattern']['grid']]
        c['pattern']['bars'] = c['len'] / proj.get('sig', 4)
    else:
        c['notes'] = [dict(x, l=min(x['l'], n - x['s'])) for x in c['notes'] if x['s'] < n]
        c['bars'] = c['len'] / proj.get('sig', 4)


def merge_regions(proj, clip_ids):
    """Merge MIDI regions of ONE track into a single region (= mergeSelected in app.js): it spans the first start
    to the last end, every pad / note keeps its exact position, gaps are empty, overlapping pads keep the louder velocity.
    The first region's fade in and the last region's fade out are kept. Returns (track, new_region)."""
    ids = list(dict.fromkeys(clip_ids or []))
    if len(ids) < 2:
        raise ModelError("give 2 or more clip ids to merge")
    found = [find_clip(proj, i) for i in ids]
    t = found[0][0]
    if any(x[0] is not t for x in found):
        raise ModelError("merge works on regions of the same track")
    clips = sorted((c for _, c in found), key=lambda c: c["start"])
    if any(c.get("kind") != "midi" for c in clips):
        raise ModelError("only pattern (MIDI) regions can be merged here; merge audio clips in the editor UI")
    start = min(c["start"] for c in clips)
    end = max(c["start"] + c["len"] for c in clips)
    nc = {"id": nid("c"), "kind": "midi", "start": start, "len": round((end - start) * 4) / 4}
    n = region_steps(nc)
    sig = proj.get("sig", 4)
    if t["type"] == "drum":
        grid = [[0] * n for _ in DRUMS]
        for c in clips:
            off = int(round((c["start"] - start) * 4))
            for r, row in enumerate((c.get("pattern") or {}).get("grid", [])):
                if r >= len(grid):
                    continue
                for k, v in enumerate(row):
                    if v and off + k < n:
                        grid[r][off + k] = max(grid[r][off + k], v)
        nc["pattern"] = {"bars": nc["len"] / sig, "grid": grid, "ids": list(DRUM_IDS)}
    else:
        notes = []
        for c in clips:
            off = int(round((c["start"] - start) * 4))
            for x in c.get("notes", []):
                if x["s"] + off < n:
                    notes.append(dict(x, s=x["s"] + off, l=min(x["l"], n - x["s"] - off)))
        nc["notes"] = notes
        nc["bars"] = nc["len"] / sig
    first = clips[0]
    last = max(clips, key=lambda c: c["start"] + c["len"])
    if first.get("fi"):
        nc["fi"] = first["fi"]
    if last.get("fo"):
        nc["fo"] = last["fo"]
    nc["linear"] = True
    t["clips"] = [c for c in t["clips"] if c not in clips] + [nc]
    return t, nc


def linearize(proj, t, c, src_steps):
    """Unroll a looping pattern (old projects / the track template) into literal steps over the region (= linearize in app.js)."""
    n, m = region_steps(c), max(1, int(src_steps))
    if t['type'] == 'drum':
        c['pattern']['grid'] = [[(r[i % m] if i % m < len(r) else 0) if r else 0 for i in range(n)] for r in c['pattern']['grid']]
    else:
        c['notes'] = [dict(x, s=off + x['s'], l=min(x['l'], n - off - x['s'])) for off in range(0, n, m) for x in c['notes'] if x['s'] < m and off + x['s'] < n]
    c['linear'] = True
    fit_region(proj, t, c)


def midi_regions(t):
    return sorted((c for c in t.get('clips', []) if c.get('kind') == 'midi'), key=lambda c: c['start'])


def has_own_pattern(t, c):
    return c.get('kind') == 'midi' and ('pattern' in c if t['type'] == 'drum' else isinstance(c.get('notes'), list))


def region_data(t, src):
    """Independent copy of a pattern (drum: pattern; synth: bars + notes) – every region owns one."""
    if t['type'] == 'drum':
        return {'pattern': json.loads(json.dumps(src['pattern']))}
    return {'bars': src.get('bars', 1), 'notes': json.loads(json.dumps(src.get('notes') or []))}


def empty_region_data(t, bars, sig):
    n = int(round(bars * sig * 4))
    if t['type'] == 'drum':
        return {'pattern': {'bars': bars, 'grid': [[0] * n for _ in DRUM_IDS], 'ids': list(DRUM_IDS)}, 'linear': True}
    return {'bars': bars, 'notes': [], 'linear': True}


def fill_regions(proj):
    """Every MIDI region owns LITERAL pads/notes for its whole length (= ensureRegions in app.js): regions without data
    get the track template unrolled over their length, old looping regions are unrolled once, lengths are fitted."""
    spb = steps_per_bar(proj)
    for t in proj.get('tracks', []):
        if t.get('type') not in ('drum', 'synth'):
            continue
        for c in t.get('clips', []):
            if c.get('kind') != 'midi':
                continue
            if not has_own_pattern(t, c):
                c.update(region_data(t, t))
                linearize(proj, t, c, pat_steps(proj, t))
            elif not c.get('linear'):
                bars = c['pattern']['bars'] if t['type'] == 'drum' else c.get('bars', 1)
                linearize(proj, t, c, round(bars * spb))
            else:
                fit_region(proj, t, c)


def pattern_to_row(pattern, steps):
    """'x...o..g' (x/X/1/* = hit 100%, o = soft 60%, g = ghost 30%, anything else = rest; spaces and | ignored)
    -> list of velocities (0 = rest), repeated to fill."""
    clean = [ch for ch in str(pattern) if ch not in ' |']
    if not clean:
        raise ModelError("pattern must not be empty")
    row = [1 if ch in 'xX1*' else VEL_CHAR.get(ch, 0) for ch in clean]
    return [row[i % len(row)] for i in range(steps)]


def row_to_pattern(row):
    return ''.join('.' if not v else 'x' if v >= 0.75 else 'o' if v >= 0.45 else 'g' for v in row)


def note_name(midi):
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def parse_note(value):
    """MIDI number or name like 'E2', 'C#3', 'Bb1' -> MIDI number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    m = re.fullmatch(r"\s*([A-Ga-g])([#b]?)(-?\d)\s*", str(value))
    if not m:
        raise ModelError(f"invalid note '{value}' (use MIDI number or a name like E2, C#3)")
    base = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[m.group(1).upper()]
    base += {'#': 1, 'b': -1, '': 0}[m.group(2)]
    return (int(m.group(3)) + 1) * 12 + base


def drum_row(part):
    key = re.sub(r"[^a-z]", "", str(part).lower())
    key = DRUM_ALIASES.get(key, key)
    for i, (pid, name) in enumerate(DRUMS):
        if key == pid or key == re.sub(r"[^a-z]", "", name.lower()):
            return i
    raise ModelError(f"unknown drum part '{part}'. Parts: " + ', '.join(f"{p} ({n})" for p, n in DRUMS))


def find_track(proj, track):
    """Track by id, exact name, or 1-based index."""
    tracks = proj['tracks']
    for t in tracks:
        if t['id'] == track:
            return t
    for t in tracks:
        if str(t['name']).lower() == str(track).lower():
            return t
    if str(track).isdigit() and 1 <= int(track) <= len(tracks):
        return tracks[int(track) - 1]
    raise ModelError(f"track '{track}' not found. Tracks: " + ', '.join(f"{t['name']} ({t['id']})" for t in tracks))


def find_clip(proj, clip_id):
    for t in proj['tracks']:
        for c in t['clips']:
            if c['id'] == clip_id:
                return t, c
    raise ModelError(f"clip '{clip_id}' not found")


def migrate_drums(proj):
    """Re-map drum grids of older projects to the current kit row order (adds pattern['ids'])."""
    for t in proj.get('tracks', []):
        if t.get('type') != 'drum':
            continue
        for h in [t] + list(t.get('clips', [])):  # the track template and every region's own pattern
            if not h.get('pattern'):
                continue
            ids = h['pattern'].get('ids') or LEGACY_DRUM_IDS
            if list(ids) == DRUM_IDS:
                continue
            grid = h['pattern'].get('grid') or []
            n = len(grid[0]) if grid else pat_steps(proj, h)
            h['pattern']['grid'] = [list(grid[ids.index(pid)]) if pid in ids and ids.index(pid) < len(grid) else [0] * n for pid in DRUM_IDS]
            h['pattern']['ids'] = list(DRUM_IDS)


def migrate_strings(proj):
    """Older projects stored guitar/bass as oscillator synths (no 'engine' key): switch them to natural string defaults."""
    for t in proj.get('tracks', []):
        s = t.get('synth')
        if t.get('type') != 'synth' or not s:
            continue
        kp = SYNTH_PRESETS.get(s.get('preset')) or {}
        if s.get('engine') == 'voice' and kp.get('engine') == 'sample':  # choir: formant synth -> real recording
            s.update({**SYNTH_DEFAULTS, **kp, 'preset': s['preset']})
        if s.get('preset') == 'Palm Mute Guitar' and s.get('sample') == 'electric_guitar_clean':  # real palm-muted recording
            s.update({k: kp[k] for k in ('sample', 'cutoff', 'decay')})
        if not t.get('instrument') and s.get('preset') == 'Bass':
            t['instrument'] = 'bass'
        if t.get('instrument') not in ('guitar', 'bass'):
            continue
        known = SYNTH_PRESETS.get(s.get('preset')) or {}
        if 'engine' not in s or (s['engine'] == 'string' and known.get('engine') == 'sample'):
            p = s['preset'] if known.get('engine') == 'sample' else DEFAULT_GUITAR_PRESET if t['instrument'] == 'guitar' else DEFAULT_BASS_PRESET
            t['synth'] = {'preset': p, **SYNTH_DEFAULTS, **SYNTH_PRESETS[p]}


def normalize_amp(t):
    """Amp distortion lives in the track's own Effects chain (visible, per layer): a synth 'drive' becomes an
    auto 'amp' insert effect on that track (mirrors normalizeAmp() in app.js)."""
    s = t.get('synth')
    if not s or not (s.get('drive') or 0) > 0:
        return
    t.setdefault('fx', [])
    g = s.get('gain') or 1
    vals = {'gain': clamp(round(-20 * math.log10(g) * 2) / 2, 0, 36), 'drive': s['drive'], 'tone': 4800,
            'level': round(g * (0.45 if (s.get('susLevel') if s.get('susLevel') is not None else 1) <= 0.001 else 1), 2)}
    old = next((f for f in t['fx'] if f.get('type') == 'amp' and f.get('auto')), None)
    if old:
        old['p'].update(vals)
    else:
        f = new_fx('amp', vals)
        f['auto'] = True
        t['fx'].insert(0, f)
    s['drive'] = 0


def apply_synth_preset(t, name):
    """Choose an instrument preset for one track; replaces the amp the previous preset added (this track only)."""
    t['synth'] = {**SYNTH_DEFAULTS, **SYNTH_PRESETS[name], 'preset': name}
    t['fx'] = [f for f in t.get('fx') or [] if not (f.get('type') == 'amp' and f.get('auto'))]
    normalize_amp(t)


def apply_drum_preset(proj, t, preset):
    if preset not in DRUM_PRESETS:
        raise ModelError(f"unknown drum preset '{preset}'. Presets: " + ', '.join(DRUM_PRESETS))
    pr = DRUM_PRESETS[preset]
    need = -(-max([16] + [len(v) for v in pr.values()]) // 16)  # 2-bar presets extend a 1-bar pattern
    if t.get('kind') != 'midi' and t['pattern'].get('bars', 1) < need:  # regions keep their own length
        t['pattern']['bars'] = need
    n = pat_steps(proj, t)
    t['pattern']['grid'] = [[VEL_CHAR.get(pr[pid][i % len(pr[pid])], 0) if pr.get(pid) else 0 for i in range(n)] for pid in DRUM_IDS]


def resize_grid(proj, t):
    n = pat_steps(proj, t)
    t['pattern']['grid'] = [(r + [0] * n)[:n] for r in t['pattern']['grid']]


def clip_len_beats(proj, c):
    """Length of a clip in beats (MIDI region: len; audio clip: duration at the project tempo). Mirrors clipLenBeats() in app.js."""
    return c['len'] if c.get('kind') == 'midi' else (c.get('dur') or 0) * (proj.get('bpm') or 120) / 60


def set_clip_fades(proj, c, fade_in_sec=None, fade_out_sec=None, fade_in_beats=None, fade_out_beats=None):
    """Fade in / fade out of ONE clip or region, like the UI's fade dialog: values in seconds (or beats), stored in beats
    (c['fi'] / c['fo']) so they follow the region when the tempo changes; 0 = off; fade in + fade out <= region length."""
    spb = 60 / (proj.get('bpm') or 120)
    length = clip_len_beats(proj, c)
    items = [('fi', fade_in_sec, fade_in_beats), ('fo', fade_out_sec, fade_out_beats)]
    items.sort(key=lambda it: 0 if (it[1] if it[1] is not None else it[2]) in (0, 0.0) else 1)  # turn fades off first, then grow
    for key, sec, beats in items:
        if sec is None and beats is None:
            continue
        v = num(sec, 'fade_%s_sec' % ('in' if key == 'fi' else 'out'), 0, 100000) / spb if sec is not None \
            else num(beats, 'fade_%s_beats' % ('in' if key == 'fi' else 'out'), 0, 100000)
        other = c.get('fo' if key == 'fi' else 'fi') or 0
        v = min(v, max(0.0, length - other))  # a fade can cover the whole region, but never overlap the other fade
        if v < 1e-6:
            c.pop(key, None)
        else:
            c[key] = round(v, 4)


def clip_fade_info(proj, c):
    """Fade / volume fields of a clip for get_project (seconds and beats)."""
    spb = 60 / (proj.get('bpm') or 120)
    out = {}
    if c.get('fi'):
        out.update(fade_in_beats=c['fi'], fade_in_sec=round(c['fi'] * spb, 3))
    if c.get('fo'):
        out.update(fade_out_beats=c['fo'], fade_out_sec=round(c['fo'] * spb, 3))
    if c.get('gain') is not None and c.get('gain') != 1:
        out['volume_percent'] = round(c['gain'] * 100, 1)
    out['length_sec'] = round(clip_len_beats(proj, c) * spb, 3)
    return out


def new_track(proj, kind, name=None):
    if kind not in TRACK_TYPES:
        raise ModelError(f"type must be one of {', '.join(TRACK_TYPES)}")
    ttype = 'synth' if kind in ('guitar', 'bass', 'vocal') else kind
    tracks = proj['tracks']
    inst = kind if kind in ('guitar', 'bass', 'vocal') else None
    n = sum(1 for x in tracks if x['type'] == ttype and x.get('instrument') == inst) + 1
    default = {'audio': 'Audio ', 'drum': 'Drums ', 'synth': 'Synth ', 'guitar': 'Guitar ', 'bass': 'Bass ', 'vocal': 'Voice '}[kind] + str(n)
    if kind in ('bass', 'vocal') and n == 1:
        default = default.strip()[:-2]
    t = {'id': nid('t'), 'type': ttype, 'name': (name or default)[:60], 'color': COLORS[len(tracks) % len(COLORS)],
         'vol': 0.8, 'pan': 0, 'mute': False, 'solo': False, 'arm': False, 'eq': {'low': 0, 'mid': 0, 'high': 0},
         'comp': {'thr': 0, 'ratio': 1}, 'rev': 0, 'dly': 0, 'fx': [], 'clips': []}
    if ttype == 'drum':
        t['pattern'] = {'bars': 1, 'grid': [], 'ids': list(DRUM_IDS)}
        apply_drum_preset(proj, t, DEFAULT_DRUM_PRESET)
        t['rev'] = 0.12
        t['kit'] = {}
        t['feel'] = {'hum': 6, 'swing': 0, 'push': 0}
    if ttype == 'synth':
        preset = {'guitar': DEFAULT_GUITAR_PRESET, 'bass': DEFAULT_BASS_PRESET, 'vocal': DEFAULT_VOCAL_PRESET}.get(kind, 'Piano')  # natural (recorded) by default
        t['synth'] = {'preset': preset, **SYNTH_DEFAULTS, **SYNTH_PRESETS[preset]}
        t['bars'] = 1
        t['notes'] = []
        if inst:
            t['instrument'] = inst
        if kind == 'vocal':
            t['fx'] = [new_fx(ty, o) for ty, o in CHOIR_FX]
    if ttype == 'audio':
        t['arm'] = not any(x.get('arm') for x in tracks)
    tracks.append(t)
    return t


def new_fx(fx_type, params=None, on=True):
    if fx_type not in FX_TYPES:
        raise ModelError(f"unknown effect '{fx_type}'. Effects: " + ', '.join(FX_TYPES))
    spec = FX_TYPES[fx_type]
    p = {k: v[0] for k, v in spec.items()}
    for k, v in (params or {}).items():
        if k not in spec:
            raise ModelError(f"effect '{fx_type}' has no parameter '{k}'. Parameters: " + ', '.join(spec))
        if isinstance(spec[k][1], list):
            if v not in spec[k][1]:
                raise ModelError(f"'{k}' must be one of {spec[k][1]}")
            p[k] = v
        else:
            p[k] = num(v, k, spec[k][1], spec[k][2])
    return {'id': nid('f'), 'type': fx_type, 'on': bool(on), 'p': p}


# ------------------------------------------------------------------ summaries
def _notes_out(notes):
    return [{'pitch': n['p'], 'note': note_name(n['p']), 'step': n['s'] + 1, 'length': n['l']} for n in sorted(notes, key=lambda n: (n['s'], n['p']))]


def _region_detail(t, c):
    if not has_own_pattern(t, c):
        return {}
    if t['type'] == 'drum':
        return {'pattern_bars': c['pattern']['bars'], 'pads': {pid: row_to_pattern(c['pattern']['grid'][i]) for i, (pid, _) in enumerate(DRUMS)}}
    return {'pattern_bars': c.get('bars', 1), 'notes': _notes_out(c['notes'])}


def track_summary(proj, t, detail=True):
    out = {'id': t['id'], 'name': t['name'], 'type': t.get('instrument') or t['type'],
           'volume': t['vol'], 'pan': t['pan'], 'mute': t['mute'], 'solo': t['solo'],
           'eq': t['eq'], 'comp': t['comp'], 'reverb_send': t['rev'], 'delay_send': t['dly'],
           'fx': [{'id': f['id'], 'type': f['type'], 'on': f['on'], 'params': f['p']} for f in t.get('fx', [])],
           'clips': [{'id': c['id'], 'kind': c['kind'], 'start_beat': c['start'],
                      **({'length_beats': c['len']} if c['kind'] == 'midi' else {'duration_sec': c.get('dur'), 'offset_sec': c.get('offset')}),
                      **clip_fade_info(proj, c),
                      **(_region_detail(t, c) if detail else {})}
                     for c in t['clips']]}
    # top-level pads / notes = the track template (used by whole-track MCP edits and as the start of new regions);
    # every region in 'clips' reports its OWN pattern – regions are independent
    if detail and t['type'] == 'drum':
        out['pattern_bars'] = t['pattern']['bars']
        out['pads'] = {pid: row_to_pattern(t['pattern']['grid'][i]) for i, (pid, _) in enumerate(DRUMS)}
        out['kit'] = {pid: {**KIT_DEFAULT, **(t.get('kit') or {}).get(pid, {})} for pid in DRUM_IDS}
    if detail and t['type'] == 'synth':
        out['pattern_bars'] = t.get('bars', 1)
        out['synth'] = t['synth']
        out['notes'] = _notes_out(t['notes'])
    return out


def project_summary(doc, detail=True):
    proj = doc['project']
    return {'title': proj.get('title'), 'bpm': proj.get('bpm'), 'time_signature': f"{proj.get('sig', 4)}/4",
            'steps_per_bar': steps_per_bar(proj), 'master': {**MASTER_DEFAULT, **(proj.get('master') or {})},
            'tracks': [track_summary(proj, t, detail) for t in proj['tracks']],
            'audio_files': {k: v.get('name', '') for k, v in (doc.get('audio') or {}).items()}}


def clone(o):
    return copy.deepcopy(o)
