"""Tags: from names and folders (rule) and from rhythm features (feature).

Thresholds were checked against the library's own labels: Swung/Straight fill folders, the
Linear packs, FourOnFloor, Shuffle and Rock styles.
"""

import re
from dataclasses import dataclass

from groom.features import COMMON_METERS, Features

BUSY_DENSITY = 4.5  # hits per beat; about the top 10 % of the library
SPARSE_DENSITY = 1.85  # about the bottom 10 %
LINEAR_SIMULTANEITY = 0.05
TRIPLET_SHARE = 0.15
GHOST_SHARE = 0.15
TOMS_SHARE = 0.2  # of all hits; the 'All About Toms' groups average 0.22
RIDE_DENSITY = 0.5


@dataclass(frozen=True)
class Tag:
    tag: str
    source: str  # "rule" or "feature" (curation tags come from the dashboard)
    confidence: float


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def rule_tags(style: str, feel: str | None) -> list[Tag]:
    tags = [Tag(slug(style), "rule", 1.0)] if slug(style) else []
    if feel:
        tags.append(Tag(slug(feel), "rule", 1.0))
    return tags


def feature_tags(f: Features, meter: tuple[int, int], kind: str, note_count: int) -> list[Tag]:
    tags: list[Tag] = []

    def add(name: str, confidence: float) -> None:
        tags.append(Tag(name, "feature", round(max(0.0, min(1.0, confidence)), 2)))

    swing = max((s for s in (f.swing8, f.swing16) if s is not None), default=None)
    if f.swung and swing is not None:
        add("swung", (swing - 0.5) / 0.15)
    if f.triplet_share >= TRIPLET_SHARE:
        add("triplet", f.triplet_share / (2 * TRIPLET_SHARE))
    if f.simultaneity <= LINEAR_SIMULTANEITY and note_count >= 8:
        add("linear", 1 - f.simultaneity / (2 * LINEAR_SIMULTANEITY))
    if f.density >= BUSY_DENSITY:
        add("busy", f.density / (BUSY_DENSITY * 1.2))
    elif f.density <= SPARSE_DENSITY:
        add("sparse", SPARSE_DENSITY / max(f.density, 0.1) / 1.2)
    by = f.density_by_piece
    if by.get("ride", 0) >= RIDE_DENSITY and by.get("ride", 0) >= by.get("hats", 0):
        add("ride", 1.0)
    toms = by.get("toms", 0) / f.density if f.density else 0.0
    if toms >= TOMS_SHARE:
        add("toms", toms / (2 * TOMS_SHARE))
    if f.ghost_share >= GHOST_SHARE:
        add("ghost-notes", f.ghost_share / (2 * GHOST_SHARE))
    if kind == "groove" and f.four_on_floor:
        add("four-on-the-floor", 1.0)
    if kind == "groove" and f.half_time:
        add("half-time", 0.8)
    if meter not in COMMON_METERS:
        add("odd-meter", 1.0)
    return tags


def merge(*groups: list[Tag]) -> list[Tag]:
    """One entry per tag name, keeping the most confident source."""
    best: dict[str, Tag] = {}
    for tag in (t for g in groups for t in g):
        if tag.tag not in best or tag.confidence > best[tag.tag].confidence:
            best[tag.tag] = tag
    return sorted(best.values(), key=lambda t: t.tag)
