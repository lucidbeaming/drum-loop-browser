"""Synthetic test library.

Generates a tiny, hand-authored stand-in for the real loop library: one or two files per naming
scheme, with the same structural quirks (96 vs 15,360 PPQ, Type 0 vs Type 1, notes on channel 1,
missing tempo events, wrong time signatures, lengths a fraction of a beat short of whole bars).
Nothing here is derived from the licensed library; the patterns are generic and generated in code.

Each ``FixtureLoop`` records what the grooming pipeline *should* conclude about the file, so
later phases can test their metadata resolution against it.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mido

KICK, SNARE, CLOSED_HAT, OPEN_HAT, CRASH = 36, 38, 42, 46, 49
TOMS = (50, 48, 47, 45, 43, 41)

Kind = Literal["groove", "fill"]


@dataclass(frozen=True)
class FixtureLoop:
    rel_path: str
    pack: str
    bpm: int | None  # BPM the names/MIDI should resolve to; None = not derivable from metadata
    meter: tuple[int, int]  # true meter
    bars: int
    kind: Kind
    ppq: int = 96
    midi_type: Literal[0, 1] = 0
    file_meter: tuple[int, int] | None = None  # time signature written in the file, if different
    tempo_event: bool = False  # whether the file carries a set_tempo event
    short_by: float = 0.25  # how many beats short of whole bars the file ends

    @property
    def written_meter(self) -> tuple[int, int]:
        return self.file_meter or self.meter


FIXTURES: tuple[FixtureLoop, ...] = (
    # BPM prefix on the file name, plus song/artist/variant
    FixtureLoop(
        "BpmPrefix_MIDILoops/MIDI Loops/118_TestSong_TestArtist1.mid",
        "BpmPrefix_MIDILoops",
        118,
        (4, 4),
        4,
        "groove",
    ),
    # BPM + meter + style in the folder; the file claims 4/4 although the folder says 7:8
    FixtureLoop(
        "BpmMeterFolder_MIDIDrumLoops/100 7:8 Angles/Angles_7_8_Grv_3.mid",
        "BpmMeterFolder_MIDIDrumLoops",
        100,
        (7, 8),
        2,
        "groove",
        ppq=15360,
        midi_type=1,
        file_meter=(4, 4),
        tempo_event=True,
    ),
    FixtureLoop(
        "BpmMeterFolder_MIDIDrumLoops/100 7:8 Angles/Angles_7_8_Fill_1.mid",
        "BpmMeterFolder_MIDIDrumLoops",
        100,
        (7, 8),
        1,
        "fill",
        ppq=15360,
        midi_type=1,
        file_meter=(4, 4),
        tempo_event=True,
    ),
    # BPM + style in the folder
    FixtureLoop(
        "BpmStyleFolder_MIDILoops/150_Grit/Linear_Grit_12.mid",
        "BpmStyleFolder_MIDILoops",
        150,
        (4, 4),
        2,
        "groove",
    ),
    # Meter + style in the folder, tempo only in the MIDI file
    FixtureLoop(
        "MeterStyleFolder_DrumLoops_MIDI/9:8_Woods/NineEight_Grv_2.mid",
        "MeterStyleFolder_DrumLoops_MIDI",
        112,
        (9, 8),
        2,
        "groove",
        ppq=15360,
        midi_type=1,
        tempo_event=True,
    ),
    # Meter as a word in the folder, no tempo anywhere
    FixtureLoop(
        "MeterWordFolder_DrumLoops_MIDI/Loops/FiveFour/FiveFour_Odd_04.mid",
        "MeterWordFolder_DrumLoops_MIDI",
        None,
        (5, 4),
        2,
        "groove",
    ),
    # Style + bar count in the folder, no tempo anywhere
    FixtureLoop(
        "BarsFolder_MIDILoops/MIDI Loops/Test Groove - 8 Bars/TestGroove_8Bars_07.mid",
        "BarsFolder_MIDILoops",
        None,
        (4, 4),
        8,
        "groove",
    ),
    FixtureLoop(
        "BarsFolder_MIDILoops/MIDI Loops/In Three - 4 Bars/InThree_4Bars_02.mid",
        "BarsFolder_MIDILoops",
        None,
        (3, 4),
        4,
        "groove",
    ),
    # Fill type, feel and bar count in the path
    FixtureLoop(
        "Fills_MIDILoops/Swung Fills/2 Bar Fills/Fill - Test Roll.mid",
        "Fills_MIDILoops",
        None,
        (4, 4),
        2,
        "fill",
    ),
    # Tempo only available from a preview file name (phase 1 adds the preview)
    FixtureLoop(
        "PreviewBpm_MIDILoops/MIDI Loops/HeavyTest/HeavyTest_05.mid",
        "PreviewBpm_MIDILoops",
        None,
        (4, 4),
        2,
        "groove",
    ),
)


def _pattern(loop: FixtureLoop) -> list[tuple[int, int, int]]:
    """Return (tick, note, velocity) hits for a simple generic beat or fill."""
    num, den = loop.meter
    unit = loop.ppq * 4 // den  # ticks per meter unit (quarter or eighth)
    bar = unit * num
    hits: list[tuple[int, int, int]] = []
    for b in range(loop.bars):
        start = b * bar
        is_fill_bar = loop.kind == "fill" and b == loop.bars - 1
        for u in range(num):
            t = start + u * unit
            if is_fill_bar:
                hits.append((t, TOMS[u % len(TOMS)], 100 - 5 * (u % 4)))
                continue
            hits.append((t, CLOSED_HAT, 96 if u % 2 == 0 else 72))
            if u == 0:
                hits.append((t, KICK, 110))
            if u == num // 2:
                hits.append((t, SNARE, 105))
        if b == 0:
            hits.append((start, CRASH, 100))
    return sorted(hits)


def _track_events(loop: FixtureLoop) -> list[mido.Message]:
    hits = _pattern(loop)
    gate = loop.ppq // 8
    timeline: list[tuple[int, int, mido.Message]] = []
    for tick, note, vel in hits:
        timeline.append((tick, 1, mido.Message("note_on", channel=0, note=note, velocity=vel)))
        timeline.append((tick + gate, 0, mido.Message("note_off", channel=0, note=note)))
    timeline.sort(key=lambda e: (e[0], e[1]))
    msgs: list[mido.Message] = []
    last = 0
    for tick, _, msg in timeline:
        msgs.append(msg.copy(time=tick - last))
        last = tick
    return msgs


def _end_tick(loop: FixtureLoop) -> int:
    num, den = loop.meter
    total_beats = loop.bars * num * 4 / den  # in quarter notes
    return round((total_beats - loop.short_by) * loop.ppq)


def build_midi(loop: FixtureLoop) -> mido.MidiFile:
    num, den = loop.written_meter
    meta: list[mido.MetaMessage] = [
        mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0)
    ]
    if loop.tempo_event and loop.bpm is not None:
        meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(loop.bpm), time=0))

    notes = _track_events(loop)
    notes_end = sum(m.time for m in notes)
    end_of_track = mido.MetaMessage("end_of_track", time=max(0, _end_tick(loop) - notes_end))

    mid = mido.MidiFile(type=loop.midi_type, ticks_per_beat=loop.ppq)
    if loop.midi_type == 0:
        mid.tracks.append(mido.MidiTrack([*meta, *notes, end_of_track]))
    else:
        mid.tracks.append(mido.MidiTrack([*meta, mido.MetaMessage("end_of_track", time=0)]))
        mid.tracks.append(mido.MidiTrack([*notes, end_of_track]))
    return mid


def write_fixture_library(root: Path) -> list[FixtureLoop]:
    """Write every fixture under ``root`` and return the fixture descriptions."""
    for loop in FIXTURES:
        path = root / loop.rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        build_midi(loop).save(path)
    return list(FIXTURES)
