"""
Ranking-format SOURCE videos: turn one Top-5 compilation into up to five
individual clip candidates, keeping where each came from.

  analyse_top5()  run segment_top5.detect(). At or above the confidence
                  threshold, save five clips (manual=0) with their original rank,
                  per-clip confidence, interest score and the rank-graphic box.
                  Below it, store only the suggestion for a human.
  set_bounds()    manual correction: six boundary times → five manual clips.

The clips are only catalogue entries. Selection still requires the source's
license, the rights to the clips INSIDE the compilation, and (if it traces to a
reference inventory) recorded permission. See db.eligible_source_sql().
"""
from __future__ import annotations

import json
from pathlib import Path

from . import catalog, probe, segment_top5


def _interest(path: Path, has_audio: bool) -> list[float]:
    motion = probe.motion_curve(path)
    loud = probe.loudness_curve(path) if has_audio else []
    return catalog.interest_curve(motion, loud)


def _score(curve: list[float], start: float, end: float) -> float:
    hz = probe.SAMPLE_HZ
    win = curve[int(start * hz):int(end * hz)] or [0.0]
    return round(0.6 * max(win) + 0.4 * sum(win) / len(win), 4)


def _save(con, src, moments: list[dict], confidence: float, manual: bool,
          labels: list[str] | None = None) -> list[int]:
    path = Path(src["path"])
    curve = _interest(path, bool(src["has_audio"]))
    con.execute("""DELETE FROM segments WHERE source_id=? AND (manual=0 OR ?)
                   AND id NOT IN (SELECT segment_id FROM segment_usage)""",
                (src["id"], int(manual)))
    origins = catalog._rights_for(path).get("moment_origins") or []
    ids = []
    for k, m in enumerate(moments):
        label = (labels or [""] * 5)[k] if labels and k < len(labels) else ""
        con.execute(
            """INSERT INTO segments (source_id, start, end, score, category, label,
                   phash, manual, source_rank, confidence, signals)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_id, start, end) DO UPDATE SET score=excluded.score,
                   label=CASE WHEN excluded.label != '' THEN excluded.label ELSE label END,
                   phash=excluded.phash, manual=excluded.manual,
                   source_rank=excluded.source_rank, confidence=excluded.confidence,
                   signals=excluded.signals""",
            (src["id"], m["start"], m["end"], _score(curve, m["start"], m["end"]),
             src["category"], label, probe.segment_hash(path, m["start"], m["end"]),
             int(manual), m["rank"], 1.0 if manual else confidence,
             json.dumps({"overlay_box": m.get("overlay_box"),
                         "origin": origins[k] if k < len(origins) else "",
                         "fsig": probe.footage_signature(path, m["start"], m["end"],
                                                         src["content_crop"] or "")})))
        cur = con.execute("SELECT id FROM segments WHERE source_id=? AND start=? AND end=?",
                          (src["id"], m["start"], m["end"]))
        ids.append(cur.fetchone()[0])
    return ids


def analyse_top5(con, source_id: int, order: str = "countdown",
                 labels: list[str] | None = None) -> dict:
    src = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if labels is None:                     # keep the source's moment annotations
        labels = catalog._rights_for(Path(src["path"])).get("moment_labels")
    info = {"width": src["width"], "height": src["height"]}
    res = segment_top5.detect(Path(src["path"]), info, bool(src["has_audio"]), order)
    crop = res.get("content_crop") or []
    con.execute("UPDATE sources SET segmentation=?, content_crop=? WHERE id=?",
                (json.dumps(res), ":".join(str(int(v)) for v in crop), source_id))
    saved = []
    if res.get("status") == "auto":
        saved = _save(con, src, res["moments"], res["confidence"], manual=False, labels=labels)
    else:                                   # keep nothing automatic from a weak guess
        con.execute("""DELETE FROM segments WHERE source_id=? AND manual=0
                       AND id NOT IN (SELECT segment_id FROM segment_usage)""", (source_id,))
    return {"status": res.get("status"), "confidence": res.get("confidence", 0.0),
            "bounds": res.get("bounds", []), "saved": len(saved),
            "content_crop": crop, "overlay_box": res.get("overlay_box")}


def set_bounds(con, source_id: int, bounds: list[float], order: str = "countdown",
               labels: list[str] | None = None) -> list[int]:
    """Human-set boundaries: [start, b1, b2, b3, b4, end] → five manual clips."""
    if len(bounds) != 6 or any(b >= a for a, b in zip(bounds[1:], bounds)):
        raise ValueError("need six strictly increasing times: start b1 b2 b3 b4 end")
    src = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if src is None:
        raise KeyError(f"source {source_id} not found")
    if bounds[0] < 0 or bounds[-1] > src["duration"] + 0.05:
        raise ValueError(f"bounds outside 0-{src['duration']}s")
    prev = json.loads(src["segmentation"] or "{}")
    box = prev.get("overlay_box")
    if labels is None:                     # keep the source's moment annotations
        labels = catalog._rights_for(Path(src["path"])).get("moment_labels")
    ranks = [5, 4, 3, 2, 1] if order == "countdown" else [1, 2, 3, 4, 5]
    moments = [{"rank": ranks[k], "start": round(a + 0.3, 2), "end": round(b - 0.15, 2),
                "overlay_box": box} for k, (a, b) in enumerate(zip(bounds, bounds[1:]))]
    prev.update(status="manual", bounds=bounds, order=order)
    con.execute("UPDATE sources SET segmentation=? WHERE id=?", (json.dumps(prev), source_id))
    return _save(con, src, moments, 1.0, manual=True, labels=labels)
