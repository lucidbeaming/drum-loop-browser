"""Per-pack naming rules (packs.yaml) and the fuzzy matching of demo WAVs to loops."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from rapidfuzz import fuzz

from groom.names import match_key

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "packs.yaml"
MATCH_THRESHOLD = 80.0
CONTAINMENT_SCORE = 90.0

Fields = dict[str, str]


@dataclass(frozen=True)
class PreviewRule:
    pattern: re.Pattern[str]
    scope: Literal["file", "group"]
    match_on: str
    # "shared": a group's loops share one tempo, the demo's; "per-loop": each demo plays one
    # loop of its group, and loops in a group may differ in tempo
    tempo: Literal["shared", "per-loop"] = "shared"


@dataclass(frozen=True)
class PackRules:
    name: str
    title: str
    group: re.Pattern[str]
    file: re.Pattern[str]
    preview: PreviewRule | None
    defaults: Fields = field(default_factory=dict)

    def group_fields(self, rel_dir: str) -> Fields | None:
        m = self.group.match(rel_dir)
        return _present(m.groupdict()) if m else None

    def file_fields(self, stem: str) -> Fields | None:
        m = self.file.match(stem)
        return _present(m.groupdict()) if m else None

    def preview_fields(self, stem: str) -> Fields | None:
        if self.preview is None:
            return None
        m = self.preview.pattern.match(stem)
        return _present(m.groupdict()) if m else None


def _present(d: dict[str, str | None]) -> Fields:
    return {k: v for k, v in d.items() if v}


def _pack(name: str, raw: dict[str, Any]) -> PackRules:
    prev = raw.get("preview")
    preview = (
        PreviewRule(
            re.compile(prev["pattern"]),
            prev["scope"],
            prev["match_on"],
            prev.get("tempo", "shared"),
        )
        if prev
        else None
    )
    return PackRules(
        name=name,
        title=raw.get("title", name),
        group=re.compile(raw["group"]),
        file=re.compile(raw["file"]),
        preview=preview,
        defaults={k: str(v) for k, v in (raw.get("defaults") or {}).items()},
    )


def load_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, PackRules]:
    data = yaml.safe_load(path.read_text())
    return {name: _pack(name, raw) for name, raw in data["packs"].items()}


def similarity(a: str, b: str) -> float:
    """Fuzzy similarity (0-100) of two names after normalising case and punctuation."""
    ka, kb = match_key(a), match_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 100.0
    if ka in kb or kb in ka:
        return CONTAINMENT_SCORE
    return float(fuzz.ratio(ka, kb))


def best_matches(key: str, targets: dict[str, str]) -> list[str]:
    """IDs of the targets whose value best matches ``key`` (ties all win), above the threshold."""
    scored = [(similarity(key, value), tid) for tid, value in targets.items()]
    if not scored:
        return []
    top = max(s for s, _ in scored)
    if top < MATCH_THRESHOLD:
        return []
    return [tid for s, tid in scored if s == top]
