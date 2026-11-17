"""Synthetic test library.

Generates a tiny, hand-authored stand-in for the real loop library: one or two files per naming
scheme, with the same structural quirks (96 vs 15,360 PPQ, Type 0 vs Type 1, notes on channel 1,
tempo events that disagree with the folder name, end-of-track far past the last note, lengths a
fraction of a beat short of whole bars) plus click-track WAV demos at known tempos.
Nothing here is derived from the licensed library; the patterns are generic and generated in code.

Each ``FixtureLoop`` records what the grooming pipeline *should* conclude about the file.
"""

import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mido
import numpy as np
import numpy.typing as npt
import soundfile as sf

KICK, SNARE, CLOSED_HAT, OPEN_HAT, CRASH = 36, 38, 42, 46, 49
TOMS = (50, 48, 47, 45, 43, 41)
DEMO_SR = 22050

Kind = Literal["groove", "fill"]
BpmCheck = Literal["confirmed", "unverified", "conflict", "audio-only", "unknown"]


@dataclass(frozen=True)
class FixtureLoop:
    rel_path: str
    pack: str
    bpm: int | None  # BPM the pipeline should settle on (None = unknown)
    bpm_check: BpmCheck
    meter: tuple[int, int]
    bars: int
    kind: Kind
    ppq: int = 96
    midi_type: Literal[0, 1] = 0
    file_bpm: float | None = None  # set_tempo written in the file (may be wrong, like the library)
    short_by: float = 0.25  # beats short of whole bars where the last note ends
    eot_beats: float | None = None  # end-of-track position, if far past the notes


@dataclass(frozen=True)
class FixtureDemo:
    rel_path: str
    loop: str  # rel_path of the fixture loop whose pattern the demo plays
    bpm: float  # tempo the demo is rendered at
    repeats: int = 4


FIXTURES: tuple[FixtureLoop, ...] = (
    # BPM prefix on the file name, plus song/artist/variant; no demo
    FixtureLoop("BpmPrefix_MIDILoops/MIDI Loops/118_TestSong_TestArtist1.mid",
                "BpmPrefix_MIDILoops", 118, "unverified", (4, 4), 4, "groove"),
    # BPM + meter in the folder; the file's tempo event is wrong; the demo confirms the folder
    FixtureLoop("BpmMeterFolder_MIDIDrumLoops/100 7:8 Angles/Angles_7_8_Grv_3.mid",
                "BpmMeterFolder_MIDIDrumLoops", 100, "confirmed", (7, 8), 2, "groove",
                ppq=15360, midi_type=1, file_bpm=91, eot_beats=400),
    FixtureLoop("BpmMeterFolder_MIDIDrumLoops/100 7:8 Angles/Angles_7_8_Fill_1.mid",
                "BpmMeterFolder_MIDIDrumLoops", 100, "confirmed", (7, 8), 1, "fill",
                ppq=15360, midi_type=1, file_bpm=91, eot_beats=400),
    # BPM + style in the folder; no demo
    FixtureLoop("BpmStyleFolder_MIDILoops/150_Grit/Linear_Grit_12.mid",
                "BpmStyleFolder_MIDILoops", 150, "unverified", (4, 4), 2, "groove"),
    # Meter + style in the folder, tempo only in the MIDI file; the demo confirms it
    FixtureLoop("MeterStyleFolder_DrumLoops_MIDI/9:8_Woods/NineEight_Grv_2.mid",
                "MeterStyleFolder_DrumLoops_MIDI", 112, "confirmed", (9, 8), 2, "groove",
                ppq=15360, midi_type=1, file_bpm=112, eot_beats=400),
    # Meter as a word in the folder, no tempo anywhere; the demo gives an audio-only estimate
    FixtureLoop("MeterWordFolder_DrumLoops_MIDI/Loops/FiveFour/FiveFour_Odd_04.mid",
                "MeterWordFolder_DrumLoops_MIDI", 120, "audio-only", (5, 4), 2, "groove"),
    # Style + bar count in the folder, no tempo anywhere, no demo
    FixtureLoop("BarsFolder_MIDILoops/MIDI Loops/Test Groove - 8 Bars/TestGroove_8Bars_07.mid",
                "BarsFolder_MIDILoops", None, "unknown", (4, 4), 8, "groove"),
    FixtureLoop("BarsFolder_MIDILoops/MIDI Loops/In Three - 4 Bars/InThree_4Bars_02.mid",
                "BarsFolder_MIDILoops", None, "unknown", (3, 4), 4, "groove"),
    # Fill type, feel and bar count in the path
    FixtureLoop("Fills_MIDILoops/Swung Fills/2 Bar Fills/Fill - Test Roll.mid",
                "Fills_MIDILoops", None, "unknown", (4, 4), 2, "fill"),
    # Tempo only in a demo file name; the demo's audio confirms it
    FixtureLoop("PreviewBpm_MIDILoops/MIDI Loops/HeavyTest/HeavyTest_05.mid",
                "PreviewBpm_MIDILoops", 96, "confirmed", (4, 4), 2, "groove"),
)  # fmt: skip

DEMOS: tuple[FixtureDemo, ...] = (
    FixtureDemo("BpmMeterFolder_MIDIDrumLoops/Demos/Angles_MIDI_Demo.wav",
                FIXTURES[1].rel_path, 100),
    FixtureDemo("MeterStyleFolder_DrumLoops_MIDI/Demos/NineEight_Woods_MIDI_Demo.wav",
                FIXTURES[4].rel_path, 112),
    FixtureDemo("MeterWordFolder_DrumLoops_MIDI/Demos/Five Four - Odd Meter Drums.wav",
                FIXTURES[5].rel_path, 120),
    FixtureDemo("PreviewBpm_MIDILoops/Demos/PreviewBpm HeavyTest 96bpm.wav",
                FIXTURES[9].rel_path, 96),
)  # fmt: skip

FIXTURE_RULES = """\
packs:
  BpmPrefix_MIDILoops:
    group: '^MIDI Loops$'
    file: '^(?P<bpm>\\d+)_(?P<song>[^_]+?)(?:_(?P<artist>.+?))?(?P<variant>\\d+)?$'
  BpmMeterFolder_MIDIDrumLoops:
    group: '^(?P<bpm>\\d+) (?P<num>\\d+):(?P<den>\\d+) (?P<style>.+)$'
    file: '^(?P<key>[A-Za-z]+)_\\d+_\\d+_(?P<kind>Grv|Brk|Fill)_(?P<variant>\\d+)$'
    preview: {pattern: '^(?P<key>[A-Za-z]+)_MIDI_Demo$', scope: group, match_on: key}
  BpmStyleFolder_MIDILoops:
    group: '^(?P<bpm>\\d+)_(?P<style>.+)$'
    file: '^Linear_(?P<key>.+)_(?P<variant>\\d+)$'
  MeterStyleFolder_DrumLoops_MIDI:
    group: '^(?P<num>\\d+):(?P<den>\\d+)_(?P<style>.+)$'
    file: '^(?P<meter>[A-Za-z]+?)_(?P<kind>Grv|Fill)_?(?P<variant>\\d+)$'
    preview: {pattern: '^[A-Za-z]+_(?P<key>[A-Za-z]+)_MIDI_Demo$', scope: group, match_on: style}
  MeterWordFolder_DrumLoops_MIDI:
    group: '^Loops/(?P<meter>[A-Za-z]+)$'
    file: '^[A-Za-z]+_Odd_(?P<variant>\\d+)$'
    preview: {pattern: '^(?P<key>.+?) - Odd Meter Drums$', scope: group, match_on: meter}
  BarsFolder_MIDILoops:
    group: '^MIDI Loops/(?P<style>.+) - (?P<bars>\\d+) Bars$'
    file: '^(?P<key>.+?)_\\d+Bars?_(?P<variant>\\d+)$'
  Fills_MIDILoops:
    group: '^(?P<feel>Swung|Straight) Fills/(?P<bars>\\d+) Bar Fills$'
    file: '^Fill - (?P<key>.+)$'
    defaults: {kind: fill}
  PreviewBpm_MIDILoops:
    group: '^MIDI Loops/(?P<style>[^/]+)$'
    file: '^(?P<key>.+)_(?P<variant>\\d+)$'
    preview: {pattern: '^PreviewBpm (?P<key>.+) (?P<bpm>\\d+)bpm$', scope: group, match_on: style}
"""


def _pattern(loop: FixtureLoop) -> list[tuple[float, int, int]]:
    """Return (beat, note, velocity) hits for a simple generic beat or fill."""
    num, den = loop.meter
    accent = zlib.crc32(loop.rel_path.encode()) % 16  # keeps every fixture's content distinct
    unit = 4 / den  # beats per meter unit (quarter or eighth)
    hits: list[tuple[float, int, int]] = []
    for b in range(loop.bars):
        start = b * num * unit
        is_fill_bar = loop.kind == "fill" and b == loop.bars - 1
        for u in range(num):
            t = start + u * unit
            if is_fill_bar:
                hits.append((t, TOMS[u % len(TOMS)], 100 - 5 * (u % 4)))
                continue
            hits.append((t, CLOSED_HAT, (96 if u % 2 == 0 else 72) + accent))
            if u == 0:
                hits.append((t, KICK, 110))
            if u == num // 2:
                hits.append((t, SNARE, 105))
        if b % 2 == 1 and not is_fill_bar:  # syncopated second bar, like a real two-bar groove
            hits.append((start + (num - 2.5) * unit, KICK, 95))
            hits.append((start + (num - 1) * unit, OPEN_HAT, 90))
        if b == 0:
            hits.append((start, CRASH, 100))
    return sorted(hits)


def loop_beats(loop: FixtureLoop) -> float:
    num, den = loop.meter
    return loop.bars * num * 4 / den


def build_midi(loop: FixtureLoop) -> mido.MidiFile:
    num, den = loop.meter
    meta: list[mido.MetaMessage] = [
        mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0)
    ]
    if loop.file_bpm is not None:
        meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(loop.file_bpm), time=0))

    gate = loop.ppq // 8
    timeline: list[tuple[int, int, mido.Message]] = []
    for beat, note, vel in _pattern(loop):
        tick = round(beat * loop.ppq)
        timeline.append((tick, 1, mido.Message("note_on", channel=0, note=note, velocity=vel)))
        timeline.append((tick + gate, 0, mido.Message("note_off", channel=0, note=note)))
    timeline.sort(key=lambda e: (e[0], e[1]))
    notes: list[mido.Message] = []
    last = 0
    for tick, _, msg in timeline:
        notes.append(msg.copy(time=tick - last))
        last = tick

    end_beats = loop.eot_beats or loop_beats(loop) - loop.short_by
    end_of_track = mido.MetaMessage("end_of_track", time=max(0, round(end_beats * loop.ppq) - last))

    mid = mido.MidiFile(type=loop.midi_type, ticks_per_beat=loop.ppq)
    if loop.midi_type == 0:
        mid.tracks.append(mido.MidiTrack([*meta, *notes, end_of_track]))
    else:
        mid.tracks.append(mido.MidiTrack([*meta, mido.MetaMessage("end_of_track", time=0)]))
        mid.tracks.append(mido.MidiTrack([*notes, end_of_track]))
    return mid


def render_demo(loop: FixtureLoop, bpm: float, repeats: int) -> npt.NDArray[np.float64]:
    """A plain click-track rendering of the loop's pattern: decaying noise/sine bursts."""
    sec_per_beat = 60.0 / bpm
    length = loop_beats(loop) * sec_per_beat
    audio = np.zeros(int((length * repeats + 1.0) * DEMO_SR))
    rng = np.random.default_rng(0)
    burst_len = int(0.08 * DEMO_SR)
    env = np.exp(-np.linspace(0, 8, burst_len))
    t = np.arange(burst_len) / DEMO_SR
    for r in range(repeats):
        for beat, note, vel in _pattern(loop):
            start = int((r * length + beat * sec_per_beat) * DEMO_SR)
            tone = np.sin(2 * np.pi * 60 * t) if note == KICK else rng.uniform(-1, 1, burst_len)
            audio[start : start + burst_len] += tone * env * vel / 127
    peak = max(1e-9, float(np.abs(audio).max()))
    return audio / peak * 0.8


def write_fixture_library(root: Path, demos: bool = True) -> list[FixtureLoop]:
    """Write every fixture (and, optionally, the WAV demos) under ``root``."""
    by_path = {f.rel_path: f for f in FIXTURES}
    for loop in FIXTURES:
        path = root / loop.rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        build_midi(loop).save(path)
    if demos:
        for demo in DEMOS:
            path = root / demo.rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, render_demo(by_path[demo.loop], demo.bpm, demo.repeats), DEMO_SR)
    return list(FIXTURES)
