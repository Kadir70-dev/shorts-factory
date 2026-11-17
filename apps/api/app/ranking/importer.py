"""
Import locally available source videos with a provenance record.

    python -m app.ranking import-sources FILES_OR_DIRS... --kind compilation \\
        --license licensed --proof "Contract #42 with Studio X" \\
        --underlying-proof "Studio X warrants rights to all included clips" \\
        --attribution "Studio X" --category animals --batch studio_x_2026_11

What it does, per file:
  1. hash it and check it against the reference inventory (filename, yt-dlp
     .info.json sidecar). A match is recorded as `provenance_ref`, and such a
     source can't become selectable without written permission AND rights to
     the clips inside.
  2. hard-link (or copy) it into data/ranking/sources/imports/<batch>/ so the
     catalogued bytes can't change under us.
  3. write its license record into that folder's licenses.yaml: unverified,
     with original path, sha256 and import time.
  4. register and analyse it. Compilations go through the Top-5 segmenter;
     single clips go through moment suggestion.

Importing never verifies anything. That stays `verify-source`, a human step.
Nothing here downloads media.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
from pathlib import Path

import yaml

from . import catalog, probe, reference
from .db import RANKING_DIR

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _files(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix.lower() in VIDEO_EXT)
        elif p.suffix.lower() in VIDEO_EXT:
            out.append(p)
        else:
            raise ValueError(f"not a video or folder: {p}")
    return out


def _sidecar_meta(video: Path) -> dict:
    side = video.with_suffix(".info.json")
    if not side.exists():
        return {}
    try:
        info = json.loads(side.read_text())
    except json.JSONDecodeError:
        return {}
    return {"title": info.get("title", ""), "origin_url": info.get("webpage_url", ""),
            "uploader": info.get("uploader", ""), "tags": info.get("tags") or []}


def import_sources(con, paths: list[Path], *, kind: str, license: str, proof: str,
                   batch: str, attribution: str = "", underlying_proof: str = "",
                   category: str = "", moment_labels: list[str] | None = None,
                   copy: bool = False) -> list[dict]:
    if kind not in ("clip", "compilation"):
        raise ValueError("kind must be clip or compilation")
    if not batch.replace("_", "").replace("-", "").isalnum():
        raise ValueError("batch must be letters, digits, - or _")
    dest_dir = RANKING_DIR / "sources" / "imports" / batch
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dest_dir / "licenses.yaml"
    manifest = (yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else {}) or {}
    report = []
    for src in _files(paths):
        src = src.resolve()
        digest = probe.sha256(src)
        meta = _sidecar_meta(src)
        ref = reference.match_ref(con, src, meta)
        dest = dest_dir / f"{src.stem}_{digest[:8]}{src.suffix.lower()}"
        if not dest.exists():
            try:
                if copy:
                    raise OSError
                os.link(src, dest)
            except OSError:
                shutil.copy2(src, dest)
        record = manifest.get(dest.name, {})
        if record.get("verified"):
            record_note = "kept existing verification"
        else:
            record_note = "unverified"
            record.update({
                "kind": kind, "license": license, "verified": False, "proof": proof,
                "attribution": attribution or meta.get("uploader", ""),
                "category": category, "title": meta.get("title", "") or src.stem,
                "origin_url": meta.get("origin_url", ""),
                "underlying_proof": underlying_proof, "underlying_verified": False,
            })
        record.update({"original_path": str(src), "sha256": digest,
                       "imported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "provenance_ref": ref})
        if moment_labels:
            record["moment_labels"] = moment_labels
        manifest[dest.name] = record
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True, allow_unicode=True))
        sid = catalog.register(con, dest)
        segs = catalog.analyse(con, sid)
        row = con.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        seg = json.loads(row["segmentation"] or "{}")
        report.append({"source_id": sid, "file": dest.name, "kind": kind,
                       "segments": len(segs), "provenance_ref": ref or None,
                       "top5": seg.get("status"), "confidence": seg.get("confidence"),
                       "topic": row["category"] or "unknown", "rights": record_note})
    return report
