from pathlib import Path

import mido
import pytest

from groom.fixtures import FIXTURES, FixtureLoop, write_fixture_library


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("library")
    write_fixture_library(root)
    return root


def _messages(mid: mido.MidiFile) -> list[mido.Message]:
    return [m for track in mid.tracks for m in track]


@pytest.mark.parametrize("loop", FIXTURES, ids=lambda f: f.rel_path)
def test_fixture_matches_description(library: Path, loop: FixtureLoop) -> None:
    mid = mido.MidiFile(library / loop.rel_path)
    msgs = _messages(mid)

    assert mid.type == loop.midi_type
    assert mid.ticks_per_beat == loop.ppq

    sigs = [(m.numerator, m.denominator) for m in msgs if m.type == "time_signature"]
    assert sigs == [loop.written_meter]

    tempos = [m for m in msgs if m.type == "set_tempo"]
    assert bool(tempos) == loop.tempo_event
    if tempos:
        assert round(mido.tempo2bpm(tempos[0].tempo)) == loop.bpm

    notes = [m for m in msgs if m.type == "note_on" and m.velocity > 0]
    assert notes, "fixture has no notes"
    assert {m.channel for m in notes} == {0}, "library files put drums on channel 1"


@pytest.mark.parametrize("loop", FIXTURES, ids=lambda f: f.rel_path)
def test_fixture_ends_short_of_whole_bars(library: Path, loop: FixtureLoop) -> None:
    mid = mido.MidiFile(library / loop.rel_path)
    length_ticks = max(sum(m.time for m in track) for track in mid.tracks)
    num, den = loop.meter
    whole_bars = loop.bars * num * 4 / den * loop.ppq
    assert length_ticks == pytest.approx(whole_bars - loop.short_by * loop.ppq)


def test_every_naming_scheme_is_covered() -> None:
    packs = {f.pack for f in FIXTURES}
    assert len(packs) == 8
    assert any(f.kind == "fill" for f in FIXTURES)
    assert any(f.file_meter and f.file_meter != f.meter for f in FIXTURES)
    assert {f.ppq for f in FIXTURES} == {96, 15360}
    assert any(f.bpm is None for f in FIXTURES)
