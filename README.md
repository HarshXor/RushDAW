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
| **Drum machine** | Metal / hardcore / punk kit: acoustic underground-metal kit: triggered Metal Kick (low thump + beater click), **high-tuned ringing snare**, Ride, China, Crash, hi-hats, ringing toms, light room reverb + velocity variation. Per-part **Tune** (±12 semitones), **Decay** and **Level** controls under each part name. Snare with audible bottom-wire rattle; cymbals with a stick-hit transient for more punch. Step sequencer 1–8 bars. Presets: Metal Double Bass (default), Metal Gallop, Blast Beat, Hammer Blast, Thrash Skank, Hardcore Breakdown, Hardcore Two-Step, D-Beat, Punk Beat, Punk Polka, Pop-Punk Drive, plus Rock, Hip-Hop, Trap, House, Reggaeton. Default tempo 180 BPM |
| **Per-track insert FX** | **Effects** tab / `FX…` button on each mixer strip: EQ, Compressor, Distortion, Filter (LP/HP/BP), Chorus, Tremolo, Delay (BPM sync), Reverb. Unlimited effects per track, on/off bypass, reordering, chain presets: Vocal, Guitar Amp, Metal Guitar, Drum Bus, Bass, Lo-Fi. Included in exports and saved projects |
| **Guitar MIDI** | `+ Guitar` track: sawtooth → amp distortion → cabinet filter. Presets Power Chord / Distortion / Palm Mute / Crunch / Clean Guitar, Drive, Pluck decay, Chord mode (single note or power chord 1-5-8) |
| **Synth / MIDI** | Piano roll C2–C6, presets Keys / Bass / Lead / Pad / Pluck / 808, wave, attack, release, filter cutoff, note length |
| **Tempo** | BPM 40–240, time signature 3/4, 4/4, 6/4, grid snap |
| **Recording** | Record from the mic onto an armed track, **metronome on/off**, count-in, latency compensation |
| **Import** | Import audio/video files (button or drag & drop onto a track). Clips can be dragged to change their position or move to another track, trimmed, split (S), duplicated (Ctrl/Cmd+D) |
| **Mastering** | Master chain EQ → Bus Compressor → Make-up → Limiter → Output, presets (Balanced, Loud Pop, Warm, Bass Boost, Bright), dBFS meter |
| **Export** | WAV, MP3, MP4 (video with waveform visualizer), M4A, AAC, OGG, OPUS, FLAC, with optional normalization |
| **Project manager** | Start screen listing all projects: create (templates Metal demo / Band / Empty), open, rename, search, delete to Trash + restore, import `.rushdaw` |
| **Revision history** | Every 💾 Save (Ctrl/Cmd+S) creates a new revision with an optional note; History lets you open any old revision, restore it (non-destructive, becomes a new revision) or download it. Unsaved changes are auto-saved as a revision when you go back to Projects |

### Keyboard shortcuts
`Space` play/stop · `Ctrl/Cmd+C / X / V` copy / cut / paste the selected clip, track (layer) or drum part · `R` record · `Home`/`Enter` back to start · `S` split · `Ctrl/Cmd+D` duplicate · `Delete` remove clip · `M` metronome toggle · `Shift + drag` on the ruler sets the loop region · double-click a Drum/Synth lane to add a pattern region.

## Data storage

All data stays on your computer in `~/.rushdaw/` (change with `rushdaw --home PATH` or `RUSHDAW_HOME`):

```
~/.rushdaw/
├── db.sql                          # SQLite – important metadata only
└── file/
    └── <project_id>/
        ├── rev-0001.rushdaw        # full project snapshot (tracks, notes, FX, embedded audio)
        ├── rev-0002.rushdaw
        └── ...
```

- `db.sql` table `projects`: id, name, bpm, time signature, created/updated time, latest revision, deleted time (soft delete).
- `db.sql` table `revisions`: project, revision number, note, file name, size, SHA-256, track count, time.
- Project content (including audio) is **not** stored in the database. It lives in the `.rushdaw` files, written atomically.
- Deleting a project only moves it to the Trash. Its files and history stay on disk.

## MCP (edit projects from an AI agent)

RushDAW includes an **MCP server** (Model Context Protocol) so AI assistants and agents can read and edit projects, tracks (layers), drum pads, notes and effects. The transport is **HTTP + SSE only**.

The API key is **optional**. Without `--api-key` MCP is **off** and the DAW works normally. To turn MCP on, start with a key (or set `RUSHDAW_API_KEY`):

```bash
rushdaw --api-key "my-secret-key"
# MCP:  http://localhost:8765/sse  (HTTP+SSE transport, header 'Authorization: Bearer <api key>')
```

- `GET /sse` opens the event stream. The first event, `endpoint`, gives the URL to post to: `/messages?session_id=...`.
- `POST /messages?session_id=...` takes JSON-RPC messages and answers `202 Accepted`. The responses arrive as `message` events on the SSE stream.
- Both endpoints require `Authorization: Bearer <api key>` (otherwise 401).

Example client config:

```json
{
  "mcpServers": {
    "rushdaw": {
      "type": "sse",
      "url": "http://localhost:8765/sse",
      "headers": { "Authorization": "Bearer my-secret-key" }
    }
  }
}
```

| Group | Tools |
|---|---|
| Info / projects | `get_reference`, `list_projects`, `get_project`, `create_project`, `update_project` (title/BPM/time signature), `list_revisions`, `restore_revision`, `delete_project` (to Trash), `set_master` |
| Tracks / layers | `add_track` (audio/drum/synth/guitar), `update_track` (name, volume, pan, mute, solo, EQ, compressor, sends), `delete_track`, `duplicate_track`, `move_track` |
| Effects | `set_track_effects`, `add_effect`, `update_effect` (params / bypass / remove) |
| Drum pads | `set_drum_pads` (turn steps on/off), `set_drum_pattern` (`"x...x..."` strings), `apply_drum_preset`, `clear_drum_pads`, `set_drum_tuning` (pitch/decay/level), `set_pattern_length` |
| Synth / guitar | `set_notes` (e.g. `{"note": "E2", "step": 1, "length": 2}`), `set_synth` |
| Clips / regions | `add_region`, `update_clip`, `delete_clip` |

Every MCP edit is saved as a **new revision** (`MCP: …` in History), so it can always be restored. An editor open in the browser reloads automatically when MCP changes the project. If you have unsaved changes, it shows a warning instead.

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
- `src/rushdaw/storage.py` – SQLite metadata + `.rushdaw` revision files
- `src/rushdaw/model.py` – server-side project model (mirrors the web UI data)
- `src/rushdaw/mcp.py` – MCP tools + JSON-RPC (served over HTTP+SSE by `server.py`, bearer auth)
- `src/rushdaw/static/` – the DAW UI (HTML/CSS/JS, Web Audio engine, offline rendering for export)
