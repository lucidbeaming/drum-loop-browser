"""Optional audio renders (`groom run --render`): play each normalised loop through the preview
SoundFont with the FluidSynth command-line tool and flag loops that come out silent or clip.

Uses the `fluidsynth` program (Homebrew: ``brew install fluid-synth``), not a Python binding.
Results are cached by loop ID, tempo and SoundFont, so only new loops are rendered on later runs.
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 44100
GAIN = 0.2  # FluidSynth's default
SILENT_PEAK = 1e-3
CLIP_PEAK = 0.99


@dataclass(frozen=True)
class Render:
    peak: float
    rms: float

    @property
    def silent(self) -> bool:
        return self.peak < SILENT_PEAK

    @property
    def clips(self) -> bool:
        return self.peak >= CLIP_PEAK


def fluidsynth() -> str | None:
    return shutil.which("fluidsynth")


def render(midi: Path, soundfont: Path, program: str = "fluidsynth") -> Render:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "out.wav"
        subprocess.run(
            [program, "-ni", "-q", "-g", str(GAIN), "-r", str(SAMPLE_RATE), "-F", str(wav),
             str(soundfont), str(midi)],
            check=True, capture_output=True,
        )  # fmt: skip
        audio, _ = sf.read(wav, dtype="float32")
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    return Render(round(peak, 4), round(rms, 5))


def render_all(
    midis: dict[str, Path], soundfont: Path, cache_dir: Path, workers: int = 8
) -> dict[str, Render]:
    """Render each file (cache key, e.g. loop ID and tempo → MIDI file), reusing cached results."""
    program = fluidsynth()
    if program is None:
        raise RuntimeError("the fluidsynth program is not installed (brew install fluid-synth)")
    sf_hash = hashlib.sha1(soundfont.read_bytes()).hexdigest()[:12]
    cache = cache_dir / f"renders-{sf_hash}.json"
    known: dict[str, dict[str, float]] = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [lid for lid in midis if lid not in known]
    with ThreadPoolExecutor(workers) as pool:
        for lid, result in zip(
            todo, pool.map(lambda lid: render(midis[lid], soundfont, program), todo), strict=True
        ):
            known[lid] = asdict(result)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(known))
    return {lid: Render(**known[lid]) for lid in midis}
