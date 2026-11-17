from pathlib import Path

import mido
import pytest
from typer.testing import CliRunner

from groom.cli import app
from groom.kit import (
    UNKNOWN,
    Pad,
    TextBox,
    build_gm_map,
    kit_from_text,
    load_kit,
    load_labels,
    match_role,
    rebuild,
    save_kit,
)
from groom.ocr import available, read_text, render_grid

# PLAN's reference: the default Kong kit, as it should come out of its screenshot
DEFAULT_LABELS = [
    "BD 1", "SD1", "HH Closed", "HH Open", "BD2", "SD2", "CLAP", "HH Tight",
    "TOM H", "TOM M", "TOM L", "CRASH", "CABASA", "TAMBOURINE", "SYNTH TOM", "RIDE",
]  # fmt: skip
DEFAULT_GROUPS = {3: 3, 4: 3, 8: 3}  # the hi-hats share group 3 (shown in the pad corner)
DEFAULT_GM_MAP = {
    36: 36, 38: 37, 42: 38, 46: 39, 35: 40, 40: 41, 37: 41, 39: 42, 44: 43,
    50: 44, 48: 44, 47: 45, 45: 45, 43: 46, 41: 46,
    49: 47, 57: 47, 52: 47, 55: 47, 69: 48, 54: 49, 51: 51, 59: 51, 53: 51,
}  # fmt: skip
DEFAULT_ROLES = [
    "kick", "snare", "closed-hat", "open-hat", "kick", "snare", "clap", "pedal-hat",
    "tom-high", "tom-mid", "tom-low", "crash", "cabasa", "tambourine", "none", "ride",
]  # fmt: skip

LABELS = load_labels()
runner = CliRunner()


def default_boxes() -> list[TextBox]:
    """OCR boxes as Vision returns them for the default kit, with the traps a real screenshot
    has: corner group numbers, a pad number joined to its label, and an OCR typo."""
    boxes = []
    for i, label in enumerate(DEFAULT_LABELS):
        pad = i + 1
        col, row_from_top = i % 4, 3 - i // 4
        x, y = col / 4, row_from_top / 4
        if pad == 3:
            boxes.append(TextBox("HH Closed 3", x + 0.12, y + 0.13, 0.12, 0.03))  # joined
        elif pad == 10:
            boxes.append(TextBox("T0M M", x + 0.09, y + 0.13, 0.08, 0.03, 0.5))  # typo
        else:
            boxes.append(TextBox(label, x + 0.09, y + 0.13, 0.08, 0.03))
            boxes.append(TextBox(str(pad), x + 0.2, y + 0.13, 0.02, 0.02))
        if pad in DEFAULT_GROUPS:
            boxes.append(TextBox(str(DEFAULT_GROUPS[pad]), x + 0.03, y + 0.04, 0.02, 0.02))
    return boxes


def check_default(kit_pads: list[Pad], gm_map: dict[int, int]) -> None:
    assert [p.role for p in kit_pads] == DEFAULT_ROLES
    assert [p.note for p in kit_pads] == list(range(36, 52))
    assert {p.pad: p.group for p in kit_pads if p.group is not None} == DEFAULT_GROUPS
    assert gm_map == dict(sorted(DEFAULT_GM_MAP.items()))


def test_default_kit_from_text() -> None:
    kit = kit_from_text("kong-default", "default.png", default_boxes(), LABELS)
    check_default(kit.pads, kit.gm_map)
    assert kit.pads[2].label == "HH Closed"  # the joined pad number is split off
    assert {30, 34, 60} <= set(kit.unmapped)
    assert not any(p.remarks for p in kit.pads)


def test_wrong_pad_number_is_flagged() -> None:
    boxes = [b if b.text != "7" else TextBox("1", b.x, b.y, b.w, b.h) for b in default_boxes()]
    pads = kit_from_text("k", "", boxes, LABELS).pads
    assert pads[6].remarks == ["the screenshot says pad 1; its position says pad 7"]


@pytest.mark.parametrize(
    ("label", "role"),
    [
        ("BD 1", "kick"), ("SD1", "snare"), ("HH CLS", "closed-hat"), ("HH Tight", "pedal-hat"),
        ("TOM 1", "tom-high"), ("Synth Tom", "none"), ("HH CL0SED", "closed-hat"),
        ("Tambourne", "tambourine"), ("Xylophone", UNKNOWN),
    ],
)  # fmt: skip
def test_match_role(label: str, role: str) -> None:
    assert match_role(label, LABELS)[0] == role


def pads(*roles: str) -> list[Pad]:
    return [Pad(i + 1, r, r, 36 + i) for i, r in enumerate(roles)]


def test_fewer_pads_fold_by_family() -> None:
    gm, unmapped = build_gm_map(pads("kick", "snare", "closed-hat", "tom-high", "tom-low", "ride"))
    assert [gm[n] for n in (50, 48, 47, 45, 43, 41)] == [39, 39, 39, 40, 40, 40]
    assert gm[44] == gm[46] == 38  # pedal and open hats fold onto the closed hat
    assert gm[37] == gm[40] == 37  # side stick and electric snare onto the snare
    assert gm[53] == gm[59] == 41
    assert 49 in unmapped and 39 in unmapped  # no cymbal or clap pad: nothing to fold onto


def test_dedicated_pads_win() -> None:
    gm, _ = build_gm_map(pads("snare", "rim", "crash", "crash", "china", "ride-bell", "ride"))
    assert (gm[37], gm[49], gm[57], gm[52], gm[55], gm[53], gm[51]) == (37, 38, 39, 40, 38, 41, 42)


def test_save_edit_rebuild(tmp_path: Path) -> None:
    kit = kit_from_text("kong-default", "default.png", default_boxes(), LABELS)
    path = tmp_path / "kong-default.yaml"
    save_kit(kit, path)
    assert path.read_text().startswith("# Kong kit map")
    loaded = load_kit(path)
    assert loaded.gm_map == kit.gm_map
    loaded.pads[14].role = "tom-low"  # SYNTH TOM used as a fourth tom
    rebuilt = rebuild(loaded)
    assert rebuilt.gm_map[41] == 50 and rebuilt.gm_map[43] == 46


@pytest.mark.skipif(not available(), reason="needs macOS and swiftc")
def test_default_kit_screenshot(tmp_path: Path) -> None:
    spec = {
        "size": 800,
        "pads": [
            {"pad": i + 1, "label": label, "group": DEFAULT_GROUPS.get(i + 1)}
            for i, label in enumerate(DEFAULT_LABELS)
        ],
    }
    image = tmp_path / "kong-default.png"
    render_grid(spec, image, tmp_path / "cache")
    kit = kit_from_text("kong-default", str(image), read_text(image, tmp_path / "cache"), LABELS)
    check_default(kit.pads, kit.gm_map)


def test_kit_and_remap_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("DRUM_DATA_DIR", str(data))
    save_kit(
        kit_from_text("kong", "x.png", default_boxes(), load_labels()), data / "kits" / "kong.yaml"
    )
    result = runner.invoke(app, ["kit", "show", "kong"])
    assert result.exit_code == 0, result.output
    assert "TOM H" in result.output

    mid = mido.MidiFile()
    mid.tracks.append(mido.MidiTrack([mido.Message("note_on", channel=9, note=50, velocity=90)]))
    (tmp_path / "Funk set").mkdir()
    mid.save(tmp_path / "Funk set" / "a.mid")
    result = runner.invoke(app, ["remap", str(tmp_path / "Funk set"), "--kit", "kong"])
    assert result.exit_code == 0, result.output
    assert (data / "remapped" / "Funk set (kong)" / "a.mid").exists()
    result = runner.invoke(app, ["remap", str(tmp_path / "Funk set"), "--kit", "nope"])
    assert result.exit_code != 0


def test_lookalike_letters() -> None:
    assert match_role("TO\u041c H", LABELS) == ("tom-high", 1.0)  # a Cyrillic M
    boxes = [
        b if b.text != "TOM H" else TextBox("TO\u041c H", b.x, b.y, b.w, b.h)
        for b in default_boxes()
    ]
    assert kit_from_text("k", "", boxes, LABELS).pads[8].label == "TOM H"
