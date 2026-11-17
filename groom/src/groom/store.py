"""catalogue.sqlite: written by groom only, read by the dashboard."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from groom import __version__
from groom.catalogue import Demo, Group, Loop
from groom.names import split_camel
from groom.soundfont import Kit

SCHEMA_VERSION = 2

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
CREATE TABLE features (
    loop_id TEXT PRIMARY KEY REFERENCES loops,
    pieces TEXT NOT NULL,  -- JSON list of kit families present
    density REAL NOT NULL, density_by_piece TEXT NOT NULL,  -- hits per beat; JSON by family
    swing8 REAL, swing16 REAL, triplet_share REAL NOT NULL, syncopation REAL NOT NULL,
    simultaneity REAL NOT NULL, velocity_mean REAL NOT NULL, velocity_range INTEGER NOT NULL,
    ghost_share REAL NOT NULL, four_on_floor INTEGER NOT NULL, backbeat INTEGER NOT NULL,
    half_time INTEGER NOT NULL,
    onset_vector BLOB NOT NULL  -- float32, one bar per kit family; see groom.features
);
CREATE TABLE tags (
    loop_id TEXT NOT NULL REFERENCES loops, tag TEXT NOT NULL,
    source TEXT NOT NULL,  -- rule | feature
    confidence REAL NOT NULL, PRIMARY KEY (loop_id, tag)
);
CREATE TABLE similar (
    loop_id TEXT NOT NULL REFERENCES loops, other_id TEXT NOT NULL REFERENCES loops,
    rank INTEGER NOT NULL, score REAL NOT NULL, PRIMARY KEY (loop_id, rank)
);
CREATE TABLE kits (  -- drum kits in the preview SoundFont, from the audibility check
    program INTEGER PRIMARY KEY, name TEXT NOT NULL,
    keys TEXT NOT NULL  -- JSON list of notes that have a sample
);
CREATE INDEX notes_loop ON notes (loop_id);
CREATE INDEX tags_tag ON tags (tag);
CREATE INDEX loops_group ON loops (group_id);
"""


def write_catalogue(
    path: Path, loops: Iterable[Loop], groups: Iterable[Group], demos: list[Demo],
    pack_titles: dict[str, str], kits: list[Kit] | None = None,
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
        con.executemany(
            f"INSERT INTO features VALUES ({', '.join('?' * 16)})",
            [_feature_row(lp) for lp in loops if lp.features],
        )
        con.executemany(
            "INSERT INTO tags VALUES (?, ?, ?, ?)",
            [(lp.loop_id, t.tag, t.source, t.confidence) for lp in loops for t in lp.tags],
        )
        con.executemany(
            "INSERT INTO similar VALUES (?, ?, ?, ?)",
            [
                (lp.loop_id, other, rank, score)
                for lp in loops
                for rank, (other, score) in enumerate(lp.similar, 1)
            ],
        )
        con.executemany(
            "INSERT INTO kits VALUES (?, ?, ?)",
            [(k.program, k.name, json.dumps(sorted(k.keys))) for k in kits or []],
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


def _feature_row(lp: Loop) -> tuple[object, ...]:
    f = lp.features
    assert f is not None
    return (
        lp.loop_id, json.dumps(f.pieces), f.density, json.dumps(f.density_by_piece),
        f.swing8, f.swing16, f.triplet_share, f.syncopation, f.simultaneity,
        f.velocity_mean, f.velocity_range, f.ghost_share,
        int(f.four_on_floor), int(f.backbeat), int(f.half_time),
        f.vector.astype(np.float32).tobytes(),
    )  # fmt: skip


def _words(value: str | None) -> str | None:
    return split_camel(value) if value else None
