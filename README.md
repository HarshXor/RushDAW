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

If port 8765 is busy: when RushDAW is already running there, `rushdaw` just opens it in the browser; when another program uses it, the next free port (8766, 8767, …) is used. With an explicit `--port`, a busy port gives a clear error instead.

`ffmpeg` is installed automatically through the `imageio-ffmpeg` dependency, so you don't need to install it yourself to export MP3/MP4.

## Features

| Area | Features |
|---|---|
| **Mixing** (main focus) | A mixer channel per track: volume fader (dB), pan, mute/solo, 3-band EQ, compressor, Reverb & Delay sends, peak meter. **Reorder tracks (layers) by drag & drop**: grab the ⠿ handle (or the track-type row) in a track header and drop it between other tracks – mouse and touch; timeline lanes and mixer strips follow the new order (MCP: `move_track`) |
| **Drum machine** | 10-part acoustic kit: **Kick, Snare, Closed Hi-Hat, Open Hi-Hat, High Tom, Mid Tom, Floor Tom, Crash Cymbal, Ride Cymbal, Pedal Hi-Hat** (open hi-hat is choked by closed/pedal hi-hat). Default kit tuning is a **rock / metal** tuning (fat ~190 Hz snare, low toms ~170 / 128 / 88 Hz, clicky metal kick). Per-part tuning under each part name, all in **percent** (100% = default): **Tune 25–400%** (−2 … +2 octaves), **Decay 10–400%**, **Volume off–200%**. Light room reverb + velocity variation. Step sequencer 1–8 bars. Presets: Metal Double Bass (default), Metal Gallop, Blast Beat, Hammer Blast, Thrash Skank, Hardcore Breakdown, Hardcore Two-Step, D-Beat, Crust D-Beat, Punk Beat, Punk Polka, Pop-Punk Drive, plus Four on the floor, Rock, Hip-Hop, Trap, Reggaeton. Projects with the older 9-part kit are converted automatically. Default tempo 180 BPM |
| **Per-track insert FX** | **Effects** tab / `FX…` button on each mixer strip: EQ, Compressor, Distortion, **Guitar Amp** (input gain → drive → cabinet tone → level) – both with an **HM-2 style heavy stage** (Boss Heavy Metal "Swedish chainsaw": tight low cut, a second asymmetric clipping stage and the chainsaw EQ with big bumps at ~100 Hz and ~1.3 kHz) that grows with **Drive** above ~0.35, so light crunch / drum-bus saturation stays mild, Filter (LP/HP/BP), Chorus, Tremolo, Delay (BPM sync), Reverb. Unlimited effects per track, on/off bypass, reordering, chain presets: Vocal, Guitar Amp, Metal Guitar, Drum Bus, Bass, Lo-Fi. Included in exports and saved projects |
| **Guitar & Bass MIDI** | `+ Guitar` / `+ Bass` tracks play **real recorded instruments** (sampled clean electric guitar, steel acoustic guitar, finger and pick electric bass), not a synth. Defaults: **Clean Guitar** and **Finger Bass**. Presets: Clean / Acoustic / Crunch / Distortion / Power Chord / Palm Mute Guitar (amped presets put a **Guitar Amp** effect into *that layer's* Effects chain – visible and editable there, independent per layer; switching back to a clean preset removes it), Finger / Pick Bass. Small random timing / dynamics / tuning variation like a real player. Long notes: **drag in the piano roll** to draw one note over many steps, drag a note to change its length, click it to delete. Each instrument has a proper note envelope – **Decay** (seconds the pluck takes to fall), **Sustain** (level a held note keeps; the recording has a seamless sustain loop, so long notes keep ringing) and **Release** (fade after the note), with a live envelope graph. Palm Mute plays the **real palm-muted guitar recording** (Sustain 0, dies away). Every recorded instrument also has **velocity → tone** (soft notes darker, hard notes brighter) and **round-robin** (a repeated note alternates between neighbouring recordings, so it is never the identical sample twice). Controls: Instrument, Decay, Sustain, Release, Tone, Chord (single / power chord). Engine can also be switched to *Modeled string* or *Synth*. Older guitar/bass tracks are upgraded automatically |
| **Synth / MIDI** | Piano roll C2–C6. Natural recorded presets **Piano** (default), **Electric Piano**, **Strings**; electronic presets Keys / Synth Bass / Lead / Pad / Pluck / 808, wave, attack, release, filter cutoff, note length |
| **Tempo** | BPM 40–240, time signature 3/4, 4/4, 6/4, grid snap |
| **Recording** | Record from the mic onto an armed track, **metronome on/off**, count-in, latency compensation. **Punch-in replace**: a new take overwrites the old audio on that track exactly where it was recorded (old clips there are deleted / trimmed / split), so only the newest take is heard; takes are numbered Take 1, 2, 3 …. **Input monitoring (🎧, on/off per audio track)**: hear the mic live through the track's effects, mixer and master while recording or practising; it is not saved in the project, so a project never opens with the mic live (use headphones to avoid feedback) |
| **Import** | Import audio/video files (button or drag & drop onto a track). Clips can be dragged to change their position or move to another track, trimmed from either edge, split (S), duplicated (Ctrl/Cmd+D) |
| **Mastering** | Chain: input trim → low cut (HPF) → 3-band EQ (gain + frequency, mid Q) → bus compressor (threshold, ratio, knee, attack, release) → saturation (tape-style) → make-up → stereo width (M/S, 0 = mono) → limiter (ceiling, release) → output → true-peak clipper. Built-in presets: Default, Flat (off), Balanced, Loud Pop, Warm, Bass Boost, Bright, Punk / Crust, Metal, Acoustic / Natural, Vocal / Podcast, Lo-Fi Tape, Atmospheric, Shoegaze, Melodic, Hardcore Punk, Punk, Rock. Master output fader: −20 … +20 dB (0 dB centred) (beyond the ceiling the clipper flattens peaks — louder but more distorted). **The chosen preset stays the project's preset**: edit any value and the name shows **“Metal (custom)”** (↺ Revert goes back); with no preset it is just **“Custom”**. **Save as…** stores your own presets (SQLite, shared by all projects; ⟳ Update / 🗑 Delete), **⬇ Export** / **⬆ Import** as `.rushmaster.json` files (import never overwrites: clashing names get “(2)” / “(imported)”). Input trim and the reverb/delay sends are not part of a preset. **Loudness (BS.1770 / EBU R128)**: integrated + short-term LUFS, loudness range, true peak (4× oversampled) of the export render; **Match** sets the input trim so the export hits a target (−14 / −16 / −11 / −9 / −23 LUFS). Exports never exceed the ceiling in true peak |
| **Clip selection** | The selected clip / region gets a translucent aqua block over the whole clip (plus outline); hovering shows a light block |
| **Fade in / fade out (per region)** | Right-click a clip or region → **◢◣ Fade in / out…** opens a dialog: a preview of the region with **two round handles to drag** (left = fade in, right = fade out), a **Volume** slider (region volume 0–200%), and **Fade in** / **Fade out** sliders with number boxes in **seconds**. The maximum is the region's own length, so a fade can cover the whole region; fades follow the region if the tempo changes. Reset / ▶ Preview / Cancel / Done. On the timeline you can also drag the small round handles at the clip's top corners. **✕ Remove fades** clears them. MCP: `update_clip` with `fade_in_sec` / `fade_out_sec` (seconds, same limits as the dialog) and `volume_percent`; `fade_in_beats` / `fade_out_beats` also work; `get_project` lists `fade_in_sec`, `fade_out_sec`, `volume_percent`, `length_sec` per clip |
| **Export one region** | Right-click a region or clip → **⬇ Export this region…** → file name + format (WAV, MP3, …) → only that region is rendered (its track's effects, mixer, fades, region volume and the master chain, plus the reverb/delay tail), even if the track is muted |
| **Download (song audio)** | **Download** renders the song: WAV, MP3, MP4 (video with waveform visualizer), M4A, AAC, OGG, OPUS, FLAC. The export renders through the same audio graph as studio playback (same mixer, FX, mastering, true-peak ceiling guard and sample rate), so it sounds like what you hear. Muted / soloed tracks are respected, saved or not. Optional **Normalize** (off by default) raises the level to the master ceiling. The project list has a **⬇ Download** button (format picker) that renders the latest saved revision without opening the editor |
| **Unsaved changes** | Leaving the editor with unsaved changes (☰ Projects, browser Back/Forward or a URL change, History → Open / Restore) asks **Save / Don't save / Cancel** (Esc = Cancel). Save stores a new revision, Don't save discards the changes since the last save, Cancel stays. Every page change starts fresh: leaving the editor clears it, the project list is re-queried from the server and a project is always re-loaded from the server when opened |
| **Export / Import project (.zip)** | **Export** (editor toolbar, project card, or 📦 per revision in History) creates one `<name>.rushdaw.zip`: `project.rushdaw` (the project; audio entries point to files) + an `audio/` folder with every recorded / imported audio file + `README.txt`. **Import (.zip / .rushdaw)** on the Projects page brings the project *and all its audio* back in one step – no files to move by hand (a re-zipped folder or a plain `.rushdaw` also works). The editor's Export packs the current state, saved or not |
| **Project manager** | Start screen listing projects: create (templates Metal demo / Band / **D-Beat / Crust Punk** / Empty), open, rename, delete to Trash + restore, import. **Search, filters and pagination run on the server (SQLite)**: text search in names *and* revision notes, date range on *Updated* or *Created*, BPM range, sort (last updated, created, name, BPM, revisions; asc/desc), 12–96 per page with page buttons – only one page is loaded at a time. API: `GET /api/projects?q=&date_field=updated|created&from=YYYY-MM-DD&to=&bpm_min=&bpm_max=&sort=&order=&page=&per_page=&deleted=1` |
| **Revision history** | Every 💾 Save (Ctrl/Cmd+S) creates a new revision with an optional note; History lets you open any old revision, restore it (non-destructive, becomes a new revision) or download it. Unsaved changes are auto-saved as a revision when you go back to Projects |

### Keyboard shortcuts
`Space` play/stop · **`Ctrl/Cmd+Z` undo · `Ctrl/Cmd+Shift+Z` (or `Ctrl+Y`) redo** (also the ↶ Undo / ↷ Redo toolbar buttons; up to 100 steps per opened project, a whole slider/knob drag is one step, audio of undone recordings is kept; while typing in a text field the field's own undo is used) · **Multiple selection**: `Shift`/`Ctrl`/`Cmd` + click clips / regions to add or remove them (`Ctrl/Cmd+A` = every clip of the selected track); drag any selected clip to move them all; right-click → **Merge** (or `Ctrl/Cmd+J`) joins the selected regions of one track into one region – every pad / note stays exactly where it was, gaps stay empty; selected audio clips are mixed into one audio clip (gain and fades baked in); MCP: `merge_regions` · `Ctrl/Cmd+C / X / V` copy / cut / paste the selected clip(s), track (layer) or drum part – several clips keep their spacing and their tracks · `R` record · `Home`/`Enter` back to start · `S` split · `Ctrl/Cmd+D` duplicate · `Delete` remove clip · `M` metronome toggle · **Fine grid**: the ruler shows bar, beat and small grid ticks; with **Snap** on, moving / resizing regions and clips, multi-selection drags, ruler clicks and loop edges snap to the small ticks (1/16 note at normal zoom, 1/8 or 1/4 note when zoomed out – the current grid is shown next to Snap), so a region moves note by note instead of jumping; Snap off = free placement · `Shift + drag` on the ruler sets the loop region · double-click a Drum/Synth lane to add a pattern region.

**Mute / solo.** Muted tracks are silent. When any track is soloed, every soloed track plays and all other tracks are silent (shown dimmed in the track header, lane and mixer). Mute wins over solo. The same rule applies to playback, Download, export and MCP (`get_project` shows each track's `audible`). **Download on the project list renders the last saved revision**: each project card shows its saved mute / solo (e.g. "Solo: Drums, Bass · Muted: Guitar"), and the revision's mute/solo summary is stored in SQLite (`revisions.mix`, also in MCP `list_projects` / `list_revisions`). Choosing "Don't save" when leaving the editor discards unsaved mute / solo too.

**Long notes are one note, never a loop.** Lengthening a MIDI note (not drums) makes ONE longer note: guitar, bass and piano ring and **decay** naturally (the real recording, no loop – a held note dies away like the instrument); vocal/choir, strings and synths **sustain** evenly ("luuuuu", not "luu-luu-luu"): sustained recordings loop over their steadiest ~1.2–2.2 s section instead of a 0.5 s slice, rebuilt as a granular sustain: 120 ms grains taken at random places of the steadiest section, aligned to whole pitch periods, so the choir's own vowel drift no longer repeats every loop ("oooo", not "ou-ou-ou") and the level stays even, in playback and in Download/export, and detuned synth layers sit low enough not to beat.

**One pitch = one voice.** A note on a pitch ends where the next note of the same pitch starts and duplicates play once (piano roll, playback and MCP `set_notes` all follow this). Held ensemble recordings (choir, voice, strings) are auto-tuned per recording at load and never round-robin, so a sung note stays one voice.

**MIDI regions are linear, not loops.** Each MIDI region (drum, guitar, bass, synth) stores its own pads/notes for its whole length: a pad sounds exactly where it is placed and nothing repeats, so deleting one pad deletes only that pad. Extending a region (drag its right edge, *Length* in the Editor, or right-click → *Extend by 1 empty bar*) adds **empty** bars; shortening cuts the end. **Both edges resize**: drag the **left edge** to resize from the start (shrinking cuts the first steps, extending adds empty steps in front; every pad/note keeps its position in the song; audio clips reveal/hide the start of the recording). MCP: `update_clip(trim_start_beats=…)`. Copy/paste, `Ctrl/Cmd+D` duplicate and `S` split create independent copies. The Editor shows the whole region with bar numbers (B1, B2, …), *Region n/m · bar x* with ◀ ▶, **+ Empty bar**, **⧉ Duplicate region** and **Apply to all regions**. Older projects are converted automatically (looping regions are written out once, so they sound the same).

**Right-click menus.** Right-click an empty spot of a lane: MIDI tracks → *Add empty bar / 2 / 4 bars here*, *Add copy of the selected region here*, *Paste here*; audio tracks → *Add audio here (import file)…*, *Record here*, *Paste here*. Right-click a region/clip → edit, extend / shorten by a bar, duplicate, split at playhead, delete. Double-clicking an empty spot of a MIDI lane also adds an empty bar.

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
| Info / projects | `get_reference`, `list_projects` (search / date + BPM filters / sort / pagination, same as the Projects page), `export_project` (project package .zip with audio/ – written on the server + download URL), `import_project` (.zip or .rushdaw from a path or base64), `get_project`, `create_project`, `update_project` (title/BPM/time signature), `list_revisions`, `restore_revision`, `delete_project` (to Trash), `set_master` (preset by name incl. your saved ones, or params; returns the label “X” / “X (custom)” / “Custom”) |
| Mastering presets | `list_master_presets`, `save_master_preset` (from a project's master and/or params), `delete_master_preset`, `export_master_preset` (`.rushmaster.json` content, optional server path), `import_master_presets` (JSON or server path) |
| Tracks / layers | `add_track` (audio/drum/synth/guitar), `update_track` (name, volume, pan, mute, solo, EQ, compressor, sends), `delete_track`, `duplicate_track`, `move_track` |
| Effects | `set_track_effects`, `add_effect`, `update_effect` (params / bypass / remove) |
| Drum pads | `set_drum_pads` (turn steps on/off), `set_drum_pattern` (`"x...x..."` strings), `apply_drum_preset`, `clear_drum_pads`, `set_drum_tuning` (`tune_percent` / `decay_percent` / `volume_percent`, or raw pitch / decay / level / `volume_db`), `set_pattern_length` |
| Synth / guitar | `set_notes` (e.g. `{"note": "E2", "step": 1, "length": 2}`), `set_synth` |
| Clips / regions | `add_region` (`empty: true` for a blank bar, `copy_from` another region, or the track pattern written out), `update_clip`, `delete_clip`. Pattern tools (`set_drum_pads`, `set_drum_pattern`, `apply_drum_preset`, `clear_drum_pads`, `set_pattern_length`, `set_notes`) take an optional `clip_id` to edit only that region; without it they edit the whole track (all regions). Regions are linear: `update_clip length_beats` / `set_pattern_length` extend with empty steps or cut the end |

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

## Third-party sounds

The guitar, bass, piano, strings and choir recordings in `src/rushdaw/static/samples/` come from the **FluidR3_GM** SoundFont by Frank Wen (MP3 renders from [midi-js-soundfonts](https://github.com/gleitz/midi-js-soundfonts)), licensed under [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/us/). See `src/rushdaw/static/samples/NOTICE.txt`.

### Vocal MIDI (voice: "hooo" / "haaa")
Click **+ Vocal MIDI** to add a sung-voice layer played from the piano roll. Drag across pads to make one long, sustained note (same as guitar/bass).
- Presets: **Choir Aah** (default), **Choir Ooh**, **Choir Ohh** – real recorded choir (FluidR3_GM, sustain-looped for long notes); **Solo Hoo**, **Solo Haa** – single voice by formant synthesis (engine `voice`; no free solo-voice recordings). Older choir tracks are upgraded to the recordings automatically.
- Editor controls: Vowel (Aah / Eeh / Iih / Ohh / Ooh), Voices (1 = solo, 2-6 = choir), Breath, Vibrato, Attack, Decay, Sustain, Release.
- New track starts with the "Choir Space" effect chain (EQ, Chorus, Reverb), visible and editable in the Effects tab.
- New effect **Vocal Formant** (vowel a/e/i/o/u, formant shift, mix) turns any layer into an "aah"/"ooh" sound.
- MCP: `add_track type=vocal`, `set_synth` with `engine: voice`, `vowel`, `voices`, `breath`, `vibrato`; `add_effect type=formant`.

### Natural drums: recorded kit, velocity and feel
- Drum tracks play a **recorded acoustic kit** (MuldjordKit, CC-BY 4.0): 3 velocity layers x 3 different hits per part, so repeated hits never sound identical. Editor → **Kit**: *Acoustic (recorded)* (default) or *Synth kit*. Tune / Decay / Volume per part still work.
- **Velocity per pad and note**: choose the velocity for new pads (Accent 100%, Normal 80%, Soft 60%, Ghost 30%); right-click or Alt+click a pad/note to cycle it. Softer pads are drawn dimmer and play a softer recording (ghost notes, accents).
- **Feel** per layer: Humanize (random timing in ms; drums add a drummer feel: snare slightly behind, hats slightly ahead), Swing, Push / lay back. New drum tracks start with Humanize 6 ms.
- MCP: `set_drum_pads velocity` (1-127), pattern strings `x` = 100%, `o` = soft, `g` = ghost, `set_notes` note `velocity`, `update_track humanize_ms / swing / push_ms`.

## Development rule: UI and MCP stay in sync

Every feature that changes project data in the browser must also be available through MCP in the same change
(Python model `src/rushdaw/model.py` + tool in `src/rushdaw/mcp.py` + a test). `tests/test_mcp.py` enforces it:
`ModelSyncTest` compares presets / drum kit / constants between `app.js` and the Python model, and
`test_every_ui_clip_setting_has_an_mcp_param` fails as soon as `app.js` writes a new clip/region field that has no MCP parameter.
