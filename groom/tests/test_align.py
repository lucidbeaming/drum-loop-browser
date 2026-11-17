from pathlib import Path

import numpy as np
import pytest

from groom import align
from groom.align import LoopOnsets, demo_tempo, fits_whole_bars
from groom.fixtures import DEMOS, FIXTURES, FixtureLoop
from groom.midi import bar_ticks, fit_to_length, parse_midi
from groom.tempo import analyse_demo


def onsets(library: Path, fx: FixtureLoop) -> LoopOnsets:
    fitted = fit_to_length(parse_midi(library / fx.rel_path).notes, fx.bars * bar_ticks(fx.meter))
    return LoopOnsets.of(fitted.notes, fitted.length, fx.meter)


def test_fits_whole_bars() -> None:
    assert fits_whole_bars(19.2, 100, 4)  # 8 bars of 4/4
    assert fits_whole_bars(23.3, 103, 5)  # 8 bars of 5/4, to the hundredth of a second
    assert not fits_whole_bars(19.2, 101, 4)
    assert not fits_whole_bars(0.5, 100, 4)  # less than a bar


@pytest.mark.parametrize("demo", DEMOS, ids=lambda d: d.rel_path)
def test_demo_tempo(library: Path, demo: object) -> None:
    from groom.fixtures import FixtureDemo

    assert isinstance(demo, FixtureDemo)
    fx = next(f for f in FIXTURES if f.rel_path == demo.loop)
    a = analyse_demo(library / demo.rel_path)
    t = demo_tempo(a.envelope, a.duration, [onsets(library, fx)])
    assert t.strong
    # the click-track demos are as regular at double time as at their own tempo
    assert t.bpm in (demo.bpm, 2 * demo.bpm)


def test_one_pass_breaks_an_octave_tie(library: Path) -> None:
    demo, fx = DEMOS[3], FIXTURES[9]  # 2 bars, 4 passes, 96 BPM: 8 bars in 20 s
    a = analyse_demo(library / demo.rel_path)
    loops = [onsets(library, fx)]
    assert demo_tempo(a.envelope, a.duration, loops).bpm == 192
    t = demo_tempo(a.envelope, a.duration, loops, one_pass=60 * 8 * 4 / a.duration)
    assert t.strong and t.bpm == 96


def test_identifies_the_loop_a_demo_plays(library: Path) -> None:
    played, sibling = FIXTURES[10], FIXTURES[11]
    a = analyse_demo(library / DEMOS[4].rel_path)
    t = demo_tempo(a.envelope, a.duration, [onsets(library, sibling), onsets(library, played)])
    assert t.loop == 1
    assert t.loop_margin >= 0.05


def test_noise_is_not_strong(library: Path) -> None:
    env = np.random.default_rng(1).random(int(20 * align.FPS))
    t = demo_tempo(env, 20.0, [onsets(library, FIXTURES[0])])
    assert not t.strong or t.score < align.MIN_SCORE
