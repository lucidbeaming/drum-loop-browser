"""catalogue.sqlite: written by groom only, read by the dashboard."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from groom import __version__
from groom.catalogue import Demo, Group, Loop
from groom.names import split_camel

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE packs (
    pack_id TEXT PRIMARY KEY, title TEXT NOT NULL, loop_count INTEGER NOT NULL,
    preview_count INTEGER NOT NULL
);
CREATE TABLE groups (
    group_id TEXT PRIMARY KEY, pack_id TEXT NOT NULL REFERENCES packs, rel_dir TEXT NOT NULL,
    style TEXT NOT NULL, preview_wavs TEXT NOT NULL  -- JSON list of library-relative paths
);
CREATE TABLE loops (
    loop_id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES groups,
    src_rel_path TEXT NOT NULL, src_sha1 TEXT NOT NULL, norm_rel_path TEXT NOT NULL,
    also_at TEXT NOT NULL,  -- JSON list of identical source files
    title TEXT NOT NULL, kind TEXT NOT NULL, variant TEXT, song TEXT, artist TEXT, feel TEXT,
    bpm REAL, bpm_source TEXT NOT NULL, bpm_confidence REAL NOT NULL, bpm_check TEXT NOT NULL,
    bpm_candidates TEXT NOT NULL,  -- JSON [{bpm, source, support, method}]
    meter_num INTEGER NOT NULL, meter_den INTEGER NOT NULL, meter_source TEXT NOT NULL,
    bars INTEGER NOT NULL, bars_source TEXT NOT NULL,
    src_ppq INTEGER NOT NULL, src_midi_type INTEGER NOT NULL,
    length_ticks INTEGER NOT NULL, note_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    issues TEXT NOT NULL,  -- JSON list: reasons the loop needs review
    remarks TEXT NOT NULL  -- JSON list: informational notes
);
CREATE TABLE notes (
    loop_id TEXT NOT NULL REFERENCES loops, tick INTEGER NOT NULL, key INTEGER NOT NULL,
    vel INTEGER NOT NULL, dur INTEGER NOT NULL
);
CREATE INDEX notes_loop ON notes (loop_id);
CREATE INDEX loops_group ON loops (group_id);
"""


def write_catalogue(
    path: Path, loops: Iterable[Loop], groups: Iterable[Group], demos: list[Demo],
    pack_titles: dict[str, str],
) -> None:  # fmt: skip
    """Build the database in a temp file, then swap it in, so readers never see a partial one."""
    loops = list(loops)
    groups = [g for g in groups if g.loops]
    tmp = path.with_suffix(".sqlite.tmp")
    tmp.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        meta = {
            "schema_version": str(SCHEMA_VERSION),
            "groom_version": __version__,
            "groomed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
        packs = sorted({g.pack for g in groups})
        con.executemany(
            "INSERT INTO packs VALUES (?, ?, ?, ?)",
            [
                (
                    p,
                    pack_titles.get(p, p),
                    sum(1 for lp in loops if lp.group.pack == p),
                    sum(1 for d in demos if d.pack == p),
                )
                for p in packs
            ],
        )
        con.executemany(
            "INSERT INTO groups VALUES (?, ?, ?, ?, ?)",
            [
                (g.group_id, g.pack, g.rel_dir, g.style, json.dumps([d.rel_path for d in g.demos]))
                for g in groups
            ],
        )
        con.executemany(
            f"INSERT INTO loops VALUES ({', '.join('?' * 29)})", [_loop_row(lp) for lp in loops]
        )
        con.executemany(
            "INSERT INTO notes VALUES (?, ?, ?, ?, ?)",
            [
                (lp.loop_id, n.tick, n.key, n.vel, n.dur)
                for lp in loops
                if lp.fitted
                for n in lp.fitted.notes
            ],
        )
        con.commit()
    finally:
        con.close()
    tmp.replace(path)


def _loop_row(lp: Loop) -> tuple[object, ...]:
    assert lp.fitted is not None
    candidates = [
        {"bpm": c.bpm, "source": c.source, "support": c.support, "method": c.method}
        for c in lp.candidates
    ]
    return (
        lp.loop_id, lp.group.group_id, lp.rel_path, lp.src_sha1, f"normalised/{lp.loop_id}.mid",
        json.dumps(lp.also_at), lp.title, lp.kind, lp.value("variant"), _words(lp.value("song")),
        _words(lp.value("artist")), lp.value("feel"),
        lp.bpm, lp.bpm_source, lp.bpm_confidence, lp.bpm_check, json.dumps(candidates),
        lp.meter[0], lp.meter[1], lp.meter_source, lp.bars, lp.bars_source,
        lp.parsed.ppq, lp.parsed.midi_type, lp.fitted.length, len(lp.fitted.notes),
        lp.status, json.dumps(lp.issues), json.dumps(lp.remarks),
    )  # fmt: skip


def _words(value: str | None) -> str | None:
    return split_camel(value) if value else None
