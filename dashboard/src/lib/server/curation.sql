-- data/curation.sqlite: the user's curation, written only by the dashboard. groom reads
-- loop_curation, loop_tags and loop_fixes (see groom/src/groom/curation.py) and applies them
-- with the highest priority. Bump schema_version (here, in curation.ts and in curation.py)
-- on any incompatible change.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS loop_curation (
    loop_id TEXT PRIMARY KEY,
    favourite INTEGER NOT NULL DEFAULT 0,
    rating INTEGER NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
    rejected INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    last_played TEXT
);

-- user edits on top of groom's tags: add a tag, or remove an automatic one
CREATE TABLE IF NOT EXISTS loop_tags (
    loop_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    op TEXT NOT NULL CHECK (op IN ('add', 'remove')),
    PRIMARY KEY (loop_id, tag)
);

-- corrections: bpm ("96"), meter ("7/8"), kind ("fill"), status ("ok" = kept after review,
-- "duplicate")
CREATE TABLE IF NOT EXISTS loop_fixes (
    loop_id TEXT NOT NULL,
    field TEXT NOT NULL CHECK (field IN ('bpm', 'meter', 'kind', 'status')),
    value TEXT NOT NULL,
    PRIMARY KEY (loop_id, field)
);

CREATE TABLE IF NOT EXISTS collections (
    collection_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER NOT NULL REFERENCES collections ON DELETE CASCADE,
    loop_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (collection_id, loop_id)
);
