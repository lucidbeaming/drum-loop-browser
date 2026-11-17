from pathlib import Path

import mido

from groom.fixtures import FIXTURES
from groom.midi import (
    NORMALISED_PPQ,
    Note,
    ParsedMidi,
    build_normalised,
    fit_to_length,
    infer_bars,
    loop_id,
    parse_midi,
    repeat_loop,
    whole_beat_repeats,
)

Q = NORMALISED_PPQ


def _parsed(onsets: list[int]) -> ParsedMidi:
    return ParsedMidi(Q, 0, [Note(t, 36, 100, 10) for t in onsets], None, (4, 4))


def test_parse_scales_to_480_ppq(library: Path) -> None:
    for fx in (FIXTURES[0], FIXTURES[1]):  # 96 PPQ and 15,360 PPQ
        parsed = parse_midi(library / fx.rel_path)
        assert parsed.ppq == fx.ppq
        assert parsed.notes[0].tick == 0
        assert all(n.tick % (Q // 4) == 0 for n in parsed.notes)  # fixture hits are on 16ths
        assert "off-grid timing" not in parsed.issues


def test_parse_reads_wrong_tempo_and_meter(library: Path) -> None:
    parsed = parse_midi(library / FIXTURES[1].rel_path)
    assert parsed.tempo_bpm == 91
    assert parsed.meter == (7, 8)


def test_infer_bars_ignores_end_of_track_and_tolerates_late_hits() -> None:
    bar = 4 * Q
    assert infer_bars(_parsed([0, bar - Q]), (4, 4)) == 1
    assert infer_bars(_parsed([0, bar + Q // 16]), (4, 4)) == 1  # slightly late hit on bar 2
    assert infer_bars(_parsed([0, bar + Q // 2]), (4, 4)) == 2
    assert infer_bars(_parsed([0, 3 * Q * 2 - Q]), (3, 4)) == 2


def test_fit_wraps_late_hits_and_drops_duplicates() -> None:
    length = 4 * Q
    notes = [Note(0, 36, 100, 10), Note(length, 36, 90, 10), Note(length + 5, 42, 80, 10)]
    fitted = fit_to_length(notes, length)
    assert fitted.dropped == 1  # a kick already sits at the loop start
    assert fitted.wrapped == 1  # the hat moves to tick 5
    assert [(n.tick, n.key) for n in fitted.notes] == [(0, 36), (5, 42)]


def test_fit_trims_durations_at_loop_end() -> None:
    fitted = fit_to_length([Note(4 * Q - 10, 42, 80, 100)], 4 * Q)
    assert fitted.notes[0].dur == 10


def test_zero_length_hits_become_one_shots_without_overlap() -> None:
    notes = [Note(0, 42, 80, 1), Note(Q // 8, 42, 80, 1), Note(Q, 36, 100, 1)]
    fitted = fit_to_length(notes, 4 * Q)
    durs = {(n.tick, n.key): n.dur for n in fitted.notes}
    assert durs[(0, 42)] == Q // 8  # stops at the next hat (a 32nd later)
    assert durs[(Q // 8, 42)] == Q // 4  # a 16th note
    assert durs[(Q, 36)] == Q // 4
    long = fit_to_length([Note(0, 49, 100, 2 * Q)], 4 * Q)
    assert long.notes[0].dur == 2 * Q  # longer hits keep their length


def test_loop_id_depends_on_content_not_tempo() -> None:
    a = fit_to_length([Note(0, 36, 100, 10)], 4 * Q)
    b = fit_to_length([Note(0, 36, 101, 10)], 4 * Q)
    assert loop_id(a, (4, 4)) == loop_id(a, (4, 4))
    assert loop_id(a, (4, 4)) != loop_id(b, (4, 4))
    assert loop_id(a, (4, 4)) != loop_id(a, (2, 2))


def test_build_normalised_round_trip(tmp_path: Path) -> None:
    fitted = fit_to_length([Note(0, 36, 100, 30), Note(Q, 38, 90, 30)], 8 * Q)
    path = tmp_path / "x.mid"
    build_normalised(fitted, (4, 4), 97.0, "Test").save(path)

    mid = mido.MidiFile(path)
    assert (mid.type, mid.ticks_per_beat, len(mid.tracks)) == (0, Q, 1)
    msgs = list(mid.tracks[0])
    assert sum(m.time for m in msgs) == 8 * Q  # exactly two bars
    assert round(mido.tempo2bpm(next(m for m in msgs if m.type == "set_tempo").tempo)) == 97
    notes = [m for m in msgs if m.type == "note_on"]
    assert {m.channel for m in notes} == {9}
    assert [m.note for m in notes] == [36, 38]


def test_whole_beat_repeats() -> None:
    assert whole_beat_repeats(1, (4, 4)) == 1
    assert whole_beat_repeats(2, (7, 8)) == 1  # 7 beats
    assert whole_beat_repeats(1, (15, 8)) == 2  # 7.5 beats -> 15
    assert whole_beat_repeats(3, (9, 8)) == 2
    assert whole_beat_repeats(1, (7, 16)) == 4


def test_repeat_loop() -> None:
    once = fit_to_length([Note(0, 36, 100, 10), Note(Q, 38, 90, 10)], 3 * Q // 2 * 5)
    twice = repeat_loop(once, 2)
    assert twice.length == 2 * once.length
    assert [n.tick for n in twice.notes] == [0, Q, once.length, once.length + Q]
