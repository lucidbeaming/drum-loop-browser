"""Reading library MIDI files and writing normalised loops."""

import hashlib
import math
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import mido

NORMALISED_PPQ = 480
DRUM_CHANNEL = 9  # MIDI channel 10
LATE_HIT_TOLERANCE = Fraction(1, 8)  # beats past a bar line still counted as the previous bar
MIN_NOTE_TICKS = 1


@dataclass(frozen=True)
class Note:
    tick: int  # at NORMALISED_PPQ
    key: int
    vel: int
    dur: int


@dataclass
class ParsedMidi:
    ppq: int
    midi_type: int
    notes: list[Note]
    tempo_bpm: float | None
    meter: tuple[int, int] | None
    issues: list[str] = field(default_factory=list)

    @property
    def last_onset(self) -> int:
        return max((n.tick for n in self.notes), default=0)


def _scale(tick: int, ppq: int) -> Fraction:
    return Fraction(tick * NORMALISED_PPQ, ppq)


def parse_midi(path: Path) -> ParsedMidi:
    """Read notes (any channel), the first tempo and the first time signature."""
    mid = mido.MidiFile(path)
    issues: list[str] = []
    tempo: float | None = None
    meter: tuple[int, int] | None = None
    open_notes: dict[int, list[tuple[int, int]]] = {}
    notes: list[Note] = []
    tick = 0
    for msg in mido.merge_tracks(mid.tracks):
        tick += msg.time
        if msg.type == "set_tempo" and tempo is None:
            tempo = round(mido.tempo2bpm(msg.tempo), 3)
        elif msg.type == "time_signature" and meter is None:
            meter = (msg.numerator, msg.denominator)
        elif msg.type == "note_on" and msg.velocity > 0:
            open_notes.setdefault(msg.note, []).append((tick, msg.velocity))
        elif msg.type in ("note_off", "note_on"):
            starts = open_notes.get(msg.note)
            if starts:
                start, vel = starts.pop(0)
                notes.append(_note(start, msg.note, vel, tick - start, mid.ticks_per_beat, issues))
    for key, starts in open_notes.items():
        for start, vel in starts:
            notes.append(_note(start, key, vel, 0, mid.ticks_per_beat, issues))
            if "hanging note" not in issues:
                issues.append("hanging note")
    notes.sort(key=lambda n: (n.tick, n.key))
    if not notes:
        issues.append("no notes")
    return ParsedMidi(mid.ticks_per_beat, mid.type, notes, tempo, meter, issues)


def _note(start: int, key: int, vel: int, dur: int, ppq: int, issues: list[str]) -> Note:
    onset = _scale(start, ppq)
    if onset.denominator != 1 and "off-grid timing" not in issues:
        issues.append("off-grid timing")  # onset finer than 480 PPQ; rounded
    return Note(round(onset), key, vel, max(MIN_NOTE_TICKS, round(_scale(dur, ppq))))


def bar_ticks(meter: tuple[int, int]) -> int:
    num, den = meter
    return num * 4 * NORMALISED_PPQ // den


def infer_bars(parsed: ParsedMidi, meter: tuple[int, int]) -> int:
    """Whole bars needed to hold every onset, allowing slightly late hits past a bar line."""
    tolerance = int(LATE_HIT_TOLERANCE * NORMALISED_PPQ)
    return max(1, math.floor(max(0, parsed.last_onset - tolerance) / bar_ticks(meter)) + 1)


@dataclass(frozen=True)
class LoopNotes:
    notes: list[Note]
    length: int
    wrapped: int  # hits at/after the loop end moved to the start
    dropped: int  # hits at/after the loop end that duplicated a hit at the start


def fit_to_length(notes: list[Note], length: int) -> LoopNotes:
    """Keep notes inside [0, length); wrap later hits to the loop start unless already there."""
    inside = [n for n in notes if n.tick < length]
    starts = {(n.key, n.tick) for n in inside}
    near = NORMALISED_PPQ // 16
    wrapped = dropped = 0
    for n in notes:
        if n.tick < length:
            continue
        t = n.tick - length
        if any((n.key, s) in starts for s in range(max(0, t - near), t + near + 1)):
            dropped += 1
            continue
        inside.append(Note(t, n.key, n.vel, n.dur))
        wrapped += 1
    fitted = [Note(n.tick, n.key, n.vel, min(n.dur, length - n.tick)) for n in inside]
    fitted.sort(key=lambda n: (n.tick, n.key))
    return LoopNotes(fitted, length, wrapped, dropped)


def loop_id(loop: LoopNotes, meter: tuple[int, int]) -> str:
    """Stable ID from the normalised content (not the tempo, so tempo fixes keep the ID)."""
    h = hashlib.sha1(f"{meter[0]}/{meter[1]}|{loop.length}|".encode())
    for n in loop.notes:
        h.update(f"{n.tick},{n.key},{n.vel},{n.dur};".encode())
    return h.hexdigest()[:16]


def build_normalised(
    loop: LoopNotes, meter: tuple[int, int], bpm: float | None, title: str
) -> mido.MidiFile:
    """Type 0, 480 PPQ, channel 10, tempo + meter at tick 0, exactly ``loop.length`` ticks."""
    events: list[tuple[int, int, mido.Message]] = []
    for n in loop.notes:
        on = mido.Message("note_on", channel=DRUM_CHANNEL, note=n.key, velocity=n.vel)
        off = mido.Message("note_off", channel=DRUM_CHANNEL, note=n.key)
        events.append((n.tick, 1, on))
        events.append((n.tick + n.dur, 0, off))
    events.sort(key=lambda e: (e[0], e[1]))

    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=title, time=0))
    track.append(
        mido.MetaMessage("time_signature", numerator=meter[0], denominator=meter[1], time=0)
    )
    if bpm is not None:
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    last = 0
    for tick, _, msg in events:
        track.append(msg.copy(time=tick - last))
        last = tick
    track.append(mido.MetaMessage("end_of_track", time=loop.length - last))

    mid = mido.MidiFile(type=0, ticks_per_beat=NORMALISED_PPQ)
    mid.tracks.append(track)
    return mid
