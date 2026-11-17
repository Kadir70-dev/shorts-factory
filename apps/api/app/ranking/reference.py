"""
Reference catalog: study material, never source material.

Imports a channel inventory (for example the @rankzilla23 Shorts listed by
yt-dlp into ~/rankzilla-factory) as METADATA ONLY. `downloaded` is set only when
a matching local file actually exists, so the catalog never implies media we
don't have.

Two uses:
  * study()        title-format patterns (length, prefixes, emoji, CTA phrasing)
                   to inform ORIGINAL copy. The titles are never reused.
  * match_ref()    provenance check. Any imported file whose name, metadata or
                   yt-dlp sidecar carries a reference video id is tagged with
                   `provenance_ref`. It can't become selectable without
                   recorded permission AND verified rights to the clips inside.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

YT_ID = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _parse_inventory(path: Path) -> list[tuple[str, str, int | None]]:
    """Lines of `id | title` or `index | id | title`, or bare ids."""
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if not parts or not parts[0] or parts[0].startswith("["):
            continue
        if len(parts) >= 3 and parts[0].isdigit():
            idx, vid, title = int(parts[0]), parts[1], " | ".join(parts[2:])
        else:
            idx, vid, title = None, parts[0], " | ".join(parts[1:])
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            rows.append((vid, title, idx))
    return rows


def import_inventory(con, directory: Path, channel: str) -> dict:
    """Import every *inventory*/*ids* text file in `directory`. Idempotent:
    titles fill in where a bare-id list had none."""
    local = {m.group(1): p for p in directory.rglob("*") if p.suffix.lower() in VIDEO_EXT
             for m in [YT_ID.search(p.stem)] if m}
    files = sorted(p for p in directory.glob("*.txt")
                   if any(k in p.name for k in ("inventory", "_ids")))
    seen: set[str] = set()
    for f in files:
        for vid, title, idx in _parse_inventory(f):
            seen.add(vid)
            con.execute(
                """INSERT INTO reference_videos (video_id, channel, title, url,
                       playlist_index, inventory, downloaded)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(platform, video_id) DO UPDATE SET
                       title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END,
                       playlist_index = COALESCE(excluded.playlist_index, playlist_index),
                       inventory = CASE WHEN instr(inventory, excluded.inventory) = 0
                                   THEN inventory || ',' || excluded.inventory ELSE inventory END,
                       downloaded = excluded.downloaded""",
                (vid, channel, title, f"https://www.youtube.com/shorts/{vid}", idx,
                 f.name, int(vid in local)))
    total = con.execute("SELECT COUNT(*) FROM reference_videos WHERE channel=?",
                        (channel,)).fetchone()[0]
    return {"files": [f.name for f in files], "ids_seen": len(seen), "catalog_total": total,
            "with_local_media": sum(1 for v in seen if v in local)}


def study(con, channel: str) -> dict:
    titles = [r[0] for r in con.execute(
        "SELECT title FROM reference_videos WHERE channel=? AND title != ''", (channel,))]
    if not titles:
        return {"titles": 0}
    counts = collections.Counter(titles)
    words = collections.Counter(w.lower() for t in titles
                                for w in re.findall(r"[A-Za-z']+", t))
    return {
        "titles": len(titles),
        "distinct_titles": len(counts),
        "most_repeated": counts.most_common(5),
        "share_starting_ranking": round(sum(t.lower().startswith(("ranking", "top 5"))
                                            for t in titles) / len(titles), 3),
        "share_with_emoji": round(sum(bool(EMOJI.search(t)) for t in titles) / len(titles), 3),
        "median_length": sorted(len(t) for t in titles)[len(titles) // 2],
        "top_words": words.most_common(15),
        "note": "patterns inform original copy; titles are never reused verbatim",
    }


def match_ref(con, video: Path, meta: dict | None = None) -> str:
    """Reference video id this file traces to, or ''. Checks the filename, a
    yt-dlp `.info.json` sidecar, and the given metadata (comment/URL tags)."""
    hay = [video.stem]
    side = video.with_suffix(".info.json")
    if side.exists():
        try:
            info = json.loads(side.read_text())
            hay += [str(info.get(k, "")) for k in ("id", "webpage_url", "channel_url",
                                                     "uploader_id", "channel")]
        except json.JSONDecodeError:
            pass
    hay += [str(v) for v in (meta or {}).values()]
    refs = {r[0] for r in con.execute("SELECT video_id FROM reference_videos")}
    for text in hay:
        for m in YT_ID.finditer(text):
            if m.group(1) in refs:
                return m.group(1)
    return ""
