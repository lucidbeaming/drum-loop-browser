"""Per-loop rhythm features, the onset vectors used for similarity, and near-duplicates.

Everything here works on normalised notes (480 PPQ, quarter-note beats). Positions inside a beat
are "phases": 0 is on the beat, 0.5 the off-beat 8th, 0.667 a swung (triplet) 8th.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

import numpy as np
import numpy.typing as npt

from groom.midi import NORMALISED_PPQ, Note, bar_ticks

FAMILIES: dict[str, frozenset[int]] = {
    "kick": frozenset({35, 36}),
    "snare": frozenset({37, 38, 39, 40}),
    "hats": frozenset({42, 44, 46}),
    "toms": frozenset({41, 43, 45, 47, 48, 50}),
    "crash": frozenset({49, 52, 55, 57}),
    "ride": frozenset({51, 53, 59}),
}
FAMILY_NAMES = (*FAMILIES, "perc")
BACKBEAT_SNARES = frozenset({38, 39, 40})
STEPS_PER_BEAT = 12  # 16ths and 8th-note triplets both land on this grid
COMMON_METERS = {(4, 4), (3, 4), (2, 4), (6, 8), (12, 8)}

ON_BEAT = 1 / 16  # beats: a hit this close to a grid point counts as on it
GHOST_RATIO = 0.5  # a snare hit at most this fraction of the loop's loudest snare is a ghost


def family(key: int) -> str:
    return next((name for name, keys in FAMILIES.items() if key in keys), "perc")


Vector = npt.NDArray[np.float64]


@dataclass
class Features:
    pieces: list[str]  # families present
    density: float  # hits per quarter-note beat
    density_by_piece: dict[str, float]
    swing8: float | None  # median phase of off-beat 8ths (0.5 straight, ~0.67 swung)
    swing16: float | None  # the same for off-beat 16ths, within each 8th
    triplet_share: float  # share of off-beat hits on 8th-note triplet positions
    syncopation: float  # share of kick/snare hits off the meter's beats
    simultaneity: float  # share of hit instants with more than one drum (0 = linear)
    velocity_mean: float
    velocity_range: int
    ghost_share: float  # share of snare hits far softer than the loudest (ghost notes)
    four_on_floor: bool
    backbeat: bool
    half_time: bool
    vector: Vector = field(repr=False)  # one bar, per family, for similarity

    @property
    def swung(self) -> bool:
        return any(s is not None and s >= 0.58 for s in (self.swing8, self.swing16))


def _phase(tick: int, per_beat: float = 1.0) -> float:
    return (tick / NORMALISED_PPQ * per_beat) % 1.0


def _near(value: float, target: float) -> bool:
    return abs(value - target) <= ON_BEAT


def _swing(phases: list[float]) -> float | None:
    """Median phase of hits between a straight off-beat (0.5) and a hard swing (0.72)."""
    offbeats = [p for p in phases if 0.45 <= p <= 0.72]
    return round(median(offbeats), 3) if len(offbeats) >= 4 else None


def analyse(notes: list[Note], length: int, meter: tuple[int, int]) -> Features:
    beats = length / NORMALISED_PPQ
    bar = bar_ticks(meter)
    bars = max(1, length // bar)
    fams = [family(n.key) for n in notes]
    by_family: dict[str, int] = defaultdict(int)
    for f in fams:
        by_family[f] += 1

    phases = [_phase(n.tick) for n in notes]
    off = [p for p in phases if not (_near(p, 0) or _near(p, 1))]
    triplets = [p for p in off if _near(p, 1 / 3) or _near(p, 2 / 3)]
    # 8th-note swing puts hits at 2/3 but never at 1/3; a 1/3 hit means real triplets
    triplet_share = len(triplets) / len(off) if off and any(_near(p, 1 / 3) for p in off) else 0.0

    unit = 4 / meter[1]  # beats per meter unit
    kick_snare = [n for n, f in zip(notes, fams, strict=True) if f in ("kick", "snare")]
    syncopated = [n for n in kick_snare if not _on_grid(n.tick, unit)]

    instants: dict[int, int] = defaultdict(int)
    for n in notes:
        instants[round(n.tick / 10)] += 1
    multi = sum(1 for c in instants.values() if c > 1)

    snares = [n for n in notes if n.key in BACKBEAT_SNARES]
    vels = [n.vel for n in notes] or [0]
    return Features(
        pieces=[f for f in FAMILY_NAMES if by_family.get(f)],
        density=round(len(notes) / beats, 3),
        density_by_piece={f: round(c / beats, 3) for f, c in sorted(by_family.items())},
        swing8=_swing(phases),
        swing16=_swing([_phase(n.tick, 2) for n in notes]),
        triplet_share=round(triplet_share, 3),
        syncopation=round(len(syncopated) / len(kick_snare), 3) if kick_snare else 0.0,
        simultaneity=round(multi / len(instants), 3) if instants else 0.0,
        velocity_mean=round(sum(vels) / len(vels), 1),
        velocity_range=max(vels) - min(vels),
        ghost_share=_ghost_share(snares),
        four_on_floor=_four_on_floor(notes, length, meter),
        backbeat=_snare_on(snares, bars, bar, meter, (1, 3)),
        half_time=_snare_on(snares, bars, bar, meter, (2,))
        and not _snare_on(snares, bars, bar, meter, (1, 3)),
        vector=onset_vector(notes, length, meter),
    )


def _ghost_share(snares: list[Note]) -> float:
    if not snares:
        return 0.0
    loudest = max(n.vel for n in snares)
    return round(sum(n.vel <= GHOST_RATIO * loudest for n in snares) / len(snares), 3)


def _on_grid(tick: int, unit: float) -> bool:
    pos = tick / NORMALISED_PPQ / unit
    return abs(pos - round(pos)) * unit <= ON_BEAT


def _four_on_floor(notes: list[Note], length: int, meter: tuple[int, int]) -> bool:
    """A kick on (nearly) every quarter-note beat, in a meter counted in quarters."""
    if meter[1] != 4:
        return False
    kicks = {round(n.tick / NORMALISED_PPQ) for n in notes if n.key in FAMILIES["kick"]
             if _near(_phase(n.tick), 0) or _near(_phase(n.tick), 1)}  # fmt: skip
    beats = length // NORMALISED_PPQ
    return beats >= 4 and len(kicks & set(range(beats))) >= 0.9 * beats


def _snare_on(
    snares: list[Note], bars: int, bar: int, meter: tuple[int, int], beats: tuple[int, ...]
) -> bool:
    """Snare on the given (0-based) beats in at least 3/4 of the bars of a 4/4 loop."""
    if meter != (4, 4) or not snares:
        return False
    hit = {(n.tick // bar, round((n.tick % bar) / NORMALISED_PPQ)) for n in snares
           if _near(_phase(n.tick), 0) or _near(_phase(n.tick), 1)}  # fmt: skip
    good = sum(all((b, beat) in hit for beat in beats) for b in range(bars))
    return good >= 0.75 * bars


def onset_vector(notes: list[Note], length: int, meter: tuple[int, int]) -> Vector:
    """The loop folded onto one bar, per family, at 12 steps per beat, slightly blurred and
    L2-normalised. Comparable only between loops in the same meter."""
    bar = bar_ticks(meter)
    steps = round(bar / NORMALISED_PPQ * STEPS_PER_BEAT)
    grid = np.zeros((len(FAMILY_NAMES), steps))
    for n in notes:
        step = round(n.tick % bar / NORMALISED_PPQ * STEPS_PER_BEAT) % steps
        grid[FAMILY_NAMES.index(family(n.key)), step] += n.vel / 127
    blurred = 0.6 * grid + 0.2 * (np.roll(grid, 1, axis=1) + np.roll(grid, -1, axis=1))
    flat = blurred.ravel()
    norm = float(np.linalg.norm(flat))
    return flat / norm if norm else flat


def pattern_key(notes: list[Note], length: int, meter: tuple[int, int]) -> tuple[object, ...]:
    """Which drums hit where (to the 12-per-beat grid), ignoring velocity, micro-timing and
    repeats: two loops with the same key play the same pattern."""
    hits = sorted({(round(n.tick / NORMALISED_PPQ * STEPS_PER_BEAT), n.key) for n in notes})
    total = round(length / NORMALISED_PPQ * STEPS_PER_BEAT)
    bar = round(bar_ticks(meter) / NORMALISED_PPQ * STEPS_PER_BEAT)
    # shortest whole-bar period the pattern repeats with
    for period in range(bar, total + 1, bar):
        if total % period:
            continue
        first = [(s, k) for s, k in hits if s < period]
        if all((s % period, k) in set(first) for s, k in hits) and len(hits) == len(first) * (
            total // period
        ):
            return (meter, period, tuple(first))
    return (meter, total, tuple(hits))


def neighbours(
    ids: list[str], meters: list[tuple[int, int]], vectors: list[Vector], k: int = 10,
    min_score: float = 0.5,
) -> dict[str, list[tuple[str, float]]]:  # fmt: skip
    """Each loop's k most similar loops (cosine of onset vectors), within the same meter."""
    out: dict[str, list[tuple[str, float]]] = {}
    by_meter: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, m in enumerate(meters):
        by_meter[m].append(i)
    for members in by_meter.values():
        mat = np.stack([vectors[i] for i in members])
        sims = mat @ mat.T
        np.fill_diagonal(sims, -1.0)
        for row, i in enumerate(members):
            order = np.argsort(sims[row])[::-1][:k]
            out[ids[i]] = [
                (ids[members[j]], round(float(sims[row, j]), 4))
                for j in order
                if sims[row, j] >= min_score
            ]
    return out
