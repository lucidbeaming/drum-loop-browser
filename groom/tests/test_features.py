import numpy as np
import pytest

from groom.features import analyse, neighbours, onset_vector, pattern_key
from groom.midi import NORMALISED_PPQ, Note
from groom.tags import Tag, feature_tags, merge, rule_tags

Q = NORMALISED_PPQ
KICK, SNARE, HAT, RIDE, TOM = 36, 38, 42, 51, 45


def note(beat: float, key: int, vel: int = 100) -> Note:
    return Note(round(beat * Q), key, vel, Q // 8)


def rock(bars: int = 2, swing: float = 0.5, hat: int = HAT) -> list[Note]:
    """Kick on 1 and 3, snare on 2 and 4, 8th-note hats (off-beats at ``swing``)."""
    notes = []
    for b in range(bars):
        for beat in range(4):
            t = b * 4 + beat
            notes += [note(t, hat), note(t + swing, hat, 70)]
            notes.append(note(t, KICK if beat % 2 == 0 else SNARE))
    return sorted(notes, key=lambda n: n.tick)


def test_straight_rock() -> None:
    f = analyse(rock(), 8 * Q, (4, 4))
    assert not f.swung
    assert f.backbeat and not f.half_time and not f.four_on_floor
    assert f.pieces == ["kick", "snare", "hats"]
    assert f.density == pytest.approx(3.0)  # 24 hits in 8 beats
    assert f.syncopation == 0


def test_swing_is_detected() -> None:
    f = analyse(rock(swing=2 / 3), 8 * Q, (4, 4))
    assert f.swung
    assert f.swing8 == pytest.approx(0.667, abs=0.01)
    assert f.triplet_share == 0  # swung 8ths alone are not triplets


def test_four_on_the_floor_and_half_time() -> None:
    four = [note(b, KICK) for b in range(8)] + [note(b + 0.5, HAT) for b in range(8)]
    assert analyse(four, 8 * Q, (4, 4)).four_on_floor
    half = [note(b * 4, KICK) for b in range(2)] + [note(b * 4 + 2, SNARE) for b in range(2)]
    f = analyse(half, 8 * Q, (4, 4))
    assert f.half_time and not f.backbeat


def test_linear_and_ghost_notes() -> None:
    linear = [note(i / 4, (KICK, SNARE, HAT, TOM)[i % 4]) for i in range(32)]
    assert analyse(linear, 8 * Q, (4, 4)).simultaneity == 0
    ghosts = rock() + [note(b + 0.75, SNARE, 30) for b in range(8)]
    f = analyse(ghosts, 8 * Q, (4, 4))
    assert f.ghost_share == pytest.approx(8 / 12, abs=1e-3)


def test_feature_tags() -> None:
    f = analyse(rock(swing=2 / 3, hat=RIDE), 8 * Q, (4, 4))
    names = {t.tag for t in feature_tags(f, (4, 4), "groove", 24)}
    assert {"swung", "ride"} <= names
    assert "odd-meter" in {t.tag for t in feature_tags(f, (7, 8), "groove", 24)}
    assert "four-on-the-floor" not in names


def test_rule_tags_and_merge() -> None:
    tags = rule_tags("Hip Hop", "Swung")
    assert [t.tag for t in tags] == ["hip-hop", "swung"]
    merged = merge(tags, [Tag("swung", "feature", 0.7), Tag("busy", "feature", 0.9)])
    assert [(t.tag, t.source) for t in merged] == [
        ("busy", "feature"),
        ("hip-hop", "rule"),
        ("swung", "rule"),
    ]


def test_pattern_key_ignores_repeats_and_velocity() -> None:
    one = rock(bars=1)
    two = rock(bars=2)
    louder = [Note(n.tick, n.key, 127, n.dur) for n in two]
    assert pattern_key(one, 4 * Q, (4, 4)) == pattern_key(two, 8 * Q, (4, 4))
    assert pattern_key(two, 8 * Q, (4, 4)) == pattern_key(louder, 8 * Q, (4, 4))
    assert pattern_key(rock(swing=2 / 3), 8 * Q, (4, 4)) != pattern_key(two, 8 * Q, (4, 4))


def test_neighbours_stay_within_a_meter() -> None:
    vectors = [
        onset_vector(rock(), 8 * Q, (4, 4)),
        onset_vector(rock(swing=0.55), 8 * Q, (4, 4)),
        onset_vector(rock(swing=2 / 3, hat=RIDE), 8 * Q, (4, 4)),
        onset_vector([note(b, KICK) for b in range(6)], 6 * Q, (3, 4)),
    ]
    assert np.linalg.norm(vectors[0]) == pytest.approx(1)
    near = neighbours(["a", "b", "c", "d"], [(4, 4)] * 3 + [(3, 4)], vectors)
    assert near["a"][0][0] == "b"
    assert near["d"] == []
    assert all(o != "d" for o, _ in near["a"])
