"""`groom run`: scan → resolve → verify tempo → normalise → write catalogue and reports."""

import csv
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from groom.catalogue import (
    Demo,
    Loop,
    Scan,
    check_tempo,
    collect_candidates,
    dedupe,
    normalise,
    resolve_structure,
    scan_library,
)
from groom.midi import build_normalised
from groom.paths import Paths
from groom.rules import DEFAULT_RULES_PATH, load_rules
from groom.store import write_catalogue
from groom.tempo import DemoAnalysis, analyse_demo

BPM_CHECKS = ("confirmed", "unverified", "conflict", "audio-only", "unknown")


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


def run(paths: Paths, rules_path: Path = DEFAULT_RULES_PATH, audio: bool = True) -> RunResult:
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
    loops = dedupe(scan.loops)

    _write_normalised(paths.data / "normalised", loops)
    write_catalogue(
        paths.data / "catalogue.sqlite",
        loops,
        scan.groups.values(),
        scan.demos,
        {name: r.title for name, r in rules.items()},
    )
    result = RunResult(scan, loops)
    _write_reports(paths.reports, result)
    return result


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
