"""The user's curation from the dashboard (``data/curation.sqlite``), applied over the rules.

The dashboard owns the file and its schema (dashboard/src/lib/server/curation.sql); groom only
reads it. Fixes and tag edits are keyed by loop ID, which groom computes *before* applying a
fix, so a loop keeps its ID (and its curation) when its meter is corrected.
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from groom.names import KIND_TOKENS

SCHEMA_VERSION = 1
KINDS = frozenset(KIND_TOKENS.values())
STATUSES = frozenset({"ok", "duplicate"})


class CurationError(Exception):
    pass


@dataclass
class Curation:
    fixes: dict[str, dict[str, str]] = field(default_factory=dict)  # loop ID -> field -> value
    tags: dict[str, dict[str, str]] = field(default_factory=dict)  # loop ID -> tag -> add|remove
    rejected: set[str] = field(default_factory=set)


def load_curation(path: Path) -> Curation:
    """The curation in ``path``, or none if the dashboard hasn't written any yet."""
    if not path.is_file():
        return Curation()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None or int(row[0]) != SCHEMA_VERSION:
            raise CurationError(
                f"{path} has schema version {row[0] if row else 'unknown'}; "
                f"this groom reads version {SCHEMA_VERSION}"
            )
        fixes: dict[str, dict[str, str]] = defaultdict(dict)
        for loop_id, name, value in con.execute("SELECT loop_id, field, value FROM loop_fixes"):
            fixes[loop_id][name] = value
        tags: dict[str, dict[str, str]] = defaultdict(dict)
        for loop_id, tag, op in con.execute("SELECT loop_id, tag, op FROM loop_tags"):
            tags[loop_id][tag] = op
        rejected = {r[0] for r in con.execute("SELECT loop_id FROM loop_curation WHERE rejected")}
    finally:
        con.close()
    return Curation(dict(fixes), dict(tags), rejected)


def parse_bpm(value: str) -> float | None:
    try:
        bpm = float(value)
    except ValueError:
        return None
    return bpm if 20 <= bpm <= 400 else None


def parse_meter(value: str) -> tuple[int, int] | None:
    num, _, den = value.partition("/")
    if not (num.isdigit() and den.isdigit()):
        return None
    meter = (int(num), int(den))
    return meter if 1 <= meter[0] <= 32 and meter[1] in (2, 4, 8, 16) else None
