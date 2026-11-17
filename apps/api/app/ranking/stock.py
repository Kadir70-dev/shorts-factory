"""
Rights-cleared real footage from Pexels (https://www.pexels.com/license/).

The Pexels License allows free use and modification, including commercial
use, without required attribution. It forbids selling unaltered copies,
redistributing on stock platforms, and showing identifiable people in a bad
light. We credit the creator anyway.

Each download writes its license record into `licenses.yaml` with the per-video
page URL as proof and `verified: false`. A human confirms the record with
`python -m app.ranking verify-source ID --by NAME` before the clip can be
selected. Fetching footage never verifies it.

Note: a channel built entirely from stock compilations can still be judged
"reused content" under YouTube's monetization policy. Holding the license and
being eligible to monetize are separate questions.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from ..config import ROOT, settings

API = "https://api.pexels.com/videos/search"
LICENSE_URL = "https://www.pexels.com/license/"


def _best_file(video: dict, max_w: int = 1920) -> dict | None:
    """Highest-resolution MP4 no wider than `max_w` (CPU budget)."""
    files = [f for f in video.get("video_files", [])
             if f.get("file_type") == "video/mp4" and f.get("width")
             and max(f["width"], f["height"]) <= max_w]
    return max(files, key=lambda f: f["width"] * f["height"], default=None)


def _api_key() -> str:
    """Settings reads `.env` relative to the CWD; the CLI runs from apps/api, so
    fall back to the repo-root .env (the key is never printed)."""
    key = settings().pexels_api_key
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("PEXELS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    return key


def search(query: str, per_page: int = 5, min_dur: int = 6, max_dur: int = 40,
           orientation: str = "") -> list[dict]:
    key = _api_key()
    if not key:
        raise RuntimeError("PEXELS_API_KEY not set in .env")
    params = {"query": query, "per_page": per_page, "size": "medium"}
    if orientation:
        params["orientation"] = orientation
    r = httpx.get(API, params=params, headers={"Authorization": key}, timeout=30)
    r.raise_for_status()
    return [v for v in r.json().get("videos", []) if min_dur <= v["duration"] <= max_dur]


def fetch(queries: list[str], out_dir: Path, category: str, per_query: int = 1) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "licenses.yaml"
    manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = manifest or {}
    got: list[Path] = []
    seen = {m.get("origin_url") for m in manifest.values()}
    for q in queries:
        n = 0
        for v in search(q, per_page=8):
            if v["url"] in seen or n >= per_query:
                continue
            f = _best_file(v)
            if f is None:
                continue
            dest = out_dir / f"pexels_{v['id']}.mp4"
            if not dest.exists():
                with httpx.stream("GET", f["link"], timeout=120, follow_redirects=True) as r:
                    r.raise_for_status()
                    with open(dest, "wb") as fh:
                        for chunk in r.iter_bytes(1 << 16):
                            fh.write(chunk)
            manifest[dest.name] = {
                "license": "licensed", "verified": False,
                "proof": f"Pexels License {LICENSE_URL} — {v['url']}",
                "origin_url": v["url"],
                "attribution": f"Video by {v['user']['name']} on Pexels",
                "category": category, "query": q,
            }
            seen.add(v["url"])
            got.append(dest)
            n += 1
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True, allow_unicode=True))
    return got
