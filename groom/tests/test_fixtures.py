from pathlib import Path

import mido
import pytest

from groom.fixtures import DEMOS, FIXTURES, FixtureLoop, loop_beats


def _messages(mid: mido.MidiFile) -> list[mido.Message]:
    return [m for track in mid.tracks for m in track]


@pytest.mark.parametrize("loop", FIXTURES, ids=lambda f: f.rel_path)
def test_fixture_matches_description(library: Path, loop: FixtureLoop) -> None:
    mid = mido.MidiFile(library / loop.rel_path)
    msgs = _messages(mid)

    assert mid.type == loop.midi_type
    assert mid.ticks_per_beat == loop.ppq
    assert [(m.numerator, m.denominator) for m in msgs if m.type == "time_signature"] == [
        loop.meter
    ]

    tempos = [round(mido.tempo2bpm(m.tempo)) for m in msgs if m.type == "set_tempo"]
    assert tempos == ([round(loop.file_bpm)] if loop.file_bpm else [])

    notes = [m for m in msgs if m.type == "note_on" and m.velocity > 0]
    assert notes, "fixture has no notes"
    assert {m.channel for m in notes} == {0}, "library files put drums on channel 1"


@pytest.mark.parametrize("loop", FIXTURES, ids=lambda f: f.rel_path)
def test_fixture_track_length(library: Path, loop: FixtureLoop) -> None:
    mid = mido.MidiFile(library / loop.rel_path)
    length = max(sum(m.time for m in track) for track in mid.tracks) / loop.ppq
    expected = loop.eot_beats or loop_beats(loop) - loop.short_by
    assert length == pytest.approx(expected)


def test_demos_are_written(library: Path) -> None:
    for demo in DEMOS:
        assert (library / demo.rel_path).stat().st_size > 10_000


def test_every_naming_scheme_is_covered() -> None:
    assert len({f.pack for f in FIXTURES}) == 10
    assert {f.bpm_check for f in FIXTURES} == {
        "confirmed",
        "audio-matched",
        "unverified",
        "unknown",
    }
    assert any(f.file_bpm and f.file_bpm != f.bpm for f in FIXTURES), "a wrong MIDI tempo"
    assert {f.ppq for f in FIXTURES} == {96, 15360}
