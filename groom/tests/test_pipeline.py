import json
import sqlite3
from pathlib import Path

import mido
import pytest

from groom.fixtures import FIXTURES, FixtureLoop
from groom.midi import whole_beat_repeats
from groom.paths import Paths
from groom.pipeline import RunResult, run
from groom.store import SCHEMA_VERSION


@pytest.fixture
def result(paths: Paths, fixture_rules: Path) -> RunResult:
    return run(paths, fixture_rules)


@pytest.fixture
def rows(result: RunResult, paths: Paths) -> dict[str, sqlite3.Row]:
    con = sqlite3.connect(paths.data / "catalogue.sqlite")
    con.row_factory = sqlite3.Row
    return {r["src_rel_path"]: r for r in con.execute("SELECT * FROM loops")}


@pytest.mark.parametrize("fx", FIXTURES, ids=lambda f: f.rel_path)
def test_loop_metadata(rows: dict[str, sqlite3.Row], fx: FixtureLoop) -> None:
    row = rows[fx.rel_path]
    assert (row["meter_num"], row["meter_den"]) == fx.meter
    # loops a fractional number of beats long are repeated to whole beats (1 bar of 7/8 -> 2)
    assert row["bars"] == fx.bars * whole_beat_repeats(fx.bars, fx.meter)
    assert row["kind"] == fx.kind
    assert row["bpm_check"] == fx.bpm_check, json.loads(row["bpm_candidates"])
    if fx.bpm is None:
        assert row["bpm"] is None
    else:
        assert row["bpm"] == pytest.approx(fx.bpm, abs=1.5)


def test_wrong_midi_tempo_loses_to_folder(rows: dict[str, sqlite3.Row]) -> None:
    candidates = json.loads(rows[FIXTURES[1].rel_path]["bpm_candidates"])
    by_source = {c["source"]: c for c in candidates}
    assert by_source["folder"]["bpm"] == 100 and by_source["folder"]["support"] >= 0.85
    assert by_source["midi"]["bpm"] == 91 and by_source["midi"]["support"] < 0.85


def test_song_and_artist_are_split(rows: dict[str, sqlite3.Row]) -> None:
    row = rows[FIXTURES[0].rel_path]
    assert (row["song"], row["artist"], row["variant"]) == ("Test Song", "Test Artist", "1")


def test_normalised_files(rows: dict[str, sqlite3.Row], paths: Paths) -> None:
    assert len(list((paths.data / "normalised").glob("*.mid"))) == len(rows)
    for fx in FIXTURES:
        row = rows[fx.rel_path]
        mid = mido.MidiFile(paths.data / row["norm_rel_path"])
        assert mid.ticks_per_beat == 480
        assert sum(m.time for m in mid.tracks[0]) == row["length_ticks"]
        num, den = fx.meter
        assert row["length_ticks"] == row["bars"] * num * 4 * 480 // den
        assert row["length_ticks"] % 480 == 0  # a whole number of beats
        assert {m.channel for m in mid.tracks[0] if m.type == "note_on"} == {9}


def test_notes_table_matches_files(rows: dict[str, sqlite3.Row], paths: Paths) -> None:
    con = sqlite3.connect(paths.data / "catalogue.sqlite")
    for row in rows.values():
        (count,) = con.execute(
            "SELECT count(*) FROM notes WHERE loop_id = ?", (row["loop_id"],)
        ).fetchone()
        assert count == row["note_count"] > 0


def test_meta_and_reports(result: RunResult, paths: Paths) -> None:
    con = sqlite3.connect(paths.data / "catalogue.sqlite")
    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    assert meta["schema_version"] == str(SCHEMA_VERSION)
    for name in ("coverage.csv", "review.csv", "previews.csv"):
        assert (paths.reports / name).exists()
    assert result.scan.unmatched_demos == []
    assert sum(r["loops"] for r in result.coverage()) == len(FIXTURES)  # type: ignore[misc]


def test_identical_files_become_one_loop(
    paths: Paths, fixture_rules: Path, library: Path, tmp_path: Path
) -> None:
    import shutil

    copy = tmp_path / "lib"
    shutil.copytree(library, copy)
    src = copy / FIXTURES[3].rel_path
    shutil.copy(src, src.with_name("Linear_Grit_99.mid"))
    result = run(Paths(data=paths.data, library=copy, soundfonts=paths.soundfonts), fixture_rules)
    assert len(result.loops) == len(FIXTURES)
    dup = next(lp for lp in result.loops if lp.also_at)
    assert dup.also_at[0].endswith("Linear_Grit_99.mid")


def test_without_audio_named_tempos_are_unverified(paths: Paths, fixture_rules: Path) -> None:
    result = run(paths, fixture_rules, audio=False)
    checks = {lp.rel_path: lp.bpm_check for lp in result.loops}
    assert checks[FIXTURES[1].rel_path] == "unverified"
    assert checks[FIXTURES[5].rel_path] == "unknown"
