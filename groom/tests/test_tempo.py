from pathlib import Path

import pytest

from groom.fixtures import DEMOS
from groom.tempo import CONFIRM_RATIO, analyse_demo, duration_agrees, duration_bpm


@pytest.mark.parametrize("demo", DEMOS, ids=lambda d: d.rel_path)
def test_demo_supports_its_own_tempo(library: Path, demo: object) -> None:
    from groom.fixtures import FIXTURES, FixtureDemo

    assert isinstance(demo, FixtureDemo)
    loop = next(f for f in FIXTURES if f.rel_path == demo.loop)
    beats_per_bar = loop.meter[0] * 4 / loop.meter[1]
    a = analyse_demo(library / demo.rel_path)
    true = a.support(demo.bpm, beats_per_bar)
    assert true >= CONFIRM_RATIO
    assert a.support(demo.bpm * 2, beats_per_bar) >= CONFIRM_RATIO  # half/double time counts
    for wrong in (0.8, 0.91, 1.1, 1.2, 1.33, 1.5):
        assert a.support(demo.bpm * wrong, beats_per_bar) < true, wrong


def test_analysis_is_cached(library: Path, tmp_path: Path) -> None:
    demo = library / DEMOS[0].rel_path
    first = analyse_demo(demo, tmp_path)
    assert len(list(tmp_path.glob("*.npz"))) == 1
    again = analyse_demo(demo, tmp_path)
    assert again.duration == pytest.approx(first.duration)
    assert (again.autocorr == first.autocorr).all()


def test_duration_bpm() -> None:
    # 8 beats repeated 3 times in 12 s is 120 BPM
    assert duration_bpm(12.0, 8, near=118) == pytest.approx(120)
    assert duration_agrees(12.0, 8, 120.5)
    assert not duration_agrees(12.0, 8, 123)
