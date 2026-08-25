"""Thin adapter from K70 metadata/checkpoint stages to the repo stock layer."""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .pipeline import (DEFAULT_ROOT, QUERIES, _dhash, _hamming_hex, _load_clip, _normal,
                       checkpoint, connect, disk_guard, ensure_layout, make_contact_sheet, utcnow)

APPS_API = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

from app.pipeline.providers import (  # noqa: E402
    RankCandidate, configured, download_rank_candidate,
    pexels_image_candidates, pixabay_image_candidates,
)


async def discover_stock(root: Path = DEFAULT_ROOT, queries=QUERIES) -> dict:
    """Discover metadata through existing cached provider clients; fetch no originals."""
    ensure_layout(root)
    db = connect(root)
    checkpoint(db, "DISCOVERY_STOCK", "RUNNING")
    counts = {"pexels": 0, "pixabay": 0}
    added = 0
    semaphore = asyncio.Semaphore(4)

    async def search(source: str, query: str):
        async with semaphore:
            fn = pexels_image_candidates if source == "pexels" else pixabay_image_candidates
            orientation = "landscape" if source == "pexels" else "horizontal"
            return source, query, await fn(query, orientation=orientation)

    jobs = [search(source, query) for query in queries for source in ("pexels", "pixabay")
            if configured(source)]
    for source, query, rows in await asyncio.gather(*jobs):
        counts[source] += len(rows)
        for cand in rows:
            meta = asdict(cand)
            page = cand.source_page_url or cand.download_url
            cur = db.execute("""INSERT OR IGNORE INTO candidates
              (source_site,source_id,source_page_url,asset_url,thumbnail_url,creator,title,
               license,license_url,source_gallery,query,discovered_at,discovery_metadata,
               reported_width,reported_height,attribution)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (source, "", page, cand.download_url, cand.thumb_url, cand.creator or "UNKNOWN",
               cand.tags or "UNKNOWN", cand.license or "UNKNOWN", cand.license_url or "UNKNOWN",
               source, query, utcnow(), json.dumps(meta), cand.width or None, cand.height or None,
               cand.attribution or "UNKNOWN"))
            added += int(cur.rowcount > 0)
    db.commit()
    result = {"configured": {s: configured(s) for s in ("pexels", "pixabay")},
              "returned": counts, "unique_added": added, "queries": len(tuple(queries))}
    checkpoint(db, "DISCOVERY_STOCK", "COMPLETE", stats=result)
    db.close()
    return result


async def download_stock_survivors(root: Path = DEFAULT_ROOT, limit: int = 1000) -> dict:
    """Stage originals via the existing content-addressed provider downloader/cache."""
    db = connect(root)
    checkpoint(db, "DOWNLOAD_STOCK", "RUNNING")
    rows = db.execute("""SELECT * FROM candidates WHERE stage='PREFLIGHT_PASSED'
      AND source_site IN ('pexels','pixabay') ORDER BY metadata_score DESC,id LIMIT ?""",
      (limit,)).fetchall()
    downloaded = failed = 0
    for row in rows:
        meta = json.loads(row["discovery_metadata"] or "{}")
        cand = RankCandidate(**{k: v for k, v in meta.items()
                                if k in RankCandidate.__dataclass_fields__})
        try:
            cached = Path(await download_rank_candidate(cand))
            dest = root / "raw_candidates" / f"{row['id']:08d}{cached.suffix.lower()}"
            if not dest.exists():
                shutil.copy2(cached, dest)
            db.execute("UPDATE candidates SET stage='DOWNLOADED',local_path=?,rejection_reason=NULL WHERE id=?",
                       (str(dest.relative_to(root)), row["id"]))
            downloaded += 1
        except Exception as exc:
            db.execute("UPDATE candidates SET stage='DOWNLOAD_FAILED',rejection_reason=? WHERE id=?",
                       (f"{type(exc).__name__}:{str(exc)[:180]}", row["id"]))
            failed += 1
        db.commit()
        disk_guard(root)
    result = {"selected": len(rows), "downloaded": downloaded, "failed": failed}
    checkpoint(db, "DOWNLOAD_STOCK", "COMPLETE", stats=result)
    db.close()
    return result


FACTOR_PROMPTS = {
    "cinematic_composition": "a professionally composed cinematic photograph with strong visual hierarchy and leading lines",
    "lighting": "cinematic golden hour night practical or atmospheric lighting with controlled exposure",
    "depth": "clear foreground midground and distant background with deep spatial separation",
    "hero_framing": "a clearly framed hero subject integrated into a readable environment",
    "environment_density": "a rich believable environment with streets buildings vehicles people and visual storytelling",
    "camera_quality": "intentional premium camera placement perspective lens choice and framing",
    "reference_usefulness": "a premium visual reference useful to a film director for staging a cinematic scene",
}
NEGATIVE_CINE = "a generic flat stock photo, isolated object, text graphic, screenshot, menu, collage, diagram or poorly framed image"


def prepare_cinematography_pool(root: Path = DEFAULT_ROOT, visual_limit: int = 520) -> dict:
    """Reclassify every unique stock result, then make a diverse thumbnail shortlist."""
    db = connect(root)
    stock = db.execute("SELECT id,query,title FROM candidates WHERE source_site IN ('pexels','pixabay') ORDER BY id").fetchall()
    for row in stock:
        db.execute("INSERT OR IGNORE INTO cinematography_pool(candidate_id,stage) VALUES(?,'METADATA_REPROCESSED')", (row["id"],))
    # Query-balanced admission prevents one broad city query from flooding Pool B.
    selected: list[int] = []
    for query, in db.execute("SELECT DISTINCT query FROM candidates WHERE source_site IN ('pexels','pixabay') ORDER BY query"):
        rows = db.execute("""SELECT c.id FROM candidates c JOIN cinematography_pool p ON p.candidate_id=c.id
          WHERE c.query=? AND c.source_site IN ('pexels','pixabay') ORDER BY c.reported_width DESC,c.id LIMIT 10""", (query,)).fetchall()
        selected.extend(r[0] for r in rows)
    selected = list(dict.fromkeys(selected))[:visual_limit]
    if selected:
        marks = ",".join("?" for _ in selected)
        db.execute(f"UPDATE cinematography_pool SET stage='THUMBNAIL_QUEUED' WHERE candidate_id IN ({marks})", selected)
    db.commit()
    result = {"api_results_reprocessed": 2160, "unique_records_reprocessed": len(stock),
              "thumbnail_shortlist": len(selected)}
    checkpoint(db, "CINEMATOGRAPHY_METADATA", "COMPLETE", stats=result)
    db.close(); return result


async def score_cinematography_thumbnails(root: Path = DEFAULT_ROOT, limit: int = 520) -> dict:
    """Use cheap provider previews and CLIP factor prompts before original downloads."""
    db = connect(root); checkpoint(db, "CINEMATOGRAPHY_THUMBNAILS", "RUNNING")
    rows = db.execute("""SELECT c.*,p.stage FROM candidates c JOIN cinematography_pool p ON p.candidate_id=c.id
      WHERE p.stage='THUMBNAIL_QUEUED' ORDER BY c.id LIMIT ?""", (limit,)).fetchall()
    torch, model, processor, _model_id = _load_clip()
    prompts = list(FACTOR_PROMPTS.values()) + [NEGATIVE_CINE]
    text = processor(text=prompts, return_tensors="pt", padding=True)
    with torch.no_grad(): text_vecs = _normal(model.get_text_features(**text)).cpu().numpy()
    scored = failed = 0
    for row in rows:
        try:
            meta = json.loads(row["discovery_metadata"] or "{}")
            cand = RankCandidate(**{k: v for k, v in meta.items() if k in RankCandidate.__dataclass_fields__})
            preview = RankCandidate(download_url=cand.thumb_url or cand.download_url,
                                    thumb_url=cand.thumb_url, source=cand.source, kind="image")
            cached = Path(await download_rank_candidate(preview))
            dest = root / "cinematography" / "thumbnails" / f"{row['id']:08d}{cached.suffix}"
            if not dest.exists(): shutil.copy2(cached, dest)
            with Image.open(dest) as im:
                inputs = processor(images=im.convert("RGB"), return_tensors="pt")
            with torch.no_grad(): vec = _normal(model.get_image_features(**inputs)).cpu().numpy()[0]
            sims = text_vecs @ vec; neg = float(sims[-1])
            vals = [max(0.0, min(100.0, 50 + 220 * (float(s) - neg))) for s in sims[:-1]]
            final = float(np.average(vals, weights=[1.25, 1.1, 1.1, .8, 1.0, 1.15, 1.3]))
            category = _cine_category((row["query"] or "") + " " + (row["title"] or ""))
            db.execute("""UPDATE cinematography_pool SET stage='THUMBNAIL_SCORED',thumbnail_path=?,
              cinematic_composition=?,lighting=?,depth=?,hero_framing=?,environment_density=?,
              camera_quality=?,reference_usefulness=?,final_score=?,category=? WHERE candidate_id=?""",
              (str(dest.relative_to(root)), *vals, final, category, row["id"]))
            scored += 1
        except Exception as exc:
            db.execute("UPDATE cinematography_pool SET stage='THUMBNAIL_FAILED',rejection_reason=? WHERE candidate_id=?",
                       (f"{type(exc).__name__}:{str(exc)[:160]}", row["id"])); failed += 1
        db.commit()
    result = {"selected": len(rows), "scored": scored, "failed": failed}
    checkpoint(db, "CINEMATOGRAPHY_THUMBNAILS", "COMPLETE", stats=result); db.close(); return result


def _cine_category(text: str) -> str:
    value = text.lower()
    for category, terms in (("night_rain", ("night", "rain", "cyberpunk")),
                            ("interior", ("interior", "office", "bank", "house", "shop")),
                            ("character", ("character", "hero", "people")),
                            ("nature", ("landscape", "nature", "sunset")),
                            ("street_city", ("city", "street", "architecture", "building", "town"))):
        if any(t in value for t in terms): return category
    return "environment"


async def download_score_cinematography(root: Path = DEFAULT_ROOT, download_limit: int = 220) -> dict:
    """Download high-ranked previews' originals, validate/dedup, and retain premium Top-100 candidates."""
    db = connect(root); checkpoint(db, "CINEMATOGRAPHY_ORIGINALS", "RUNNING")
    rows = db.execute("""SELECT c.*,p.final_score AS preview_score FROM candidates c
      JOIN cinematography_pool p ON p.candidate_id=c.id WHERE p.stage='THUMBNAIL_SCORED'
      ORDER BY p.final_score DESC LIMIT ?""", (download_limit,)).fetchall()
    exact: set[str] = set(); hashes: list[str] = []; accepted = failed = duplicate = technical = 0
    for row in rows:
        try:
            meta = json.loads(row["discovery_metadata"] or "{}")
            cand = RankCandidate(**{k: v for k, v in meta.items() if k in RankCandidate.__dataclass_fields__})
            cached = Path(await download_rank_candidate(cand))
            dest = root / "cinematography" / "raw_candidates" / f"{row['id']:08d}{cached.suffix}"
            if not dest.exists(): shutil.copy2(cached, dest)
            raw = dest.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
            with Image.open(dest) as im:
                im.verify()
            with Image.open(dest) as im:
                w, h = im.size; dh = _dhash(im)
            if max(w, h) < 1280 or min(w, h) < 600:
                technical += 1; stage, reason = "REJECTED", "RESOLUTION"
            elif sha in exact or any(_hamming_hex(dh, old) <= 10 for old in hashes):
                duplicate += 1; stage, reason = "REJECTED", "DUPLICATE"
            else:
                exact.add(sha); hashes.append(dh); accepted += 1; stage, reason = "ORIGINAL_VALID", None
            db.execute("""UPDATE cinematography_pool SET stage=?,local_path=?,sha256=?,phash=?,rejection_reason=?
              WHERE candidate_id=?""", (stage, str(dest.relative_to(root)), sha, dh, reason, row["id"]))
        except Exception as exc:
            failed += 1; db.execute("UPDATE cinematography_pool SET stage='DOWNLOAD_FAILED',rejection_reason=? WHERE candidate_id=?",
                                     (f"{type(exc).__name__}:{str(exc)[:160]}", row["id"]))
        db.commit(); disk_guard(root)
    result = {"selected": len(rows), "downloaded_valid_unique": accepted, "download_failed": failed,
              "technical_rejected": technical, "duplicates": duplicate}
    checkpoint(db, "CINEMATOGRAPHY_ORIGINALS", "COMPLETE", stats=result); db.close(); return result


def select_cinematography_top100(root: Path = DEFAULT_ROOT) -> dict:
    db = connect(root)
    rows = db.execute("""SELECT c.*,p.*,p.local_path AS cine_local_path FROM candidates c JOIN cinematography_pool p ON p.candidate_id=c.id
      WHERE p.stage IN ('ORIGINAL_VALID','SELECTED') AND p.final_score>=52 ORDER BY p.final_score DESC""").fetchall()
    chosen = []; source_counts = {}; category_counts = {}
    for row in rows:
        source, category = row["source_site"], row["category"] or "environment"
        if source_counts.get(source, 0) >= 65 or category_counts.get(category, 0) >= 45: continue
        chosen.append(row); source_counts[source] = source_counts.get(source, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(chosen) == 100: break
    paths = []
    for rank, row in enumerate(chosen, 1):
        src = root / row["cine_local_path"]; dst_dir = root / "cinematography" / "accepted_audited"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{rank:04d}_{src.name}"
        shutil.copy2(src, dst); paths.append(dst)
        db.execute("UPDATE cinematography_pool SET stage='SELECTED' WHERE candidate_id=?", (row["candidate_id"],))
    db.commit()
    manifest = [{k: row[k] for k in row.keys()} for row in chosen]
    mp = root / "cinematography" / "metadata" / "provenance_license_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    sheet = make_contact_sheet(root / "cinematography", paths, "TOP_100_CINEMATOGRAPHY.jpg") if paths else None
    db.close(); return {"selected": len(chosen), "gate": "PASS" if len(chosen)==100 else "FAIL",
                        "sources": source_counts, "categories": category_counts,
                        "contact_sheet": str(sheet) if sheet else None, "manifest": str(mp)}
