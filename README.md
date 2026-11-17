# drum-loop-browser

A local toolkit for browsing, previewing, curating and sketching with a personal library of MIDI drum loops, built for getting loops into Reason (Kong) and Reaper.

It has two parts:

| Component | What it does | Stack |
|---|---|---|
| [`groom/`](groom/) | Offline command-line app that analyses, normalises, tags and grooms the raw loop library into a clean catalogue | Python 3.13, uv, mido |
| [`dashboard/`](dashboard/) | Local web app for browsing, previewing (FluidSynth), curating and simple whole-bar sequencing | SvelteKit, TypeScript, js-synthesizer |

They share nothing except the git-ignored `data/` folder: groom writes the catalogue there, and the dashboard reads it.

> **Status:** phase 1. `groom run` turns the whole library into a catalogue of normalised loops with checked tempos. The dashboard has a FluidSynth playback spike; the loop browser comes next (phase 2).

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
| `DRUM_LIBRARY_DIR` | `../patterns` | groom |
| `DRUM_SOUNDFONT_DIR` | `../sf2` | groom, dashboard |
| `DRUM_DATA_DIR` | `./data` | groom, dashboard |
| `DRUM_EXPORT_DIR` | `/Users/lucid/_Audio/drum-loops` | dashboard |

## Requirements

- macOS
- [uv](https://docs.astral.sh/uv/) (Python 3.13 is installed by uv as needed)
- [nvm](https://github.com/nvm-sh/nvm) with **Node 24** (pinned in `.nvmrc`; it ships npm 11, which the dashboard needs because npm 10 fails to install its dependency tree)
- FluidSynth from Homebrew (`brew install fluid-synth`), for groom's offline rendering in a later phase

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
uv run groom run                 # groom the library into data/ (about 5 s; first run ~15 s while demos are analysed)
uv run groom report              # per-pack coverage from the last run
uv run groom inspect Angular_7_8 # everything known about a loop (ID or part of its path)
uv run groom paths               # show the locations groom reads and writes
uv run groom fixtures /tmp/fx    # write the synthetic test library
```

`groom run` does the following for every MIDI file:

1. **Names → metadata** using the per-pack rules in [`groom/packs.yaml`](groom/packs.yaml): BPM, meter, bar count, kind (groove, fill, break, ending), style, song/artist.
2. **Bars from the notes** when the name doesn't say: the last hit decides, with a ⅛-beat allowance for slightly late hits. End-of-track markers are ignored (some files put them at beat 400).
3. **Tempo checked against the vendor's WAV demos.** Each BPM candidate (file name, folder, demo name, MIDI tempo) is scored against the demo's onset periodicity. Names disagree surprisingly often, and the MIDI tempo events in particular are mostly wrong.
4. **Normalised copy** in `data/normalised/<loop_id>.mid`: Type 0, 480 PPQ, channel 10, tempo and meter at tick 0, exactly N bars. Timing and velocities are untouched. Additionally:
   - Hits at or just past the loop end wrap to the start.
   - Hits last at least a 16th note, but never into the next hit on the same drum. Most vendor hits have zero length, and synths that honour note-off, FluidSynth included, would cut them to almost nothing.
   - A loop that isn't a whole number of beats long (e.g. one bar of 15/8 = 7.5 beats) is repeated until it is, because DAWs such as REAPER round a MIDI clip up to a whole beat. This affects 138 loops.
5. **Catalogue and reports:** `data/catalogue.sqlite`, plus `data/reports/coverage.csv`, `review.csv` and `previews.csv`.

Each loop's `bpm_check` says how far its tempo can be trusted:

| `bpm_check` | Meaning |
|---|---|
| `confirmed` | A demo's audio agrees with the named BPM |
| `unverified` | Named BPM, but no demo to check it against |
| `conflict` | The audio contradicts a name; all candidates (and the audio's own estimate) are kept for review |
| `audio-only` | No BPM in any name; estimated from the demo; needs review |
| `unknown` | No BPM anywhere and no demo |

`loop_id` is a hash of the normalised notes, so it survives renames and re-runs, and identical files become one loop.

### dashboard

`make dev`, then open <http://localhost:5173/spike>. The spike page loads `lucidrum.sf2` into FluidSynth and plays a hand-made test loop on MIDI channel 10, with kit and tempo controls and a level meter.

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
