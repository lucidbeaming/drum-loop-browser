"""Checking BPM candidates against the vendor's WAV demos.

The MIDI files carry no reliable tempo of their own, so the demos are the only independent
evidence. Two checks are used:

* **Periodicity support:** a looped groove makes the onset envelope repeat every beat, bar and
  two bars. For a candidate BPM we read the envelope's autocorrelation at those lags and compare
  it with the best score any tempo achieves on that demo. Half and double time count as support.
* **Duration check:** when a demo plays exactly one loop (repeated a whole number of times),
  its length gives the tempo directly: bpm = 60 * beats * repeats / seconds.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import numpy.typing as npt
import soundfile as sf

SR = 22050
HOP = 256
GRID = np.arange(40.0, 260.5, 0.5)
OCTAVES = (1.0, 2.0, 0.5)
CONFIRM_RATIO = 0.85  # candidate support / best support on the demo
DURATION_TOLERANCE_BPM = 1.0

Floats = npt.NDArray[np.float64]


@dataclass
class DemoAnalysis:
    path: Path
    duration: float
    autocorr: Floats
    _best: dict[float, float] = field(default_factory=dict, repr=False)

    def score(self, bpm: float, beats_per_bar: float) -> float:
        beat = 60.0 / bpm
        bar = beat * beats_per_bar
        return 0.2 * self._at(beat) + 0.4 * self._at(bar) + 0.4 * self._at(2 * bar)

    def support(self, bpm: float, beats_per_bar: float) -> float:
        """Best score of ``bpm`` (or half/double) relative to the best score of any tempo."""
        best = self._best.get(beats_per_bar)
        if best is None:
            best = self._best[beats_per_bar] = max(self.score(b, beats_per_bar) for b in GRID)
        if best <= 0:
            return 0.0
        own = max(
            self.score(bpm * k, beats_per_bar) for k in OCTAVES if GRID[0] <= bpm * k <= GRID[-1]
        )
        return round(own / best, 3)

    def estimate(self, beats_per_bar: float, low: float = 70.0, high: float = 180.0) -> float:
        """Blind estimate in [low, high): weak (octave errors are common); a fallback only."""
        grid = GRID[(low <= GRID) & (high > GRID)]
        scores = np.array([self.score(b, beats_per_bar) for b in grid])
        return float(grid[int(scores.argmax())])

    def _at(self, seconds: float) -> float:
        lag = int(seconds * SR / HOP)
        if lag + 1 >= len(self.autocorr) or lag < 1:
            return 0.0
        return float(self.autocorr[max(1, lag - 2) : lag + 3].max())


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def analyse_demo(path: Path, cache_dir: Path | None = None) -> DemoAnalysis:
    """Onset-envelope autocorrelation of a demo, cached by file content hash."""
    cache = cache_dir / f"{_file_hash(path)}.npz" if cache_dir else None
    if cache and cache.exists():
        data = np.load(cache)
        return DemoAnalysis(path, float(data["duration"]), data["autocorr"])

    duration = float(sf.info(str(path)).duration)
    y, _ = librosa.load(path, sr=SR, mono=True)
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP).astype(np.float64)
    env -= env.mean()
    n = len(env)
    spec = np.fft.rfft(env, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    autocorr = ac / ac[0] if ac[0] > 0 else ac

    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, duration=duration, autocorr=autocorr)
    return DemoAnalysis(path, duration, autocorr)


def duration_bpm(seconds: float, loop_beats: float, near: float, max_repeats: int = 8) -> float:
    """Tempo implied by a demo of one loop repeated n times, choosing n closest to ``near``."""
    options = [60.0 * loop_beats * n / seconds for n in range(1, max_repeats + 1)]
    return min(options, key=lambda b: abs(b - near))


def duration_agrees(seconds: float, loop_beats: float, bpm: float) -> bool:
    return abs(duration_bpm(seconds, loop_beats, bpm) - bpm) <= DURATION_TOLERANCE_BPM
