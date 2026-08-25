"""Local searchable asset catalog (SQLite-backed).

Every row here corresponds 1:1 to a `license.schema.LicenseEntry` by
`asset_id` — the catalog stores WHAT an asset is and HOW to find it;
license/manifest.json stores whether it's allowed to be used. `query()`
joins the two, so a caller never has to remember to check licensing
separately.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .tags import expand
from ..license import manifest as license_manifest

DB_PATH = Path(__file__).resolve().parent / "catalog.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id      TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    category      TEXT NOT NULL,
    format        TEXT NOT NULL,
    local_path    TEXT NOT NULL,
    description   TEXT DEFAULT '',
    tags          TEXT NOT NULL,        -- JSON list
    rigged        INTEGER DEFAULT 0,
    poly_style    TEXT DEFAULT '',      -- e.g. "low_poly", "photoreal"
    file_bytes    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
"""


@dataclass
class AssetRecord:
    asset_id: str
    source: str
    category: str
    format: str
    local_path: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    rigged: bool = False
    poly_style: str = ""
    file_bytes: int = 0


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    return conn


def rebuild(records: list[AssetRecord], path: Path = DB_PATH) -> int:
    """Full rebuild — the catalog is a derived cache of the vendor/ folder
    plus indexer scans, never hand-edited, so wiping and re-inserting is
    simpler and safer than diffing."""
    conn = _connect(path)
    conn.execute("DELETE FROM assets")
    for r in records:
        conn.execute(
            "INSERT INTO assets (asset_id, source, category, format, local_path,"
            " description, tags, rigged, poly_style, file_bytes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r.asset_id, r.source, r.category, r.format, r.local_path, r.description,
             json.dumps(r.tags), int(r.rigged), r.poly_style, r.file_bytes),
        )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    conn.close()
    return n


def query(tags: list[str], category: str | None = None, limit: int = 20,
          licensed_only: bool = True, path: Path = DB_PATH) -> list[AssetRecord]:
    """Semantic tag query. `licensed_only=True` (default) drops anything
    not currently `eligible()` in the license manifest — this is the ONLY
    query path the storyboard/visual-mode selector should use."""
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM assets"
    params: list = []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    wanted = expand(tags) if tags else set()
    scored: list[tuple[int, AssetRecord]] = []
    for row in rows:
        rec = AssetRecord(
            asset_id=row["asset_id"], source=row["source"], category=row["category"],
            format=row["format"], local_path=row["local_path"], description=row["description"],
            tags=json.loads(row["tags"]), rigged=bool(row["rigged"]),
            poly_style=row["poly_style"], file_bytes=row["file_bytes"],
        )
        if licensed_only:
            try:
                if not license_manifest.is_eligible(rec.asset_id):
                    continue
            except FileNotFoundError:
                continue
        score = len(wanted & set(t.lower() for t in rec.tags)) if wanted else 1
        if wanted and score == 0:
            continue
        scored.append((score, rec))
    scored.sort(key=lambda sr: sr[0], reverse=True)
    return [r for _, r in scored[:limit]]


def stats(path: Path = DB_PATH) -> dict:
    conn = _connect(path)
    total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    by_cat = dict(conn.execute(
        "SELECT category, COUNT(*) FROM assets GROUP BY category").fetchall())
    rigged = conn.execute("SELECT COUNT(*) FROM assets WHERE rigged=1").fetchone()[0]
    conn.close()
    return {"total": total, "by_category": by_cat, "rigged_count": rigged}
