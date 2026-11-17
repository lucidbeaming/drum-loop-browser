"""Scan the library, resolve each loop's metadata, check tempos against demos, normalise."""

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from groom.midi import (
    LoopNotes,
    ParsedMidi,
    bar_ticks,
    fit_to_length,
    infer_bars,
    loop_id,
    parse_midi,
)
from groom.names import kind_from_token, meter_from_words, split_camel
from groom.rules import PackRules, best_matches
from groom.tempo import CONFIRM_RATIO, DemoAnalysis, duration_agrees, duration_bpm

SKIP_SUFFIXES = {".txt", ".webloc"}
SOURCE_PRIORITY = ("curation", "filename", "folder", "preview", "midi")
CONFIDENCE = {"confirmed": 0.95, "unverified": 0.6, "audio-only": 0.4, "conflict": 0.3}
SAME_BPM = 1.0


@dataclass
class Demo:
    rel_path: str
    pack: str
    fields: dict[str, str]
    scope: str
    targets: list[str] = field(default_factory=list)  # group ids or source rel paths
    analysis: DemoAnalysis | None = None

    @property
    def bpm(self) -> float | None:
        return float(self.fields["bpm"]) if "bpm" in self.fields else None


@dataclass
class Group:
    group_id: str
    pack: str
    rel_dir: str
    fields: dict[str, str]
    loops: list["Loop"] = field(default_factory=list)
    demos: list[Demo] = field(default_factory=list)

    @property
    def style(self) -> str:
        raw = self.fields.get("style") or self.fields.get("meter") or self.rel_dir.split("/")[-1]
        return split_camel(raw)

    def field_value(self, name: str) -> str | None:
        """A group field, or the most common value of that field among its files."""
        if name in self.fields:
            return self.fields[name]
        values = Counter(lp.file_fields[name] for lp in self.loops if name in lp.file_fields)
        return values.most_common(1)[0][0] if values else None


@dataclass
class Candidate:
    bpm: float
    source: str
    support: float | None = None
    method: str | None = None  # "periodicity" or "duration"


@dataclass
class Loop:
    rel_path: str
    src_sha1: str
    group: Group
    file_fields: dict[str, str]
    parsed: ParsedMidi
    issues: list[str] = field(default_factory=list)  # need review
    demos: list[Demo] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)  # informational only

    meter: tuple[int, int] = (4, 4)
    meter_source: str = "default"
    bars: int = 1
    bars_source: str = "computed"
    kind: str = "groove"
    candidates: list[Candidate] = field(default_factory=list)
    bpm: float | None = None
    bpm_source: str = "unknown"
    bpm_check: str = "unknown"
    fitted: LoopNotes | None = None
    loop_id: str = ""
    also_at: list[str] = field(default_factory=list)

    @property
    def stem(self) -> str:
        return Path(self.rel_path).stem

    @property
    def title(self) -> str:
        return split_camel(self.stem)

    @property
    def beats_per_bar(self) -> float:
        return self.meter[0] * 4 / self.meter[1]

    @property
    def loop_beats(self) -> float:
        return self.bars * self.beats_per_bar

    def value(self, name: str) -> str | None:
        return self.file_fields.get(name) or self.group.fields.get(name)

    @property
    def status(self) -> str:
        if self.bpm_check in ("conflict", "audio-only", "unknown") or self.issues:
            return "review"
        return "ok"

    @property
    def bpm_confidence(self) -> float:
        return CONFIDENCE.get(self.bpm_check, 0.0)


@dataclass
class Scan:
    groups: dict[str, Group]
    loops: list[Loop]
    demos: list[Demo]
    unknown_packs: list[str]
    unmatched_demos: list[Demo]


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def scan_library(library: Path, rules: dict[str, PackRules]) -> Scan:
    groups: dict[str, Group] = {}
    loops: list[Loop] = []
    demos: list[Demo] = []
    unknown: list[str] = []
    for pack_dir in sorted(p for p in library.iterdir() if p.is_dir()):
        pack = rules.get(pack_dir.name)
        if pack is None:
            unknown.append(pack_dir.name)
            continue
        for path in sorted(pack_dir.rglob("*")):
            if not path.is_file() or path.name.startswith(".") or path.suffix in SKIP_SUFFIXES:
                continue
            if path.suffix.lower() == ".mid":
                loops.append(_scan_loop(library, pack, path, groups))
            elif path.suffix.lower() == ".wav" and pack.preview:
                fields = pack.preview_fields(path.stem) or {}
                rel = str(path.relative_to(library))
                demos.append(Demo(rel, pack.name, fields, pack.preview.scope))
    unmatched = _match_demos(rules, groups, loops, demos)
    return Scan(groups, loops, demos, unknown, unmatched)


def _scan_loop(library: Path, pack: PackRules, path: Path, groups: dict[str, Group]) -> Loop:
    rel_dir = str(path.parent.relative_to(library / pack.name))
    gid = hashlib.sha1(f"{pack.name}/{rel_dir}".encode()).hexdigest()[:12]
    group = groups.get(gid)
    issues: list[str] = []
    if group is None:
        gfields = pack.group_fields(rel_dir)
        group = groups[gid] = Group(gid, pack.name, rel_dir, gfields or {})
        if gfields is None:
            group.fields["unmatched"] = "1"
    if "unmatched" in group.fields:
        issues.append("group folder matches no rule")
    ffields = pack.file_fields(path.stem)
    if ffields is None:
        issues.append("file name matches no rule")
    fields = {**pack.defaults, **(ffields or {})}
    parsed = parse_midi(path)
    loop = Loop(str(path.relative_to(library)), _sha1(path), group, fields, parsed, issues)
    issues.extend(parsed.issues)
    group.loops.append(loop)
    return loop


def _match_demos(
    rules: dict[str, PackRules], groups: dict[str, Group], loops: list[Loop], demos: list[Demo]
) -> list[Demo]:
    unmatched = []
    for demo in demos:
        rule = rules[demo.pack].preview
        key = demo.fields.get("key")
        if rule is None or key is None:
            unmatched.append(demo)
            continue
        if demo.scope == "group":
            targets = {
                g.group_id: v
                for g in groups.values()
                if g.pack == demo.pack and (v := g.field_value(rule.match_on))
            }
            demo.targets = best_matches(key, targets)
            for gid in demo.targets:
                groups[gid].demos.append(demo)
                for lp in groups[gid].loops:
                    lp.demos.append(demo)
        else:
            by_path = {lp.rel_path: lp for lp in loops if lp.group.pack == demo.pack}
            targets = {p: v for p, lp in by_path.items() if (v := lp.value(rule.match_on))}
            demo.targets = best_matches(key, targets)
            for p in demo.targets:
                by_path[p].demos.append(demo)
        if not demo.targets:
            unmatched.append(demo)
    return unmatched


def resolve_structure(loop: Loop) -> None:
    """Meter, bars and kind from names first, then the MIDI file."""
    g, f = loop.group.fields, loop.file_fields
    named: tuple[int, int] | None = None
    if "num" in g and "den" in g:
        named = (int(g["num"]), int(g["den"]))
    elif "meter" in g or "meter" in f:
        named = meter_from_words(g.get("meter") or f["meter"])
    if named:
        loop.meter, loop.meter_source = (
            named,
            "folder" if ("num" in g or "meter" in g) else "filename",
        )
        if loop.parsed.meter and loop.parsed.meter != named:
            fn, fd = loop.parsed.meter
            loop.issues.append(f"meter conflict: name {named[0]}/{named[1]}, file {fn}/{fd}")
    elif loop.parsed.meter:
        loop.meter, loop.meter_source = loop.parsed.meter, "midi"
    else:
        loop.issues.append("meter unknown, assumed 4/4")

    inferred = infer_bars(loop.parsed, loop.meter)
    named_bars = loop.value("bars")
    if named_bars:
        loop.bars, loop.bars_source = int(named_bars), "folder"
        if inferred != loop.bars:
            loop.issues.append(f"bars conflict: name {loop.bars}, notes need {inferred}")
    else:
        loop.bars = inferred

    loop.kind = kind_from_token(loop.value("kind")) or "groove"


def collect_candidates(loop: Loop) -> None:
    def add(value: str | float | None, source: str) -> None:
        if value is None:
            return
        bpm = round(float(value), 2)
        if not any(abs(c.bpm - bpm) < SAME_BPM and c.source == source for c in loop.candidates):
            loop.candidates.append(Candidate(bpm, source))

    add(loop.file_fields.get("bpm"), "filename")
    add(loop.group.fields.get("bpm"), "folder")
    for demo in loop.demos:
        add(demo.bpm, "preview")
    add(loop.parsed.tempo_bpm, "midi")


def check_tempo(loop: Loop, analyse: Callable[[Demo], DemoAnalysis | None]) -> None:
    """Score each candidate against the loop's demos and pick the BPM (see module tempo)."""
    analyses = [(d, a) for d in loop.demos if (a := analyse(d)) is not None]
    for c in loop.candidates:
        best: tuple[float, str] | None = None
        for demo, a in analyses:
            if demo.scope == "file" and duration_agrees(a.duration, loop.loop_beats, c.bpm):
                best = (1.0, "duration")
                break
            s = a.support(c.bpm, loop.beats_per_bar)
            if best is None or s > best[0]:
                best = (s, "periodicity")
        if best:
            c.support, c.method = best

    if not loop.candidates:
        _audio_only(loop, analyses)
        return

    priority = sorted(loop.candidates, key=lambda c: (SOURCE_PRIORITY.index(c.source), c.bpm))
    if not analyses:
        loop.bpm, loop.bpm_source, loop.bpm_check = (
            priority[0].bpm,
            priority[0].source,
            "unverified",
        )
        return

    confirmed = [c for c in priority if (c.support or 0) >= CONFIRM_RATIO]
    named = priority[0]
    if confirmed:
        pick = confirmed[0]
        loop.bpm, loop.bpm_source = pick.bpm, pick.source
        # a higher-priority name the audio contradicts is a conflict to review
        contradicted = (named.support or 0) < CONFIRM_RATIO and abs(
            named.bpm - pick.bpm
        ) >= SAME_BPM
        loop.bpm_check = "conflict" if contradicted else "confirmed"
    else:
        loop.bpm, loop.bpm_source, loop.bpm_check = named.bpm, named.source, "conflict"
        # offer the demo's own tempo as the alternative to choose in review
        demo, a = analyses[0]
        if demo.scope == "group":
            est = a.estimate(loop.beats_per_bar)
            loop.candidates.append(
                Candidate(est, "audio", a.support(est, loop.beats_per_bar), "periodicity")
            )


def _audio_only(loop: Loop, analyses: list[tuple[Demo, DemoAnalysis]]) -> None:
    if not analyses:
        return
    demo, a = analyses[0]
    if demo.scope == "file":
        options = [duration_bpm(a.duration, loop.loop_beats, near) for near in range(60, 201, 10)]
        options = [b for b in set(round(o, 2) for o in options) if 60 <= b <= 200]
        bpm = max(options, key=lambda b: a.support(b, loop.beats_per_bar)) if options else None
    else:
        bpm = a.estimate(loop.beats_per_bar)
    if bpm is not None:
        loop.bpm, loop.bpm_source, loop.bpm_check = round(bpm), "audio", "audio-only"


def normalise(loop: Loop) -> None:
    length = loop.bars * bar_ticks(loop.meter)
    loop.fitted = fit_to_length(loop.parsed.notes, length)
    if loop.fitted.wrapped or loop.fitted.dropped:
        loop.remarks.append(
            f"hits past loop end: {loop.fitted.wrapped} wrapped, {loop.fitted.dropped} dropped"
        )
    loop.loop_id = loop_id(loop.fitted, loop.meter)


def dedupe(loops: list[Loop]) -> list[Loop]:
    """One record per loop ID; identical files elsewhere are listed in ``also_at``."""
    by_id: dict[str, Loop] = {}
    for lp in loops:
        first = by_id.setdefault(lp.loop_id, lp)
        if first is not lp:
            first.also_at.append(lp.rel_path)
    return list(by_id.values())
