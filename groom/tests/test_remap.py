import csv
from pathlib import Path

import mido
import pytest

from groom.kit import Kit, Pad, build_gm_map
from groom.remap import NotDrums, remap_folder

ROLES = ["kick", "snare", "closed-hat", "open-hat", "tom-high", "tom-low", "crash", "ride"]


@pytest.fixture
def kit() -> Kit:
    pads = [Pad(i + 1, r, r, 36 + i) for i, r in enumerate(ROLES)]
    gm_map, unmapped = build_gm_map(pads)
    return Kit("test", "", pads, gm_map, unmapped)


def gm_file(path: Path, notes: list[int], gap: int = 120) -> None:
    track = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=500000, time=0)])
    for n in notes:
        track.append(mido.Message("note_on", channel=9, note=n, velocity=100, time=gap))
        track.append(mido.Message("note_off", channel=9, note=n, time=60))
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid = mido.MidiFile(ticks_per_beat=480)
    mid.tracks.append(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(path)


def onsets(path: Path) -> list[tuple[int, int, int]]:
    """(absolute tick, channel, note) of each note-on."""
    tick, out = 0, []
    for msg in mido.MidiFile(path).tracks[0]:
        tick += msg.time
        if msg.type == "note_on":
            out.append((tick, msg.channel, msg.note))
    return out


def test_remaps_a_folder(kit: Kit, tmp_path: Path) -> None:
    src = tmp_path / "Funk set"
    gm_file(src / "a.mid", [36, 38, 42, 50, 48, 41, 49, 60])
    gm_file(src / "sub" / "b.mid", [36, 36])
    out = tmp_path / "out"
    reports = remap_folder(src, out, kit)
    assert [r.path for r in reports] == ["a.mid", "sub/b.mid"]
    # kick 36, snare 37, closed hat 38, toms 50/48 -> high (40), 41 -> low (41), crash 42;
    # 60 (bongo) has no pad and is kept
    assert [n for _, _, n in onsets(out / "a.mid")] == [36, 37, 38, 40, 40, 41, 42, 60]
    assert {c for _, c, _ in onsets(out / "a.mid")} == {9}
    assert (out / "sub" / "b.mid").exists()
    rows = list(csv.DictReader((out / "remap-report.csv").open()))
    assert rows[0]["folded"].startswith("41 Low Floor Tom; 48 Hi-Mid Tom")
    assert rows[0]["unmapped_kept"] == "60 Hi Bongo"
    assert [n for _, _, n in onsets(src / "a.mid")] == [36, 38, 42, 50, 48, 41, 49, 60]  # untouched


def test_unmapped_drop_keeps_timing(kit: Kit, tmp_path: Path) -> None:
    gm_file(tmp_path / "in" / "a.mid", [36, 60, 38])
    remap_folder(tmp_path / "in", tmp_path / "out", kit, unmapped="drop")
    assert onsets(tmp_path / "out" / "a.mid") == [(120, 9, 36), (480, 9, 37)]


def test_unmapped_to_a_pad_and_channel(kit: Kit, tmp_path: Path) -> None:
    gm_file(tmp_path / "in" / "a.mid", [60])
    reports = remap_folder(tmp_path / "in", tmp_path / "out", kit, unmapped=8, channel=1)
    assert onsets(tmp_path / "out" / "a.mid") == [(120, 0, 43)]
    assert reports[0].moved == {60}


def test_dry_run_and_refusals_write_nothing(kit: Kit, tmp_path: Path) -> None:
    gm_file(tmp_path / "in" / "a.mid", [36])
    remap_folder(tmp_path / "in", tmp_path / "out", kit, dry_run=True)
    assert not (tmp_path / "out").exists()
    gm_file(tmp_path / "in" / "b.mid", [100])  # not a drum note
    with pytest.raises(NotDrums):
        remap_folder(tmp_path / "in", tmp_path / "out", kit)
    assert not (tmp_path / "out").exists()
    remap_folder(tmp_path / "in", tmp_path / "out", kit, force=True)
    assert (tmp_path / "out" / "b.mid").exists()
