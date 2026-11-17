"""Tempo from lining a loop's MIDI up with a demo's audio.

At a trial BPM the loop's hits (tiled, starting at each of its bars) become an onset curve,
which is slid along the demo's onset-strength envelope; the best Pearson correlation is the
loop's score at that BPM. Scanning a grid of BPMs gives a curve whose peak is the demo tempo.

Peaks alone are not trusted: a neighbouring tempo often scores almost as well. A tempo counts
as strong only if a second, independent check agrees: the vendor's tempos are whole BPMs and
each demo lasts a whole number of bars, so the demo's length must fit a whole number of bars at
a whole BPM within a beat or so of the peak.

Double and half time often score nearly as well as the true tempo (a demo checked against its
own named tempo was right every time, but by margins as thin as 1%). When a demo's name says how
many bars it plays, one pass of those bars breaks such a tie.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from groom.features import FAMILIES
from groom.midi import NORMALISED_PPQ, Note
from groom.tempo import HOP, SR

VERSION = 2  # bump when a change here alters results, to invalidate cached alignments
FPS = SR / HOP
COARSE = np.arange(60.0, 220.01, 1.0)  # vendor tempos are 70-210; lower invites half-time errors
FINE_STEP = 0.25
PEAKS = 6  # coarse peaks refined
MAX_WINDOW = 12.0  # seconds of demo matched at a time
MAX_STARTS = 16  # bars a window may start on
SMOOTH = 1.2  # frames
NEAR_PEAK = 1.0  # BPM: how far a whole-BPM tempo may be from the alignment peak
FIT_SECONDS = 0.03  # how closely the demo length must fit whole bars at that tempo
MIN_SCORE = 0.6
OCTAVE_TIE = 0.9  # an octave scoring at least this share of the peak's score ties with it

Floats = npt.NDArray[np.float64]

_SNARES = frozenset({38, 40})
_KERNEL = np.exp(-0.5 * (np.arange(-5, 6) / SMOOTH) ** 2)
_KERNEL /= _KERNEL.sum()


def _weight(key: int) -> float:
    if key in FAMILIES["kick"] or key in _SNARES:
        return 1.0
    if key in FAMILIES["toms"]:
        return 0.8
    if key in FAMILIES["snare"]:
        return 0.7  # side stick, clap
    return 0.5  # cymbals and percussion are weak, smeared onsets


@dataclass(frozen=True)
class LoopOnsets:
    beats: Floats  # hit positions in beats
    weights: Floats
    loop_beats: float
    beats_per_bar: float

    @classmethod
    def of(cls, notes: list[Note], length: int, meter: tuple[int, int]) -> "LoopOnsets":
        return cls(
            np.array([n.tick / NORMALISED_PPQ for n in notes]),
            np.array([_weight(n.key) * n.vel / 127 for n in notes]),
            length / NORMALISED_PPQ,
            meter[0] * 4 / meter[1],
        )


def _curves(loop: LoopOnsets, bpm: float, seconds: float) -> list[Floats]:
    """Onset curves ``seconds`` long at ``bpm``: the loop tiled, starting at each bar."""
    frames_per_beat = 60 / bpm * FPS
    n = int(seconds * FPS)
    span = seconds * bpm / 60
    reps = int(np.ceil((span + loop.loop_beats) / loop.loop_beats)) + 1
    tiled = (loop.beats[None, :] + loop.loop_beats * np.arange(reps)[:, None]).ravel()
    weights = np.tile(loop.weights, reps)
    out = []
    for start in np.arange(0, loop.loop_beats, loop.beats_per_bar)[:MAX_STARTS]:
        rel = tiled - start
        keep = (rel >= 0) & (rel < span)
        curve = np.zeros(n + 1)
        np.add.at(
            curve, np.round(rel[keep] * frames_per_beat).astype(int).clip(0, n), weights[keep]
        )
        out.append(np.convolve(curve, _KERNEL, "same"))
    return out


def _slide(env: Floats, short: Floats) -> float:
    """Best Pearson correlation of ``short`` with any same-length stretch of ``env``."""
    width = len(short)
    if width >= len(env) or width < 8:
        return 0.0
    centred = short - short.mean()
    norm = np.linalg.norm(centred)
    if norm == 0:
        return 0.0
    size = len(env) + width - 1
    dots = np.fft.irfft(np.fft.rfft(env, size) * np.conj(np.fft.rfft(centred, size)), size)
    dots = dots[: len(env) - width + 1]  # correlation at each start of a full-width stretch
    s1 = np.cumsum(np.r_[0, env])
    s2 = np.cumsum(np.r_[0, env * env])
    sums, squares = s1[width:] - s1[:-width], s2[width:] - s2[:-width]
    spread = np.sqrt(np.maximum(squares - sums * sums / width, 1e-9))
    return float((dots / (spread * norm)).max())


def score(env: Floats, loop: LoopOnsets, bpm: float) -> float:
    seconds = min(MAX_WINDOW, 0.9 * len(env) / FPS)
    return max(_slide(env, c) for c in _curves(loop, bpm, seconds))


@dataclass(frozen=True)
class DemoTempo:
    bpm: float  # a whole BPM when strong, else the alignment peak
    score: float
    strong: bool
    loop: int  # index of the loop that lines up best at ``bpm``
    loop_margin: float  # its score minus the next loop's (0 with one loop)


def demo_tempo(
    env: Floats, duration: float, loops: list[LoopOnsets], one_pass: float | None = None
) -> DemoTempo:
    """The tempo a demo plays at, given the loops it may play and, if known, the tempo at which
    the demo's length is one pass of the bars its name says it plays."""

    def best(bpm: float) -> float:
        return max(score(env, lp, bpm) for lp in loops)

    curve = {float(b): best(b) for b in COARSE}
    for peak in sorted(curve, key=curve.__getitem__, reverse=True)[:PEAKS]:
        for b in np.arange(peak - 0.75, peak + 0.76, FINE_STEP):
            curve.setdefault(round(float(b), 2), best(b))
    peak = max(curve, key=curve.__getitem__)
    if one_pass is not None and abs(one_pass - peak) > NEAR_PEAK:
        for octave in (peak * 2, peak / 2):
            if abs(octave - one_pass) <= NEAR_PEAK and COARSE[0] <= octave <= COARSE[-1]:
                curve[octave] = best(octave)
                if curve[octave] >= OCTAVE_TIE * curve[peak]:
                    peak = octave

    fits = [
        b for b in range(round(peak - NEAR_PEAK), round(peak + NEAR_PEAK) + 1)
        if abs(b - peak) <= NEAR_PEAK and fits_whole_bars(duration, b, loops[0].beats_per_bar)
    ]  # fmt: skip
    strong = bool(fits) and curve[peak] >= MIN_SCORE
    bpm = float(min(fits, key=lambda b: abs(b - peak))) if strong else peak

    by_loop = sorted(((score(env, lp, bpm), i) for i, lp in enumerate(loops)), reverse=True)
    margin = by_loop[0][0] - by_loop[1][0] if len(by_loop) > 1 else 0.0
    return DemoTempo(bpm, round(curve[peak], 3), strong, by_loop[0][1], round(margin, 3))


def fits_whole_bars(duration: float, bpm: float, beats_per_bar: float) -> bool:
    bar = 60 * beats_per_bar / bpm
    bars = round(duration / bar)
    return bars >= 1 and abs(duration - bars * bar) <= FIT_SECONDS
