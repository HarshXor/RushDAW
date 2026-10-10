"""Server-side model of a RushDAW project (mirrors static/app.js).

Used by the MCP tools to read and edit ``.rushdaw`` project documents without a
browser.  Every structure produced here must be loadable by the web UI, so the
constants below are kept in sync with ``static/app.js`` (see tests).
"""
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
DRUM_PRESETS = {
    'Metal Double Bass': {'kick': 'xxxxxxxxxxxxxxxx', 'snare': '....x.......x...', 'crash': 'x...............', 'ride': 'x...x...x...x...'},
    'Metal Gallop': {'kick': 'x.xxx.xxx.xxx.xx', 'snare': '....x.......x...', 'crash': 'x...x...x...x...'},
    'Blast Beat': {'kick': 'x.x.x.x.x.x.x.x.', 'snare': '.x.x.x.x.x.x.x.x', 'crash': 'x.......x.......'},
    'Hammer Blast': {'kick': 'x.x.x.x.x.x.x.x.', 'snare': 'x.x.x.x.x.x.x.x.', 'ride': 'x...x...x...x...'},
    'Thrash Skank': {'kick': 'x...x...x...x...', 'snare': '..x...x...x...x.', 'crash': 'x.x.x.x.x.x.x.x.'},
    'Hardcore Breakdown': {'kick': 'x..x..x...x..x..', 'snare': '........x.......', 'crash': 'x.......x.......', 'toml': '......x.......x.', 'phh': '..x...x...x...x.'},
    'Hardcore Two-Step': {'kick': 'x.xx....x.xx....', 'snare': '....x.......x...', 'chh': 'x.x.x.x.x.x.x.x.', 'crash': 'x...............'},
    'D-Beat': {'kick': 'x.xx..x.x.xx..x.', 'snare': '....x.......x...', 'crash': 'x.x.x.x.x.x.x.x.'},
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
SYNTH_DEFAULTS = {'engine': 'osc', 'sample': 'electric_guitar_clean', 'drive': 0, 'chord': 'none', 'pluck': 0, 'brightness': 0.5, 'sustain': 0.5, 'pick': 0.13, 'body': 0.5}
DEFAULT_GUITAR_PRESET, DEFAULT_BASS_PRESET = 'Clean Guitar', 'Finger Bass'
SAMPLE_SETS = ['electric_guitar_clean', 'acoustic_guitar_steel', 'electric_bass_finger', 'electric_bass_pick']
_SMP = {'engine': 'sample', 'wave': 'sawtooth', 'attack': 0.001, 'detune': 0, 'pluck': 0}
SYNTH_PRESETS = {
    # real instruments: recorded guitar / bass (FluidR3_GM soundfont)
    'Clean Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.25, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none'},
    'Acoustic Guitar': {**_SMP, 'sample': 'acoustic_guitar_steel', 'release': 0.35, 'cutoff': 12000, 'gain': 0.6, 'drive': 0, 'chord': 'none'},
    'Finger Bass': {**_SMP, 'sample': 'electric_bass_finger', 'release': 0.15, 'cutoff': 12000, 'gain': 0.75, 'drive': 0, 'chord': 'none'},
    'Pick Bass': {**_SMP, 'sample': 'electric_bass_pick', 'release': 0.12, 'cutoff': 12000, 'gain': 0.75, 'drive': 0, 'chord': 'none'},
    # synth sounds (oscillators)
    'Keys': {'wave': 'triangle', 'attack': 0.005, 'release': 0.4, 'cutoff': 5000, 'detune': 4, 'gain': 0.5},
    'Synth Bass': {'wave': 'sawtooth', 'attack': 0.005, 'release': 0.15, 'cutoff': 900, 'detune': 0, 'gain': 0.55},
    'Lead': {'wave': 'square', 'attack': 0.01, 'release': 0.2, 'cutoff': 3500, 'detune': 8, 'gain': 0.35},
    'Pad': {'wave': 'sawtooth', 'attack': 0.5, 'release': 1.2, 'cutoff': 2200, 'detune': 12, 'gain': 0.3},
    'Pluck': {'wave': 'sawtooth', 'attack': 0.002, 'release': 0.12, 'cutoff': 2600, 'detune': 5, 'gain': 0.4},
    'Sub 808': {'wave': 'sine', 'attack': 0.003, 'release': 0.6, 'cutoff': 400, 'detune': 0, 'gain': 0.8},
    # amped guitars: real clean guitar recording -> amp distortion -> cabinet
    'Crunch Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.15, 'cutoff': 6000, 'gain': 0.4, 'drive': 0.35, 'chord': 'none'},
    'Distortion Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.12, 'cutoff': 5000, 'gain': 0.32, 'drive': 0.8, 'chord': 'none'},
    'Power Chord Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.12, 'cutoff': 5000, 'gain': 0.26, 'drive': 0.8, 'chord': 'power'},
    'Palm Mute Guitar': {**_SMP, 'sample': 'electric_guitar_clean', 'release': 0.05, 'cutoff': 1800, 'gain': 0.32, 'drive': 0.75, 'chord': 'power', 'pluck': 0.12},
    # modeled string (Karplus-Strong), kept for experimenting
    'Modeled String': {'engine': 'string', 'wave': 'sawtooth', 'attack': 0.002, 'release': 0.12, 'cutoff': 3800, 'detune': 0, 'gain': 0.55, 'drive': 0, 'chord': 'none', 'pluck': 0, 'brightness': 0.4, 'sustain': 0.55, 'pick': 0.14, 'body': 0.5},
}
SYNTH_PARAMS = {  # name: (min, max) or list of choices
    'engine': ['sample', 'string', 'osc'], 'sample': list(SAMPLE_SETS), 'wave': ['sine', 'triangle', 'square', 'sawtooth'], 'attack': (0.001, 2), 'release': (0.01, 3),
    'cutoff': (100, 12000), 'detune': (0, 50), 'gain': (0, 1.5), 'drive': (0, 1), 'pluck': (0, 3), 'chord': ['none', 'power'],
    'brightness': (0.05, 1), 'sustain': (0, 1), 'pick': (0.02, 0.5), 'body': (0, 1),
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
    'filter': {'mode': ('lowpass', ['lowpass', 'highpass', 'bandpass']), 'freq': (2000, 30, 18000), 'q': (1, 0.1, 15)},
    'chorus': {'rate': (1.5, 0.1, 8), 'depth': (0.004, 0, 0.012), 'mix': (0.5, 0, 1)},
    'tremolo': {'rate': (5, 0.5, 20), 'depth': (0.5, 0, 1)},
    'delay': {'time': (0.75, 0.125, 2), 'feedback': (0.35, 0, 0.9), 'tone': (5000, 500, 12000), 'mix': (0.3, 0, 1)},
    'reverb': {'size': (2, 0.2, 8), 'tone': (8000, 1000, 16000), 'mix': (0.3, 0, 1)},
}
KIT_DEFAULT = {'pitch': 0, 'decay': 1, 'level': 1}
KIT_RANGES = {'pitch': (-24, 24), 'decay': (0.1, 4), 'level': (0, 2)}  # wide: ±2 octaves, 10-400% decay, 0-200% level
TRACK_TYPES = ('audio', 'drum', 'synth', 'guitar', 'bass')
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
    bars = t['pattern']['bars'] if t['type'] == 'drum' else t.get('bars', 1)
    return int(bars) * steps_per_bar(proj)


def pattern_to_row(pattern, steps):
    """'x...x...' (x/X/1/* = hit, anything else = rest; spaces and | ignored) -> list of 0/1, repeated to fill."""
    clean = [ch for ch in str(pattern) if ch not in ' |']
    if not clean:
        raise ModelError("pattern must not be empty")
    row = [1 if ch in 'xX1*' else 0 for ch in clean]
    return [row[i % len(row)] for i in range(steps)]


def row_to_pattern(row):
    return ''.join('x' if v else '.' for v in row)


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
        if t.get('type') != 'drum' or not t.get('pattern'):
            continue
        ids = t['pattern'].get('ids') or LEGACY_DRUM_IDS
        if list(ids) == DRUM_IDS:
            continue
        grid = t['pattern'].get('grid') or []
        n = len(grid[0]) if grid else pat_steps(proj, t)
        t['pattern']['grid'] = [list(grid[ids.index(pid)]) if pid in ids and ids.index(pid) < len(grid) else [0] * n for pid in DRUM_IDS]
        t['pattern']['ids'] = list(DRUM_IDS)


def migrate_strings(proj):
    """Older projects stored guitar/bass as oscillator synths (no 'engine' key): switch them to natural string defaults."""
    for t in proj.get('tracks', []):
        s = t.get('synth')
        if t.get('type') != 'synth' or not s:
            continue
        if not t.get('instrument') and s.get('preset') == 'Bass':
            t['instrument'] = 'bass'
        if t.get('instrument') not in ('guitar', 'bass'):
            continue
        known = SYNTH_PRESETS.get(s.get('preset')) or {}
        if 'engine' not in s or (s['engine'] == 'string' and known.get('engine') == 'sample'):
            p = s['preset'] if known.get('engine') == 'sample' else DEFAULT_GUITAR_PRESET if t['instrument'] == 'guitar' else DEFAULT_BASS_PRESET
            t['synth'] = {'preset': p, **SYNTH_DEFAULTS, **SYNTH_PRESETS[p]}


def apply_drum_preset(proj, t, preset):
    if preset not in DRUM_PRESETS:
        raise ModelError(f"unknown drum preset '{preset}'. Presets: " + ', '.join(DRUM_PRESETS))
    n = pat_steps(proj, t)
    pr = DRUM_PRESETS[preset]
    t['pattern']['grid'] = [[1 if pr.get(pid) and pr[pid][i % 16] == 'x' else 0 for i in range(n)] for pid in DRUM_IDS]


def resize_grid(proj, t):
    n = pat_steps(proj, t)
    t['pattern']['grid'] = [(r + [0] * n)[:n] for r in t['pattern']['grid']]


def new_track(proj, kind, name=None):
    if kind not in TRACK_TYPES:
        raise ModelError(f"type must be one of {', '.join(TRACK_TYPES)}")
    ttype = 'synth' if kind in ('guitar', 'bass') else kind
    tracks = proj['tracks']
    inst = kind if kind in ('guitar', 'bass') else None
    n = sum(1 for x in tracks if x['type'] == ttype and x.get('instrument') == inst) + 1
    default = {'audio': 'Audio ', 'drum': 'Drums ', 'synth': 'Synth ', 'guitar': 'Guitar ', 'bass': 'Bass '}[kind] + str(n)
    if kind == 'bass' and n == 1:
        default = 'Bass'
    t = {'id': nid('t'), 'type': ttype, 'name': (name or default)[:60], 'color': COLORS[len(tracks) % len(COLORS)],
         'vol': 0.8, 'pan': 0, 'mute': False, 'solo': False, 'arm': False, 'eq': {'low': 0, 'mid': 0, 'high': 0},
         'comp': {'thr': 0, 'ratio': 1}, 'rev': 0, 'dly': 0, 'fx': [], 'clips': []}
    if ttype == 'drum':
        t['pattern'] = {'bars': 1, 'grid': [], 'ids': list(DRUM_IDS)}
        apply_drum_preset(proj, t, DEFAULT_DRUM_PRESET)
        t['rev'] = 0.12
        t['kit'] = {}
    if ttype == 'synth':
        preset = {'guitar': DEFAULT_GUITAR_PRESET, 'bass': DEFAULT_BASS_PRESET}.get(kind, 'Keys')
        t['synth'] = {'preset': preset, **SYNTH_DEFAULTS, **SYNTH_PRESETS[preset]}
        t['bars'] = 1
        t['notes'] = []
        if inst:
            t['instrument'] = inst
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
def track_summary(proj, t, detail=True):
    out = {'id': t['id'], 'name': t['name'], 'type': t.get('instrument') or t['type'],
           'volume': t['vol'], 'pan': t['pan'], 'mute': t['mute'], 'solo': t['solo'],
           'eq': t['eq'], 'comp': t['comp'], 'reverb_send': t['rev'], 'delay_send': t['dly'],
           'fx': [{'id': f['id'], 'type': f['type'], 'on': f['on'], 'params': f['p']} for f in t.get('fx', [])],
           'clips': [{'id': c['id'], 'kind': c['kind'], 'start_beat': c['start'],
                      **({'length_beats': c['len']} if c['kind'] == 'midi' else {'duration_sec': c.get('dur'), 'offset_sec': c.get('offset')})}
                     for c in t['clips']]}
    if detail and t['type'] == 'drum':
        out['pattern_bars'] = t['pattern']['bars']
        out['pads'] = {pid: row_to_pattern(t['pattern']['grid'][i]) for i, (pid, _) in enumerate(DRUMS)}
        out['kit'] = {pid: {**KIT_DEFAULT, **(t.get('kit') or {}).get(pid, {})} for pid in DRUM_IDS}
    if detail and t['type'] == 'synth':
        out['pattern_bars'] = t.get('bars', 1)
        out['synth'] = t['synth']
        out['notes'] = [{'pitch': n['p'], 'note': note_name(n['p']), 'step': n['s'] + 1, 'length': n['l']} for n in sorted(t['notes'], key=lambda n: (n['s'], n['p']))]
    return out


def project_summary(doc, detail=True):
    proj = doc['project']
    return {'title': proj.get('title'), 'bpm': proj.get('bpm'), 'time_signature': f"{proj.get('sig', 4)}/4",
            'steps_per_bar': steps_per_bar(proj), 'master': {**MASTER_DEFAULT, **(proj.get('master') or {})},
            'tracks': [track_summary(proj, t, detail) for t in proj['tracks']],
            'audio_files': {k: v.get('name', '') for k, v in (doc.get('audio') or {}).items()}}


def clone(o):
    return copy.deepcopy(o)
