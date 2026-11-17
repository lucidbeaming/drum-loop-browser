"""`groom run`: scan → resolve → verify tempo → normalise → analyse → tag → QC → write."""

import csv
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from groom import align
from groom.align import DemoTempo, Floats, LoopOnsets
from groom.catalogue import (
    Demo,
    Group,
    Loop,
    Scan,
    align_tempos,
    check_tempo,
    collect_candidates,
    dedupe,
    normalise,
    resolve_structure,
    scan_library,
)
from groom.features import analyse, neighbours, pattern_key
from groom.midi import build_normalised
from groom.paths import Paths
from groom.render import render_all
from groom.rules import DEFAULT_RULES_PATH, load_rules
from groom.soundfont import Kit, drum_kits
from groom.store import write_catalogue
from groom.tags import feature_tags, merge, rule_tags
from groom.tempo import DemoAnalysis, analyse_demo

BPM_CHECKS = ("confirmed", "audio-matched", "unverified", "conflict", "audio-only", "unknown")
PREVIEW_SOUNDFONT = "lucidrum.sf2"
STANDARD_KIT = 0  # GS program of the kit a file with no program change plays
NEAR_DUPLICATE = 0.995  # onset-vector cosine


@dataclass
class RunResult:
    scan: Scan
    loops: list[Loop]  # deduplicated

    def coverage(self) -> list[dict[str, object]]:
        rows = []
        for pack in sorted({lp.group.pack for lp in self.loops}):
            pl = [lp for lp in self.loops if lp.group.pack == pack]
            checks = Counter(lp.bpm_check for lp in pl)
            rows.append(
                {
                    "pack": pack,
                    "loops": len(pl),
                    "bpm_known": sum(lp.bpm is not None for lp in pl),
                    **{c: checks.get(c, 0) for c in BPM_CHECKS},
                    "meter_from_names": sum(lp.meter_source in ("folder", "filename") for lp in pl),
                    "review": sum(lp.status == "review" for lp in pl),
                }
            )
        return rows


class CachedAligner:
    """``catalogue.Aligner`` over the demo analyses, caching results in a JSON file. Demo tempos
    are slow (a BPM scan per demo), so ``prepare`` works them out in parallel first."""

    def __init__(self, analyse: Callable[[Demo], DemoAnalysis | None], cache: Path) -> None:
        self.analyse = analyse
        self.cache = cache
        try:
            self.known: dict[str, object] = json.loads(cache.read_text())
        except (OSError, ValueError):
            self.known = {}

    def _tempo_key(self, a: DemoAnalysis, loops: list[Loop]) -> str:
        ids = hashlib.sha1(",".join(lp.loop_id for lp in loops).encode()).hexdigest()[:16]
        return f"v{align.VERSION}:tempo:{a.key}:{ids}"

    def prepare(self, jobs: list[tuple[Demo, list[Loop]]]) -> None:
        todo: dict[str, tuple[Floats, float, list[LoopOnsets], float | None]] = {}
        for demo, loops in jobs:
            a = self.analyse(demo)
            if a is not None and loops and (key := self._tempo_key(a, loops)) not in self.known:
                todo[key] = _tempo_args(demo, a, loops)
        if not todo:
            return
        with ProcessPoolExecutor() as pool:
            results = pool.map(align.demo_tempo, *zip(*todo.values(), strict=True))
            for key, result in zip(todo, results, strict=True):
                self.known[key] = asdict(result)

    def tempo(self, demo: Demo, loops: list[Loop]) -> DemoTempo | None:
        a = self.analyse(demo)
        if a is None or not loops:
            return None
        key = self._tempo_key(a, loops)
        if key not in self.known:
            self.known[key] = asdict(align.demo_tempo(*_tempo_args(demo, a, loops)))
        return DemoTempo(**self.known[key])  # type: ignore[arg-type]

    def score(self, demo: Demo, loop: Loop, bpm: float) -> float:
        a = self.analyse(demo)
        if a is None:
            return 0.0
        key = f"v{align.VERSION}:score:{a.key}:{loop.loop_id}:{bpm:g}"
        if key not in self.known:
            self.known[key] = round(align.score(a.envelope, _onsets(loop), bpm), 4)
        return float(self.known[key])  # type: ignore[arg-type]

    def save(self) -> None:
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps(self.known))


def _onsets(loop: Loop) -> LoopOnsets:
    assert loop.fitted is not None
    return LoopOnsets.of(loop.fitted.notes, loop.fitted.length, loop.meter)


def _tempo_args(
    demo: Demo, a: DemoAnalysis, loops: list[Loop]
) -> tuple[Floats, float, list[LoopOnsets], float | None]:
    """Arguments of ``align.demo_tempo``, with the one-pass tempo of a demo named by its bars."""
    bars = demo.fields.get("bars")
    one_pass = 60 * int(bars) * loops[0].beats_per_bar / a.duration if bars else None
    return a.envelope, a.duration, [_onsets(lp) for lp in loops], one_pass


def _alignment_jobs(groups: list[Group]) -> list[tuple[Demo, list[Loop]]]:
    """The demo tempos ``align_tempos`` will ask for (see there)."""
    jobs: list[tuple[Demo, list[Loop]]] = []
    for g in groups:
        doubtful = [lp for lp in g.loops if lp.bpm_check in ("audio-only", "conflict")]
        if doubtful:
            jobs += [(d, d.loops) for d in g.demos]
            jobs += [(d, [lp]) for lp in doubtful for d in lp.demos if d.scope == "file"]
    return jobs


def run(
    paths: Paths, rules_path: Path = DEFAULT_RULES_PATH, audio: bool = True, render: bool = False
) -> RunResult:
    rules = load_rules(rules_path)
    scan = scan_library(paths.library, rules)
    cache_dir = paths.data / "cache" / "tempo"
    analyses: dict[str, DemoAnalysis | None] = {}

    def analyse(demo: Demo) -> DemoAnalysis | None:
        if not audio:
            return None
        if demo.rel_path not in analyses:
            analyses[demo.rel_path] = analyse_demo(paths.library / demo.rel_path, cache_dir)
        return analyses[demo.rel_path]

    for loop in scan.loops:
        resolve_structure(loop)
        collect_candidates(loop)
        check_tempo(loop, analyse)
        normalise(loop)
    if audio:
        aligner = CachedAligner(analyse, cache_dir / "alignments.json")
        groups = list(scan.groups.values())
        aligner.prepare(_alignment_jobs(groups))
        align_tempos(groups, aligner)
        aligner.save()
    loops = dedupe(scan.loops)
    soundfont = paths.soundfonts / PREVIEW_SOUNDFONT
    kits = _load_kits(soundfont)
    analyse_loops(loops, kits)

    _write_normalised(paths.data / "normalised", loops)
    if render:
        check_renders(loops, paths.data / "normalised", soundfont, paths.data / "cache")
    write_catalogue(
        paths.data / "catalogue.sqlite",
        loops,
        scan.groups.values(),
        scan.demos,
        {name: r.title for name, r in rules.items()},
        kits,
    )
    result = RunResult(scan, loops)
    _write_reports(paths.reports, result)
    return result


def _load_kits(path: Path) -> list[Kit]:
    """The preview SoundFont's drum kits, or none if it isn't there (e.g. in CI)."""
    return drum_kits(path) if path.is_file() else []


def analyse_loops(loops: list[Loop], kits: list[Kit]) -> None:
    """Features, tags, similar loops, near-duplicates and the audibility check."""
    for lp in loops:
        assert lp.fitted is not None
        f = lp.features = analyse(lp.fitted.notes, lp.fitted.length, lp.meter)
        lp.tags = merge(
            rule_tags(lp.group.style, lp.value("feel")),
            feature_tags(f, lp.meter, lp.kind, len(lp.fitted.notes)),
        )

    near = neighbours(
        [lp.loop_id for lp in loops],
        [lp.meter for lp in loops],
        [lp.features.vector for lp in loops if lp.features],
    )
    by_id = {lp.loop_id: lp for lp in loops}
    for lp in loops:
        lp.similar = near.get(lp.loop_id, [])
    _flag_near_duplicates(loops, by_id)

    standard = next((k for k in kits if k.program == STANDARD_KIT), None)
    for lp in loops:
        assert lp.fitted is not None
        silent = sorted({n.key for n in lp.fitted.notes} - standard.keys) if standard else []
        if silent:
            lp.issues.append(f"no sound in the {standard.name} kit for notes {silent}")  # type: ignore[union-attr]


def check_renders(loops: list[Loop], normalised: Path, soundfont: Path, cache_dir: Path) -> None:
    """Render every loop with FluidSynth; a silent or clipping render is an issue to review."""
    files = {f"{lp.loop_id}@{lp.bpm}": normalised / f"{lp.loop_id}.mid" for lp in loops}
    renders = render_all(files, soundfont, cache_dir)
    for lp in loops:
        r = renders[f"{lp.loop_id}@{lp.bpm}"]
        if r.silent:
            lp.issues.append("renders silent with the preview SoundFont")
        elif r.clips:
            lp.issues.append(f"render clips (peak {r.peak:.2f})")


def _flag_near_duplicates(loops: list[Loop], by_id: dict[str, Loop]) -> None:
    """A loop that plays the same pattern as an earlier one (same hits, ignoring velocity and
    repeats), or is almost identical to it, goes to review; the earlier one stays as it is."""
    first_with: dict[tuple[object, ...], Loop] = {}
    seen: set[str] = set()
    for lp in loops:
        assert lp.fitted is not None
        key = pattern_key(lp.fitted.notes, lp.fitted.length, lp.meter)
        original = first_with.setdefault(key, lp)
        if original is lp:
            close = [by_id[o] for o, score in lp.similar if score >= NEAR_DUPLICATE and o in seen]
            original = close[0] if close and close[0].bars == lp.bars else lp
        if original is not lp:
            lp.issues.append(f"near-duplicate of {original.rel_path}")
        seen.add(lp.loop_id)


def _write_normalised(out: Path, loops: list[Loop]) -> None:
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for lp in loops:
        assert lp.fitted is not None
        build_normalised(lp.fitted, lp.meter, lp.bpm, lp.title).save(tmp / f"{lp.loop_id}.mid")
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        if not rows:
            return
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_reports(reports: Path, result: RunResult) -> None:
    _write_csv(reports / "coverage.csv", result.coverage())
    _write_csv(
        reports / "review.csv",
        [
            {
                "loop_id": lp.loop_id,
                "source": lp.rel_path,
                "bpm": lp.bpm,
                "bpm_check": lp.bpm_check,
                "candidates": "; ".join(
                    f"{c.bpm:g} {c.source} ({c.support if c.support is not None else '-'})"
                    for c in lp.candidates
                ),
                "issues": "; ".join(lp.issues),
            }
            for lp in result.loops
            if lp.status == "review"
        ],
    )
    _write_csv(
        reports / "previews.csv",
        [
            {
                "demo": d.rel_path,
                "scope": d.scope,
                "key": d.fields.get("key", ""),
                "bpm_in_name": d.fields.get("bpm", ""),
                "matched": len(d.targets),
                "targets": "; ".join(
                    result.scan.groups[t].rel_dir if d.scope == "group" else t for t in d.targets
                ),
            }
            for d in result.scan.demos
        ],
    )
