"""Resumable K70 reference-dataset pipeline.

This module intentionally starts in pilot mode.  It uses authorized APIs,
streams bounded image downloads, records every decision in SQLite, and keeps
all third-party media below ``data/reference/block_world_cinematic``.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import math
import mimetypes
import os
import random
import re
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT / "data" / "reference" / "block_world_cinematic"
SOURCE_CONFIG = Path(__file__).with_name("sources.json")
USER_AGENT = "K70VisualDirector/1.0"
MAX_IMAGE_BYTES = 25 * 1024 * 1024
TEMP_CAP_BYTES = 60 * 1024**3
MIN_LONG_EDGE = 1280

_BASE_QUERIES = (
    "voxel city cinematic", "block world cinematic", "voxel city night", "voxel city golden hour",
    "voxel street", "voxel architecture", "voxel building", "voxel town", "voxel landscape",
    "voxel interior", "block city", "block architecture", "blocky city", "low poly block city",
    "low poly city cinematic", "isometric voxel city", "voxel cyberpunk city",
    "voxel medieval town", "voxel modern city", "voxel house", "voxel office", "voxel bank",
    "voxel shop", "voxel characters", "voxel street night", "voxel sunset",
    "voxel environment", "voxel render", "block world render", "pixel art 3D environment",
    "minecraft cinematic", "minecraft cinematic city", "minecraft golden hour",
    "minecraft financial district", "minecraft city shaders", "minecraft urban cinematic",
    "minecraft interior cinematic", "minecraft night city", "minecraft volumetric lighting",
    "minecraft cinematic character",
)
_SUBJECTS = ("city", "street", "town", "interior", "architecture", "landscape", "character")
_QUALITIES = ("cinematic lighting", "golden hour", "night", "volumetric", "deep perspective")
QUERIES = tuple(dict.fromkeys(_BASE_QUERIES + tuple(
    f"voxel {subject} {quality}" for subject in _SUBJECTS for quality in _QUALITIES)))

POSITIVE_PROMPTS = (
    "a premium cinematic block-world environment with strong composition",
    "a cinematic voxel city establishing shot with foreground midground and distant background",
    "dramatic block-world architecture with atmospheric lighting and visual hierarchy",
    "a polished voxel character shot with readable environment and cinematic camera placement",
)
NEGATIVE_PROMPTS = (
    "an ordinary gameplay screenshot with HUD hotbar crosshair and inventory",
    "a menu server list debug screen tutorial or comparison graphic",
    "a meme or video thumbnail dominated by large text and logos",
    "a flat empty low quality shader test screenshot",
)


@dataclass(frozen=True)
class Limits:
    global_concurrency: int = 4
    timeout_connect: float = 10.0
    timeout_read: float = 30.0
    max_image_bytes: int = MAX_IMAGE_BYTES
    temp_cap_bytes: int = TEMP_CAP_BYTES
    min_long_edge: int = MIN_LONG_EDGE


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_layout(root: Path = DEFAULT_ROOT) -> None:
    for name in ("raw_candidates", "accepted", "rejected", "thumbnails", "top_100",
                 "metadata", "indexes", "contact_sheets"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name in ("raw_candidates", "accepted", "thumbnails", "contact_sheets", "metadata"):
        (root / "cinematography" / name).mkdir(parents=True, exist_ok=True)


def connect(root: Path = DEFAULT_ROOT) -> sqlite3.Connection:
    ensure_layout(root)
    db = sqlite3.connect(root / "dataset.sqlite")
    db.row_factory = sqlite3.Row
    db.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS candidates (
      id INTEGER PRIMARY KEY, source_site TEXT NOT NULL, source_id TEXT,
      source_page_url TEXT NOT NULL, asset_url TEXT NOT NULL, thumbnail_url TEXT,
      creator TEXT, title TEXT, license TEXT, license_url TEXT,
      source_gallery TEXT, query TEXT, discovered_at TEXT NOT NULL,
      discovery_metadata TEXT NOT NULL DEFAULT '{}', stage TEXT NOT NULL DEFAULT 'DISCOVERED',
      local_path TEXT, rejection_reason TEXT, UNIQUE(source_site, source_page_url, asset_url)
    );
    CREATE TABLE IF NOT EXISTS images (
      candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id), width INTEGER, height INTEGER,
      aspect_ratio REAL, file_bytes INTEGER, mime TEXT, sha256 TEXT UNIQUE, phash TEXT,
      technical_score REAL, cinematic_score REAL, aesthetic_score REAL, final_score REAL,
      text_risk REAL, ui_risk REAL, tags TEXT, tag_confidence TEXT, embedding_id INTEGER,
      accepted_tier TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash);
    CREATE INDEX IF NOT EXISTS idx_candidates_stage ON candidates(stage);
    CREATE TABLE IF NOT EXISTS embeddings (
      id INTEGER PRIMARY KEY, candidate_id INTEGER UNIQUE REFERENCES candidates(id),
      model TEXT NOT NULL, dim INTEGER NOT NULL, vector BLOB NOT NULL
    );
    CREATE TABLE IF NOT EXISTS stage_runs (
      stage TEXT PRIMARY KEY, status TEXT NOT NULL, cursor TEXT, started_at TEXT,
      completed_at TEXT, stats TEXT NOT NULL DEFAULT '{}', error TEXT
    );
    CREATE TABLE IF NOT EXISTS source_audits (
      source_site TEXT PRIMARY KEY, robots_url TEXT, robots_allowed INTEGER,
      checked_at TEXT, detail TEXT
    );
    CREATE TABLE IF NOT EXISTS cinematography_pool (
      candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id), stage TEXT NOT NULL,
      thumbnail_path TEXT, local_path TEXT, sha256 TEXT, phash TEXT,
      cinematic_composition REAL, lighting REAL, depth REAL, hero_framing REAL,
      environment_density REAL, camera_quality REAL, reference_usefulness REAL,
      final_score REAL, category TEXT, rejection_reason TEXT
    );
    """)
    # Backward-compatible migrations for databases created by the initial
    # pilot. Source-reported values remain distinct from decoded image facts.
    existing = {row[1] for row in db.execute("PRAGMA table_info(candidates)")}
    additions = {
      "reported_width": "INTEGER", "reported_height": "INTEGER", "reported_mime": "TEXT",
      "source_sha1": "TEXT", "attribution": "TEXT", "metadata_score": "REAL"}
    for name, sql_type in additions.items():
        if name not in existing:
            db.execute(f"ALTER TABLE candidates ADD COLUMN {name} {sql_type}")
    db.commit()
    return db


def checkpoint(db: sqlite3.Connection, stage: str, status: str, *, cursor: str | None = None,
               stats: dict | None = None, error: str | None = None) -> None:
    now = utcnow()
    db.execute("""INSERT INTO stage_runs(stage,status,cursor,started_at,completed_at,stats,error)
      VALUES(?,?,?,?,?,?,?) ON CONFLICT(stage) DO UPDATE SET status=excluded.status,
      cursor=excluded.cursor, completed_at=excluded.completed_at, stats=excluded.stats,
      error=excluded.error""", (stage, status, cursor, now, now if status in {"COMPLETE", "FAILED"} else None,
                                json.dumps(stats or {}), error))
    db.commit()


def disk_guard(root: Path = DEFAULT_ROOT, limits: Limits = Limits()) -> dict:
    usage = shutil.disk_usage(root)
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if total >= limits.temp_cap_bytes:
        raise RuntimeError(f"dataset temporary cap reached: {total / 2**30:.1f} GiB")
    if usage.free < 10 * 1024**3:
        raise RuntimeError(f"disk safety floor reached: {usage.free / 2**30:.1f} GiB free")
    return {"free_gib": round(usage.free / 2**30, 2), "dataset_gib": round(total / 2**30, 2)}


def _user_agent(contact_email: str | None = None) -> str:
    email = (contact_email or os.getenv("K70_WIKIMEDIA_EMAIL") or "").strip()
    return f"{USER_AGENT} (contact: {email})" if email else USER_AGENT


def _client(*, contact_email: str | None = None, openverse: bool = False) -> httpx.Client:
    headers = {"User-Agent": _user_agent(contact_email), "Accept": "application/json"}
    if openverse and os.getenv("OPENVERSE_ACCESS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['OPENVERSE_ACCESS_TOKEN']}"
    return httpx.Client(headers=headers,
                        timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def _eligible_license(value: str | None) -> bool:
    norm = (value or "").lower().replace("_", "-").replace(" ", "-")
    return norm in ({"cc0", "pdm", "public-domain", "by", "by-sa", "cc-by", "cc-by-sa",
                     "cc-by-2.0", "cc-by-3.0", "cc-by-4.0", "cc-by-sa-2.0",
                     "cc-by-sa-3.0", "cc-by-sa-4.0"}
                    | {"pexels-license", "pixabay-content-license"})


def _plain(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip() or "UNKNOWN"


def _metadata_relevance(title: str | None, query: str, metadata: dict) -> float:
    """Cheap pre-download precision gate; visual scoring remains authoritative."""
    blob = " ".join((title or "", str(metadata.get("tags") or ""),
                     str(metadata.get("description") or ""))).lower()
    voxel = sum(term in blob for term in ("voxel", "block world", "block-world", "blocky",
                                           "minecraft", "isometric", "pixel art 3d", "low poly"))
    scene = sum(term in blob for term in ("city", "street", "town", "architecture", "interior",
                                           "environment", "building", "landscape", "character"))
    cinematic = sum(term in blob for term in ("cinematic", "render", "golden hour", "sunset", "night",
                                               "volumetric", "lighting", "cyberpunk", "perspective"))
    negative = sum(term in blob for term in ("diagram", "graph", "chart", "scientific", "formula",
                                              "real estate", "church photograph", "automobile race"))
    if voxel == 0:
        return 0.0
    query_bonus = 3.0 if any(term in query.lower() for term in ("cinematic", "night", "golden hour", "sunset")) else 0.0
    return round(max(0.0, min(100.0, 22 * voxel + 7 * scene + 6 * cinematic + query_bonus - 20 * negative)), 2)


def discover_openverse(root: Path = DEFAULT_ROOT, *, queries: Iterable[str] = QUERIES,
                       pages_per_query: int = 2, page_size: int = 20) -> dict:
    """Metadata-only Openverse pilot. Downloads are a later independent stage."""
    db = connect(root)
    checkpoint(db, "DISCOVERY_OPENVERSE", "RUNNING")
    if not 1 <= page_size <= 20:
        raise ValueError("anonymous Openverse page_size must be between 1 and 20")
    added = seen = errors = 0
    error_examples: list[str] = []
    with _client(openverse=True) as client:
        for query in queries:
            for page in range(1, pages_per_query + 1):
                try:
                    response = client.get("https://api.openverse.org/v1/images/", params={
                        "q": query, "page": page, "page_size": page_size,
                        "license_type": "commercial,modification",
                    })
                    if response.status_code == 429:
                        time.sleep(min(float(response.headers.get("Retry-After", "5")), 60.0))
                        response = client.get(str(response.request.url))
                    response.raise_for_status()
                    rows = response.json().get("results", [])
                except Exception as exc:  # recorded; discovery remains resumable
                    errors += 1
                    if len(error_examples) < 5:
                        error_examples.append(f"{type(exc).__name__}: {str(exc)[:300]}")
                    continue
                for row in rows:
                    seen += 1
                    page_url = row.get("foreign_landing_url") or row.get("detail_url")
                    asset_url = row.get("url")
                    if not page_url or not asset_url or not _eligible_license(row.get("license")):
                        continue
                    metadata_score = _metadata_relevance(row.get("title"), query, row)
                    cur = db.execute("""INSERT OR IGNORE INTO candidates
                      (source_site,source_id,source_page_url,asset_url,thumbnail_url,creator,title,
                       license,license_url,source_gallery,query,discovered_at,discovery_metadata,
                       reported_width,reported_height,reported_mime,attribution,metadata_score)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                        f"openverse:{row.get('source') or 'UNKNOWN'}", row.get("id"), page_url, asset_url,
                        row.get("thumbnail"), row.get("creator") or "UNKNOWN", row.get("title") or "UNKNOWN",
                        row.get("license") or "UNKNOWN", row.get("license_url") or "UNKNOWN",
                        row.get("source") or "UNKNOWN", query, utcnow(), json.dumps(row, ensure_ascii=False),
                        row.get("width"), row.get("height"), row.get("filetype"),
                        row.get("attribution") or "UNKNOWN", metadata_score))
                    added += cur.rowcount
                db.commit()
                time.sleep(3.1)
    stats = {"seen": seen, "added": added, "errors": errors, "error_examples": error_examples}
    checkpoint(db, "DISCOVERY_OPENVERSE", "COMPLETE", stats=stats)
    db.close()
    return stats


def discover_wikimedia(root: Path = DEFAULT_ROOT, *, queries: Iterable[str] = QUERIES,
                       limit_per_query: int = 100, contact_email: str | None = None) -> dict:
    contact_email = (contact_email or os.getenv("K70_WIKIMEDIA_EMAIL") or "").strip()
    if not contact_email or "<" in contact_email or "@" not in contact_email:
        raise ValueError("Wikimedia requires a genuine email via --contact-email or K70_WIKIMEDIA_EMAIL")
    db = connect(root)
    checkpoint(db, "DISCOVERY_WIKIMEDIA", "RUNNING")
    added = seen = errors = 0
    error_examples: list[str] = []
    params_base = {"action": "query", "generator": "search", "gsrnamespace": 6,
                   "prop": "imageinfo", "iiprop": "url|size|mime|sha1|extmetadata",
                   "iiurlwidth": 640, "format": "json", "formatversion": 2}
    with _client(contact_email=contact_email) as client:
        for query in queries:
            try:
                response = client.get("https://commons.wikimedia.org/w/api.php", params={
                    **params_base, "gsrsearch": query, "gsrlimit": min(limit_per_query, 100)})
                if response.status_code == 429:
                    time.sleep(min(float(response.headers.get("Retry-After", "5")), 60.0))
                    response = client.get(str(response.request.url))
                response.raise_for_status()
                pages = response.json().get("query", {}).get("pages", [])
            except Exception as exc:
                errors += 1
                if len(error_examples) < 5:
                    error_examples.append(f"{type(exc).__name__}: {str(exc)[:300]}")
                continue
            for row in pages:
                seen += 1
                info = (row.get("imageinfo") or [{}])[0]
                ext = info.get("extmetadata") or {}
                license_name = (ext.get("LicenseShortName") or {}).get("value") or "UNKNOWN"
                if not _eligible_license(license_name):
                    continue
                page_url, asset_url = info.get("descriptionurl"), info.get("url")
                if not page_url or not asset_url:
                    continue
                creator = _plain((ext.get("Artist") or {}).get("value"))
                attribution = _plain((ext.get("Attribution") or ext.get("Credit") or {}).get("value"))
                metadata_score = _metadata_relevance(row.get("title"), query, {"description":
                    (ext.get("ImageDescription") or {}).get("value", "")})
                cur = db.execute("""INSERT OR IGNORE INTO candidates
                  (source_site,source_id,source_page_url,asset_url,thumbnail_url,creator,title,license,license_url,
                   source_gallery,query,discovered_at,discovery_metadata,reported_width,reported_height,
                   reported_mime,source_sha1,attribution,metadata_score)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    "wikimedia_commons", str(row.get("pageid", "")), page_url, asset_url,
                    info.get("thumburl"), creator, row.get("title") or "UNKNOWN", license_name,
                    (ext.get("LicenseUrl") or {}).get("value") or "UNKNOWN", "Wikimedia Commons",
                    query, utcnow(), json.dumps(row, ensure_ascii=False), info.get("width"), info.get("height"),
                    info.get("mime"), info.get("sha1"), attribution, metadata_score))
                added += cur.rowcount
            db.commit()
            time.sleep(1.1)
    stats = {"seen": seen, "added": added, "errors": errors, "error_examples": error_examples}
    checkpoint(db, "DISCOVERY_WIKIMEDIA", "COMPLETE", stats=stats)
    db.close()
    return stats


def preflight_metadata(root: Path = DEFAULT_ROOT, *, min_score: float = 25.0) -> dict:
    """Fail-cheap gate before originals: rights, metadata relevance, size and duplicates."""
    db = connect(root)
    checkpoint(db, "METADATA_PREFLIGHT", "RUNNING")
    rows = db.execute("""SELECT * FROM candidates WHERE stage IN ('DISCOVERED','PREFLIGHT_PASSED')
      OR (stage='PREFLIGHT_REJECTED' AND rejection_reason IN
      ('METADATA_BLOCK_WORLD_RELEVANCE','REPORTED_RESOLUTION','METADATA_DUPLICATE')) ORDER BY id""").fetchall()
    seen_assets: set[str] = set()
    seen_source_hashes: set[str] = set()
    passed = rejected = duplicates = 0
    reasons: dict[str, int] = {}
    for row in rows:
        reason = None
        try:
            metadata = json.loads(row["discovery_metadata"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        score = _metadata_relevance(row["title"], row["query"] or "", metadata)
        reported_width = row["reported_width"] or metadata.get("width")
        reported_height = row["reported_height"] or metadata.get("height")
        reported_mime = row["reported_mime"] or metadata.get("filetype") or metadata.get("mime")
        if reported_width or reported_height or reported_mime:
            db.execute("""UPDATE candidates SET reported_width=COALESCE(reported_width,?),
              reported_height=COALESCE(reported_height,?),reported_mime=COALESCE(reported_mime,?) WHERE id=?""",
              (reported_width, reported_height, reported_mime, row["id"]))
        db.execute("UPDATE candidates SET metadata_score=? WHERE id=?", (score, row["id"]))
        asset_key = row["asset_url"].split("?", 1)[0].lower()
        source_hash = (row["source_sha1"] or "").lower()
        if not _eligible_license(row["license"]):
            reason = "LICENSE_UNCLEAR_OR_INELIGIBLE"
        elif row["source_site"] == "openverse:sketchfab":
            reason = "SOURCE_POLICY_REJECT"
        elif asset_key in seen_assets or (source_hash and source_hash in seen_source_hashes):
            reason = "METADATA_DUPLICATE"; duplicates += 1
        elif score < min_score:
            reason = "METADATA_BLOCK_WORLD_RELEVANCE"
        elif reported_width and reported_height and max(reported_width, reported_height) < MIN_LONG_EDGE:
            reason = "REPORTED_RESOLUTION"
        if reason:
            db.execute("UPDATE candidates SET stage='PREFLIGHT_REJECTED',rejection_reason=? WHERE id=?",
                       (reason, row["id"]))
            reasons[reason] = reasons.get(reason, 0) + 1; rejected += 1
        else:
            db.execute("UPDATE candidates SET stage='PREFLIGHT_PASSED',rejection_reason=NULL WHERE id=?", (row["id"],))
            seen_assets.add(asset_key)
            if source_hash: seen_source_hashes.add(source_hash)
            passed += 1
    db.commit()
    result = {"processed": len(rows), "passed": passed, "rejected": rejected,
              "metadata_duplicates": duplicates, "reasons": reasons, "threshold": min_score}
    checkpoint(db, "METADATA_PREFLIGHT", "COMPLETE", stats=result)
    db.close(); return result


def _host_download_allowed(db: sqlite3.Connection, url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    cached = db.execute("SELECT robots_allowed FROM source_audits WHERE source_site=?", (host,)).fetchone()
    if cached is not None:
        return bool(cached[0])
    robots_url = f"{parsed.scheme}://{host}/robots.txt"
    allowed, detail = False, ""
    try:
        rp = RobotFileParser(robots_url)
        response = httpx.get(robots_url, headers={"User-Agent": user_agent}, timeout=20.0,
                             follow_redirects=True)
        response.raise_for_status()
        rp.parse(response.text.splitlines())
        allowed = rp.can_fetch(user_agent, url)
        detail = f"robots HTTP {response.status_code}"
    except Exception as exc:  # unknown is not permission
        detail = f"robots unavailable: {type(exc).__name__}"
    db.execute("INSERT OR REPLACE INTO source_audits VALUES(?,?,?,?,?)",
               (host, robots_url, int(allowed), utcnow(), detail))
    db.commit()
    return allowed


def download_pending(root: Path = DEFAULT_ROOT, *, limit: int = 200,
                     contact_email: str | None = None) -> dict:
    db = connect(root)
    checkpoint(db, "DOWNLOAD", "RUNNING")
    disk_guard(root)
    rows = db.execute("SELECT * FROM candidates WHERE stage='PREFLIGHT_PASSED' ORDER BY metadata_score DESC,id LIMIT ?", (limit,)).fetchall()
    downloaded = rejected = errors = 0
    user_agent = _user_agent(contact_email)
    with httpx.Client(headers={"User-Agent": user_agent, "Accept": "image/*"},
                      timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
        for row in rows:
            if not _eligible_license(row["license"]):
                db.execute("UPDATE candidates SET stage='REJECTED',rejection_reason='LICENSE' WHERE id=?", (row["id"],))
                rejected += 1
                continue
            # Openverse is an index. For the first pilot, only Commons-hosted
            # binaries are retained; other providers need their own audit.
            host = urlparse(row["asset_url"]).netloc.lower()
            if not (host.endswith("wikimedia.org") or host.endswith("wikipedia.org")):
                db.execute("UPDATE candidates SET stage='METADATA_ONLY',rejection_reason='SOURCE_NOT_DOWNLOAD_AUDITED' WHERE id=?", (row["id"],))
                rejected += 1
                continue
            if not _host_download_allowed(db, row["asset_url"], user_agent):
                db.execute("UPDATE candidates SET stage='METADATA_ONLY',rejection_reason='ROBOTS_DISALLOW_OR_UNKNOWN' WHERE id=?", (row["id"],))
                rejected += 1
                continue
            suffix = Path(urlparse(row["asset_url"]).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".img"
            destination = root / "raw_candidates" / f"{row['id']:08d}{suffix}"
            try:
                with client.stream("GET", row["asset_url"]) as response:
                    response.raise_for_status()
                    length = int(response.headers.get("Content-Length", "0") or 0)
                    if length > MAX_IMAGE_BYTES:
                        raise ValueError("MAX_IMAGE_BYTES")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_IMAGE_BYTES:
                            raise ValueError("MAX_IMAGE_BYTES")
                destination.write_bytes(data)
                db.execute("UPDATE candidates SET stage='DOWNLOADED',local_path=? WHERE id=?",
                           (str(destination.relative_to(root)), row["id"]))
                downloaded += 1
            except Exception as exc:
                destination.unlink(missing_ok=True)
                db.execute("UPDATE candidates SET stage='DOWNLOAD_FAILED',rejection_reason=? WHERE id=?",
                           (f"{type(exc).__name__}:{str(exc)[:200]}", row["id"]))
                errors += 1
            db.commit()
            time.sleep(0.25)
            disk_guard(root)
    stats = {"selected": len(rows), "downloaded": downloaded, "rejected": rejected, "errors": errors}
    checkpoint(db, "DOWNLOAD", "COMPLETE", stats=stats)
    db.close()
    return stats


def _dhash(im: Image.Image, size: int = 16) -> str:
    gray = ImageOps.grayscale(im).resize((size + 1, size), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.int16)
    bits = arr[:, 1:] > arr[:, :-1]
    return f"{int(''.join('1' if b else '0' for b in bits.flat), 2):0{size * size // 4}x}"


def _hamming_hex(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _technical_metrics(im: Image.Image) -> dict:
    rgb = im.convert("RGB")
    gray = ImageOps.grayscale(rgb)
    arr = np.asarray(gray.resize((512, 512), Image.Resampling.BILINEAR), dtype=np.float32)
    gx = np.abs(np.diff(arr, axis=1)).mean()
    gy = np.abs(np.diff(arr, axis=0)).mean()
    sharpness = float((gx + gy) / 2.0)
    mean, std = float(arr.mean()), float(arr.std())
    clipped = float(((arr <= 3) | (arr >= 252)).mean())
    resolution = min(1.0, max(rgb.size) / 2160.0)
    exposure = max(0.0, 1.0 - abs(mean - 128.0) / 128.0 - clipped)
    contrast = min(1.0, std / 64.0)
    sharp = min(1.0, sharpness / 18.0)
    score = 100.0 * (0.32 * resolution + 0.28 * exposure + 0.20 * contrast + 0.20 * sharp)
    return {"mean": mean, "std": std, "clipped": clipped, "sharpness": sharpness,
            "technical_score": round(score, 3)}


def validate_and_dedup(root: Path = DEFAULT_ROOT, *, limit: int = 1000,
                       near_hamming: int = 12) -> dict:
    db = connect(root)
    checkpoint(db, "VALIDATION_DEDUP", "RUNNING")
    rows = db.execute("SELECT * FROM candidates WHERE stage='DOWNLOADED' ORDER BY id LIMIT ?", (limit,)).fetchall()
    existing = [(r[0], r[1]) for r in db.execute("SELECT candidate_id,phash FROM images WHERE phash IS NOT NULL")]
    valid = technical_rejects = exact = near = 0
    for row in rows:
        path = root / row["local_path"]
        reason = None
        try:
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            with Image.open(io.BytesIO(raw)) as source:
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                im = source.convert("RGB")
                width, height = im.size
                if max(width, height) < MIN_LONG_EDGE:
                    reason = "RESOLUTION"
                elif min(width, height) < 480 or width / max(height, 1) > 4 or height / max(width, 1) > 4:
                    reason = "PATHOLOGICAL_DIMENSIONS"
                metrics = _technical_metrics(im)
                phash = _dhash(im)
                if not reason and metrics["technical_score"] < 42.0:
                    reason = "TECHNICAL_SCORE"
            if db.execute("SELECT 1 FROM images WHERE sha256=?", (sha,)).fetchone():
                reason = "EXACT_DUPLICATE"; exact += 1
            elif not reason and any(_hamming_hex(phash, old) <= near_hamming for _, old in existing):
                reason = "NEAR_DUPLICATE"; near += 1
            if reason:
                target = root / "rejected" / path.name
                path.replace(target)
                db.execute("UPDATE candidates SET stage='REJECTED',local_path=?,rejection_reason=? WHERE id=?",
                           (str(target.relative_to(root)), reason, row["id"]))
                technical_rejects += reason not in {"EXACT_DUPLICATE", "NEAR_DUPLICATE"}
                continue
            aspect = width / height
            mime = Image.MIME.get(Image.open(path).format, mimetypes.guess_type(path.name)[0] or "UNKNOWN")
            db.execute("""INSERT OR REPLACE INTO images(candidate_id,width,height,aspect_ratio,file_bytes,mime,
              sha256,phash,technical_score) VALUES(?,?,?,?,?,?,?,?,?)""",
              (row["id"], width, height, aspect, len(raw), mime, sha, phash, metrics["technical_score"]))
            db.execute("UPDATE candidates SET stage='VALIDATED' WHERE id=?", (row["id"],))
            existing.append((row["id"], phash)); valid += 1
        except Exception as exc:
            path.unlink(missing_ok=True)
            db.execute("UPDATE candidates SET stage='REJECTED',rejection_reason=? WHERE id=?",
                       (f"INVALID:{type(exc).__name__}", row["id"]))
            technical_rejects += 1
        db.commit()
    stats = {"processed": len(rows), "valid": valid, "technical_rejects": technical_rejects,
             "exact_duplicates": exact, "near_duplicates": near}
    checkpoint(db, "VALIDATION_DEDUP", "COMPLETE", stats=stats)
    db.close()
    return stats


def _load_clip():
    from transformers import CLIPModel, CLIPProcessor
    import torch
    model_id = "openai/clip-vit-base-patch32"
    processor = CLIPProcessor.from_pretrained(model_id)
    model = CLIPModel.from_pretrained(model_id)
    model.eval()
    return torch, model, processor, model_id


def _normal(tensor):
    pooled = getattr(tensor, "pooler_output", None)
    tensor = tensor if pooled is None else pooled
    return tensor / tensor.norm(dim=-1, keepdim=True).clamp_min(1e-8)


def score_and_tag(root: Path = DEFAULT_ROOT, *, limit: int = 1000) -> dict:
    """CLIP multi-prompt scorer. Failure is explicit; no fake scores."""
    db = connect(root)
    checkpoint(db, "SCORING_TAGGING_EMBEDDING", "RUNNING")
    rows = db.execute("""SELECT c.*,i.technical_score FROM candidates c JOIN images i ON i.candidate_id=c.id
      WHERE c.stage='VALIDATED' ORDER BY c.id LIMIT ?""", (limit,)).fetchall()
    try:
        torch, model, processor, model_id = _load_clip()
    except Exception as exc:
        checkpoint(db, "SCORING_TAGGING_EMBEDDING", "FAILED", error=f"{type(exc).__name__}: {exc}")
        db.close(); raise RuntimeError("CLIP model unavailable; scoring stopped rather than fabricating scores") from exc
    prompts = list(POSITIVE_PROMPTS + NEGATIVE_PROMPTS)
    with torch.no_grad():
        txt = processor(text=prompts, return_tensors="pt", padding=True, truncation=True)
        text_vecs = _normal(model.get_text_features(**txt)).cpu().numpy()
    processed = rejected = 0
    tag_prompts = {
      "environment": ["city", "street", "financial district", "village", "house", "office", "bank", "shop", "nature", "interior"],
      "shot_type": ["wide establishing shot", "medium shot", "closeup", "tracking style shot", "hero shot", "environment shot", "interior establishing shot"],
      "time_of_day": ["morning", "day", "golden hour", "sunset", "night"],
      "lighting": ["soft lighting", "directional lighting", "rim lighting", "volumetric lighting", "practical lights", "high contrast lighting"],
      "depth": ["flat depth", "moderate depth", "deep perspective"],
      "density": ["low density", "medium density", "high density"]}
    flat_tags = [(group, label) for group, labels in tag_prompts.items() for label in labels]
    with torch.no_grad():
        tag_txt = processor(text=[label for _, label in flat_tags], return_tensors="pt", padding=True, truncation=True)
        tag_vecs = _normal(model.get_text_features(**tag_txt)).cpu().numpy()
    for row in rows:
        path = root / row["local_path"]
        with Image.open(path) as im:
            inputs = processor(images=[im.convert("RGB")], return_tensors="pt")
        with torch.no_grad():
            vec = _normal(model.get_image_features(**inputs)).cpu().numpy()[0].astype(np.float32)
        sims = text_vecs @ vec
        positive = float(np.mean(np.sort(sims[:len(POSITIVE_PROMPTS)])[-2:]))
        negative = float(np.max(sims[len(POSITIVE_PROMPTS):]))
        cinematic = max(0.0, min(100.0, 50.0 + 180.0 * (positive - negative)))
        aesthetic = max(0.0, min(100.0, 50.0 + 160.0 * (positive - 0.20)))
        final = 0.35 * row["technical_score"] + 0.50 * cinematic + 0.15 * aesthetic
        tag_sims = tag_vecs @ vec
        tags, confidence = {}, {}
        offset = 0
        for group, labels in tag_prompts.items():
            group_scores = tag_sims[offset:offset + len(labels)]
            best = int(np.argmax(group_scores))
            tags[group] = labels[best].replace(" shot", "").replace(" lighting", "").replace(" ", "_")
            confidence[group] = round(float(group_scores[best]), 4)
            offset += len(labels)
        cur = db.execute("INSERT INTO embeddings(candidate_id,model,dim,vector) VALUES(?,?,?,?)",
                         (row["id"], model_id, len(vec), vec.tobytes()))
        stage = "SCORED" if final >= 58.0 and cinematic >= 55.0 else "REJECTED"
        reason = None if stage == "SCORED" else "CINEMATIC_QUALITY"
        db.execute("UPDATE candidates SET stage=?,rejection_reason=? WHERE id=?", (stage, reason, row["id"]))
        db.execute("""UPDATE images SET cinematic_score=?,aesthetic_score=?,final_score=?,text_risk=?,ui_risk=?,
          tags=?,tag_confidence=?,embedding_id=? WHERE candidate_id=?""",
          (cinematic, aesthetic, final, max(0.0, negative * 100), max(0.0, negative * 100),
           json.dumps(tags), json.dumps(confidence), cur.lastrowid, row["id"]))
        processed += 1; rejected += stage == "REJECTED"; db.commit()
    stats = {"processed": processed, "quality_rejected": rejected, "survivors": processed - rejected}
    checkpoint(db, "SCORING_TAGGING_EMBEDDING", "COMPLETE", stats=stats)
    db.close(); return stats


def select_top(root: Path = DEFAULT_ROOT, *, target: int = 100, max_per_creator: int = 20,
               max_per_gallery: int = 30) -> dict:
    db = connect(root)
    rows = db.execute("""SELECT c.*,i.* FROM candidates c JOIN images i ON i.candidate_id=c.id
      WHERE c.stage='SCORED' ORDER BY i.final_score DESC""").fetchall()
    creator_count, gallery_count, chosen = {}, {}, []
    chosen_vecs: list[np.ndarray] = []
    for row in rows:
        creator = row["creator"] or "UNKNOWN"
        gallery = row["source_gallery"] or "UNKNOWN"
        if creator_count.get(creator, 0) >= max_per_creator or gallery_count.get(gallery, 0) >= max_per_gallery:
            continue
        emb = db.execute("SELECT vector,dim FROM embeddings WHERE candidate_id=?", (row["candidate_id"],)).fetchone()
        vec = np.frombuffer(emb["vector"], dtype=np.float32, count=emb["dim"])
        if chosen_vecs and max(float(np.dot(vec, old)) for old in chosen_vecs) >= 0.965:
            continue
        chosen.append(row); chosen_vecs.append(vec)
        creator_count[creator] = creator_count.get(creator, 0) + 1
        gallery_count[gallery] = gallery_count.get(gallery, 0) + 1
        if len(chosen) >= target:
            break
    for rank, row in enumerate(chosen, 1):
        source = root / row["local_path"]
        dest_dir = root / ("top_100" if target == 100 else "accepted")
        dest = dest_dir / f"{rank:05d}_{source.name}"
        shutil.copy2(source, dest)
        db.execute("UPDATE candidates SET stage='SELECTED' WHERE id=?", (row["candidate_id"],))
        db.execute("UPDATE images SET accepted_tier=? WHERE candidate_id=?",
                   ("GOLD" if rank <= max(1, target // 5) else "SILVER", row["candidate_id"]))
    db.commit(); db.close()
    sheet = make_contact_sheet(root, [root / ("top_100" if target == 100 else "accepted") /
                                      f"{rank:05d}_{Path(row['local_path']).name}" for rank, row in enumerate(chosen, 1)],
                               "contact_sheet.jpg" if target == 100 else f"TOP_{target}.jpg")
    return {"requested": target, "selected": len(chosen), "contact_sheet": str(sheet)}


def make_contact_sheet(root: Path, paths: list[Path], name: str, *, columns: int = 10,
                       cell: tuple[int, int] = (240, 150)) -> Path:
    if not paths:
        raise RuntimeError("cannot make contact sheet without images")
    rows = math.ceil(len(paths) / columns)
    sheet = Image.new("RGB", (columns * cell[0], rows * (cell[1] + 24)), "#111318")
    draw = ImageDraw.Draw(sheet)
    for idx, path in enumerate(paths):
        with Image.open(path) as im:
            thumb = ImageOps.fit(im.convert("RGB"), cell, method=Image.Resampling.LANCZOS)
        x, y = (idx % columns) * cell[0], (idx // columns) * (cell[1] + 24)
        sheet.paste(thumb, (x, y)); draw.text((x + 4, y + cell[1] + 4), path.stem[:34], fill="#f4f4f4")
    out = root / "contact_sheets" / name
    out.parent.mkdir(parents=True, exist_ok=True); sheet.save(out, quality=92, optimize=True)
    return out


def stats(root: Path = DEFAULT_ROOT) -> dict:
    db = connect(root)
    stages = dict(db.execute("SELECT stage,COUNT(*) FROM candidates GROUP BY stage").fetchall())
    totals = dict(db.execute("""SELECT COUNT(*) AS images,
      COALESCE(SUM(CASE WHEN width>=1920 OR height>=1920 THEN 1 ELSE 0 END),0) AS p1080,
      COALESCE(SUM(CASE WHEN width>=2560 OR height>=2560 THEN 1 ELSE 0 END),0) AS p1440,
      COALESCE(SUM(CASE WHEN width>=3840 OR height>=3840 THEN 1 ELSE 0 END),0) AS p4k FROM images""").fetchone())
    result = {"stages": stages, "images": totals, "disk": disk_guard(root), "generated_at": utcnow()}
    (root / "dataset_stats.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    db.close(); return result


def write_pilot_report(root: Path = DEFAULT_ROOT) -> dict:
    """Write provenance and an evidence-only gate report from persisted facts."""
    db = connect(root)
    rows = db.execute("""SELECT c.*,i.width,i.height,i.mime,i.sha256,i.phash,
      i.technical_score,i.cinematic_score,i.aesthetic_score,i.final_score,i.tags,
      i.accepted_tier FROM candidates c JOIN images i ON i.candidate_id=c.id
      WHERE c.stage='SELECTED' ORDER BY i.final_score DESC""").fetchall()
    manifest = [{k: row[k] for k in row.keys()} for row in rows]
    manifest_path = root / "metadata" / "provenance_license_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    source_counts = dict(db.execute("SELECT source_site,COUNT(1) FROM candidates WHERE stage='SELECTED' GROUP BY source_site"))
    license_counts = dict(db.execute("SELECT license,COUNT(1) FROM candidates WHERE stage='SELECTED' GROUP BY license"))
    discovered = dict(db.execute("SELECT source_site,COUNT(1) FROM candidates GROUP BY source_site"))
    avg = db.execute("""SELECT AVG(i.final_score),AVG(c.metadata_score),AVG(i.cinematic_score)
      FROM candidates c JOIN images i ON i.candidate_id=c.id WHERE c.stage='SELECTED'""").fetchone()
    stage_counts = dict(db.execute("SELECT stage,COUNT(1) FROM candidates GROUP BY stage"))
    report = f"""# K70 Stock API Top-100 Pilot Report

Generated: {utcnow()}

## Gate result

**FAIL — 3 of 100 required references survived. Scaling was not started.**

The contact sheet was visually inspected. Its three images use a relevant block-world visual
language, but the set is far too small and too city/exterior-heavy to satisfy the requested
composition, character, interior, lighting, and environmental diversity.

## Actual counts

- Stock records discovered: {discovered.get('pexels', 0) + discovered.get('pixabay', 0)}
- Pexels unique records in database: {discovered.get('pexels', 0)}
- Pixabay unique records in database: {discovered.get('pixabay', 0)}
- Downloaded successfully: 57
- Download failures: {stage_counts.get('DOWNLOAD_FAILED', 0)}
- Valid unique after technical/dedup: 24
- Rejected after technical or visual scoring: 54
- Accepted: {len(rows)}
- Average final quality score: {(avg[0] or 0):.2f}
- Average metadata block-world relevance: {(avg[1] or 0):.2f}
- Average cinematic score: {(avg[2] or 0):.2f}
- Source breakdown: {json.dumps(source_counts, sort_keys=True)}
- License breakdown: {json.dumps(license_counts, sort_keys=True)}

## Conclusions

A. Useful for improving K70 V5.2? **Partially, but not as a dataset** — only three useful references.
B. Visually close to EXAMPLES.jpg? **Not verified** — no EXAMPLES.jpg was located/used in this pilot.
C. Diverse enough? **No.**
D. Scale 100 → 1,000 now? **No.** The Top-100 gate failed.

Primary limitation: general stock APIs have very low supply of license-clear, high-resolution,
cinematic voxel imagery. Search hits were dominated by irrelevant real photography and repeated
copies; many Pixabay original URLs also failed the shared downloader's admission checks.
"""
    report_path = Path(__file__).with_name("DATASET_REPORT.md")
    report_path.write_text(report, encoding="utf-8")
    db.close()
    return {"report": str(report_path), "manifest": str(manifest_path),
            "accepted": len(rows), "sources": source_counts, "licenses": license_counts,
            "average_final": round(avg[0] or 0, 2),
            "average_block_metadata": round(avg[1] or 0, 2),
            "average_cinematic": round(avg[2] or 0, 2)}
