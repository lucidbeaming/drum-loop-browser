import pytest

from groom.names import kind_from_token, match_key, meter_from_words, split_camel
from groom.rules import best_matches, load_rules, similarity


@pytest.mark.parametrize(
    ("text", "meter"),
    [
        ("SevenEight", (7, 8)),
        ("Seven Eight", (7, 8)),
        ("NineEight_Drums", (9, 8)),
        ("FifteenEight", (15, 8)),
        ("ElevenEight", (11, 8)),
        ("ThreeFour", (3, 4)),
        ("Seven", None),
        ("FiveThree", None),
    ],
)
def test_meter_from_words(text: str, meter: tuple[int, int] | None) -> None:
    assert meter_from_words(text) == meter


def test_kind_tokens() -> None:
    assert kind_from_token("Grv") == "groove"
    assert kind_from_token("Brk") == "break"
    assert kind_from_token("Crsh") == "ending"
    assert kind_from_token("Fill") == "fill"
    assert kind_from_token("Odd") is None
    assert kind_from_token(None) is None


def test_split_camel_and_match_key() -> None:
    assert split_camel("StraightUpGroove") == "Straight Up Groove"
    assert split_camel("Oakland_3013") == "Oakland 3013"
    assert match_key("Straight Up-Groove") == "straightupgroove"


def test_similarity() -> None:
    assert similarity("Straight Up Groove", "StraightUp Groove") == 100
    assert similarity("Funky", "UpFunky") == 90  # containment
    assert similarity("BillyJean", "BillieJean") >= 80
    assert similarity("Popped", "Carbonized") < 50


def test_best_matches_ties_and_threshold() -> None:
    targets = {"a": "Cinematic", "b": "Cinematic", "c": "Indie Rock"}
    assert sorted(best_matches("Cinematic", targets)) == ["a", "b"]
    assert best_matches("Gritty Kit", targets) == []


# One synthetic name per pack, shaped like that pack's real files, with the fields it must yield.
EXAMPLES = {
    "ClassicBeats_MIDILoops": ("MIDI Loops", "99_SomeSong_SomeBand2", {"bpm": "99", "song": "SomeSong", "artist": "SomeBand", "variant": "2"}),  # noqa: E501
    "DrumaticBeats_MIDIDrumLoops": ("100 7:8 Shapes", "Shapes_7_8_Brk_3", {"bpm": "100", "num": "7", "kind": "Brk"}),  # noqa: E501
    "EpicDrums1_MIDILoops": ("MIDI Loops/BigThing", "BigThing_04", {"style": "BigThing", "variant": "04"}),  # noqa: E501
    "FillsUnlimited_MIDILoops": ("Swung Fills/2 Bar Fills", "Fill - Some Roll", {"feel": "Swung", "bars": "2", "key": "Some Roll"}),  # noqa: E501
    "LinearDrums_MIDILoops": ("88_Thing", "Linear_Thing_7", {"bpm": "88", "key": "Thing"}),
    "LongLoops3_MIDILoops": ("MIDI Loops/Some Style - 8 Bars", "SomeStyle_8Bar_03", {"bars": "8", "style": "Some Style"}),  # noqa: E501
    "OddMeter_DrumLoops_MIDI": ("11:8_Quirk", "ElevenEight_Grv14", {"num": "11", "den": "8", "kind": "Grv"}),  # noqa: E501
    "OddMeter_DrumLoops2_MIDI": ("Loops/SevenFour", "SevenFour_Odd_11", {"meter": "SevenFour"}),
    "OddMeter_DrumLoops3_MIDI": ("Loops/NineFour_Drums", "NineFour_OddMeter_20", {"meter": "NineFour"}),  # noqa: E501
}  # fmt: skip


@pytest.mark.parametrize("pack", EXAMPLES)
def test_real_pack_rules_parse_example_names(pack: str) -> None:
    rules = load_rules()[pack]
    group_dir, stem, expected = EXAMPLES[pack]
    fields = {**(rules.group_fields(group_dir) or {}), **(rules.file_fields(stem) or {})}
    assert expected.items() <= fields.items()


def test_every_real_pack_has_rules() -> None:
    assert len(load_rules()) == 18
