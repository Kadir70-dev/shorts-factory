"""
Release checks for a rendered countdown. Every check measures the actual file
or the actual plates — nothing is assumed from the plan.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PIL import Image

from . import probe
from .plates import SAFE, SAFE_TOP, H, W


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "pass": bool(ok), "detail": detail}


def _streams(mp4: str) -> dict:
    import json
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                        "-of", "json", mp4], capture_output=True, text=True)
    return json.loads(r.stdout)


def black_intervals(mp4: str) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-vf",
                        "blackdetect=d=0.1:pix_th=0.06", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [(float(a), float(b)) for a, b in
            re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]


def plate_bbox(path: str, x: int, y: int) -> tuple[int, int, int, int]:
    """Opaque-pixel bounding box of a plate placed at (x, y), in frame coords."""
    img = Image.open(path).convert("RGBA")
    bb = img.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
    if bb is None:
        return (x, y, x, y)
    return (x + bb[0], y + bb[1], x + bb[2], y + bb[3])


def _touches_border(path: str) -> bool:
    """Opaque pixels on a plate's outer edge mean text was cut off."""
    a = Image.open(path).convert("RGBA").getchannel("A")
    w, h = a.size
    edge = [a.getpixel((x, 0)) for x in range(0, w, 3)] + \
           [a.getpixel((x, h - 1)) for x in range(0, w, 3)] + \
           [a.getpixel((0, y)) for y in range(0, h, 3)] + \
           [a.getpixel((w - 1, y)) for y in range(0, h, 3)]
    return max(edge) > 24


def analyze(manifest: dict, concept: dict, cfg: dict, dup_threshold: int = 10) -> dict:
    mp4 = manifest["mp4"]
    info = _streams(mp4)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    r = cfg.get("render", {})
    lo, hi = r.get("min_duration", 20), r.get("max_duration", 45)
    fps = probe._rate(v["avg_frame_rate"])
    checks = [
        _check("resolution", (v["width"], v["height"]) == (W, H), f"{v['width']}x{v['height']}"),
        _check("codec", v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p"
               and a is not None and a["codec_name"] == "aac",
               f"{v['codec_name']}/{v.get('pix_fmt')} + {(a or {}).get('codec_name')}"),
        _check("fps", abs(fps - 30) < 0.01, f"{fps:.3f}"),
        _check("duration", lo <= dur <= hi, f"{dur:.2f}s (target {lo}-{hi}s)"),
    ]
    if a is not None:
        vd, ad = float(v.get("duration", dur)), float(a.get("duration", dur))
        checks.append(_check("av_sync", abs(vd - ad) <= 0.05,
                             f"video {vd:.3f}s / audio {ad:.3f}s (Δ {abs(vd - ad) * 1000:.0f} ms)"))
    blacks = [b for b in black_intervals(mp4) if b[0] < dur - 0.4]  # outro fade allowed
    checks.append(_check("no_black_frames", not blacks, f"{blacks or 'none'}"))

    order = [p["part"] for p in manifest["timeline"]]
    expected = ["hook", "rank5", "rank4", "rank3", "rank2", "rank1", "outro"]
    ranks = {x["rank"]: x for x in concept["payload"]["ranks"]}
    # The approved payload is the editorial truth: a reviewer may reorder ranks
    # by taste, so scores are reported, not enforced.
    asc = all(ranks[k]["score"] <= ranks[k - 1]["score"] for k in (5, 4, 3, 2))
    checks.append(_check("ranking_order", order == expected and sorted(ranks) == [1, 2, 3, 4, 5],
                         f"{order}; scores ascending={asc}"
                         + ("" if asc else " (editorial order)")))

    seg_ids = [x["segment_id"] for x in concept["payload"]["ranks"]]
    hashes = [(x["segment_id"], probe.segment_hash(Path(x["path"]), x["in"], x["out"]))
              for x in concept["payload"]["ranks"]]
    close = [(i, j, probe.hash_distance(hi_, hj)) for n, (i, hi_) in enumerate(hashes)
             for j, hj in hashes[n + 1:] if probe.hash_distance(hi_, hj) <= dup_threshold]
    checks.append(_check("no_duplicate_segments", len(set(seg_ids)) == 5 and not close,
                         f"ids={seg_ids}; near-dupes={close or 'none'}"))

    lay, pl = manifest["layout"], manifest["plates"]
    boxes = {"title": plate_bbox(pl["title"], 0, lay["title_y"]),
             "hook": plate_bbox(pl["hook"], 0, lay["hook_y"])}
    for k in (5, 4, 3, 2, 1):
        boxes[f"badge{k}"] = plate_bbox(pl[f"badge{k}"], *lay["badge"])
        boxes[f"cap{k}"] = plate_bbox(pl[f"cap{k}"], *lay["caption"])
    def outside(name, b):
        z = SAFE_TOP if name == "title" else SAFE
        return (b[0] < z["left"] - 2 or b[2] > z["right"] + 2
                or b[1] < z["top"] or b[3] > z["bottom"])
    bad = {n: b for n, b in boxes.items() if outside(n, b)}
    clipped = [n for n in boxes if _touches_border(pl[n])]
    checks.append(_check("text_not_clipped", not clipped,
                         f"plates with ink on their edge: {clipped or 'none'}"))
    checks.append(_check("overlays_in_safe_area", not bad,
                         f"{len(boxes)} plates; outside={bad or 'none'}"))

    lr = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-vn", "-af",
                         "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", lr.stderr)
    lufs = float(m[-1]) if m else -99.0
    checks.append(_check("loudness", -15.0 <= lufs <= -13.0, f"{lufs:.1f} LUFS (target -14)"))

    rt = manifest["render_seconds"]
    checks.append(_check("cpu_performance", rt <= dur * 10,
                         f"{rt:.1f}s wall for {dur:.1f}s video ({rt / dur:.2f}x realtime)"))
    return {"pass": all(c["pass"] for c in checks), "duration": round(dur, 2),
            "checks": checks}


def format_report(rep: dict) -> str:
    lines = [f"QA {'PASS' if rep['pass'] else 'FAIL'} — {rep['duration']}s"]
    lines += [f"  [{'✓' if c['pass'] else '✗'}] {c['check']:<24} {c['detail']}"
              for c in rep["checks"]]
    return "\n".join(lines)
