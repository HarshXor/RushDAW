# RushDAW 🎛️

A web-based DAW, inspired by **BandLab**, for writing songs, **mixing**, **recording**, and **mastering**.
It's a Python package: the Python side runs a small local server, and the studio runs in your browser using the Web Audio API.

## Installation

```bash
python3 -m pip install .          # from the source folder
# or, once it's on PyPI:
python3 -m pip install rushdaw
```

Start it:

```bash
rushdaw                 # opens http://localhost:8765 in your browser
rushdaw --port 9000 --no-browser
python3 -m rushdaw      # alternative
```

`ffmpeg` is installed automatically through the `imageio-ffmpeg` dependency, so you don't need to install it yourself to export MP3/MP4.

## Features

| Area | Features |
|---|---|
| **Mixing** (main focus) | A mixer channel per track: volume fader (dB), pan, mute/solo, 3-band EQ, compressor, Reverb & Delay sends, peak meter |
| **Drum machine** | Metal / hardcore / punk kit: clicky Metal Kick (for double bass), **Tight / High-Tuned Snare**, China, Crash, hi-hats, toms, clap. Step sequencer 1–8 bars. Presets: Metal Double Bass (default), Metal Gallop, Blast Beat, Hammer Blast, Thrash Skank, Hardcore Breakdown, Hardcore Two-Step, D-Beat, Punk Beat, Punk Polka, Pop-Punk Drive, plus Rock, Hip-Hop, Trap, House, Reggaeton. Default tempo 180 BPM |
| **Per-track insert FX** | **Effects** tab / `FX…` button on each mixer strip: EQ, Compressor, Distortion, Filter (LP/HP/BP), Chorus, Tremolo, Delay (BPM sync), Reverb. Unlimited effects per track, on/off bypass, reordering, chain presets: Vocal, Guitar Amp, Metal Guitar, Drum Bus, Bass, Lo-Fi. Included in exports and saved projects |
| **Guitar MIDI** | `+ Guitar` track: sawtooth → amp distortion → cabinet filter. Presets Power Chord / Distortion / Palm Mute / Crunch / Clean Guitar, Drive, Pluck decay, Chord mode (single note or power chord 1-5-8) |
| **Synth / MIDI** | Piano roll C2–C6, presets Keys / Bass / Lead / Pad / Pluck / 808, wave, attack, release, filter cutoff, note length |
| **Tempo** | BPM 40–240, time signature 3/4, 4/4, 6/4, grid snap |
| **Recording** | Record from the mic onto an armed track, **metronome on/off**, count-in, latency compensation |
| **Import** | Import audio/video files (button or drag & drop onto a track). Clips can be dragged to change their position or move to another track, trimmed, split (S), duplicated (Ctrl/Cmd+D) |
| **Mastering** | Master chain EQ → Bus Compressor → Make-up → Limiter → Output, presets (Balanced, Loud Pop, Warm, Bass Boost, Bright), dBFS meter |
| **Export** | WAV, MP3, MP4 (video with waveform visualizer), M4A, AAC, OGG, OPUS, FLAC, with optional normalization |
| **Project** | Save/Open `.rushdaw` files (including audio) |

### Keyboard shortcuts
`Space` play/stop · `R` record · `Home`/`Enter` back to start · `S` split · `Ctrl/Cmd+D` duplicate · `Delete` remove clip · `M` metronome toggle · `Shift + drag` on the ruler sets the loop region · double-click a Drum/Synth lane to add a pattern region.

## Uploading to PyPI

```bash
python3 -m pip install build twine
python3 -m build                 # creates dist/rushdaw-0.1.0.tar.gz and .whl
python3 -m twine check dist/*
python3 -m twine upload dist/*   # requires a PyPI API token
```

Bump `version` in `pyproject.toml` and `src/rushdaw/__init__.py` for every release. If the name `rushdaw` is already taken on PyPI, change `name` in `pyproject.toml`.

## Development

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
```

## Architecture
- `src/rushdaw/server.py` – standard-library HTTP server (static UI + `/api/export`, `/api/info`)
- `src/rushdaw/export.py` – converts the WAV mixdown to other formats with ffmpeg
- `src/rushdaw/static/` – the DAW UI (HTML/CSS/JS, Web Audio engine, offline rendering for export)
