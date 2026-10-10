/* RushDAW – browser DAW engine + UI (Web Audio API) */
'use strict';
const $ = s => document.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k in e && k !== 'list') e[k] = v; else e.setAttribute(k, v);
  }
  kids.flat().forEach(c => c != null && e.append(c));
  return e;
};
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const dbToGain = db => Math.pow(10, db / 20);
const gainToDb = g => g <= 0.00001 ? -Infinity : 20 * Math.log10(g);
const fmtDb = g => { const d = gainToDb(g); return d === -Infinity ? '-∞' : d.toFixed(1); };
let uidN = 1;
const nid = p => `${p}${Date.now().toString(36)}${(uidN++).toString(36)}`;

const COLORS = ['#00e5ff', '#ffffff', '#7fffd4', '#00b8d4', '#b2f5ff', '#4dd0e1', '#d9d9d9', '#1de9b6'];
const DRUMS = [
  { id: 'kick', name: 'Kick' }, { id: 'snare', name: 'Snare' }, { id: 'chh', name: 'Closed Hi-Hat' },
  { id: 'ohh', name: 'Open Hi-Hat' }, { id: 'tomh', name: 'High Tom' }, { id: 'tomm', name: 'Mid Tom' },
  { id: 'toml', name: 'Floor Tom' }, { id: 'crash', name: 'Crash Cymbal' }, { id: 'ride', name: 'Ride Cymbal' },
  { id: 'phh', name: 'Pedal Hi-Hat' },
];
const DRUM_IDS = DRUMS.map(d => d.id);
// row order used by projects saved before pattern.ids existed (9-part kit)
const LEGACY_DRUM_IDS = ['kick', 'snare', 'ride', 'chh', 'ohh', 'tomh', 'toml', 'rim', 'crash'];
// re-map a drum track's grid rows to the current kit order (keeps old projects intact)
function migrateDrumTrack(t) {
  if (t.type !== 'drum') return;
  [t, ...t.clips].forEach(h => {  // the track's template pattern and every region's own pattern
    if (!h.pattern) return;
    const ids = h.pattern.ids || LEGACY_DRUM_IDS;
    if (ids.join() === DRUM_IDS.join()) return;
    const n = (h.pattern.grid[0] || []).length || h.pattern.bars * 16;
    h.pattern.grid = DRUM_IDS.map(id => { const i = ids.indexOf(id); return i >= 0 && h.pattern.grid[i] ? h.pattern.grid[i].slice() : Array(n).fill(0); });
    h.pattern.ids = DRUM_IDS.slice();
  });
}
const DEFAULT_DRUM_PRESET = 'Metal Double Bass';
const DRUM_PRESETS = {
  // --- metal / hardcore / punk (16 steps = one 4/4 bar of 16th notes) ---
  'Metal Double Bass': { kick: 'xxxxxxxxxxxxxxxx', snare: '....x.......x...', crash: 'x...............', ride: 'x...x...x...x...' },
  'Metal Gallop': { kick: 'x.xxx.xxx.xxx.xx', snare: '....x.......x...', crash: 'x...x...x...x...' },
  'Blast Beat': { kick: 'x.x.x.x.x.x.x.x.', snare: '.x.x.x.x.x.x.x.x', crash: 'x.......x.......' },
  'Hammer Blast': { kick: 'x.x.x.x.x.x.x.x.', snare: 'x.x.x.x.x.x.x.x.', ride: 'x...x...x...x...' },
  'Thrash Skank': { kick: 'x...x...x...x...', snare: '..x...x...x...x.', crash: 'x.x.x.x.x.x.x.x.' },
  'Hardcore Breakdown': { kick: 'x..x..x...x..x..', snare: '........x.......', crash: 'x.......x.......', toml: '......x.......x.', phh: '..x...x...x...x.' },
  'Hardcore Two-Step': { kick: 'x.xx....x.xx....', snare: '....x.......x...', chh: 'x.x.x.x.x.x.x.x.', crash: 'x...............' },
  'D-Beat': { kick: 'x..x.x..x..x.x..', snare: '..x...x...x...x.', ohh: 'x.x.x.x.x.x.x.x.', crash: 'x...............' },
  // 2 bars: crash on the 1, OPEN hi-hat 8ths (not under the crash), snare on every '&', kick K..K.K.. (classic Discharge d-beat)
  'Crust D-Beat': { kick: 'x..x.x..x..x.x..x..x.x..x..x.x..', snare: '..x...x...x...x...x...x...x...x.',
    ohh: '..x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.', crash: 'x...............................' },
  'Punk Beat': { kick: 'x.x...x.x.x...x.', snare: '....x.......x...', chh: 'x.x.x.x.x.x.x.x.', crash: 'x...............' },
  'Punk Polka': { kick: 'x...x...x...x...', snare: '..x...x...x...x.', chh: 'x.x.x.x.x.x.x.x.' },
  'Pop-Punk Drive': { kick: 'x.....x.x.......', snare: '....x.......x...', ohh: 'x.x.x.x.x.x.x.x.', crash: 'x...............' },
  // --- other genres ---
  'Four on the floor': { kick: 'x...x...x...x...', snare: '....x.......x...', chh: '..x...x...x...x.', ohh: '......x.......x.' },
  'Rock': { kick: 'x.......x.x.....', snare: '....x.......x...', chh: 'x.x.x.x.x.x.x.x.', crash: 'x...............' },
  'Hip-Hop': { kick: 'x......x..x.....', snare: '....x.......x...', chh: 'x.x.x.x.x.x.xxx.', ohh: '...........x....' },
  'Trap': { kick: 'x.....x...x.....', snare: '........x.......', chh: 'xxxxxxxxx.xxxxxx', ohh: '.......x........' },
  'Reggaeton': { kick: 'x...x...x...x...', snare: '...x..x....x..x.', chh: 'x.x.x.x.x.x.x.x.' },
  'Empty': {},
};
const SYNTH_PRESETS = {
  // --- real instruments (engine 'sample' = recorded guitar / bass, FluidR3_GM soundfont) ---
  'Clean Guitar': { engine: 'sample', sample: 'electric_guitar_clean', wave: 'sawtooth', attack: 0.001, release: 0.3, cutoff: 12000, detune: 0, gain: 0.6, drive: 0, chord: 'none', pluck: 0, decay: 2.0, susLevel: 0.35 },
  'Acoustic Guitar': { engine: 'sample', sample: 'acoustic_guitar_steel', wave: 'sawtooth', attack: 0.001, release: 0.4, cutoff: 12000, detune: 0, gain: 0.6, drive: 0, chord: 'none', pluck: 0, decay: 2.5, susLevel: 0.3 },
  'Finger Bass': { engine: 'sample', sample: 'electric_bass_finger', wave: 'sawtooth', attack: 0.001, release: 0.2, cutoff: 12000, detune: 0, gain: 0.75, drive: 0, chord: 'none', pluck: 0, decay: 2.5, susLevel: 0.45 },
  'Pick Bass': { engine: 'sample', sample: 'electric_bass_pick', wave: 'sawtooth', attack: 0.001, release: 0.15, cutoff: 12000, detune: 0, gain: 0.75, drive: 0, chord: 'none', pluck: 0, decay: 2.0, susLevel: 0.4 },
  // --- synth sounds (oscillators) ---
  'Keys': { wave: 'triangle', attack: 0.005, release: 0.4, cutoff: 5000, detune: 4, gain: 0.5 },
  'Synth Bass': { wave: 'sawtooth', attack: 0.005, release: 0.15, cutoff: 900, detune: 0, gain: 0.55 },
  'Lead': { wave: 'square', attack: 0.01, release: 0.2, cutoff: 3500, detune: 8, gain: 0.35 },
  'Pad': { wave: 'sawtooth', attack: 0.5, release: 1.2, cutoff: 2200, detune: 12, gain: 0.3 },
  'Pluck': { wave: 'sawtooth', attack: 0.002, release: 0.12, cutoff: 2600, detune: 5, gain: 0.4 },
  'Sub 808': { wave: 'sine', attack: 0.003, release: 0.6, cutoff: 400, detune: 0, gain: 0.8 },
  // --- amped guitars: the real clean guitar recording through amp distortion + cabinet ---
  'Crunch Guitar': { engine: 'sample', sample: 'electric_guitar_clean', wave: 'sawtooth', attack: 0.001, release: 0.2, cutoff: 6000, detune: 0, gain: 0.4, drive: 0.35, chord: 'none', pluck: 0, decay: 3.0, susLevel: 0.6 },
  'Distortion Guitar': { engine: 'sample', sample: 'electric_guitar_clean', wave: 'sawtooth', attack: 0.001, release: 0.2, cutoff: 5000, detune: 0, gain: 0.32, drive: 0.8, chord: 'none', pluck: 0, decay: 4.0, susLevel: 0.75 },
  'Power Chord Guitar': { engine: 'sample', sample: 'electric_guitar_clean', wave: 'sawtooth', attack: 0.001, release: 0.2, cutoff: 5000, detune: 0, gain: 0.26, drive: 0.8, chord: 'power', pluck: 0, decay: 4.0, susLevel: 0.75 },
  'Palm Mute Guitar': { engine: 'sample', sample: 'electric_guitar_clean', wave: 'sawtooth', attack: 0.001, release: 0.05, cutoff: 1800, detune: 0, gain: 0.32, drive: 0.75, chord: 'power', pluck: 0, decay: 0.18, susLevel: 0.0 },
  // --- modeled string (Karplus-Strong), kept for experimenting ---
  'Modeled String': { engine: 'string', wave: 'sawtooth', attack: 0.002, release: 0.12, cutoff: 3800, detune: 0, gain: 0.55, drive: 0, chord: 'none', pluck: 0, brightness: 0.4, sustain: 0.55, pick: 0.14, body: 0.5 },
};
const MASTER_PRESETS = {
  'Flat (off)': { eqLow: 0, eqMid: 0, eqHigh: 0, compThr: 0, compRatio: 1, makeup: 0, ceiling: -0.3 },
  'Balanced': { eqLow: 1, eqMid: 0, eqHigh: 1.5, compThr: -18, compRatio: 2.5, makeup: 3, ceiling: -1 },
  'Loud Pop': { eqLow: 2, eqMid: -1, eqHigh: 3, compThr: -24, compRatio: 4, makeup: 7, ceiling: -0.5 },
  'Warm': { eqLow: 3, eqMid: 0.5, eqHigh: -2, compThr: -20, compRatio: 3, makeup: 4, ceiling: -1 },
  'Bass Boost': { eqLow: 5, eqMid: -1, eqHigh: 0.5, compThr: -20, compRatio: 3, makeup: 4, ceiling: -1 },
  'Bright': { eqLow: -1, eqMid: 1, eqHigh: 4, compThr: -18, compRatio: 2.5, makeup: 3, ceiling: -1 },
};
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const LOW_NOTE = 36, HIGH_NOTE = 84;

/* ------------------------------------------------------------------ state */
const P = {
  title: 'My Song', bpm: 180, sig: 4, tracks: [], loop: { start: 0, end: 16 },
  master: { vol: 1, eqLow: 0, eqMid: 0, eqHigh: 0, compThr: -18, compRatio: 2.5, compAtk: 0.01, compRel: 0.25, makeup: 3, ceiling: -1, reverbSize: 2.5, delayDiv: 0.75, delayFb: 0.35 },
};
const buffers = new Map();   // bufId -> AudioBuffer
const bufNames = new Map();  // bufId -> file name
const peaksCache = new Map();
let ctx = null, rt = null;
let selTrackId = null, selClipId = null;
const T = { playing: false, recording: false, pos: 0, segs: [], cursor: 0, first: true, timer: null, sources: [], click: false, clickBefore: -1e9 };

const pxB = () => +$('#zoom').value;          // pixels per beat
const spb = () => 60 / P.bpm;                  // seconds per beat
const stepsPerBar = () => P.sig * 4;
const getTrack = id => P.tracks.find(t => t.id === id);
const findClip = id => { for (const t of P.tracks) { const c = t.clips.find(c => c.id === id); if (c) return [t, c]; } return [null, null]; };
const clipLenBeats = c => c.kind === 'audio' ? c.dur / spb() : c.len;
const songEndBeats = () => {
  let e = 0;
  P.tracks.forEach(t => t.clips.forEach(c => { e = Math.max(e, c.start + clipLenBeats(c)); }));
  return e;
};
const status = msg => { $('#status').textContent = msg; };

function newTrack(type) {
  const n = P.tracks.filter(t => t.type === type).length + 1;
  const t = {
    id: nid('t'), type, name: (type === 'audio' ? 'Audio ' : type === 'drum' ? 'Drums ' : 'Synth ') + n,
    color: COLORS[P.tracks.length % COLORS.length], vol: 0.8, pan: 0, mute: false, solo: false, arm: false,
    eq: { low: 0, mid: 0, high: 0 }, comp: { thr: 0, ratio: 1 }, rev: 0, dly: 0, fx: [], clips: [],
  };
  if (type === 'drum') { t.pattern = { bars: 1, grid: DRUMS.map(() => Array(stepsPerBar()).fill(0)), ids: DRUM_IDS.slice() }; applyDrumPreset(t, DEFAULT_DRUM_PRESET); t.rev = 0.12; /* a little room = acoustic kit feel */ }
  if (type === 'synth') { t.synth = { preset: 'Keys', ...SYNTH_PRESETS.Keys }; t.bars = 1; t.notes = []; }
  if (type === 'audio') t.arm = !P.tracks.some(x => x.arm);
  P.tracks.push(t);
  return t;
}
/* MIDI regions are LINEAR, not loops: every MIDI region (clip) owns its pads/notes for its whole length – step k of
   the region (16th notes from the region start) sounds exactly where it is, nothing repeats. Drum regions keep
   c.pattern {bars, grid, ids} with one grid column per 16th of the region; synth/guitar/bass regions keep c.notes.
   Extending a region adds EMPTY steps, shortening cuts the end. The track's own t.pattern / t.notes is only the
   template used when a track has no region yet (and by whole-track MCP edits). */
const regionSteps = c => Math.max(1, Math.round(c.len * 4));
const patBars = h => h.kind === 'midi' ? h.len / P.sig : h.pattern ? h.pattern.bars : (h.bars || 1);
const patSteps = h => h.kind === 'midi' ? regionSteps(h) : patBars(h) * stepsPerBar();
const isPatHolder = (t, c) => c && c.kind === 'midi' && (t.type === 'drum' ? !!c.pattern : Array.isArray(c.notes));
const regionData = (t, src) => t.type === 'drum'
  ? { pattern: JSON.parse(JSON.stringify(src.pattern)) }
  : { bars: src.bars || 1, notes: JSON.parse(JSON.stringify(src.notes || [])) };
// unroll a looping pattern (older projects / the track template) into literal steps over the region length
function linearize(t, c, srcSteps) {
  const n = regionSteps(c), m = Math.max(1, srcSteps);
  if (t.type === 'drum') c.pattern.grid = c.pattern.grid.map(r => Array.from({ length: n }, (_, i) => r.length ? (r[i % m] || 0) : 0));
  else {
    const out = [];
    for (let off = 0; off < n; off += m) c.notes.forEach(x => { if (x.s < m && off + x.s < n) out.push({ ...x, s: off + x.s, l: Math.min(x.l, n - off - x.s) }); });
    c.notes = out;
  }
  c.linear = true; fitRegion(t, c);
}
// make the region's data exactly as long as the region: new steps are empty, steps past the end are cut
function fitRegion(t, c) {
  const n = regionSteps(c);
  if (t.type === 'drum') {
    c.pattern.grid = c.pattern.grid.map(r => r.length === n ? r : r.slice(0, n).concat(Array(Math.max(0, n - r.length)).fill(0)));
    c.pattern.bars = c.len / P.sig;
  } else {
    c.notes = c.notes.filter(x => x.s < n).map(x => x.s + x.l > n ? { ...x, l: n - x.s } : x);
    c.bars = c.len / P.sig;
  }
}
// every region owns literal data: fill regions without data from the template, unroll old looping regions once
function ensureRegions() {
  P.tracks.forEach(t => {
    if (t.type !== 'drum' && t.type !== 'synth') return;
    t.clips.forEach(c => {
      if (c.kind !== 'midi') return;
      if (!isPatHolder(t, c)) { Object.assign(c, regionData(t, t)); linearize(t, c, patBars(t) * stepsPerBar()); }
      else if (!c.linear) linearize(t, c, Math.round((c.pattern ? c.pattern.bars : (c.bars || 1)) * stepsPerBar()));
      else if (t.type === 'drum' ? (c.pattern.grid[0] || []).length !== regionSteps(c) : false) fitRegion(t, c);
    });
  });
}
const nextFreeBar = t => { const last = t.clips.reduce((a, c) => Math.max(a, c.start + clipLenBeats(c)), 0); return t.clips.length ? Math.ceil(last / P.sig - 1e-9) * P.sig : Math.floor(T.pos / P.sig) * P.sig; };
const midiRegions = t => t.clips.filter(c => c.kind === 'midi').sort((a, b) => a.start - b.start);
// the region shown in the editor: the selected region of this track, else its first region, else the track template
function edHolder(t) {
  const sel = t.clips.find(c => c.id === selClipId);
  if (sel && sel.kind === 'midi') return sel;
  return midiRegions(t)[0] || t;
}
// empty region (blank pads / no notes), length in bars
function newEmptyRegion(t, start, bars = 1) {
  const len = bars * P.sig, n = Math.round(len * 4);
  const c = { id: nid('c'), kind: 'midi', start, len, linear: true,
    ...(t.type === 'drum' ? { pattern: { bars, grid: DRUMS.map(() => Array(n).fill(0)), ids: DRUM_IDS.slice() } } : { bars, notes: [] }) };
  t.clips.push(c); return c;
}
// region that starts as an exact (independent) copy of another region or of the track template
function newRegion(t, start, src = edHolder(t)) {
  const isReg = src.kind === 'midi';
  const c = { id: nid('c'), kind: 'midi', start, len: isReg ? src.len : patBars(src) * P.sig, ...regionData(t, src) };
  t.clips.push(c);
  if (isReg) { c.linear = true; fitRegion(t, c); } else linearize(t, c, patSteps(src));
  return c;
}
function resizeGrid(t) {
  const n = patSteps(t);
  t.pattern.grid = t.pattern.grid.map(r => { const a = r.slice(0, n); while (a.length < n) a.push(0); return a; });
}
// presets are 16 (1 bar) or 32 (2 bars) steps long; a 2-bar preset extends a 1-bar pattern to 2 bars
function applyDrumPreset(t, name) {
  const pr = DRUM_PRESETS[name];
  const need = Math.ceil(Math.max(16, ...Object.values(pr).map(s => s.length)) / 16);
  if (t.kind !== 'midi' && t.pattern.bars < need) t.pattern.bars = need;  // regions keep their own length
  const n = patSteps(t);
  t.pattern.grid = DRUMS.map(d => Array.from({ length: n }, (_, i) => { const s = pr[d.id]; return s && s[i % s.length] === 'x' ? 1 : 0; }));
}

/* ------------------------------------------------------------ audio engine */
function ensureCtx() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'interactive' });
    rt = createGraph(ctx, true);
  }
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}
const noiseCache = new WeakMap();
function noise(c) {
  if (noiseCache.has(c)) return noiseCache.get(c);
  const b = c.createBuffer(1, c.sampleRate * 2, c.sampleRate); const d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  noiseCache.set(c, b); return b;
}
function makeIR(c, secs) {
  const len = Math.max(1, Math.floor(c.sampleRate * secs)); const b = c.createBuffer(2, len, c.sampleRate);
  for (let ch = 0; ch < 2; ch++) { const d = b.getChannelData(ch); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3); }
  return b;
}
function setP(param, v, c, live) { if (live) param.setTargetAtTime(v, c.currentTime, 0.015); else param.value = v; }

function createGraph(c, live) {
  const g = { c, live, tracks: new Map() };
  g.in = c.createGain();
  g.low = c.createBiquadFilter(); g.low.type = 'lowshelf'; g.low.frequency.value = 120;
  g.mid = c.createBiquadFilter(); g.mid.type = 'peaking'; g.mid.frequency.value = 1200; g.mid.Q.value = 0.8;
  g.high = c.createBiquadFilter(); g.high.type = 'highshelf'; g.high.frequency.value = 8000;
  g.comp = c.createDynamicsCompressor(); g.makeup = c.createGain();
  g.lim = c.createDynamicsCompressor(); g.lim.knee.value = 0; g.lim.ratio.value = 20; g.lim.attack.value = 0.001; g.lim.release.value = 0.08;
  g.out = c.createGain(); g.an = c.createAnalyser(); g.an.fftSize = 2048;
  g.in.connect(g.low); g.low.connect(g.mid); g.mid.connect(g.high); g.high.connect(g.comp);
  g.comp.connect(g.makeup); g.makeup.connect(g.lim); g.lim.connect(g.out); g.out.connect(g.an); g.an.connect(c.destination);
  g.revIn = c.createGain(); g.conv = c.createConvolver(); g.irSize = P.master.reverbSize; g.conv.buffer = makeIR(c, g.irSize);
  g.revIn.connect(g.conv); g.conv.connect(g.in);
  g.dlyIn = c.createGain(); g.dly = c.createDelay(5); g.fb = c.createGain(); g.dlyLp = c.createBiquadFilter(); g.dlyLp.frequency.value = 4500;
  g.dlyIn.connect(g.dly); g.dly.connect(g.dlyLp); g.dlyLp.connect(g.fb); g.fb.connect(g.dly); g.dlyLp.connect(g.in);
  g.click = c.createGain(); g.click.gain.value = 0.6; g.click.connect(c.destination);
  applyMaster(g); syncGraph(g);
  return g;
}
function applyMaster(g) {
  const m = P.master, c = g.c, L = g.live;
  setP(g.low.gain, m.eqLow, c, L); setP(g.mid.gain, m.eqMid, c, L); setP(g.high.gain, m.eqHigh, c, L);
  setP(g.comp.threshold, m.compThr, c, L); setP(g.comp.ratio, m.compRatio, c, L);
  setP(g.comp.attack, m.compAtk, c, L); setP(g.comp.release, m.compRel, c, L);
  setP(g.makeup.gain, dbToGain(m.makeup), c, L); setP(g.lim.threshold, m.ceiling, c, L);
  setP(g.out.gain, m.vol, c, L);
  setP(g.dly.delayTime, Math.min(4.9, m.delayDiv * spb()), c, L); setP(g.fb.gain, m.delayFb, c, L);
  if (Math.abs(g.irSize - m.reverbSize) > 0.01) { g.irSize = m.reverbSize; g.conv.buffer = makeIR(c, m.reverbSize); }
}
function trackNodes(g, t) {
  let n = g.tracks.get(t.id);
  if (n) return n;
  const c = g.c;
  n = { in: c.createGain(), low: c.createBiquadFilter(), mid: c.createBiquadFilter(), high: c.createBiquadFilter(),
    comp: c.createDynamicsCompressor(), fader: c.createGain(), pan: c.createStereoPanner(), rev: c.createGain(), dly: c.createGain(), an: c.createAnalyser() };
  n.low.type = 'lowshelf'; n.low.frequency.value = 150; n.mid.type = 'peaking'; n.mid.frequency.value = 1500; n.mid.Q.value = 0.9;
  n.high.type = 'highshelf'; n.high.frequency.value = 6000; n.an.fftSize = 1024;
  n.fxUnits = new Map(); n.fxKey = null; // insert FX chain lives between n.in and n.low (built in applyTrack)
  n.low.connect(n.mid); n.mid.connect(n.high); n.high.connect(n.comp); n.comp.connect(n.fader);
  n.fader.connect(n.pan); n.pan.connect(g.in); n.pan.connect(n.rev); n.rev.connect(g.revIn); n.pan.connect(n.dly); n.dly.connect(g.dlyIn); n.pan.connect(n.an);
  g.tracks.set(t.id, n); applyTrack(g, t);
  return n;
}
function applyTrack(g, t) {
  const n = trackNodes(g, t), c = g.c, L = g.live;
  buildFxChain(g, t, n);
  (t.fx || []).forEach(fx => { const u = n.fxUnits.get(fx.id); if (u) setFxUnit(u, fx, c, L); });
  const anySolo = P.tracks.some(x => x.solo);
  const audible = !t.mute && (!anySolo || t.solo);
  setP(n.low.gain, t.eq.low, c, L); setP(n.mid.gain, t.eq.mid, c, L); setP(n.high.gain, t.eq.high, c, L);
  setP(n.comp.threshold, t.comp.thr, c, L); setP(n.comp.ratio, t.comp.ratio, c, L);
  setP(n.fader.gain, audible ? t.vol : 0, c, L); setP(n.pan.pan, t.pan, c, L);
  setP(n.rev.gain, t.rev, c, L); setP(n.dly.gain, t.dly, c, L);
}
function syncGraph(g = rt) {
  if (!g) return;
  for (const [id, n] of g.tracks) if (!getTrack(id)) { n.pan.disconnect(); n.fxUnits.forEach(disposeFxUnit); g.tracks.delete(id); }
  P.tracks.forEach(t => applyTrack(g, t));
  applyMaster(g);
}

/* ------------------------------------------------- per-track insert effects */
// param spec: [default, min, max, step, unit]  (or [default, [choices]] for selects)
const FX_TYPES = {
  eq: { name: 'EQ', params: { low: [0, -15, 15, 0.5, 'dB'], lowF: [120, 30, 600, 1, 'Hz'], mid: [0, -15, 15, 0.5, 'dB'], midF: [1000, 200, 8000, 10, 'Hz'], high: [0, -15, 15, 0.5, 'dB'], highF: [6000, 1500, 16000, 10, 'Hz'] } },
  comp: { name: 'Compressor', params: { thr: [-20, -60, 0, 1, 'dB'], ratio: [4, 1, 20, 0.5, ':1'], attack: [0.01, 0.001, 0.3, 0.001, 's'], release: [0.2, 0.02, 1, 0.01, 's'], makeup: [3, 0, 24, 0.5, 'dB'] } },
  dist: { name: 'Distortion', params: { drive: [0.5, 0, 1, 0.01, ''], tone: [4500, 500, 12000, 10, 'Hz'], level: [0.6, 0, 1.5, 0.01, ''], mix: [1, 0, 1, 0.01, ''] } },
  // guitar amp: input gain -> distortion -> highpass 90 Hz -> cabinet lowpass (Tone) -> output Level
  amp: { name: 'Guitar Amp', params: { gain: [10, 0, 36, 0.5, 'dB'], drive: [0.8, 0, 1, 0.01, ''], tone: [4800, 500, 12000, 10, 'Hz'], level: [0.32, 0, 1.5, 0.01, ''] } },
  filter: { name: 'Filter', params: { mode: ['lowpass', ['lowpass', 'highpass', 'bandpass']], freq: [2000, 30, 18000, 1, 'Hz'], q: [1, 0.1, 15, 0.1, ''] } },
  chorus: { name: 'Chorus', params: { rate: [1.5, 0.1, 8, 0.1, 'Hz'], depth: [0.004, 0, 0.012, 0.0005, 's'], mix: [0.5, 0, 1, 0.01, ''] } },
  tremolo: { name: 'Tremolo', params: { rate: [5, 0.5, 20, 0.1, 'Hz'], depth: [0.5, 0, 1, 0.01, ''] } },
  delay: { name: 'Delay', params: { time: [0.75, 0.125, 2, 0.125, 'beat'], feedback: [0.35, 0, 0.9, 0.01, ''], tone: [5000, 500, 12000, 10, 'Hz'], mix: [0.3, 0, 1, 0.01, ''] } },
  reverb: { name: 'Reverb', params: { size: [2, 0.2, 8, 0.1, 's'], tone: [8000, 1000, 16000, 10, 'Hz'], mix: [0.3, 0, 1, 0.01, ''] } },
};
const FX_CHAIN_PRESETS = {
  'Vocal': [['eq', { low: -4, lowF: 120, mid: 1.5, midF: 2500, high: 3 }], ['comp', { thr: -24, ratio: 4, makeup: 6 }], ['delay', { time: 0.5, feedback: 0.25, mix: 0.12 }], ['reverb', { size: 2.2, mix: 0.25 }]],
  'Guitar Amp': [['dist', { drive: 0.7, tone: 4200, level: 0.5 }], ['eq', { low: -2, mid: 2.5, midF: 1800, high: -1 }], ['reverb', { size: 1.2, mix: 0.15 }]],
  'Metal Guitar': [['filter', { mode: 'highpass', freq: 90, q: 0.7 }], ['dist', { drive: 0.9, tone: 5000, level: 0.45 }], ['eq', { low: 2, lowF: 110, mid: -4, midF: 700, high: 3, highF: 4000 }], ['comp', { thr: -18, ratio: 3, makeup: 2 }]],
  'Drum Bus': [['comp', { thr: -18, ratio: 4, attack: 0.02, release: 0.15, makeup: 4 }], ['eq', { low: 3, lowF: 80, high: 2, highF: 8000 }], ['dist', { drive: 0.15, mix: 0.3, level: 0.9 }]],
  'Bass': [['comp', { thr: -20, ratio: 5, makeup: 4 }], ['eq', { low: 3, lowF: 80, mid: -2, midF: 400 }], ['filter', { mode: 'lowpass', freq: 6000, q: 0.7 }]],
  'Lo-Fi': [['filter', { mode: 'lowpass', freq: 3200, q: 0.8 }], ['dist', { drive: 0.3, mix: 0.4 }], ['chorus', { rate: 0.6, depth: 0.006, mix: 0.4 }]],
  'Clear (no FX)': [],
};
const FX_LABELS = { low: 'Low', lowF: 'Low freq', mid: 'Mid', midF: 'Mid freq', high: 'High', highF: 'High freq', thr: 'Threshold', ratio: 'Ratio', attack: 'Attack', release: 'Release', makeup: 'Make-up', gain: 'Input gain', drive: 'Drive', tone: 'Tone', level: 'Level', mix: 'Mix', mode: 'Mode', freq: 'Cutoff', q: 'Resonance', rate: 'Rate', depth: 'Depth', time: 'Time', feedback: 'Feedback', size: 'Size' };
function newFx(type, over = {}) {
  const p = {}; for (const [k, v] of Object.entries(FX_TYPES[type].params)) p[k] = v[0];
  return { id: nid('f'), type, on: true, p: { ...p, ...over } };
}
function makeFxUnit(c, type) {
  const u = { type, in: c.createGain(), out: c.createGain(), N: {}, oscs: [], ir: null }, N = u.N;
  const wetDry = () => { N.dry = c.createGain(); N.wet = c.createGain(); u.in.connect(N.dry); N.dry.connect(u.out); N.wet.connect(u.out); };
  const bq = t => { const f = c.createBiquadFilter(); f.type = t; return f; };
  switch (type) {
    case 'eq': N.l = bq('lowshelf'); N.m = bq('peaking'); N.m.Q.value = 1; N.h = bq('highshelf'); u.in.connect(N.l); N.l.connect(N.m); N.m.connect(N.h); N.h.connect(u.out); break;
    case 'comp': N.c = c.createDynamicsCompressor(); N.g = c.createGain(); u.in.connect(N.c); N.c.connect(N.g); N.g.connect(u.out); break;
    case 'dist': wetDry(); N.ws = c.createWaveShaper(); N.ws.oversample = '4x'; N.lp = bq('lowpass'); N.lvl = c.createGain(); u.in.connect(N.ws); N.ws.connect(N.lp); N.lp.connect(N.lvl); N.lvl.connect(N.wet); break;
    case 'filter': N.f = bq('lowpass'); u.in.connect(N.f); N.f.connect(u.out); break;
    case 'amp': N.pre = c.createGain(); N.ws = c.createWaveShaper(); N.ws.oversample = '4x'; N.hp = bq('highpass'); N.hp.frequency.value = 90;
      N.cab = bq('lowpass'); N.cab.Q.value = 0.7; N.lvl = c.createGain();
      u.in.connect(N.pre); N.pre.connect(N.ws); N.ws.connect(N.hp); N.hp.connect(N.cab); N.cab.connect(N.lvl); N.lvl.connect(u.out); break;
    case 'chorus': wetDry(); N.d = c.createDelay(0.1); N.d.delayTime.value = 0.018; N.lfo = c.createOscillator(); N.dep = c.createGain();
      N.lfo.connect(N.dep); N.dep.connect(N.d.delayTime); u.in.connect(N.d); N.d.connect(N.wet); N.lfo.start(); u.oscs.push(N.lfo); break;
    case 'tremolo': N.amp = c.createGain(); N.lfo = c.createOscillator(); N.dep = c.createGain();
      N.lfo.connect(N.dep); N.dep.connect(N.amp.gain); u.in.connect(N.amp); N.amp.connect(u.out); N.lfo.start(); u.oscs.push(N.lfo); break;
    case 'delay': wetDry(); N.d = c.createDelay(5); N.fb = c.createGain(); N.lp = bq('lowpass'); u.in.connect(N.d); N.d.connect(N.lp); N.lp.connect(N.fb); N.fb.connect(N.d); N.lp.connect(N.wet); break;
    case 'reverb': wetDry(); N.cv = c.createConvolver(); N.lp = bq('lowpass'); u.in.connect(N.cv); N.cv.connect(N.lp); N.lp.connect(N.wet); break;
  }
  return u;
}
function setFxUnit(u, fx, c, L) {
  const p = fx.p, N = u.N, s = (param, v) => setP(param, v, c, L);
  switch (u.type) {
    case 'eq': s(N.l.frequency, p.lowF); s(N.l.gain, p.low); s(N.m.frequency, p.midF); s(N.m.gain, p.mid); s(N.h.frequency, p.highF); s(N.h.gain, p.high); break;
    case 'comp': s(N.c.threshold, p.thr); s(N.c.ratio, p.ratio); s(N.c.attack, p.attack); s(N.c.release, p.release); s(N.g.gain, dbToGain(p.makeup)); break;
    case 'dist': N.ws.curve = distCurve(1 + Math.round(p.drive * 60)); s(N.lp.frequency, p.tone); s(N.lvl.gain, p.level); s(N.wet.gain, p.mix); s(N.dry.gain, 1 - p.mix); break;
    case 'amp': if (u.drv !== p.drive) { u.drv = p.drive; N.ws.curve = distCurve(1 + Math.round(p.drive * 40)); }
      s(N.pre.gain, dbToGain(p.gain)); s(N.cab.frequency, p.tone); s(N.lvl.gain, p.level); break;
    case 'filter': N.f.type = p.mode; s(N.f.frequency, p.freq); s(N.f.Q, p.q); break;
    case 'chorus': s(N.lfo.frequency, p.rate); s(N.dep.gain, p.depth); s(N.wet.gain, p.mix); s(N.dry.gain, 1 - p.mix * 0.5); break;
    case 'tremolo': s(N.lfo.frequency, p.rate); s(N.amp.gain, 1 - p.depth / 2); s(N.dep.gain, p.depth / 2); break;
    case 'delay': s(N.d.delayTime, Math.min(4.9, p.time * spb())); s(N.fb.gain, p.feedback); s(N.lp.frequency, p.tone); s(N.wet.gain, p.mix); s(N.dry.gain, 1); break;
    case 'reverb': if (u.ir !== p.size) { u.ir = p.size; N.cv.buffer = makeIR(c, p.size); } s(N.lp.frequency, p.tone); s(N.wet.gain, p.mix); s(N.dry.gain, 1 - p.mix * 0.5); break;
  }
}
function disposeFxUnit(u) { u.oscs.forEach(o => { try { o.stop(); } catch (e) { /* stopped */ } }); u.in.disconnect(); u.out.disconnect(); }
// (re)wire n.in -> [enabled FX in order] -> n.low whenever the chain structure changes
function buildFxChain(g, t, n) {
  const active = (t.fx || []).filter(f => f.on);
  const key = active.map(f => f.id + f.type).join('|');
  if (n.fxKey === key) return;
  n.fxKey = key;
  for (const [id, u] of n.fxUnits) if (!active.some(f => f.id === id)) { disposeFxUnit(u); n.fxUnits.delete(id); }
  n.in.disconnect(); n.fxUnits.forEach(u => u.out.disconnect());
  let prev = n.in;
  active.forEach(f => {
    let u = n.fxUnits.get(f.id);
    if (!u) { u = makeFxUnit(g.c, f.type); n.fxUnits.set(f.id, u); }
    prev.connect(u.in); prev = u.out;
  });
  prev.connect(n.low);
}

/* instruments: synthesized drum kit + subtractive synth */
function env(c, gainParam, t, peak, decay) {
  gainParam.setValueAtTime(0.0001, t); gainParam.exponentialRampToValueAtTime(peak, t + 0.002);
  gainParam.exponentialRampToValueAtTime(0.0001, t + decay);
}
// per-part kit settings (stored on the drum track: t.kit[partId])
const KIT_DEFAULT = { pitch: 0, decay: 1, level: 1 };
// wide tuning ranges: ±24 semitones (two octaves), 10%..400% decay, 0..200% level
const KIT_RANGES = { pitch: [-24, 24], decay: [0.1, 4], level: [0, 2] };
// Tune is stored in semitones (compatible with saved projects / MCP) and shown as pitch percent: 100% = default tuning
const fmtTunePct = st => Math.round(Math.pow(2, st / 12) * 100) + '%';
// returns the part's settings object itself (filled with defaults in place) – never a copy, so the
// editor sliders, preview and playback always read and write the same object
function kitOf(track, id) {
  track.kit = track.kit || {};
  const k = track.kit[id] || (track.kit[id] = {});
  for (const [key, v] of Object.entries(KIT_DEFAULT)) if (typeof k[key] !== 'number') k[key] = v;
  return k;
}
// kind = drum part id, t = start time, vel = velocity, kit = { pitch (semitones), decay (x), level (x) }
function playDrum(c, dest, kind, t, vel = 1, kit = KIT_DEFAULT) {
  const srcs = [];
  const pr = Math.pow(2, (kit.pitch || 0) / 12), dk = kit.decay || 1;
  const F = f => Math.min(18000, f * pr), D = d => d * dk;
  const out = c.createGain(); out.gain.value = vel * (kit.level ?? 1); out.connect(dest);
  const osc = (type, f0, f1, dur, peak, start = t) => {
    const o = c.createOscillator(), g = c.createGain(); o.type = type; dur = D(dur);
    o.frequency.setValueAtTime(F(f0), start); o.frequency.exponentialRampToValueAtTime(F(f1), start + dur * 0.6);
    env(c, g.gain, start, peak, dur); o.connect(g); g.connect(out); o.start(start); o.stop(start + dur + 0.05); srcs.push(o);
  };
  const nz = (ftype, freq, dur, peak, q = 0.7, start = t) => {
    const s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(); dur = D(dur);
    s.buffer = noise(c); f.type = ftype; f.frequency.value = F(freq); f.Q.value = q;
    env(c, g.gain, start, peak, dur);
    s.connect(f); f.connect(g); g.connect(out); s.start(start, Math.random()); s.stop(start + dur + 0.05); srcs.push(s);
  };
  // acoustic drumhead mode: sine with a small pitch drop and natural exponential ring
  const mode = (f, dur, peak, drop = 0.96, type = 'sine') => osc(type, f, f * drop, dur, peak);
  // metallic partials (inharmonic square bank) through a filter -> cymbal shimmer
  const metal = (base, ftype, ffreq, dur, peak, q = 0.7) => {
    const f = c.createBiquadFilter(), g = c.createGain(); f.type = ftype; f.frequency.value = F(ffreq); f.Q.value = q; dur = D(dur);
    env(c, g.gain, t, peak, dur); f.connect(g); g.connect(out);
    [1, 1.342, 1.2312, 1.6532, 1.9523, 2.1523].forEach(r => {
      const o = c.createOscillator(); o.type = 'square'; o.frequency.value = F(base * r); o.connect(f); o.start(t); o.stop(t + dur + 0.05); srcs.push(o);
    });
  };
  // stick hitting a cymbal: short bright "tick" that gives cymbals their punch
  const stick = (freq, peak) => nz('bandpass', freq, 0.025, peak, 0.9);
  switch (kind) {
    // metal kick (triggered, underground style): low thump + punchy body + hard beater click
    case 'kick':
      // gains scaled so the raw (pre-fader) kick peak stays <= 1.0
      osc('sine', 125, 52, 0.32, 0.42); mode(68, 0.22, 0.17, 0.85);
      nz('highpass', 2800, 0.018, 0.25, 0.8); osc('triangle', 1600, 900, 0.012, 0.15); break;
    // rock / metal snare (default tuning, use the part's Tune knob for higher/lower):
    // fat ~190 Hz head with natural overtones, hard stick crack, and a clear bottom snare-wire rattle
    case 'snare': {
      const f0 = 190;  // gains leave headroom: raw peak stays < 1.0 even with random noise
      mode(f0, 0.24, 0.32, 0.93, 'triangle'); mode(f0 * 1.59, 0.16, 0.15); mode(f0 * 2.14, 0.12, 0.08);
      nz('bandpass', 2000, 0.03, 0.24, 0.8);              // stick crack
      nz('bandpass', 4500, 0.26, 0.25, 0.55);             // bottom wires: main sizzle
      nz('highpass', 2000, 0.2, 0.2, 0.7);                // wires: body of the rattle
      nz('bandpass', 3200, 0.18, 0.13, 1.4, t + 0.008);   // wires: delayed buzz (wires react after the head)
      nz('highpass', 8000, 0.1, 0.09, 0.7); break;        // air / brightness
    }
    // ride: stick ping + strong bell + metallic wash
    case 'ride': stick(3200, 0.38); mode(2350, 0.8, 0.14, 1); mode(3520, 0.55, 0.1, 1); metal(480, 'bandpass', 6000, 1.3, 0.2, 0.6); nz('highpass', 6500, 1.0, 0.14); break;
    // hi-hats: stick tick + metallic partials + bright noise (acoustic, not 808)
    case 'chh': stick(4500, 0.32); metal(420, 'highpass', 7500, 0.06, 0.24); nz('highpass', 8000, 0.07, 0.38); break;
    case 'ohh': stick(4200, 0.3); metal(420, 'highpass', 7000, 0.55, 0.2); nz('highpass', 7500, 0.6, 0.32); break;
    // toms, rock / metal tuning: low and fat (12" ~170 Hz, 13" ~128 Hz, 16" floor ~88 Hz), natural pitch drop,
    // plus a bright stick attack so fast fills stay defined
    case 'tomh': mode(170, 0.62, 0.6, 0.9); mode(170 * 1.5, 0.3, 0.18); nz('lowpass', 4500, 0.03, 0.24); break;
    case 'tomm': mode(128, 0.72, 0.64, 0.89); mode(128 * 1.5, 0.35, 0.18); nz('lowpass', 4000, 0.032, 0.24); break;
    case 'toml': mode(88, 0.85, 0.68, 0.87); mode(88 * 1.5, 0.42, 0.18); nz('lowpass', 3500, 0.035, 0.24); break;
    // pedal hi-hat: foot closes the hats -> short "chick" + small low thud, no stick tick
    case 'phh': metal(420, 'highpass', 6500, 0.035, 0.2); nz('bandpass', 6000, 0.04, 0.3, 0.8); nz('bandpass', 900, 0.02, 0.1, 1); break;
    // crash: hard stick hit + loud metallic wash with a long tail
    case 'crash': stick(2600, 0.42); metal(380, 'highpass', 4200, 1.9, 0.16); nz('highpass', 3800, 2.1, 0.38); nz('bandpass', 6000, 0.45, 0.23, 0.8); break;
  }
  return srcs;
}
const midiFreq = m => 440 * Math.pow(2, (m - 69) / 12);
const SYNTH_DEFAULTS = { engine: 'osc', sample: 'electric_guitar_clean', decay: 1.5, susLevel: 0.3, drive: 0, chord: 'none', pluck: 0, brightness: 0.5, sustain: 0.5, pick: 0.13, body: 0.5 };
const DEFAULT_GUITAR_PRESET = 'Clean Guitar', DEFAULT_BASS_PRESET = 'Finger Bass';
/* amp distortion lives in the track's own Effects chain (visible + editable per layer), never hidden
   inside the instrument: a preset/synth "drive" becomes a 'Guitar Amp' insert effect on THAT track.
   Same signal as before: note*gain -> amp input (1/gain) -> distortion -> cab -> level (gain). */
function normalizeAmp(t) {
  const s = t.synth; if (!s || !(s.drive > 0)) return;
  t.fx = t.fx || [];
  const g = s.gain || 1, vals = { gain: clamp(Math.round(-20 * Math.log10(g) * 2) / 2, 0, 36), drive: s.drive, tone: 4800, level: +(g * (s.susLevel <= 0.001 ? 0.45 : 1)).toFixed(2) };  // muted chug: amp would flatten it -> -7 dB keeps the old loudness
  const old = t.fx.find(f => f.type === 'amp' && f.auto);
  if (old) Object.assign(old.p, vals); else { const f = newFx('amp', vals); f.auto = true; t.fx.unshift(f); }
  s.drive = 0;
}
// choose an instrument preset for one track: replaces the amp that the previous preset added (on this track only)
function applySynthPreset(t, name) {
  Object.assign(t.synth, SYNTH_DEFAULTS, SYNTH_PRESETS[name], { preset: name });
  t.fx = (t.fx || []).filter(f => !(f.type === 'amp' && f.auto));
  normalizeAmp(t);
}
/* older projects stored guitar/bass as oscillator synths (no 'engine' key) or modeled strings:
   switch them to the real recorded instruments (same preset name when it exists, else the default) */
function migrateStringTrack(t) {
  if (t.type !== 'synth' || !t.synth) return;
  if (!t.instrument && t.synth.preset === 'Bass') t.instrument = 'bass';
  if (t.instrument !== 'guitar' && t.instrument !== 'bass') return;
  const known = SYNTH_PRESETS[t.synth.preset];
  if (!('engine' in t.synth) || (t.synth.engine === 'string' && known?.engine === 'sample')) {
    const p = known?.engine === 'sample' ? t.synth.preset : t.instrument === 'guitar' ? DEFAULT_GUITAR_PRESET : DEFAULT_BASS_PRESET;
    t.synth = { preset: p, ...SYNTH_DEFAULTS, ...SYNTH_PRESETS[p] };
  }
}

/* Karplus-Strong plucked string: a short burst of (filtered) noise circulating in a delay line
   with a gentle lowpass + loss in the loop. Rendered once per (note, params) and cached. */
const stringCache = new Map();
const STRING_VARIANTS = 4;  // every pluck picks one of several excitations, so repeated notes are never identical
function stringBuffer(c, freq, seconds, s, variant = 0) {
  const sr = c.sampleRate, exact = sr / freq, N = Math.max(2, Math.round(exact));
  const bright = clamp(s.brightness ?? 0.5, 0.05, 1), sus = clamp(s.sustain ?? 0.5, 0, 1), pick = clamp(s.pick ?? 0.13, 0.02, 0.5);
  const t60 = 0.25 + sus * sus * 9;                         // ring time of a low note (higher notes die faster, like real strings)
  const len = Math.min(Math.ceil(Math.min(seconds, t60 * 1.2) * 4) / 4, 8);
  const key = [sr, N, bright.toFixed(2), sus.toFixed(2), pick.toFixed(2), len, variant].join('|');
  let entry = stringCache.get(key);
  if (!entry) {
    const L = Math.max(N * 2, Math.floor(len * sr)), buf = c.createBuffer(1, L, sr), y = buf.getChannelData(0);
    // excitation: noise softened by brightness, comb-filtered by the pick position (where the string is plucked)
    const ex = new Float32Array(N); let lp = 0, seed = N * 9301 + 49297 + variant * 7919;
    const rnd = () => ((seed = (seed * 233280 + 49297) % 2147483647) / 2147483647) * 2 - 1;
    const exA = 0.05 + 0.9 * bright * bright;                // pluck softness: lower = rounder attack (finger), higher = pick
    for (let i = 0; i < N; i++) { lp += exA * (rnd() - lp); ex[i] = lp; }
    const pd = Math.max(1, Math.round(N * pick));
    for (let i = N - 1; i >= pd; i--) ex[i] -= ex[i - pd];
    const rho = Math.pow(10, -3 * (N / sr) / t60);          // loss per trip around the loop
    const damp = 0.5 + 0.3 * bright;                        // loop lowpass: highs die faster than lows, like a real string
    for (let n = 0; n < L; n++) {
      const a = n >= N ? y[n - N] : 0, b = n >= N + 1 ? y[n - N - 1] : 0;
      y[n] = (n < N ? ex[n] : 0) + rho * (damp * a + (1 - damp) * b);
    }
    let pk = 0; for (let n = 0; n < L; n++) pk = Math.max(pk, Math.abs(y[n]));
    if (pk > 0) for (let n = 0; n < L; n++) y[n] /= pk;
    // short fade-out at the very end of the rendered buffer
    const fade = Math.min(L, Math.floor(sr * 0.02)); for (let n = 0; n < fade; n++) y[L - 1 - n] *= n / fade;
    entry = { buf, rate: N / exact };                       // playbackRate corrects the integer delay length -> exact pitch
    if (stringCache.size > 300) stringCache.delete(stringCache.keys().next().value);
    stringCache.set(key, entry);
  }
  return entry;
}
const distCache = new Map();
function distCurve(k) {
  if (distCache.has(k)) return distCache.get(k);
  const n = 2048, cv = new Float32Array(n);
  for (let i = 0; i < n; i++) { const x = i / (n - 1) * 2 - 1; cv[i] = Math.tanh(k * x) / Math.tanh(k); }
  distCache.set(k, cv); return cv;
}
/* Real recorded instruments (engine 'sample'): FluidR3_GM soundfont recordings (CC-BY 3.0, see static/samples/NOTICE.txt),
   one recording every 3 semitones; the nearest one is re-pitched by at most +-1.5 semitones. */
const SAMPLE_SETS = {
  electric_guitar_clean: { name: 'Electric Guitar (clean)', lo: 40, hi: 88 },
  acoustic_guitar_steel: { name: 'Acoustic Guitar (steel)', lo: 40, hi: 88 },
  electric_bass_finger: { name: 'Electric Bass (finger)', lo: 28, hi: 67 },
  electric_bass_pick: { name: 'Electric Bass (pick)', lo: 28, hi: 67 },
};
const SAMPLE_STEP = 3;
const sampleBank = new Map();   // set id -> Map(midi -> { buf, off })  (AudioBuffers are shared by all contexts)
const sampleLoads = new Map();  // set id -> Promise
let sampleDecoder = null;
function loadSampleSet(id) {
  const set = SAMPLE_SETS[id]; if (!set) return Promise.resolve();
  if (sampleLoads.has(id)) return sampleLoads.get(id);
  sampleDecoder = sampleDecoder || new OfflineAudioContext(1, 1, 48000);
  const bank = new Map(), jobs = [];
  for (let m = set.lo; m <= set.hi; m += SAMPLE_STEP) {
    jobs.push(fetch(`samples/${id}/${m}.mp3`).then(r => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
      .then(a => sampleDecoder.decodeAudioData(a)).then(buf => {
        // skip the mp3 encoder delay / leading silence so notes start exactly on the beat
        const y = buf.getChannelData(0); let pk = 0; for (const v of y) pk = Math.max(pk, Math.abs(v));
        let i = 0; while (i < y.length && Math.abs(y[i]) < pk * 0.02) i++;
        const off = Math.max(0, i - 24) / buf.sampleRate;
        bank.set(m, { ...prepSustain(buf, midiFreq(m), off), off, peak: pk });
      }).catch(e => console.warn('sample', id, m, e)));
  }
  const p = Promise.all(jobs).then(() => { sampleBank.set(id, bank); });
  sampleLoads.set(id, p); return p;
}
/* Make a recording sustainable like a real sampler instrument:
   1. after the pick attack (first ~80 ms) the recording's own fade-out is evened out to a steady level, so the
      Decay / Sustain / Release envelope (not the length of the recording) decides how the note fades;
   2. a pitch-synchronous sustain LOOP (~0.5 s, 1.0 s after the attack) with a 50 ms crossfade lets a note ring
      for as long as it is held, without a click or a pulse at the seam. */
function prepSustain(src, freq, off) {
  const sr = src.sampleRate, N = src.length, s0 = Math.round(off * sr);
  const out = sampleDecoder.createBuffer(src.numberOfChannels, N, sr);
  const win = Math.round(sr * 0.02), hop = Math.round(sr * 0.005);
  const mono = src.getChannelData(0), env = [];
  for (let a = s0; a + win < N; a += hop) { let e = 0; for (let k = a; k < a + win; k++) e += mono[k] * mono[k]; env.push(Math.sqrt(e / win) + 1e-6); }
  const envAt = idx => env[Math.max(0, Math.min(env.length - 1, Math.round((idx - s0) / hop)))];
  const tA = s0 + Math.round(sr * 0.08), ramp = Math.round(sr * 0.05), ref = envAt(tA);
  const P = sr / freq, ls = s0 + Math.round(sr * 1.0), Lp = Math.max(1, Math.round(Math.round(0.5 * sr / P) * P)), le = Math.min(ls + Lp, N - 1);
  const X = Math.min(Math.round(sr * 0.05), ls - tA - 1, le - ls - 1);
  for (let ch = 0; ch < src.numberOfChannels; ch++) {
    const x = src.getChannelData(ch), y = out.getChannelData(ch);
    for (let n = 0; n < N; n++) {
      if (n < tA) { y[n] = x[n]; continue; }
      const gFlat = Math.min(8, ref / envAt(n)), w = Math.min(1, (n - tA) / ramp);
      y[n] = x[n] * (1 + (gFlat - 1) * w);
    }
    for (let j = 0; j < X; j++) { const w = j / X, a = le - X + j, b = ls - X + j; y[a] = y[a] * (1 - w) + y[b] * w; }  // seam crossfade
    // re-pitched playback interpolates a few samples PAST loopEnd: make them the continuation of loopStart,
    // otherwise every loop wrap clicks
    for (let k = 0; k < 256 && le + k < N; k++) y[le + k] = y[ls + k];
  }
  return { buf: out, loopStart: ls / sr, loopEnd: le / sr };
}
const loadAllSamples = () => Promise.all(Object.keys(SAMPLE_SETS).map(loadSampleSet));
// before an offline render/export: make sure every sample set used by the project is decoded
async function samplesReady() {
  const ids = new Set(P.tracks.filter(t => t.synth?.engine === 'sample').map(t => t.synth.sample));
  await Promise.all([...ids].map(loadSampleSet));
}
function nearestSample(id, m) {
  const set = SAMPLE_SETS[id], bank = sampleBank.get(id); if (!set || !bank) return null;
  const k = clamp(set.lo + Math.round((m - set.lo) / SAMPLE_STEP) * SAMPLE_STEP, set.lo, set.hi);
  const e = bank.get(k); return e ? { ...e, rate: Math.pow(2, (m - k) / 12) } : null;
}
// Decay (s) and Sustain (0..1) of the sample engine; older tracks without them use their preset's values
const envOf = s => ({ decay: Math.max(0.03, s.decay ?? SYNTH_PRESETS[s.preset]?.decay ?? 1.5), sus: clamp(s.susLevel ?? SYNTH_PRESETS[s.preset]?.susLevel ?? 0.3, 0, 1) });
function playSynth(c, dest, s, midi, t, dur, vel = 1) {
  if (s.engine === 'sample' && !sampleBank.has(s.sample)) {
    // recordings still loading (first seconds after start): use the modeled string meanwhile
    loadSampleSet(s.sample); s = { ...s, engine: 'string' };
  }
  const f = c.createBiquadFilter(), g = c.createGain(); f.type = 'lowpass'; f.frequency.value = s.cutoff; f.Q.value = 1.2;
  const drive = s.drive || 0;
  if (drive > 0) {
    // amp distortion + guitar cabinet simulation
    const ws = c.createWaveShaper(), hp = c.createBiquadFilter(), cab = c.createBiquadFilter();
    ws.curve = distCurve(1 + Math.round(drive * 40)); ws.oversample = '4x';
    hp.type = 'highpass'; hp.frequency.value = 90; cab.type = 'lowpass'; cab.frequency.value = 4800; cab.Q.value = 0.7;
    f.connect(ws); ws.connect(hp); hp.connect(cab); cab.connect(g);
  } else f.connect(g);
  g.connect(dest);
  const isString = s.engine === 'string';
  let input = f;
  const isBass = /bass/i.test(s.preset || ''), extra = [];
  if (s.engine === 'sample') { t += Math.random() * 0.006; vel *= 0.92 + Math.random() * 0.08; }  // humanize timing + dynamics
  if (isString) {
    // humanize like a real player: small random timing (+-4 ms) and dynamics (+-10%)
    t += Math.random() * 0.008; vel *= 0.9 + Math.random() * 0.1;
    // instrument body: several wood resonances (air / top / back) + presence, deeper for bass;
    // plus a gentle "boxy" mid cut so it doesn't sound like a raw oscillator
    const bd = s.body ?? 0.5;
    const peaks = isBass ? [[85, 1.1, 6], [190, 1.4, 2.5], [700, 0.7, -2], [1100, 0.8, 1.5]]
                         : [[100, 1.2, 5], [210, 1.5, 4], [420, 1.3, 2], [1000, 0.7, -2.5], [2800, 0.8, 1.5]];
    let first = null, prev = null;
    peaks.forEach(([fr, q, gdb]) => {
      const p = c.createBiquadFilter(); p.type = 'peaking'; p.frequency.value = fr; p.Q.value = q;
      p.gain.value = gdb < 0 ? gdb : gdb * (0.4 + bd * 1.2);
      if (prev) prev.connect(p); else first = p; prev = p;
    });
    prev.connect(f); input = first;
    // attack transient: pick hitting the string (guitar) or finger/thumb thump (bass)
    const s0 = c.createBufferSource(), nf = c.createBiquadFilter(), ng = c.createGain();
    s0.buffer = noise(c); nf.type = 'bandpass'; nf.Q.value = 0.8;
    nf.frequency.value = isBass ? 380 + (s.brightness ?? 0.5) * 900 : 1800 + (s.brightness ?? 0.5) * 3000;
    const tk = (isBass ? 0.3 : 0.22) * (0.6 + (s.brightness ?? 0.5) * 0.8);  // relative to the normalized string (1.0)
    ng.gain.setValueAtTime(0.0001, t); ng.gain.exponentialRampToValueAtTime(tk, t + 0.001); ng.gain.exponentialRampToValueAtTime(0.0001, t + (isBass ? 0.03 : 0.015));
    s0.connect(nf); nf.connect(ng); ng.connect(input); s0.start(t, Math.random()); s0.stop(t + 0.05); extra.push(s0);
  }
  const peak = s.gain * vel, rel = Math.max(0.01, s.release), att = Math.max(0.001, s.attack), hold = Math.max(att, dur);
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(peak, t + att);
  let end = t + hold + rel + 0.05;
  if (s.engine === 'sample') {
    // ADSR: pick attack -> DECAY (seconds to fall to the sustain level) -> SUSTAIN (level kept while the note is
    // held, the recording loops so long notes keep ringing) -> RELEASE (fade after the note ends)
    const { decay, sus } = envOf(s);
    g.gain.setTargetAtTime(Math.max(0.0001, peak * sus), t + att, decay / 3);
    // Sustain 0% (palm mute): close the tail fast after Decay, like a noise gate, so an amp effect on the
    // track can't drag the dying tail out
    if (sus <= 0.001 && t + att + decay < t + hold) g.gain.setTargetAtTime(0.0001, t + att + decay, decay / 12);
    g.gain.setTargetAtTime(0.0001, t + hold, rel / 3);
    end = t + hold + rel * 2 + 0.05;
  } else if (s.pluck > 0) { g.gain.setTargetAtTime(0.0001, t + att, s.pluck / 3); g.gain.setTargetAtTime(0.0001, t + hold, rel / 4); }
  else { g.gain.setValueAtTime(peak, t + hold); g.gain.exponentialRampToValueAtTime(0.0001, t + hold + rel); }
  const intervals = s.chord === 'power' ? [0, 7, 12] : [0];
  const oscs = extra;
  if (s.engine === 'sample') {
    // real recording: re-pitch the nearest sample, tiny random tuning (+-3 cents) like a real player
    intervals.forEach((iv, k) => (s.detune ? [-s.detune, s.detune] : [0]).forEach(d => {
      const smp = nearestSample(s.sample, midi + iv); if (!smp) return;
      const src = c.createBufferSource(), sg = c.createGain();
      src.buffer = smp.buf; src.playbackRate.value = smp.rate; src.detune.value = d + (Math.random() * 6 - 3);
      src.loop = true; src.loopStart = smp.loopStart; src.loopEnd = smp.loopEnd;  // sustain loop: long notes keep ringing
      sg.gain.value = (intervals.length > 1 ? 0.6 : 1) * (s.detune ? 0.7 : 1) / Math.max(0.05, smp.peak);  // recordings normalized to 1.0
      src.connect(sg); sg.connect(input);
      src.start(t + k * (0.006 + Math.random() * 0.006), smp.off); src.stop(end); oscs.push(src);  // chord notes strummed a few ms apart
    }));
    return oscs;
  }
  if (isString) {
    // a real string vibrates in two planes with very slightly different pitch/decay -> subtle natural beating.
    // Each pluck uses random excitations, so repeated notes never sound copy-pasted.
    const planes = [[0, 0.78], [1.2 + Math.random() * 1.2, 0.3]];  // [cents, gain]
    intervals.forEach((iv, k) => (s.detune ? [-s.detune, s.detune] : [0]).forEach(d => planes.forEach(([pc, pg]) => {
      const v = Math.floor(Math.random() * STRING_VARIANTS);
      const { buf, rate } = stringBuffer(c, midiFreq(midi + iv), end - t, s, v);
      const src = c.createBufferSource(); src.buffer = buf; src.playbackRate.value = rate; src.detune.value = d + pc;
      const sg = c.createGain(); sg.gain.value = pg * (intervals.length > 1 ? 0.6 : 1) * (s.detune ? 0.7 : 1);
      src.connect(sg); sg.connect(input); src.start(t + k * (0.006 + Math.random() * 0.006)); src.stop(end); oscs.push(src);  // chord notes strummed a few ms apart
    })));
    return oscs;
  }
  intervals.forEach(iv => (s.detune ? [-s.detune, s.detune] : [0]).forEach(d => {
    const o = c.createOscillator(); o.type = s.wave; o.frequency.value = midiFreq(midi + iv); o.detune.value = d;
    o.connect(f); o.start(t); o.stop(end); oscs.push(o);
  }));
  return oscs;
}
function playClick(g, t, accent) {
  const c = g.c, o = c.createOscillator(), e = c.createGain();
  o.frequency.value = accent ? 1600 : 1000; env(c, e.gain, t, 0.8, 0.06);
  o.connect(e); e.connect(g.click); o.start(t); o.stop(t + 0.08);
  return [o];
}

/* schedule all events whose beat lies in [b0,b1) using segment mapping seg {t,b} */
function scheduleRange(g, b0, b1, seg, o = {}) {
  const S = spb(), tOf = b => seg.t + (b - seg.b) * S;
  const keep = arr => { if (o.sources) o.sources.push(...arr); };
  for (const t of P.tracks) {
    const tn = trackNodes(g, t);
    for (const clip of t.clips) {
      if (clip.kind === 'audio') {
        const buf = buffers.get(clip.buf); if (!buf) continue;
        const end = clip.start + clip.dur / S;
        let off = null, when = 0, dur = 0;
        if (clip.start >= b0 && clip.start < b1) { off = clip.offset; when = tOf(clip.start); dur = clip.dur; }
        else if (o.first && clip.start < b0 && end > b0) { const into = (b0 - clip.start) * S; off = clip.offset + into; when = tOf(b0); dur = clip.dur - into; }
        if (off !== null && dur > 0) {
          const src = g.c.createBufferSource(), cg = g.c.createGain(); src.buffer = buf; cg.gain.value = clip.gain ?? 1;
          src.connect(cg); cg.connect(tn.in); src.start(Math.max(when, g.c.currentTime), off, dur);
          if (o.stopAt) src.stop(o.stopAt);
          keep([src]);
        }
      } else {
        const h = isPatHolder(t, clip) ? clip : t;  // the region's own pattern (track template only as a fallback)
        const steps = patSteps(h); if (!steps) continue;
        const from = Math.max(b0, clip.start), to = Math.min(b1, clip.start + clip.len);
        if (to <= from) continue;
        for (let k = Math.ceil((from - clip.start) * 4 - 1e-9); clip.start + k / 4 < to - 1e-9; k++) {
          if (k >= steps) break;                                         // linear region: nothing repeats
          const beat = clip.start + k / 4, i = k, when = tOf(beat);
          if (t.type === 'drum') DRUMS.forEach((d, r) => {
            if (!h.pattern.grid[r][i]) return;
            // hi-hat choke: closing the hats (closed / pedal) cuts a ringing open hi-hat
            if ((d.id === 'chh' || d.id === 'phh') && tn.openHat) { tn.openHat.forEach(v => { try { v.stop(when + 0.01); } catch (e) { /* already ended */ } }); tn.openHat = null; }
            const v = playDrum(g.c, tn.in, d.id, when, 0.86 + Math.random() * 0.14, kitOf(t, d.id)); /* slight velocity variation = human feel */
            if (d.id === 'ohh') tn.openHat = v;
            keep(v);
          });
          else h.notes.forEach(n => { if (n.s === i) keep(playSynth(g.c, tn.in, t.synth, n.p, when, n.l * S / 4)); });
        }
      }
    }
  }
  if (o.click || o.clickBefore > b0) {
    for (let b = Math.ceil(b0 - 1e-9); b < b1; b++) if (o.click || b < o.clickBefore) keep(playClick(g, tOf(b), ((b % P.sig) + P.sig) % P.sig === 0));
  }
}

/* --------------------------------------------------------------- transport */
function currentBeat() {
  if (!T.playing) return T.pos;
  const now = ctx.currentTime; let seg = T.segs[0];
  for (const s of T.segs) if (s.t <= now) seg = s;
  return seg.b + (now - seg.t) / spb();
}
const loopActive = () => $('#loop').checked && !T.recording && P.loop.end > P.loop.start;
function startTransport(fromBeat, opts = {}) {
  ensureCtx(); syncGraph();
  const now = ctx.currentTime + 0.06;
  Object.assign(T, { playing: true, segs: [{ t: now, b: fromBeat }], cursor: fromBeat, first: true, sources: [],
    click: opts.record ? $('#metronome').checked : $('#metroPlay').checked, clickBefore: opts.clickBefore ?? -1e9 });
  tick(); T.timer = setInterval(tick, 25);
  $('#btnPlay').classList.add('on'); $('#btnPlay').textContent = '■';
}
function tick() {
  if (!T.playing) return;
  const S = spb(); let seg = T.segs[T.segs.length - 1];
  const horizon = ctx.currentTime + 0.2;
  let target = seg.b + (horizon - seg.t) / S;
  const opt = () => ({ first: T.first, click: T.click, clickBefore: T.clickBefore, sources: T.sources });
  if (loopActive() && T.cursor < P.loop.end && seg.b < P.loop.end) {
    const tEnd = seg.t + (P.loop.end - seg.b) * S;
    if (target >= P.loop.end) {
      scheduleRange(rt, T.cursor, P.loop.end, seg, { ...opt(), stopAt: tEnd });
      seg = { t: tEnd, b: P.loop.start }; T.segs.push(seg); if (T.segs.length > 4) T.segs.shift();
      T.cursor = P.loop.start; T.first = true;
      target = seg.b + (horizon - seg.t) / S;
      const tEnd2 = seg.t + (P.loop.end - seg.b) * S;
      scheduleRange(rt, T.cursor, Math.min(target, P.loop.end), seg, { ...opt(), stopAt: tEnd2 });
      T.cursor = Math.min(target, P.loop.end); T.first = false;
      return;
    }
    if (target > T.cursor) { scheduleRange(rt, T.cursor, target, seg, { ...opt(), stopAt: tEnd }); T.cursor = target; T.first = false; }
    return;
  }
  if (target > T.cursor) { scheduleRange(rt, T.cursor, target, seg, opt()); T.cursor = target; T.first = false; }
  if (!T.recording && currentBeat() > Math.max(songEndBeats(), 0) + 0.5 && !loopActive()) { stopTransport(); T.pos = 0; drawPlayhead(); $('#timelineWrap').scrollLeft = 0; }
  if (T.sources.length > 4000) T.sources = T.sources.slice(-2000);
}
function stopTransport() {
  if (!T.playing) return;
  const b = currentBeat();
  clearInterval(T.timer); T.timer = null;
  T.sources.forEach(s => { try { s.stop(); } catch (e) { /* already stopped */ } });
  T.sources = []; T.playing = false; T.pos = Math.max(0, b);
  if (T.recording) finishRecording();
  $('#btnPlay').classList.remove('on'); $('#btnPlay').textContent = '▶';
}
function togglePlay() {
  if (T.playing) { stopTransport(); return; }
  // song already finished (playhead at/after the last clip) -> start again from the beginning
  const end = songEndBeats();
  if (end > 0 && T.pos >= end - 0.01) T.pos = 0;
  startTransport(T.pos);
}
function seek(beat) {
  const was = T.playing; if (was) stopTransport();
  T.pos = Math.max(0, beat); if (was && !T.recording) startTransport(T.pos);
  drawPlayhead();
}

/* --------------------------------------------------------------- recording */
let recState = null;
async function startRecording() {
  if (T.recording) { stopTransport(); return; }
  ensureCtx();
  let t = P.tracks.find(x => x.arm && x.type === 'audio');
  if (!t) { const s = getTrack(selTrackId); t = s && s.type === 'audio' ? s : newTrack('audio'); t.arm = true; render(); }
  if (T.playing) stopTransport();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  } catch (e) { status('Microphone unavailable: ' + e.message); return; }
  const rec = new MediaRecorder(stream); const chunks = [];
  rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  const countBeats = $('#countIn').checked ? P.sig : 0, startBeat = T.pos;
  T.recording = true; $('#btnRecord').classList.add('on');
  rec.start(); const recStartCtx = ctx.currentTime;
  startTransport(startBeat - countBeats, { record: true, clickBefore: startBeat });
  const latency = (ctx.outputLatency || 0) + (ctx.baseLatency || 0);
  const skip = Math.max(0, T.segs[0].t + countBeats * spb() - recStartCtx + latency);
  recState = { rec, stream, chunks, track: t, startBeat, skip };
  status(countBeats ? 'Count-in… recording on ' + t.name : 'Recording on ' + t.name);
}
/* Punch-in replace: the new take overwrites whatever audio the track had in [b0, b1) (beats).
   Clips fully inside are deleted, clips sticking out are trimmed, a clip spanning the whole range is cut
   in two around it – so only the newest take is heard there. */
function punchReplace(track, b0, b1, keepBuf = null) {  // keepBuf = the new take's audio (not on a clip yet)
  const S = spb(), keep = [];
  for (const c of track.clips) {
    if (c.kind !== 'audio') { keep.push(c); continue; }
    const s = c.start, e = c.start + clipLenBeats(c);
    if (e <= b0 + 1e-6 || s >= b1 - 1e-6) { keep.push(c); continue; }            // no overlap
    if (s < b0) keep.push({ ...c, dur: (b0 - s) * S });                            // part before the take
    if (e > b1) keep.push({ ...c, id: s < b0 ? nid('c') : c.id, start: b1,         // part after the take
      offset: c.offset + (b1 - s) * S, dur: (e - b1) * S });
  }
  const changed = track.clips.length - keep.filter(c => track.clips.includes(c)).length;  // clips deleted or trimmed
  track.clips = keep;
  // free decoded audio no clip uses any more (saved projects only include used audio anyway)
  const used = new Set(); P.tracks.forEach(t => t.clips.forEach(c => c.kind === 'audio' && used.add(c.buf)));
  const cb = typeof clipboard !== 'undefined' && clipboard ? JSON.stringify(clipboard) : '';
  if (keepBuf) used.add(keepBuf);
  for (const id of [...buffers.keys()]) if (!used.has(id) && !cb.includes(id)) { buffers.delete(id); bufNames.delete(id); peaksCache.delete(id); }
  return changed;
}
function finishRecording() {
  const r = recState; recState = null; T.recording = false; $('#btnRecord').classList.remove('on');
  if (!r) return;
  r.rec.onstop = async () => {
    r.stream.getTracks().forEach(x => x.stop());
    try {
      const ab = await new Blob(r.chunks).arrayBuffer();
      const buf = await ctx.decodeAudioData(ab);
      const takeNo = 1 + Math.max(0, ...[...bufNames.values()].map(n => +(/^Take (\d+)$/.exec(n) || [0, 0])[1]));  // unique take numbers
      const id = nid('b'); buffers.set(id, buf); bufNames.set(id, 'Take ' + takeNo);
      const dur = buf.duration - r.skip;
      if (dur > 0.05) {
        const changed = punchReplace(r.track, r.startBeat, r.startBeat + dur / spb(), id);
        r.track.clips.push({ id: nid('c'), kind: 'audio', buf: id, start: r.startBeat, offset: r.skip, dur, gain: 1 });
        render(); status(changed ? `Recording replaced the old audio on ${r.track.name}` : 'Recording added to ' + r.track.name);
      } else { buffers.delete(id); bufNames.delete(id); render(); status('Recording too short – nothing changed'); }
    } catch (e) { status('Could not decode recording: ' + e.message); }
  };
  r.rec.stop();
}

/* ------------------------------------------------------------------ import */
async function importFiles(files, track = null, beat = null) {
  ensureCtx();
  for (const f of files) {
    try {
      status('Importing ' + f.name + '…');
      const buf = await ctx.decodeAudioData(await f.arrayBuffer());
      const id = nid('b'); buffers.set(id, buf); bufNames.set(id, f.name);
      let t = track && track.type === 'audio' ? track : null;
      if (!t) { t = newTrack('audio'); t.name = f.name.replace(/\.[^.]+$/, '').slice(0, 24); }
      t.clips.push({ id: nid('c'), kind: 'audio', buf: id, start: beat ?? T.pos, offset: 0, dur: buf.duration, gain: 1 });
      track = null; status('Imported ' + f.name);
    } catch (e) { status('Cannot import ' + f.name + ': ' + e.message); }
  }
  render();
}

/* ------------------------------------------------------------------ render */
function render() { ensureRegions(); renderArrange(); renderMixer(); renderEditor(); renderFx(); renderMaster(); }

function timelineBeats() { return Math.max(64, Math.ceil((songEndBeats() + P.sig * 8) / P.sig) * P.sig); }

function renderArrange() {
  const hdr = $('#trackHeaders'), lanes = $('#lanes'); hdr.innerHTML = ''; lanes.innerHTML = '';
  const W = timelineBeats() * pxB(), barPx = pxB() * P.sig;
  $('#timeline').style.width = W + 'px';
  const ruler = $('#ruler'); ruler.innerHTML = ''; ruler.style.width = W + 'px';
  const every = barPx < 30 ? 4 : barPx < 60 ? 2 : 1;
  for (let bar = 0; bar * P.sig < timelineBeats(); bar += every) ruler.append(el('span', { style: { left: bar * barPx + 'px' } }, String(bar + 1)));
  P.tracks.forEach(t => {
    const sel = t.id === selTrackId;
    const titles = { mute: 'Mute this track (silence)', solo: 'Solo: hear only soloed tracks', arm: 'Arm for recording' };
    const btn = (txt, key, cls = '') => el('button', { className: cls + (t[key] ? ' on' : ''), title: titles[key], onclick: e => { e.stopPropagation(); t[key] = !t[key]; if (key === 'arm' && t.arm) P.tracks.forEach(x => { if (x !== t) x.arm = false; }); syncGraph(); render(); } }, txt);
    const stop = e => e.stopPropagation();
    const volOut = el('span', { className: 'val' }, fmtDb(t.vol) + ' dB');
    const panOut = el('span', { className: 'val', 'data-pan': t.id }, panLabel(t.pan));
    const panIn = el('input', { type: 'range', className: 'pan', 'data-pan': t.id, min: -100, max: 100, step: 1, value: Math.round(t.pan * 100), title: 'Pan: drag left/right · double-click = center',
      oninput: e => setPan(t, +e.target.value / 100, panOut), ondblclick: e => { e.target.value = 0; setPan(t, 0, panOut); }, onclick: stop, onpointerdown: stop });
    const quick = (txt, v) => el('button', { className: 'pq', title: v === 0 ? 'Center' : (v < 0 ? 'Hard left' : 'Hard right'), onclick: e => { stop(e); panIn.value = v * 100; setPan(t, v, panOut); } }, txt);
    hdr.append(el('div', { className: 'thead' + (sel ? ' sel' : '') + (t.mute ? ' muted' : ''), style: { '--c': t.color }, onclick: () => { lastFocus = 'track'; selClipId = null; document.querySelectorAll('.clip.sel').forEach(c => c.classList.remove('sel')); selectTrack(t.id); } },
      el('div', { className: 'row' },
        el('input', { className: 'name', value: t.name, onchange: e => { t.name = e.target.value; renderMixer(); }, onclick: stop }),
        btn(t.mute ? '🔇' : '🔊', 'mute', 'mute'), btn('S', 'solo'), t.type === 'audio' ? btn('●', 'arm', 'arm') : null,
        el('button', { title: 'Delete track', onclick: e => { stop(e); deleteTrack(t.id); } }, '✕')),
      el('div', { className: 'row' }, el('span', { className: 'kind' }, t.type === 'drum' ? 'Drum machine' : t.type === 'synth' ? (t.instrument === 'guitar' ? 'Guitar / MIDI' : t.instrument === 'bass' ? 'Bass / MIDI' : 'Synth / MIDI') : 'Audio')),
      el('div', { className: 'row ctl' }, el('span', { className: 'lab' }, 'Vol'),
        el('input', { type: 'range', min: 0, max: 1.5, step: 0.01, value: t.vol, title: 'Volume',
          oninput: e => { t.vol = +e.target.value; volOut.textContent = fmtDb(t.vol) + ' dB'; syncGraph(); renderMixer(); }, onclick: stop, onpointerdown: stop }), volOut),
      el('div', { className: 'row ctl' }, quick('L', -1), panIn, quick('R', 1), panOut)));
    const lane = el('div', { className: 'lane' + (sel ? ' sel' : '') + (t.mute ? ' muted' : ''), style: { backgroundSize: barPx + 'px 100%' } });
    lane.dataset.track = t.id;
    lane.addEventListener('pointerdown', e => { if (e.target === lane) { lastFocus = 'track'; selectTrack(t.id); selClipId = null; document.querySelectorAll('.clip.sel').forEach(c => c.classList.remove('sel')); } });
    lane.addEventListener('dblclick', e => {
      if (e.target !== lane || t.type === 'audio') return;
      const beat = Math.floor(xToBeat(e, lane) / P.sig) * P.sig;
      const c = newEmptyRegion(t, beat); selClipId = c.id; lastFocus = 'clip'; render(); showTab('editor');  // empty bar
    });
    lane.addEventListener('contextmenu', e => { if (e.target !== lane) return; e.preventDefault(); laneMenu(e, t, lane); });
    lane.addEventListener('dragover', e => e.preventDefault());
    lane.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); hideDrop(); if (e.dataTransfer.files.length) importFiles([...e.dataTransfer.files], t, snapBeat(xToBeat(e, lane))); });
    t.clips.forEach(c => lane.append(clipEl(t, c)));
    lanes.append(lane);
  });
  drawLoop(); drawPlayhead();
}
/* pan: -1 = hard left, 0 = center, +1 = hard right */
function panLabel(v) {
  const n = Math.round(Math.abs(v) * 100);
  if (n === 0) return 'C';
  return (v < 0 ? 'L ' : 'R ') + n + (n === 100 ? ' max' : '');
}
function setPan(t, v, outEl) {
  t.pan = clamp(Math.round(v * 100) / 100, -1, 1);
  if (outEl) outEl.textContent = panLabel(t.pan);
  syncGraph();
  // keep the other pan controls (header <-> mixer) in sync without a full re-render
  document.querySelectorAll(`[data-pan="${t.id}"]`).forEach(x => { if (x.tagName === 'INPUT') x.value = Math.round(t.pan * 100); else x.textContent = panLabel(t.pan); });
}
function xToBeat(e, ref) { return Math.max(0, (e.clientX - ref.getBoundingClientRect().left) / pxB()); }
function snapBeat(b, grid = 1) { return $('#snap').checked ? Math.round(b / grid) * grid : b; }

function clipEl(t, c) {
  const w = Math.max(4, clipLenBeats(c) * pxB());
  const name = c.kind === 'audio' ? (bufNames.get(c.buf) || 'Audio') : (t.type === 'drum' ? 'Drum pattern' : 'MIDI');
  const d = el('div', { className: 'clip' + (c.id === selClipId ? ' sel' : ''), style: { left: c.start * pxB() + 'px', width: w + 'px', '--c': t.color } });
  const cv = el('canvas'); cv.height = 60; sizeClipCanvas(cv, w); d.append(cv, el('div', { className: 'lbl' }, name), el('div', { className: 'rs', title: 'Resize' }));
  requestAnimationFrame(() => drawClip(cv, t, c));
  d.addEventListener('pointerdown', e => clipMouseDown(e, t, c, d));
  d.addEventListener('dblclick', () => { if (c.kind === 'midi') { selectTrack(t.id); showTab('editor'); } });
  d.addEventListener('contextmenu', e => { e.preventDefault(); e.stopPropagation(); clipMenu(e, t, c); });
  return d;
}
function getPeaks(id) {
  if (peaksCache.has(id)) return peaksCache.get(id);
  const b = buffers.get(id); const per = Math.floor(b.sampleRate / 200); const n = Math.ceil(b.length / per);
  const pk = new Float32Array(n); const chs = [...Array(b.numberOfChannels).keys()].map(i => b.getChannelData(i));
  for (let i = 0; i < n; i++) { let m = 0; for (const ch of chs) for (let j = i * per, e = Math.min(b.length, j + per); j < e; j += 4) { const v = Math.abs(ch[j]); if (v > m) m = v; } pk[i] = m; }
  peaksCache.set(id, pk); return pk;
}
// canvas pixel size follows the clip's on-screen width (never CSS-stretched), so pads keep their
// position/size while the clip edge is dragged
function sizeClipCanvas(cv, w) {
  cv.width = Math.max(1, Math.min(Math.ceil(w), 8000)); cv.style.width = w + 'px'; cv._scale = cv.width / w;
}
function drawClip(cv, t, c) {
  const g = cv.getContext('2d'), W = cv.width, H = cv.height; g.clearRect(0, 0, W, H); g.fillStyle = t.color;
  if (c.kind === 'audio') {
    if (!buffers.has(c.buf)) return;
    const pk = getPeaks(c.buf), p0 = c.offset * 200, pn = c.dur * 200;
    for (let x = 0; x < W; x++) { const i = Math.floor(p0 + (x / W) * pn); const v = (pk[i] || 0) * (H / 2 - 8); g.fillRect(x, H / 2 + 4 - v, 1, Math.max(1, v * 2)); }
  } else {
    const h = isPatHolder(t, c) ? c : t, cols = Math.round(c.len * 4), cw = pxB() / 4 * (cv._scale || 1);
    if (t.type === 'drum') { const rh = (H - 16) / DRUMS.length; for (let k = 0; k < cols; k++) DRUMS.forEach((_, r) => { if (h.pattern.grid[r] && h.pattern.grid[r][k]) g.fillRect(k * cw, 16 + r * rh, Math.max(1, cw - 1), rh - 1); }); }
    else { const rh = (H - 16) / (HIGH_NOTE - LOW_NOTE + 1); h.notes.forEach(n => { if (n.s < cols) g.fillRect(n.s * cw, 16 + (HIGH_NOTE - n.p) * rh, Math.max(1, n.l * cw - 1), Math.max(2, rh)); }); }
    // bar lines inside the region
    g.fillStyle = 'rgba(255,255,255,.18)'; for (let k = stepsPerBar(); k < cols; k += stepsPerBar()) g.fillRect(k * cw, 0, 1, H);
  }
}
function clipMouseDown(e, t, c, d) {
  e.stopPropagation(); if (e.button !== 0) return;
  const prevSel = selClipId;
  selClipId = c.id; lastFocus = 'clip'; selectTrack(t.id, false);
  document.querySelectorAll('.clip.sel').forEach(x => x.classList.remove('sel')); d.classList.add('sel');
  if (c.kind === 'midi' && prevSel !== c.id) renderEditor();  // the editor follows the clicked region
  const resize = e.target.classList.contains('rs'), x0 = e.clientX, y0 = e.clientY, s0 = c.start, l0 = clipLenBeats(c);
  let target = t, moved = false;
  const mm = ev => {
    moved = true; const db = (ev.clientX - x0) / pxB();
    if (resize) {
      let nl = Math.max(0.25, $('#snap').checked ? Math.round((s0 + l0 + db) * 4) / 4 - s0 : l0 + db);
      if (c.kind === 'audio') { const max = buffers.get(c.buf).duration - c.offset; c.dur = clamp(nl * spb(), 0.05, max); d.style.width = c.dur / spb() * pxB() + 'px'; }
      else { c.len = Math.max(0.25, nl); d.style.width = c.len * pxB() + 'px'; }
      // redraw at the new size instead of stretching: filled pads stay where they are
      const cv = d.querySelector('canvas'); if (cv) { sizeClipCanvas(cv, Math.max(4, clipLenBeats(c) * pxB())); drawClip(cv, t, c); }
    } else {
      c.start = Math.max(0, snapBeat(s0 + db, $('#snap').checked ? (c.kind === 'midi' ? 1 : 0.25) : 1)); d.style.left = c.start * pxB() + 'px';
      const laneEl = document.elementsFromPoint(ev.clientX, ev.clientY).find(x => x.classList && x.classList.contains('lane'));
      const nt = laneEl && getTrack(laneEl.dataset.track);
      if (nt && nt !== target && nt.type === t.type) { target = nt; laneEl.append(d); d.style.setProperty('--c', nt.color); }
    }
    void y0;
  };
  const mu = () => {
    window.removeEventListener('pointermove', mm); window.removeEventListener('pointerup', mu); window.removeEventListener('pointercancel', mu);
    if (target !== t) { t.clips = t.clips.filter(x => x !== c); target.clips.push(c); selectTrack(target.id, false); }
    if (resize && c.kind === 'midi') { c.len = Math.max(0.25, Math.round(c.len * 4) / 4); fitRegion(target, c); }
    if (moved) render();
  };
  window.addEventListener('pointermove', mm); window.addEventListener('pointerup', mu); window.addEventListener('pointercancel', mu);
}
function selectTrack(id, rerender = true) {
  if (selTrackId === id) return;
  selTrackId = id;
  document.querySelectorAll('.thead').forEach((h, i) => h.classList.toggle('sel', P.tracks[i] && P.tracks[i].id === id));
  document.querySelectorAll('.lane').forEach(l => l.classList.toggle('sel', l.dataset.track === id));
  renderEditor(); renderFx(); void rerender;
}
function deleteTrack(id) {
  P.tracks = P.tracks.filter(t => t.id !== id); if (selTrackId === id) selTrackId = null; syncGraph(); render();
}
function drawPlayhead() {
  const b = currentBeat(); $('#playhead').style.left = Math.max(0, b) * pxB() + 'px';
  highlightStep();
  const bb = Math.max(0, b), bar = Math.floor(bb / P.sig) + 1, beat = Math.floor(bb % P.sig) + 1, six = Math.floor((bb % 1) * 4) + 1;
  const sec = Math.max(0, b) * spb(), m = Math.floor(sec / 60), s = (sec % 60).toFixed(3).padStart(6, '0');
  $('#timeDisplay').textContent = (b < 0 ? 'COUNT ' + Math.ceil(-b) : `${bar}.${beat}.${six}`) + ` | ${String(m).padStart(2, '0')}:${s}`;
}
function drawLoop() {
  const r = $('#loopRegion'); r.style.display = $('#loop').checked ? 'block' : 'none';
  r.style.left = P.loop.start * pxB() + 'px'; r.style.width = (P.loop.end - P.loop.start) * pxB() + 'px';
}

/* ------------------------------------------------------------------- mixer */
function slider(label, min, max, step, val, fmt, on) {
  const out = el('span', {}, fmt(val));
  return el('label', {}, label, el('input', { type: 'range', min, max, step, value: val, oninput: e => { const v = +e.target.value; out.textContent = fmt(v); on(v); } }), out);
}
function panControl(t) {
  const out = el('span', { className: 'val', 'data-pan': t.id }, panLabel(t.pan));
  return el('div', { className: 'panbox' },
    el('div', { className: 'panhd' }, el('span', {}, 'L'), el('span', {}, 'Pan'), el('span', {}, 'R')),
    el('input', { type: 'range', className: 'pan', 'data-pan': t.id, min: -100, max: 100, step: 1, value: Math.round(t.pan * 100),
      title: 'Drag left/right · double-click = center', oninput: e => setPan(t, +e.target.value / 100, out), ondblclick: e => { e.target.value = 0; setPan(t, 0, out); } }),
    out);
}
function renderMixer() {
  const m = $('#mixer'); m.innerHTML = '';
  P.tracks.forEach(t => {
    const set = fn => v => { fn(v); syncGraph(); };
    m.append(el('div', { className: 'strip' + (t.mute ? ' muted' : ''), style: { '--c': t.color } },
      el('div', { className: 't', title: t.name }, t.name),
      el('div', { className: 'meter' }, el('div', { id: 'meter-' + t.id })),
      slider('Vol', 0, 1.5, 0.01, t.vol, fmtDb, set(v => { t.vol = v; })),
      panControl(t),
      el('div', { className: 'btns' },
        el('button', { className: 'mute' + (t.mute ? ' on' : ''), title: 'Mute this track', onclick: () => { t.mute = !t.mute; syncGraph(); render(); } }, t.mute ? '🔇 Muted' : '🔊 Mute'),
        el('button', { className: t.solo ? 'on' : '', onclick: () => { t.solo = !t.solo; syncGraph(); render(); } }, 'Solo')),
      el('div', { className: 'fx' }, 'EQ'),
      slider('Low', -15, 15, 0.5, t.eq.low, v => v.toFixed(1), set(v => { t.eq.low = v; })),
      slider('Mid', -15, 15, 0.5, t.eq.mid, v => v.toFixed(1), set(v => { t.eq.mid = v; })),
      slider('High', -15, 15, 0.5, t.eq.high, v => v.toFixed(1), set(v => { t.eq.high = v; })),
      el('div', { className: 'fx' }, 'Compressor'),
      slider('Thr', -60, 0, 1, t.comp.thr, v => v + '', set(v => { t.comp.thr = v; })),
      slider('Ratio', 1, 20, 0.5, t.comp.ratio, v => v + ':1', set(v => { t.comp.ratio = v; })),
      el('div', { className: 'fx' }, 'Sends'),
      slider('Reverb', 0, 1, 0.01, t.rev, v => Math.round(v * 100) + '', set(v => { t.rev = v; })),
      slider('Delay', 0, 1, 0.01, t.dly, v => Math.round(v * 100) + '', set(v => { t.dly = v; })),
      el('div', { className: 'fx' }, 'Insert FX'),
      el('div', { className: 'fxlist', title: 'Insert effects' }, (t.fx || []).filter(f => f.on).map(f => FX_TYPES[f.type].name).join(' › ') || '—'),
      el('button', { onclick: () => { selectTrack(t.id); renderFx(); showTab('fx'); } }, 'FX…')));
  });
  m.append(el('div', { className: 'strip mst' }, el('div', { className: 't' }, 'MASTER'),
    el('div', { className: 'meter' }, el('div', { id: 'meter-master' })), el('div', { id: 'peak-master' }, '-∞ dB'),
    slider('Vol', 0, 1.5, 0.01, P.master.vol, fmtDb, v => { P.master.vol = v; syncGraph(); }),
    el('button', { onclick: () => showTab('master') }, 'Mastering →')));
}

/* ------------------------------------------------------------ context menus */
function closeCtxMenu() { const m = document.getElementById('ctxmenu'); if (m) m.remove(); }
// items: { label, run, disabled } or '-' for a separator
function showCtxMenu(x, y, title, items) {
  closeCtxMenu();
  const m = el('div', { id: 'ctxmenu', className: 'ctxmenu', role: 'menu', oncontextmenu: e => e.preventDefault() }, el('div', { className: 'ctxtitle' }, title),
    items.filter(Boolean).map(it => it === '-' ? el('div', { className: 'ctxsep' })
      : el('button', { role: 'menuitem', disabled: !!it.disabled, onclick: () => { closeCtxMenu(); it.run(); } }, it.label)));
  document.body.append(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 4)) + 'px';
  m.style.top = Math.max(4, Math.min(y, innerHeight - r.height - 4)) + 'px';
}
document.addEventListener('pointerdown', e => { if (!e.target.closest || !e.target.closest('#ctxmenu')) closeCtxMenu(); }, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeCtxMenu(); });
window.addEventListener('blur', closeCtxMenu);
const clipFits = (t, cb) => cb && cb.kind === 'clip' && cb.data.trackType === t.type;
function pasteAt(t, beat) { selTrackId = t.id; T.pos = beat; pasteClipboard(); }
function pickAudioFile(t, beat) {
  const inp = el('input', { type: 'file', accept: 'audio/*,video/*', multiple: true, style: { display: 'none' } });
  inp.onchange = () => { if (inp.files.length) importFiles([...inp.files], t, beat); inp.remove(); };
  document.body.append(inp); inp.click();
}
// right-click on an empty spot of a lane: MIDI tracks add bars, audio tracks add audio
function laneMenu(e, t, lane) {
  const beat = Math.floor(xToBeat(e, lane) / P.sig) * P.sig, bar = beat / P.sig + 1;
  selectTrack(t.id); lastFocus = 'track';
  const sel = t.clips.find(c => c.id === selClipId && c.kind === 'midi');
  const add = (bars) => () => { const c = newEmptyRegion(t, beat, bars); selClipId = c.id; lastFocus = 'clip'; render(); showTab('editor'); };
  if (t.type === 'audio') {
    showCtxMenu(e.clientX, e.clientY, `${t.name} · bar ${bar}`, [
      { label: '🎵 Add audio here (import file)…', run: () => pickAudioFile(t, beat) },
      { label: '● Record here', run: () => { P.tracks.forEach(x => { x.arm = x === t; }); seek(beat); startRecording(); } },
      { label: '📋 Paste here', disabled: !clipFits(t, clipboard), run: () => pasteAt(t, beat) },
    ]);
    return;
  }
  showCtxMenu(e.clientX, e.clientY, `${t.name} · bar ${bar}`, [
    { label: '➕ Add empty bar here', run: add(1) },
    { label: '➕ Add 2 empty bars here', run: add(2) },
    { label: '➕ Add 4 empty bars here', run: add(4) },
    { label: '⧉ Add copy of the selected region here', disabled: !sel, run: () => { const c = newRegion(t, beat, sel); selClipId = c.id; lastFocus = 'clip'; render(); } },
    '-',
    { label: '📋 Paste here', disabled: !clipFits(t, clipboard), run: () => pasteAt(t, beat) },
  ]);
}
// right-click on a clip / region
function clipMenu(e, t, c) {
  selClipId = c.id; lastFocus = 'clip'; selectTrack(t.id, false);
  document.querySelectorAll('.clip.sel').forEach(x => x.classList.remove('sel'));
  if (e.currentTarget && e.currentTarget.classList) e.currentTarget.classList.add('sel');
  if (c.kind === 'midi') renderEditor();
  const inside = currentBeat() > c.start && currentBeat() < c.start + clipLenBeats(c);
  const remove = () => { t.clips = t.clips.filter(x => x !== c); selClipId = null; render(); };
  const items = c.kind === 'midi' ? [
    { label: '✎ Edit pads / notes', run: () => { showTab('editor'); renderEditor(); } },
    { label: '➕ Extend by 1 empty bar', run: () => { c.len += P.sig; fitRegion(t, c); render(); } },
    { label: '➖ Shorten by 1 bar', disabled: c.len <= P.sig, run: () => { c.len = Math.max(P.sig, c.len - P.sig); fitRegion(t, c); render(); } },
    { label: '⧉ Duplicate (Ctrl/Cmd+D)', run: duplicateClip },
    { label: '✂ Split at playhead (S)', disabled: !inside, run: splitClip },
    '-', { label: '🗑 Delete region', run: remove },
  ] : [
    { label: '⧉ Duplicate (Ctrl/Cmd+D)', run: duplicateClip },
    { label: '✂ Split at playhead (S)', disabled: !inside, run: splitClip },
    '-', { label: '🗑 Delete clip', run: remove },
  ];
  showCtxMenu(e.clientX, e.clientY, c.kind === 'midi' ? `Region · bar ${Math.floor(c.start / P.sig) + 1} · ${+(c.len / P.sig).toFixed(2)} bar(s)` : (bufNames.get(c.buf) || 'Audio clip'), items);
}

/* ------------------------------------------------------------------ editor */
let paintVal = null, noteLen = 1;
function renderEditor() {
  const ed = $('#editor'); ed.innerHTML = '';
  const t = getTrack(selTrackId);
  if (!t || t.type === 'audio') {
    ed.append(el('p', { className: 'hint' }, t ? `“${t.name}” is an audio track: import or record audio, drag clips to position them, drag the right edge to trim, S = split at playhead, Ctrl/Cmd+D = duplicate, Delete = remove.` : 'Select a Drum or Synth track to edit its pattern. Double-click an empty spot in its lane to add a pattern region.'));
    return;
  }
  const h = edHolder(t);  // the region being edited (each region has its own pattern)
  const steps = patSteps(h), spbar = stepsPerBar();
  // region length in bars: longer = new EMPTY bars at the end, shorter = the end is cut (nothing loops)
  const curBars = patBars(h), barOpts = [...new Set([1, 2, 3, 4, 6, 8, 12, 16, curBars])].sort((x, y) => x - y);
  const barsSel = el('select', { title: 'Region length – extending adds empty bars, nothing repeats', onchange: e => {
    const b = +e.target.value;
    if (h.kind === 'midi') { h.len = b * P.sig; fitRegion(t, h); }
    else if (t.type === 'drum') { h.pattern.bars = b; resizeGrid(h); } else { h.bars = b; h.notes = h.notes.filter(n => n.s < patSteps(h)); }
    render(); } },
    barOpts.map(b => el('option', { value: b, selected: Math.abs(b - curBars) < 1e-9 }, (Number.isInteger(b) ? b : b.toFixed(2)) + ' bar' + (b === 1 ? '' : 's'))));
  // region navigator: which region is being edited, step through the regions of this track
  const regs = midiRegions(t), ri = regs.indexOf(h);
  const goRegion = d => { const c = regs[(ri + d + regs.length) % regs.length]; if (!c) return; selClipId = c.id; lastFocus = 'clip'; render(); };
  const regionInfo = ri >= 0
    ? el('span', { className: 'reginfo', title: 'Each region has its own pattern – edits here change only this region' }, `Region ${ri + 1}/${regs.length} · bar ${Math.floor(h.start / P.sig) + 1}`)
    : el('span', { className: 'reginfo' }, 'No region yet – “+ Add region” or double-click the lane');
  const tools = el('div', { className: 'edtools' }, el('b', {}, t.name),
    el('button', { title: 'Previous region', disabled: regs.length < 2, onclick: () => goRegion(-1) }, '◀'), regionInfo,
    el('button', { title: 'Next region', disabled: regs.length < 2, onclick: () => goRegion(1) }, '▶'),
    'Length', barsSel,
    el('button', { title: 'Add an empty 1-bar region after the last one', onclick: () => {
      const c = newEmptyRegion(t, nextFreeBar(t)); selClipId = c.id; lastFocus = 'clip'; render(); } }, '+ Empty bar'),
    el('button', { title: 'Copy this region (independent copy) right after the last region', disabled: h.kind !== 'midi', onclick: () => {
      const c = newRegion(t, nextFreeBar(t), h); selClipId = c.id; lastFocus = 'clip'; render(); } }, '⧉ Duplicate region'),
    el('button', { title: 'Copy this pattern into every region of this track', disabled: regs.length < 2 || ri < 0, onclick: () => {
      regs.forEach(c => { if (c !== h) { Object.assign(c, regionData(t, h)); c.linear = true; fitRegion(t, c); } }); render(); status(`Copied this pattern to all ${regs.length} regions of ${t.name}`); } }, 'Apply to all regions'));
  ed.append(tools);
  const grid = el('div', { className: 'grid ' + (t.type === 'drum' ? 'drumgrid' : 'rollgrid'), style: { gridTemplateColumns: `${t.type === 'drum' ? 200 : 64}px repeat(${steps}, 28px)` } });
  // step ruler: beat numbers above the grid
  grid.append(el('div', { className: 'gcorner' }, t.type === 'drum' ? 'Part · tuning' : 'Note'));
  const bar0 = h.kind === 'midi' ? Math.floor(h.start / P.sig) : 0;
  for (let i = 0; i < steps; i++) {
    const barStart = i % spbar === 0;
    grid.append(el('div', { className: 'ghead' + (i % 4 === 0 ? ' beat' : '') + (barStart ? ' bar' : ''), title: barStart ? `Bar ${bar0 + i / spbar + 1}` : '' },
      barStart ? 'B' + (bar0 + i / spbar + 1) : i % 4 === 0 ? String(Math.floor(i / 4) % P.sig + 1) : '·'));
  }
  const up = () => { paintVal = null; window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up); renderArrange(); };
  grid.addEventListener('pointermove', e => { if (paintVal === null) return; const x = document.elementFromPoint(e.clientX, e.clientY); if (x && x._apply) x._apply(); });
  if (t.type === 'drum') {
    tools.append('Preset', el('select', { onchange: e => { applyDrumPreset(h, e.target.value); render(); } }, el('option', {}, '— choose —'), Object.keys(DRUM_PRESETS).map(k => el('option', {}, k))));
    DRUMS.forEach((d, r) => {
      const kit = kitOf(t, d.id);
      const preview = () => { ensureCtx(); playDrum(ctx, trackNodes(rt, t).in, d.id, ctx.currentTime + 0.01, 1, kitOf(t, d.id)); };
      // toUi / fromUi map the stored value to the slider scale (identity, or dB for the volume fader)
      const knob = (label, key, min, max, step, fmt, toUi = v => v, fromUi = v => v) => {
        const out = el('span', { className: 'kval' }, fmt(kit[key]));
        return el('label', { className: 'kctl', title: label + ' (double-click = reset)' }, el('span', { className: 'klab' }, label),
          el('input', { type: 'range', min, max, step, value: toUi(kit[key]),
            oninput: e => { kit[key] = fromUi(+e.target.value); out.textContent = fmt(kit[key]); },
            onchange: preview,
            ondblclick: e => { kit[key] = KIT_DEFAULT[key]; e.target.value = toUi(kit[key]); out.textContent = fmt(kit[key]); preview(); } }), out);
      };
      const isSel = selPart && selPart.trackId === t.id && selPart.row === r;
      const lbl = el('div', { className: 'drumlbl' + (isSel ? ' sel' : ''), onpointerdown: () => { selPart = { trackId: t.id, row: r }; lastFocus = 'part'; document.querySelectorAll('.drumlbl.sel').forEach(x => x.classList.remove('sel')); lbl.classList.add('sel'); } },
        el('div', { className: 'dl-top' },
          el('button', { className: 'dl-play', title: 'Preview', onclick: preview }, '▶'),
          el('span', { className: 'dl-name', title: d.name }, d.name),
          el('button', { className: 'dl-mini', title: 'Copy part (pattern + tuning) · Ctrl/Cmd+C', onclick: () => { selPart = { trackId: t.id, row: r }; lastFocus = 'part'; copySelection(); } }, '⧉'),
          el('button', { className: 'dl-mini', title: 'Paste part here · Ctrl/Cmd+V', onclick: () => { selPart = { trackId: t.id, row: r }; lastFocus = 'part'; pasteClipboard(); } }, '📋')),
        // everything in percent (100% = default): Tune = pitch of the drum (25%..400% = -2..+2 octaves),
        // Decay = length of the ring (10%..400%), Volume = loudness of the part (off..200%)
        knob('Tune', 'pitch', KIT_RANGES.pitch[0], KIT_RANGES.pitch[1], 0.5, fmtTunePct),
        knob('Decay', 'decay', KIT_RANGES.decay[0], KIT_RANGES.decay[1], 0.05, v => Math.round(v * 100) + '%'),
        knob('Volume', 'level', KIT_RANGES.level[0], KIT_RANGES.level[1], 0.01, v => v <= 0 ? 'off' : Math.round(v * 100) + '%'));
      grid.append(lbl);
      for (let i = 0; i < steps; i++) {
        const cell = el('div', { className: 'cell' + (Math.floor(i / 4) % 2 ? '' : ' beat') + (i % 4 === 0 ? ' bstart' : '') + (i && i % spbar === 0 ? ' barline' : '') + (h.pattern.grid[r][i] ? ' on' : '') });
        cell.dataset.col = i;
        const apply = () => { h.pattern.grid[r][i] = paintVal; cell.classList.toggle('on', !!paintVal); };
        cell._apply = apply;
        cell.addEventListener('pointerdown', e => { e.preventDefault(); if (cell.hasPointerCapture && cell.hasPointerCapture(e.pointerId)) cell.releasePointerCapture(e.pointerId); paintVal = h.pattern.grid[r][i] ? 0 : 1; apply(); if (paintVal) preview(); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up); });
        grid.append(cell);
      }
    });
  } else {
    const s = t.synth;
    const setS = (k, v) => { s[k] = v; };
    // envelope preview: a note held for one bar, then released (Attack · Decay · Sustain · Release)
    const envCanvas = el('canvas', { className: 'envgraph', width: 220, height: 54, title: 'Envelope of a note held for 1 bar: pluck → decay → sustain → release' });
    const drawEnv = () => {
      const g = envCanvas.getContext('2d'), W = envCanvas.width, H = envCanvas.height, { decay, sus } = envOf(s);
      const hold = P.sig * spb(), rel = Math.max(0.01, s.release), total = hold + rel * 2, X = tt => 4 + (tt / total) * (W - 8), Y = v => H - 6 - v * (H - 14);
      g.clearRect(0, 0, W, H); g.strokeStyle = 'rgba(255,255,255,.15)'; g.beginPath(); g.moveTo(X(hold), 0); g.lineTo(X(hold), H); g.stroke();
      g.strokeStyle = '#00e5ff'; g.lineWidth = 2; g.beginPath(); g.moveTo(X(0), Y(0));
      let v = 1;
      for (let i = 0; i <= 160; i++) {
        const tt = total * i / 160;
        v = tt <= hold ? sus + (1 - sus) * Math.exp(-3 * tt / decay) : (sus + (1 - sus) * Math.exp(-3 * hold / decay)) * Math.exp(-3 * (tt - hold) / rel);
        g.lineTo(X(tt), Y(v));
      }
      g.stroke(); g.fillStyle = '#fff'; g.font = '9px ui-monospace,Menlo,monospace';
      g.fillText('1 bar held', X(hold) - 52, 10); g.fillText('release', X(hold) + 3, 10);
    };
    requestAnimationFrame(drawEnv);
    tools.append('Sound', el('select', { onchange: e => { applySynthPreset(t, e.target.value); syncGraph(); renderEditor(); renderFx(); renderMixer(); } }, Object.keys(SYNTH_PRESETS).map(k => el('option', { selected: k === s.preset }, k))),
      'Engine', el('select', { title: 'Real instrument = recorded guitar/bass, Modeled string = simulated plucked string, Synth = oscillators', onchange: e => { setS('engine', e.target.value); if (e.target.value === 'sample') loadSampleSet(s.sample || 'electric_guitar_clean'); renderEditor(); } },
        [['sample', 'Real instrument'], ['string', 'Modeled string'], ['osc', 'Synth']].map(([v, l]) => el('option', { value: v, selected: v === (s.engine || 'osc') }, l))),
      ...(s.engine === 'sample' ? [
        el('select', { title: 'Recorded instrument', onchange: e => { setS('sample', e.target.value); loadSampleSet(e.target.value); } },
          Object.entries(SAMPLE_SETS).map(([v, o]) => el('option', { value: v, selected: v === s.sample }, o.name))),
        // note envelope of a held note: Decay = how long the pluck takes to fall to the Sustain level,
        // Sustain = level kept while the note is held (0% = dies away like palm mute), Release = fade after note end
        el('span', { title: 'Decay: time for the pluck to fall to the sustain level' }, slider('Decay', 0.03, 10, 0.01, envOf(s).decay, v => v.toFixed(2) + ' s', v => { setS('decay', v); drawEnv(); })),
        el('span', { title: 'Sustain: level the note keeps while it is held (long notes keep ringing)' }, slider('Sustain', 0, 1, 0.01, envOf(s).sus, v => Math.round(v * 100) + '%', v => { setS('susLevel', v); drawEnv(); })),
        envCanvas,
      ] : s.engine === 'string' ? [
        slider('Brightness', 0.05, 1, 0.01, s.brightness ?? 0.5, v => Math.round(v * 100) + '%', v => setS('brightness', v)),
        slider('Sustain', 0, 1, 0.01, s.sustain ?? 0.5, v => Math.round(v * 100) + '%', v => setS('sustain', v)),
        slider('Body', 0, 1, 0.01, s.body ?? 0.5, v => Math.round(v * 100) + '%', v => setS('body', v)),
        slider('Pick pos', 0.02, 0.5, 0.01, s.pick ?? 0.13, v => Math.round(v * 100) + '%', v => setS('pick', v)),
      ] : [
        el('select', { onchange: e => setS('wave', e.target.value) }, ['sine', 'triangle', 'square', 'sawtooth'].map(w => el('option', { selected: w === s.wave }, w))),
        slider('Attack', 0.001, 2, 0.001, s.attack, v => v.toFixed(3), v => setS('attack', v)),
        slider('Pluck decay', 0, 3, 0.01, s.pluck || 0, v => v ? v.toFixed(2) + 's' : 'off', v => setS('pluck', v)),
      ]),
      el('span', { title: 'Release: fade-out after the note ends' }, slider('Release', 0.01, 3, 0.01, s.release, v => v.toFixed(2) + ' s', v => { setS('release', v); drawEnv(); })),
      slider('Tone', 100, 12000, 10, s.cutoff, v => Math.round(v) + 'Hz', v => setS('cutoff', v)),
      el('button', { title: 'Distortion / amp of this layer is an insert effect – edit it in the Effects tab', onclick: () => showTab('fx') }, 'Amp / FX: ' + ((t.fx || []).filter(f => f.on).map(f => FX_TYPES[f.type].name).join(' › ') || 'none') + ' →'),
      'Chord', el('select', { onchange: e => setS('chord', e.target.value) }, [['none', 'Single note'], ['power', 'Power chord (1-5-8)']].map(([v, l]) => el('option', { value: v, selected: v === (s.chord || 'none') }, l))),
      'Note length', el('select', { onchange: e => { noteLen = +e.target.value; } }, [[1, '1/16'], [2, '1/8'], [4, '1/4'], [8, '1/2'], [16, '1 bar']].map(([v, l]) => el('option', { value: v, selected: v === noteLen }, l))),
      el('button', { onclick: () => { h.notes = []; render(); } }, 'Clear'));
    const covering = (p, i) => h.notes.find(n => n.p === p && i >= n.s && i < n.s + n.l);
    // piano roll: one note can span many steps (a long, sustained note).
    //   drag on empty cells  -> draw one long note (several pads become ONE note)
    //   drag an existing note -> change its length      click a note (no drag) -> delete it
    const rowCells = new Map();
    const paintRow = p => (rowCells.get(p) || []).forEach((cell, i) => {
      const n = covering(p, i);
      cell.classList.toggle('on', !!n);
      cell.classList.toggle('nstart', !!n && n.s === i);
      cell.classList.toggle('ncont', !!n && n.s !== i);
      cell.classList.toggle('nend', !!n && n.s + n.l - 1 === i);
      cell.title = n ? `${NOTE_NAMES[p % 12]}${Math.floor(p / 12) - 1} · ${n.l} step${n.l > 1 ? 's' : ''} (${(n.l / 4).toFixed(2)} beats) – drag to resize, click to delete` : '';
    });
    const startDrag = (e, p, i) => {
      e.preventDefault();
      let note = covering(p, i), existing = !!note, moved = false;
      if (!note) {
        note = { p, s: i, l: Math.min(noteLen, steps - i) }; h.notes.push(note);
        ensureCtx(); playSynth(ctx, trackNodes(rt, t).in, s, p, ctx.currentTime + 0.01, 0.25);
      }
      paintRow(p);
      // a note can't grow into the next note of the same pitch
      const limit = () => Math.min(steps, ...h.notes.filter(x => x !== note && x.p === p && x.s > note.s).map(x => x.s)) - note.s;
      // column under the pointer from its X position along this row (works over gaps / outside the cells too)
      const row = rowCells.get(p), r0 = row[0].getBoundingClientRect();
      const pitch = row.length > 1 ? row[1].getBoundingClientRect().left - r0.left : r0.width;
      const mv = ev => {
        const col = clamp(Math.floor((ev.clientX - r0.left) / pitch), 0, steps - 1);
        if (col !== i) moved = true;
        if (!moved) return;
        note.l = clamp(col - note.s + 1, 1, limit()); paintRow(p);
      };
      const upFn = () => {
        window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', upFn); window.removeEventListener('pointercancel', upFn);
        if (existing && !moved) h.notes = h.notes.filter(x => x !== note);  // plain click on a note = delete
        renderEditor(); renderArrange();
      };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', upFn); window.addEventListener('pointercancel', upFn);
    };
    tools.append(el('span', { className: 'hint', style: { margin: 0 } }, 'Drag = long note · drag a note = resize · click a note = delete'));
    for (let p = HIGH_NOTE; p >= LOW_NOTE; p--) {
      const nm = NOTE_NAMES[p % 12], black = nm.includes('#');
      grid.append(el('div', { className: 'rowlbl' + (black ? ' black' : ''), onclick: () => { ensureCtx(); playSynth(ctx, trackNodes(rt, t).in, s, p, ctx.currentTime + 0.01, 0.3); } }, nm + (Math.floor(p / 12) - 1)));
      const cells = [];
      for (let i = 0; i < steps; i++) {
        const cell = el('div', { className: 'cell' + (Math.floor(i / 4) % 2 ? '' : ' beat') + (i && i % spbar === 0 ? ' barline' : '') });
        cell.dataset.col = i; cell.dataset.p = p;
        cell.addEventListener('pointerdown', e => startDrag(e, p, i));
        cells.push(cell); grid.append(cell);
      }
      rowCells.set(p, cells); paintRow(p);
    }
  }
  grid._h = h; grid._steps = steps; grid._ph = el('div', { className: 'edplayhead' }); grid.append(grid._ph);
  ed.append(grid);
  requestAnimationFrame(highlightStep);
}
// editor playhead: a vertical line over the pad grid at the transport position inside the edited
// region (follows play, seek and stop), plus the step column under it is outlined while playing
function highlightStep() {
  const grid = document.querySelector('#editor .grid'), line = grid && grid._ph;
  document.querySelectorAll('#editor .cell.play').forEach(c => c.classList.remove('play'));
  if (!line) return;
  const h = grid._h, steps = grid._steps, b = Math.max(0, currentBeat());
  const rel = h && h.kind === 'midi' ? (b - h.start) * 4 : -1;  // position in steps inside this region
  if (rel < 0 || rel >= steps) { line.style.display = 'none'; return; }
  const col = Math.floor(rel), cell = grid.querySelector(`.cell[data-col="${col}"]`);
  if (!cell) { line.style.display = 'none'; return; }
  const next = grid.querySelector(`.cell[data-col="${col + 1}"]`), pitch = next ? next.offsetLeft - cell.offsetLeft : cell.offsetWidth + 3;
  line.style.left = cell.offsetLeft + (rel - col) * pitch + 'px'; line.style.display = 'block';
  if (T.playing) grid.querySelectorAll(`.cell[data-col="${col}"]`).forEach(x => x.classList.add('play'));
}

/* ------------------------------------------------------------ effects tab */
function renderFx() {
  const box = $('#fxPanel'); if (!box) return; box.innerHTML = '';
  const t = getTrack(selTrackId);
  if (!t) { box.append(el('p', { className: 'hint' }, 'Select a track (drum, guitar, bass, vocal/audio…) to add insert effects.')); return; }
  t.fx = t.fx || [];
  const changed = (structural) => { syncGraph(); if (structural) { renderFx(); renderMixer(); } };
  const addSel = el('select', { onchange: e => { const v = e.target.value; e.target.selectedIndex = 0; if (!v) return;
      if (v.startsWith('preset:')) t.fx = FX_CHAIN_PRESETS[v.slice(7)].map(([ty, o]) => newFx(ty, o)); else t.fx.push(newFx(v));
      changed(true); } },
    el('option', { value: '' }, '+ Add effect…'),
    el('optgroup', { label: 'Effects' }, Object.entries(FX_TYPES).map(([k, d]) => el('option', { value: k }, d.name))),
    el('optgroup', { label: 'Chain presets (replace)' }, Object.keys(FX_CHAIN_PRESETS).map(k => el('option', { value: 'preset:' + k }, k))));
  box.append(el('div', { className: 'edtools' }, el('b', {}, 'Insert FX – ' + t.name), addSel,
    el('span', { className: 'hint' }, 'Signal: input → effects (left → right) → channel EQ/comp → fader → pan → sends')));
  const chain = el('div', { className: 'fxchain' });
  if (!t.fx.length) chain.append(el('p', { className: 'hint' }, 'No effects yet. Add EQ, Compressor, Distortion, Filter, Chorus, Tremolo, Delay, or Reverb, or load a chain preset (Vocal, Guitar Amp, Metal Guitar, Drum Bus, Bass, Lo-Fi).'));
  t.fx.forEach((fx, i) => {
    const spec = FX_TYPES[fx.type];
    const move = d => { const j = i + d; if (j < 0 || j >= t.fx.length) return; [t.fx[i], t.fx[j]] = [t.fx[j], t.fx[i]]; changed(true); };
    const card = el('div', { className: 'fxcard' + (fx.on ? '' : ' off') },
      el('div', { className: 'hd' }, el('b', {}, (i + 1) + '. ' + spec.name),
        el('button', { className: fx.on ? 'on' : '', title: 'Bypass on/off', onclick: () => { fx.on = !fx.on; changed(true); } }, fx.on ? 'ON' : 'OFF'),
        el('button', { title: 'Move left', onclick: () => move(-1) }, '◀'),
        el('button', { title: 'Move right', onclick: () => move(1) }, '▶'),
        el('button', { title: 'Remove', onclick: () => { t.fx.splice(i, 1); changed(true); } }, '✕')));
    for (const [k, sp] of Object.entries(spec.params)) {
      if (Array.isArray(sp[1])) card.append(el('label', {}, FX_LABELS[k] || k, el('select', { onchange: e => { fx.p[k] = e.target.value; changed(false); } }, sp[1].map(o => el('option', { selected: o === fx.p[k] }, o)))));
      else {
        const [, mn, mx, st, unit] = sp;
        const fmt = v => unit === '' ? (mx <= 1.5 ? Math.round(v * 100) + '%' : v.toFixed(1)) : (st < 0.01 ? v.toFixed(3) : st < 1 ? (+v).toFixed(2) : Math.round(v)) + ' ' + unit;
        card.append(slider(FX_LABELS[k] || k, mn, mx, st, fx.p[k], fmt, v => { fx.p[k] = v; changed(false); }));
      }
    }
    if (i) chain.append(el('div', { className: 'fxarrow' }, '›'));
    chain.append(card);
  });
  box.append(chain);
}

/* --------------------------------------------------------------- mastering */
function renderMaster() {
  const m = $('#master'), M = P.master; m.innerHTML = '';
  const set = (k) => v => { M[k] = v; if (rt) applyMaster(rt); };
  m.append(
    el('div', { className: 'mstbox' }, el('h4', {}, 'Preset'),
      el('select', { onchange: e => { Object.assign(M, MASTER_PRESETS[e.target.value]); if (rt) applyMaster(rt); renderMaster(); } }, el('option', {}, '— choose —'), Object.keys(MASTER_PRESETS).map(k => el('option', {}, k))),
      el('p', { className: 'hint' }, 'Chain: EQ → Compressor → Make-up → Limiter → Output. Export renders through this chain.'),
      el('div', { className: 'meter', style: { height: '10px', background: '#000' } }, el('div', { id: 'meter-master2', style: { height: '100%', width: 0, background: 'var(--meter)' } })),
      el('div', { id: 'peak-master2' }, '-∞ dB')),
    el('div', { className: 'mstbox' }, el('h4', {}, 'Master EQ'),
      slider('Low (120Hz)', -12, 12, 0.5, M.eqLow, v => v + ' dB', set('eqLow')),
      slider('Mid (1.2k)', -12, 12, 0.5, M.eqMid, v => v + ' dB', set('eqMid')),
      slider('High (8k)', -12, 12, 0.5, M.eqHigh, v => v + ' dB', set('eqHigh'))),
    el('div', { className: 'mstbox' }, el('h4', {}, 'Bus Compressor'),
      slider('Threshold', -50, 0, 1, M.compThr, v => v + ' dB', set('compThr')),
      slider('Ratio', 1, 20, 0.5, M.compRatio, v => v + ':1', set('compRatio')),
      slider('Attack', 0.001, 0.2, 0.001, M.compAtk, v => (v * 1000).toFixed(0) + ' ms', set('compAtk')),
      slider('Release', 0.02, 1, 0.01, M.compRel, v => (v * 1000).toFixed(0) + ' ms', set('compRel')),
      slider('Make-up', 0, 18, 0.5, M.makeup, v => '+' + v + ' dB', set('makeup'))),
    el('div', { className: 'mstbox' }, el('h4', {}, 'Limiter / Output'),
      slider('Ceiling', -12, 0, 0.1, M.ceiling, v => v.toFixed(1) + ' dB', set('ceiling')),
      slider('Output', 0, 1.5, 0.01, M.vol, fmtDb, set('vol'))),
    el('div', { className: 'mstbox' }, el('h4', {}, 'Space FX (send buses)'),
      slider('Reverb size', 0.3, 6, 0.1, M.reverbSize, v => v.toFixed(1) + ' s', set('reverbSize')),
      slider('Delay (beats)', 0.25, 2, 0.25, M.delayDiv, v => v + '', set('delayDiv')),
      slider('Feedback', 0, 0.9, 0.01, M.delayFb, v => Math.round(v * 100) + '%', set('delayFb'))));
}

/* ------------------------------------------------------------------ meters */
const meterBuf = new Float32Array(2048);
function peakOf(an) { an.getFloatTimeDomainData(meterBuf.subarray(0, an.fftSize)); let m = 0; for (let i = 0; i < an.fftSize; i++) { const v = Math.abs(meterBuf[i]); if (v > m) m = v; } return m; }
function frame() {
  if (T.playing) {
    drawPlayhead(); highlightStep();
    const wrap = $('#timelineWrap'), x = Math.max(0, currentBeat()) * pxB();
    if (x > wrap.scrollLeft + wrap.clientWidth - 60 || x < wrap.scrollLeft) wrap.scrollLeft = Math.max(0, x - 60);
  }
  if (rt) {
    P.tracks.forEach(t => { const n = rt.tracks.get(t.id), e = document.getElementById('meter-' + t.id); if (n && e) e.style.width = Math.min(100, peakOf(n.an) * 100) + '%'; });
    const pk = peakOf(rt.an), w = Math.min(100, pk * 100) + '%', txt = (pk > 0 ? (20 * Math.log10(pk)).toFixed(1) : '-∞') + ' dBFS';
    ['meter-master', 'meter-master2'].forEach(id => { const e = document.getElementById(id); if (e) e.style.width = w; });
    ['peak-master', 'peak-master2'].forEach(id => { const e = document.getElementById(id); if (e) e.textContent = txt; });
  }
  requestAnimationFrame(frame);
}

/* ------------------------------------------------------------- wav / export */
function encodeWAV(buf, bits = 16) {
  const nCh = buf.numberOfChannels, len = buf.length, bps = bits / 8, data = len * nCh * bps;
  const ab = new ArrayBuffer(44 + data), v = new DataView(ab); let o = 0;
  const str = s => { for (const ch of s) v.setUint8(o++, ch.charCodeAt(0)); };
  const u32 = x => { v.setUint32(o, x, true); o += 4; }, u16 = x => { v.setUint16(o, x, true); o += 2; };
  str('RIFF'); u32(36 + data); str('WAVE'); str('fmt '); u32(16); u16(1); u16(nCh); u32(buf.sampleRate); u32(buf.sampleRate * nCh * bps); u16(nCh * bps); u16(bits);
  str('data'); u32(data);
  const chs = [...Array(nCh).keys()].map(i => buf.getChannelData(i));
  for (let i = 0; i < len; i++) for (let c = 0; c < nCh; c++) {
    const s = clamp(chs[c][i], -1, 1);
    if (bits === 16) { v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true); o += 2; }
    else { const x = Math.round(s < 0 ? s * 0x800000 : s * 0x7fffff); v.setUint8(o, x & 255); v.setUint8(o + 1, (x >> 8) & 255); v.setUint8(o + 2, (x >> 16) & 255); o += 3; }
  }
  return new Blob([ab], { type: 'audio/wav' });
}
async function renderMix() {
  ensureRegions();
  await samplesReady();
  const end = songEndBeats(); if (end <= 0) throw new Error('Nothing to export – add some clips first');
  const sr = 44100, secs = end * spb() + 2.5;
  const oc = new OfflineAudioContext(2, Math.ceil(sr * secs), sr);
  const g = createGraph(oc, false);
  scheduleRange(g, 0, end, { t: 0, b: 0 }, { first: true });
  const out = await oc.startRendering();
  let pk = 0; for (let c = 0; c < out.numberOfChannels; c++) { const d = out.getChannelData(c); for (let i = 0; i < d.length; i++) { const a = Math.abs(d[i]); if (a > pk) pk = a; } }
  const target = dbToGain(Math.min(-0.3, P.master.ceiling));
  // Normalize: bring the peak to the ceiling. Without normalize: still never exceed the ceiling
  // (the Web Audio limiter is not a true brickwall, so this guard prevents clipped exports).
  if (pk > 0 && ($('#normalize').checked || pk > target)) {
    const k = target / pk; for (let c = 0; c < out.numberOfChannels; c++) { const d = out.getChannelData(c); for (let i = 0; i < d.length; i++) d[i] *= k; }
  }
  return out;
}
function download(blob, name) {
  const a = el('a', { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 30000);
}
async function exportSong() {
  const fmt = $('#exportFmt').value, title = $('#title').value || 'RushDAW';
  const btn = $('#btnExport'); btn.disabled = true;
  try {
    status('Rendering mixdown…');
    const wav = encodeWAV(await renderMix());
    if (fmt === 'wav') { download(wav, title + '.wav'); status('Exported WAV'); return; }
    status('Encoding ' + fmt.toUpperCase() + ' with ffmpeg…');
    const r = await fetch(`/api/export?format=${encodeURIComponent(fmt)}&title=${encodeURIComponent(title)}`, { method: 'POST', body: wav, headers: { 'Content-Type': 'audio/wav' } });
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error; } catch (e) { /* ignore */ } throw new Error(m); }
    download(await r.blob(), `${title}.${fmt}`); status('Exported ' + fmt.toUpperCase());
  } catch (e) { status('Export failed: ' + e.message); }
  finally { btn.disabled = false; }
}

/* ------------------------------------------- projects: save / load / history */
// Projects live on the local server: metadata in ~/.rushdaw/db.sql (SQLite),
// every saved revision as a full .rushdaw file in ~/.rushdaw/file/<project_id>/.
const blobToB64 = b => new Promise(res => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.readAsDataURL(b); });
const DEFAULT_MASTER = JSON.parse(JSON.stringify(P.master));
let currentProject = null;   // { id, name, head_revision, ... }
let savedSnapshot = '';      // state at last save/load, used for the unsaved-changes indicator
let saving = false;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch (e) { /* not json */ } throw new Error(m); }
  return r;
}
const snapshot = () => JSON.stringify(P) + '|' + [...buffers.keys()].join(',');
const isDirty = () => !!currentProject && snapshot() !== savedSnapshot;
function markClean() { savedSnapshot = snapshot(); updateDirty(); }
function updateDirty() { const d = $('#dirtyDot'); if (d) d.classList.toggle('on', isDirty()); }

async function serializeProject() {
  ensureRegions();
  P.title = $('#title').value;
  const used = new Set(); P.tracks.forEach(t => t.clips.forEach(c => c.kind === 'audio' && used.add(c.buf)));
  const audio = {};
  for (const id of used) if (buffers.has(id)) audio[id] = { name: bufNames.get(id) || '', wav: await blobToB64(encodeWAV(buffers.get(id))) };
  return JSON.stringify({ app: 'rushdaw', version: 1, project: P, audio });
}
async function saveRevision(message) {
  if (!currentProject || saving) return null;
  saving = true; status('Saving revision…');
  try {
    const body = await serializeProject();
    const r = await (await api(`/api/projects/${currentProject.id}/revisions?message=${encodeURIComponent(message || '')}`, { method: 'POST', body, headers: { 'Content-Type': 'application/json' } })).json();
    currentProject.head_revision = r.number; currentProject.name = P.title;
    markClean(); $('#revMsg').value = '';
    status(`Saved revision ${r.number} (${(r.size / 1048576).toFixed(2)} MB) → ~/.rushdaw/file/${currentProject.id.slice(0, 8)}…/${r.file_name}`);
    return r;
  } catch (e) { status('Save failed: ' + e.message); return null; }
  finally { saving = false; }
}
async function autoSave() { if (isDirty()) await saveRevision('Auto-save'); }

function resetState() {
  stopTransport();
  if (rt) { rt.tracks.forEach(n => { n.pan.disconnect(); n.fxUnits.forEach(disposeFxUnit); }); rt.tracks.clear(); }
  buffers.clear(); bufNames.clear(); peaksCache.clear();
  P.tracks = []; P.master = JSON.parse(JSON.stringify(DEFAULT_MASTER)); P.loop = { start: 0, end: 16 }; P.sig = 4;
  selTrackId = null; selClipId = null; T.pos = 0;
}
// D-Beat / Crust Punk: d-beat drums, pick bass + distorted power-chord guitar doubling a dark riff in E
const CRUST_RIFF = [[40, 0, 2], [40, 2, 1], [40, 3, 1], [43, 4, 2], [41, 6, 2], [40, 8, 2], [40, 10, 1], [40, 11, 1], [46, 12, 2], [45, 14, 2]];
function applyCrustTemplate() {
  const d = newTrack('drum'); d.name = 'Drums'; applyDrumPreset(d, 'Crust D-Beat'); d.clips.push({ id: nid('c'), kind: 'midi', start: 0, len: 16 });
  const b = newBassTrack(0); b.synth = { preset: 'Pick Bass', ...SYNTH_DEFAULTS, ...SYNTH_PRESETS['Pick Bass'] };
  b.notes = CRUST_RIFF.map(([p, s, l]) => ({ p, s, l })); b.clips[0].len = 16;
  b.fx = [newFx('dist', { drive: 0.35, tone: 2500, level: 0.8, mix: 0.5 })];  // gritty crust bass
  const g = newGuitarTrack(0); applySynthPreset(g, 'Power Chord Guitar');  // its amp shows up in this layer's Effects
  g.notes = CRUST_RIFF.map(([p, s, l]) => ({ p, s, l })); g.clips[0].len = 16;
  newTrack('audio').name = 'Vocal';
  selTrackId = d.id;
}
function applyTemplate(tpl) {
  if (tpl === 'empty') { newTrack('audio'); return; }
  if (tpl === 'dbeat') { applyCrustTemplate(); return; }
  const d = newTrack('drum'); d.clips.push({ id: nid('c'), kind: 'midi', start: 0, len: 16 });
  newBassTrack(0).clips[0].len = 16;
  newGuitarTrack(0).clips[0].len = 16;
  const a = newTrack('audio'); if (tpl === 'band') { a.name = 'Vocal'; a.fx = FX_CHAIN_PRESETS.Vocal.map(([ty, o]) => newFx(ty, o)); }
  selTrackId = d.id;
}
async function loadProjectData(j) {
  ensureCtx(); resetState();
  if (j.app !== 'rushdaw') throw new Error('not a RushDAW project');
  for (const [id, a] of Object.entries(j.audio || {})) {
    const bin = Uint8Array.from(atob(a.wav), ch => ch.charCodeAt(0));
    buffers.set(id, await ctx.decodeAudioData(bin.buffer)); bufNames.set(id, a.name);
  }
  Object.assign(P, j.project); P.master = { ...DEFAULT_MASTER, ...j.project.master };
  P.tracks.forEach(t => { t.fx = t.fx || []; migrateDrumTrack(t); migrateStringTrack(t); normalizeAmp(t); });
  ensureRegions();  // older projects: every region gets its own copy of the track pattern
  $('#bpm').value = P.bpm; $('#sig').value = P.sig; $('#title').value = P.title;
  selTrackId = P.tracks[0]?.id || null; syncGraph(); render();
}
async function openProject(id, rev = null) {
  try {
    status('Opening project…');
    const meta = await (await api(`/api/projects/${id}`)).json();
    const r = await api(`/api/projects/${id}/file${rev ? '?rev=' + rev : ''}`);
    await loadProjectData(await r.json());
    P.title = meta.name; $('#title').value = meta.name;   // DB name wins (rename in manager)
    currentProject = meta; markClean();
    const n = +r.headers.get('X-Revision');
    if (rev && n !== meta.head_revision) { savedSnapshot = ''; updateDirty(); }  // older revision loaded = unsaved working copy
    history.replaceState(null, '', '#p=' + id);
    hideHome();
    status(rev && n !== meta.head_revision ? `Viewing revision ${n} of ${meta.name} – Save creates revision ${meta.head_revision + 1}` : `Opened ${meta.name} (revision ${n})`);
  } catch (e) { status('Open failed: ' + e.message); showHome(); }
}
async function createProject() {
  const name = $('#npName').value.trim() || 'New Song', bpm = clamp(+$('#npBpm').value || 180, 40, 240);
  try {
    const meta = await (await api('/api/projects', { method: 'POST', body: JSON.stringify({ name, bpm, sig: 4 }), headers: { 'Content-Type': 'application/json' } })).json();
    ensureCtx(); resetState(); P.bpm = bpm; P.title = name; $('#bpm').value = bpm; $('#sig').value = 4; $('#title').value = name;
    applyTemplate($('#npTpl').value); syncGraph(); render();
    currentProject = meta; await saveRevision('Created');
    history.replaceState(null, '', '#p=' + meta.id); hideHome();
  } catch (e) { status('Create failed: ' + e.message); }
}

/* project manager screen */
let showTrash = false;
const fmtAgo = ts => { const s = Date.now() / 1000 - ts; if (s < 60) return 'just now'; if (s < 3600) return Math.floor(s / 60) + ' min ago'; if (s < 86400) return Math.floor(s / 3600) + ' h ago'; return new Date(ts * 1000).toLocaleString(); };
const fmtSize = b => b == null ? '–' : b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
async function showHome() {
  await autoSave();
  stopTransport();
  $('#home').classList.add('show'); history.replaceState(null, '', location.pathname);
  renderHome();
}
function hideHome() { $('#home').classList.remove('show'); }
async function renderHome() {
  const list = $('#projList'); list.innerHTML = '<p class="hint">Loading…</p>';
  $('#homeTitle').textContent = showTrash ? 'Trash (deleted projects – files are kept)' : 'Projects';
  $('#btnTrash').textContent = showTrash ? '← Back to projects' : '🗑 Trash';
  try {
    const data = await (await api('/api/projects' + (showTrash ? '?deleted=1' : ''))).json();
    $('#homePath').textContent = `Data: ${data.home}/db.sql  ·  files: ${data.home}/file/`;
    const q = $('#projSearch').value.trim().toLowerCase();
    const items = data.projects.filter(p => !q || p.name.toLowerCase().includes(q));
    list.innerHTML = '';
    if (!items.length) list.append(el('p', { className: 'hint' }, showTrash ? 'Trash is empty.' : 'No projects yet – create one above.'));
    items.forEach(p => {
      const nameEl = el('div', { className: 'pname', title: 'Open' }, p.name);
      const card = el('div', { className: 'pcard' },
        nameEl,
        el('div', { className: 'pmeta' }, `${Math.round(p.bpm)} BPM · ${p.sig}/4 · rev ${p.head_revision} · ${fmtSize(p.size)}`),
        el('div', { className: 'pmeta' }, 'Updated ' + fmtAgo(p.updated_at)),
        el('div', { className: 'pbtns' }, showTrash
          ? [el('button', { className: 'primary', onclick: async () => { await api(`/api/projects/${p.id}/undelete`, { method: 'POST' }); renderHome(); } }, '↺ Restore')]
          : [el('button', { className: 'primary', onclick: () => openProject(p.id) }, 'Open'),
            el('button', { onclick: () => openHistory(p.id, true) }, '🕘 History'),
            el('button', { onclick: () => {
              const inp = el('input', { value: p.name, className: 'pname-edit' });
              const done = async ok => { if (ok && inp.value.trim()) await api(`/api/projects/${p.id}/rename`, { method: 'POST', body: JSON.stringify({ name: inp.value }), headers: { 'Content-Type': 'application/json' } }); renderHome(); };
              inp.onkeydown = e => { if (e.key === 'Enter') done(true); if (e.key === 'Escape') done(false); };
              inp.onblur = () => done(true); nameEl.replaceWith(inp); inp.focus(); inp.select();
            } }, '✎ Rename'),
            el('button', { title: 'Move to trash (can be restored)', onclick: async () => { await api(`/api/projects/${p.id}`, { method: 'DELETE' }); renderHome(); } }, '🗑')]));
      if (!showTrash) nameEl.onclick = () => openProject(p.id);
      list.append(card);
    });
  } catch (e) { list.innerHTML = ''; list.append(el('p', { className: 'hint' }, 'Cannot reach the RushDAW server: ' + e.message)); }
}

/* revision history dialog */
async function openHistory(id = currentProject?.id, fromHome = false) {
  if (!id) return;
  const box = $('#historyList'); box.innerHTML = '<p class="hint">Loading…</p>'; $('#historyDlg').classList.add('show');
  try {
    const p = await (await api(`/api/projects/${id}`)).json();
    $('#historyTitle').textContent = `History – ${p.name} (${p.revisions.length} revisions)`;
    box.innerHTML = '';
    p.revisions.forEach(r => box.append(el('div', { className: 'hrow' + (r.number === p.head_revision ? ' head' : '') },
      el('div', { className: 'hnum' }, 'r' + r.number),
      el('div', { className: 'hinfo' }, el('b', {}, r.message), el('span', { className: 'pmeta' }, `${new Date(r.created_at * 1000).toLocaleString()} · ${r.track_count} tracks · ${fmtSize(r.size)}${r.number === p.head_revision ? ' · latest' : ''}`)),
      el('div', { className: 'pbtns' },
        el('button', { title: 'Load this revision into the editor', onclick: async () => { $('#historyDlg').classList.remove('show'); if (!fromHome) await autoSave(); openProject(id, r.number); } }, 'Open'),
        r.number !== p.head_revision ? el('button', { title: 'Make this revision the latest (creates a new revision, nothing is lost)', onclick: async () => {
          if (!fromHome) await autoSave();
          await api(`/api/projects/${id}/restore?rev=${r.number}`, { method: 'POST' }); $('#historyDlg').classList.remove('show'); openProject(id);
        } }, '↺ Restore') : null,
        el('a', { className: 'btnlink', href: `/api/projects/${id}/file?rev=${r.number}&download=1`, title: 'Download this revision as a .rushdaw file' }, '⬇')))));
  } catch (e) { box.innerHTML = ''; box.append(el('p', { className: 'hint' }, 'Error: ' + e.message)); }
}
async function importProjectFile(file) {
  try {
    status('Importing ' + file.name + '…');
    const meta = await (await api('/api/projects/import?name=' + encodeURIComponent(file.name.replace(/\.(rushdaw|json)$/i, '')), { method: 'POST', body: await file.arrayBuffer() })).json();
    renderHome(); openProject(meta.id);
  } catch (e) { status('Import failed: ' + e.message); alert('Import failed: ' + e.message); }
}

/* ------------------------------------------------- clipboard: copy / cut / paste */
// Works on whatever was focused last: a clip/region ('clip'), a whole track/layer ('track')
// or a drum part row ('part'). Audio buffers travel with the clipboard so pasting
// still works after opening another project.
let clipboard = null;        // { kind, data, buffers: Map }
let selPart = null;          // { trackId, row } – selected drum part in the editor
let lastFocus = null;        // 'clip' | 'track' | 'part'
const deepCopy = o => JSON.parse(JSON.stringify(o));
function buffersFor(clips) {
  const m = new Map();
  clips.forEach(c => { if (c.kind === 'audio' && buffers.has(c.buf)) m.set(c.buf, { buf: buffers.get(c.buf), name: bufNames.get(c.buf) }); });
  return m;
}
function restoreBuffers(m) { m.forEach((v, id) => { if (!buffers.has(id)) { buffers.set(id, v.buf); bufNames.set(id, v.name); } }); }
function copySelection(cut = false) {
  if (lastFocus === 'part' && selPart) {
    const t = getTrack(selPart.trackId); if (!t || t.type !== 'drum') return;
    const d = DRUMS[selPart.row];
    const h = edHolder(t);
    clipboard = { kind: 'part', data: { id: d.id, name: d.name, steps: h.pattern.grid[selPart.row].slice(), kit: { ...kitOf(t, d.id) } } };
    if (cut) { h.pattern.grid[selPart.row].fill(0); render(); }
    status(`${cut ? 'Cut' : 'Copied'} drum part “${d.name}” (pattern + tuning)`); return;
  }
  const [ct, c] = findClip(selClipId);
  if (lastFocus === 'clip' && c) {
    clipboard = { kind: 'clip', data: { clip: deepCopy(c), trackType: ct.type, trackId: ct.id }, buffers: buffersFor([c]) };
    if (cut) { ct.clips = ct.clips.filter(x => x !== c); selClipId = null; render(); }
    status(`${cut ? 'Cut' : 'Copied'} ${c.kind === 'audio' ? 'audio clip' : 'pattern region'}`); return;
  }
  const t = getTrack(selTrackId);
  if (t) {
    clipboard = { kind: 'track', data: deepCopy(t), buffers: buffersFor(t.clips) };
    if (cut) deleteTrack(t.id);
    status(`${cut ? 'Cut' : 'Copied'} track “${t.name}”`); return;
  }
  status('Nothing selected to copy – click a clip, a track or a drum part first');
}
function pasteClipboard() {
  if (!clipboard) { status('Clipboard is empty'); return; }
  const cb = clipboard;
  if (cb.buffers) restoreBuffers(cb.buffers);
  if (cb.kind === 'part') {
    let t = getTrack(selTrackId);
    if (!t || t.type !== 'drum') t = selPart && getTrack(selPart.trackId);
    if (!t || t.type !== 'drum') { status('Select a drum track to paste the part into'); return; }
    const row = selPart && selPart.trackId === t.id ? selPart.row : DRUMS.findIndex(d => d.id === cb.data.id);
    const h = edHolder(t), n = patSteps(h), src = cb.data.steps;
    h.pattern.grid[row] = Array.from({ length: n }, (_, i) => src[i] || 0);  // copied as-is, the rest stays empty (no repeating)
    t.kit = t.kit || {}; t.kit[DRUMS[row].id] = { ...cb.data.kit };
    render(); status(`Pasted “${cb.data.name}” into ${DRUMS[row].name} on ${t.name}`); return;
  }
  if (cb.kind === 'clip') {
    const want = cb.data.trackType;
    let t = getTrack(selTrackId);
    if (!t || t.type !== want) t = getTrack(cb.data.trackId) || P.tracks.find(x => x.type === want);
    if (!t) { t = newTrack(want); }
    const nc = { ...deepCopy(cb.data.clip), id: nid('c'), start: snapBeat(T.pos, 0.25) };
    t.clips.push(nc); selClipId = nc.id; lastFocus = 'clip'; selectTrack(t.id, false);
    render(); status(`Pasted clip on ${t.name} at bar ${Math.floor(nc.start / P.sig) + 1}`); return;
  }
  if (cb.kind === 'track') {
    const t = deepCopy(cb.data);
    t.id = nid('t'); t.name = t.name.replace(/( \(copy( \d+)?\))?$/, '') + ' (copy)';
    t.solo = false; t.arm = false; t.color = COLORS[P.tracks.length % COLORS.length];
    t.clips.forEach(c => { c.id = nid('c'); }); (t.fx || []).forEach(f => { f.id = nid('f'); });
    const at = P.tracks.findIndex(x => x.id === selTrackId);
    P.tracks.splice(at < 0 ? P.tracks.length : at + 1, 0, t);
    selTrackId = t.id; lastFocus = 'track'; syncGraph(); render(); status(`Pasted track “${t.name}”`);
  }
}

/* --------------------------------------------------------------- tab / misc */
function showTab(name) {
  document.querySelectorAll('.tabs button[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + name));
}
function hideDrop() { $('#dropOverlay').style.display = 'none'; }
function splitClip() {
  const [t, c] = findClip(selClipId); if (!c) return;
  const b = currentBeat(), len = clipLenBeats(c); if (b <= c.start || b >= c.start + len) return;
  const cut = b - c.start, nc = { ...deepCopy(c), id: nid('c'), start: b };  // deep copy: the halves are independent
  if (c.kind === 'audio') { nc.offset = c.offset + cut * spb(); nc.dur = c.dur - cut * spb(); c.dur = cut * spb(); }
  else { const k = Math.round(cut * 4); nc.len = c.len - cut; c.len = cut; if (isPatHolder(t, nc)) { shiftLeft(t, nc, k); fitRegion(t, c); fitRegion(t, nc); } }
  t.clips.push(nc); render();
}
function duplicateClip() {
  const [t, c] = findClip(selClipId); if (!c) return;
  const nc = { ...deepCopy(c), id: nid('c'), start: c.start + clipLenBeats(c) }; t.clips.push(nc); selClipId = nc.id; render();  // independent copy
}
// drop the first k steps of a region (split: the right half starts where the cut was)
function shiftLeft(t, h, k) {
  if (t.type === 'drum') h.pattern.grid = h.pattern.grid.map(r => r.slice(k));
  else h.notes = h.notes.filter(x => x.s >= k).map(x => ({ ...x, s: x.s - k }));
}

/* MIDI guitar track = synth track with a guitar preset + starter power-chord riff */
function newGuitarTrack(startBeat = 0) {
  const t = newTrack('synth');
  t.instrument = 'guitar';
  t.name = 'Guitar ' + P.tracks.filter(x => x.instrument === 'guitar').length;
  t.synth = { preset: DEFAULT_GUITAR_PRESET, ...SYNTH_DEFAULTS, ...SYNTH_PRESETS[DEFAULT_GUITAR_PRESET] };
  [[40, 0, 2], [40, 2, 1], [40, 3, 1], [43, 4, 2], [45, 6, 2], [40, 8, 2], [46, 10, 1], [45, 11, 1], [43, 12, 4]]
    .forEach(([p, s, l]) => t.notes.push({ p, s, l }));
  t.clips.push({ id: nid('c'), kind: 'midi', start: startBeat, len: P.sig * 4 });
  return t;
}
/* MIDI bass track = synth track with a natural plucked bass string */
function newBassTrack(startBeat = 0) {
  const t = newTrack('synth');
  t.instrument = 'bass';
  t.name = 'Bass' + (P.tracks.filter(x => x.instrument === 'bass').length > 1 ? ' ' + P.tracks.filter(x => x.instrument === 'bass').length : '');
  t.synth = { preset: DEFAULT_BASS_PRESET, ...SYNTH_DEFAULTS, ...SYNTH_PRESETS[DEFAULT_BASS_PRESET] };
  [[40, 0, 2], [40, 4, 2], [43, 8, 2], [45, 12, 4]].forEach(([p, s, l]) => t.notes.push({ p, s, l }));
  t.clips.push({ id: nid('c'), kind: 'midi', start: startBeat, len: P.sig * 4 });
  return t;
}

/* ------------------------------------------------------------------ wiring */
function init() {
  loadAllSamples();  // real guitar/bass recordings (~1 MB) decoded in the background right away
  $('#btnPlay').onclick = togglePlay;
  $('#btnRewind').onclick = () => seek(0);
  $('#btnRecord').onclick = startRecording;
  $('#bpm').onchange = e => {
    const was = T.playing && !T.recording, b = currentBeat(); if (was) stopTransport();
    P.bpm = clamp(+e.target.value || 120, 40, 240); e.target.value = P.bpm; if (was) startTransport(b); syncGraph(); render();
  };
  $('#sig').onchange = e => {
    P.sig = +e.target.value;
    P.tracks.forEach(t => [t, ...t.clips.filter(c => isPatHolder(t, c))].forEach(h => {
      if (t.type === 'drum') resizeGrid(h); if (t.type === 'synth') h.notes = h.notes.filter(n => n.s < patSteps(h));
    }));
    render();
  };
  $('#zoom').oninput = () => renderArrange();
  $('#loop').onchange = drawLoop;
  $('#title').onchange = e => { P.title = e.target.value; };
  $('#addBass').onclick = () => { const t = newBassTrack(Math.floor(T.pos / P.sig) * P.sig); selTrackId = t.id; syncGraph(); render(); showTab('editor'); };
  $('#addGuitar').onclick = () => { const t = newGuitarTrack(Math.floor(T.pos / P.sig) * P.sig); selTrackId = t.id; syncGraph(); render(); showTab('editor'); };
  ['addAudio', 'addDrum', 'addSynth'].forEach(id => { $('#' + id).onclick = () => {
    const t = newTrack(id.slice(3).toLowerCase());
    if (t.type !== 'audio') t.clips.push({ id: nid('c'), kind: 'midi', start: Math.floor(T.pos / P.sig) * P.sig, len: P.sig * 4 });
    selTrackId = t.id; syncGraph(); render(); if (t.type !== 'audio') showTab('editor');
  }; });
  $('#btnImport').onclick = () => $('#fileInput').click();
  $('#btnCopy').onclick = () => copySelection(false);
  $('#btnCut').onclick = () => copySelection(true);
  $('#btnPaste').onclick = () => pasteClipboard();
  $('#fileInput').onchange = e => { const t = getTrack(selTrackId); importFiles([...e.target.files], t, null); e.target.value = ''; };
  $('#btnSave').onclick = () => saveRevision($('#revMsg').value);
  $('#revMsg').onkeydown = e => { if (e.key === 'Enter') saveRevision($('#revMsg').value); };
  $('#btnHistory').onclick = () => openHistory();
  $('#btnProjects').onclick = showHome;
  $('#historyClose').onclick = () => $('#historyDlg').classList.remove('show');
  $('#historyDlg').onclick = e => { if (e.target.id === 'historyDlg') $('#historyDlg').classList.remove('show'); };
  $('#npCreate').onclick = createProject;
  $('#npName').onkeydown = e => { if (e.key === 'Enter') createProject(); };
  $('#npImport').onclick = () => $('#npImportFile').click();
  $('#npImportFile').onchange = e => { if (e.target.files[0]) importProjectFile(e.target.files[0]); e.target.value = ''; };
  $('#projSearch').oninput = renderHome;
  $('#btnTrash').onclick = () => { showTrash = !showTrash; renderHome(); };
  setInterval(updateDirty, 1000);
  // pick up edits made from outside the browser (MCP tools create new revisions)
  let externalWarned = 0;
  setInterval(async () => {
    if (!currentProject || saving || $('#home').classList.contains('show') || document.hidden) return;
    try {
      const meta = await (await api(`/api/projects/${currentProject.id}`)).json();
      if (meta.head_revision <= currentProject.head_revision) return;
      const msg = meta.revisions[0]?.message || '';
      if (!isDirty() && !T.playing && !T.recording) {
        const keepTab = document.querySelector('.tabs button.active')?.dataset.tab, keepTrack = selTrackId;
        await openProject(currentProject.id);
        if (getTrack(keepTrack)) { selTrackId = keepTrack; render(); }
        if (keepTab) showTab(keepTab);
        status(`Reloaded – updated outside the editor: r${meta.head_revision} “${msg}”`);
      } else if (externalWarned !== meta.head_revision) {
        externalWarned = meta.head_revision;
        status(`⚠ Project changed outside the editor (r${meta.head_revision} “${msg}”). Your unsaved changes are kept; Save creates a newer revision on top (open History to compare).`);
      }
    } catch (e) { /* server busy / offline – try again later */ }
  }, 3000);
  window.addEventListener('beforeunload', e => { if (isDirty()) { e.preventDefault(); e.returnValue = ''; } });
  $('#btnExport').onclick = exportSong;
  document.querySelectorAll('.tabs button[data-tab]').forEach(b => { b.onclick = () => showTab(b.dataset.tab); });

  // ruler: click to seek, shift+drag to set loop region
  $('#ruler').addEventListener('pointerdown', e => {
    const r = $('#ruler'); const b0 = snapBeat(xToBeat(e, r));
    if (!e.shiftKey) { seek(b0); return; }
    $('#loop').checked = true;
    const mm = ev => { const b1 = snapBeat(xToBeat(ev, r)); P.loop = { start: Math.min(b0, b1), end: Math.max(b0, b1) }; drawLoop(); };
    const mu = () => { window.removeEventListener('pointermove', mm); window.removeEventListener('pointerup', mu); };
    window.addEventListener('pointermove', mm); window.addEventListener('pointerup', mu);
  });
  // resizable bottom panel (mouse + touch), remembered between sessions
  const bottom = $('#bottom'), savedH = +localStorage.getItem('rushdaw.bottomH');
  if (savedH) bottom.style.height = savedH + 'px';
  $('#splitter').addEventListener('pointerdown', e => {
    e.preventDefault(); const y0 = e.clientY, h0 = bottom.getBoundingClientRect().height;
    const mm = ev => { const h = clamp(h0 + (y0 - ev.clientY), 120, window.innerHeight - 160); bottom.style.height = h + 'px'; };
    const mu = () => { window.removeEventListener('pointermove', mm); window.removeEventListener('pointerup', mu); localStorage.setItem('rushdaw.bottomH', Math.round(bottom.getBoundingClientRect().height)); };
    window.addEventListener('pointermove', mm); window.addEventListener('pointerup', mu);
  });
  // sync header scroll with timeline
  $('#timelineWrap').addEventListener('scroll', e => { $('#trackHeaders').style.transform = `translateY(${-e.target.scrollTop}px)`; });
  // global drag & drop import
  let dragDepth = 0;
  window.addEventListener('dragenter', e => { if (e.dataTransfer.types.includes('Files')) { dragDepth++; $('#dropOverlay').style.display = 'flex'; } });
  window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; hideDrop(); } });
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => { e.preventDefault(); dragDepth = 0; hideDrop(); if (e.dataTransfer.files.length) importFiles([...e.dataTransfer.files]); });
  // keyboard: Ctrl/Cmd+S always saves a revision (even while typing in a field)
  window.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) { e.preventDefault(); e.stopImmediatePropagation(); if (!$('#home').classList.contains('show')) saveRevision($('#revMsg').value); }
  }, true);
  window.addEventListener('keydown', e => {
    if ($('#home').classList.contains('show') || $('#historyDlg').classList.contains('show')) return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && e.target.type !== 'range' && e.target.type !== 'checkbox') return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'Home' || e.key === 'Enter') seek(0);
    else if (e.key === 'r' || e.key === 'R') startRecording();
    else if (e.key === 'Delete' || e.key === 'Backspace') { const [t, c] = findClip(selClipId); if (c && lastFocus === 'clip') { t.clips = t.clips.filter(x => x !== c); selClipId = null; render(); } }
    else if ((e.ctrlKey || e.metaKey) && e.key === 'd') { e.preventDefault(); duplicateClip(); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C')) { e.preventDefault(); copySelection(false); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === 'x' || e.key === 'X')) { e.preventDefault(); copySelection(true); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === 'v' || e.key === 'V')) { e.preventDefault(); pasteClipboard(); }
    else if (e.key === 's' && !e.ctrlKey && !e.metaKey) splitClip();
    else if (e.key === 'm' || e.key === 'M') { $('#metronome').checked = !$('#metronome').checked; }
  });
  // export formats supported by the server
  fetch('/api/info').then(r => r.json()).then(info => {
    const s = $('#exportFmt'); s.innerHTML = '';
    info.formats.forEach(f => s.append(el('option', { value: f, selected: f === 'mp3' }, f.toUpperCase() + (f === 'mp4' ? ' (video)' : ''))));
  }).catch(() => status('Offline mode: WAV export only'));

  requestAnimationFrame(frame);
  status('Ready – Space: play · R: record · Ctrl/Cmd+S: save revision · S: split · Ctrl+D: duplicate · Del: delete');
  // start in the project manager, or reopen the project from the URL (#p=<id>)
  const m = location.hash.match(/p=([0-9a-f]{32})/);
  if (m) openProject(m[1]); else showHome();
}
init();
