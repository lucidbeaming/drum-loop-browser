import struct
from pathlib import Path

import mido
import pytest

from groom.paths import project_paths
from groom.pipeline import PREVIEW_SOUNDFONT
from groom.render import Render, fluidsynth, render_all
from groom.soundfont import drum_kits


def chunk(cid: bytes, body: bytes) -> bytes:
    return cid + struct.pack("<I", len(body)) + body + b"\0" * (len(body) & 1)


def tiny_sf2() -> bytes:
    """A SoundFont with a drum kit whose preset covers keys 36-38 and whose instrument has
    samples on 30-36 and 38 (so 36 and 38 sound), plus a melodic preset that is ignored."""

    def phdr(name: bytes, program: int, bank: int, bag: int) -> bytes:
        return struct.pack("<20sHHHIII", name, program, bank, bag, 0, 0, 0)

    def keys(lo: int, hi: int) -> int:
        return lo | hi << 8

    pdta = b"pdta" + b"".join(
        [
            chunk(
                b"phdr",
                phdr(b"Piano", 0, 0, 0) + phdr(b"Standard", 0, 128, 1) + phdr(b"EOP", 0, 0, 2),
            ),
            chunk(b"pbag", struct.pack("<6H", 0, 0, 1, 0, 3, 0)),
            chunk(b"pgen", struct.pack("<8H", 41, 0, 43, keys(36, 38), 41, 0, 0, 0)),
            chunk(b"inst", struct.pack("<20sH20sH", b"Drums", 0, b"EOI", 2)),
            chunk(b"ibag", struct.pack("<6H", 0, 0, 2, 0, 4, 0)),
            chunk(
                b"igen", struct.pack("<10H", 43, keys(30, 36), 53, 0, 43, keys(38, 38), 53, 1, 0, 0)
            ),
        ]
    )
    body = b"sfbk" + chunk(b"LIST", b"INFO") + chunk(b"LIST", pdta)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_drum_kits(tmp_path: Path) -> None:
    path = tmp_path / "tiny.sf2"
    path.write_bytes(tiny_sf2())
    [kit] = drum_kits(path)
    assert (kit.bank, kit.program, kit.name) == (128, 0, "Standard")
    assert kit.keys == {36, 38}


def test_not_a_soundfont(tmp_path: Path) -> None:
    path = tmp_path / "x.sf2"
    path.write_bytes(b"RIFF\0\0\0\0WAVE")
    with pytest.raises(ValueError):
        drum_kits(path)


def test_render_flags() -> None:
    assert Render(0.0, 0.0).silent
    assert Render(0.995, 0.2).clips
    assert not Render(0.3, 0.05).silent and not Render(0.3, 0.05).clips


PREVIEW_SF2 = project_paths().soundfonts / PREVIEW_SOUNDFONT


@pytest.mark.skipif(
    fluidsynth() is None or not PREVIEW_SF2.is_file(),
    reason="needs the fluidsynth program and the preview SoundFont",
)
def test_render_all(tmp_path: Path) -> None:
    def drums(*keys: int) -> Path:
        msgs = [mido.Message("note_on", channel=9, note=k, velocity=100) for k in keys]
        mid = mido.MidiFile(ticks_per_beat=480)
        mid.tracks.append(mido.MidiTrack([*msgs, mido.MetaMessage("end_of_track", time=1920)]))
        path = tmp_path / f"{len(keys)}.mid"
        mid.save(path)
        return path

    files = {"kick": drums(36), "empty": drums()}
    first = render_all(files, PREVIEW_SF2, tmp_path / "cache")
    assert first["empty"].silent
    assert not first["kick"].silent and not first["kick"].clips
    assert render_all(files, PREVIEW_SF2, tmp_path / "cache") == first  # from the cache
