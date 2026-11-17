# drum-loop-browser

A local toolkit for browsing, previewing, curating and sketching with a personal library of MIDI drum loops, built for getting loops into Reason (Kong) and Reaper.

It has two parts:

| Component | What it does | Stack |
|---|---|---|
| [`groom/`](groom/) | Offline command-line app that analyses, normalises, tags and grooms the raw loop library into a clean catalogue | Python 3.13, uv, mido |
| [`dashboard/`](dashboard/) | Local web app for browsing, previewing (FluidSynth), curating and simple whole-bar sequencing | SvelteKit, TypeScript, js-synthesizer |

They share nothing except the git-ignored `data/` folder: groom writes the catalogue there, and the dashboard reads it.

> **Status:** phase 3. `groom run` turns the whole library into a catalogue of normalised loops with checked tempos, rhythm features, tags and similar loops, and the dashboard browses, filters and auditions them through FluidSynth or a MIDI output. Curation comes next.

## Folder layout

The repo expects these siblings, none of which are committed:

```
midi-drums/
├── drum-loop-browser/   ← this repo
│   └── data/            ← generated: catalogue, normalised MIDI, kits, remaps (git-ignored)
├── patterns/            ← the loop library (read-only, licensed: never commit)
└── sf2/                 ← SoundFonts, including lucidrum.sf2 (read-only)
```

Saved loops from the dashboard go to `/Users/lucid/_Audio/drum-loops`, where Reason and Reaper pick them up.

| Variable | Default | Used by |
|---|---|---|
| `DRUM_LIBRARY_DIR` | `../patterns` | groom, dashboard (vendor demos only) |
| `DRUM_SOUNDFONT_DIR` | `../sf2` | groom, dashboard |
| `DRUM_DATA_DIR` | `./data` | groom, dashboard |
| `DRUM_EXPORT_DIR` | `/Users/lucid/_Audio/drum-loops` | dashboard |

## Requirements

- macOS
- [uv](https://docs.astral.sh/uv/) (Python 3.13 is installed by uv as needed)
- [nvm](https://github.com/nvm-sh/nvm) with **Node 24** (pinned in `.nvmrc`; it ships npm 11, which the dashboard needs because npm 10 fails to install its dependency tree)
- FluidSynth from Homebrew (`brew install fluid-synth`), only for `groom run --render`

## Getting started

```sh
nvm install    # first time only: installs the Node version from .nvmrc
nvm use        # in each new shell
make setup     # install both components and enable the pre-commit guard
make test      # groom (pytest) + dashboard (vitest)
make lint      # ruff, mypy, prettier, eslint, svelte-check
make e2e       # Playwright smoke tests
make dev       # dashboard at http://localhost:5173
```

### groom

```sh
cd groom
uv run groom run                 # groom the library into data/ (about 7 s; the first run takes ~2 min while demos are analysed)
uv run groom run --render        # also render every loop with FluidSynth and flag silent or clipping ones
uv run groom report              # per-pack coverage from the last run
uv run groom inspect Angular_7_8 # everything known about a loop (ID or part of its path)
uv run groom paths               # show the locations groom reads and writes
uv run groom fixtures /tmp/fx --rules-out /tmp/fx.yaml   # write the synthetic test library and its rules
uv run groom run --rules /tmp/fx.yaml                     # groom with other pack rules (default: packs.yaml)
```

`groom run` does the following for every MIDI file:

1. **Names → metadata** using the per-pack rules in [`groom/packs.yaml`](groom/packs.yaml): BPM, meter, bar count, kind (groove, fill, break, ending), style, song/artist.
2. **Bars from the notes** when the name doesn't say: the last hit decides, with a ⅛-beat allowance for slightly late hits. End-of-track markers are ignored (some files put them at beat 400).
3. **Tempo checked against the vendor's WAV demos.** Each BPM candidate (file name, folder, demo name, MIDI tempo) is scored against the demo's onset periodicity. Names disagree surprisingly often, and the MIDI tempo events in particular are mostly wrong.
4. **Tempo from aligning MIDI with audio** where names leave it in doubt: the loop's hits are slid along the demo's onsets at each trial BPM, and the best-fitting BPM wins. It counts as strong only when the demo's length also fits a whole number of bars at a whole BPM within a beat of it. (On 67 demos with a tempo in their name, every strong match gave that tempo.) In packs whose demos each play one loop (`tempo: per-loop` in `packs.yaml`, e.g. Long Loops), the loop a demo clearly plays is matched, and its siblings take the tempo of the demo they line up with best, as an unchecked suggestion.
5. **Normalised copy** in `data/normalised/<loop_id>.mid`: Type 0, 480 PPQ, channel 10, tempo and meter at tick 0, exactly N bars. Timing and velocities are untouched. Additionally:
   - Hits at or just past the loop end wrap to the start.
   - Hits last at least a 16th note, but never into the next hit on the same drum. Most vendor hits have zero length, and synths that honour note-off, FluidSynth included, would cut them to almost nothing.
   - A loop that isn't a whole number of beats long (e.g. one bar of 15/8 = 7.5 beats) is repeated until it is, because DAWs such as REAPER round a MIDI clip up to a whole beat. This affects 138 loops.
6. **Analysis:** rhythm features (kit pieces, density, swing, triplets, syncopation, linear playing, ghost notes, backbeat, half time, four on the floor), tags from names (style, feel) and from features (`swung`, `triplet`, `linear`, `busy`, `sparse`, `ride`, `toms`, `ghost-notes`, `four-on-the-floor`, `half-time`, `odd-meter`), and the 10 most similar loops in the same meter.
7. **QC:** near-duplicates (the same hits as another loop, ignoring velocity and repeats) and notes with no sample in the preview SoundFont's Standard kit go to review; so do silent or clipping renders with `--render`.
8. **Catalogue and reports:** `data/catalogue.sqlite`, plus `data/reports/coverage.csv`, `review.csv` and `previews.csv`.

Each loop's `bpm_check` says how far its tempo can be trusted:

| `bpm_check` | Meaning |
|---|---|
| `confirmed` | A demo's audio agrees with the named BPM |
| `audio-matched` | No BPM in any name, but the MIDI lines up clearly with a demo |
| `unverified` | Named BPM with no demo to check it against, or (`bpm_source = sibling-demo`) the tempo of a demo of another loop in the group |
| `conflict` | The audio contradicts a name; all candidates (and the audio's own estimate) are kept for review |
| `audio-only` | No BPM in any name; estimated from the demo; needs review |
| `unknown` | No BPM anywhere and no demo |

`loop_id` is a hash of the normalised notes, so it survives renames and re-runs, and identical files become one loop.

### dashboard

`make dev`, then open <http://localhost:5173>. The dashboard reads `data/catalogue.sqlite` (run `groom run` first) and refuses to start against a catalogue with a different schema version.

- **Find:** pick a pack or *Needs review* in the sidebar, search (name, song, artist, style, pack, path, tags such as `swung` or `linear`, `7/8`, `120bpm`), and filter by BPM range, meter and kind. Column headers sort.
- **Listen:** click a loop's name to play it. FluidSynth loads `lucidrum.sf2` on the first play. Loops play at their own BPM (or the global tempo, if *Loop's own tempo* is off or the BPM is unknown), repeat gaplessly, and with *Switch on the bar* the next loop takes over on the downbeat. *Fills play once* plays a fill a single time, then returns to the groove that was playing.
- **See:** the inspector shows the drum grid (darker = louder, with a playhead), the tempo check, tags, review issues, similar loops (click to open one), and the vendor's WAV demo for the group.
- **Kits and outputs:** choose any lucidrum kit (SFX is left out: it has no kick or snare). *Enable MIDI out* sends the same notes to a Web MIDI port, such as an IAC bus into Reason or REAPER, on channel 10 by default (Chrome; Safari has no Web MIDI).

| Key (in the loop list) | Does |
|---|---|
| ↑ ↓, Page Up/Down, Home/End | Move; while playing, the new loop takes over |
| Space | Play or stop the selected loop |
| Enter | Play the selected loop |
| Escape | Stop |
| `/` (anywhere) | Jump to search |

API routes (localhost only): `GET /api/loops`, `/api/loops/<id>` (with notes), `/api/midi/<id>` (normalised file), `/api/preview/<group>/<n>` (WAV demo, with byte ranges) and `/api/soundfont/<name>.sf2`.

`/spike` is the phase 0 FluidSynth check: a hand-made test loop with kit and tempo controls and a level meter.

The Playwright tests (`make e2e`) build their own catalogue from groom's synthetic fixtures (`dashboard/scripts/fixture-catalogue.mjs`, needs uv), so they never touch the real library.

## SoundFont

Previews use `../sf2/lucidrum.sf2`. Its 12 kits were moved to General MIDI drum bank 128 with Roland GS program numbers by [`scripts/patch_lucidrum_banks.py`](scripts/patch_lucidrum_banks.py) (the original is kept as `lucidrum.orig.sf2`), so a file that sends no program change plays the Standard kit:

| Program | Kit | Program | Kit |
|---|---|---|---|
| 0 | Standard | 25 | TR-808 |
| 1 | mash | 32 | Jazz |
| 2 | Warehouse Perc | 40 | Brush |
| 8 | Room | 48 | Orchestral |
| 16 | Power | 56 | SFX |
| 24 | Electronic | 127 | CM-64/32L |

## Keeping licensed content out of git

The loop library's license forbids redistribution in any form, including edited or re-rendered versions. So:

- `.gitignore` excludes `patterns/`, `data/`, MIDI, audio, SoundFonts and databases.
- A pre-commit hook (`.githooks/pre-commit`, enabled by `make setup`) rejects those files even if they are force-added.
- Tests and CI use only synthetic fixtures generated in code (`groom/src/groom/fixtures.py`, `dashboard/src/lib/audio/fixtureLoop.ts`).
