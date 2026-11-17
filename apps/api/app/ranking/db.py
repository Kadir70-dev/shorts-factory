"""
SQLite catalog for the ranking pipeline.

Kept in its own file (data/ranking/ranking.db) so it can never collide with the
SQLModel `factory.db` the main pipeline owns. Plain sqlite3, no ORM: the schema
is small and the queries are explicit.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..config import DATA_DIR

RANKING_DIR = Path(os.getenv("RANKING_DATA_DIR", str(DATA_DIR / "ranking")))
DEFAULT_RANKING_DIR = DATA_DIR / "ranking"


def output_root(channel_output_dir: Path) -> Path:
    """Where a catalog's drafts/renders go. Concept ids are per catalog, so a
    second catalog (RANKING_DATA_DIR=…) gets its own subfolder and can never
    overwrite the default catalog's renders."""
    if RANKING_DIR.resolve() == DEFAULT_RANKING_DIR.resolve():
        return channel_output_dir
    return channel_output_dir / "catalogs" / RANKING_DIR.name

# Licenses that permit reuse once VERIFIED by a human. Anything else (including
# "unknown") is catalogued but can never be selected.
REUSABLE_LICENSES = {"owned", "licensed", "cc0", "cc-by", "public-domain",
                     "original-synthetic"}

CATEGORIES = ["funny_fails", "unexpected", "animals", "pranks", "sports",
              "reactions"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY,
    path          TEXT UNIQUE NOT NULL,
    sha256        TEXT NOT NULL,
    duration      REAL, width INTEGER, height INTEGER, fps REAL,
    has_audio     INTEGER DEFAULT 0,
    license       TEXT DEFAULT 'unknown',
    license_verified INTEGER DEFAULT 0,
    license_proof TEXT DEFAULT '',     -- URL / contract / receipt reference
    attribution   TEXT DEFAULT '',     -- credit line required by the license
    origin_url    TEXT DEFAULT '',
    category      TEXT DEFAULT '',
    scanned_at    TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY,
    source_id  INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    start      REAL NOT NULL,
    end        REAL NOT NULL,
    score      REAL DEFAULT 0,       -- motion + loudness interest, 0..1
    category   TEXT DEFAULT '',
    label      TEXT DEFAULT '',      -- human description of the moment
    phash      TEXT DEFAULT '',      -- 3 x 64-bit dHash, hex, comma-joined
    manual     INTEGER DEFAULT 0,    -- 1 = timestamps corrected by a human
    disabled   INTEGER DEFAULT 0,
    UNIQUE(source_id, start, end)
);
CREATE TABLE IF NOT EXISTS concepts (
    id          INTEGER PRIMARY KEY,
    channel     TEXT NOT NULL,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    combo_key   TEXT UNIQUE NOT NULL,  -- sorted segment ids: no combo reuse
    payload     TEXT NOT NULL,         -- JSON: ranks, captions, hook, credits
    status      TEXT DEFAULT 'pending_approval',
    approved_by TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS segment_usage (
    segment_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    PRIMARY KEY (segment_id, concept_id)
);
CREATE TABLE IF NOT EXISTS renders (
    id         INTEGER PRIMARY KEY,
    concept_id INTEGER NOT NULL,
    path       TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    qa_json    TEXT DEFAULT '{}',
    meta_json  TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS uploads (
    id          INTEGER PRIMARY KEY,
    channel     TEXT NOT NULL,
    render_sha  TEXT NOT NULL,
    concept_id  INTEGER,
    video_id    TEXT DEFAULT '',
    privacy     TEXT DEFAULT 'private',
    publish_at  TEXT DEFAULT '',
    status      TEXT DEFAULT 'queued',   -- queued|uploading|uploaded|failed
    attempts    INTEGER DEFAULT 0,
    resume_uri  TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(channel, render_sha)
);
CREATE TABLE IF NOT EXISTS reference_videos (
    -- Study material only (e.g. a channel inventory found with yt-dlp).
    -- Metadata, never media: rows here can't be selected, rendered or uploaded.
    id          INTEGER PRIMARY KEY,
    platform    TEXT NOT NULL DEFAULT 'youtube',
    video_id    TEXT NOT NULL,
    channel     TEXT DEFAULT '',
    title       TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    playlist_index INTEGER,
    inventory   TEXT DEFAULT '',        -- which inventory file listed it
    downloaded  INTEGER DEFAULT 0,      -- 1 only if a local file is actually present
    imported_at TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, video_id)
);
CREATE TABLE IF NOT EXISTS quota (
    channel TEXT NOT NULL,
    day     TEXT NOT NULL,              -- Pacific date: YouTube's quota day
    units   INTEGER DEFAULT 0,
    PRIMARY KEY (channel, day)
);
"""


# Columns added after the first release: (table, column, DDL). Applied in place
# so an existing catalog keeps its data.
MIGRATIONS = [
    ("sources", "kind", "TEXT DEFAULT 'clip'"),            # clip | compilation
    ("sources", "title", "TEXT DEFAULT ''"),
    ("sources", "provenance_ref", "TEXT DEFAULT ''"),      # matched reference video id
    ("sources", "permission_proof", "TEXT DEFAULT ''"),    # needed if provenance_ref set
    ("sources", "underlying_rights_verified", "INTEGER DEFAULT 0"),  # compilations
    ("sources", "underlying_proof", "TEXT DEFAULT ''"),
    ("sources", "content_crop", "TEXT DEFAULT ''"),        # w:h:x:y of the live picture
    ("sources", "topic_confidence", "REAL DEFAULT 0"),
    ("sources", "segmentation", "TEXT DEFAULT ''"),        # JSON detection report
    ("segments", "source_rank", "INTEGER"),                # position in a Top-5 source
    ("segments", "confidence", "REAL DEFAULT 0"),
    ("segments", "signals", "TEXT DEFAULT ''"),
]


def _migrate(con) -> None:
    for table, col, ddl in MIGRATIONS:
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if col not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def db_path() -> Path:
    return RANKING_DIR / "ranking.db"


@contextmanager
def connect(path: Path | None = None):
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    _migrate(con)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def eligible_source_sql() -> tuple[str, list[str]]:
    """WHERE fragment restricting to rights-verified, reusable sources."""
    marks = ",".join("?" * len(REUSABLE_LICENSES))
    return (f"s.license_verified = 1 AND s.license IN ({marks})"
            # a compilation's clips belong to their original creators: the
            # compilation license alone is not enough
            " AND (s.kind != 'compilation' OR s.underlying_rights_verified = 1)"
            # anything traced to a reference inventory needs recorded permission
            " AND (s.provenance_ref = '' OR s.permission_proof != '')",
            sorted(REUSABLE_LICENSES))


def row_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    if "payload" in d and isinstance(d["payload"], str):
        d["payload"] = json.loads(d["payload"])
    return d
